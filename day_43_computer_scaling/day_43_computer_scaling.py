#!/usr/bin/env python3
"""
Compute Scaling: Vertical Scaling, Horizontal Scaling, Capacity Limits,
and Workload Planning.

A self-contained compute capacity simulator using only the Python standard
library. It models instance sizing, replica allocation, workload demand,
resource bottlenecks, scaling decisions, cooldown periods, and cost estimates.

Run:
    python compute_scaling.py

The model is educational. Its capacity and cost values are configurable
estimates, not measurements from a real cloud provider.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterable


class ScalingMode(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class Resource(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    CONNECTIONS = "connections"
    NETWORK = "network"


@dataclass(frozen=True)
class InstanceType:
    name: str
    vcpus: int
    memory_gib: float
    max_connections: int
    network_gbps: float
    hourly_cost: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Instance name cannot be empty.")
        if self.vcpus < 1:
            raise ValueError("An instance must have at least one vCPU.")
        if self.memory_gib <= 0 or self.network_gbps <= 0:
            raise ValueError("Memory and network capacity must be positive.")
        if self.max_connections < 1 or self.hourly_cost < 0:
            raise ValueError("Connection capacity must be positive and cost non-negative.")


@dataclass(frozen=True)
class Workload:
    name: str
    requests_per_second: float
    cpu_cores_per_request: float
    memory_gib_per_replica: float
    connections_per_replica: int
    network_gbps_per_replica: float
    latency_budget_ms: float = 250.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Workload name cannot be empty.")
        if self.requests_per_second < 0:
            raise ValueError("Request rate cannot be negative.")
        if self.cpu_cores_per_request <= 0:
            raise ValueError("CPU demand per request must be positive.")
        if self.memory_gib_per_replica <= 0:
            raise ValueError("Replica memory demand must be positive.")
        if self.connections_per_replica < 0:
            raise ValueError("Connection demand cannot be negative.")
        if self.network_gbps_per_replica < 0:
            raise ValueError("Network demand cannot be negative.")
        if self.latency_budget_ms <= 0:
            raise ValueError("Latency budget must be positive.")


@dataclass(frozen=True)
class CapacityProfile:
    """
    Capacity assumptions for a particular workload.

    CPU service demand is approximated as CPU cores consumed per request.
    Real systems also require benchmark data, request concurrency,
    dependency latency, and queueing measurements.
    """
    cpu_utilization_target: float = 0.65
    memory_utilization_target: float = 0.75
    connection_utilization_target: float = 0.70
    network_utilization_target: float = 0.70
    requests_per_cpu_core_second: float = 1.0
    safety_factor: float = 1.25

    def __post_init__(self) -> None:
        for name in (
            "cpu_utilization_target",
            "memory_utilization_target",
            "connection_utilization_target",
            "network_utilization_target",
        ):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be greater than zero and at most one.")
        if self.requests_per_cpu_core_second <= 0:
            raise ValueError("Benchmark throughput must be positive.")
        if self.safety_factor < 1:
            raise ValueError("Safety factor must be at least one.")


@dataclass
class ScalingDecision:
    mode: ScalingMode
    instance: InstanceType
    replicas: int
    requested_rps: float
    estimated_capacity_rps: float
    estimated_cpu_utilization: float
    estimated_memory_utilization: float
    estimated_connection_utilization: float
    estimated_network_utilization: float
    hourly_cost: float
    feasible: bool
    limiting_resources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["mode"] = self.mode.value
        return result


@dataclass(frozen=True)
class ScalingPolicy:
    scale_out_threshold: float = 0.70
    scale_in_threshold: float = 0.30
    cooldown_seconds: int = 120
    minimum_replicas: int = 2
    maximum_replicas: int = 20
    maximum_vertical_vcpus: int = 64
    maximum_vertical_memory_gib: float = 512.0

    def __post_init__(self) -> None:
        if not 0 < self.scale_in_threshold < self.scale_out_threshold <= 1:
            raise ValueError("Scaling thresholds must be ordered and within (0, 1].")
        if self.cooldown_seconds < 0:
            raise ValueError("Cooldown cannot be negative.")
        if self.minimum_replicas < 1:
            raise ValueError("Minimum replicas must be at least one.")
        if self.maximum_replicas < self.minimum_replicas:
            raise ValueError("Maximum replicas must not be below the minimum.")
        if self.maximum_vertical_vcpus < 1 or self.maximum_vertical_memory_gib <= 0:
            raise ValueError("Vertical scaling limits must be positive.")


def build_instance_catalog() -> list[InstanceType]:
    """Return a hypothetical instance catalog with increasing resource sizes."""
    return [
        InstanceType("compute-small", 2, 4, 500, 1.0, 0.08),
        InstanceType("compute-medium", 4, 8, 1500, 2.0, 0.16),
        InstanceType("compute-large", 8, 16, 3000, 5.0, 0.32),
        InstanceType("compute-xlarge", 16, 32, 6000, 10.0, 0.64),
        InstanceType("compute-2xlarge", 32, 64, 12000, 20.0, 1.28),
        InstanceType("compute-4xlarge", 64, 128, 24000, 40.0, 2.56),
    ]


def required_cpu_cores(
    workload: Workload,
    profile: CapacityProfile,
) -> float:
    """Estimate CPU cores needed at the configured target utilization."""
    raw_cores = (
        workload.requests_per_second
        * workload.cpu_cores_per_request
        / profile.requests_per_cpu_core_second
    )
    return raw_cores * profile.safety_factor / profile.cpu_utilization_target


def estimate_instance_capacity(
    instance: InstanceType,
    workload: Workload,
    profile: CapacityProfile,
) -> tuple[float, list[str]]:
    """
    Calculate approximate per-instance throughput.

    The minimum across CPU, memory, connections, and network represents
    the bottleneck. Memory is treated as a workload admission constraint,
    rather than assuming that more CPU can solve insufficient RAM.
    """
    cpu_capacity = (
        instance.vcpus
        * profile.requests_per_cpu_core_second
        * profile.cpu_utilization_target
        / (workload.cpu_cores_per_request * profile.safety_factor)
    )

    memory_capacity = (
        instance.memory_gib * profile.memory_utilization_target
        / workload.memory_gib_per_replica
    )

    connection_capacity = (
        instance.max_connections
        * profile.connection_utilization_target
        / max(workload.connections_per_replica, 1)
    )

    network_capacity = (
        instance.network_gbps
        * profile.network_utilization_target
        / max(workload.network_gbps_per_replica, 0.001)
    )

    limits = {
        Resource.CPU.value: cpu_capacity,
        Resource.MEMORY.value: memory_capacity,
        Resource.CONNECTIONS.value: connection_capacity,
        Resource.NETWORK.value: network_capacity,
    }

    capacity = min(limits.values())
    bottlenecks = [
        name for name, value in limits.items()
        if math.isclose(value, capacity, rel_tol=1e-9)
    ]
    return max(0.0, capacity), bottlenecks


def evaluate_deployment(
    instance: InstanceType,
    replicas: int,
    workload: Workload,
    profile: CapacityProfile,
    mode: ScalingMode,
) -> ScalingDecision:
    """Evaluate the safety of a deployment and its approximate cost."""
    if replicas < 1:
        raise ValueError("Replica count must be at least one.")

    per_instance_capacity, bottlenecks = estimate_instance_capacity(
        instance, workload, profile
    )
    capacity = per_instance_capacity * replicas

    cpu_demand = (
        workload.requests_per_second
        * workload.cpu_cores_per_request
        / profile.requests_per_cpu_core_second
    )
    total_cpu = instance.vcpus * replicas

    cpu_utilization = cpu_demand / total_cpu if total_cpu else 0.0
    memory_utilization = (
        workload.memory_gib_per_replica / instance.memory_gib
    )
    connection_utilization = (
        workload.connections_per_replica / instance.max_connections
    )
    network_utilization = (
        workload.network_gbps_per_replica / instance.network_gbps
    )

    limits = []
    if cpu_utilization > profile.cpu_utilization_target:
        limits.append(Resource.CPU.value)
    if memory_utilization > profile.memory_utilization_target:
        limits.append(Resource.MEMORY.value)
    if connection_utilization > profile.connection_utilization_target:
        limits.append(Resource.CONNECTIONS.value)
    if network_utilization > profile.network_utilization_target:
        limits.append(Resource.NETWORK.value)
    if workload.requests_per_second > capacity:
        limits.extend(resource for resource in bottlenecks if resource not in limits)

    feasible = (
        workload.requests_per_second <= capacity
        and memory_utilization <= profile.memory_utilization_target
        and connection_utilization <= profile.connection_utilization_target
        and network_utilization <= profile.network_utilization_target
        and cpu_utilization <= profile.cpu_utilization_target
    )

    return ScalingDecision(
        mode=mode,
        instance=instance,
        replicas=replicas,
        requested_rps=workload.requests_per_second,
        estimated_capacity_rps=capacity,
        estimated_cpu_utilization=cpu_utilization,
        estimated_memory_utilization=memory_utilization,
        estimated_connection_utilization=connection_utilization,
        estimated_network_utilization=network_utilization,
        hourly_cost=instance.hourly_cost * replicas,
        feasible=feasible,
        limiting_resources=sorted(set(limits)),
    )


def plan_vertical_scaling(
    catalog: Iterable[InstanceType],
    workload: Workload,
    profile: CapacityProfile,
    current_replicas: int = 1,
    policy: ScalingPolicy | None = None,
) -> ScalingDecision | None:
    """
    Select the smallest eligible instance type that meets demand.

    Vertical scaling increases resources assigned to each instance.
    The number of replicas remains unchanged in this plan.
    """
    policy = policy or ScalingPolicy()
    candidates = [
        instance for instance in catalog
        if instance.vcpus <= policy.maximum_vertical_vcpus
        and instance.memory_gib <= policy.maximum_vertical_memory_gib
    ]

    for instance in sorted(candidates, key=lambda item: item.hourly_cost):
        decision = evaluate_deployment(
            instance, current_replicas, workload, profile, ScalingMode.VERTICAL
        )
        if decision.feasible:
            return decision

    return None


def plan_horizontal_scaling(
    instance: InstanceType,
    workload: Workload,
    profile: CapacityProfile,
    policy: ScalingPolicy | None = None,
) -> ScalingDecision | None:
    """
    Select the smallest replica count that meets demand.

    Horizontal scaling adds independent instances. It requires that the
    application, sessions, storage, and dependencies support distribution.
    """
    policy = policy or ScalingPolicy()

    for replicas in range(policy.minimum_replicas, policy.maximum_replicas + 1):
        decision = evaluate_deployment(
            instance, replicas, workload, profile, ScalingMode.HORIZONTAL
        )
        if decision.feasible:
            return decision

    return None


@dataclass
class Autoscaler:
    """A small time-driven replica autoscaler with cooldown protection."""

    policy: ScalingPolicy
    replicas: int
    last_change_seconds: float = -math.inf

    def observe(
        self,
        utilization: float,
        timestamp_seconds: float,
    ) -> str:
        if not 0 <= utilization <= 10:
            raise ValueError("Utilization must be a finite, non-negative ratio.")
        if not math.isfinite(timestamp_seconds):
            raise ValueError("Timestamp must be finite.")
        if timestamp_seconds < 0:
            raise ValueError("Timestamp cannot be negative.")
        if self.replicas < self.policy.minimum_replicas:
            raise ValueError("Replica count is below the configured minimum.")
        if self.replicas > self.policy.maximum_replicas:
            raise ValueError("Replica count exceeds the configured maximum.")

        if timestamp_seconds - self.last_change_seconds < self.policy.cooldown_seconds:
            return "cooldown"

        if utilization > self.policy.scale_out_threshold:
            if self.replicas >= self.policy.maximum_replicas:
                return "scale-out-blocked-at-maximum"
            self.replicas += 1
            self.last_change_seconds = timestamp_seconds
            return "scale-out"

        if utilization < self.policy.scale_in_threshold:
            if self.replicas <= self.policy.minimum_replicas:
                return "scale-in-blocked-at-minimum"
            self.replicas -= 1
            self.last_change_seconds = timestamp_seconds
            return "scale-in"

        return "stable"


def percentile(values: list[float], quantile: float) -> float:
    """Compute a linearly interpolated percentile without dependencies."""
    if not values:
        raise ValueError("At least one observation is required.")
    if not 0 <= quantile <= 1:
        raise ValueError("Quantile must be between zero and one.")

    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (
        position - lower
    )


def workload_forecast(
    hourly_rps: list[float],
    growth_rate: float,
    safety_factor: float = 1.25,
) -> dict[str, float]:
    """
    Forecast demand from observed hourly traffic.

    growth_rate is a fractional increase, so 0.20 represents 20 percent.
    The safety factor covers uncertainty, not a guarantee of availability.
    """
    if not hourly_rps:
        raise ValueError("Hourly observations cannot be empty.")
    if any(not math.isfinite(value) or value < 0 for value in hourly_rps):
        raise ValueError("Traffic observations must be finite and non-negative.")
    if not math.isfinite(growth_rate) or growth_rate < 0:
        raise ValueError("Growth rate must be finite and non-negative.")
    if not math.isfinite(safety_factor) or safety_factor < 1:
        raise ValueError("Safety factor must be finite and at least one.")

    peak = max(hourly_rps)
    p95 = percentile(hourly_rps, 0.95)
    growth_multiplier = 1 + growth_rate

    return {
        "mean_rps": statistics.fmean(hourly_rps),
        "p95_rps": p95,
        "peak_rps": peak,
        "forecast_p95_rps": p95 * growth_multiplier,
        "planning_rps": p95 * growth_multiplier * safety_factor,
    }


def estimate_monthly_cost(hourly_cost: float, hours: int = 730) -> float:
    """Estimate compute-only monthly cost using a configurable hour count."""
    if hourly_cost < 0 or not math.isfinite(hourly_cost):
        raise ValueError("Hourly cost must be finite and non-negative.")
    if hours < 0:
        raise ValueError("Hours cannot be negative.")
    return hourly_cost * hours


def print_decision(title: str, decision: ScalingDecision | None) -> None:
    print(f"\n{title}")
    if decision is None:
        print("No feasible configuration found within the configured limits.")
        return

    print(f"  Mode: {decision.mode.value}")
    print(f"  Instance: {decision.instance.name}")
    print(f"  Replicas: {decision.replicas}")
    print(f"  Demand: {decision.requested_rps:.2f} requests/second")
    print(f"  Estimated capacity: {decision.estimated_capacity_rps:.2f} requests/second")
    print(f"  Estimated hourly cost: ${decision.hourly_cost:.2f}")
    print(f"  Estimated monthly compute cost: ${estimate_monthly_cost(decision.hourly_cost):.2f}")
    print(f"  Feasible under modeled constraints: {decision.feasible}")
    print(f"  Limiting resources: {', '.join(decision.limiting_resources) or 'none'}")


def run_demonstration() -> None:
    catalog = build_instance_catalog()
    profile = CapacityProfile()
    policy = ScalingPolicy()

    historical_traffic = [
        120, 145, 138, 160, 175, 210, 245, 300,
        360, 420, 510, 480, 450, 390, 350, 320,
        290, 275, 260, 230, 210, 190, 160, 140,
    ]

    forecast = workload_forecast(
        historical_traffic,
        growth_rate=0.30,
        safety_factor=1.20,
    )

    print("Compute Scaling and Workload Planning")
    print(json.dumps(forecast, indent=2))

    workload = Workload(
        name="order-api",
        requests_per_second=forecast["planning_rps"],
        cpu_cores_per_request=0.08,
        memory_gib_per_replica=2.0,
        connections_per_replica=300,
        network_gbps_per_replica=0.15,
        latency_budget_ms=200,
    )

    vertical = plan_vertical_scaling(
        catalog, workload, profile, current_replicas=2, policy=policy
    )
    print_decision("Vertical scaling plan", vertical)

    horizontal = plan_horizontal_scaling(
        catalog[1], workload, profile, policy
    )
    print_decision("Horizontal scaling plan", horizontal)

    print("\nAutoscaling event simulation")
    autoscaler = Autoscaler(policy=policy, replicas=3)
    observations = [
        (0, 0.45),
        (30, 0.88),
        (90, 0.92),
        (160, 0.91),
        (300, 0.20),
        (450, 0.18),
        (600, 0.50),
    ]

    for timestamp, utilization in observations:
        action = autoscaler.observe(utilization, timestamp)
        print(
            f"  t={timestamp:>3}s utilization={utilization:.0%} "
            f"action={action} replicas={autoscaler.replicas}"
        )

    print("\nCapacity-boundary checks")
    smallest = catalog[0]
    single_instance_capacity, bottlenecks = estimate_instance_capacity(
        smallest, workload, profile
    )
    print(f"  Smallest instance capacity: {single_instance_capacity:.2f} requests/second")
    print(f"  Bottleneck(s): {', '.join(bottlenecks)}")

    constrained = plan_horizontal_scaling(
        smallest,
        workload,
        profile,
        ScalingPolicy(minimum_replicas=2, maximum_replicas=3),
    )
    print_decision("Constrained horizontal plan", constrained)


def run_self_tests() -> None:
    catalog = build_instance_catalog()
    profile = CapacityProfile()

    # Empty traffic and zero demand are valid planning conditions.
    empty_forecast = workload_forecast([0, 0, 0], growth_rate=0)
    assert empty_forecast["planning_rps"] == 0

    # Invalid workload inputs must fail early instead of creating bad plans.
    try:
        Workload("invalid", -1, 0.1, 1, 10, 0.1)
    except ValueError:
        pass
    else:
        raise AssertionError("Negative request rates must be rejected.")

    # Horizontal scaling must respect replica limits.
    policy = ScalingPolicy(minimum_replicas=2, maximum_replicas=20)
    workload = Workload("test-api", 100, 0.05, 1, 100, 0.05)
    plan = plan_horizontal_scaling(catalog[1], workload, profile, policy)
    assert plan is not None
    assert policy.minimum_replicas <= plan.replicas <= policy.maximum_replicas
    assert plan.feasible

    # A workload that exceeds all configured capacities must return no plan.
    impossible = Workload(
        "oversized-api", 1_000_000, 1.0, 1000, 1_000_000, 1000
    )
    assert plan_vertical_scaling(catalog, impossible, profile) is None
    assert plan_horizontal_scaling(
        catalog[0],
        impossible,
        profile,
        ScalingPolicy(minimum_replicas=2, maximum_replicas=3),
    ) is None

    # Autoscaling must not scale below the minimum replica count.
    scaler = Autoscaler(policy=policy, replicas=2)
    assert scaler.observe(0.05, 0) == "scale-in-blocked-at-minimum"

    # Percentile and monthly cost calculations have deterministic boundaries.
    assert percentile([10, 20, 30], 0) == 10
    assert percentile([10, 20, 30], 1) == 30
    assert estimate_monthly_cost(1.0, 730) == 730.0

    print("\nAll self-tests passed.")


if __name__ == "__main__":
    run_demonstration()
    run_self_tests()
