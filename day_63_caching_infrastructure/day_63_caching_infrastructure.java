import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

public class CacheInfrastructureDemo {

    enum CacheStrategy {
        CACHE_ASIDE,
        WRITE_THROUGH
    }

    enum CacheLayer {
        LOCAL,
        DISTRIBUTED
    }

    record Product(
        int id,
        String name,
        double price,
        int stock,
        long version
    ) {
        Product {
            if (id <= 0) {
                throw new IllegalArgumentException("id must be positive");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name cannot be blank");
            }
            if (!Double.isFinite(price) || price < 0) {
                throw new IllegalArgumentException("price is invalid");
            }
            if (stock < 0) {
                throw new IllegalArgumentException("stock cannot be negative");
            }
        }

        Product withChanges(Double newPrice, Integer newStock) {
            return new Product(
                id,
                name,
                newPrice == null ? price : newPrice,
                newStock == null ? stock : newStock,
                version + 1
            );
        }
    }

    record CacheEntry<T>(
        T value,
        Instant expiresAt,
        long version
    ) {
        boolean expired() {
            return expiresAt != null && Instant.now().isAfter(expiresAt);
        }
    }

    record CacheMetrics(
        long hits,
        long misses,
        long writes,
        long invalidations,
        long staleRejections,
        long distributedFailures
    ) {
        double hitRate() {
            long total = hits + misses;
            return total == 0 ? 0.0 : (double) hits / total;
        }
    }

    interface CacheStore<T> {
        Optional<CacheEntry<T>> get(String key);
        void put(String key, T value, Duration ttl, long version);
        void delete(String key);
    }

    static final class DistributedCacheUnavailable
        extends RuntimeException {

        DistributedCacheUnavailable(String message) {
            super(message);
        }
    }

    static final class InMemoryCache<T>
        implements CacheStore<T> {

        private final int capacity;
        private final Map<String, CacheEntry<T>> entries =
            new ConcurrentHashMap<>();

        InMemoryCache(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException(
                    "capacity must be positive"
                );
            }
            this.capacity = capacity;
        }

        @Override
        public Optional<CacheEntry<T>> get(String key) {
            CacheEntry<T> entry = entries.get(key);

            if (entry == null) {
                return Optional.empty();
            }

            if (entry.expired()) {
                entries.remove(key);
                return Optional.empty();
            }

            return Optional.of(entry);
        }

        @Override
        public synchronized void put(
            String key,
            T value,
            Duration ttl,
            long version
        ) {
            if (entries.size() >= capacity &&
                !entries.containsKey(key)) {

                String evictionKey =
                    entries.keySet().stream().findFirst().orElse(null);

                if (evictionKey != null) {
                    entries.remove(evictionKey);
                }
            }

            entries.put(
                key,
                new CacheEntry<>(
                    value,
                    Instant.now().plus(ttl),
                    version
                )
            );
        }

        @Override
        public void delete(String key) {
            entries.remove(key);
        }
    }

    static final class DistributedCache<T>
        implements CacheStore<T> {

        private final Map<String, CacheEntry<T>> entries =
            new ConcurrentHashMap<>();

        private volatile boolean available = true;

        void setAvailable(boolean available) {
            this.available = available;
        }

        private void ensureAvailable() {
            if (!available) {
                throw new DistributedCacheUnavailable(
                    "distributed cache is unavailable"
                );
            }
        }

        @Override
        public Optional<CacheEntry<T>> get(String key) {
            ensureAvailable();

            CacheEntry<T> entry = entries.get(key);

            if (entry == null || entry.expired()) {
                return Optional.empty();
            }

            return Optional.of(entry);
        }

        @Override
        public void put(
            String key,
            T value,
            Duration ttl,
            long version
        ) {
            ensureAvailable();

            entries.put(
                key,
                new CacheEntry<>(
                    value,
                    Instant.now().plus(ttl),
                    version
                )
            );
        }

        @Override
        public void delete(String key) {
            ensureAvailable();
            entries.remove(key);
        }
    }

    static final class ProductRepository {

        private final Map<Integer, Product> products =
            new ConcurrentHashMap<>();

        void seed(Product product) {
            products.put(product.id(), product);
        }

        Optional<Product> find(int id) {
            return Optional.ofNullable(products.get(id));
        }

        synchronized Product update(
            int id,
            Double price,
            Integer stock
        ) {
            Product current = products.get(id);

            if (current == null) {
                throw new IllegalArgumentException(
                    "product does not exist"
                );
            }

            Product updated = current.withChanges(price, stock);
            products.put(id, updated);

            return updated;
        }
    }

    static final class CacheService {

        private final ProductRepository repository;
        private final InMemoryCache<Product> local;
        private final DistributedCache<Product> distributed;

        private final Duration localTtl = Duration.ofSeconds(5);
        private final Duration distributedTtl = Duration.ofSeconds(15);

        private final AtomicLong hits = new AtomicLong();
        private final AtomicLong misses = new AtomicLong();
        private final AtomicLong writes = new AtomicLong();
        private final AtomicLong invalidations = new AtomicLong();
        private final AtomicLong staleRejections = new AtomicLong();
        private final AtomicLong distributedFailures =
            new AtomicLong();

        CacheService(
            ProductRepository repository,
            InMemoryCache<Product> local,
            DistributedCache<Product> distributed
        ) {
            this.repository = Objects.requireNonNull(repository);
            this.local = Objects.requireNonNull(local);
            this.distributed = Objects.requireNonNull(distributed);
        }

        private String key(int id) {
            return "product:" + id;
        }

        Optional<Product> get(int id) {
            if (id <= 0) {
                throw new IllegalArgumentException(
                    "product id must be positive"
                );
            }

            String key = key(id);

            Optional<CacheEntry<Product>> localEntry =
                local.get(key);

            if (localEntry.isPresent()) {
                hits.incrementAndGet();
                return Optional.of(localEntry.get().value());
            }

            misses.incrementAndGet();

            try {
                Optional<CacheEntry<Product>> remoteEntry =
                    distributed.get(key);

                if (remoteEntry.isPresent()) {
                    Optional<Product> authoritative =
                        repository.find(id);

                    if (authoritative.isPresent() &&
                        remoteEntry.get().version()
                            >= authoritative.get().version()) {

                        hits.incrementAndGet();

                        local.put(
                            key,
                            remoteEntry.get().value(),
                            localTtl,
                            remoteEntry.get().version()
                        );

                        return Optional.of(
                            remoteEntry.get().value()
                        );
                    }

                    if (authoritative.isPresent()) {
                        staleRejections.incrementAndGet();
                    }
                }
            } catch (DistributedCacheUnavailable ex) {
                distributedFailures.incrementAndGet();
            }

            misses.incrementAndGet();

            Optional<Product> authoritative =
                repository.find(id);

            if (authoritative.isEmpty()) {
                return Optional.empty();
            }

            Product product = authoritative.get();

            local.put(
                key,
                product,
                localTtl,
                product.version()
            );

            try {
                distributed.put(
                    key,
                    product,
                    distributedTtl,
                    product.version()
                );
            } catch (DistributedCacheUnavailable ex) {
                distributedFailures.incrementAndGet();
            }

            return Optional.of(product);
        }

        Product cacheAsideUpdate(
            int id,
            Double price,
            Integer stock
        ) {
            Product updated =
                repository.update(id, price, stock);

            invalidate(id);
            return updated;
        }

        Product writeThroughUpdate(
            int id,
            Double price,
            Integer stock
        ) {
            Product updated =
                repository.update(id, price, stock);

            String key = key(id);

            local.put(
                key,
                updated,
                localTtl,
                updated.version()
            );

            try {
                distributed.put(
                    key,
                    updated,
                    distributedTtl,
                    updated.version()
                );
            } catch (DistributedCacheUnavailable ex) {
                distributedFailures.incrementAndGet();
            }

            writes.incrementAndGet();
            return updated;
        }

        void invalidate(int id) {
            String key = key(id);
            local.delete(key);

            try {
                distributed.delete(key);
            } catch (DistributedCacheUnavailable ex) {
                distributedFailures.incrementAndGet();
            }

            invalidations.incrementAndGet();
        }

        CacheMetrics metrics() {
            return new CacheMetrics(
                hits.get(),
                misses.get(),
                writes.get(),
                invalidations.get(),
                staleRejections.get(),
                distributedFailures.get()
            );
        }
    }

    static void printProduct(Optional<Product> product) {
        if (product.isEmpty()) {
            System.out.println("NOT_FOUND");
        } else {
            System.out.println(product.get());
        }
    }

    public static void main(String[] args) {
        ProductRepository repository =
            new ProductRepository();

        repository.seed(
            new Product(
                3001,
                "Payment Gateway",
                99000,
                15,
                1
            )
        );

        repository.seed(
            new Product(
                3002,
                "Audit Platform",
                76000,
                6,
                1
            )
        );

        InMemoryCache<Product> local =
            new InMemoryCache<>(100);

        DistributedCache<Product> distributed =
            new DistributedCache<>();

        CacheService service =
            new CacheService(
                repository,
                local,
                distributed
            );

        System.out.println("=== Cache-Aside Read ===");
        printProduct(service.get(3001));
        printProduct(service.get(3001));

        System.out.println("\n=== Cache-Aside Update ===");
        System.out.println(
            service.cacheAsideUpdate(
                3001,
                95000.0,
                null
            )
        );
        printProduct(service.get(3001));

        System.out.println("\n=== Write-Through Update ===");
        System.out.println(
            service.writeThroughUpdate(
                3002,
                null,
                5
            )
        );
        printProduct(service.get(3002));

        System.out.println("\n=== Distributed Failure ===");
        distributed.setAvailable(false);
        printProduct(service.get(3002));
        distributed.setAvailable(true);

        System.out.println("\n=== Missing Product ===");
        printProduct(service.get(9999));

        System.out.println("\n=== Validation ===");
        try {
            service.cacheAsideUpdate(
                3001,
                -500.0,
                null
            );
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "Rejected invalid price: " + ex.getMessage()
            );
        }

        CacheMetrics metrics = service.metrics();

        System.out.println("\n=== Metrics ===");
        System.out.println("hits=" + metrics.hits());
        System.out.println("misses=" + metrics.misses());
        System.out.printf(
            "hitRate=%.3f%n",
            metrics.hitRate()
        );
        System.out.println(
            "writes=" + metrics.writes()
        );
        System.out.println(
            "invalidations=" + metrics.invalidations()
        );
        System.out.println(
            "staleRejections=" + metrics.staleRejections()
        );
        System.out.println(
            "distributedFailures=" +
            metrics.distributedFailures()
        );

        System.out.println("\n=== Enterprise Controls ===");
        System.out.println(
            "Repository versions are authoritative."
        );
        System.out.println(
            "Local cache uses short TTL for low latency."
        );
        System.out.println(
            "Distributed cache uses longer TTL for cross-instance reuse."
        );
        System.out.println(
            "A remote entry cannot overwrite a newer repository version."
        );
    }
}
