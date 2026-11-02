"use strict";

const crypto = require("node:crypto");

class CacheError extends Error {}
class DistributedCacheUnavailable extends CacheError {}

class CacheEntry {
    constructor(value, expiresAt, version) {
        this.value = value;
        this.expiresAt = expiresAt;
        this.version = version;
    }

    isExpired() {
        return this.expiresAt !== null && Date.now() >= this.expiresAt;
    }
}

class LocalCache {
    constructor(maxEntries = 1000) {
        if (!Number.isInteger(maxEntries) || maxEntries <= 0) {
            throw new Error("maxEntries must be positive");
        }
        this.maxEntries = maxEntries;
        this.entries = new Map();
    }

    get(key) {
        const entry = this.entries.get(key);
        if (!entry) return null;

        if (entry.isExpired()) {
            this.entries.delete(key);
            return null;
        }

        return entry;
    }

    put(key, value, ttlMs, version) {
        if (!key) throw new Error("cache key cannot be empty");
        if (ttlMs !== null && ttlMs <= 0) {
            throw new Error("TTL must be positive");
        }

        if (this.entries.size >= this.maxEntries && !this.entries.has(key)) {
            const firstKey = this.entries.keys().next().value;
            this.entries.delete(firstKey);
        }

        const expiresAt = ttlMs === null ? null : Date.now() + ttlMs;
        this.entries.set(key, new CacheEntry(value, expiresAt, version));
    }

    delete(key) {
        return this.entries.delete(key);
    }
}

class DistributedCache {
    constructor() {
        this.entries = new Map();
        this.available = true;
    }

    ensureAvailable() {
        if (!this.available) {
            throw new DistributedCacheUnavailable(
                "distributed cache service unavailable"
            );
        }
    }

    get(key) {
        this.ensureAvailable();
        const serialized = this.entries.get(key);
        if (!serialized) return null;

        const data = JSON.parse(serialized);
        return new CacheEntry(
            data.value,
            data.expiresAt,
            data.version
        );
    }

    put(key, value, ttlMs, version) {
        this.ensureAvailable();

        const expiresAt = ttlMs === null ? null : Date.now() + ttlMs;

        // Serialization is intentional: remote cache values must cross a
        // process boundary using a controlled representation.
        const serialized = JSON.stringify({
            value,
            expiresAt,
            version
        });

        this.entries.set(key, serialized);
    }

    delete(key) {
        this.ensureAvailable();
        this.entries.delete(key);
    }
}

class ProductRepository {
    constructor() {
        this.products = new Map();
    }

    seed(product) {
        this.products.set(product.id, { ...product });
    }

    get(id) {
        const product = this.products.get(id);
        return product ? { ...product } : null;
    }

    update(id, changes) {
        const current = this.products.get(id);

        if (!current) {
            throw new Error(`Product ${id} does not exist`);
        }

        if (
            changes.price !== undefined &&
            (!Number.isFinite(changes.price) || changes.price < 0)
        ) {
            throw new Error("price must be a non-negative finite number");
        }

        if (
            changes.stock !== undefined &&
            (!Number.isInteger(changes.stock) || changes.stock < 0)
        ) {
            throw new Error("stock must be a non-negative integer");
        }

        const updated = {
            ...current,
            ...changes,
            version: current.version + 1
        };

        this.products.set(id, updated);
        return { ...updated };
    }
}

class CacheService {
    constructor(repository, localCache, distributedCache) {
        this.repository = repository;
        this.local = localCache;
        this.distributed = distributedCache;

        this.ttlMs = 2000;
        this.metrics = {
            hits: 0,
            misses: 0,
            writes: 0,
            invalidations: 0,
            staleRejections: 0,
            distributedFailures: 0
        };
    }

    static key(productId) {
        const digest = crypto
            .createHash("sha256")
            .update(`product:${productId}`)
            .digest("hex")
            .slice(0, 16);

        return `product:${digest}`;
    }

    getProduct(id) {
        if (!Number.isInteger(id) || id <= 0) {
            throw new Error("product id must be a positive integer");
        }

        const key = CacheService.key(id);
        const local = this.local.get(key);

        if (local) {
            this.metrics.hits++;
            return { ...local.value };
        }

        this.metrics.misses++;

        let remote = null;

        try {
            remote = this.distributed.get(key);
        } catch (error) {
            if (error instanceof DistributedCacheUnavailable) {
                this.metrics.distributedFailures++;
            } else {
                throw error;
            }
        }

        const authoritative = this.repository.get(id);

        if (
            remote &&
            !remote.isExpired() &&
            authoritative &&
            remote.version >= authoritative.version
        ) {
            this.metrics.hits++;

            this.local.put(
                key,
                remote.value,
                this.ttlMs,
                remote.version
            );

            return { ...remote.value };
        }

        if (remote && authoritative && remote.version < authoritative.version) {
            this.metrics.staleRejections++;
        }

        this.metrics.misses++;

        if (!authoritative) return null;

        this.local.put(
            key,
            authoritative,
            this.ttlMs,
            authoritative.version
        );

        try {
            this.distributed.put(
                key,
                authoritative,
                this.ttlMs * 2,
                authoritative.version
            );
        } catch (error) {
            if (error instanceof DistributedCacheUnavailable) {
                this.metrics.distributedFailures++;
            } else {
                throw error;
            }
        }

        return { ...authoritative };
    }

    cacheAsideUpdate(id, changes) {
        const updated = this.repository.update(id, changes);
        this.invalidate(id);
        return updated;
    }

    writeThroughUpdate(id, changes) {
        const updated = this.repository.update(id, changes);
        const key = CacheService.key(id);

        this.local.put(
            key,
            updated,
            this.ttlMs,
            updated.version
        );

        try {
            this.distributed.put(
                key,
                updated,
                this.ttlMs * 2,
                updated.version
            );
        } catch (error) {
            if (error instanceof DistributedCacheUnavailable) {
                this.metrics.distributedFailures++;
            } else {
                throw error;
            }
        }

        this.metrics.writes++;
        return updated;
    }

    invalidate(id) {
        const key = CacheService.key(id);

        this.local.delete(key);

        try {
            this.distributed.delete(key);
        } catch (error) {
            if (error instanceof DistributedCacheUnavailable) {
                this.metrics.distributedFailures++;
            } else {
                throw error;
            }
        }

        this.metrics.invalidations++;
    }

    report() {
        const total = this.metrics.hits + this.metrics.misses;

        return {
            ...this.metrics,
            hitRate: total === 0 ? 0 : this.metrics.hits / total
        };
    }
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
    const repository = new ProductRepository();

    repository.seed({
        id: 501,
        name: "API Gateway",
        price: 75000,
        stock: 10,
        version: 1
    });

    repository.seed({
        id: 502,
        name: "Database Cluster",
        price: 180000,
        stock: 4,
        version: 1
    });

    const local = new LocalCache(100);
    const distributed = new DistributedCache();
    const service = new CacheService(repository, local, distributed);

    console.log("=== Cache-Aside Read ===");
    console.log(service.getProduct(501));
    console.log(service.getProduct(501));

    console.log("\n=== Cache-Aside Write ===");
    console.log(
        service.cacheAsideUpdate(501, {
            price: 72000
        })
    );
    console.log(service.getProduct(501));

    console.log("\n=== Write-Through ===");
    console.log(
        service.writeThroughUpdate(502, {
            stock: 3
        })
    );

    console.log("\n=== Event-Driven Invalidation ===");
    const events = [
        {
            type: "PRODUCT_PRICE_CHANGED",
            productId: 501,
            price: 69000
        },
        {
            type: "PRODUCT_STOCK_CHANGED",
            productId: 502,
            stock: 2
        }
    ];

    for (const event of events) {
        if (event.type === "PRODUCT_PRICE_CHANGED") {
            service.cacheAsideUpdate(event.productId, {
                price: event.price
            });
        }

        if (event.type === "PRODUCT_STOCK_CHANGED") {
            service.cacheAsideUpdate(event.productId, {
                stock: event.stock
            });
        }
    }

    console.log(service.getProduct(501));
    console.log(service.getProduct(502));

    console.log("\n=== Distributed Failure ===");
    distributed.available = false;
    console.log(service.getProduct(501));
    distributed.available = true;

    console.log("\n=== TTL Expiration ===");
    await sleep(2100);
    console.log(service.getProduct(501));

    console.log("\n=== Metrics ===");
    console.log(service.report());

    console.log("\n=== Validation ===");

    try {
        repository.update(501, { price: -1 });
    } catch (error) {
        console.log(`Rejected invalid price: ${error.message}`);
    }

    try {
        service.getProduct(0);
    } catch (error) {
        console.log(`Rejected invalid identifier: ${error.message}`);
    }

    console.log("\n=== Security Properties ===");
    console.log("Remote values are serialized before storage.");
    console.log("Cache keys use SHA-256-derived identifiers.");
    console.log("Authoritative repository versions prevent stale cache promotion.");

    if (repository.get(501).price !== 69000) {
        throw new Error("price invariant failed");
    }

    if (repository.get(502).stock !== 2) {
        throw new Error("stock invariant failed");
    }
}

main().catch(error => {
    console.error("Fatal error:", error);
    process.exitCode = 1;
});
