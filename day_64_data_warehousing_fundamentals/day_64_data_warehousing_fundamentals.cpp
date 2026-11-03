#include <algorithm>
#include <chrono>
#include <cmath>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class LoadStrategy {
    ETL,
    ELT
};

enum class PipelineState {
    Created,
    Extracted,
    Validated,
    Loaded,
    Failed
};

struct SalesRecord {
    int orderId{};
    std::string orderDate;
    int customerId{};
    int productId{};
    std::string region;
    int quantity{};
    double unitPrice{};

    double revenue() const {
        return quantity * unitPrice;
    }
};

struct WarehouseFact {
    int orderId{};
    int dateKey{};
    int customerId{};
    int productId{};
    std::string region;
    int quantity{};
    double revenue{};
};

struct PipelineReport {
    PipelineState state{PipelineState::Created};
    std::size_t extracted{};
    std::size_t rejected{};
    std::size_t loaded{};
    std::vector<std::string> errors;
};

class ValidationError : public std::runtime_error {
public:
    explicit ValidationError(const std::string& message)
        : std::runtime_error(message) {}
};

class PipelineError : public std::runtime_error {
public:
    explicit PipelineError(const std::string& message)
        : std::runtime_error(message) {}
};

class OLTPStore {
private:
    std::unordered_map<int, SalesRecord> orders_;

public:
    void insert(const SalesRecord& record) {
        validate(record);

        if (orders_.contains(record.orderId)) {
            throw ValidationError("Duplicate order ID: " +
                                  std::to_string(record.orderId));
        }

        orders_.emplace(record.orderId, record);
    }

    std::vector<SalesRecord> extract() const {
        std::vector<SalesRecord> records;
        records.reserve(orders_.size());

        for (const auto& [id, record] : orders_) {
            records.push_back(record);
        }

        std::sort(
            records.begin(),
            records.end(),
            [](const SalesRecord& a, const SalesRecord& b) {
                return a.orderId < b.orderId;
            });

        return records;
    }

private:
    static void validate(const SalesRecord& record) {
        if (record.orderId <= 0) {
            throw ValidationError("Order ID must be positive");
        }

        if (record.customerId <= 0 || record.productId <= 0) {
            throw ValidationError("Dimension IDs must be positive");
        }

        if (record.orderDate.size() != 10 ||
            record.orderDate[4] != '-' ||
            record.orderDate[7] != '-') {
            throw ValidationError("Date must use YYYY-MM-DD");
        }

        if (record.quantity <= 0) {
            throw ValidationError("Quantity must be positive");
        }

        if (record.unitPrice < 0.0) {
            throw ValidationError("Unit price cannot be negative");
        }

        if (record.region.empty()) {
            throw ValidationError("Region cannot be empty");
        }
    }
};

class DataWarehouse {
private:
    std::map<int, std::string> dimDate_;
    std::set<int> dimCustomers_;
    std::set<int> dimProducts_;
    std::vector<WarehouseFact> facts_;

    static int dateKey(const std::string& date) {
        std::string digits = date;
        digits.erase(
            std::remove(digits.begin(), digits.end(), '-'),
            digits.end()
        );
        return std::stoi(digits);
    }

public:
    void loadDimensions(const std::vector<SalesRecord>& records) {
        for (const auto& record : records) {
            dimDate_[dateKey(record.orderDate)] = record.orderDate;
            dimCustomers_.insert(record.customerId);
            dimProducts_.insert(record.productId);
        }
    }

    void loadFacts(const std::vector<SalesRecord>& records) {
        std::set<int> existing;
        for (const auto& fact : facts_) {
            existing.insert(fact.orderId);
        }

        for (const auto& record : records) {
            if (existing.contains(record.orderId)) {
                throw PipelineError(
                    "Fact already exists for order " +
                    std::to_string(record.orderId)
                );
            }

            facts_.push_back({
                record.orderId,
                dateKey(record.orderDate),
                record.customerId,
                record.productId,
                record.region,
                record.quantity,
                std::round(record.revenue() * 100.0) / 100.0
            });
        }
    }

    std::map<std::string, double> revenueByRegion() const {
        std::map<std::string, double> result;

        for (const auto& fact : facts_) {
            result[fact.region] += fact.revenue;
        }

        return result;
    }

    std::map<std::string, double> revenueByMonth() const {
        std::map<std::string, double> result;

        for (const auto& fact : facts_) {
            const std::string& date = dimDate_.at(fact.dateKey);
            result[date.substr(0, 7)] += fact.revenue;
        }

        return result;
    }

    double totalRevenue() const {
        return std::accumulate(
            facts_.begin(),
            facts_.end(),
            0.0,
            [](double total, const WarehouseFact& fact) {
                return total + fact.revenue;
            }
        );
    }

    const std::vector<WarehouseFact>& facts() const {
        return facts_;
    }
};

static SalesRecord transform(SalesRecord record) {
    std::transform(
        record.region.begin(),
        record.region.end(),
        record.region.begin(),
        [](unsigned char c) {
            return static_cast<char>(std::toupper(c));
        }
    );

    record.unitPrice =
        std::round(record.unitPrice * 100.0) / 100.0;

    return record;
}

PipelineReport runPipeline(
    const OLTPStore& source,
    DataWarehouse& warehouse,
    LoadStrategy strategy
) {
    PipelineReport report;

    try {
        const auto extracted = source.extract();

        report.extracted = extracted.size();
        report.state = PipelineState::Extracted;

        std::vector<SalesRecord> valid;
        valid.reserve(extracted.size());

        for (const auto& record : extracted) {
            try {
                valid.push_back(transform(record));
            } catch (const std::exception& error) {
                ++report.rejected;
                report.errors.push_back(
                    "Order " + std::to_string(record.orderId) +
                    ": " + error.what()
                );
            }
        }

        report.state = PipelineState::Validated;

        if (strategy == LoadStrategy::ETL) {
            warehouse.loadDimensions(valid);
            warehouse.loadFacts(valid);
        } else {
            // ELT loads source-shaped data before warehouse transformation.
            warehouse.loadDimensions(extracted);
            warehouse.loadFacts(valid);
        }

        report.loaded = valid.size();
        report.state = PipelineState::Loaded;
    } catch (const std::exception& error) {
        report.state = PipelineState::Failed;
        report.errors.push_back(error.what());
    }

    return report;
}

static std::string stateName(PipelineState state) {
    switch (state) {
        case PipelineState::Created: return "created";
        case PipelineState::Extracted: return "extracted";
        case PipelineState::Validated: return "validated";
        case PipelineState::Loaded: return "loaded";
        case PipelineState::Failed: return "failed";
    }
    return "unknown";
}

int main() {
    try {
        OLTPStore source;

        source.insert({3001, "2026-01-10", 801, 4001, "North", 5, 120.00});
        source.insert({3002, "2026-01-14", 802, 4002, "South", 3, 250.00});
        source.insert({3003, "2026-02-04", 801, 4001, "North", 7, 120.00});
        source.insert({3004, "2026-02-18", 803, 4003, "West", 2, 450.00});
        source.insert({3005, "2026-03-01", 804, 4002, "East", 4, 250.00});

        try {
            source.insert(
                {3006, "2026-03-05", 805, 4004, "North", -1, 90.00}
            );
        } catch (const ValidationError& error) {
            std::cout << "Invalid OLTP transaction rejected: "
                      << error.what() << "\n";
        }

        DataWarehouse warehouse;

        const auto report =
            runPipeline(source, warehouse, LoadStrategy::ETL);

        std::cout << "\nPipeline state: "
                  << stateName(report.state) << "\n";
        std::cout << "Extracted: " << report.extracted << "\n";
        std::cout << "Rejected: " << report.rejected << "\n";
        std::cout << "Loaded: " << report.loaded << "\n";

        if (!report.errors.empty()) {
            std::cout << "Errors:\n";
            for (const auto& error : report.errors) {
                std::cout << "  " << error << "\n";
            }
        }

        std::cout << std::fixed << std::setprecision(2);

        std::cout << "\nRevenue by region:\n";
        for (const auto& [region, amount] :
             warehouse.revenueByRegion()) {
            std::cout << "  " << region << ": " << amount << "\n";
        }

        std::cout << "\nRevenue by month:\n";
        for (const auto& [month, amount] :
             warehouse.revenueByMonth()) {
            std::cout << "  " << month << ": " << amount << "\n";
        }

        std::cout << "\nTotal warehouse revenue: "
                  << warehouse.totalRevenue() << "\n";

        // Analytical scan demonstrates projection of only required fields.
        std::cout << "\nHigh-value facts:\n";
        for (const auto& fact : warehouse.facts()) {
            if (fact.revenue >= 500.0) {
                std::cout << "  order=" << fact.orderId
                          << ", region=" << fact.region
                          << ", revenue=" << fact.revenue
                          << "\n";
            }
        }

        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << "\n";
        return 1;
    }
}
