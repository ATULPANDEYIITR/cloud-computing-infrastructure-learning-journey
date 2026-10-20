#!/usr/bin/env python3
"""
Storage performance and optimization simulator.

Models:
- IOPS
- throughput
- latency
- cache hit/miss behavior
- storage tiers
- cost/performance trade-offs
- workload validation
- simple tier selection
- benchmark-style execution

The model is intentionally analytical rather than dependent on a real disk,
so it can run consistently on any Python 3 installation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections import OrderedDict
from statistics import mean
from typing import Iterable
import random
import time


class AccessType(Enum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class StorageTier:
    name: str
    max_iops: float
    max_throughput_mbps: float
    latency_ms: float
    monthly_cost_per_gb: float


@dataclass(frozen=True)
class IORequest:
    request_id: int
    access_type: AccessType
    size_kb: int
    key: str


@dataclass
class WorkloadMetrics:
    requests: int = 0
    reads: int = 0
    writes: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_latency_ms: float = 0.0
    total_bytes: int = 0

    @property
    def average_latency_ms(self) -> float:
        return self.total_latency_ms / self.requests if self.requests else 0.0

    @property
    def cache_hit_ratio(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0

    @property
    def throughput_mbps(self) -> float:
        if self.total_latency_ms <= 0:
            return 0.0
        seconds = self.total_latency_ms / 1000.0
        return self.total_bytes / 1024 / 1024 / seconds


class LRUCache:
    """A bounded cache using O(1)-average dictionary lookups."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("Cache capacity must be positive")
        self.capacity = capacity
        self._items: OrderedDict[str, bytes] = OrderedDict()

    def get(self, key: str) -> bytes | None:
        if key not in self._items:
            return None
        value = self._items.pop(key)
        self._items[key] = value
        return value

    def put(self, key: str, value: bytes) -> None:
        if key in self._items:
            self._items.pop(key)
        elif len(self._items) >= self.capacity:
            self._items.popitem(last=False)
        self._items[key] = value


class StorageSimulator:
    def __init__(self, tier: StorageTier, cache_capacity: int = 32) -> None:
        self.tier = tier
        self.cache = LRUCache(cache_capacity)
        self.metrics = WorkloadMetrics()

    def _validate_request(self, request: IORequest) -> None:
        if request.size_kb <= 0:
            raise ValueError("I/O size must be positive")
        if request.size_kb > 1024 * 1024:
            raise ValueError("I/O request is unrealistically large")
        if not request.key or len(request.key) > 256:
            raise ValueError("Storage key is invalid")

    def process(self, request: IORequest) -> None:
        self._validate_request(request)

        self.metrics.requests += 1
        self.metrics.total_bytes += request.size_kb * 1024

        if request.access_type is AccessType.READ:
            self.metrics.reads += 1
            cached = self.cache.get(request.key)

            if cached is not None:
                self.metrics.cache_hits += 1
                latency = max(0.05, self.tier.latency_ms * 0.10)
            else:
                self.metrics.cache_misses += 1
                latency = self._storage_latency(request.size_kb)
                self.cache.put(request.key, bytes(min(request.size_kb * 1024, 4096)))
        else:
            self.metrics.writes += 1
            latency = self._storage_latency(request.size_kb)
            # Write-through behavior keeps the cache coherent with storage.
            self.cache.put(request.key, bytes(min(request.size_kb * 1024, 4096)))

        self.metrics.total_latency_ms += latency

    def _storage_latency(self, size_kb: int) -> float:
        """
        A simplified latency model:
        base latency + transfer time.

        Transfer time = size / throughput.
        The IOPS limit is handled separately when estimating sustainable load.
        """
        transfer_ms = (size_kb / 1024) / self.tier.max_throughput_mbps * 1000
        return self.tier.latency_ms + transfer_ms

    def sustainable_iops(self, request_size_kb: int) -> float:
        if request_size_kb <= 0:
            raise ValueError("Request size must be positive")

        throughput_limited_iops = (
            self.tier.max_throughput_mbps * 1024 / request_size_kb
        )
        return min(self.tier.max_iops, throughput_limited_iops)


TIERS = [
    StorageTier(
        "HDD",
        max_iops=180,
        max_throughput_mbps=220,
        latency_ms=8.0,
        monthly_cost_per_gb=0.02,
    ),
    StorageTier(
        "SATA SSD",
        max_iops=75000,
        max_throughput_mbps=550,
        latency_ms=0.10,
        monthly_cost_per_gb=0.08,
    ),
    StorageTier(
        "NVMe SSD",
        max_iops=800000,
        max_throughput_mbps=7000,
        latency_ms=0.025,
        monthly_cost_per_gb=0.15,
    ),
)


def choose_tier(
    required_iops: float,
    required_mbps: float,
    capacity_gb: float,
    max_monthly_cost: float | None = None,
) -> StorageTier:
    if required_iops < 0 or required_mbps < 0 or capacity_gb <= 0:
        raise ValueError("Invalid workload requirements")

    candidates = [
        tier
        for tier in TIERS
        if tier.max_iops >= required_iops
        and tier.max_throughput_mbps >= required_mbps
        and (
            max_monthly_cost is None
            or tier.monthly_cost_per_gb * capacity_gb <= max_monthly_cost
        )
    ]

    if not candidates:
        raise RuntimeError("No storage tier satisfies the workload constraints")

    return min(candidates, key=lambda tier: tier.monthly_cost_per_gb)


def generate_workload(count: int, seed: int = 42) -> list[IORequest]:
    if count <= 0:
        raise ValueError("Workload size must be positive")

    rng = random.Random(seed)
    requests: list[IORequest] = []

    hot_keys = [f"customer:{i}" for i in range(12)]
    cold_keys = [f"archive:{i}" for i in range(200)]

    for request_id in range(count):
        key = rng.choice(hot_keys if rng.random() < 0.75 else cold_keys)
        access_type = (
            AccessType.READ if rng.random() < 0.80 else AccessType.WRITE
        )
        size_kb = rng.choice([4, 8, 16, 32, 64, 128])
        requests.append(IORequest(request_id, access_type, size_kb, key))

    return requests


def print_tier_analysis() -> None:
    print("Storage tier comparison")
    print("-" * 76)
    print(
        f"{'Tier':<12} {'IOPS':>12} {'MB/s':>12} "
        f"{'Latency ms':>14} {'$/GB/month':>14}"
    )

    for tier in TIERS:
        print(
            f"{tier.name:<12} "
            f"{tier.max_iops:>12,.0f} "
            f"{tier.max_throughput_mbps:>12,.0f} "
            f"{tier.latency_ms:>14.3f} "
            f"{tier.monthly_cost_per_gb:>14.3f}"
        )


def main() -> None:
    print_tier_analysis()
    print()

    required_iops = 120_000
    required_mbps = 1_500
    capacity_gb = 2_000

    selected = choose_tier(
        required_iops,
        required_mbps,
        capacity_gb,
    )

    monthly_cost = selected.monthly_cost_per_gb * capacity_gb

    print("Capacity planning")
    print(f"Required IOPS:       {required_iops:,}")
    print(f"Required throughput: {required_mbps:,} MB/s")
    print(f"Capacity:            {capacity_gb:,} GB")
    print(f"Selected tier:       {selected.name}")
    print(f"Estimated monthly:   ${monthly_cost:,.2f}")
    print()

    simulator = StorageSimulator(selected, cache_capacity=32)
    workload = generate_workload(2_000)

    start = time.perf_counter()

    for request in workload:
        simulator.process(request)

    elapsed = time.perf_counter() - start
    metrics = simulator.metrics

    print("Workload simulation")
    print(f"Requests:            {metrics.requests:,}")
    print(f"Reads:               {metrics.reads:,}")
    print(f"Writes:              {metrics.writes:,}")
    print(f"Cache hits:          {metrics.cache_hits:,}")
    print(f"Cache misses:        {metrics.cache_misses:,}")
    print(f"Cache hit ratio:     {metrics.cache_hit_ratio:.2%}")
    print(f"Average latency:     {metrics.average_latency_ms:.4f} ms")
    print(f"Modeled throughput:  {metrics.throughput_mbps:.2f} MB/s")
    print(f"CPU simulation time: {elapsed:.6f} s")
    print()

    for request_size in (4, 64, 256):
        print(
            f"Sustainable IOPS at {request_size:>3} KB: "
            f"{simulator.sustainable_iops(request_size):,.0f}"
        )

    print()
    print("Optimization interpretation:")
    if metrics.cache_hit_ratio >= 0.70:
        print("- The workload has strong locality; caching materially reduces storage reads.")
    else:
        print("- Cache locality is limited; increasing cache size may have modest benefit.")

    if required_iops > selected.max_iops * 0.80:
        print("- IOPS utilization is high; consider workload distribution or a faster tier.")

    if required_mbps > selected.max_throughput_mbps * 0.80:
        print("- Throughput utilization is high; larger sequential I/O or more devices may help.")

    print("- Benchmark production storage with the real workload before changing tiers.")
    print("- Avoid caching sensitive data without appropriate access-control and eviction policies.")


if __name__ == "__main__":
    main()
