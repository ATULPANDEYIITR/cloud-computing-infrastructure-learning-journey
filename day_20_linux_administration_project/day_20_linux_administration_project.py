#!/usr/bin/env python3
"""
Linux Administration Project
============================

A self-contained educational administration toolkit covering:

- Linux server setup concepts
- Users and groups
- File ownership and permissions
- SSH hardening
- Services
- System inspection
- Automation
- Validation and configuration auditing
- Logging
- Backups
- Scheduling concepts
- Security-oriented administration practices

The script is intentionally designed to be safe to study and run. It uses a
temporary laboratory directory for demonstrations instead of modifying real
system accounts, SSH configuration, or services.

Run:
    python3 linux_admin_project.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional


# ---------------------------------------------------------------------------
# 1. Basic terminology and platform inspection
# ---------------------------------------------------------------------------

@dataclass
class SystemInformation:
    hostname: str
    operating_system: str
    kernel: str
    architecture: str
    python_version: str
    cpu_count: Optional[int]
    current_user: str


def get_system_information() -> SystemInformation:
    """Collect non-destructive information about the current machine."""
    try:
        current_user = os.getlogin()
    except OSError:
        current_user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    return SystemInformation(
        hostname=platform.node(),
        operating_system=platform.system(),
        kernel=platform.release(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count(),
        current_user=current_user,
    )


def print_system_information() -> None:
    info = get_system_information()
    print("\nSYSTEM INFORMATION")
    print("=" * 70)
    for key, value in asdict(info).items():
        print(f"{key.replace('_', ' ').title():22}: {value}")


# ---------------------------------------------------------------------------
# 2. Linux command execution
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    command: str
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float


def run_command(
    command: list[str],
    *,
    timeout: int = 10,
    check: bool = False,
) -> CommandResult:
    """
    Execute a command safely without invoking a shell.

    Passing a list instead of a shell command string avoids shell expansion
    and makes accidental command injection less likely.
    """
    started = time.perf_counter()

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        result = CommandResult(
            command=" ".join(command),
            return_code=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            duration_seconds=time.perf_counter() - started,
        )
    except FileNotFoundError as exc:
        result = CommandResult(
            command=" ".join(command),
            return_code=127,
            stdout="",
            stderr=str(exc),
            duration_seconds=time.perf_counter() - started,
        )
    except subprocess.TimeoutExpired as exc:
        result = CommandResult(
            command=" ".join(command),
            return_code=124,
            stdout=(exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            stderr="Command timed out",
            duration_seconds=time.perf_counter() - started,
        )

    if check and result.return_code != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.return_code}: {result.command}\n"
            f"{result.stderr}"
        )

    return result


# ---------------------------------------------------------------------------
# 3. Users and groups
# ---------------------------------------------------------------------------

@dataclass
class UserRecord:
    username: str
    uid: int
    gid: int
    home: str
    shell: str


def parse_passwd_file(path: Path = Path("/etc/passwd")) -> list[UserRecord]:
    """
    Parse the traditional passwd format.

    Format:
        username:x:uid:gid:gecos:home:shell

    Reading /etc/passwd is normally safe because it contains account metadata,
    not plaintext passwords.
    """
    users: list[UserRecord] = []

    if not path.exists():
        return users

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return users

    for line in lines:
        if not line or line.startswith("#"):
            continue

        fields = line.split(":")
        if len(fields) != 7:
            continue

        try:
            uid = int(fields[2])
            gid = int(fields[3])
        except ValueError:
            continue

        users.append(
            UserRecord(
                username=fields[0],
                uid=uid,
                gid=gid,
                home=fields[5],
                shell=fields[6],
            )
        )

    return users


def classify_user(user: UserRecord) -> str:
    """
    A common Linux convention is that UID 0 is root and ordinary users
    generally have larger UIDs. Exact UID ranges vary by distribution.
    """
    if user.uid == 0:
        return "root"
    if user.uid < 1000:
        return "system/service account"
    return "regular user"


def show_users(limit: int = 20) -> None:
    users = parse_passwd_file()
    print("\nLOCAL ACCOUNT INVENTORY")
    print("=" * 90)
    print(f"{'USER':<20} {'UID':<8} {'GID':<8} {'TYPE':<22} {'SHELL'}")
    print("-" * 90)

    for user in users[:limit]:
        print(
            f"{user.username:<20} "
            f"{user.uid:<8} "
            f"{user.gid:<8} "
            f"{classify_user(user):<22} "
            f"{user.shell}"
        )


# ---------------------------------------------------------------------------
# 4. Groups
# ---------------------------------------------------------------------------

@dataclass
class GroupRecord:
    name: str
    gid: int
    members: list[str] = field(default_factory=list)


def parse_group_file(path: Path = Path("/etc/group")) -> list[GroupRecord]:
    groups: list[GroupRecord] = []

    if not path.exists():
        return groups

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return groups

    for line in lines:
        if not line or line.startswith("#"):
            continue

        fields = line.split(":")
        if len(fields) != 4:
            continue

        try:
            gid = int(fields[2])
        except ValueError:
            continue

        members = [member for member in fields[3].split(",") if member]

        groups.append(GroupRecord(fields[0], gid, members))

    return groups


def show_groups(limit: int = 20) -> None:
    groups = parse_group_file()
    print("\nGROUP INVENTORY")
    print("=" * 80)

    for group in groups[:limit]:
        members = ", ".join(group.members) if group.members else "(none)"
        print(f"{group.name:<25} GID={group.gid:<8} members={members}")


# ---------------------------------------------------------------------------
# 5. Permission model
# ---------------------------------------------------------------------------

PERMISSION_BITS = {
    "owner": (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
    "group": (stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
    "other": (stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH),
}


def permission_string(mode: int) -> str:
    """
    Convert permission bits into a familiar representation such as rwxr-x---.

    The first character is handled separately because it represents file type.
    """
    result = []

    for who in ("owner", "group", "other"):
        read_bit, write_bit, execute_bit = PERMISSION_BITS[who]
        result.append("r" if mode & read_bit else "-")
        result.append("w" if mode & write_bit else "-")
        result.append("x" if mode & execute_bit else "-")

    return "".join(result)


def numeric_permissions(mode: int) -> str:
    """Return permissions such as 750 or 644."""
    digits = []

    for read_bit, write_bit, execute_bit in PERMISSION_BITS.values():
        value = 0
        value += 4 if mode & read_bit else 0
        value += 2 if mode & write_bit else 0
        value += 1 if mode & execute_bit else 0
        digits.append(str(value))

    return "".join(digits)


def explain_permissions(permission: str) -> str:
    """
    Explain a nine-character permission string.

    Example:
        rwxr-x---
        owner: rwx
        group: r-x
        other: ---
    """
    if len(permission) != 9 or any(char not in "rwx-" for char in permission):
        raise ValueError("Permission string must contain exactly nine r/w/x/- characters.")

    owner = permission[0:3]
    group = permission[3:6]
    other = permission[6:9]

    return (
        f"owner={owner} ({_permission_value(owner)}), "
        f"group={group} ({_permission_value(group)}), "
        f"other={other} ({_permission_value(other)})"
    )


def _permission_value(bits: str) -> int:
    value = 0
    value += 4 if bits[0] == "r" else 0
    value += 2 if bits[1] == "w" else 0
    value += 1 if bits[2] == "x" else 0
    return value


def demonstrate_permissions(lab: Path) -> None:
    print("\nFILE PERMISSIONS LAB")
    print("=" * 80)

    examples = {
        "private.txt": 0o600,
        "shared.txt": 0o640,
        "script.sh": 0o750,
        "public.txt": 0o644,
        "dangerous.txt": 0o777,
    }

    for filename, mode in examples.items():
        path = lab / filename
        path.write_text(f"Example file: {filename}\n", encoding="utf-8")
        os.chmod(path, mode)

        actual_mode = stat.S_IMODE(path.stat().st_mode)
        print(
            f"{filename:<18} "
            f"numeric={numeric_permissions(actual_mode)} "
            f"symbolic={permission_string(actual_mode)} "
            f"| {explain_permissions(permission_string(actual_mode))}"
        )

    print("\nImportant permission principles:")
    print("  400 = owner read only")
    print("  600 = owner read/write")
    print("  640 = owner read/write, group read")
    print("  644 = owner read/write, everyone else read")
    print("  750 = owner full access, group read/execute")
    print("  755 = owner full access, others read/execute")
    print("  777 = everyone read/write/execute and is usually inappropriate for sensitive files")


# ---------------------------------------------------------------------------
# 6. Ownership and security checks
# ---------------------------------------------------------------------------

@dataclass
class PermissionFinding:
    path: str
    permissions: str
    issue: str
    severity: str


def audit_directory_permissions(root: Path) -> list[PermissionFinding]:
    """
    Find world-writable files/directories inside a controlled directory.

    This deliberately audits only the supplied root rather than recursively
    scanning the entire host filesystem.
    """
    findings: list[PermissionFinding] = []

    if not root.exists():
        return findings

    for path in root.rglob("*"):
        try:
            mode = path.stat().st_mode
        except OSError:
            continue

        if mode & stat.S_IWOTH:
            permissions = permission_string(mode)
            findings.append(
                PermissionFinding(
                    path=str(path),
                    permissions=permissions,
                    issue="World-writable object",
                    severity="HIGH",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# 7. SSH hardening concepts
# ---------------------------------------------------------------------------

@dataclass
class SSHSetting:
    key: str
    value: str
    recommended_value: str
    reason: str


SSH_HARDENING_BASELINE = [
    SSHSetting(
        "PermitRootLogin",
        "yes",
        "no",
        "Direct root SSH login increases the impact of credential compromise.",
    ),
    SSHSetting(
        "PasswordAuthentication",
        "yes",
        "no",
        "Key-based authentication can reduce exposure to password guessing.",
    ),
    SSHSetting(
        "PubkeyAuthentication",
        "no",
        "yes",
        "Public-key authentication provides a strong alternative to passwords.",
    ),
    SSHSetting(
        "PermitEmptyPasswords",
        "yes",
        "no",
        "Empty-password accounts should not be accepted over SSH.",
    ),
    SSHSetting(
        "MaxAuthTries",
        "20",
        "3-6",
        "Limiting authentication attempts reduces repeated guessing opportunities.",
    ),
]


def parse_sshd_config(text: str) -> dict[str, str]:
    """
    Parse a useful subset of sshd_config.

    This is intentionally not a complete OpenSSH parser because real
    configuration semantics include Match blocks, includes, and distribution-
    specific details.
    """
    settings: dict[str, str] = {}

    for line in text.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        parts = stripped.split(None, 1)
        if len(parts) == 2:
            key, value = parts
            settings[key.lower()] = value.strip()

    return settings


def audit_ssh_configuration(config_text: str) -> list[str]:
    settings = parse_sshd_config(config_text)
    findings: list[str] = []

    root_login = settings.get("permitrootlogin", "prohibit-password").lower()
    if root_login == "yes":
        findings.append("HIGH: PermitRootLogin is enabled.")

    password_auth = settings.get("passwordauthentication", "yes").lower()
    if password_auth == "yes":
        findings.append(
            "MEDIUM: PasswordAuthentication is enabled. "
            "Evaluate whether key-only authentication is appropriate."
        )

    public_key = settings.get("pubkeyauthentication", "yes").lower()
    if public_key == "no":
        findings.append("HIGH: PubkeyAuthentication is disabled.")

    empty_passwords = settings.get("permitemptypasswords", "no").lower()
    if empty_passwords == "yes":
        findings.append("CRITICAL: Empty-password SSH authentication is enabled.")

    try:
        max_auth_tries = int(settings.get("maxauthtries", "6"))
        if max_auth_tries > 6:
            findings.append(
                f"MEDIUM: MaxAuthTries is {max_auth_tries}; consider a lower limit."
            )
    except ValueError:
        findings.append("WARNING: MaxAuthTries is not a valid integer.")

    return findings


def demonstrate_ssh_audit() -> None:
    example_config = """
# Educational SSH configuration example
Port 22
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication no
PermitEmptyPasswords no
MaxAuthTries 12
"""

    print("\nSSH HARDENING AUDIT")
    print("=" * 80)

    for finding in audit_ssh_configuration(example_config):
        print(f"  {finding}")

    print("\nKey SSH concepts:")
    print("  - Authentication answers: who are you?")
    print("  - Authorization answers: what are you allowed to do?")
    print("  - Encryption protects traffic in transit.")
    print("  - Host keys help clients identify servers.")
    print("  - User keys commonly use a private/public key pair.")
    print("  - sshd_config controls the SSH server.")
    print("  - authorized_keys controls which public keys may authenticate for a user.")
    print("  - Configuration changes should be validated before restarting sshd.")


# ---------------------------------------------------------------------------
# 8. Service management
# ---------------------------------------------------------------------------

@dataclass
class ServiceStatus:
    service: str
    available: bool
    active: Optional[bool]
    raw_output: str


def systemctl_available() -> bool:
    return shutil.which("systemctl") is not None


def get_service_status(service_name: str) -> ServiceStatus:
    """
    Inspect a service without changing its state.

    Typical Linux commands include:
        systemctl status service
        systemctl is-active service
        systemctl is-enabled service

    No start/stop/restart operation is performed by this educational tool.
    """
    if not systemctl_available():
        return ServiceStatus(service_name, False, None, "systemctl is unavailable")

    result = run_command(["systemctl", "is-active", service_name])

    active = result.return_code == 0

    return ServiceStatus(
        service=service_name,
        available=True,
        active=active,
        raw_output=result.stdout or result.stderr,
    )


def show_service_status(service_name: str) -> None:
    status = get_service_status(service_name)

    print("\nSERVICE INSPECTION")
    print("=" * 80)
    print(f"Service : {status.service}")
    print(f"Available: {status.available}")
    print(f"Active  : {status.active}")
    print(f"Output  : {status.raw_output}")


# ---------------------------------------------------------------------------
# 9. Process inspection
# ---------------------------------------------------------------------------

def process_snapshot() -> list[dict[str, str]]:
    """
    Read process information using ps where available.

    The command is read-only.
    """
    if not shutil.which("ps"):
        return []

    result = run_command(
        ["ps", "-eo", "pid,user,stat,comm"],
        timeout=5,
    )

    if result.return_code != 0:
        return []

    processes = []

    for line in result.stdout.splitlines()[1:]:
        fields = line.split(None, 3)
        if len(fields) == 4:
            processes.append(
                {
                    "pid": fields[0],
                    "user": fields[1],
                    "state": fields[2],
                    "command": fields[3],
                }
            )

    return processes


def show_processes(limit: int = 15) -> None:
    processes = process_snapshot()

    print("\nPROCESS SNAPSHOT")
    print("=" * 80)

    if not processes:
        print("Process information is unavailable.")
        return

    print(f"{'PID':<10} {'USER':<20} {'STATE':<8} COMMAND")
    print("-" * 80)

    for process in processes[:limit]:
        print(
            f"{process['pid']:<10} "
            f"{process['user']:<20} "
            f"{process['state']:<8} "
            f"{process['command']}"
        )


# ---------------------------------------------------------------------------
# 10. Disk usage
# ---------------------------------------------------------------------------

@dataclass
class DiskInformation:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int

    @property
    def used_percentage(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return self.used_bytes / self.total_bytes * 100


def get_disk_information(path: str = "/") -> DiskInformation:
    usage = shutil.disk_usage(path)

    return DiskInformation(
        path=path,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
    )


def human_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    number = float(value)

    for unit in units:
        if number < 1024 or unit == units[-1]:
            return f"{number:.2f} {unit}"
        number /= 1024

    return f"{value} B"


def show_disk_usage(path: str = "/") -> None:
    try:
        disk = get_disk_information(path)
    except OSError as exc:
        print(f"Unable to inspect disk: {exc}")
        return

    print("\nDISK USAGE")
    print("=" * 80)
    print(f"Path : {disk.path}")
    print(f"Total: {human_bytes(disk.total_bytes)}")
    print(f"Used : {human_bytes(disk.used_bytes)} ({disk.used_percentage:.2f}%)")
    print(f"Free : {human_bytes(disk.free_bytes)}")


# ---------------------------------------------------------------------------
# 11. Configuration validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    name: str
    passed: bool
    message: str


def validate_hostname(hostname: str) -> ValidationResult:
    if not hostname:
        return ValidationResult("hostname", False, "Hostname cannot be empty.")

    if len(hostname) > 253:
        return ValidationResult("hostname", False, "Hostname is too long.")

    pattern = re.compile(
        r"^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)$"
    )

    if not pattern.match(hostname):
        return ValidationResult(
            "hostname",
            False,
            "Hostname contains invalid characters.",
        )

    return ValidationResult("hostname", True, "Hostname format is valid.")


def validate_username(username: str) -> ValidationResult:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        return ValidationResult(
            "username",
            False,
            "Use lowercase letters, digits, underscores, and hyphens with a safe length.",
        )

    if username in {"root", "daemon", "bin", "nobody"}:
        return ValidationResult(
            "username",
            False,
            "This name is reserved or normally associated with a system account.",
        )

    return ValidationResult("username", True, "Username format is acceptable.")


def validate_port(port: int) -> ValidationResult:
    if 1 <= port <= 65535:
        return ValidationResult("port", True, "Port is within the TCP/UDP range.")
    return ValidationResult("port", False, "Port must be between 1 and 65535.")


def demonstrate_validation() -> None:
    print("\nCONFIGURATION VALIDATION")
    print("=" * 80)

    tests: list[tuple[str, ValidationResult]] = [
        ("server01", validate_hostname("server01")),
        ("bad host", validate_hostname("bad host")),
        ("deploy_user", validate_username("deploy_user")),
        ("BadUser", validate_username("BadUser")),
        ("443", validate_port(443)),
        ("70000", validate_port(70000)),
    ]

    for value, result in tests:
        state = "PASS" if result.passed else "FAIL"
        print(f"{state:<5} {result.name:<12} {value:<15} {result.message}")


# ---------------------------------------------------------------------------
# 12. Automation and idempotency
# ---------------------------------------------------------------------------

@dataclass
class AutomationTask:
    name: str
    action: Callable[[], None]


def ensure_directory(path: Path, mode: int = 0o750) -> bool:
    """
    Idempotent operation:
    - First execution creates the directory.
    - Later executions leave it in place.
    - Permissions are enforced each time.
    """
    created = False

    if not path.exists():
        path.mkdir(parents=True)
        created = True

    if not path.is_dir():
        raise NotADirectoryError(str(path))

    os.chmod(path, mode)
    return created


def ensure_text_file(path: Path, content: str, mode: int = 0o640) -> bool:
    """
    Ensure a file contains exactly the desired configuration.

    Returning whether a change was needed makes automation easier to audit.
    """
    changed = False

    current = None
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            current = None

    if current != content:
        path.write_text(content, encoding="utf-8")
        changed = True

    os.chmod(path, mode)
    return changed


def demonstrate_idempotent_automation(lab: Path) -> None:
    print("\nAUTOMATION AND IDEMPOTENCY")
    print("=" * 80)

    config_dir = lab / "etc" / "example-service"
    config_file = config_dir / "service.conf"

    first_directory_change = ensure_directory(config_dir)
    second_directory_change = ensure_directory(config_dir)

    desired_config = (
        "service_name=example-service\n"
        "listen_address=127.0.0.1\n"
        "listen_port=8080\n"
        "enabled=true\n"
    )

    first_file_change = ensure_text_file(config_file, desired_config)
    second_file_change = ensure_text_file(config_file, desired_config)

    print(f"First directory run changed state : {first_directory_change}")
    print(f"Second directory run changed state: {second_directory_change}")
    print(f"First file run changed state      : {first_file_change}")
    print(f"Second file run changed state     : {second_file_change}")

    print(
        "\nIdempotency means repeatedly applying the desired state produces "
        "the same final state rather than creating duplicate or conflicting changes."
    )


# ---------------------------------------------------------------------------
# 13. Backup and integrity
# ---------------------------------------------------------------------------

@dataclass
class FileChecksum:
    path: str
    algorithm: str
    digest: str
    size_bytes: int


def calculate_sha256(path: Path) -> FileChecksum:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return FileChecksum(
        path=str(path),
        algorithm="SHA-256",
        digest=digest.hexdigest(),
        size_bytes=path.stat().st_size,
    )


def create_backup(source: Path, destination_directory: Path) -> Path:
    """
    Create a simple local backup.

    Production backup systems should also consider:
    - retention
    - encryption
    - off-host copies
    - immutable storage
    - restore testing
    - permissions
    - monitoring
    """
    destination_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = destination_directory / f"{source.name}.{timestamp}.bak"

    shutil.copy2(source, destination)
    return destination


def demonstrate_backup(lab: Path) -> None:
    print("\nBACKUP AND INTEGRITY")
    print("=" * 80)

    source = lab / "important.conf"
    source.write_text(
        "# Example configuration\n"
        "environment=production\n"
        "debug=false\n",
        encoding="utf-8",
    )
    os.chmod(source, 0o640)

    before = calculate_sha256(source)
    backup = create_backup(source, lab / "backups")
    after = calculate_sha256(backup)

    print(f"Original : {source}")
    print(f"Backup   : {backup}")
    print(f"Original SHA-256: {before.digest}")
    print(f"Backup SHA-256  : {after.digest}")
    print(f"Integrity match : {before.digest == after.digest}")


# ---------------------------------------------------------------------------
# 14. Logging
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    timestamp: str
    level: str
    component: str
    message: str


class SimpleAuditLog:
    def __init__(self) -> None:
        self.entries: list[LogEntry] = []

    def record(self, level: str, component: str, message: str) -> None:
        self.entries.append(
            LogEntry(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                level=level.upper(),
                component=component,
                message=message,
            )
        )

    def export_json(self, path: Path) -> None:
        path.write_text(
            json.dumps([asdict(entry) for entry in self.entries], indent=2),
            encoding="utf-8",
        )

    def print_entries(self) -> None:
        for entry in self.entries:
            print(
                f"{entry.timestamp} "
                f"{entry.level:<8} "
                f"{entry.component:<16} "
                f"{entry.message}"
            )


def demonstrate_logging(lab: Path) -> None:
    print("\nAUDIT LOGGING")
    print("=" * 80)

    audit_log = SimpleAuditLog()

    audit_log.record("INFO", "user-management", "Account inventory inspected.")
    audit_log.record("INFO", "ssh-audit", "SSH configuration checked.")
    audit_log.record("WARNING", "permissions", "World-writable file detected.")
    audit_log.record("INFO", "backup", "Configuration backup completed.")

    audit_log.print_entries()

    output = lab / "audit-log.json"
    audit_log.export_json(output)
    print(f"\nStructured log written to: {output}")


# ---------------------------------------------------------------------------
# 15. Security baseline
# ---------------------------------------------------------------------------

@dataclass
class SecurityCheck:
    name: str
    status: str
    explanation: str


def security_baseline() -> list[SecurityCheck]:
    """
    These checks describe principles rather than making changes to the host.
    """
    return [
        SecurityCheck(
            "Least privilege",
            "CHECK",
            "Users and services should receive only the permissions they require.",
        ),
        SecurityCheck(
            "SSH root login",
            "CHECK",
            "Prefer administrative access through controlled accounts and privilege escalation.",
        ),
        SecurityCheck(
            "SSH authentication",
            "CHECK",
            "Use strong authentication and disable unnecessary authentication mechanisms.",
        ),
        SecurityCheck(
            "Software updates",
            "CHECK",
            "Security fixes depend on maintaining supported and updated packages.",
        ),
        SecurityCheck(
            "Firewall",
            "CHECK",
            "Restrict inbound network access to required ports and trusted sources.",
        ),
        SecurityCheck(
            "Logging",
            "CHECK",
            "Important authentication and service events should be observable.",
        ),
        SecurityCheck(
            "Backups",
            "CHECK",
            "Backups are useful only when restoration has been tested.",
        ),
        SecurityCheck(
            "Secrets",
            "CHECK",
            "Passwords, private keys, and tokens should not be stored in ordinary source files.",
        ),
    ]


def show_security_baseline() -> None:
    print("\nSECURITY BASELINE")
    print("=" * 80)

    for check in security_baseline():
        print(f"[{check.status}] {check.name}")
        print(f"       {check.explanation}")


# ---------------------------------------------------------------------------
# 16. Linux administration workflow
# ---------------------------------------------------------------------------

def explain_server_lifecycle() -> None:
    print("\nSERVER ADMINISTRATION LIFECYCLE")
    print("=" * 80)

    phases = [
        ("1. Provision", "Install or provision the operating system and establish network access."),
        ("2. Update", "Apply supported security and software updates."),
        ("3. Identity", "Create users, groups, administrative access, and authentication policies."),
        ("4. Secure SSH", "Restrict remote administration and validate SSH configuration."),
        ("5. Permissions", "Apply ownership and least-privilege permissions."),
        ("6. Services", "Install, configure, enable, inspect, and monitor required services."),
        ("7. Network", "Control listening ports, firewall rules, DNS, and routing."),
        ("8. Automation", "Turn repeatable administrative tasks into reproducible procedures."),
        ("9. Observe", "Monitor logs, processes, storage, resources, and service health."),
        ("10. Recover", "Maintain backups, test restoration, and document recovery procedures."),
    ]

    for phase, description in phases:
        print(f"{phase:<14} {description}")


# ---------------------------------------------------------------------------
# 17. Resource monitoring
# ---------------------------------------------------------------------------

def show_memory_information() -> None:
    print("\nMEMORY INFORMATION")
    print("=" * 80)

    meminfo = Path("/proc/meminfo")

    if not meminfo.exists():
        print("/proc/meminfo is unavailable on this operating system.")
        return

    values: dict[str, int] = {}

    try:
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^(\w+):\s+(\d+)\s+kB$", line)
            if match:
                values[match.group(1)] = int(match.group(2))
    except OSError as exc:
        print(f"Unable to read memory information: {exc}")
        return

    for key in ("MemTotal", "MemFree", "MemAvailable", "SwapTotal", "SwapFree"):
        if key in values:
            print(f"{key:<18}: {values[key] / 1024:.2f} MiB")


# ---------------------------------------------------------------------------
# 18. Demonstration test suite
# ---------------------------------------------------------------------------

def run_self_tests() -> None:
    print("\nSELF TESTS")
    print("=" * 80)

    tests: list[tuple[str, Callable[[], None]]] = []

    def test_permission_values() -> None:
        assert _permission_value("rwx") == 7
        assert _permission_value("r-x") == 5
        assert _permission_value("---") == 0

    def test_validation() -> None:
        assert validate_port(22).passed
        assert not validate_port(0).passed
        assert validate_username("deploy_user").passed
        assert not validate_username("Bad User").passed
        assert validate_hostname("server01.example.com").passed
        assert not validate_hostname("bad host").passed

    def test_ssh_audit() -> None:
        config = """
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication no
PermitEmptyPasswords yes
MaxAuthTries 20
"""
        findings = audit_ssh_configuration(config)
        assert len(findings) == 5

    def test_idempotency() -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "application"
            file_path = directory / "config.ini"

            assert ensure_directory(directory)
            assert not ensure_directory(directory)

            assert ensure_text_file(file_path, "enabled=true\n")
            assert not ensure_text_file(file_path, "enabled=true\n")

    tests.extend(
        [
            ("permission conversion", test_permission_values),
            ("input validation", test_validation),
            ("SSH audit", test_ssh_audit),
            ("idempotent configuration", test_idempotency),
        ]
    )

    passed = 0

    for name, test in tests:
        try:
            test()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {name}: {exc}")

    print(f"\n{passed}/{len(tests)} tests passed.")


# ---------------------------------------------------------------------------
# 19. Full educational laboratory
# ---------------------------------------------------------------------------

def run_lab() -> None:
    print("=" * 80)
    print("LINUX ADMINISTRATION EDUCATIONAL LABORATORY")
    print("=" * 80)
    print(
        "\nThis laboratory is non-destructive. Configuration files and permission "
        "experiments are created inside a temporary directory."
    )

    print_system_information()
    explain_server_lifecycle()
    demonstrate_permissions(Path(tempfile.mkdtemp(prefix="linux-admin-lab-")))
    demonstrate_ssh_audit()
    demonstrate_validation()

    with tempfile.TemporaryDirectory(prefix="linux-admin-automation-") as temporary:
        lab = Path(temporary)
        demonstrate_idempotent_automation(lab)
        demonstrate_backup(lab)
        demonstrate_logging(lab)

        findings = audit_directory_permissions(lab)

        print("\nLABORATORY PERMISSION AUDIT")
        print("=" * 80)

        if findings:
            for finding in findings:
                print(
                    f"{finding.severity:<8} "
                    f"{finding.permissions:<10} "
                    f"{finding.path:<60} "
                    f"{finding.issue}"
                )
        else:
            print("No world-writable objects were found in the lab.")

    show_disk_usage("/")
    show_memory_information()
    show_processes()

    if platform.system() == "Linux":
        show_users()
        show_groups()
        show_service_status("ssh")
    else:
        print("\nLinux-specific account and service inspection was skipped because")
        print("the current operating system is not Linux.")

    show_security_baseline()
    run_self_tests()

    print("\nLAB COMPLETE")
    print("=" * 80)


# ---------------------------------------------------------------------------
# 20. Command-line interface
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Educational Linux administration toolkit."
    )

    parser.add_argument(
        "--users",
        action="store_true",
        help="Display local account information.",
    )
    parser.add_argument(
        "--groups",
        action="store_true",
        help="Display local group information.",
    )
    parser.add_argument(
        "--processes",
        action="store_true",
        help="Display a process snapshot.",
    )
    parser.add_argument(
        "--disk",
        default="/",
        help="Display disk information for a path.",
    )
    parser.add_argument(
        "--service",
        help="Inspect whether a service is active.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the built-in tests.",
    )
    parser.add_argument(
        "--lab",
        action="store_true",
        help="Run the complete educational laboratory.",
    )

    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.lab or not any(
        [
            args.users,
            args.groups,
            args.processes,
            args.service,
            args.self_test,
        ]
    ):
        run_lab()
        return 0

    if args.users:
        show_users()

    if args.groups:
        show_groups()

    if args.processes:
        show_processes()

    if args.service:
        show_service_status(args.service)

    if args.disk:
        show_disk_usage(args.disk)

    if args.self_test:
        run_self_tests()

    return 0


if __name__ == "__main__":
    sys.exit(main())
