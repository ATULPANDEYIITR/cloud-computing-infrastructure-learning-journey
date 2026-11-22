#!/usr/bin/env python3
"""
Container Registry Management and Image Distribution

Models container repositories, image manifests, content digests, tags,
versioning, private registry authentication, access policies, image
distribution, and lifecycle management.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RegistryError(Exception):
    """Base exception for registry operations."""


class AuthenticationError(RegistryError):
    pass


class AuthorizationError(RegistryError):
    pass


class ValidationError(RegistryError):
    pass


class ImageNotFoundError(RegistryError):
    pass


class ConflictError(RegistryError):
    pass


class AccessRole(Enum):
    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"


class ImageState(Enum):
    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class Operation(Enum):
    PUSH = "push"
    PULL = "pull"
    DELETE = "delete"
    ADMIN = "admin"


@dataclass(frozen=True)
class ImageManifest:
    media_type: str
    layers: tuple[str, ...]
    config_digest: str
    architecture: str
    operating_system: str
    created_at: float

    def canonical_content(self) -> str:
        return json.dumps({
            "media_type": self.media_type,
            "layers": self.layers,
            "config_digest": self.config_digest,
            "architecture": self.architecture,
            "operating_system": self.operating_system,
        }, sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        content = self.canonical_content().encode("utf-8")
        return "sha256:" + hashlib.sha256(content).hexdigest()


@dataclass
class ImageArtifact:
    manifest: ImageManifest
    state: ImageState = ImageState.AVAILABLE
    pushed_at: float = field(default_factory=time.time)
    pull_count: int = 0

    @property
    def digest(self) -> str:
        return self.manifest.digest


@dataclass
class Repository:
    name: str
    private: bool = True
    tags: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, ImageArtifact] = field(default_factory=dict)
    immutable_tags: bool = False


@dataclass
class RegistryUser:
    username: str
    token_hash: str
    roles: dict[str, AccessRole] = field(default_factory=dict)
    active: bool = True


@dataclass(frozen=True)
class AuditEvent:
    timestamp: float
    username: str
    operation: str
    repository: str
    reference: str
    outcome: str


class ContainerRegistry:
    """
    In-memory registry with digest-addressed artifacts and mutable or
    immutable tags.

    Image manifests are content-addressed. Tags are references to
    manifests and may change independently of artifact identity.
    """

    REPOSITORY_PATTERN = re.compile(
        r"^[a-z0-9]+(?:[._/-][a-z0-9]+)*$"
    )
    TAG_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
    DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")

    def __init__(self, name: str):
        if not name.strip():
            raise ValidationError("Registry name cannot be empty.")

        self.name = name
        self.repositories: dict[str, Repository] = {}
        self.users: dict[str, RegistryUser] = {}
        self.audit_log: list[AuditEvent] = []

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def add_user(self, username: str, token: str) -> None:
        if not username or not token or len(token) < 12:
            raise ValidationError(
                "Username is required and token must contain at least 12 characters."
            )

        if username in self.users:
            raise ConflictError("User already exists.")

        self.users[username] = RegistryUser(
            username=username,
            token_hash=self._hash_token(token)
        )

    def authenticate(self, username: str, token: str) -> RegistryUser:
        user = self.users.get(username)

        if user is None or not user.active:
            raise AuthenticationError("Invalid or inactive account.")

        if user.token_hash != self._hash_token(token):
            raise AuthenticationError("Invalid credentials.")

        return user

    def grant_access(
        self,
        admin_username: str,
        admin_token: str,
        username: str,
        repository: str,
        role: AccessRole,
    ) -> None:
        admin = self.authenticate(admin_username, admin_token)

        if not any(
            assigned_role == AccessRole.ADMIN
            for assigned_role in admin.roles.values()
        ):
            raise AuthorizationError("Registry administrator required.")

        target = self.users.get(username)
        if target is None:
            raise ValidationError("Target user does not exist.")

        if repository not in self.repositories:
            raise ImageNotFoundError("Repository does not exist.")

        target.roles[repository] = role

    def create_repository(
        self,
        name: str,
        private: bool = True,
        immutable_tags: bool = False,
    ) -> Repository:
        if not self.REPOSITORY_PATTERN.fullmatch(name):
            raise ValidationError("Invalid repository name.")

        if name in self.repositories:
            raise ConflictError("Repository already exists.")

        repository = Repository(
            name=name,
            private=private,
            immutable_tags=immutable_tags,
        )
        self.repositories[name] = repository
        return repository

    def _authorize(
        self,
        user: RegistryUser,
        repository: Repository,
        operation: Operation,
    ) -> None:
        if not repository.private and operation == Operation.PULL:
            return

        role = user.roles.get(repository.name)

        if role is None:
            raise AuthorizationError(
                f"No access to repository '{repository.name}'."
            )

        allowed = {
            Operation.PULL: {
                AccessRole.READER,
                AccessRole.WRITER,
                AccessRole.ADMIN,
            },
            Operation.PUSH: {
                AccessRole.WRITER,
                AccessRole.ADMIN,
            },
            Operation.DELETE: {AccessRole.ADMIN},
            Operation.ADMIN: {AccessRole.ADMIN},
        }

        if role not in allowed[operation]:
            raise AuthorizationError(
                f"Role '{role.value}' cannot perform '{operation.value}'."
            )

    def _record(
        self,
        username: str,
        operation: Operation,
        repository: str,
        reference: str,
        outcome: str,
    ) -> None:
        self.audit_log.append(AuditEvent(
            timestamp=time.time(),
            username=username,
            operation=operation.value,
            repository=repository,
            reference=reference,
            outcome=outcome,
        ))

    def push(
        self,
        username: str,
        token: str,
        repository_name: str,
        tag: str,
        manifest: ImageManifest,
    ) -> str:
        reference = f"{repository_name}:{tag}"

        try:
            user = self.authenticate(username, token)
            repository = self.repositories.get(repository_name)

            if repository is None:
                raise ImageNotFoundError("Repository does not exist.")

            self._authorize(user, repository, Operation.PUSH)

            if not self.TAG_PATTERN.fullmatch(tag):
                raise ValidationError("Invalid image tag.")

            if not manifest.layers or not manifest.config_digest:
                raise ValidationError("Manifest requires layers and config.")

            if not manifest.config_digest.startswith("sha256:"):
                raise ValidationError("Config must use a SHA-256 digest.")

            digest = manifest.digest

            if (
                repository.immutable_tags
                and tag in repository.tags
                and repository.tags[tag] != digest
            ):
                raise ConflictError(
                    "Immutable tag cannot be reassigned."
                )

            # Store the artifact by digest. Repeated pushes of identical
            # content do not create duplicate artifacts.
            repository.artifacts.setdefault(
                digest,
                ImageArtifact(manifest=manifest)
            )

            # A mutable tag is a pointer, not an independent image.
            repository.tags[tag] = digest

            self._record(
                username, Operation.PUSH, repository_name,
                tag, "success"
            )
            return digest

        except RegistryError as exc:
            self._record(
                username, Operation.PUSH, repository_name,
                tag, f"failure: {type(exc).__name__}"
            )
            raise

    def pull(
        self,
        username: str,
        token: str,
        repository_name: str,
        reference: str,
    ) -> ImageArtifact:
        try:
            user = self.authenticate(username, token)
            repository = self.repositories.get(repository_name)

            if repository is None:
                raise ImageNotFoundError("Repository does not exist.")

            self._authorize(user, repository, Operation.PULL)

            digest = (
                reference
                if self.DIGEST_PATTERN.fullmatch(reference)
                else repository.tags.get(reference)
            )

            if digest is None:
                raise ImageNotFoundError("Image reference not found.")

            artifact = repository.artifacts.get(digest)

            if artifact is None or artifact.state == ImageState.DELETED:
                raise ImageNotFoundError("Image artifact unavailable.")

            artifact.pull_count += 1

            self._record(
                username, Operation.PULL, repository_name,
                reference, "success"
            )
            return artifact

        except RegistryError as exc:
            self._record(
                username, Operation.PULL, repository_name,
                reference, f"failure: {type(exc).__name__}"
            )
            raise

    def delete_tag(
        self,
        username: str,
        token: str,
        repository_name: str,
        tag: str,
    ) -> None:
        user = self.authenticate(username, token)
        repository = self.repositories.get(repository_name)

        if repository is None:
            raise ImageNotFoundError("Repository does not exist.")

        self._authorize(user, repository, Operation.DELETE)

        if tag not in repository.tags:
            raise ImageNotFoundError("Tag does not exist.")

        del repository.tags[tag]
        self._record(
            username, Operation.DELETE, repository_name,
            tag, "success"
        )

    def garbage_collect(
        self,
        admin_username: str,
        admin_token: str,
        repository_name: str,
    ) -> int:
        user = self.authenticate(admin_username, admin_token)
        repository = self.repositories.get(repository_name)

        if repository is None:
            raise ImageNotFoundError("Repository does not exist.")

        self._authorize(user, repository, Operation.ADMIN)

        referenced = set(repository.tags.values())
        unreferenced = set(repository.artifacts) - referenced

        for digest in unreferenced:
            del repository.artifacts[digest]

        return len(unreferenced)

    def repository_report(self, repository_name: str) -> dict:
        repository = self.repositories.get(repository_name)

        if repository is None:
            raise ImageNotFoundError("Repository does not exist.")

        return {
            "repository": repository.name,
            "private": repository.private,
            "tag_count": len(repository.tags),
            "artifact_count": len(repository.artifacts),
            "total_pulls": sum(
                artifact.pull_count
                for artifact in repository.artifacts.values()
            ),
            "tags": dict(sorted(repository.tags.items())),
        }


def create_manifest(
    version: str,
    layers: tuple[str, ...],
    architecture: str = "amd64",
) -> ImageManifest:
    if not version:
        raise ValidationError("Version is required.")

    if architecture not in {"amd64", "arm64", "arm", "386"}:
        raise ValidationError("Unsupported architecture.")

    return ImageManifest(
        media_type="application/vnd.oci.image.manifest.v1+json",
        layers=layers,
        config_digest="sha256:" + hashlib.sha256(
            f"config-{version}".encode()
        ).hexdigest(),
        architecture=architecture,
        operating_system="linux",
        created_at=time.time(),
    )


def demonstration() -> None:
    registry = ContainerRegistry("production-registry")

    registry.add_user("administrator", "admin-secret-token-2026")
    registry.add_user("developer", "developer-secret-token-2026")
    registry.add_user("deployment", "deployment-secret-token-2026")

    admin = registry.users["administrator"]
    admin.roles["*"] = AccessRole.ADMIN

    # Initial administrative repository setup.
    repository = registry.create_repository(
        "platform/api",
        private=True,
        immutable_tags=False,
    )

    # Administrator permissions are assigned directly during bootstrap.
    registry.users["administrator"].roles[repository.name] = AccessRole.ADMIN
    registry.grant_access(
        "administrator",
        "admin-secret-token-2026",
        "developer",
        repository.name,
        AccessRole.WRITER,
    )
    registry.grant_access(
        "administrator",
        "admin-secret-token-2026",
        "deployment",
        repository.name,
        AccessRole.READER,
    )

    manifest_v1 = create_manifest(
        "1.0.0",
        (
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
        ),
    )

    digest_v1 = registry.push(
        "developer",
        "developer-secret-token-2026",
        "platform/api",
        "1.0.0",
        manifest_v1,
    )

    registry.push(
        "developer",
        "developer-secret-token-2026",
        "platform/api",
        "latest",
        manifest_v1,
    )

    pulled = registry.pull(
        "deployment",
        "deployment-secret-token-2026",
        "platform/api",
        "latest",
    )

    assert pulled.digest == digest_v1

    # A new version moves the mutable latest pointer.
    manifest_v2 = create_manifest(
        "2.0.0",
        ("sha256:" + "c" * 64,),
        architecture="arm64",
    )

    registry.push(
        "developer",
        "developer-secret-token-2026",
        "platform/api",
        "2.0.0",
        manifest_v2,
    )

    registry.push(
        "developer",
        "developer-secret-token-2026",
        "platform/api",
        "latest",
        manifest_v2,
    )

    # Digest references remain stable when tags move.
    old_image = registry.pull(
        "deployment",
        "deployment-secret-token-2026",
        "platform/api",
        digest_v1,
    )

    assert old_image.digest == digest_v1

    print("Repository report:")
    print(json.dumps(
        registry.repository_report("platform/api"),
        indent=2
    ))

    try:
        registry.push(
            "deployment",
            "deployment-secret-token-2026",
            "platform/api",
            "unauthorized",
            manifest_v2,
        )
    except AuthorizationError as exc:
        print(f"Expected authorization failure: {exc}")

    removed = registry.garbage_collect(
        "administrator",
        "admin-secret-token-2026",
        "platform/api",
    )

    print(f"Unreferenced artifacts removed: {removed}")
    print(f"Audit events recorded: {len(registry.audit_log)}")

    assert len(registry.audit_log) >= 5


if __name__ == "__main__":
    demonstration()
