'use strict';

/*
 * Content Delivery Network simulation.
 *
 * The model separates:
 *   - origin authority
 *   - edge locations
 *   - cache entries and TTL
 *   - request routing
 *   - cache invalidation
 *   - conditional validation
 *   - asynchronous origin access
 *
 * It intentionally avoids third-party dependencies so the file runs directly
 * with Node.js 18+.
 */

const crypto = require('node:crypto');

class OriginObject {
    constructor(path, body, contentType, version) {
        this.path = path;
        this.body = Buffer.from(body, 'utf8');
        this.contentType = contentType;
        this.version = version;
        this.updatedAt = Date.now();
        this.etag = `"${crypto.createHash('sha256').update(this.body).digest('hex')}"`;
    }
}

class OriginServer {
    constructor() {
        this.objects = new Map();
    }

    publish(path, body, contentType = 'text/plain') {
        if (!path.startsWith('/')) {
            throw new Error('Origin path must begin with "/"');
        }

        if (typeof body !== 'string' || body.length === 0) {
            throw new Error('Origin content must be a non-empty string');
        }

        const oldObject = this.objects.get(path);
        const version = oldObject ? oldObject.version + 1 : 1;

        const object = new OriginObject(path, body, contentType, version);
        this.objects.set(path, object);
        return object;
    }

    async fetch(path) {
        // Simulates network I/O. Real CDNs communicate over HTTP/TLS.
        await new Promise(resolve => setTimeout(resolve, 8));

        const object = this.objects.get(path);
        if (!object) {
            const error = new Error(`Origin object not found: ${path}`);
            error.code = 'NOT_FOUND';
            throw error;
        }

        return object;
    }
}

class EdgeLocation {
    constructor(name, region, capacity) {
        this.name = name;
        this.region = region;
        this.capacity = capacity;
    }
}

class CacheEntry {
    constructor(originObject, ttlMs, now) {
        this.body = Buffer.from(originObject.body);
        this.etag = originObject.etag;
        this.version = originObject.version;
        this.createdAt = now;
        this.expiresAt = now + ttlMs;
    }

    isFresh(now) {
        return now < this.expiresAt;
    }
}

class EdgeCache {
    constructor(location) {
        this.location = location;
        this.entries = new Map();
        this.hits = 0;
        this.misses = 0;
        this.invalidations = 0;
    }

    lookup(path, now) {
        const entry = this.entries.get(path);

        if (!entry) {
            this.misses++;
            return { state: 'MISS', entry: null };
        }

        if (!entry.isFresh(now)) {
            this.misses++;
            return { state: 'STALE', entry };
        }

        this.hits++;
        return { state: 'HIT', entry };
    }

    store(path, originObject, ttlMs, now) {
        if (!this.entries.has(path) && this.entries.size >= this.location.capacity) {
            let victimPath = null;
            let earliestExpiry = Number.POSITIVE_INFINITY;

            for (const [candidatePath, entry] of this.entries) {
                if (entry.expiresAt < earliestExpiry) {
                    earliestExpiry = entry.expiresAt;
                    victimPath = candidatePath;
                }
            }

            if (victimPath !== null) {
                this.entries.delete(victimPath);
            }
        }

        const entry = new CacheEntry(originObject, ttlMs, now);
        this.entries.set(path, entry);
        return entry;
    }

    invalidate(path) {
        const removed = this.entries.delete(path);
        if (removed) {
            this.invalidations++;
        }
        return removed;
    }

    invalidatePrefix(prefix) {
        let removed = 0;

        for (const path of this.entries.keys()) {
            if (path.startsWith(prefix)) {
                this.entries.delete(path);
                removed++;
            }
        }

        this.invalidations += removed;
        return removed;
    }
}

class ContentDeliveryNetwork {
    constructor(origin, locations) {
        this.origin = origin;
        this.edges = new Map(
            locations.map(location => [
                location.name,
                new EdgeCache(location)
            ])
        );

        this.latency = new Map([
            ['India:India', 20],
            ['India:Europe', 115],
            ['India:North America', 210],
            ['Europe:India', 115],
            ['Europe:Europe', 25],
            ['Europe:North America', 90],
            ['North America:India', 210],
            ['North America:Europe', 90],
            ['North America:North America', 25]
        ]);

        this.requests = 0;
        this.originFetches = 0;
    }

    distance(clientRegion, edgeRegion) {
        return this.latency.get(`${clientRegion}:${edgeRegion}`) ?? 150;
    }

    chooseEdge(clientRegion) {
        let selected = null;
        let bestLatency = Number.POSITIVE_INFINITY;

        for (const edge of this.edges.values()) {
            const value = this.distance(clientRegion, edge.location.region);

            if (value < bestLatency) {
                bestLatency = value;
                selected = edge;
            }
        }

        if (!selected) {
            throw new Error('No edge locations are configured');
        }

        return selected;
    }

    async request(path, clientRegion, options = {}) {
        const {
            ttlMs = 30_000,
            cacheControl = 'public',
            ifNoneMatch = null
        } = options;

        if (!path.startsWith('/')) {
            throw new Error('Invalid request path');
        }

        if (ttlMs < 0) {
            throw new Error('TTL cannot be negative');
        }

        this.requests++;

        const edge = this.chooseEdge(clientRegion);
        const now = Date.now();

        // User-specific/private responses should not enter a shared public cache.
        const bypassCache = cacheControl === 'private' || cacheControl === 'no-store';

        if (!bypassCache) {
            const lookup = edge.lookup(path, now);

            if (lookup.state === 'HIT') {
                if (ifNoneMatch && ifNoneMatch === lookup.entry.etag) {
                    return {
                        status: 304,
                        edge: edge.location.name,
                        source: 'edge',
                        etag: lookup.entry.etag,
                        version: lookup.entry.version,
                        latencyMs: this.distance(clientRegion, edge.location.region)
                    };
                }

                return {
                    status: 200,
                    edge: edge.location.name,
                    source: 'edge',
                    etag: lookup.entry.etag,
                    version: lookup.entry.version,
                    latencyMs: this.distance(clientRegion, edge.location.region)
                };
            }
        }

        let originObject;

        try {
            originObject = await this.origin.fetch(path);
            this.originFetches++;
        } catch (error) {
            // Stale-if-error can be a valid production policy for resilient
            // static delivery. This simulation serves stale data only when
            // explicitly requested by the caller.
            if (!bypassCache && options.allowStaleOnError) {
                const lookup = edge.lookup(path, Number.MAX_SAFE_INTEGER);

                if (lookup.entry) {
                    return {
                        status: 200,
                        edge: edge.location.name,
                        source: 'stale-edge-on-origin-error',
                        etag: lookup.entry.etag,
                        version: lookup.entry.version,
                        latencyMs: this.distance(clientRegion, edge.location.region)
                    };
                }
            }

            throw error;
        }

        if (!bypassCache) {
            edge.store(path, originObject, ttlMs, now);
        }

        if (ifNoneMatch && ifNoneMatch === originObject.etag) {
            return {
                status: 304,
                edge: edge.location.name,
                source: 'origin-validation',
                etag: originObject.etag,
                version: originObject.version,
                latencyMs: this.distance(clientRegion, edge.location.region) + 80
            };
        }

        return {
            status: 200,
            edge: edge.location.name,
            source: 'origin',
            etag: originObject.etag,
            version: originObject.version,
            latencyMs: this.distance(clientRegion, edge.location.region) + 80
        };
    }

    invalidate(path) {
        let count = 0;

        for (const edge of this.edges.values()) {
            if (edge.invalidate(path)) {
                count++;
            }
        }

        return count;
    }

    invalidatePrefix(prefix) {
        let count = 0;

        for (const edge of this.edges.values()) {
            count += edge.invalidatePrefix(prefix);
        }

        return count;
    }

    statistics() {
        let hits = 0;
        let misses = 0;
        let invalidations = 0;

        for (const edge of this.edges.values()) {
            hits += edge.hits;
            misses += edge.misses;
            invalidations += edge.invalidations;
        }

        const lookups = hits + misses;

        return {
            requests: this.requests,
            originFetches: this.originFetches,
            cacheHits: hits,
            cacheMisses: misses,
            cacheHitRatio: lookups === 0 ? 0 : Number((hits / lookups).toFixed(4)),
            invalidations
        };
    }
}

function publicCacheKey(path, query) {
    if (!path.startsWith('/')) {
        throw new Error('Invalid path');
    }

    // Only parameters that change public content belong in a shared key.
    // Tracking identifiers must not create an unbounded cache-key space.
    const allowedNames = new Set(['language', 'format', 'page']);

    const selected = Object.entries(query)
        .filter(([key]) => allowedNames.has(key))
        .sort(([a], [b]) => a.localeCompare(b));

    const serialized = selected
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
        .join('&');

    return serialized ? `${path}?${serialized}` : path;
}

async function main() {
    const origin = new OriginServer();

    origin.publish(
        '/assets/app.js',
        'console.log("release-1");',
        'application/javascript'
    );

    origin.publish(
        '/images/logo.svg',
        '<svg><title>CDN logo</title></svg>',
        'image/svg+xml'
    );

    origin.publish(
        '/api/config',
        JSON.stringify({ release: '2026.10', feature: 'edge-cache' }),
        'application/json'
    );

    const cdn = new ContentDeliveryNetwork(origin, [
        new EdgeLocation('delhi-1', 'India', 100),
        new EdgeLocation('frankfurt-1', 'Europe', 100),
        new EdgeLocation('virginia-1', 'North America', 100)
    ]);

    const first = await cdn.request('/assets/app.js', 'India', {
        ttlMs: 60_000
    });

    const second = await cdn.request('/assets/app.js', 'India', {
        ttlMs: 60_000
    });

    console.log('First request:', first);
    console.log('Repeated request:', second);

    origin.publish(
        '/assets/app.js',
        'console.log("release-2");',
        'application/javascript'
    );

    const stillCached = await cdn.request('/assets/app.js', 'India', {
        ttlMs: 60_000
    });

    console.log('Origin changed, cache still valid:', stillCached);

    const removed = cdn.invalidate('/assets/app.js');
    console.log('Invalidated copies:', removed);

    const refreshed = await cdn.request('/assets/app.js', 'India', {
        ttlMs: 60_000
    });

    console.log('After invalidation:', refreshed);

    const validated = await cdn.request('/assets/app.js', 'India', {
        ttlMs: 60_000,
        ifNoneMatch: refreshed.etag
    });

    console.log('Conditional request:', validated);

    const privateResponse = await cdn.request('/api/config', 'India', {
        cacheControl: 'private'
    });

    console.log('Private response bypassing shared cache:', privateResponse);

    console.log(
        'Safe public cache key:',
        publicCacheKey('/products', {
            page: '2',
            language: 'en',
            trackingId: 'excluded'
        })
    );

    console.log('Statistics:', cdn.statistics());
}

main().catch(error => {
    console.error(`CDN simulation failed: ${error.message}`);
    process.exitCode = 1;
});
