from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from time import monotonic, sleep
from typing import Any, Callable, Dict, Optional
import hashlib
import json


class CachePolicy(Enum):
    CACHE_ASIDE = "cache-aside"
    WRITE_THROUGH = "write-through"


class CacheError(Exception):
    pass


class CacheSerializationError(CacheError):
    pass


class DistributedCacheUnavailable(CacheError):
    pass


@dataclass
class CacheEntry:
    value: Any
    expires_at: Optional[float]
    version: int

    def expired(self) -> bool:
        return self.expires_at is not None and monotonic() >= self.expires_at


@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    invalidations: int = 0
    stale_rejections: int = 0
    distributed_failures: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class InMemoryCache:
    """Thread-safe local cache with TTL and version-aware writes."""

    def __init__(self, max_entries: int = 1000):
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._entries: Dict[str, CacheEntry] = {}
        self._lock = RLock()

    def get(self, key: str) -> Optional[CacheEntry]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expired():
                del self._entries[key]
                return None
            return entry

    def put(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float],
        version: int,
    ) -> None:
        if not key:
            raise ValueError("cache key cannot be empty")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        with self._lock:
            if len(self._entries) >= self.max_entries and key not in self._entries:
                oldest_key = min(
                    self._entries,
                    key=lambda k: self._entries[k].expires_at
                    if self._entries[k].expires_at is not None
                    else float("inf"),
                )
                self._entries.pop(oldest_key, None)

            expires_at = (
                monotonic() + ttl_seconds if ttl_seconds is not None else None
            )
            self._entries[key] = CacheEntry(value, expires_at, version)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


class DistributedCache:
    """
    A Redis-like distributed cache simulation.

    Values are serialized before storage to model the boundary between
    application memory and a remote cache service.
    """

    def __init__(self, failure_rate: float = 0.0):
        if not 0.0 <= failure_rate <= 1.0:
            raise ValueError("failure_rate must be between 0 and 1")
        self.failure_rate = failure_rate
        self._store: Dict[str, str] = {}
        self._lock = RLock()
        self.available = True

    def _check_available(self) -> None:
        if not self.available:
            raise DistributedCacheUnavailable("distributed cache is unavailable")

    def get(self, key: str) -> Optional[CacheEntry]:
        self._check_available()
        with self._lock:
            raw = self._store.get(key)
            if raw is None:
                return None

            try:
                data = json.loads(raw)
                return CacheEntry(
                    value=data["value"],
                    expires_at=data["expires_at"],
                    version=data["version"],
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise CacheSerializationError(
                    f"invalid distributed-cache entry for {key}"
                ) from exc

    def put(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float],
        version: int,
    ) -> None:
        self._check_available()
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        expires_at = (
            monotonic() + ttl_seconds if ttl_seconds is not None else None
        )

        try:
            payload = json.dumps(
                {
                    "value": value,
                    "expires_at": expires_at,
                    "version": version,
                },
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise CacheSerializationError(
                f"value for {key} is not JSON serializable"
            ) from exc

        with self._lock:
            self._store[key] = payload

    def delete(self, key: str) -> None:
        self._check_available()
        with self._lock:
            self._store.pop(key, None)


@dataclass
class Product:
    product_id: int
    name: str
    price: float
    stock: int
    version: int = 1


class ProductRepository:
    """Authoritative data store. Cache is never the source of truth."""

    def __init__(self):
        self._products: Dict[int, Product] = {}
        self._lock = RLock()

    def seed(self, product: Product) -> None:
        with self._lock:
            self._products[product.product_id] = product

    def get(self, product_id: int) -> Optional[Product]:
        with self._lock:
            product = self._products.get(product_id)
            if product is None:
                return None
            return Product(**vars(product))

    def update(
        self,
        product_id: int,
        *,
        price: Optional[float] = None,
        stock: Optional[int] = None,
    ) -> Product:
        with self._lock:
            product = self._products.get(product_id)
            if product is None:
                raise KeyError(f"product {product_id} does not exist")

            if price is not None and price < 0:
                raise ValueError("price cannot be negative")
            if stock is not None and stock < 0:
                raise ValueError("stock cannot be negative")

            if price is not None:
                product.price = price
            if stock is not None:
                product.stock = stock

            product.version += 1
            return Product(**vars(product))


class CacheService:
    def __init__(
        self,
        repository: ProductRepository,
        local_cache: InMemoryCache,
        distributed_cache: DistributedCache,
        *,
        default_ttl: float = 30.0,
    ):
        self.repository = repository
        self.local = local_cache
        self.distributed = distributed_cache
        self.default_ttl = default_ttl
        self.metrics = CacheMetrics()

    @staticmethod
    def cache_key(product_id: int) -> str:
        raw = f"product:{product_id}".encode()
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return f"product:{digest}"

    def _record_hit(self, source: str) -> None:
        self.metrics.hits += 1
        print(f"[CACHE HIT] source={source}")

    def _record_miss(self, source: str) -> None:
        self.metrics.misses += 1
        print(f"[CACHE MISS] source={source}")

    def _is_fresh(self, entry: CacheEntry, authoritative: Product) -> bool:
        return entry.version >= authoritative.version

    def get_product(self, product_id: int) -> Optional[Product]:
        key = self.cache_key(product_id)

        local_entry = self.local.get(key)
        if local_entry is not None:
            self._record_hit("local")
            return Product(**local_entry.value)

        self._record_miss("local")

        try:
            remote_entry = self.distributed.get(key)
        except DistributedCacheUnavailable:
            self.metrics.distributed_failures += 1
            remote_entry = None

        if remote_entry is not None and not remote_entry.expired():
            authoritative = self.repository.get(product_id)
            if authoritative is not None and self._is_fresh(
                remote_entry, authoritative
            ):
                self.local.put(
                    key,
                    remote_entry.value,
                    self.default_ttl,
                    remote_entry.version,
                )
                self._record_hit("distributed")
                return Product(**remote_entry.value)

            self.metrics.stale_rejections += 1

        self._record_miss("distributed")

        product = self.repository.get(product_id)
        if product is None:
            return None

        self.local.put(
            key,
            vars(product),
            self.default_ttl,
            product.version,
        )

        try:
            self.distributed.put(
                key,
                vars(product),
                self.default_ttl * 2,
                product.version,
            )
        except DistributedCacheUnavailable:
            self.metrics.distributed_failures += 1

        return product

    def update_product_cache_aside(
        self,
        product_id: int,
        *,
        price: Optional[float] = None,
        stock: Optional[int] = None,
    ) -> Product:
        """
        Cache-aside writes update the database first and invalidate caches.
        This avoids serving a known stale representation after a successful
        authoritative update.
        """
        product = self.repository.update(
            product_id,
            price=price,
            stock=stock,
        )
        self.invalidate_product(product_id)
        return product

    def write_through_product(
        self,
        product_id: int,
        *,
        price: Optional[float] = None,
        stock: Optional[int] = None,
    ) -> Product:
        """
        Write-through updates the authoritative store and immediately refreshes
        both cache tiers with the new version.
        """
        product = self.repository.update(
            product_id,
            price=price,
            stock=stock,
        )

        key = self.cache_key(product_id)
        self.local.put(
            key,
            vars(product),
            self.default_ttl,
            product.version,
        )

        try:
            self.distributed.put(
                key,
                vars(product),
                self.default_ttl * 2,
                product.version,
            )
        except DistributedCacheUnavailable:
            self.metrics.distributed_failures += 1
            # The database update remains valid. The local cache is also valid,
            # while the distributed layer will be repopulated on a later read.

        self.metrics.writes += 1
        return product

    def invalidate_product(self, product_id: int) -> None:
        key = self.cache_key(product_id)
        self.local.delete(key)
        try:
            self.distributed.delete(key)
        except DistributedCacheUnavailable:
            self.metrics.distributed_failures += 1
        self.metrics.invalidations += 1

    def metrics_report(self) -> dict:
        return {
            "hits": self.metrics.hits,
            "misses": self.metrics.misses,
            "hit_rate": round(self.metrics.hit_rate, 3),
            "writes": self.metrics.writes,
            "invalidations": self.metrics.invalidations,
            "stale_rejections": self.metrics.stale_rejections,
            "distributed_failures": self.metrics.distributed_failures,
            "local_entries": self.local.size(),
        }


def demonstrate() -> None:
    repository = ProductRepository()
    repository.seed(Product(101, "Enterprise Laptop", 125000.0, 12))
    repository.seed(Product(102, "Security Gateway", 85000.0, 7))

    service = CacheService(
        repository,
        InMemoryCache(max_entries=100),
        DistributedCache(),
        default_ttl=2.0,
    )

    print("=== Cache-Aside Read Path ===")
    first = service.get_product(101)
    print(first)

    second = service.get_product(101)
    print(second)

    print("\n=== Cache-Aside Update ===")
    updated = service.update_product_cache_aside(101, price=120000.0)
    print(updated)

    refreshed = service.get_product(101)
    print(refreshed)

    print("\n=== Write-Through Update ===")
    updated = service.write_through_product(102, stock=4)
    print(updated)

    print("\n=== Distributed Cache Failure ===")
    service.distributed.available = False
    degraded = service.get_product(102)
    print(degraded)
    service.distributed.available = True

    print("\n=== TTL Expiration ===")
    service.get_product(101)
    sleep(2.1)
    service.get_product(101)

    print("\n=== Cache Metrics ===")
    print(json.dumps(service.metrics_report(), indent=2))

    print("\n=== Edge-Case Validation ===")
    try:
        service.get_product(-1)
    except Exception as exc:
        print(f"Unexpected read failure: {exc}")

    try:
        repository.update(101, price=-1)
    except ValueError as exc:
        print(f"Rejected invalid price: {exc}")

    print("\n=== Security Controls ===")
    print("Cache keys use a deterministic SHA-256-derived identifier.")
    print("Authoritative product state is never accepted from an untrusted cache.")
    print("Distributed-cache serialization rejects unsupported object types.")

    assert repository.get(101).price == 120000.0
    assert repository.get(102).stock == 4


if __name__ == "__main__":
    demonstrate()
