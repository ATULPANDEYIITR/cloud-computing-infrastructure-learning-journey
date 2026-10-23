from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Dict, Iterable, Optional
import json
import time


class CacheStatus(Enum):
    HIT = "HIT"
    MISS = "MISS"
    STALE = "STALE"
    BYPASS = "BYPASS"


@dataclass(frozen=True)
class EdgeLocation:
    name: str
    region: str
    latitude: float
    longitude: float
    capacity_objects: int


@dataclass
class CacheEntry:
    content: bytes
    etag: str
    created_at: float
    expires_at: float
    version: int

    @property
    def size(self) -> int:
        return len(self.content)

    def is_fresh(self, now: float) -> bool:
        return now < self.expires_at


@dataclass
class OriginObject:
    path: str
    content: bytes
    content_type: str
    version: int
    updated_at: float

    @property
    def etag(self) -> str:
        return sha256(self.content).hexdigest()


@dataclass
class RequestResult:
    edge: str
    path: str
    status: CacheStatus
    latency_ms: float
    source: str
    etag: Optional[str]
    version: Optional[int]


class OriginServer:
    """Authoritative source of content.

    A CDN must treat the origin as the source of truth. Edge caches only hold
    temporary copies and must not become authoritative accidentally.
    """

    def __init__(self) -> None:
        self.objects: Dict[str, OriginObject] = {}

    def publish(self, path: str, content: str, content_type: str = "text/plain") -> OriginObject:
        if not path.startswith("/"):
            raise ValueError("Origin paths must start with '/'")
        if not content:
            raise ValueError("Published content cannot be empty")

        previous = self.objects.get(path)
        version = 1 if previous is None else previous.version + 1
        obj = OriginObject(
            path=path,
            content=content.encode("utf-8"),
            content_type=content_type,
            version=version,
            updated_at=time.time(),
        )
        self.objects[path] = obj
        return obj

    def fetch(self, path: str) -> OriginObject:
        if path not in self.objects:
            raise FileNotFoundError(f"Origin object not found: {path}")
        return self.objects[path]


class EdgeCache:
    """Bounded in-memory cache representing one CDN edge location."""

    def __init__(self, location: EdgeLocation) -> None:
        self.location = location
        self.entries: Dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0
        self.invalidations = 0

    def get(self, path: str, now: float) -> tuple[CacheStatus, Optional[CacheEntry]]:
        entry = self.entries.get(path)

        if entry is None:
            self.misses += 1
            return CacheStatus.MISS, None

        if not entry.is_fresh(now):
            self.misses += 1
            return CacheStatus.STALE, entry

        self.hits += 1
        return CacheStatus.HIT, entry

    def put(self, path: str, obj: OriginObject, ttl_seconds: float, now: float) -> CacheEntry:
        if len(self.entries) >= self.location.capacity_objects and path not in self.entries:
            # Simple deterministic eviction: remove the entry with the earliest expiry.
            victim = min(self.entries, key=lambda key: self.entries[key].expires_at)
            del self.entries[victim]

        entry = CacheEntry(
            content=obj.content,
            etag=obj.etag,
            created_at=now,
            expires_at=now + ttl_seconds,
            version=obj.version,
        )
        self.entries[path] = entry
        return entry

    def invalidate(self, path: str) -> bool:
        existed = path in self.entries
        self.entries.pop(path, None)
        if existed:
            self.invalidations += 1
        return existed

    def invalidate_prefix(self, prefix: str) -> int:
        keys = [key for key in self.entries if key.startswith(prefix)]
        for key in keys:
            del self.entries[key]
        self.invalidations += len(keys)
        return len(keys)


class ContentDeliveryNetwork:
    """Models request routing, edge caching, origin fetches and invalidation."""

    def __init__(self, origin: OriginServer, edges: Iterable[EdgeLocation]) -> None:
        self.origin = origin
        self.edges = {edge.name: EdgeCache(edge) for edge in edges}
        self.request_count = 0
        self.origin_fetches = 0

        # Approximate network distance/latency rather than performing real
        # geolocation. Production CDNs use routing infrastructure and telemetry.
        self.network_latency = {
            ("India", "India"): 20.0,
            ("India", "Europe"): 115.0,
            ("India", "North America"): 210.0,
            ("Europe", "India"): 115.0,
            ("Europe", "Europe"): 25.0,
            ("Europe", "North America"): 90.0,
            ("North America", "India"): 210.0,
            ("North America", "Europe"): 90.0,
            ("North America", "North America"): 25.0,
        }

    def _latency(self, client_region: str, edge_region: str, cache_hit: bool) -> float:
        base = self.network_latency.get((client_region, edge_region), 150.0)
        return base if cache_hit else base + 80.0

    def choose_edge(self, client_region: str) -> EdgeCache:
        candidates = list(self.edges.values())

        if not candidates:
            raise RuntimeError("CDN has no configured edge locations")

        regional = [
            edge for edge in candidates
            if edge.location.region == client_region
        ]

        return min(
            regional or candidates,
            key=lambda edge: self.network_latency.get(
                (client_region, edge.location.region), 150.0
            ),
        )

    def request(
        self,
        path: str,
        client_region: str,
        ttl_seconds: float = 30.0,
        now: Optional[float] = None,
        no_cache: bool = False,
    ) -> RequestResult:
        if not path.startswith("/"):
            raise ValueError("Request path must start with '/'")
        if ttl_seconds < 0:
            raise ValueError("TTL cannot be negative")

        now = monotonic() if now is None else now
        self.request_count += 1
        edge = self.choose_edge(client_region)

        if no_cache:
            status = CacheStatus.BYPASS
            cached = None
        else:
            status, cached = edge.get(path, now)

        if status == CacheStatus.HIT:
            latency = self._latency(client_region, edge.location.region, True)
            return RequestResult(
                edge=edge.location.name,
                path=path,
                status=status,
                latency_ms=latency,
                source="edge-cache",
                etag=cached.etag if cached else None,
                version=cached.version if cached else None,
            )

        # MISS, STALE, or explicit cache bypass requires origin access.
        origin_object = self.origin.fetch(path)
        self.origin_fetches += 1

        if not no_cache:
            cached = edge.put(path, origin_object, ttl_seconds, now)

        latency = self._latency(client_region, edge.location.region, False)

        return RequestResult(
            edge=edge.location.name,
            path=path,
            status=status,
            latency_ms=latency,
            source="origin",
            etag=origin_object.etag,
            version=origin_object.version,
        )

    def invalidate(self, path: str, edge_name: Optional[str] = None) -> int:
        if edge_name is not None:
            if edge_name not in self.edges:
                raise KeyError(f"Unknown edge: {edge_name}")
            return int(self.edges[edge_name].invalidate(path))

        return sum(edge.invalidate(path) for edge in self.edges.values())

    def invalidate_prefix(self, prefix: str) -> int:
        return sum(edge.invalidate_prefix(prefix) for edge in self.edges.values())

    def statistics(self) -> dict:
        hits = sum(edge.hits for edge in self.edges.values())
        misses = sum(edge.misses for edge in self.edges.values())
        lookups = hits + misses

        return {
            "requests": self.request_count,
            "origin_fetches": self.origin_fetches,
            "cache_hits": hits,
            "cache_misses": misses,
            "cache_hit_ratio": round(hits / lookups, 4) if lookups else 0.0,
            "invalidations": sum(edge.invalidations for edge in self.edges.values()),
            "edge_objects": {
                name: len(edge.entries) for name, edge in self.edges.items()
            },
        }


def conditional_request(
    cdn: ContentDeliveryNetwork,
    path: str,
    client_region: str,
    known_etag: Optional[str],
) -> dict:
    """Demonstrates validator-based revalidation.

    A real HTTP CDN can send If-None-Match to the origin. A matching ETag lets
    the origin return 304 Not Modified instead of retransmitting the body.
    """
    edge = cdn.choose_edge(client_region)
    status, entry = edge.get(path, monotonic())

    if status == CacheStatus.HIT and entry is not None:
        if known_etag == entry.etag:
            return {
                "status_code": 304,
                "edge": edge.location.name,
                "source": "edge-cache",
                "etag": entry.etag,
            }

        return {
            "status_code": 200,
            "edge": edge.location.name,
            "source": "edge-cache",
            "etag": entry.etag,
            "version": entry.version,
        }

    result = cdn.request(path, client_region)
    if known_etag == result.etag:
        return {
            "status_code": 304,
            "edge": result.edge,
            "source": "origin-validation",
            "etag": result.etag,
        }

    return {
        "status_code": 200,
        "edge": result.edge,
        "source": result.source,
        "etag": result.etag,
        "version": result.version,
    }


def secure_cache_key(path: str, query_parameters: dict[str, str]) -> str:
    """Builds a deterministic cache key.

    Sensitive request headers, cookies, or authorization tokens must not be
    accidentally incorporated into a shared public cache key. Public content
    should be separated from user-specific content.
    """
    if not path.startswith("/"):
        raise ValueError("Invalid path")

    allowed = {
        key: value
        for key, value in query_parameters.items()
        if key in {"language", "format", "page"}
    }

    canonical_query = "&".join(
        f"{key}={allowed[key]}"
        for key in sorted(allowed)
    )
    return f"{path}?{canonical_query}" if canonical_query else path


def demonstrate_file_cache() -> None:
    """Shows how immutable versioned assets can be safely cached.

    A content hash in the filename makes long TTLs practical because a new
    deployment creates a new URL rather than mutating the old object.
    """
    with TemporaryDirectory() as directory:
        root = Path(directory)
        content = b"release-2026.10"
        digest = sha256(content).hexdigest()[:16]
        asset = root / f"app.{digest}.js"
        asset.write_bytes(content)

        assert asset.read_bytes() == content
        assert digest in asset.name


def main() -> None:
    origin = OriginServer()
    origin.publish(
        "/assets/app.js",
        "console.log('release-1');",
        "application/javascript",
    )
    origin.publish(
        "/images/logo.svg",
        "<svg><title>Repository CDN</title></svg>",
        "image/svg+xml",
    )
    origin.publish(
        "/api/config",
        '{"release":"2026.10","region":"global"}',
        "application/json",
    )

    edges = [
        EdgeLocation("delhi-1", "India", 28.61, 77.21, 100),
        EdgeLocation("frankfurt-1", "Europe", 50.11, 8.68, 100),
        EdgeLocation("virginia-1", "North America", 37.43, -77.45, 100),
    ]

    cdn = ContentDeliveryNetwork(origin, edges)

    simulated_time = 1_000.0

    first = cdn.request("/assets/app.js", "India", ttl_seconds=60, now=simulated_time)
    second = cdn.request("/assets/app.js", "India", ttl_seconds=60, now=simulated_time + 5)

    print("Initial request:", first)
    print("Repeated request:", second)

    stale = cdn.request(
        "/assets/app.js",
        "India",
        ttl_seconds=60,
        now=simulated_time + 61,
    )
    print("After TTL:", stale)

    origin.publish(
        "/assets/app.js",
        "console.log('release-2');",
        "application/javascript",
    )

    before_invalidation = cdn.request(
        "/assets/app.js",
        "India",
        ttl_seconds=60,
        now=simulated_time + 62,
    )
    print("After origin update but before invalidation:", before_invalidation)

    invalidated = cdn.invalidate("/assets/app.js")
    print("Invalidated edge copies:", invalidated)

    after_invalidation = cdn.request(
        "/assets/app.js",
        "India",
        ttl_seconds=60,
        now=simulated_time + 63,
    )
    print("After invalidation:", after_invalidation)

    conditional = conditional_request(
        cdn,
        "/assets/app.js",
        "India",
        after_invalidation.etag,
    )
    print("Conditional request:", conditional)

    cache_key = secure_cache_key(
        "/products",
        {"page": "2", "language": "en", "tracking_id": "do-not-cache"},
    )
    print("Public cache key:", cache_key)

    demonstrate_file_cache()

    print(json.dumps(cdn.statistics(), indent=2))


if __name__ == "__main__":
    main()
