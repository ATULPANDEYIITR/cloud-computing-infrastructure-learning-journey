#include <algorithm>
#include <chrono>
#include <exception>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using Clock = std::chrono::steady_clock;

enum class CacheStrategy {
    CacheAside,
    WriteThrough
};

enum class CheckStatus {
    Passed,
    Failed
};

struct Product {
    int id;
    std::string name;
    double price;
    int stock;
    int version;
};

struct CacheEntry {
    Product product;
    Clock::time_point expiresAt;
};

struct Metrics {
    std::size_t hits = 0;
    std::size_t misses = 0;
    std::size_t writes = 0;
    std::size_t invalidations = 0;
    std::size_t staleRejections = 0;
    std::size_t distributedFailures = 0;

    double hitRate() const {
        const auto total = hits + misses;
        return total == 0
            ? 0.0
            : static_cast<double>(hits) / static_cast<double>(total);
    }
};

class CacheException : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class DistributedCacheUnavailable : public CacheException {
public:
    using CacheException::CacheException;
};

class ProductRepository {
private:
    std::unordered_map<int, Product> products_;

public:
    void seed(const Product& product) {
        products_[product.id] = product;
    }

    std::optional<Product> get(int id) const {
        auto it = products_.find(id);

        if (it == products_.end()) {
            return std::nullopt;
        }

        return it->second;
    }

    Product update(
        int id,
        std::optional<double> price,
        std::optional<int> stock
    ) {
        auto it = products_.find(id);

        if (it == products_.end()) {
            throw CacheException("product does not exist");
        }

        if (price && *price < 0.0) {
            throw CacheException("price cannot be negative");
        }

        if (stock && *stock < 0) {
            throw CacheException("stock cannot be negative");
        }

        if (price) {
            it->second.price = *price;
        }

        if (stock) {
            it->second.stock = *stock;
        }

        ++it->second.version;
        return it->second;
    }
};

class LocalCache {
private:
    std::size_t capacity_;
    std::unordered_map<std::string, CacheEntry> entries_;

public:
    explicit LocalCache(std::size_t capacity)
        : capacity_(capacity) {
        if (capacity == 0) {
            throw std::invalid_argument("cache capacity must be positive");
        }
    }

    std::optional<CacheEntry> get(const std::string& key) {
        auto it = entries_.find(key);

        if (it == entries_.end()) {
            return std::nullopt;
        }

        if (Clock::now() >= it->second.expiresAt) {
            entries_.erase(it);
            return std::nullopt;
        }

        return it->second;
    }

    void put(
        const std::string& key,
        const Product& product,
        std::chrono::seconds ttl
    ) {
        if (entries_.size() >= capacity_ &&
            entries_.find(key) == entries_.end()) {
            entries_.erase(entries_.begin());
        }

        entries_[key] = CacheEntry{
            product,
            Clock::now() + ttl
        };
    }

    void erase(const std::string& key) {
        entries_.erase(key);
    }

    std::size_t size() const {
        return entries_.size();
    }
};

class DistributedCache {
private:
    std::unordered_map<std::string, CacheEntry> entries_;
    bool available_ = true;

public:
    void setAvailable(bool available) {
        available_ = available;
    }

    std::optional<CacheEntry> get(const std::string& key) const {
        if (!available_) {
            throw DistributedCacheUnavailable(
                "distributed cache is unavailable"
            );
        }

        auto it = entries_.find(key);

        if (it == entries_.end()) {
            return std::nullopt;
        }

        if (Clock::now() >= it->second.expiresAt) {
            return std::nullopt;
        }

        return it->second;
    }

    void put(
        const std::string& key,
        const Product& product,
        std::chrono::seconds ttl
    ) {
        if (!available_) {
            throw DistributedCacheUnavailable(
                "distributed cache is unavailable"
            );
        }

        entries_[key] = CacheEntry{
            product,
            Clock::now() + ttl
        };
    }

    void erase(const std::string& key) {
        if (!available_) {
            throw DistributedCacheUnavailable(
                "distributed cache is unavailable"
            );
        }

        entries_.erase(key);
    }
};

class MergeEligibilityEngine {
private:
    ProductRepository& repository_;
    LocalCache& local_;
    DistributedCache& distributed_;
    Metrics metrics_;

    static std::string key(int id) {
        return "product:" + std::to_string(id);
    }

    void populateCaches(const Product& product) {
        const std::string cacheKey = key(product.id);

        local_.put(
            cacheKey,
            product,
            std::chrono::seconds(5)
        );

        try {
            distributed_.put(
                cacheKey,
                product,
                std::chrono::seconds(15)
            );
        } catch (const DistributedCacheUnavailable&) {
            ++metrics_.distributedFailures;
        }
    }

public:
    MergeEligibilityEngine(
        ProductRepository& repository,
        LocalCache& local,
        DistributedCache& distributed
    )
        : repository_(repository),
          local_(local),
          distributed_(distributed) {}

    std::optional<Product> getProduct(int id) {
        if (id <= 0) {
            throw std::invalid_argument("product id must be positive");
        }

        const std::string cacheKey = key(id);

        if (auto entry = local_.get(cacheKey)) {
            ++metrics_.hits;
            return entry->product;
        }

        ++metrics_.misses;

        try {
            if (auto entry = distributed_.get(cacheKey)) {
                auto authoritative = repository_.get(id);

                if (authoritative &&
                    entry->product.version >= authoritative->version) {
                    ++metrics_.hits;

                    local_.put(
                        cacheKey,
                        entry->product,
                        std::chrono::seconds(5)
                    );

                    return entry->product;
                }

                if (authoritative) {
                    ++metrics_.staleRejections;
                }
            }
        } catch (const DistributedCacheUnavailable&) {
            ++metrics_.distributedFailures;
        }

        ++metrics_.misses;

        auto product = repository_.get(id);

        if (!product) {
            return std::nullopt;
        }

        populateCaches(*product);
        return product;
    }

    Product cacheAsideUpdate(
        int id,
        std::optional<double> price,
        std::optional<int> stock
    ) {
        Product updated = repository_.update(id, price, stock);
        invalidate(id);
        return updated;
    }

    Product writeThroughUpdate(
        int id,
        std::optional<double> price,
        std::optional<int> stock
    ) {
        Product updated = repository_.update(id, price, stock);
        const std::string cacheKey = key(id);

        local_.put(
            cacheKey,
            updated,
            std::chrono::seconds(5)
        );

        try {
            distributed_.put(
                cacheKey,
                updated,
                std::chrono::seconds(15)
            );
        } catch (const DistributedCacheUnavailable&) {
            ++metrics_.distributedFailures;
        }

        ++metrics_.writes;
        return updated;
    }

    void invalidate(int id) {
        const std::string cacheKey = key(id);
        local_.erase(cacheKey);

        try {
            distributed_.erase(cacheKey);
        } catch (const DistributedCacheUnavailable&) {
            ++metrics_.distributedFailures;
        }

        ++metrics_.invalidations;
    }

    const Metrics& metrics() const {
        return metrics_;
    }
};

void printProduct(const std::optional<Product>& product) {
    if (!product) {
        std::cout << "NOT_FOUND\n";
        return;
    }

    std::cout
        << "id=" << product->id
        << ", name=" << product->name
        << ", price=" << std::fixed << std::setprecision(2)
        << product->price
        << ", stock=" << product->stock
        << ", version=" << product->version
        << '\n';
}

int main() {
    try {
        ProductRepository repository;

        repository.seed({
            9001,
            "Identity Service",
            55000.0,
            20,
            1
        });

        repository.seed({
            9002,
            "Event Processor",
            68000.0,
            8,
            1
        });

        LocalCache local(100);
        DistributedCache distributed;

        MergeEligibilityEngine engine(
            repository,
            local,
            distributed
        );

        std::cout << "=== Two-Tier Read Path ===\n";
        printProduct(engine.getProduct(9001));
        printProduct(engine.getProduct(9001));

        std::cout << "\n=== Cache-Aside Update ===\n";
        printProduct(
            engine.cacheAsideUpdate(
                9001,
                53000.0,
                std::nullopt
            )
        );
        printProduct(engine.getProduct(9001));

        std::cout << "\n=== Write-Through Update ===\n";
        printProduct(
            engine.writeThroughUpdate(
                9002,
                std::nullopt,
                6
            )
        );
        printProduct(engine.getProduct(9002));

        std::cout << "\n=== Distributed Failure ===\n";
        distributed.setAvailable(false);
        printProduct(engine.getProduct(9002));
        distributed.setAvailable(true);

        std::cout << "\n=== Missing Record ===\n";
        printProduct(engine.getProduct(9999));

        std::cout << "\n=== Invalid Update ===\n";
        try {
            engine.cacheAsideUpdate(
                9001,
                -10.0,
                std::nullopt
            );
        } catch (const std::exception& ex) {
            std::cout << "Rejected: " << ex.what() << '\n';
        }

        const Metrics& metrics = engine.metrics();

        std::cout << "\n=== Metrics ===\n";
        std::cout
            << "hits=" << metrics.hits << '\n'
            << "misses=" << metrics.misses << '\n'
            << "hit_rate=" << std::fixed
            << std::setprecision(3)
            << metrics.hitRate() << '\n'
            << "writes=" << metrics.writes << '\n'
            << "invalidations=" << metrics.invalidations << '\n'
            << "stale_rejections=" << metrics.staleRejections << '\n'
            << "distributed_failures="
            << metrics.distributedFailures << '\n';

        std::cout << "\n=== Design Properties ===\n";
        std::cout << "The repository remains the authoritative data source.\n";
        std::cout << "Local cache provides low-latency process-local reads.\n";
        std::cout << "Distributed cache shares entries across application instances.\n";
        std::cout << "Versions prevent an older remote entry from replacing newer data.\n";

        if (!repository.get(9001) ||
            repository.get(9001)->price != 53000.0) {
            throw std::logic_error("price invariant failed");
        }

        if (!repository.get(9002) ||
            repository.get(9002)->stock != 6) {
            throw std::logic_error("stock invariant failed");
        }

        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Fatal error: " << ex.what() << '\n';
        return 1;
    }
}
