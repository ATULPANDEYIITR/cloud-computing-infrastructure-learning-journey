#!/usr/bin/env python3
"""Model geographic regions, availability zones, failure domains, and resilient workloads.

Standard-library only. Run with Python 3.10 or later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from typing import Iterable
import json
import random
import unittest


class ZoneState(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class PlacementMode(str, Enum):
    SINGLE_ZONE = "single_zone"
    MULTI_ZONE = "multi_zone"


@dataclass(frozen=True)
class Region:
    region_id: str
    name: str
    continent: str
    data_residency_group: str

    def __post_init__(self) -> None:
        if not self.region_id.strip():
            raise ValueError("Region identifier cannot be empty.")


@dataclass
class AvailabilityZone:
    zone_id: str
    region_id: str
    failure_domains: set[str]
    state: ZoneState = ZoneState.AVAILABLE
    capacity: int = 100
    used_capacity: int = 0
    latency_ms: float = 5.0

    @property
    def available_capacity(self) -> int:
        if self.state == ZoneState.UNAVAILABLE:
            return 0
        if self.state == ZoneState.DEGRADED:
            return max(0, (self.capacity - self.used_capacity) // 2)
        return max(0, self.capacity - self.used_capacity)


@dataclass
class Workload:
    workload_id: str
    required_replicas: int
    replicas_by_zone: dict[str, int] = field(default_factory=dict)
    minimum_healthy_replicas: int = 1
    placement_mode: PlacementMode = PlacementMode.MULTI_ZONE

    def healthy_replicas(self, zones: dict[str, AvailabilityZone]) -> int:
        return sum(
            count
            for zone_id, count in self.replicas_by_zone.items()
            if zone_id in zones and zones[zone_id].state == ZoneState.AVAILABLE
        )

    def is_available(self, zones: dict[str, AvailabilityZone]) -> bool:
        return self.healthy_replicas(zones) >= self.minimum_healthy_replicas


class Infrastructure:
    """Maintain topology and reject invalid cross-region zone relationships."""

    def __init__(self) -> None:
        self.regions: dict[str, Region] = {}
        self.zones: dict[str, AvailabilityZone] = {}
        self.workloads: dict[str, Workload] = {}

    def add_region(self, region: Region) -> None:
        if region.region_id in self.regions:
            raise ValueError(f"Duplicate region: {region.region_id}")
        self.regions[region.region_id] = region

    def add_zone(self, zone: AvailabilityZone) -> None:
        if zone.zone_id in self.zones:
            raise ValueError(f"Duplicate zone: {zone.zone_id}")
        if zone.region_id not in self.regions:
            raise ValueError("A zone must belong to a registered region.")
        if zone.capacity < 0 or zone.used_capacity < 0:
            raise ValueError("Capacity cannot be negative.")
        if zone.used_capacity > zone.capacity:
            raise ValueError("Used capacity exceeds total capacity.")
        if zone.latency_ms < 0:
            raise ValueError("Latency cannot be negative.")
        self.zones[zone.zone_id] = zone

    def add_workload(self, workload: Workload) -> None:
        if workload.workload_id in self.workloads:
            raise ValueError("Duplicate workload identifier.")
        if workload.required_replicas < 1:
            raise ValueError("At least one replica is required.")
        if not 1 <= workload.minimum_healthy_replicas <= workload.required_replicas:
            raise ValueError("Invalid minimum healthy replica requirement.")
        self.workloads[workload.workload_id] = workload

    def place_replicas(self, workload_id: str, zone_ids: Iterable[str]) -> None:
        """Place one replica per selected zone after validating all placements."""
        workload = self.workloads[workload_id]
        selected = list(zone_ids)

        if len(selected) != workload.required_replicas:
            raise ValueError("Placement count must equal required replica count.")
        if len(set(selected)) != len(selected):
            raise ValueError("Replicas must occupy distinct zones.")

        target_zones: list[AvailabilityZone] = []
        for zone_id in selected:
            if zone_id not in self.zones:
                raise ValueError(f"Unknown zone: {zone_id}")
            zone = self.zones[zone_id]
            if zone.state != ZoneState.AVAILABLE:
                raise ValueError(f"Zone {zone_id} is not fully available.")
            if zone.available_capacity < 1:
                raise ValueError(f"Zone {zone_id} lacks capacity.")
            target_zones.append(zone)

        region_ids = {zone.region_id for zone in target_zones}
        if workload.placement_mode == PlacementMode.MULTI_ZONE and len(selected) > 1:
            if len(region_ids) != 1:
                raise ValueError(
                    "A regional multi-zone workload must use zones in one region."
                )

        # Validate before mutating capacity to avoid partial placement.
        for zone in target_zones:
            zone.used_capacity += 1
        workload.replicas_by_zone = dict.fromkeys(selected, 1)

    def simulate_zone_failure(self, zone_id: str) -> dict[str, object]:
        if zone_id not in self.zones:
            raise ValueError(f"Unknown zone: {zone_id}")

        zone = self.zones[zone_id]
        previous_state = zone.state
        zone.state = ZoneState.UNAVAILABLE

        affected: list[dict[str, object]] = []
        for workload in self.workloads.values():
            if zone_id in workload.replicas_by_zone:
                healthy = workload.healthy_replicas(self.zones)
                affected.append({
                    "workload": workload.workload_id,
                    "healthy_replicas": healthy,
                    "required_healthy": workload.minimum_healthy_replicas,
                    "available": workload.is_available(self.zones),
                })

        return {
            "failed_zone": zone_id,
            "previous_state": previous_state.value,
            "affected_workloads": affected,
        }

    def restore_zone(self, zone_id: str) -> None:
        self.zones[zone_id].state = ZoneState.AVAILABLE

    def recommend_placement(
        self, required_replicas: int, preferred_region: str
    ) -> list[str]:
        """Choose distinct zones, favoring different modeled failure domains."""
        candidates = [
            zone for zone in self.zones.values()
            if zone.region_id == preferred_region
            and zone.state == ZoneState.AVAILABLE
            and zone.available_capacity > 0
        ]
        candidates.sort(key=lambda zone: (zone.latency_ms, zone.zone_id))

        chosen: list[AvailabilityZone] = []
        domains_used: set[str] = set()

        for zone in candidates:
            # A domain represents a modeled shared dependency such as power.
            # Real independence requires provider-specific topology evidence.
            if domains_used.isdisjoint(zone.failure_domains):
                chosen.append(zone)
                domains_used.update(zone.failure_domains)
            if len(chosen) == required_replicas:
                return [zone.zone_id for zone in chosen]

        raise RuntimeError(
            "Cannot find enough zones with distinct modeled failure domains."
        )

    def report(self) -> dict[str, object]:
        region_report: dict[str, object] = {}
        for region in self.regions.values():
            regional_zones = [
                zone for zone in self.zones.values()
                if zone.region_id == region.region_id
            ]
            region_report[region.region_id] = {
                "name": region.name,
                "zone_count": len(regional_zones),
                "available_zones": sum(
                    zone.state == ZoneState.AVAILABLE for zone in regional_zones
                ),
                "zones": [
                    {
                        "id": zone.zone_id,
                        "state": zone.state.value,
                        "capacity": zone.capacity,
                        "used_capacity": zone.used_capacity,
                        "latency_ms": zone.latency_ms,
                        "failure_domains": sorted(zone.failure_domains),
                    }
                    for zone in regional_zones
                ],
            }

        workload_report = {}
        for workload in self.workloads.values():
            workload_report[workload.workload_id] = {
                "placement": workload.replicas_by_zone,
                "healthy_replicas": workload.healthy_replicas(self.zones),
                "minimum_healthy": workload.minimum_healthy_replicas,
                "available": workload.is_available(self.zones),
            }

        return {"regions": region_report, "workloads": workload_report}


def build_demo_infrastructure() -> Infrastructure:
    infra = Infrastructure()
    infra.add_region(Region("ap-south", "South Asia", "Asia", "IN"))
    infra.add_region(Region("eu-central", "Central Europe", "Europe", "EU"))

    for zone in [
        AvailabilityZone("south-a", "ap-south", {"power-a", "network-a"}, capacity=20, latency_ms=4),
        AvailabilityZone("south-b", "ap-south", {"power-b", "network-b"}, capacity=20, latency_ms=6),
        AvailabilityZone("south-c", "ap-south", {"power-c", "network-c"}, capacity=20, latency_ms=8),
        AvailabilityZone("eu-a", "eu-central", {"eu-power-a"}, capacity=20, latency_ms=90),
        AvailabilityZone("eu-b", "eu-central", {"eu-power-b"}, capacity=20, latency_ms=95),
    ]:
        infra.add_zone(zone)

    infra.add_workload(
        Workload("payments-api", 3, minimum_healthy_replicas=2)
    )
    placement = infra.recommend_placement(3, "ap-south")
    infra.place_replicas("payments-api", placement)
    return infra


def estimate_availability(component_availabilities: list[float]) -> float:
    """Availability of independent serial dependencies is their product."""
    if not component_availabilities:
        return 1.0
    if any(not 0.0 <= value <= 1.0 for value in component_availabilities):
        raise ValueError("Availability values must be between zero and one.")
    result = 1.0
    for value in component_availabilities:
        result *= value
    return result


def estimate_parallel_availability(component_availabilities: list[float]) -> float:
    """At least one independent replica works; assumes independent failures."""
    if not component_availabilities:
        return 0.0
    if any(not 0.0 <= value <= 1.0 for value in component_availabilities):
        raise ValueError("Availability values must be between zero and one.")
    probability_all_fail = 1.0
    for value in component_availabilities:
        probability_all_fail *= 1.0 - value
    return 1.0 - probability_all_fail


def monte_carlo_zone_outages(
    zone_ids: list[str],
    replica_count: int,
    minimum_healthy: int,
    outage_probability: float,
    trials: int = 10_000,
    seed: int = 17,
) -> float:
    """Estimate workload availability under an independent zone-outage model."""
    if not zone_ids or len(set(zone_ids)) != len(zone_ids):
        raise ValueError("Provide distinct zone identifiers.")
    if not 1 <= minimum_healthy <= replica_count <= len(zone_ids):
        raise ValueError("Replica and zone counts are inconsistent.")
    if not 0 <= outage_probability <= 1:
        raise ValueError("Outage probability must be between zero and one.")
    if trials < 1:
        raise ValueError("Trials must be positive.")

    rng = random.Random(seed)
    successful_trials = 0
    for _ in range(trials):
        healthy = sum(
            rng.random() >= outage_probability
            for _ in range(replica_count)
        )
        successful_trials += healthy >= minimum_healthy
    return successful_trials / trials


class InfrastructureTests(unittest.TestCase):
    def test_parallel_availability(self) -> None:
        self.assertAlmostEqual(
            estimate_parallel_availability([0.99, 0.99]),
            0.9999,
        )

    def test_serial_dependencies(self) -> None:
        self.assertAlmostEqual(
            estimate_availability([0.99, 0.98]),
            0.9702,
        )

    def test_invalid_availability(self) -> None:
        with self.assertRaises(ValueError):
            estimate_availability([1.1])

    def test_failure_tolerance(self) -> None:
        infra = build_demo_infrastructure()
        result = infra.simulate_zone_failure("south-a")
        self.assertTrue(result["affected_workloads"][0]["available"])
        infra.restore_zone("south-a")
        self.assertEqual(
            infra.workloads["payments-api"].healthy_replicas(infra.zones),
            3,
        )

    def test_atomic_placement_validation(self) -> None:
        infra = build_demo_infrastructure()
        before = {
            zone_id: zone.used_capacity
            for zone_id, zone in infra.zones.items()
        }
        with self.assertRaises(ValueError):
            infra.place_replicas("payments-api", ["south-a", "south-a", "south-c"])
        after = {
            zone_id: zone.used_capacity
            for zone_id, zone in infra.zones.items()
        }
        self.assertEqual(before, after)


def main() -> None:
    infrastructure = build_demo_infrastructure()

    print("REGIONAL TOPOLOGY AND WORKLOAD PLACEMENT")
    print(json.dumps(infrastructure.report(), indent=2))

    print("\nSIMULATED AVAILABILITY-ZONE OUTAGE")
    print(json.dumps(
        infrastructure.simulate_zone_failure("south-b"),
        indent=2,
    ))

    print("\nAVAILABILITY ESTIMATES")
    single_dependency = estimate_availability([0.999])
    two_independent_replicas = estimate_parallel_availability([0.999, 0.999])
    print(f"Single component: {single_dependency:.6%}")
    print(f"Two parallel replicas: {two_independent_replicas:.6%}")
    print(
        "Three zones, two healthy replicas required: "
        f"{monte_carlo_zone_outages(['a', 'b', 'c'], 3, 2, 0.01):.4%}"
    )

    print("\nAUTOMATED VALIDATION")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InfrastructureTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
