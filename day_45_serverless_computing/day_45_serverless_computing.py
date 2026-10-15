#!/usr/bin/env python3
"""
Serverless Computing: Functions, Event Triggers, Execution Environments,
Cold Starts, and Elastic Scaling.

A self-contained simulation of an event-driven serverless platform.
The model includes event routing, function configuration, execution
environment reuse, initialization latency, concurrency limits, retries,
dead-letter handling, idempotency, and invocation metrics.

Run with:
    python serverless_platform.py
"""

from __future__ import annotations

import json
import math
import statistics
import time
import uuid
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


class ServerlessError(Exception):
    """Base exception for simulated serverless platform failures."""


class ConfigurationError(ServerlessError):
    """Raised when a function configuration is invalid."""


class InvocationError(ServerlessError):
    """Raised when an invocation fails."""


class ConcurrencyLimitError(ServerlessError):
    """Raised when a function exceeds its concurrency limit."""


@dataclass(frozen=True)
class Event:
    """Immutable event envelope used by event-driven functions."""

    event_id: str
    source: str
    event_type: str
    payload: dict[str, Any]
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        source: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> "Event":
        if not source.strip() or not event_type.strip():
            raise ValueError("Event source and type must not be empty.")
        if not isinstance(payload, dict):
            raise ValueError("Event payload must be a dictionary.")
        return cls(
            event_id=str(uuid.uuid4()),
            source=source,
            event_type=event_type,
            payload=dict(payload),
        )


@dataclass(frozen=True)
class FunctionConfig:
    """Execution and scaling policy for one deployed function."""

    name: str
    memory_mb: int = 256
    timeout_seconds: float = 3.0
    initialization_ms: float = 120.0
    max_concurrency: int = 10
    max_retries: int = 2
    idle_ttl_seconds: float = 300.0
    reserved_concurrency: int | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ConfigurationError("Function name cannot be empty.")
        if self.memory_mb < 128:
            raise ConfigurationError("Memory must be at least 128 MB.")
        if self.timeout_seconds <= 0:
            raise ConfigurationError("Timeout must be positive.")
        if self.initialization_ms < 0:
            raise ConfigurationError("Initialization time cannot be negative.")
        if self.max_concurrency < 1:
            raise ConfigurationError("Maximum concurrency must be positive.")
        if self.max_retries < 0:
            raise ConfigurationError("Retry count cannot be negative.")
        if self.idle_ttl_seconds < 0:
            raise ConfigurationError("Idle TTL cannot be negative.")
        if (
            self.reserved_concurrency is not None
            and self.reserved_concurrency < 1
        ):
            raise ConfigurationError("Reserved concurrency must be positive.")


@dataclass
class ExecutionEnvironment:
    """Reusable isolated execution environment for a deployed function."""

    environment_id: str
    created_at: float
    last_used_at: float
    invocation_count: int = 0
    busy: bool = False


@dataclass
class InvocationResult:
    function_name: str
    event_id: str
    success: bool
    cold_start: bool
    duration_ms: float
    initialization_ms: float
    attempts: int
    result: Any = None
    error: str | None = None


@dataclass
class FunctionMetrics:
    invocations: int = 0
    successes: int = 0
    failures: int = 0
    cold_starts: int = 0
    retries: int = 0
    throttles: int = 0
    timeouts: int = 0
    total_duration_ms: float = 0.0
    durations_ms: list[float] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        durations = self.durations_ms
        return {
            "invocations": self.invocations,
            "successes": self.successes,
            "failures": self.failures,
            "cold_starts": self.cold_starts,
            "retries": self.retries,
            "throttles": self.throttles,
            "timeouts": self.timeouts,
            "average_duration_ms": (
                round(statistics.mean(durations), 2) if durations else 0
            ),
            "p95_duration_ms": percentile(durations, 0.95),
            "total_duration_ms": round(self.total_duration_ms, 2),
        }


def percentile(values: list[float], quantile: float) -> float:
    """Return a linearly interpolated percentile without external packages."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    value = ordered[lower] + (
        ordered[upper] - ordered[lower]
    ) * (position - lower)
    return round(value, 2)


class ServerlessFunction:
    """
    Models one deployed function and its execution environments.

    Handler execution is synchronous in this educational simulator.
    Simulated durations do not represent actual provider billing or latency.
    """

    def __init__(
        self,
        config: FunctionConfig,
        handler: Callable[[Event, dict[str, Any]], Any],
    ) -> None:
        self.config = config
        self.handler = handler
        self.environments: list[ExecutionEnvironment] = []
        self.metrics = FunctionMetrics()
        self.idempotency_results: dict[str, Any] = {}
        self._idempotency_in_progress: set[str] = set()

    def _acquire_environment(
        self,
        now: float,
    ) -> tuple[ExecutionEnvironment, bool]:
        # Expired idle environments are discarded before selecting capacity.
        self.environments = [
            env
            for env in self.environments
            if env.busy
            or now - env.last_used_at <= self.config.idle_ttl_seconds
        ]

        idle = next(
            (env for env in self.environments if not env.busy),
            None,
        )

        if idle is not None:
            idle.busy = True
            return idle, False

        effective_limit = min(
            self.config.max_concurrency,
            self.config.reserved_concurrency
            if self.config.reserved_concurrency is not None
            else self.config.max_concurrency,
        )

        if len(self.environments) >= effective_limit:
            self.metrics.throttles += 1
            raise ConcurrencyLimitError(
                f"{self.config.name} reached concurrency limit "
                f"{effective_limit}."
            )

        environment = ExecutionEnvironment(
            environment_id=str(uuid.uuid4())[:8],
            created_at=now,
            last_used_at=now,
            busy=True,
        )
        self.environments.append(environment)
        return environment, True

    def invoke(
        self,
        event: Event,
        now: float | None = None,
        idempotency_key: str | None = None,
        simulated_duration_ms: float = 20.0,
        forced_failure: bool = False,
    ) -> InvocationResult:
        """Execute a function with retry, timeout, and idempotency behavior."""
        invocation_time = time.monotonic() if now is None else now

        if simulated_duration_ms < 0:
            raise ValueError("Duration cannot be negative.")

        self.metrics.invocations += 1

        if idempotency_key:
            if idempotency_key in self.idempotency_results:
                self.metrics.successes += 1
                return InvocationResult(
                    function_name=self.config.name,
                    event_id=event.event_id,
                    success=True,
                    cold_start=False,
                    duration_ms=0.0,
                    initialization_ms=0.0,
                    attempts=0,
                    result=self.idempotency_results[idempotency_key],
                )

            if idempotency_key in self._idempotency_in_progress:
                self.metrics.failures += 1
                return InvocationResult(
                    function_name=self.config.name,
                    event_id=event.event_id,
                    success=False,
                    cold_start=False,
                    duration_ms=0.0,
                    initialization_ms=0.0,
                    attempts=0,
                    error="Duplicate operation is already in progress.",
                )

            self._idempotency_in_progress.add(idempotency_key)

        cold_start = False
        initialization_ms = 0.0
        attempts = 0
        last_error: str | None = None

        try:
            for attempt in range(self.config.max_retries + 1):
                attempts += 1
                environment: ExecutionEnvironment | None = None

                try:
                    environment, is_cold = self._acquire_environment(
                        invocation_time
                    )
                    if is_cold:
                        cold_start = True
                        initialization_ms += self.config.initialization_ms

                    effective_duration = (
                        simulated_duration_ms
                        + (self.config.initialization_ms if is_cold else 0)
                    )

                    if effective_duration > self.config.timeout_seconds * 1000:
                        self.metrics.timeouts += 1
                        raise InvocationError(
                            f"Execution exceeded {self.config.timeout_seconds}s "
                            f"timeout."
                        )

                    if forced_failure:
                        raise InvocationError("Simulated downstream failure.")

                    context = {
                        "function_name": self.config.name,
                        "environment_id": environment.environment_id,
                        "memory_mb": self.config.memory_mb,
                        "attempt": attempts,
                        "cold_start": is_cold,
                    }
                    result = self.handler(event, context)

                    environment.invocation_count += 1
                    environment.last_used_at = invocation_time
                    self.metrics.successes += 1
                    self.metrics.total_duration_ms += effective_duration
                    self.metrics.durations_ms.append(effective_duration)

                    if idempotency_key:
                        self.idempotency_results[idempotency_key] = result

                    return InvocationResult(
                        function_name=self.config.name,
                        event_id=event.event_id,
                        success=True,
                        cold_start=cold_start,
                        duration_ms=effective_duration,
                        initialization_ms=initialization_ms,
                        attempts=attempts,
                        result=result,
                    )

                except ConcurrencyLimitError as exc:
                    last_error = str(exc)
                    break

                except Exception as exc:
                    last_error = str(exc)
                    if attempt < self.config.max_retries:
                        self.metrics.retries += 1

                finally:
                    if environment is not None:
                        environment.busy = False
                        environment.last_used_at = invocation_time

            self.metrics.failures += 1
            return InvocationResult(
                function_name=self.config.name,
                event_id=event.event_id,
                success=False,
                cold_start=cold_start,
                duration_ms=0.0,
                initialization_ms=initialization_ms,
                attempts=attempts,
                error=last_error,
            )

        finally:
            if idempotency_key:
                self._idempotency_in_progress.discard(idempotency_key)


class EventRouter:
    """Routes event types to functions and retains failed deliveries."""

    def __init__(self) -> None:
        self.routes: dict[str, ServerlessFunction] = {}
        self.dead_letter_queue: deque[dict[str, Any]] = deque()
        self.delivery_log: list[dict[str, Any]] = []

    def subscribe(
        self,
        event_type: str,
        function: ServerlessFunction,
    ) -> None:
        if not event_type.strip():
            raise ValueError("Event type cannot be empty.")
        if event_type in self.routes:
            raise ConfigurationError(
                f"Event type {event_type!r} already has a subscription."
            )
        self.routes[event_type] = function

    def publish(
        self,
        event: Event,
        now: float,
        forced_failure: bool = False,
    ) -> InvocationResult:
        function = self.routes.get(event.event_type)
        if function is None:
            record = {
                "event_id": event.event_id,
                "reason": "No matching subscription.",
                "event_type": event.event_type,
            }
            self.dead_letter_queue.append(record)
            raise InvocationError(record["reason"])

        result = function.invoke(
            event,
            now=now,
            idempotency_key=event.payload.get("idempotency_key"),
            simulated_duration_ms=float(
                event.payload.get("simulated_duration_ms", 20.0)
            ),
            forced_failure=forced_failure,
        )

        self.delivery_log.append(
            {
                "event_id": event.event_id,
                "function": function.config.name,
                "success": result.success,
                "attempts": result.attempts,
            }
        )

        if not result.success:
            self.dead_letter_queue.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "function": function.config.name,
                    "reason": result.error,
                    "attempts": result.attempts,
                }
            )

        return result


def validate_order(event: Event, context: dict[str, Any]) -> dict[str, Any]:
    """Validate a commerce event and return a normalized decision."""
    order_id = event.payload.get("order_id")
    amount = event.payload.get("amount")

    if not isinstance(order_id, str) or not order_id.strip():
        raise ValueError("A non-empty order_id is required.")

    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("Order amount must be numeric.")

    if not math.isfinite(float(amount)) or amount <= 0:
        raise ValueError("Order amount must be finite and positive.")

    return {
        "order_id": order_id,
        "amount": round(float(amount), 2),
        "decision": "accepted",
        "execution_environment": context["environment_id"],
        "cold_start": context["cold_start"],
    }


def resize_thumbnail(event: Event, context: dict[str, Any]) -> dict[str, Any]:
    """Model an object-storage event triggering image processing."""
    object_key = event.payload.get("object_key")
    width = event.payload.get("width")

    if not isinstance(object_key, str) or not object_key.strip():
        raise ValueError("object_key is required.")

    if not object_key.startswith("uploads/"):
        raise ValueError("Only uploads/ objects may be processed.")

    if not isinstance(width, int) or isinstance(width, bool):
        raise ValueError("Image width must be an integer.")

    if not 1 <= width <= 4096:
        raise ValueError("Image width must be between 1 and 4096.")

    return {
        "source": object_key,
        "thumbnail": f"thumbnails/{object_key.rsplit('/', 1)[-1]}",
        "width": width,
        "processor_environment": context["environment_id"],
    }


def demonstrate_environment_reuse() -> None:
    print("\n=== Execution environments and cold starts ===")

    function = ServerlessFunction(
        FunctionConfig(
            name="order-validator",
            initialization_ms=150,
            idle_ttl_seconds=10,
        ),
        validate_order,
    )

    first_event = Event.create(
        "checkout",
        "order.created",
        {"order_id": "ORD-2041", "amount": 1299.50},
    )
    second_event = Event.create(
        "checkout",
        "order.created",
        {"order_id": "ORD-2042", "amount": 499.00},
    )

    first = function.invoke(first_event, now=100.0)
    second = function.invoke(second_event, now=101.0)
    third = function.invoke(second_event, now=120.0)

    for label, result in (
        ("First invocation", first),
        ("Warm invocation", second),
        ("After idle expiry", third),
    ):
        print(
            f"{label}: success={result.success}, "
            f"cold_start={result.cold_start}, "
            f"duration={result.duration_ms}ms"
        )

    print("Metrics:", json.dumps(function.metrics.snapshot(), indent=2))


def demonstrate_event_driven_processing() -> None:
    print("\n=== Event triggers and dead-letter handling ===")

    order_function = ServerlessFunction(
        FunctionConfig(
            name="order-created-handler",
            initialization_ms=90,
            max_retries=1,
        ),
        validate_order,
    )

    image_function = ServerlessFunction(
        FunctionConfig(
            name="thumbnail-handler",
            initialization_ms=200,
            max_retries=0,
        ),
        resize_thumbnail,
    )

    router = EventRouter()
    router.subscribe("order.created", order_function)
    router.subscribe("storage.object.created", image_function)

    events = [
        Event.create(
            "checkout",
            "order.created",
            {
                "order_id": "ORD-3100",
                "amount": 780,
                "idempotency_key": "payment:ORD-3100",
            },
        ),
        Event.create(
            "object-storage",
            "storage.object.created",
            {"object_key": "uploads/product-81.jpg", "width": 640},
        ),
        Event.create(
            "checkout",
            "order.created",
            {"order_id": "", "amount": 780},
        ),
    ]

    for event in events:
        result = router.publish(event, now=200.0)
        print(
            f"{event.event_type}: success={result.success}, "
            f"attempts={result.attempts}, error={result.error}"
        )

    print("Dead-letter queue:")
    print(json.dumps(list(router.dead_letter_queue), indent=2))


def demonstrate_idempotency() -> None:
    print("\n=== Idempotency for at-least-once delivery ===")

    function = ServerlessFunction(
        FunctionConfig(name="idempotent-order-handler"),
        validate_order,
    )
    event = Event.create(
        "checkout",
        "order.created",
        {"order_id": "ORD-4100", "amount": 2450},
    )

    first = function.invoke(
        event,
        now=300.0,
        idempotency_key="order:ORD-4100",
    )
    duplicate = function.invoke(
        event,
        now=301.0,
        idempotency_key="order:ORD-4100",
    )

    print("First result:", first.result)
    print(
        "Duplicate result:",
        duplicate.result,
        "duration:",
        duplicate.duration_ms,
    )
    print(
        "Successful invocations:",
        function.metrics.successes,
        "Function executions:",
        len(function.environments[0:1]),
    )

    # Production idempotency must be durable and atomic across instances.
    # A local dictionary is only a single-process demonstration.


def demonstrate_scaling_and_capacity() -> None:
    print("\n=== Concurrency capacity ===")

    function = ServerlessFunction(
        FunctionConfig(
            name="report-generator",
            max_concurrency=2,
            reserved_concurrency=2,
        ),
        lambda event, context: {
            "report_id": event.payload["report_id"],
            "environment": context["environment_id"],
        },
    )

    # This synchronous simulation reuses environments sequentially.
    # Real concurrency requires overlapping invocations; this loop illustrates
    # environment reuse and the configured capacity, not a load benchmark.
    for report_number in range(4):
        event = Event.create(
            "scheduler",
            "report.generate",
            {"report_id": f"RPT-{report_number + 1}"},
        )
        result = function.invoke(
            event,
            now=400.0 + report_number,
        )
        print(
            f"Report {report_number + 1}: "
            f"success={result.success}, "
            f"environment_count={len(function.environments)}"
        )

    print("Capacity policy:", asdict(function.config))
    print("Metrics:", json.dumps(function.metrics.snapshot(), indent=2))


def demonstrate_validation_and_failures() -> None:
    print("\n=== Input validation, timeout, and retries ===")

    function = ServerlessFunction(
        FunctionConfig(
            name="bounded-handler",
            timeout_seconds=0.05,
            max_retries=1,
            initialization_ms=0,
        ),
        validate_order,
    )

    cases = [
        (
            "Invalid amount",
            {"order_id": "ORD-5001", "amount": -1},
            10,
        ),
        (
            "Execution timeout",
            {"order_id": "ORD-5002", "amount": 100},
            100,
        ),
    ]

    for label, payload, duration in cases:
        event = Event.create("checkout", "order.created", payload)
        result = function.invoke(
            event,
            now=500.0,
            simulated_duration_ms=duration,
        )
        print(
            f"{label}: success={result.success}, "
            f"attempts={result.attempts}, error={result.error}"
        )

    print("Metrics:", json.dumps(function.metrics.snapshot(), indent=2))


def main() -> None:
    print("SERVERLESS COMPUTING PLATFORM SIMULATION")
    demonstrate_environment_reuse()
    demonstrate_event_driven_processing()
    demonstrate_idempotency()
    demonstrate_scaling_and_capacity()
    demonstrate_validation_and_failures()

    print("\n=== Platform design considerations ===")
    print(
        "Cold starts depend on runtime initialization, dependency loading, "
        "runtime reuse, and provider scheduling."
    )
    print(
        "Scaling limits must account for downstream database connections, "
        "API quotas, and the concurrency policy of each function."
    )
    print(
        "Retries require idempotent operations because event delivery may "
        "occur more than once."
    )
    print(
        "Production metrics should separate initialization latency, "
        "handler latency, queue delay, throttling, and downstream latency."
    )


if __name__ == "__main__":
    main()
