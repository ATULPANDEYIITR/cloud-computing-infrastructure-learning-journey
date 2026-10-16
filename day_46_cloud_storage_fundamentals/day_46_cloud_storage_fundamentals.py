#!/usr/bin/env python3
"""Cloud storage fundamentals: durability, availability, replication, redundancy, and storage classes.

Run with Python 3.10 or later:
    python cloud_storage_fundamentals.py

The simulation uses only the Python standard library. Its probabilities and
latencies are illustrative and are not measurements of any cloud provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil, log
from random import Random
from statistics import mean
from typing import Iterable


class StorageClass(str, Enum):
    STANDARD = "STANDARD"
    INFREQUENT_ACCESS = "INFREQUENT_ACCESS"
    ARCHIVE = "ARCHIVE"


class ReplicationMode(str, Enum):
    SINGLE_COPY = "SINGLE_COPY"
    SYNCHRONOUS = "SYNCHRONOUS"
    ASYNCHRONOUS = "ASYNCHRONOUS"


@dataclass(frozen=True)
class StorageClassPolicy:
    name: StorageClass
    monthly_cost_per_gb: float
    retrieval_cost_per_gb: float
    minimum_retention_days: int
    retrieval_latency_seconds: float
    minimum_billable_gb: float = 0.0

    def __post_init__(self) -> None:
        if min(
            self.monthly_cost_per_gb,
            self.retrieval_cost_per_gb,
            self.retrieval_latency_seconds,
            self.minimum_billable_gb,
        ) < 0:
            raise ValueError("Storage costs, latency, and billing size cannot be negative")
        if self.minimum_retention_days < 0:
            raise ValueError("Minimum retention cannot be negative")


STORAGE_POLICIES = {
    StorageClass.STANDARD: StorageClassPolicy(
        StorageClass.STANDARD, 0.023, 0.0, 0, 0.05
    ),
    StorageClass.INFREQUENT_ACCESS: StorageClassPolicy(
        StorageClass.INFREQUENT_ACCESS, 0.0125, 0.01, 30, 0.1
    ),
    StorageClass.ARCHIVE: StorageClassPolicy(
        StorageClass.ARCHIVE, 0.004, 0.03, 90, 3600
    ),
}


@dataclass
class StoredObject:
    key: str
    size_gb: float
    storage_class: StorageClass
    created_day: int
    checksum: str
    replicas: set[str] = field(default_factory=set)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Object key cannot be empty")
        if self.size_gb <= 0:
            raise ValueError("Object size must be positive")
        if self.created_day < 0:
            raise ValueError("Creation day cannot be negative")
        if not self.checksum.strip():
            raise ValueError("A content checksum is required")


@dataclass
class StorageRegion:
    name: str
    available: bool = True
    objects: dict[str, StoredObject] = field(default_factory=dict)


class StorageError(Exception):
    """Base exception for storage operations."""


class ObjectNotFound(StorageError):
    pass


class RegionUnavailable(StorageError):
    pass


class ReplicationError(StorageError):
    pass


class CloudStorage:
    """A small object-storage model with region-aware replication."""

    def __init__(
        self,
        region_names: Iterable[str],
        replication_mode: ReplicationMode = ReplicationMode.ASYNCHRONOUS,
    ) -> None:
        names = list(region_names)
        if not names or len(set(names)) != len(names):
            raise ValueError("Provide at least one uniquely named region")
        self.regions = {name: StorageRegion(name) for name in names}
        self.replication_mode = replication_mode
        self._primary_region = names[0]
        self._pending_replication: list[tuple[str, StoredObject]] = []
        self._versions: dict[str, int] = {}
        self._lost_writes: list[str] = []

    @property
    def primary_region(self) -> str:
        return self._primary_region

    def put(
        self,
        key: str,
        size_gb: float,
        storage_class: StorageClass,
        checksum: str,
        day: int = 0,
    ) -> StoredObject:
        primary = self.regions[self._primary_region]
        if not primary.available:
            raise RegionUnavailable("The primary region is unavailable")

        version = self._versions.get(key, 0) + 1
        candidate = StoredObject(
            key=key,
            size_gb=size_gb,
            storage_class=storage_class,
            created_day=day,
            checksum=checksum,
            replicas={self._primary_region},
            version=version,
        )

        other_regions = [
            region for region in self.regions.values()
            if region.name != self._primary_region
        ]

        if self.replication_mode == ReplicationMode.SINGLE_COPY:
            primary.objects[key] = candidate
        elif self.replication_mode == ReplicationMode.SYNCHRONOUS:
            if any(not region.available for region in other_regions):
                raise ReplicationError(
                    "Synchronous write rejected because a replica region is unavailable"
                )
            candidate.replicas.update(region.name for region in other_regions)
            primary.objects[key] = candidate
            for region in other_regions:
                region.objects[key] = candidate
        else:
            primary.objects[key] = candidate
            for region in other_regions:
                self._pending_replication.append((region.name, candidate))

        self._versions[key] = version
        return candidate

    def replicate_pending(self) -> int:
        """Deliver queued asynchronous replicas to available destinations."""
        remaining: list[tuple[str, StoredObject]] = []
        completed = 0

        for region_name, obj in self._pending_replication:
            region = self.regions[region_name]
            if not region.available:
                remaining.append((region_name, obj))
                continue

            current = region.objects.get(obj.key)
            if current is None or current.version <= obj.version:
                region.objects[obj.key] = obj
                obj.replicas.add(region_name)
                completed += 1

        self._pending_replication = remaining
        return completed

    def read(self, key: str, preferred_region: str | None = None) -> StoredObject:
        if preferred_region is not None:
            if preferred_region not in self.regions:
                raise ValueError(f"Unknown region: {preferred_region}")
            candidates = [self.regions[preferred_region]]
        else:
            candidates = list(self.regions.values())

        for region in candidates:
            if region.available and key in region.objects:
                return region.objects[key]

        raise ObjectNotFound(f"No accessible replica exists for {key!r}")

    def set_region_availability(self, region_name: str, available: bool) -> None:
        if region_name not in self.regions:
            raise ValueError(f"Unknown region: {region_name}")
        self.regions[region_name].available = available

    def failover(self, region_name: str) -> None:
        if region_name not in self.regions:
            raise ValueError(f"Unknown region: {region_name}")
        if not self.regions[region_name].available:
            raise RegionUnavailable("Cannot promote an unavailable region")
        if not self.regions[region_name].objects:
            raise StorageError("Cannot promote an empty region")

        self._primary_region = region_name

    def simulate_region_loss(self, region_name: str) -> list[str]:
        """Remove one region's data to illustrate the impact of redundancy."""
        if region_name not in self.regions:
            raise ValueError(f"Unknown region: {region_name}")

        region = self.regions[region_name]
        region.available = False
        lost = []

        for key in list(region.objects):
            surviving = any(
                other.available and key in other.objects
                for other in self.regions.values()
                if other.name != region_name
            )
            if not surviving:
                lost.append(key)
                self._lost_writes.append(key)

        return lost

    def accessible_regions(self, key: str) -> list[str]:
        return [
            region.name
            for region in self.regions.values()
            if region.available and key in region.objects
        ]

    def durability_estimate(self, independent_copy_loss_probability: float) -> float:
        """Estimate object loss probability for independent complete-copy failures."""
        if not 0 <= independent_copy_loss_probability <= 1:
            raise ValueError("Failure probability must be between zero and one")

        copies = sum(
            key_exists
            for region in self.regions.values()
            for key_exists in [region.available and bool(region.objects)]
        )
        if copies == 0:
            return 1.0
        return independent_copy_loss_probability ** copies


def expected_monthly_cost(
    size_gb: float,
    storage_class: StorageClass,
    monthly_retrieved_gb: float = 0,
    object_count: int = 1,
    replication_factor: int = 1,
    minimum_billable_gb: float | None = None,
) -> float:
    """Estimate storage and retrieval charges using explicitly supplied rates."""
    if size_gb < 0 or monthly_retrieved_gb < 0:
        raise ValueError("Storage and retrieval sizes cannot be negative")
    if object_count < 1 or replication_factor < 1:
        raise ValueError("Object count and replication factor must be positive")

    policy = STORAGE_POLICIES[storage_class]
    billable_size = max(
        size_gb,
        policy.minimum_billable_gb
        if minimum_billable_gb is None
        else minimum_billable_gb,
    )
    return (
        billable_size * policy.monthly_cost_per_gb * replication_factor
        + monthly_retrieved_gb * policy.retrieval_cost_per_gb
        + object_count * 0.0004
    )


def availability_from_independent_failure(
    component_availability: float,
    independent_components: int,
) -> float:
    """Availability of redundant components when any healthy copy can serve."""
    if not 0 <= component_availability <= 1:
        raise ValueError("Availability must be between zero and one")
    if independent_components < 1:
        raise ValueError("At least one component is required")
    return 1 - (1 - component_availability) ** independent_components


def simulate_availability(
    component_availability: float,
    independent_components: int,
    trials: int = 100_000,
    seed: int = 42,
) -> float:
    """Monte Carlo estimate; independence is an explicit simplifying assumption."""
    if not 0 <= component_availability <= 1:
        raise ValueError("Availability must be between zero and one")
    if independent_components < 1 or trials < 1:
        raise ValueError("Component count and trial count must be positive")

    rng = Random(seed)
    successful = 0
    for _ in range(trials):
        if any(
            rng.random() < component_availability
            for _ in range(independent_components)
        ):
            successful += 1
    return successful / trials


def minimum_copies_for_loss_target(
    independent_copy_loss_probability: float,
    maximum_object_loss_probability: float,
) -> int:
    """Find copies required under an independent-failure model."""
    for probability in (
        independent_copy_loss_probability,
        maximum_object_loss_probability,
    ):
        if not 0 < probability < 1:
            raise ValueError("Probabilities must be strictly between zero and one")

    if independent_copy_loss_probability <= maximum_object_loss_probability:
        return 1

    return ceil(
        log(maximum_object_loss_probability)
        / log(independent_copy_loss_probability)
    )


def demonstrate_storage_classes() -> None:
    print("\nStorage class cost comparison")
    size_gb = 500
    retrieval_gb = 20

    for storage_class in StorageClass:
        policy = STORAGE_POLICIES[storage_class]
        cost = expected_monthly_cost(
            size_gb, storage_class, retrieval_gb, object_count=100
        )
        print(
            f"{storage_class.value:20} "
            f"storage=${size_gb * policy.monthly_cost_per_gb:7.2f} "
            f"retrieval=${retrieval_gb * policy.retrieval_cost_per_gb:6.2f} "
            f"estimated total=${cost:7.2f} "
            f"latency={policy.retrieval_latency_seconds:.2f}s"
        )

    # The lowest storage price is not necessarily the lowest total cost.
    frequent_archive_reads = expected_monthly_cost(
        500, StorageClass.ARCHIVE, monthly_retrieved_gb=600
    )
    standard_reads = expected_monthly_cost(
        500, StorageClass.STANDARD, monthly_retrieved_gb=600
    )
    print(f"Archive with heavy reads: ${frequent_archive_reads:.2f}")
    print(f"Standard with heavy reads: ${standard_reads:.2f}")


def demonstrate_replication() -> None:
    print("\nReplication and regional failure")
    store = CloudStorage(
        ["ap-south-1", "ap-southeast-1", "eu-west-1"],
        ReplicationMode.ASYNCHRONOUS,
    )
    stored = store.put(
        "audit/2026-10-16.parquet",
        2.5,
        StorageClass.INFREQUENT_ACCESS,
        checksum="sha256:8f2c7d",
    )
    print(f"Write accepted in {store.primary_region}, version={stored.version}")
    print(f"Accessible copies before replication: {store.accessible_regions(stored.key)}")

    completed = store.replicate_pending()
    print(f"Replica deliveries completed: {completed}")
    print(f"Accessible copies after replication: {store.accessible_regions(stored.key)}")

    store.set_region_availability("ap-south-1", False)
    try:
        replica = store.read(stored.key, "ap-southeast-1")
        print(f"Regional failover read: {replica.key}, version={replica.version}")
        store.failover("ap-southeast-1")
        print(f"Promoted primary region: {store.primary_region}")
    except StorageError as exc:
        print(f"Recovery failed: {exc}")


def demonstrate_consistency_and_failure() -> None:
    print("\nConsistency and write failures")
    synchronous = CloudStorage(
        ["region-a", "region-b"], ReplicationMode.SYNCHRONOUS
    )
    synchronous.set_region_availability("region-b", False)

    try:
        synchronous.put(
            "reports/monthly.csv",
            0.4,
            StorageClass.STANDARD,
            checksum="sha256:abc123",
        )
    except ReplicationError as exc:
        print(f"Synchronous write rejected: {exc}")

    asynchronous = CloudStorage(
        ["region-a", "region-b"], ReplicationMode.ASYNCHRONOUS
    )
    original = asynchronous.put(
        "reports/monthly.csv",
        0.4,
        StorageClass.STANDARD,
        checksum="sha256:abc123",
    )
    asynchronous.put(
        "reports/monthly.csv",
        0.4,
        StorageClass.STANDARD,
        checksum="sha256:def456",
    )
    asynchronous.replicate_pending()
    replica = asynchronous.read("reports/monthly.csv", "region-b")
    print(f"Latest delivered version: {replica.version}")
    print(f"Primary version: {original.version + 1}")


def demonstrate_reliability_math() -> None:
    print("\nDurability and availability estimates")
    single_copy_loss = 1e-4
    target_loss = 1e-12
    copies = minimum_copies_for_loss_target(single_copy_loss, target_loss)
    print(f"Copies for illustrative loss target: {copies}")

    component_availability = 0.999
    for copies in (1, 2, 3):
        estimate = availability_from_independent_failure(
            component_availability, copies
        )
        simulation = simulate_availability(
            component_availability, copies, trials=20_000, seed=42
        )
        print(
            f"{copies} independent service paths: "
            f"analytic={estimate:.6%}, simulated={simulation:.6%}"
        )

    # Real cloud failures are correlated. Shared power, credentials, control
    # planes, accidental deletion, or compromised accounts invalidate the
    # simple independence assumption.
    print("Theoretical estimates do not replace provider durability commitments.")


def demonstrate_input_validation() -> None:
    print("\nValidation and billing boundaries")
    invalid_inputs = [
        ("empty key", lambda: StoredObject("", 1, StorageClass.STANDARD, 0, "abc")),
        ("zero size", lambda: StoredObject("x", 0, StorageClass.STANDARD, 0, "abc")),
        ("negative day", lambda: StoredObject("x", 1, StorageClass.STANDARD, -1, "abc")),
        (
            "unknown region",
            lambda: CloudStorage(["region-a"]).set_region_availability(
                "region-z", False
            ),
        ),
    ]

    for description, operation in invalid_inputs:
        try:
            operation()
        except (ValueError, StorageError) as exc:
            print(f"Rejected {description}: {exc}")

    archive = STORAGE_POLICIES[StorageClass.ARCHIVE]
    print(
        "Archive minimum retention:",
        f"{archive.minimum_retention_days} days",
    )
    print(
        "Archive latency:",
        f"{archive.retrieval_latency_seconds:.0f} seconds",
    )


def main() -> None:
    print("Cloud Storage Fundamentals")
    demonstrate_storage_classes()
    demonstrate_replication()
    demonstrate_consistency_and_failure()
    demonstrate_reliability_math()
    demonstrate_input_validation()


if __name__ == "__main__":
    main()
