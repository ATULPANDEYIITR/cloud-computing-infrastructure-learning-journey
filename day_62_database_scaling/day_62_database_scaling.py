#!/usr/bin/env python3
"""
Database Scaling Case Study

Models:
- Vertical scaling
- Horizontal scaling
- Range partitioning
- Sharding
- Read replicas
- Routing decisions
- Capacity and consistency trade-offs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable


class ScalingStrategy(Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    PARTITIONING = "partitioning"
    SHARDING = "sharding"
    READ_REPLICA = "read_replica"


class OperationType(Enum):
    READ = "read"
    WRITE = "write"


class Consistency(Enum):
    STRONG = "strong"
    EVENTUAL = "eventual"


@dataclass(frozen=True)
class Request:
    request_id: str
    customer_id: int
    operation: OperationType
    consistency: Consistency = Consistency.EVENTUAL


@dataclass
class DatabaseNode:
    node_id: str
    region: str
    capacity_ops: int
    active_ops: int = 0
    healthy: bool = True

    @property
    def utilization(self) -> float:
        if self.capacity_ops <= 0:
            return 1.0
        return self.active_ops / self.capacity_ops

    def can_accept(self) -> bool:
        return self.healthy and self.active_ops < self.capacity_ops


@dataclass
class Partition:
    partition_id: str
    minimum_customer_id: int
    maximum_customer_id: int
    rows: list[dict] = field(default_factory=list)

    def contains(self, customer_id: int) -> bool:
        return self.minimum_customer_id <= customer_id <= self.maximum_customer_id

    def insert(self, row: dict) -> None:
        customer_id = row["customer_id"]
        if not self.contains(customer_id):
            raise ValueError(
                f"Customer {customer_id} does not belong to partition "
                f"{self.partition_id}"
            )
        self.rows.append(row)


class PartitionedTable:
    """
    Partitioning keeps one logical table while physically separating rows.
    This example uses customer-ID range partitioning.
    """

    def __init__(self, partitions: Iterable[Partition]):
        self.partitions = list(partitions)

    def locate(self, customer_id: int) -> Partition:
        for partition in self.partitions:
            if partition.contains(customer_id):
                return partition
        raise KeyError(f"No partition exists for customer {customer_id}")

    def insert(self, row: dict) -> None:
        self.locate(row["customer_id"]).insert(row)

    def query_customer(self, customer_id: int) -> list[dict]:
        # Partition pruning means only one partition is searched.
        return [
            row
            for row in self.locate(customer_id).rows
            if row["customer_id"] == customer_id
        ]


class ShardRouter:
    """
    A deterministic hash router distributes logical data across independent
    database shards. Production systems normally use a stable hashing scheme
    and a routing metadata service so adding shards does not move every row.
    """

    def __init__(self, shard_ids: list[str]):
        if not shard_ids:
            raise ValueError("At least one shard is required")
        self.shard_ids = tuple(shard_ids)

    def shard_for(self, customer_id: int) -> str:
        return self.shard_ids[customer_id % len(self.shard_ids)]


class ReadReplicaCluster:
    """
    Writes go to the primary. Eventual-consistency reads can use replicas.
    Strong reads are routed to the primary.
    """

    def __init__(self, primary: DatabaseNode, replicas: list[DatabaseNode]):
        self.primary = primary
        self.replicas = replicas
        self.replica_cursor = 0

    def route(self, operation: OperationType, consistency: Consistency) -> DatabaseNode:
        if operation == OperationType.WRITE or consistency == Consistency.STRONG:
            if not self.primary.can_accept():
                raise RuntimeError("Primary cannot accept the request")
            return self.primary

        healthy = [node for node in self.replicas if node.can_accept()]
        if not healthy:
            if self.primary.can_accept():
                return self.primary
            raise RuntimeError("No database node can serve the read")

        node = healthy[self.replica_cursor % len(healthy)]
        self.replica_cursor += 1
        return node


class DatabaseScaler:
    """
    Provides simple capacity decisions. The thresholds are deliberately
    explicit so scaling policy is observable and testable.
    """

    def __init__(self, scale_out_threshold: float = 0.75):
        if not 0 < scale_out_threshold < 1:
            raise ValueError("Threshold must be between 0 and 1")
        self.scale_out_threshold = scale_out_threshold

    def choose_strategy(
        self,
        workload_ops: int,
        node_capacity_ops: int,
        write_ratio: float,
        working_set_rows: int,
    ) -> ScalingStrategy:
        if workload_ops <= 0:
            raise ValueError("Workload must be positive")
        if node_capacity_ops <= 0:
            raise ValueError("Node capacity must be positive")
        if not 0 <= write_ratio <= 1:
            raise ValueError("Write ratio must be between 0 and 1")

        utilization = workload_ops / node_capacity_ops

        if utilization <= 0.70:
            return ScalingStrategy.VERTICAL

        if write_ratio < 0.30:
            return ScalingStrategy.READ_REPLICA

        if working_set_rows > 10_000_000:
            return ScalingStrategy.PARTITIONING

        return ScalingStrategy.HORIZONTAL


class Metrics:
    def __init__(self):
        self.counts = defaultdict(int)
        self.latencies_ms: list[float] = []

    def record(self, operation: OperationType, latency_ms: float) -> None:
        self.counts[operation.value] += 1
        self.latencies_ms.append(latency_ms)

    def summary(self) -> dict:
        if not self.latencies_ms:
            return {
                "operations": dict(self.counts),
                "average_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
            }

        ordered = sorted(self.latencies_ms)
        p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
        return {
            "operations": dict(self.counts),
            "average_latency_ms": sum(ordered) / len(ordered),
            "p95_latency_ms": ordered[p95_index],
        }


def build_partitioned_orders() -> PartitionedTable:
    return PartitionedTable(
        [
            Partition("p0_999", 0, 999),
            Partition("p1000_1999", 1000, 1999),
            Partition("p2000_2999", 2000, 2999),
        ]
    )


def simulate_workload(cluster: ReadReplicaCluster) -> Metrics:
    metrics = Metrics()

    requests = [
        Request("r1", 101, OperationType.READ, Consistency.EVENTUAL),
        Request("r2", 102, OperationType.READ, Consistency.EVENTUAL),
        Request("r3", 103, OperationType.READ, Consistency.STRONG),
        Request("r4", 104, OperationType.WRITE, Consistency.STRONG),
        Request("r5", 105, OperationType.READ, Consistency.EVENTUAL),
        Request("r6", 106, OperationType.WRITE, Consistency.STRONG),
    ]

    for request in requests:
        node = cluster.route(request.operation, request.consistency)
        node.active_ops += 1

        simulated_latency = (
            5.0
            if node is cluster.primary
            else 2.5
        )
        metrics.record(request.operation, simulated_latency)

        # Release the operation immediately after the simulation step.
        node.active_ops -= 1

    return metrics


def validate_edge_cases() -> None:
    partitions = build_partitioned_orders()

    partitions.insert({"order_id": 1, "customer_id": 101, "amount": 250.0})
    partitions.insert({"order_id": 2, "customer_id": 1500, "amount": 400.0})

    assert len(partitions.query_customer(101)) == 1
    assert len(partitions.query_customer(999)) == 0

    try:
        partitions.insert({"order_id": 3, "customer_id": 4000, "amount": 100.0})
    except KeyError:
        pass
    else:
        raise AssertionError("Out-of-range customer should fail")

    router = ShardRouter(["shard-a", "shard-b", "shard-c"])
    assert router.shard_for(100) == "shard-a"
    assert router.shard_for(101) == "shard-b"

    primary = DatabaseNode("primary", "ap-south", 1000)
    replicas = [
        DatabaseNode("replica-1", "ap-south", 800),
        DatabaseNode("replica-2", "ap-south", 800),
    ]

    cluster = ReadReplicaCluster(primary, replicas)
    assert cluster.route(
        OperationType.WRITE, Consistency.STRONG
    ) is primary
    assert cluster.route(
        OperationType.READ, Consistency.STRONG
    ) is primary

    replicas[0].healthy = False
    replicas[1].healthy = False

    # Eventual reads safely fall back to the primary when replicas are down.
    assert cluster.route(
        OperationType.READ, Consistency.EVENTUAL
    ) is primary


def main() -> None:
    print("Database Scaling Case Study")
    print("=" * 60)

    scaler = DatabaseScaler()

    scenarios = [
        (500, 1000, 0.50, 100_000),
        (900, 1000, 0.10, 500_000),
        (900, 1000, 0.80, 20_000_000),
        (950, 1000, 0.50, 2_000_000),
    ]

    print("\nScaling decisions:")
    for workload, capacity, write_ratio, rows in scenarios:
        strategy = scaler.choose_strategy(
            workload,
            capacity,
            write_ratio,
            rows,
        )
        print(
            f"workload={workload}, capacity={capacity}, "
            f"write_ratio={write_ratio:.0%}, rows={rows:,} "
            f"-> {strategy.value}"
        )

    print("\nPartitioning:")
    table = build_partitioned_orders()

    now = datetime.now(timezone.utc)
    for index, customer_id in enumerate([101, 1500, 2100, 101], start=1):
        table.insert(
            {
                "order_id": index,
                "customer_id": customer_id,
                "created_at": now - timedelta(minutes=index),
                "amount": 100.0 * index,
            }
        )

    for partition in table.partitions:
        print(
            f"{partition.partition_id}: "
            f"{len(partition.rows)} rows"
        )

    print("\nSharding:")
    router = ShardRouter(["shard-a", "shard-b", "shard-c"])
    for customer_id in [101, 102, 103, 104, 105]:
        print(
            f"customer {customer_id} -> "
            f"{router.shard_for(customer_id)}"
        )

    print("\nRead replicas:")
    primary = DatabaseNode("primary", "ap-south", 1000)
    replicas = [
        DatabaseNode("replica-1", "ap-south", 800),
        DatabaseNode("replica-2", "ap-southeast", 800),
    ]
    cluster = ReadReplicaCluster(primary, replicas)
    metrics = simulate_workload(cluster)
    print(metrics.summary())

    print("\nValidation:")
    validate_edge_cases()
    print("All edge-case assertions passed.")

    print("\nProduction considerations:")
    print("- Vertical scaling increases capacity of one database node.")
    print("- Horizontal scaling adds independent database nodes.")
    print("- Partitioning divides one logical table into manageable physical parts.")
    print("- Sharding distributes ownership of data across independent databases.")
    print("- Read replicas increase read capacity but introduce replication lag.")
    print("- Connection pools, indexes, query plans, backups, and observability")
    print("  must be evaluated before changing the architecture.")


if __name__ == "__main__":
    main()
