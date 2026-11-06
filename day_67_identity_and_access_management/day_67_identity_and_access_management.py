#!/usr/bin/env python3
"""
Identity and Access Management (IAM)
Users, groups, roles, policies, permissions, and least privilege.

A self-contained IAM simulation with:
- User and group management
- Role-based access control (RBAC)
- Permission and policy evaluation
- Explicit deny precedence
- Resource-level access decisions
- Temporary role assignments
- Least-privilege auditing
- Access revocation
- JSON persistence
- Unit-style assertions
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("iam")


class IAMError(Exception):
    """Base exception for IAM operations."""


class ValidationError(IAMError):
    """Raised when an IAM object is invalid."""


class NotFoundError(IAMError):
    """Raised when an IAM object does not exist."""


class AccessDeniedError(IAMError):
    """Raised when an access operation is denied."""


class Effect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True, order=True)
class Permission:
    resource: str
    action: str

    def __post_init__(self):
        if not self.resource or not self.action:
            raise ValidationError("Permission fields cannot be empty.")

        if self.resource != "*" and not all(
            part and part != ".."
            for part in self.resource.split("/")
        ):
            raise ValidationError("Invalid resource pattern.")

        if self.action != "*" and not self.action.replace("_", "").isalnum():
            raise ValidationError("Invalid action.")

    def matches(self, resource: str, action: str) -> bool:
        resource_match = (
            self.resource == "*"
            or self.resource == resource
            or (
                self.resource.endswith("/*")
                and resource.startswith(self.resource[:-1])
            )
        )

        action_match = self.action in ("*", action)

        return resource_match and action_match


@dataclass
class User:
    user_id: str
    email: str
    active: bool = True
    group_ids: set[str] = field(default_factory=set)

    def __post_init__(self):
        if not self.user_id.strip():
            raise ValidationError("User ID is required.")

        if "@" not in self.email:
            raise ValidationError("Invalid email address.")


@dataclass
class Group:
    group_id: str
    name: str
    role_ids: set[str] = field(default_factory=set)


@dataclass
class Role:
    role_id: str
    name: str
    permissions: set[Permission] = field(default_factory=set)


@dataclass
class Policy:
    policy_id: str
    name: str
    effect: Effect
    permission: Permission
    user_ids: set[str] = field(default_factory=set)
    group_ids: set[str] = field(default_factory=set)
    active: bool = True
    expires_at: Optional[datetime] = None

    def is_active(self, now: datetime) -> bool:
        if not self.active:
            return False

        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise ValidationError("Policy expiration must be timezone-aware.")

            return now < self.expires_at

        return True


@dataclass
class RoleAssignment:
    user_id: str
    role_id: str
    expires_at: Optional[datetime] = None

    def is_active(self, now: datetime) -> bool:
        if self.expires_at is None:
            return True

        if self.expires_at.tzinfo is None:
            raise ValidationError("Assignment expiration must be timezone-aware.")

        return now < self.expires_at


@dataclass(frozen=True)
class AccessResult:
    decision: Decision
    reason: str
    matched_roles: tuple[str, ...] = ()
    matched_policies: tuple[str, ...] = ()


class IAM:
    def __init__(self):
        self.users: dict[str, User] = {}
        self.groups: dict[str, Group] = {}
        self.roles: dict[str, Role] = {}
        self.policies: dict[str, Policy] = {}
        self.assignments: list[RoleAssignment] = {}

    def add_user(self, user: User) -> None:
        if user.user_id in self.users:
            raise ValidationError("Duplicate user ID.")

        self.users[user.user_id] = user

    def add_group(self, group: Group) -> None:
        if group.group_id in self.groups:
            raise ValidationError("Duplicate group ID.")

        self.groups[group.group_id] = group

    def add_role(self, role: Role) -> None:
        if role.role_id in self.roles:
            raise ValidationError("Duplicate role ID.")

        self.roles[role.role_id] = role

    def add_policy(self, policy: Policy) -> None:
        if policy.policy_id in self.policies:
            raise ValidationError("Duplicate policy ID.")

        unknown_users = policy.user_ids - self.users.keys()
        unknown_groups = policy.group_ids - self.groups.keys()

        if unknown_users or unknown_groups:
            raise ValidationError("Policy references unknown principals.")

        self.policies[policy.policy_id] = policy

    def add_user_to_group(self, user_id: str, group_id: str) -> None:
        user = self._user(user_id)
        self._group(group_id)
        user.group_ids.add(group_id)

    def assign_role_to_group(
        self,
        group_id: str,
        role_id: str
    ) -> None:
        group = self._group(group_id)
        self._role(role_id)
        group.role_ids.add(role_id)

    def assign_role(
        self,
        user_id: str,
        role_id: str,
        expires_at: Optional[datetime] = None
    ) -> None:
        self._user(user_id)
        self._role(role_id)

        if expires_at is not None:
            if expires_at.tzinfo is None:
                raise ValidationError("Expiration must be timezone-aware.")

        if any(
            a.user_id == user_id and a.role_id == role_id
            and a.expires_at == expires_at
            for a in self.assignments
        ):
            raise ValidationError("Duplicate role assignment.")

        self.assignments.append(
            RoleAssignment(user_id, role_id, expires_at)
        )

    def revoke_role(self, user_id: str, role_id: str) -> None:
        self._user(user_id)
        self._role(role_id)

        self.assignments = [
            a for a in self.assignments
            if not (a.user_id == user_id and a.role_id == role_id)
        ]

    def deactivate_user(self, user_id: str) -> None:
        self._user(user_id).active = False

    def _user(self, user_id: str) -> User:
        if user_id not in self.users:
            raise NotFoundError(f"Unknown user: {user_id}")

        return self.users[user_id]

    def _group(self, group_id: str) -> Group:
        if group_id not in self.groups:
            raise NotFoundError(f"Unknown group: {group_id}")

        return self.groups[group_id]

    def _role(self, role_id: str) -> Role:
        if role_id not in self.roles:
            raise NotFoundError(f"Unknown role: {role_id}")

        return self.roles[role_id]

    def effective_roles(
        self,
        user_id: str,
        now: Optional[datetime] = None
    ) -> set[str]:
        now = now or datetime.now(timezone.utc)
        user = self._user(user_id)

        if not user.active:
            return set()

        roles = set()

        for group_id in user.group_ids:
            roles.update(self._group(group_id).role_ids)

        for assignment in self.assignments:
            if assignment.user_id == user_id and assignment.is_active(now):
                roles.add(assignment.role_id)

        return roles

    def evaluate(
        self,
        user_id: str,
        resource: str,
        action: str,
        now: Optional[datetime] = None
    ) -> AccessResult:
        now = now or datetime.now(timezone.utc)

        if now.tzinfo is None:
            raise ValidationError("Evaluation time must be timezone-aware.")

        user = self._user(user_id)

        if not resource or not action:
            raise ValidationError("Resource and action are required.")

        if not user.active:
            return AccessResult(Decision.DENY, "User is inactive.")

        roles = self.effective_roles(user_id, now)
        groups = user.group_ids

        matched_roles = []
        role_allowed = False

        for role_id in roles:
            role = self._role(role_id)

            if any(
                permission.matches(resource, action)
                for permission in role.permissions
            ):
                matched_roles.append(role.name)
                role_allowed = True

        matched_policies = []
        explicit_allow = False
        explicit_deny = False

        for policy in self.policies.values():
            if not policy.is_active(now):
                continue

            principal_match = (
                user_id in policy.user_ids
                or bool(groups.intersection(policy.group_ids))
            )

            if not principal_match:
                continue

            if policy.permission.matches(resource, action):
                matched_policies.append(policy.policy_id)

                if policy.effect == Effect.DENY:
                    explicit_deny = True
                else:
                    explicit_allow = True

        # Explicit deny overrides every allow source.
        if explicit_deny:
            return AccessResult(
                Decision.DENY,
                "Explicit deny policy takes precedence.",
                tuple(matched_roles),
                tuple(matched_policies)
            )

        # Role permissions and explicit allow policies are independent
        # authorization grants.
        if role_allowed or explicit_allow:
            return AccessResult(
                Decision.ALLOW,
                "Permission granted.",
                tuple(matched_roles),
                tuple(matched_policies)
            )

        return AccessResult(
            Decision.DENY,
            "No matching permission.",
            tuple(matched_roles),
            tuple(matched_policies)
        )

    def require_access(
        self,
        user_id: str,
        resource: str,
        action: str
    ) -> None:
        result = self.evaluate(user_id, resource, action)

        if result.decision == Decision.DENY:
            raise AccessDeniedError(result.reason)

    def audit_user(
        self,
        user_id: str,
        resources: list[Permission]
    ) -> list[dict]:
        """Evaluate requested permissions for least-privilege auditing."""
        report = []

        for permission in resources:
            result = self.evaluate(
                user_id,
                permission.resource,
                permission.action
            )

            report.append({
                "resource": permission.resource,
                "action": permission.action,
                "decision": result.decision.value,
                "reason": result.reason
            })

        return report

    def save(self, filename: str) -> None:
        """Persist IAM configuration as JSON."""
        data = {
            "users": [
                {
                    "user_id": u.user_id,
                    "email": u.email,
                    "active": u.active,
                    "group_ids": sorted(u.group_ids)
                }
                for u in self.users.values()
            ],
            "groups": [
                {
                    "group_id": g.group_id,
                    "name": g.name,
                    "role_ids": sorted(g.role_ids)
                }
                for g in self.groups.values()
            ],
            "roles": [
                {
                    "role_id": r.role_id,
                    "name": r.name,
                    "permissions": [
                        asdict(p) for p in sorted(r.permissions)
                    ]
                }
                for r in self.roles.values()
            ],
            "policies": [
                {
                    "policy_id": p.policy_id,
                    "name": p.name,
                    "effect": p.effect.value,
                    "permission": asdict(p.permission),
                    "user_ids": sorted(p.user_ids),
                    "group_ids": sorted(p.group_ids),
                    "active": p.active,
                    "expires_at": (
                        p.expires_at.isoformat()
                        if p.expires_at else None
                    )
                }
                for p in self.policies.values()
            ],
            "assignments": [
                {
                    "user_id": a.user_id,
                    "role_id": a.role_id,
                    "expires_at": (
                        a.expires_at.isoformat()
                        if a.expires_at else None
                    )
                }
                for a in self.assignments
            ]
        }

        path = Path(filename)
        path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )

    @classmethod
    def load(cls, filename: str) -> "IAM":
        """Load and validate persisted IAM configuration."""
        data = json.loads(Path(filename).read_text(encoding="utf-8"))
        iam = cls()

        for item in data["users"]:
            iam.add_user(User(
                item["user_id"],
                item["email"],
                item["active"],
                set(item["group_ids"])
            ))

        for item in data["groups"]:
            iam.add_group(Group(
                item["group_id"],
                item["name"],
                set(item["role_ids"])
            ))

        for item in data["roles"]:
            permissions = {
                Permission(**p) for p in item["permissions"]
            }

            iam.add_role(Role(
                item["role_id"],
                item["name"],
                permissions
            ))

        for item in data["policies"]:
            expires_at = (
                datetime.fromisoformat(item["expires_at"])
                if item["expires_at"] else None
            )

            iam.add_policy(Policy(
                item["policy_id"],
                item["name"],
                Effect(item["effect"]),
                Permission(**item["permission"]),
                set(item["user_ids"]),
                set(item["group_ids"]),
                item["active"],
                expires_at
            ))

        for item in data["assignments"]:
            expires_at = (
                datetime.fromisoformat(item["expires_at"])
                if item["expires_at"] else None
            )

            iam.assign_role(
                item["user_id"],
                item["role_id"],
                expires_at
            )

        # Validate references created through persisted group membership.
        for user in iam.users.values():
            for group_id in user.group_ids:
                iam._group(group_id)

        for group in iam.groups.values():
            for role_id in group.role_ids:
                iam._role(role_id)

        return iam


def build_example() -> IAM:
    iam = IAM()

    iam.add_user(User("U001", "alice@example.com"))
    iam.add_user(User("U002", "bob@example.com"))
    iam.add_user(User("U003", "carol@example.com"))

    iam.add_group(Group("G001", "Engineering"))
    iam.add_group(Group("G002", "Security"))

    iam.add_role(Role(
        "R001",
        "Developer",
        {
            Permission("applications/project-a", "read"),
            Permission("applications/project-a", "write")
        }
    ))

    iam.add_role(Role(
        "R002",
        "SecurityAuditor",
        {
            Permission("security/logs", "read"),
            Permission("security/reports", "read")
        }
    ))

    iam.add_role(Role(
        "R003",
        "Administrator",
        {
            Permission("*", "*")
        }
    ))

    iam.add_user_to_group("U001", "G001")
    iam.add_user_to_group("U003", "G002")

    iam.assign_role_to_group("G001", "R001")
    iam.assign_role_to_group("G002", "R002")

    # Temporary elevated access for an incident investigation.
    iam.assign_role(
        "U002",
        "R003",
        datetime.now(timezone.utc) + timedelta(hours=1)
    )

    # Explicit deny prevents developers from accessing production secrets.
    iam.add_policy(Policy(
        "P001",
        "Protect production secrets",
        Effect.DENY,
        Permission("production/secrets", "*"),
        group_ids={"G001"}
    ))

    # Explicit allow provides a narrow, user-specific permission.
    iam.add_policy(Policy(
        "P002",
        "Read deployment reports",
        Effect.ALLOW,
        Permission("deployment/reports", "read"),
        user_ids={"U001"}
    ))

    return iam


def run_tests(iam: IAM) -> None:
    assert iam.evaluate(
        "U001", "applications/project-a", "read"
    ).decision == Decision.ALLOW

    assert iam.evaluate(
        "U001", "applications/project-a", "write"
    ).decision == Decision.ALLOW

    assert iam.evaluate(
        "U001", "production/secrets", "read"
    ).decision == Decision.DENY

    assert iam.evaluate(
        "U001", "deployment/reports", "read"
    ).decision == Decision.ALLOW

    assert iam.evaluate(
        "U001", "deployment/reports", "delete"
    ).decision == Decision.DENY

    assert iam.evaluate(
        "U003", "security/logs", "read"
    ).decision == Decision.ALLOW

    assert iam.evaluate(
        "U003", "applications/project-a", "write"
    ).decision == Decision.DENY

    iam.deactivate_user("U003")

    assert iam.evaluate(
        "U003", "security/logs", "read"
    ).decision == Decision.DENY

    try:
        iam.require_access("U001", "production/secrets", "read")
        raise AssertionError("Expected access denial.")
    except AccessDeniedError:
        pass

    try:
        iam.add_user(User("U001", "duplicate@example.com"))
        raise AssertionError("Expected duplicate user rejection.")
    except ValidationError:
        pass

    try:
        iam._user("UNKNOWN")
        raise AssertionError("Expected unknown user rejection.")
    except NotFoundError:
        pass

    print("All IAM tests passed.")


def main() -> None:
    iam = build_example()

    print("\nIDENTITY AND ACCESS MANAGEMENT")
    print("=" * 55)

    requests = [
        ("U001", "applications/project-a", "read"),
        ("U001", "production/secrets", "read"),
        ("U001", "deployment/reports", "read"),
        ("U002", "production/secrets", "delete"),
        ("U003", "security/logs", "read"),
        ("U001", "applications/project-a", "delete")
    ]

    for user_id, resource, action in requests:
        result = iam.evaluate(user_id, resource, action)

        print(
            f"{user_id:5} | {resource:30} | "
            f"{action:8} | {result.decision.value:5} | "
            f"{result.reason}"
        )

    print("\nLEAST-PRIVILEGE AUDIT")
    print("-" * 55)

    audit = iam.audit_user("U001", [
        Permission("applications/project-a", "read"),
        Permission("applications/project-a", "delete"),
        Permission("production/secrets", "read"),
        Permission("deployment/reports", "read")
    ])

    for entry in audit:
        print(json.dumps(entry))

    print("\nPERSISTENCE TEST")
    filename = "iam_configuration.json"

    try:
        iam.save(filename)
        restored = IAM.load(filename)

        assert restored.evaluate(
            "U001",
            "production/secrets",
            "read"
        ).decision == Decision.DENY

        Path(filename).unlink(missing_ok=True)
        print("Configuration persistence verified.")

    except (OSError, ValueError, KeyError, IAMError) as error:
        logger.error("Persistence operation failed: %s", error)
        raise

    print("\nTESTING")
    run_tests(iam)


if __name__ == "__main__":
    main()
