import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class CdnGovernanceDemo {

    enum CacheStatus {
        HIT,
        MISS,
        STALE,
        BYPASS
    }

    enum ContentClass {
        PUBLIC_STATIC,
        PUBLIC_DYNAMIC,
        PRIVATE
    }

    record EdgeLocation(
        String name,
        String region,
        int capacity
    ) {
        EdgeLocation {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Edge name is required");
            }
            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException("Edge region is required");
            }
            if (capacity <= 0) {
                throw new IllegalArgumentException("Edge capacity must be positive");
            }
        }
    }

    record OriginObject(
        String path,
        String body,
        String contentType,
        int version,
        String etag,
        Instant updatedAt
    ) {}

    record CacheEntry(
        String body,
        String etag,
        int version,
        Instant createdAt,
        Instant expiresAt
    ) {
        boolean fresh(Instant now) {
            return now.isBefore(expiresAt);
        }
    }

    record DeliveryResult(
        CacheStatus status,
        String edge,
        String source,
        String etag,
        int version,
        Duration latency
    ) {}

    interface OriginRepository {
        OriginObject publish(
            String path,
            String body,
            String contentType
        );

        OriginObject fetch(String path);
    }

    static final class InMemoryOrigin implements OriginRepository {
        private final Map<String, OriginObject> objects = new HashMap<>();

        @Override
        public OriginObject publish(
            String path,
            String body,
            String contentType
        ) {
            validatePath(path);

            if (body == null || body.isBlank()) {
                throw new IllegalArgumentException(
                    "Origin body cannot be empty"
                );
            }

            OriginObject previous = objects.get(path);
            int version = previous == null ? 1 : previous.version() + 1;

            String etag = '"' + sha256(path + ":" + version + ":" + body) + '"';

            OriginObject object = new OriginObject(
                path,
                body,
                contentType,
                version,
                etag,
                Instant.now()
            );

            objects.put(path, object);
            return object;
        }

        @Override
        public OriginObject fetch(String path) {
            validatePath(path);

            OriginObject object = objects.get(path);

            if (object == null) {
                throw new IllegalStateException(
                    "Origin object not found: " + path
                );
            }

            return object;
        }
    }

    static final class EdgeCache {
        private final EdgeLocation location;
        private final Map<String, CacheEntry> entries = new HashMap<>();

        private long hits;
        private long misses;
        private long invalidations;

        EdgeCache(EdgeLocation location) {
            this.location = Objects.requireNonNull(location);
        }

        Optional<CacheEntry> lookup(
            String path,
            Instant now
        ) {
            CacheEntry entry = entries.get(path);

            if (entry == null) {
                misses++;
                return Optional.empty();
            }

            if (!entry.fresh(now)) {
                misses++;
                return Optional.empty();
            }

            hits++;
            return Optional.of(entry);
        }

        void store(
            String path,
            OriginObject origin,
            Duration ttl,
            Instant now
        ) {
            if (!entries.containsKey(path) &&
                entries.size() >= location.capacity()) {

                String victim = entries.entrySet()
                    .stream()
                    .min(Comparator.comparing(
                        entry -> entry.getValue().expiresAt()
                    ))
                    .map(Map.Entry::getKey)
                    .orElseThrow();

                entries.remove(victim);
            }

            entries.put(
                path,
                new CacheEntry(
                    origin.body(),
                    origin.etag(),
                    origin.version(),
                    now,
                    now.plus(ttl)
                )
            );
        }

        boolean invalidate(String path) {
            boolean removed = entries.remove(path) != null;

            if (removed) {
                invalidations++;
            }

            return removed;
        }

        int invalidatePrefix(String prefix) {
            List<String> paths = entries.keySet()
                .stream()
                .filter(path -> path.startsWith(prefix))
                .toList();

            paths.forEach(entries::remove);
            invalidations += paths.size();

            return paths.size();
        }
    }

    static final class ContentDeliveryNetwork {
        private final OriginRepository origin;
        private final List<EdgeCache> edges;
        private final Map<String, Integer> latency = new HashMap<>();

        private long requests;
        private long originFetches;

        ContentDeliveryNetwork(
            OriginRepository origin,
            List<EdgeLocation> locations
        ) {
            this.origin = Objects.requireNonNull(origin);

            if (locations.isEmpty()) {
                throw new IllegalArgumentException(
                    "At least one edge is required"
                );
            }

            this.edges = locations.stream()
                .map(EdgeCache::new)
                .toList();

            configureLatency();
        }

        private void configureLatency() {
            latency.put("India:India", 20);
            latency.put("India:Europe", 115);
            latency.put("India:North America", 210);

            latency.put("Europe:India", 115);
            latency.put("Europe:Europe", 25);
            latency.put("Europe:North America", 90);

            latency.put("North America:India", 210);
            latency.put("North America:Europe", 90);
            latency.put("North America:North America", 25);
        }

        private int latency(
            String clientRegion,
            String edgeRegion
        ) {
            return latency.getOrDefault(
                clientRegion + ":" + edgeRegion,
                150
            );
        }

        private EdgeCache selectEdge(String clientRegion) {
            return edges.stream()
                .min(Comparator.comparingInt(
                    edge -> latency(
                        clientRegion,
                        edge.location.region()
                    )
                ))
                .orElseThrow();
        }

        DeliveryResult deliver(
            String path,
            String clientRegion,
            Duration ttl,
            ContentClass contentClass,
            Optional<String> ifNoneMatch
        ) {
            validatePath(path);

            if (ttl.isNegative()) {
                throw new IllegalArgumentException(
                    "TTL cannot be negative"
                );
            }

            requests++;

            EdgeCache edge = selectEdge(clientRegion);
            Instant now = Instant.now();

            boolean bypass =
                contentClass == ContentClass.PRIVATE;

            if (!bypass) {
                Optional<CacheEntry> cached =
                    edge.lookup(path, now);

                if (cached.isPresent()) {
                    CacheEntry entry = cached.get();

                    if (ifNoneMatch.isPresent() &&
                        ifNoneMatch.get().equals(entry.etag())) {

                        return new DeliveryResult(
                            CacheStatus.HIT,
                            edge.location.name(),
                            "edge-validation",
                            entry.etag(),
                            entry.version(),
                            Duration.ofMillis(
                                latency(
                                    clientRegion,
                                    edge.location.region()
                                )
                            )
                        );
                    }

                    return new DeliveryResult(
                        CacheStatus.HIT,
                        edge.location.name(),
                        "edge",
                        entry.etag(),
                        entry.version(),
                        Duration.ofMillis(
                            latency(
                                clientRegion,
                                edge.location.region()
                            )
                        )
                    );
                }
            }

            OriginObject object = origin.fetch(path);
            originFetches++;

            if (!bypass) {
                edge.store(path, object, ttl, now);
            }

            if (ifNoneMatch.isPresent() &&
                ifNoneMatch.get().equals(object.etag())) {

                return new DeliveryResult(
                    CacheStatus.MISS,
                    edge.location.name(),
                    "origin-validation",
                    object.etag(),
                    object.version(),
                    Duration.ofMillis(
                        latency(
                            clientRegion,
                            edge.location.region()
                        ) + 80
                    )
                );
            }

            return new DeliveryResult(
                bypass ? CacheStatus.BYPASS : CacheStatus.MISS,
                edge.location.name(),
                "origin",
                object.etag(),
                object.version(),
                Duration.ofMillis(
                    latency(
                        clientRegion,
                        edge.location.region()
                    ) + 80
                )
            );
        }

        int invalidate(String path) {
            int count = 0;

            for (EdgeCache edge : edges) {
                if (edge.invalidate(path)) {
                    count++;
                }
            }

            return count;
        }

        int invalidatePrefix(String prefix) {
            return edges.stream()
                .mapToInt(edge -> edge.invalidatePrefix(prefix))
                .sum();
        }

        long originFetches() {
            return originFetches;
        }

        long requests() {
            return requests;
        }

        long cacheHits() {
            return edges.stream()
                .mapToLong(edge -> edge.hits)
                .sum();
        }
    }

    record CachePolicy(
        Duration defaultTtl,
        EnumSet<ContentClass> cacheableClasses,
        boolean requireVersionedAssets
    ) {
        CachePolicy {
            if (defaultTtl.isNegative() || defaultTtl.isZero()) {
                throw new IllegalArgumentException(
                    "Default TTL must be positive"
                );
            }

            cacheableClasses = cacheableClasses.clone();
        }

        boolean allows(ContentClass contentClass) {
            return cacheableClasses.contains(contentClass);
        }
    }

    static final class RepositoryDeliveryService {
        private final ContentDeliveryNetwork cdn;
        private final CachePolicy policy;

        RepositoryDeliveryService(
            ContentDeliveryNetwork cdn,
            CachePolicy policy
        ) {
            this.cdn = Objects.requireNonNull(cdn);
            this.policy = Objects.requireNonNull(policy);
        }

        DeliveryResult deliverAsset(
            String path,
            String region,
            Optional<String> validator
        ) {
            if (!policy.allows(ContentClass.PUBLIC_STATIC)) {
                throw new IllegalStateException(
                    "Static content caching is disabled by policy"
                );
            }

            if (policy.requireVersionedAssets() &&
                !path.matches(".+\\.[a-f0-9]{8,}\\.(js|css|png|svg)$")) {

                throw new IllegalArgumentException(
                    "Static assets must use content-versioned names"
                );
            }

            return cdn.deliver(
                path,
                region,
                policy.defaultTtl(),
                ContentClass.PUBLIC_STATIC,
                validator
            );
        }
    }

    static void validatePath(String path) {
        if (path == null ||
            path.isBlank() ||
            !path.startsWith("/")) {

            throw new IllegalArgumentException(
                "Path must be an absolute URL path"
            );
        }
    }

    static String sha256(String value) {
        try {
            var digest =
                java.security.MessageDigest.getInstance("SHA-256");

            byte[] bytes =
                digest.digest(value.getBytes(
                    java.nio.charset.StandardCharsets.UTF_8
                ));

            StringBuilder result = new StringBuilder();

            for (byte valueByte : bytes) {
                result.append(String.format("%02x", valueByte));
            }

            return result.toString();
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException(
                "SHA-256 is unavailable",
                error
            );
        }
    }

    public static void main(String[] args) {
        InMemoryOrigin origin = new InMemoryOrigin();

        origin.publish(
            "/assets/app.a91f42d7.js",
            "release-1",
            "application/javascript"
        );

        origin.publish(
            "/images/logo.52ab11ef.svg",
            "<svg>cdn</svg>",
            "image/svg+xml"
        );

        ContentDeliveryNetwork cdn =
            new ContentDeliveryNetwork(
                origin,
                List.of(
                    new EdgeLocation("delhi-1", "India", 100),
                    new EdgeLocation("frankfurt-1", "Europe", 100),
                    new EdgeLocation("virginia-1", "North America", 100)
                )
            );

        CachePolicy policy =
            new CachePolicy(
                Duration.ofMinutes(10),
                EnumSet.of(ContentClass.PUBLIC_STATIC),
                true
            );

        RepositoryDeliveryService service =
            new RepositoryDeliveryService(cdn, policy);

        DeliveryResult first =
            service.deliverAsset(
                "/assets/app.a91f42d7.js",
                "India",
                Optional.empty()
            );

        DeliveryResult second =
            service.deliverAsset(
                "/assets/app.a91f42d7.js",
                "India",
                Optional.of(first.etag())
            );

        System.out.println("First delivery: " + first);
        System.out.println("Validated delivery: " + second);

        int invalidated =
            cdn.invalidate("/assets/app.a91f42d7.js");

        System.out.println(
            "Invalidated edge copies: " + invalidated
        );

        DeliveryResult refreshed =
            service.deliverAsset(
                "/assets/app.a91f42d7.js",
                "India",
                Optional.empty()
            );

        System.out.println("After invalidation: " + refreshed);

        DeliveryResult privateConfig =
            cdn.deliver(
                "/images/logo.52ab11ef.svg",
                "Europe",
                Duration.ofMinutes(10),
                ContentClass.PRIVATE,
                Optional.empty()
            );

        System.out.println(
            "Private-content delivery: " + privateConfig
        );

        System.out.println(
            "Requests=" + cdn.requests() +
            ", originFetches=" + cdn.originFetches() +
            ", cacheHits=" + cdn.cacheHits()
        );
    }
}
