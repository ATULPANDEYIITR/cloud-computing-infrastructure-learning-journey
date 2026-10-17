#!/usr/bin/env python3
"""
Object Storage Engineering Laboratory

A self-contained simulation of an object storage service covering:
- Buckets, object keys, immutable object identifiers, and payloads
- System and custom metadata
- Object versioning and version-specific retrieval
- Lifecycle transitions, expiration, and noncurrent-version cleanup
- Bucket access policies, principal permissions, and explicit denies
- Conditional writes, integrity verification, pagination, and audit events
- Policy evaluation, concurrency safeguards, and failure handling

Run with Python 3.10 or later:
    python object_storage_lab.py
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamps must include a timezone.")
    return value.astimezone(timezone.utc)


class StorageError(Exception):
    """Base exception for storage operations."""


class NotFound(StorageError):
    pass


class AccessDenied(StorageError):
    pass


class InvalidRequest(StorageError):
    pass


class PreconditionFailed(StorageError):
    pass


class VersioningState(str, Enum):
    ENABLED = "Enabled"
    SUSPENDED = "Suspended"
    DISABLED = "Disabled"


class StorageClass(str, Enum):
    STANDARD = "STANDARD"
    INFREQUENT_ACCESS = "INFREQUENT_ACCESS"
    ARCHIVE = "ARCHIVE"


class ObjectState(str, Enum):
    CURRENT = "CURRENT"
    NONCURRENT = "NONCURRENT"
    DELETE_MARKER = "DELETE_MARKER"


@dataclass(frozen=True)
class Principal:
    name: str
    roles: frozenset[str] = frozenset()
    authenticated: bool = True


@dataclass(frozen=True)
class PolicyStatement:
    effect: str
    actions: frozenset[str]
    resources: frozenset[str]
    principals: frozenset[str]
    conditions: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.effect not in {"Allow", "Deny"}:
            raise ValueError("Policy effect must be Allow or Deny.")
        if not self.actions or not self.resources or not self.principals:
            raise ValueError("Policy statements require actions, resources, and principals.")


@dataclass(frozen=True)
class ObjectMetadata:
    content_type: str
    content_length: int
    etag: str
    sha256: str
    last_modified: datetime
    user_metadata: dict[str, str]


@dataclass
class StoredVersion:
    version_id: str
    key: str
    body: bytes
    metadata: ObjectMetadata
    created_at: datetime
    storage_class: StorageClass = StorageClass.STANDARD
    noncurrent_since: datetime | None = None
    delete_marker: bool = False
    retention_until: datetime | None = None

    @property
    def size(self) -> int:
        return len(self.body)


@dataclass(frozen=True)
class ObjectSnapshot:
    bucket: str
    key: str
    version_id: str
    size: int
    etag: str
    sha256: str
    content_type: str
    storage_class: str
    delete_marker: bool


@dataclass
class LifecycleRule:
    rule_id: str
    prefix: str = ""
    transition_after_days: int | None = None
    target_storage_class: StorageClass = StorageClass.INFREQUENT_ACCESS
    expire_after_days: int | None = None
    noncurrent_expire_after_days: int | None = None
    abort_incomplete_upload_after_days: int | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        durations = (
            self.transition_after_days,
            self.expire_after_days,
            self.noncurrent_expire_after_days,
            self.abort_incomplete_upload_after_days,
        )
        if all(value is None for value in durations):
            raise ValueError("A lifecycle rule must define at least one action.")
        if any(value is not None and value < 0 for value in durations):
            raise ValueError("Lifecycle durations cannot be negative.")


@dataclass(frozen=True)
class AuditEvent:
    timestamp: datetime
    principal: str
    action: str
    bucket: str
    key: str | None
    outcome: str
    detail: str


class Bucket:
    def __init__(
        self,
        name: str,
        owner: Principal,
        versioning: VersioningState = VersioningState.DISABLED,
        default_encryption: str = "AES256",
    ) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", name):
            raise InvalidRequest(f"Invalid bucket name: {name!r}")
        if ".." in name or ".-" in name or "-." in name:
            raise InvalidRequest("Bucket name contains an invalid separator sequence.")
        if not default_encryption:
            raise InvalidRequest("Default encryption cannot be empty.")

        self.name = name
        self.owner = owner
        self.versioning = versioning
        self.default_encryption = default_encryption
        self.statements: list[PolicyStatement] = []
        self.lifecycle_rules: list[LifecycleRule] = []
        self.versions: dict[str, list[StoredVersion]] = {}
        self.incomplete_uploads: dict[str, datetime] = {}
        self.lock = threading.RLock()

    def validate_key(self, key: str) -> None:
        if not isinstance(key, str) or not key:
            raise InvalidRequest("Object key must be a nonempty string.")
        if key.startswith("/") or "\x00" in key:
            raise InvalidRequest("Object key must be relative and cannot contain NUL.")
        if len(key.encode("utf-8")) > 1024:
            raise InvalidRequest("Object key exceeds the 1024-byte UTF-8 limit.")
        if any(part == ".." for part in key.split("/")):
            raise InvalidRequest("Parent-directory segments are not accepted.")


class ObjectStorage:
    """
    Thread-safe, in-memory object storage simulator.

    The simulator deliberately separates logical object keys from version IDs.
    It is not a durable service and does not implement a cloud provider's
    complete policy language, replication protocol, or billing semantics.
    """

    VALID_ACTIONS = frozenset({
        "bucket:ListObjects",
        "bucket:GetPolicy",
        "bucket:PutPolicy",
        "object:Get",
        "object:Put",
        "object:Delete",
        "object:ListVersions",
        "object:GetVersion",
        "object:DeleteVersion",
        "object:Restore",
        "object:ManageLifecycle",
    })

    def __init__(self) -> None:
        self.buckets: dict[str, Bucket] = {}
        self.audit_log: list[AuditEvent] = []
        self._audit_lock = threading.Lock()

    def _audit(
        self,
        principal: Principal,
        action: str,
        bucket: str,
        key: str | None,
        outcome: str,
        detail: str,
    ) -> None:
        event = AuditEvent(utc_now(), principal.name, action, bucket, key, outcome, detail)
        with self._audit_lock:
            self.audit_log.append(event)

    def create_bucket(
        self,
        name: str,
        owner: Principal,
        versioning: VersioningState = VersioningState.DISABLED,
    ) -> Bucket:
        if name in self.buckets:
            raise InvalidRequest(f"Bucket already exists: {name}")
        bucket = Bucket(name, owner, versioning)
        self.buckets[name] = bucket
        self._audit(owner, "bucket:Create", name, None, "ALLOWED", "Bucket created.")
        return bucket

    def _bucket(self, name: str) -> Bucket:
        try:
            return self.buckets[name]
        except KeyError as exc:
            raise NotFound(f"Bucket not found: {name}") from exc

    @staticmethod
    def _matches(pattern: str, value: str) -> bool:
        # A trailing wildcard is treated as a prefix, not as a full glob engine.
        if pattern.endswith("*"):
            return value.startswith(pattern[:-1])
        return pattern == value

    def authorize(
        self,
        principal: Principal,
        bucket: Bucket,
        action: str,
        key: str | None = None,
        request_conditions: dict[str, str] | None = None,
    ) -> bool:
        if not principal.authenticated:
            return False

        if principal.name == bucket.owner.name:
            return True

        resource = f"arn:object:{bucket.name}/{key}" if key is not None else f"arn:object:{bucket.name}"

        applicable: list[PolicyStatement] = []
        for statement in bucket.statements:
            principal_matches = (
                "*" in statement.principals
                or principal.name in statement.principals
                or bool(principal.roles.intersection(statement.principals))
            )
            action_matches = any(
                self._matches(pattern, action) for pattern in statement.actions
            )
            resource_matches = any(
                self._matches(pattern, resource) for pattern in statement.resources
            )
            conditions_match = all(
                (request_conditions or {}).get(name) == expected
                for name, expected in statement.conditions.items()
            )
            if principal_matches and action_matches and resource_matches and conditions_match:
                applicable.append(statement)

        # Explicit deny wins. Every other request is denied unless an allow matches.
        if any(statement.effect == "Deny" for statement in applicable):
            return False
        return any(statement.effect == "Allow" for statement in applicable)

    def _require(
        self,
        principal: Principal,
        bucket: Bucket,
        action: str,
        key: str | None = None,
        request_conditions: dict[str, str] | None = None,
    ) -> None:
        if action not in self.VALID_ACTIONS and action not in {"bucket:Create"}:
            raise InvalidRequest(f"Unknown operation: {action}")
        if not self.authorize(principal, bucket, action, key, request_conditions):
            self._audit(principal, action, bucket.name, key, "DENIED", "Policy evaluation rejected request.")
            raise AccessDenied(f"{principal.name} cannot perform {action} on {bucket.name}/{key or ''}")

    def put_policy(
        self,
        principal: Principal,
        bucket_name: str,
        statements: Iterable[PolicyStatement],
    ) -> None:
        bucket = self._bucket(bucket_name)
        if principal.name != bucket.owner.name and not self.authorize(
            principal, bucket, "bucket:PutPolicy"
        ):
            raise AccessDenied("Only the bucket owner or an authorized policy manager can change policy.")

        proposed = list(statements)
        for statement in proposed:
            unknown = {
                action for action in statement.actions
                if action not in self.VALID_ACTIONS and action != "*"
            }
            if unknown:
                raise InvalidRequest(f"Policy contains unknown actions: {sorted(unknown)}")
        with bucket.lock:
            bucket.statements = proposed
        self._audit(principal, "bucket:PutPolicy", bucket.name, None, "ALLOWED", "Bucket policy replaced.")

    def put_object(
        self,
        principal: Principal,
        bucket_name: str,
        key: str,
        body: bytes,
        *,
        content_type: str | None = None,
        user_metadata: dict[str, str] | None = None,
        if_match: str | None = None,
        if_none_match: bool = False,
        retention_days: int = 0,
        request_conditions: dict[str, str] | None = None,
    ) -> StoredVersion:
        bucket = self._bucket(bucket_name)
        bucket.validate_key(key)
        if not isinstance(body, bytes):
            raise InvalidRequest("Object payload must be bytes.")
        if retention_days < 0:
            raise InvalidRequest("Retention days cannot be negative.")

        clean_metadata: dict[str, str] = {}
        for name, value in (user_metadata or {}).items():
            normalized_name = name.lower()
            if not re.fullmatch(r"[a-z0-9-]{1,64}", normalized_name):
                raise InvalidRequest(f"Invalid metadata name: {name!r}")
            if not isinstance(value, str) or len(value.encode("utf-8")) > 2048:
                raise InvalidRequest(f"Invalid metadata value for {name!r}")
            clean_metadata[normalized_name] = value

        self._require(principal, bucket, "object:Put", key, request_conditions)

        with bucket.lock:
            existing = self._visible_version(bucket, key)
            if if_none_match and existing is not None:
                raise PreconditionFailed("Object already exists.")
            if if_match is not None and (
                existing is None or existing.metadata.etag != if_match
            ):
                raise PreconditionFailed("ETag condition did not match the current object.")

            now = utc_now()
            digest = hashlib.sha256(body).hexdigest()
            # ETag is represented as a content digest in this simulator.
            # Multipart cloud uploads can use different ETag semantics.
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            detected_type = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
            metadata = ObjectMetadata(
                content_type=detected_type,
                content_length=len(body),
                etag=etag,
                sha256=digest,
                last_modified=now,
                user_metadata=clean_metadata,
            )

            history = bucket.versions.setdefault(key, [])
            if bucket.versioning == VersioningState.ENABLED:
                for old in history:
                    if not old.delete_marker and old.noncurrent_since is None:
                        old.noncurrent_since = now
                version_id = str(uuid4())
            elif bucket.versioning == VersioningState.SUSPENDED:
                # A null version is replaced while versioning is suspended.
                history[:] = [v for v in history if v.version_id != "null"]
                version_id = "null"
                for old in history:
                    if not old.delete_marker and old.noncurrent_since is None:
                        old.noncurrent_since = now
            else:
                history.clear()
                version_id = "null"

            version = StoredVersion(
                version_id=version_id,
                key=key,
                body=body,
                metadata=metadata,
                created_at=now,
                retention_until=now + timedelta(days=retention_days) if retention_days else None,
            )
            history.insert(0, version)

        self._audit(principal, "object:Put", bucket.name, key, "ALLOWED", f"Stored {len(body)} bytes.")
        return version

    @staticmethod
    def _visible_version(bucket: Bucket, key: str) -> StoredVersion | None:
        history = bucket.versions.get(key, [])
        if not history:
            return None
        latest = history[0]
        return None if latest.delete_marker else latest

    def get_object(
        self,
        principal: Principal,
        bucket_name: str,
        key: str,
        version_id: str | None = None,
    ) -> tuple[bytes, ObjectMetadata]:
        bucket = self._bucket(bucket_name)
        bucket.validate_key(key)
        action = "object:GetVersion" if version_id is not None else "object:Get"
        self._require(principal, bucket, action, key)

        with bucket.lock:
            history = bucket.versions.get(key, [])
            if version_id is None:
                version = self._visible_version(bucket, key)
                if version is None:
                    raise NotFound(f"No current object exists at key {key!r}.")
            else:
                version = next(
                    (item for item in history if item.version_id == version_id),
                    None,
                )
                if version is None:
                    raise NotFound(f"Version {version_id!r} was not found.")
                if version.delete_marker:
                    raise NotFound("The selected version is a delete marker.")

            if version.storage_class == StorageClass.ARCHIVE:
                raise InvalidRequest("Archived object must be restored before retrieval.")
            return version.body, version.metadata

    def delete_object(
        self,
        principal: Principal,
        bucket_name: str,
        key: str,
        version_id: str | None = None,
    ) -> None:
        bucket = self._bucket(bucket_name)
        bucket.validate_key(key)
        action = "object:DeleteVersion" if version_id is not None else "object:Delete"
        self._require(principal, bucket, action, key)

        with bucket.lock:
            history = bucket.versions.get(key, [])
            if version_id is not None:
                version = next((v for v in history if v.version_id == version_id), None)
                if version is None:
                    raise NotFound(f"Version {version_id!r} not found.")
                if version.retention_until and utc_now() < version.retention_until:
                    raise InvalidRequest("Retention period prevents deletion.")
                history.remove(version)
                if not history:
                    bucket.versions.pop(key, None)
            elif bucket.versioning == VersioningState.ENABLED:
                now = utc_now()
                for old in history:
                    if not old.delete_marker and old.noncurrent_since is None:
                        old.noncurrent_since = now
                history.insert(0, StoredVersion(
                    version_id=str(uuid4()),
                    key=key,
                    body=b"",
                    metadata=ObjectMetadata(
                        "application/x-delete-marker", 0, "", "",
                        now, {},
                    ),
                    created_at=now,
                    delete_marker=True,
                ))
            else:
                current = self._visible_version(bucket, key)
                if current is None:
                    raise NotFound(f"No current object exists at key {key!r}.")
                if current.retention_until and utc_now() < current.retention_until:
                    raise InvalidRequest("Retention period prevents deletion.")
                history.clear()
                bucket.versions.pop(key, None)

        self._audit(principal, action, bucket.name, key, "ALLOWED", "Delete operation completed.")

    def list_objects(
        self,
        principal: Principal,
        bucket_name: str,
        *,
        prefix: str = "",
        limit: int = 100,
        continuation_key: str | None = None,
    ) -> tuple[list[ObjectSnapshot], str | None]:
        bucket = self._bucket(bucket_name)
        self._require(principal, bucket, "bucket:ListObjects")
        if not 1 <= limit <= 1000:
            raise InvalidRequest("Page size must be between 1 and 1000.")

        with bucket.lock:
            snapshots = []
            for key in sorted(bucket.versions):
                if not key.startswith(prefix):
                    continue
                if continuation_key is not None and key <= continuation_key:
                    continue
                current = self._visible_version(bucket, key)
                if current is None:
                    continue
                snapshots.append(ObjectSnapshot(
                    bucket.name, key, current.version_id, current.size,
                    current.metadata.etag, current.metadata.sha256,
                    current.metadata.content_type, current.storage_class.value,
                    current.delete_marker,
                ))

            page = snapshots[:limit]
            next_key = page[-1].key if len(snapshots) > limit and page else None
            return page, next_key

    def list_versions(
        self,
        principal: Principal,
        bucket_name: str,
        key: str,
    ) -> list[ObjectSnapshot]:
        bucket = self._bucket(bucket_name)
        self._require(principal, bucket, "object:ListVersions", key)
        with bucket.lock:
            return [
                ObjectSnapshot(
                    bucket.name, key, version.version_id, version.size,
                    version.metadata.etag, version.metadata.sha256,
                    version.metadata.content_type, version.storage_class.value,
                    version.delete_marker,
                )
                for version in bucket.versions.get(key, [])
            ]

    def configure_lifecycle(
        self,
        principal: Principal,
        bucket_name: str,
        rules: Iterable[LifecycleRule],
    ) -> None:
        bucket = self._bucket(bucket_name)
        self._require(principal, bucket, "object:ManageLifecycle")
        rule_list = list(rules)
        if len({rule.rule_id for rule in rule_list}) != len(rule_list):
            raise InvalidRequest("Lifecycle rule identifiers must be unique.")
        with bucket.lock:
            bucket.lifecycle_rules = rule_list
        self._audit(principal, "object:ManageLifecycle", bucket.name, None, "ALLOWED", "Lifecycle rules replaced.")

    def apply_lifecycle(self, bucket_name: str, now: datetime | None = None) -> dict[str, int]:
        bucket = self._bucket(bucket_name)
        current_time = normalize_time(now or utc_now())
        counts = {"transitioned": 0, "expired": 0, "noncurrent_deleted": 0, "uploads_aborted": 0}

        with bucket.lock:
            for key, history in list(bucket.versions.items()):
                matching_rules = [
                    rule for rule in bucket.lifecycle_rules
                    if rule.enabled and key.startswith(rule.prefix)
                ]
                for version in list(history):
                    age_days = (current_time - version.created_at).total_seconds() / 86400
                    noncurrent_age = (
                        (current_time - version.noncurrent_since).total_seconds() / 86400
                        if version.noncurrent_since else None
                    )

                    if version.delete_marker:
                        continue

                    for rule in matching_rules:
                        if (
                            rule.transition_after_days is not None
                            and age_days >= rule.transition_after_days
                            and version.storage_class != rule.target_storage_class
                            and version.storage_class != StorageClass.ARCHIVE
                        ):
                            version.storage_class = rule.target_storage_class
                            counts["transitioned"] += 1

                        if (
                            rule.noncurrent_expire_after_days is not None
                            and noncurrent_age is not None
                            and noncurrent_age >= rule.noncurrent_expire_after_days
                        ):
                            if version.retention_until and current_time < version.retention_until:
                                continue
                            history.remove(version)
                            counts["noncurrent_deleted"] += 1
                            break

                        is_current = (
                            history
                            and history[0] is version
                            and version.noncurrent_since is None
                        )
                        if (
                            is_current
                            and rule.expire_after_days is not None
                            and age_days >= rule.expire_after_days
                        ):
                            if version.retention_until and current_time < version.retention_until:
                                continue
                            if bucket.versioning == VersioningState.ENABLED:
                                version.noncurrent_since = current_time
                                history.insert(0, StoredVersion(
                                    version_id=str(uuid4()),
                                    key=key,
                                    body=b"",
                                    metadata=ObjectMetadata(
                                        "application/x-delete-marker", 0, "", "",
                                        current_time, {},
                                    ),
                                    created_at=current_time,
                                    delete_marker=True,
                                ))
                            else:
                                history.remove(version)
                            counts["expired"] += 1
                            break

                if not history:
                    bucket.versions.pop(key, None)

            for upload_id, started_at in list(bucket.incomplete_uploads.items()):
                for rule in bucket.lifecycle_rules:
                    if (
                        rule.enabled
                        and rule.abort_incomplete_upload_after_days is not None
                        and (current_time - started_at).total_seconds() / 86400
                        >= rule.abort_incomplete_upload_after_days
                    ):
                        del bucket.incomplete_uploads[upload_id]
                        counts["uploads_aborted"] += 1
                        break

        return counts

    def restore_archived_object(
        self,
        principal: Principal,
        bucket_name: str,
        key: str,
        version_id: str,
    ) -> None:
        bucket = self._bucket(bucket_name)
        self._require(principal, bucket, "object:Restore", key)
        with bucket.lock:
            version = next(
                (v for v in bucket.versions.get(key, []) if v.version_id == version_id),
                None,
            )
            if version is None or version.delete_marker:
                raise NotFound("Restorable object version not found.")
            if version.storage_class != StorageClass.ARCHIVE:
                return
            # A production restore is asynchronous and may create a temporary copy.
            version.storage_class = StorageClass.INFREQUENT_ACCESS
        self._audit(principal, "object:Restore", bucket.name, key, "ALLOWED", "Archive restore simulated.")

    def verify_integrity(
        self,
        principal: Principal,
        bucket_name: str,
        key: str,
        version_id: str | None = None,
    ) -> bool:
        body, metadata = self.get_object(principal, bucket_name, key, version_id)
        return (
            len(body) == metadata.content_length
            and hashlib.sha256(body).hexdigest() == metadata.sha256
        )


def policy_statement(
    effect: str,
    actions: set[str],
    resources: set[str],
    principals: set[str],
    conditions: dict[str, str] | None = None,
) -> PolicyStatement:
    return PolicyStatement(
        effect,
        frozenset(actions),
        frozenset(resources),
        frozenset(principals),
        conditions or {},
    )


def run_demo() -> None:
    print("Object Storage Engineering Laboratory")
    storage = ObjectStorage()

    owner = Principal("platform-admin", frozenset({"storage-admin"}))
    engineer = Principal("application-engineer", frozenset({"engineer"}))
    auditor = Principal("security-auditor", frozenset({"auditor"}))
    anonymous = Principal("anonymous", authenticated=False)

    bucket = storage.create_bucket(
        "research-artifacts-prod",
        owner,
        VersioningState.ENABLED,
    )

    storage.put_policy(owner, bucket.name, [
        policy_statement(
            "Allow",
            {"object:Get", "object:GetVersion", "object:ListVersions"},
            {f"arn:object:{bucket.name}/reports/*"},
            {"auditor"},
        ),
        policy_statement(
            "Allow",
            {"object:Get", "object:Put", "object:Delete"},
            {f"arn:object:{bucket.name}/reports/*"},
            {"engineer"},
            {"transport": "tls"},
        ),
        policy_statement(
            "Deny",
            {"object:Delete", "object:DeleteVersion"},
            {f"arn:object:{bucket.name}/reports/regulated/*"},
            {"*"},
        ),
    ])

    storage.configure_lifecycle(owner, bucket.name, [
        LifecycleRule(
            rule_id="reports-archive",
            prefix="reports/archive/",
            transition_after_days=30,
            target_storage_class=StorageClass.ARCHIVE,
            noncurrent_expire_after_days=90,
        ),
        LifecycleRule(
            rule_id="temporary-export-cleanup",
            prefix="tmp/",
            expire_after_days=7,
            abort_incomplete_upload_after_days=2,
        ),
    ])

    first = storage.put_object(
        engineer,
        bucket.name,
        "reports/quarterly.json",
        json.dumps({
            "period": "2026-Q3",
            "records_processed": 185420,
            "validation_failures": 37,
        }, indent=2).encode("utf-8"),
        content_type="application/json",
        user_metadata={"department": "research", "classification": "internal"},
        request_conditions={"transport": "tls"},
    )

    second = storage.put_object(
        engineer,
        bucket.name,
        "reports/quarterly.json",
        b'{"period":"2026-Q3","records_processed":185420,"validation_failures":35}',
        content_type="application/json",
        user_metadata={"department": "research", "revision": "corrected"},
        if_match=first.metadata.etag,
        request_conditions={"transport": "tls"},
    )

    print("\nVersioned object write:")
    print(f"First version:  {first.version_id}")
    print(f"Second version: {second.version_id}")
    print(f"SHA-256:        {second.metadata.sha256}")

    body, metadata = storage.get_object(
        auditor,
        bucket.name,
        "reports/quarterly.json",
        first.version_id,
    )
    print(f"Historical payload retrieved: {len(body)} bytes")
    print(f"Historical integrity valid:   {storage.verify_integrity(auditor, bucket.name, 'reports/quarterly.json', first.version_id)}")
    print(f"Historical content type:       {metadata.content_type}")

    print("\nPaginated object listing:")
    page, continuation = storage.list_objects(
        owner, bucket.name, prefix="reports/", limit=1
    )
    for item in page:
        print(f"{item.key}: {item.size} bytes, version={item.version_id}")
    print(f"Continuation key: {continuation}")

    print("\nAuthorization and conditional-write checks:")
    try:
        storage.put_object(
            engineer, bucket.name, "reports/quarterly.json", b"stale update",
            if_match="stale-etag", request_conditions={"transport": "tls"},
        )
    except PreconditionFailed as exc:
        print(f"Stale write rejected: {exc}")

    try:
        storage.put_object(
            anonymous, bucket.name, "reports/public.json", b"public",
        )
    except AccessDenied as exc:
        print(f"Unauthenticated write rejected: {exc}")

    try:
        storage.delete_object(
            engineer, bucket.name, "reports/regulated/audit.csv",
            request_conditions={"transport": "tls"},
        )
    except (AccessDenied, NotFound) as exc:
        print(f"Restricted deletion rejected: {exc}")

    print("\nLifecycle simulation:")
    old_time = utc_now() - timedelta(days=45)
    archive = storage.put_object(
        owner,
        bucket.name,
        "reports/archive/2026-08.csv",
        b"account_id,total\nA104,15300\nB205,21700\n",
        content_type="text/csv",
    )
    # Backdate timestamps only inside this controlled simulation.
    archive.created_at = old_time
    archive.metadata = ObjectMetadata(
        archive.metadata.content_type,
        archive.metadata.content_length,
        archive.metadata.etag,
        archive.metadata.sha256,
        old_time,
        archive.metadata.user_metadata,
    )

    lifecycle_result = storage.apply_lifecycle(
        bucket.name,
        now=utc_now(),
    )
    print(f"Lifecycle results: {lifecycle_result}")

    try:
        storage.get_object(owner, bucket.name, "reports/archive/2026-08.csv")
    except InvalidRequest as exc:
        print(f"Archived read requires restoration: {exc}")

    storage.restore_archived_object(
        owner, bucket.name, "reports/archive/2026-08.csv", archive.version_id
    )
    restored, _ = storage.get_object(
        owner, bucket.name, "reports/archive/2026-08.csv"
    )
    print(f"Restored payload length: {len(restored)} bytes")

    print("\nVersion-aware deletion:")
    storage.delete_object(
        engineer, bucket.name, "reports/quarterly.json",
        request_conditions={"transport": "tls"},
    )
    try:
        storage.get_object(owner, bucket.name, "reports/quarterly.json")
    except NotFound:
        print("Current key is hidden by a delete marker.")
    historical_body, _ = storage.get_object(
        owner, bucket.name, "reports/quarterly.json", second.version_id
    )
    print(f"Previous version remains retrievable: {len(historical_body)} bytes")

    print("\nAudit log:")
    for event in storage.audit_log:
        print(
            f"{event.timestamp.isoformat()} | {event.principal} | "
            f"{event.action} | {event.outcome} | {event.detail}"
        )


if __name__ == "__main__":
    run_demo()
