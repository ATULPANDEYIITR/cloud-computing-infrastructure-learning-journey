#!/usr/bin/env python3
"""
Auto Scaling Laboratory

A self-contained simulation of cloud auto scaling, including:
- Scaling groups and instance lifecycle management.
- CPU and request-latency metrics.
- Metric thresholds, rolling averages, and cooldown periods.
- Target-tracking, step-scaling, and scheduled policies.
- Minimum, maximum, and desired capacity.
- Instance health, replacement, and warm-up behavior.
- Scale-in protection, stabilization, and capacity limits.
- Event history, cost estimation, and unit tests.

Run with:
    python autoscaling_lab.py

The simulation uses synthetic metrics and does not provision cloud resources.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import unittest
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable


class InstanceState(str, Enum):
    PENDING = "pending"
    WARMING = "warming"
    IN_SERVICE = "in_service"
    UNHEALTHY = "unhealthy"
    TERMINATING = "terminating"


class PolicyType(str, Enum):
    TARGET_TRACKING = "target_tracking"
    STEP_SCALING = "step_scaling"
    SCHEDULED = "scheduled"


@dataclass(frozen=True)
class ScalingMetric:
    timestamp: datetime
    cpu_percent: float
    requests_per_second: float
    p95_latency_ms: float
    error_rate_percent: float

    def __post_init__(self) -> None:
        if not 0 <= self.cpu_percent <= 100:
            raise ValueError("CPU utilization must be between 0 and 100.")
        if self.requests_per_second < 0:
            raise ValueError("Request rate cannot be negative.")
        if self.p95_latency_ms < 0:
            raise ValueError("Latency cannot be negative.")
        if not 0 <= self.error_rate_percent <= 100:
            raise ValueError("Error rate must be between 0 and 100.")


@dataclass
class Instance:
    instance_id: str
    state: InstanceState
    launched_at: datetime
    ready_at: datetime
    protected_from_scale_in: bool = False
    health_reason: str = "initializing"


@dataclass(frozen=True)
class ScalingEvent:
    timestamp: datetime
    action: str
    old_capacity: int
    new_capacity: int
    reason: str


@dataclass(frozen=True)
class ScalingPolicy:
    name: str
    policy_type: PolicyType
    metric_name: str
    target_value: float
    scale_out_cooldown_seconds: int = 60
    scale_in_cooldown_seconds: int = 180
    scale_out_step: int = 2
    scale_in_step: int = 1
    minimum_change: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Policy name cannot be empty.")
        if not math.isfinite(self.target_value) or self.target_value <= 0:
            raise ValueError("Target value must be positive and finite.")
        if self.scale_out_cooldown_seconds < 0:
            raise ValueError("Scale-out cooldown cannot be negative.")
        if self.scale_in_cooldown_seconds < 0:
            raise ValueError("Scale-in cooldown cannot be negative.")
        if min(self.scale_out_step, self.scale_in_step, self.minimum_change) < 1:
            raise ValueError("Scaling steps must be positive.")


@dataclass
class ScalingGroup:
    name: str
    min_size: int
    max_size: int
    desired_capacity: int
    instance_warmup_seconds: int = 90
    health_check_grace_seconds: int = 120
    instances: dict[str, Instance] = field(default_factory=dict)
    events: list[ScalingEvent] = field(default_factory=list)
    last_scale_out: datetime | None = None
    last_scale_in: datetime | None = None
    _instance_counter: int = 0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Scaling group name cannot be empty.")
        if self.min_size < 0:
            raise ValueError("Minimum capacity cannot be negative.")
        if self.max_size < self.min_size:
            raise ValueError("Maximum capacity cannot be below minimum capacity.")
        if not self.min_size <= self.desired_capacity <= self.max_size:
            raise ValueError("Desired capacity must be within group limits.")
        if self.instance_warmup_seconds < 0:
            raise ValueError("Instance warm-up cannot be negative.")
        if self.health_check_grace_seconds < 0:
            raise ValueError("Health-check grace period cannot be negative.")

    @property
    def actual_capacity(self) -> int:
        return sum(
            instance.state in {
                InstanceState.PENDING,
                InstanceState.WARMING,
                InstanceState.IN_SERVICE,
                InstanceState.UNHEALTHY,
            }
            for instance in self.instances.values()
        )

    @property
    def in_service_capacity(self) -> int:
        return sum(
            instance.state == InstanceState.IN_SERVICE
            for instance in self.instances.values()
        )

    def _new_instance(self, now: datetime) -> Instance:
        self._instance_counter += 1
        instance_id = f"{self.name}-instance-{self._instance_counter:04d}"
        state = (
            InstanceState.IN_SERVICE
            if self.instance_warmup_seconds == 0
            else InstanceState.WARMING
        )
        instance = Instance(
            instance_id=instance_id,
            state=state,
            launched_at=now,
            ready_at=now + timedelta(seconds=self.instance_warmup_seconds),
        )
        self.instances[instance_id] = instance
        return instance

    def reconcile(self, now: datetime) -> None:
        """Bring actual capacity toward desired capacity without exceeding limits."""
        self.desired_capacity = min(
            self.max_size, max(self.min_size, self.desired_capacity)
        )

        for instance in self.instances.values():
            if (
                instance.state == InstanceState.WARMING
                and now >= instance.ready_at
            ):
                instance.state = InstanceState.IN_SERVICE
                instance.health_reason = "healthy"

        while self.actual_capacity < self.desired_capacity:
            self._new_instance(now)

        while self.actual_capacity > self.desired_capacity:
            candidates = [
                instance
                for instance in self.instances.values()
                if instance.state in {
                    InstanceState.PENDING,
                    InstanceState.WARMING,
                    InstanceState.IN_SERVICE,
                }
                and not instance.protected_from_scale_in
            ]
            if not candidates:
                break

            # Prefer removing the least recently launched eligible instance.
            victim = min(candidates, key=lambda instance: instance.launched_at)
            victim.state = InstanceState.TERMINATING

        for instance in self.instances.values():
            if instance.state == InstanceState.TERMINATING:
                del self.instances[instance.instance_id]
                break

    def change_capacity(
        self, delta: int, now: datetime, reason: str
    ) -> bool:
        """Apply a bounded desired-capacity change and record its cause."""
        if delta == 0:
            return False

        old_capacity = self.desired_capacity
        new_capacity = min(self.max_size, max(self.min_size, old_capacity + delta))

        if new_capacity == old_capacity:
            self.events.append(
                ScalingEvent(now, "no_change", old_capacity, old_capacity, reason)
            )
            return False

        self.desired_capacity = new_capacity
        action = "scale_out" if new_capacity > old_capacity else "scale_in"
        self.events.append(
            ScalingEvent(now, action, old_capacity, new_capacity, reason)
        )

        if action == "scale_out":
            self.last_scale_out = now
        else:
            self.last_scale_in = now

        self.reconcile(now)
        return True

    def mark_unhealthy(self, instance_id: str, now: datetime) -> None:
        """Replace failed instances while preserving the desired capacity target."""
        instance = self.instances.get(instance_id)
        if instance is None:
            raise KeyError(f"Unknown instance: {instance_id}")
        if instance.state == InstanceState.TERMINATING:
            raise ValueError("A terminating instance cannot be marked unhealthy.")

        instance.state = InstanceState.UNHEALTHY
        instance.health_reason = "failed health check"
        self.events.append(
            ScalingEvent(
                now, "health_failure", self.desired_capacity,
                self.desired_capacity, instance_id
            )
        )
        # Remove the failed instance and let reconciliation restore capacity.
        del self.instances[instance_id]
        self.reconcile(now)

    def capacity_snapshot(self) -> dict[str, int]:
        counts = {state.value: 0 for state in InstanceState}
        for instance in self.instances.values():
            counts[instance.state.value] += 1
        return {
            "minimum": self.min_size,
            "desired": self.desired_capacity,
            "maximum": self.max_size,
            "actual": self.actual_capacity,
            "in_service": self.in_service_capacity,
            **counts,
        }


class MetricWindow:
    """Retain recent metric observations for moving-average decisions."""

    def __init__(self, max_samples: int = 5) -> None:
        if max_samples < 1:
            raise ValueError("Metric window must retain at least one sample.")
        self.samples: deque[ScalingMetric] = deque(maxlen=max_samples)

    def add(self, metric: ScalingMetric) -> None:
        if self.samples and metric.timestamp < self.samples[-1].timestamp:
            raise ValueError("Metrics must be supplied in chronological order.")
        self.samples.append(metric)

    def average(self, metric_name: str) -> float:
        if not self.samples:
            raise RuntimeError("Cannot calculate an average without metrics.")
        allowed = {
            "cpu_percent",
            "requests_per_second",
            "p95_latency_ms",
            "error_rate_percent",
        }
        if metric_name not in allowed:
            raise ValueError(f"Unsupported metric: {metric_name}")
        return statistics.fmean(
            getattr(sample, metric_name) for sample in self.samples
        )


class AutoScaler:
    def __init__(
        self,
        group: ScalingGroup,
        policies: Iterable[ScalingPolicy],
        metric_window_size: int = 3,
        evaluation_periods: int = 2,
        scale_out_threshold: float = 1.10,
        scale_in_threshold: float = 0.75,
    ) -> None:
        if evaluation_periods < 1:
            raise ValueError("Evaluation periods must be positive.")
        if not 0 < scale_in_threshold < 1 < scale_out_threshold:
            raise ValueError("Thresholds must leave a neutral band around 1.")
        self.group = group
        self.policies = list(policies)
        self.window = MetricWindow(metric_window_size)
        self.evaluation_periods = evaluation_periods
        self.scale_out_threshold = scale_out_threshold
        self.scale_in_threshold = scale_in_threshold
        self._out_breaches = 0
        self._in_breaches = 0

    def evaluate(self, metric: ScalingMetric) -> str:
        self.window.add(metric)
        self.group.reconcile(metric.timestamp)

        if self.group.in_service_capacity == 0:
            return "waiting_for_healthy_capacity"

        policy = next(
            (
                candidate
                for candidate in self.policies
                if candidate.policy_type == PolicyType.TARGET_TRACKING
            ),
            None,
        )
        if policy is None:
            return "no_target_tracking_policy"

        observed = self.window.average(policy.metric_name)
        ratio = observed / policy.target_value

        # Separate scale-out and scale-in counters prevent a single spike from
        # immediately reversing direction when a later sample is lower.
        if ratio >= self.scale_out_threshold:
            self._out_breaches += 1
            self._in_breaches = 0
        elif ratio <= self.scale_in_threshold:
            self._in_breaches += 1
            self._out_breaches = 0
        else:
            self._out_breaches = 0
            self._in_breaches = 0
            return f"stable: {policy.metric_name}={observed:.2f}"

        now = metric.timestamp

        if self._out_breaches >= self.evaluation_periods:
            if (
                self.group.last_scale_out is not None
                and (now - self.group.last_scale_out).total_seconds()
                < policy.scale_out_cooldown_seconds
            ):
                return "scale_out_suppressed_by_cooldown"

            # Proportional target tracking estimates the capacity needed to
            # return the metric toward its target. Ceiling avoids under-scaling.
            raw_delta = math.ceil(
                self.group.desired_capacity * (ratio - 1.0)
            )
            delta = max(policy.minimum_change, raw_delta)
            delta = min(delta, policy.scale_out_step * 3)
            self._out_breaches = 0
            self.group.change_capacity(
                delta, now,
                f"{policy.name}: {policy.metric_name}={observed:.2f}, "
                f"target={policy.target_value:.2f}"
            )
            return f"scale_out_requested:{delta}"

        if self._in_breaches >= self.evaluation_periods:
            if (
                self.group.last_scale_in is not None
                and (now - self.group.last_scale_in).total_seconds()
                < policy.scale_in_cooldown_seconds
            ):
                return "scale_in_suppressed_by_cooldown"

            # Conservative scale-in reduces the chance of oscillation.
            self._in_breaches = 0
            changed = self.group.change_capacity(
                -policy.scale_in_step, now,
                f"{policy.name}: sustained low {policy.metric_name}={observed:.2f}"
            )
            return "scale_in_requested" if changed else "capacity_unchanged"

        return "waiting_for_additional_evaluation_periods"

    def evaluate_step_policy(
        self, metric: ScalingMetric, policy: ScalingPolicy
    ) -> str:
        """Apply an explicit step policy to one observation."""
        if policy.policy_type != PolicyType.STEP_SCALING:
            raise ValueError("The supplied policy is not a step-scaling policy.")

        observed = getattr(metric, policy.metric_name, None)
        if observed is None:
            raise ValueError(f"Unsupported metric: {policy.metric_name}")

        ratio = observed / policy.target_value
        if ratio >= self.scale_out_threshold:
            delta = policy.scale_out_step
        elif ratio <= self.scale_in_threshold:
            delta = -policy.scale_in_step
        else:
            return "within_step_policy_band"

        changed = self.group.change_capacity(
            delta, metric.timestamp,
            f"{policy.name}: explicit step ratio={ratio:.2f}"
        )
        return "step_applied" if changed else "step_limited_by_capacity"


@dataclass(frozen=True)
class ScheduledAction:
    name: str
    at: datetime
    desired_capacity: int


def apply_scheduled_action(
    group: ScalingGroup, action: ScheduledAction, now: datetime
) -> str:
    if action.at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Scheduled actions require timezone-aware timestamps.")
    if now < action.at:
        return "not_due"
    if not group.min_size <= action.desired_capacity <= group.max_size:
        raise ValueError("Scheduled capacity violates scaling-group limits.")

    delta = action.desired_capacity - group.desired_capacity
    changed = group.change_capacity(
        delta, now, f"scheduled action: {action.name}"
    )
    return "scheduled_capacity_applied" if changed else "already_at_target"


def estimate_hourly_cost(
    running_instances: int,
    hourly_instance_price: float,
    hours: float,
) -> float:
    if running_instances < 0 or hourly_instance_price < 0 or hours < 0:
        raise ValueError("Cost inputs cannot be negative.")
    return running_instances * hourly_instance_price * hours


def create_metric(
    now: datetime,
    cpu: float,
    requests: float,
    latency: float,
    errors: float = 0.2,
) -> ScalingMetric:
    return ScalingMetric(
        timestamp=now,
        cpu_percent=cpu,
        requests_per_second=requests,
        p95_latency_ms=latency,
        error_rate_percent=errors,
    )


def run_simulation() -> None:
    print("AUTO SCALING LABORATORY")
    print("=" * 72)

    now = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
    group = ScalingGroup(
        name="checkout-api",
        min_size=2,
        max_size=10,
        desired_capacity=2,
        instance_warmup_seconds=60,
    )
    group.reconcile(now)

    target_policy = ScalingPolicy(
        name="checkout-cpu-target",
        policy_type=PolicyType.TARGET_TRACKING,
        metric_name="cpu_percent",
        target_value=55.0,
        scale_out_cooldown_seconds=120,
        scale_in_cooldown_seconds=180,
        scale_out_step=2,
        scale_in_step=1,
    )
    scaler = AutoScaler(
        group,
        [target_policy],
        metric_window_size=2,
        evaluation_periods=2,
    )

    # Increasing load causes sustained CPU threshold breaches. Warm-up delays
    # readiness, so desired capacity and serving capacity are tracked separately.
    workload = [
        (42, 150, 180),
        (63, 220, 240),
        (72, 280, 310),
        (81, 340, 380),
        (68, 310, 290),
        (39, 180, 170),
        (31, 130, 150),
        (28, 100, 120),
        (26, 90, 110),
    ]

    for index, (cpu, requests, latency) in enumerate(workload):
        sample_time = now + timedelta(seconds=index * 90)
        metric = create_metric(sample_time, cpu, requests, latency)
        decision = scaler.evaluate(metric)
        snapshot = group.capacity_snapshot()
        print(
            f"{sample_time.isoformat()} | CPU {cpu:>5.1f}% | "
            f"decision={decision:<42} | desired={snapshot['desired']} "
            f"| serving={snapshot['in_service']} | actual={snapshot['actual']}"
        )

    print("\nScheduled capacity adjustment")
    scheduled = ScheduledAction(
        name="weekday traffic preparation",
        at=now + timedelta(hours=1),
        desired_capacity=5,
    )
    scheduled_time = now + timedelta(hours=1)
    print(apply_scheduled_action(group, scheduled, scheduled_time))
    print("Capacity:", json.dumps(group.capacity_snapshot(), indent=2))

    print("\nHealth replacement")
    if group.instances:
        instance_id = next(iter(group.instances))
        group.mark_unhealthy(instance_id, scheduled_time)
        print("Failed instance:", instance_id)
        print("Capacity after replacement:", group.capacity_snapshot())

    print("\nEstimated compute cost")
    cost = estimate_hourly_cost(
        running_instances=group.actual_capacity,
        hourly_instance_price=0.048,
        hours=24,
    )
    print(f"Illustrative daily compute cost: ${cost:.2f}")

    print("\nScaling event history")
    for event in group.events:
        print(
            f"{event.timestamp.isoformat()} | {event.action:<14} | "
            f"{event.old_capacity} -> {event.new_capacity} | {event.reason}"
        )


class AutoScalingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
        self.group = ScalingGroup(
            "test-api", min_size=1, max_size=5, desired_capacity=2,
            instance_warmup_seconds=0,
        )
        self.group.reconcile(self.now)

    def test_group_starts_at_desired_capacity(self) -> None:
        self.assertEqual(self.group.actual_capacity, 2)
        self.assertEqual(self.group.in_service_capacity, 2)

    def test_capacity_is_bounded(self) -> None:
        self.group.change_capacity(100, self.now, "test upper bound")
        self.assertEqual(self.group.desired_capacity, 5)
        self.group.change_capacity(-100, self.now, "test lower bound")
        self.assertEqual(self.group.desired_capacity, 1)

    def test_metric_rejects_invalid_cpu(self) -> None:
        with self.assertRaises(ValueError):
            create_metric(self.now, 101, 100, 50)

    def test_protected_instances_are_not_removed(self) -> None:
        protected = next(iter(self.group.instances.values()))
        protected.protected_from_scale_in = True
        self.group.desired_capacity = 1
        self.group.reconcile(self.now)
        self.assertIn(protected.instance_id, self.group.instances)
        self.assertEqual(self.group.actual_capacity, 2)

    def test_metric_window_rejects_out_of_order_samples(self) -> None:
        window = MetricWindow()
        window.add(create_metric(self.now, 40, 100, 80))
        with self.assertRaises(ValueError):
            window.add(create_metric(self.now - timedelta(seconds=1), 40, 100, 80))

    def test_cost_calculation(self) -> None:
        self.assertAlmostEqual(estimate_hourly_cost(3, 0.05, 2), 0.30)

    def test_warmup_transitions_to_in_service(self) -> None:
        warming_group = ScalingGroup(
            "warm-api", 1, 3, 1, instance_warmup_seconds=30
        )
        warming_group.reconcile(self.now)
        self.assertEqual(warming_group.actual_capacity, 1)
        self.assertEqual(warming_group.in_service_capacity, 0)
        warming_group.reconcile(self.now + timedelta(seconds=31))
        self.assertEqual(warming_group.in_service_capacity, 1)


if __name__ == "__main__":
    random.seed(7)
    run_simulation()
    print("\nAUTOMATED TESTS")
    unittest.main(argv=["autoscaling_lab.py"], exit=False, verbosity=2)
