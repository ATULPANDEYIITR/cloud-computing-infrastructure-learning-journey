#!/usr/bin/env python3
"""
Docker Container Management Simulator

Models container lifecycle, environment variables, commands, logs,
inspection, resource limits, restart policies, and operational failures.

Uses only the Python standard library.
"""

from __future__ import annotations

import json
import logging
import shlex
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("container-manager")


class ContainerError(Exception):
    """Base exception for container management."""


class ContainerNotFound(ContainerError):
    pass


class InvalidTransition(ContainerError):
    pass


class ConfigurationError(ContainerError):
    pass


class ContainerState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    RESTARTING = "restarting"
    STOPPED = "stopped"
    EXITED = "exited"
    REMOVING = "removing"


class RestartPolicy(str, Enum):
    NO = "no"
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    UNLESS_STOPPED = "unless-stopped"


@dataclass
class ContainerConfig:
    image: str
    command: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    restart_policy: RestartPolicy = RestartPolicy.NO
    memory_limit_mb: int = 512
    cpu_limit: float = 1.0
    labels: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.image or any(c.isspace() for c in self.image):
            raise ConfigurationError("A valid image reference is required.")

        if self.memory_limit_mb < 16:
            raise ConfigurationError("Memory limit must be at least 16 MB.")

        if not 0.1 <= self.cpu_limit <= 64:
            raise ConfigurationError("CPU limit must be between 0.1 and 64.")

        for key, value in self.environment.items():
            if not key or not key.replace("_", "a").isalnum():
                raise ConfigurationError(f"Invalid environment key: {key}")
            if not isinstance(value, str):
                raise ConfigurationError("Environment values must be strings.")

        if any("\x00" in value for value in self.environment.values()):
            raise ConfigurationError("Environment values cannot contain NUL.")


@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str


@dataclass
class Container:
    container_id: str
    name: str
    config: ContainerConfig
    state: ContainerState
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    restart_count: int = 0
    logs: list[LogEntry] = field(default_factory=list)

    def add_log(self, message: str, level: str = "INFO") -> None:
        self.logs.append(
            LogEntry(
                datetime.now(timezone.utc).isoformat(),
                level,
                message,
            )
        )


class ContainerManager:
    """In-memory container lifecycle and operational management."""

    def __init__(self, log_directory: str = "container_logs"):
        self.containers: dict[str, Container] = {}
        self.names: dict[str, str] = {}
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)

    def _resolve(self, identifier: str) -> Container:
        container_id = self.names.get(identifier, identifier)
        container = self.containers.get(container_id)

        if container is None:
            raise ContainerNotFound(f"Container not found: {identifier}")

        return container

    def create(
        self,
        name: str,
        config: ContainerConfig,
    ) -> Container:
        config.validate()

        if not name or name in self.names:
            raise ConfigurationError("Container name is empty or already used.")

        container_id = uuid.uuid4().hex[:12]

        container = Container(
            container_id=container_id,
            name=name,
            config=config,
            state=ContainerState.CREATED,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        container.add_log(f"Container created from {config.image}")

        self.containers[container_id] = container
        self.names[name] = container_id

        logger.info("Created container %s (%s)", name, container_id)
        return container

    def start(self, identifier: str) -> Container:
        container = self._resolve(identifier)

        if container.state not in (
            ContainerState.CREATED,
            ContainerState.STOPPED,
            ContainerState.EXITED,
        ):
            raise InvalidTransition(
                f"Cannot start container in {container.state.value} state."
            )

        container.state = ContainerState.RUNNING
        container.started_at = datetime.now(timezone.utc).isoformat()
        container.finished_at = None
        container.exit_code = None

        container.add_log("Container started.")
        return container

    def pause(self, identifier: str) -> Container:
        container = self._resolve(identifier)

        if container.state != ContainerState.RUNNING:
            raise InvalidTransition("Only running containers can be paused.")

        container.state = ContainerState.PAUSED
        container.add_log("Container paused.")
        return container

    def unpause(self, identifier: str) -> Container:
        container = self._resolve(identifier)

        if container.state != ContainerState.PAUSED:
            raise InvalidTransition("Only paused containers can be unpaused.")

        container.state = ContainerState.RUNNING
        container.add_log("Container resumed.")
        return container

    def stop(self, identifier: str, exit_code: int = 0) -> Container:
        container = self._resolve(identifier)

        if container.state not in (
            ContainerState.RUNNING,
            ContainerState.PAUSED,
        ):
            raise InvalidTransition("Container is not running or paused.")

        if not 0 <= exit_code <= 255:
            raise ValueError("Exit code must be between 0 and 255.")

        container.state = ContainerState.STOPPED
        container.finished_at = datetime.now(timezone.utc).isoformat()
        container.exit_code = exit_code
        container.add_log(f"Container stopped with exit code {exit_code}.")
        return container

    def simulate_exit(
        self,
        identifier: str,
        exit_code: int,
    ) -> Container:
        container = self._resolve(identifier)

        if container.state != ContainerState.RUNNING:
            raise InvalidTransition("Only running containers can exit.")

        if not 0 <= exit_code <= 255:
            raise ValueError("Invalid exit code.")

        container.state = ContainerState.EXITED
        container.finished_at = datetime.now(timezone.utc).isoformat()
        container.exit_code = exit_code

        container.add_log(
            f"Process exited with code {exit_code}.",
            "ERROR" if exit_code else "INFO",
        )
        return container

    def restart(self, identifier: str) -> Container:
        container = self._resolve(identifier)

        if container.state not in (
            ContainerState.RUNNING,
            ContainerState.PAUSED,
            ContainerState.STOPPED,
            ContainerState.EXITED,
        ):
            raise InvalidTransition("Container cannot be restarted.")

        container.state = ContainerState.RESTARTING
        container.add_log("Restart initiated.")

        container.state = ContainerState.RUNNING
        container.started_at = datetime.now(timezone.utc).isoformat()
        container.finished_at = None
        container.exit_code = None
        container.restart_count += 1

        container.add_log("Container restarted.")
        return container

    def remove(
        self,
        identifier: str,
        force: bool = False,
    ) -> None:
        container = self._resolve(identifier)

        if container.state in (
            ContainerState.RUNNING,
            ContainerState.PAUSED,
        ) and not force:
            raise InvalidTransition(
                "Stop the container before removing it, or use force=True."
            )

        container.state = ContainerState.REMOVING
        container.add_log("Container removed.")

        del self.containers[container.container_id]
        del self.names[container.name]

    def execute(
        self,
        identifier: str,
        command: list[str],
    ) -> dict[str, Any]:
        container = self._resolve(identifier)

        if container.state != ContainerState.RUNNING:
            raise InvalidTransition(
                "Commands can only be executed in running containers."
            )

        if not command or not all(isinstance(x, str) for x in command):
            raise ValueError("Command must be a non-empty string list.")

        # This simulator does not execute arbitrary host shell commands.
        allowed = {"printenv", "echo", "hostname", "date"}

        if command[0] not in allowed:
            raise PermissionError(
                f"Command is not permitted by the simulator: {command[0]}"
            )

        if command[0] == "printenv":
            if len(command) == 1:
                output = "\n".join(
                    f"{key}={value}"
                    for key, value in sorted(
                        container.config.environment.items()
                    )
                )
            else:
                key = command[1]
                output = container.config.environment.get(key, "")

        elif command[0] == "echo":
            output = " ".join(command[1:])

        elif command[0] == "hostname":
            output = container.name

        else:
            output = datetime.now(timezone.utc).isoformat()

        container.add_log(f"Command executed: {shlex.join(command)}")
        return {
            "container": container.name,
            "command": command,
            "output": output,
            "exit_code": 0,
        }

    def inspect(self, identifier: str) -> dict[str, Any]:
        container = self._resolve(identifier)

        return {
            "id": container.container_id,
            "name": container.name,
            "image": container.config.image,
            "state": container.state.value,
            "created_at": container.created_at,
            "started_at": container.started_at,
            "finished_at": container.finished_at,
            "exit_code": container.exit_code,
            "restart_count": container.restart_count,
            "environment": container.config.environment.copy(),
            "command": container.config.command.copy(),
            "resources": {
                "memory_mb": container.config.memory_limit_mb,
                "cpu": container.config.cpu_limit,
            },
            "restart_policy": container.config.restart_policy.value,
            "labels": container.config.labels.copy(),
        }

    def list_containers(
        self,
        state: ContainerState | None = None,
    ) -> list[dict[str, str]]:
        result = []

        for container in self.containers.values():
            if state is None or container.state == state:
                result.append(
                    {
                        "id": container.container_id,
                        "name": container.name,
                        "image": container.config.image,
                        "state": container.state.value,
                    }
                )

        return sorted(result, key=lambda item: item["name"])

    def logs(
        self,
        identifier: str,
        tail: int | None = None,
        level: str | None = None,
    ) -> list[dict[str, str]]:
        container = self._resolve(identifier)
        entries = container.logs

        if level:
            entries = [
                entry for entry in entries
                if entry.level == level.upper()
            ]

        if tail is not None:
            if tail < 0:
                raise ValueError("Tail must not be negative.")
            entries = entries[-tail:] if tail else []

        return [asdict(entry) for entry in entries]

    def export_logs(self, identifier: str) -> Path:
        container = self._resolve(identifier)

        safe_name = container.container_id
        output_file = self.log_directory / f"{safe_name}.json"

        # The generated filename is based on a server-controlled ID.
        temporary = output_file.with_suffix(".tmp")

        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                [asdict(entry) for entry in container.logs],
                file,
                indent=2,
            )

        temporary.replace(output_file)
        return output_file

    def apply_restart_policy(self, identifier: str) -> bool:
        container = self._resolve(identifier)

        if container.state != ContainerState.EXITED:
            return False

        policy = container.config.restart_policy

        should_restart = (
            policy == RestartPolicy.ALWAYS
            or policy == RestartPolicy.UNLESS_STOPPED
            or (
                policy == RestartPolicy.ON_FAILURE
                and container.exit_code != 0
            )
        )

        if should_restart:
            self.restart(identifier)
            container.add_log(
                f"Restart policy {policy.value} applied."
            )

        return should_restart


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def run_demo() -> None:
    manager = ContainerManager()

    print_section("1. Container Creation")

    web = manager.create(
        "web-api",
        ContainerConfig(
            image="python:3.13-slim",
            command=["python", "app.py"],
            environment={
                "APP_ENV": "production",
                "PORT": "8000",
                "LOG_LEVEL": "INFO",
            },
            restart_policy=RestartPolicy.ON_FAILURE,
            memory_limit_mb=1024,
            cpu_limit=2.0,
            labels={"team": "platform", "service": "web-api"},
        ),
    )

    print(json.dumps(manager.inspect(web.container_id), indent=2))

    print_section("2. Container Lifecycle")

    manager.start("web-api")
    print("Started:", manager.inspect("web-api")["state"])

    manager.pause("web-api")
    print("Paused:", manager.inspect("web-api")["state"])

    manager.unpause("web-api")
    print("Resumed:", manager.inspect("web-api")["state"])

    print_section("3. Environment Variables and Commands")

    print(manager.execute("web-api", ["printenv", "APP_ENV"]))
    print(manager.execute("web-api", ["echo", "Service ready"]))
    print(manager.execute("web-api", ["hostname"]))

    print_section("4. Logs")

    for entry in manager.logs("web-api", tail=5):
        print(entry)

    print_section("5. Exit and Restart Policy")

    manager.simulate_exit("web-api", 1)
    print("Exited:", manager.inspect("web-api")["state"])

    restarted = manager.apply_restart_policy("web-api")
    print("Restart policy applied:", restarted)
    print("Current state:", manager.inspect("web-api")["state"])

    print_section("6. Container Inspection and Listing")

    print(json.dumps(manager.list_containers(), indent=2))

    print_section("7. Log Export")

    exported = manager.export_logs("web-api")
    print("Exported logs:", exported)

    print_section("8. Validation and Failure Handling")

    try:
        manager.start("web-api")
    except InvalidTransition as error:
        print("Expected lifecycle error:", error)

    try:
        manager.create(
            "invalid-container",
            ContainerConfig(
                image="nginx:latest",
                memory_limit_mb=4,
            ),
        )
    except ConfigurationError as error:
        print("Expected configuration error:", error)

    try:
        manager.execute("web-api", ["rm", "-rf", "/"])
    except PermissionError as error:
        print("Expected command security rejection:", error)

    print_section("9. Removal")

    manager.stop("web-api")
    manager.remove("web-api")
    print("Remaining containers:", manager.list_containers())

    assert not manager.containers
    print("\nAll demonstration assertions passed.")


if __name__ == "__main__":
    run_demo()
