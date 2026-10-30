#!/usr/bin/env python3
"""
Database High Availability: multi-zone replication and controlled failover.

This executable model simulates an active-passive database cluster. It checks
replica health, replication lag, voting-member quorum, observation freshness,
and primary fencing before promoting a replica.

The model does not perform real database replication or remote infrastructure
operations. Fencing is represented by an explicit confirmation recorded on
the failed primary.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("database-ha")


class NodeRole(str, Enum):
    PRIMARY = "primary"
    REPLICA = "replica"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


class ReplicationMode(str, Enum):
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"


@dataclass
class DatabaseNode:
    node_id: str
    zone: str
    role: NodeRole
    voting_member: bool
    replication_mode: ReplicationMode
    replication_lag_ms: int
    health: HealthStatus
    observed_at: datetime
    fenced: bool = False
    fencing_token: int = 0

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("Node ID cannot be empty")
        if not self.zone.strip():
            raise ValueError("Availability zone cannot be empty")
        if self.replication_lag_ms < 0:
            raise ValueError("Replication lag cannot be negative")
        if self.observed_at.tzinfo is None:
            raise ValueError("Health observation must be timezone-aware")


@dataclass(frozen=True)
class FailoverPolicy:
    quorum_required: int
    max_replication_lag_ms: int
    require_synchronous_replica: bool
    max_observation_age_seconds: int
    minimum_availability_zones: int = 2

    def __post_init__(self) -> None:
        if self.quorum_required < 1:
            raise ValueError("Quorum must be at least one")
        if self.max_replication_lag_ms < 0:
            raise ValueError("Maximum replication lag cannot be negative")
        if self.max_observation_age_seconds <= 0:
            raise ValueError("Observation freshness limit must be positive")
        if self.minimum_availability_zones < 2:
            raise ValueError("A multi-zone policy requires at least two zones")


@dataclass(frozen=True)
class FailoverDecision:
    eligible: bool
    reasons: tuple[str, ...]
    healthy_voters: int
    candidate_id: str
    candidate_lag_ms: int | None


@dataclass(frozen=True)
class FailoverEvent:
    timestamp: str
    old_primary_id: str
    new_primary_id: str
    previous_epoch: int
    new_epoch: int
    fencing_token: int
    healthy_voters: int


@dataclass
class DatabaseCluster:
    cluster_id: str
    nodes: dict[str, DatabaseNode]
    current_primary_id: str
    policy: FailoverPolicy
    epoch: int = 1
    fencing_token: int = 1
    events: list[FailoverEvent] = field(default_factory=list)
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not self.cluster_id.strip():
            raise ValueError("Cluster ID cannot be empty")
        if not self.nodes:
            raise ValueError("A cluster must contain database nodes")
        if len(self.nodes) != len(set(self.nodes)):
            raise ValueError("Node identifiers must be unique")
        if self.current_primary_id not in self.nodes:
            raise ValueError("Current primary is not a cluster member")

        voters = sum(node.voting_member for node in self.nodes.values())
        zones = {node.zone for node in self.nodes.values()}

        if self.policy.quorum_required > voters:
            raise ValueError("Required quorum exceeds the voting membership")
        if len(zones) < self.policy.minimum_availability_zones:
            raise ValueError("Cluster does not meet its multi-zone requirement")
        if self.nodes[self.current_primary_id].role is not NodeRole.PRIMARY:
            raise ValueError("Current primary must have the primary role")

        primary_count = sum(
            node.role is NodeRole.PRIMARY for node in self.nodes.values()
        )
        if primary_count != 1:
            raise ValueError("A cluster must have exactly one primary")


def is_observation_fresh(
    node: DatabaseNode,
    now: datetime,
    maximum_age_seconds: int,
) -> bool:
    age = (now - node.observed_at).total_seconds()
    return 0 <= age <= maximum_age_seconds


def evaluate_failover(
    cluster: DatabaseCluster,
    candidate_id: str,
    now: datetime | None = None,
) -> FailoverDecision:
    """Evaluate safety and eligibility without changing cluster state."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Evaluation time must be timezone-aware")

    reasons: list[str] = []
    candidate = cluster.nodes.get(candidate_id)

    if candidate is None:
        return FailoverDecision(
            False, ("candidate_not_found",), 0, candidate_id, None
        )

    primary = cluster.nodes.get(cluster.current_primary_id)
    if primary is None:
        return FailoverDecision(
            False, ("current_primary_not_found",), 0, candidate_id,
            candidate.replication_lag_ms,
        )

    if candidate_id == cluster.current_primary_id:
        reasons.append("candidate_is_already_primary")
    if candidate.role is not NodeRole.REPLICA:
        reasons.append("candidate_is_not_a_replica")
    if candidate.health is not HealthStatus.HEALTHY:
        reasons.append("candidate_is_not_healthy")
    if not is_observation_fresh(
        candidate,
        now,
        cluster.policy.max_observation_age_seconds,
    ):
        reasons.append("candidate_health_observation_is_stale")

    if cluster.policy.require_synchronous_replica:
        if candidate.replication_mode is not ReplicationMode.SYNCHRONOUS:
            reasons.append("candidate_is_not_synchronous")

    if candidate.replication_lag_ms > cluster.policy.max_replication_lag_ms:
        reasons.append("candidate_replication_lag_exceeds_policy")

    primary_is_fresh = is_observation_fresh(
        primary,
        now,
        cluster.policy.max_observation_age_seconds,
    )
    if (
        primary.health is HealthStatus.HEALTHY
        and primary_is_fresh
    ):
        reasons.append("current_primary_is_still_healthy")

    # A failed health probe alone is not sufficient protection from
    # split brain. The old primary must also have been fenced.
    if not primary.fenced:
        reasons.append("current_primary_has_not_been_fenced")

    healthy_voters = sum(
        1
        for node in cluster.nodes.values()
        if node.voting_member
        and node.health is HealthStatus.HEALTHY
        and is_observation_fresh(
            node,
            now,
            cluster.policy.max_observation_age_seconds,
        )
    )

    if healthy_voters < cluster.policy.quorum_required:
        reasons.append("healthy_voter_quorum_not_reached")

    return FailoverDecision(
        eligible=not reasons,
        reasons=tuple(reasons),
        healthy_voters=healthy_voters,
        candidate_id=candidate_id,
        candidate_lag_ms=candidate.replication_lag_ms,
    )


def promote_replica(
    cluster: DatabaseCluster,
    candidate_id: str,
    expected_epoch: int,
    now: datetime | None = None,
) -> FailoverEvent:
    """
    Promote a validated replica atomically within the in-memory model.

    The expected epoch provides optimistic concurrency protection. The lock
    serializes competing promotion requests within this process.
    """
    now = now or datetime.now(timezone.utc)

    with cluster._lock:
        if expected_epoch != cluster.epoch:
            raise RuntimeError(
                f"Stale cluster epoch: expected {expected_epoch}, "
                f"current epoch is {cluster.epoch}"
            )

        decision = evaluate_failover(cluster, candidate_id, now)
        if not decision.eligible:
            raise RuntimeError(
                "Failover rejected: " + ", ".join(decision.reasons)
            )

        old_primary = cluster.nodes[cluster.current_primary_id]
        new_primary = cluster.nodes[candidate_id]

        previous_epoch = cluster.epoch
        next_epoch = previous_epoch + 1
        next_fencing_token = cluster.fencing_token + 1

        # Demote first so the model never exposes two primary nodes.
        old_primary.role = NodeRole.REPLICA
        new_primary.role = NodeRole.PRIMARY
        new_primary.fenced = False
        new_primary.fencing_token = next_fencing_token

        cluster.current_primary_id = candidate_id
        cluster.epoch = next_epoch
        cluster.fencing_token = next_fencing_token

        event = FailoverEvent(
            timestamp=now.isoformat(),
            old_primary_id=old_primary.node_id,
            new_primary_id=new_primary.node_id,
            previous_epoch=previous_epoch,
            new_epoch=next_epoch,
            fencing_token=next_fencing_token,
            healthy_voters=decision.healthy_voters,
        )
        cluster.events.append(event)

        LOGGER.info(
            "Cluster %s promoted %s; epoch=%d fencing_token=%d",
            cluster.cluster_id,
            candidate_id,
            next_epoch,
            next_fencing_token,
        )
        return event


def build_example_cluster(now: datetime) -> DatabaseCluster:
    """Build a three-zone cluster with one failed primary and two replicas."""
    nodes = {
        "db-az1-primary": DatabaseNode(
            node_id="db-az1-primary",
            zone="availability-zone-a",
            role=NodeRole.PRIMARY,
            voting_member=True,
            replication_mode=ReplicationMode.SYNCHRONOUS,
            replication_lag_ms=0,
            health=HealthStatus.UNREACHABLE,
            observed_at=now,
            fenced=True,
            fencing_token=1,
        ),
        "db-az2-replica": DatabaseNode(
            node_id="db-az2-replica",
            zone="availability-zone-b",
            role=NodeRole.REPLICA,
            voting_member=True,
            replication_mode=ReplicationMode.SYNCHRONOUS,
            replication_lag_ms=15,
            health=HealthStatus.HEALTHY,
            observed_at=now,
        ),
        "db-az3-replica": DatabaseNode(
            node_id="db-az3-replica",
            zone="availability-zone-c",
            role=NodeRole.REPLICA,
            voting_member=True,
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_ms=160,
            health=HealthStatus.HEALTHY,
            observed_at=now,
        ),
    }

    policy = FailoverPolicy(
        quorum_required=2,
        max_replication_lag_ms=100,
        require_synchronous_replica=True,
        max_observation_age_seconds=30,
        minimum_availability_zones=3,
    )

    return DatabaseCluster(
        cluster_id="orders-production",
        nodes=nodes,
        current_primary_id="db-az1-primary",
        policy=policy,
        epoch=7,
        fencing_token=14,
    )


def decision_to_dict(decision: FailoverDecision) -> dict[str, Any]:
    return asdict(decision)


def main() -> None:
    now = datetime.now(timezone.utc)
    cluster = build_example_cluster(now)

    print("DATABASE HIGH AVAILABILITY: FAILOVER SIMULATION")
    print(f"Cluster: {cluster.cluster_id}")
    print(f"Initial primary: {cluster.current_primary_id}")
    print(f"Cluster epoch: {cluster.epoch}")

    delayed_candidate = evaluate_failover(
        cluster, "db-az3-replica", now
    )
    print("\nDelayed asynchronous replica:")
    print(json.dumps(decision_to_dict(delayed_candidate), indent=2))

    assert not delayed_candidate.eligible
    assert "candidate_is_not_synchronous" in delayed_candidate.reasons
    assert "candidate_replication_lag_exceeds_policy" in (
        delayed_candidate.reasons
    )

    eligible_candidate = evaluate_failover(
        cluster, "db-az2-replica", now
    )
    print("\nSynchronous replica:")
    print(json.dumps(decision_to_dict(eligible_candidate), indent=2))

    assert eligible_candidate.eligible
    assert eligible_candidate.healthy_voters == 2

    event = promote_replica(
        cluster,
        candidate_id="db-az2-replica",
        expected_epoch=cluster.epoch,
        now=now,
    )

    assert cluster.current_primary_id == "db-az2-replica"
    assert cluster.nodes["db-az1-primary"].role is NodeRole.REPLICA
    assert cluster.nodes["db-az2-replica"].role is NodeRole.PRIMARY
    assert len(cluster.events) == 1

    print("\nPromotion event:")
    print(json.dumps(asdict(event), indent=2))

    print("\nFinal cluster state:")
    print(
        json.dumps(
            {
                "cluster_id": cluster.cluster_id,
                "current_primary_id": cluster.current_primary_id,
                "epoch": cluster.epoch,
                "fencing_token": cluster.fencing_token,
                "nodes": [
                    {
                        "node_id": node.node_id,
                        "zone": node.zone,
                        "role": node.role.value,
                        "health": node.health.value,
                        "replication_mode": node.replication_mode.value,
                        "replication_lag_ms": node.replication_lag_ms,
                        "fenced": node.fenced,
                        "fencing_token": node.fencing_token,
                    }
                    for node in cluster.nodes.values()
                ],
            },
            indent=2,
        )
    )

    # A stale epoch must never authorize a second promotion.
    try:
        promote_replica(
            cluster,
            candidate_id="db-az3-replica",
            expected_epoch=7,
            now=now,
        )
    except RuntimeError as exc:
        print(f"\nExpected concurrency protection: {exc}")


if __name__ == "__main__":
    main()
