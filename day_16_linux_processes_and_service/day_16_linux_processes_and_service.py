```python
#!/usr/bin/env python3
"""
Linux Processes and Services
============================

A self-contained study program covering:

- Processes and process IDs
- Parent/child relationships
- Process states
- /proc
- ps and process inspection
- CPU and memory measurements
- Signals
- Graceful and forced termination
- Process groups and sessions
- Services and daemons
- systemd concepts
- systemctl
- Service lifecycle management
- Dependencies and targets
- Logging with journald
- Resource limits
- Privilege and security considerations
- Monitoring and troubleshooting
- A practical service-monitoring simulation

The examples are designed to run on Linux. Some operating-system-specific
sections detect unsupported environments and explain what would normally
happen rather than failing unnecessarily.

Run:
    python3 linux_processes_services.py
"""

from __future__ import annotations

import errno
import os
import platform
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def heading(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subheading(title: str) -> None:
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def run_command(
    command: list[str],
    *,
    timeout: float = 5.0,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command safely and return its completed-process object."""
    try:
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=check,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            command,
            returncode=127,
            stdout="",
            stderr=f"Command not found: {command[0]}",
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=f"Command timed out after {timeout} seconds.",
        )


def print_command_result(result: subprocess.CompletedProcess[str]) -> None:
    """Display command output without hiding errors."""
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print("[stderr]")
        print(result.stderr.rstrip())
    print(f"[exit status] {result.returncode}")


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def require_linux() -> bool:
    if not is_linux():
        print(
            f"This demonstration requires Linux. "
            f"Detected platform: {platform.system()}"
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Fundamental process concepts
# ---------------------------------------------------------------------------

def explain_process_model() -> None:
    heading("1. Processes: the fundamental model")

    print(
        textwrap.dedent(
            """
            A process is a running instance of a program.

            A program is passive data stored on disk. A process is the active
            execution state created when the operating system loads a program.

            A process normally has:
              * a process ID (PID)
              * a parent process ID (PPID)
              * an address space
              * CPU register state
              * open file descriptors
              * environment variables
              * credentials
              * scheduling information
              * signal dispositions
              * resource limits

            Linux represents processes through kernel data structures and
            exposes much of their observable state through /proc.
            """
        ).strip()
    )

    if not is_linux():
        return

    print(f"\nCurrent PID : {os.getpid()}")
    print(f"Parent PID  : {os.getppid()}")
    print(f"User ID     : {os.getuid()}")
    print(f"Group ID    : {os.getgid()}")
    print(f"Process group ID: {os.getpgrp()}")
    print(f"Session ID  : {os.getsid(0)}")


# ---------------------------------------------------------------------------
# /proc inspection
# ---------------------------------------------------------------------------

def read_proc_file(pid: int, filename: str) -> Optional[str]:
    """Read a procfs file if available."""
    path = Path("/proc") / str(pid) / filename
    try:
        return path.read_text(errors="replace")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None


def parse_proc_status(pid: int) -> dict[str, str]:
    """Parse selected key/value information from /proc/<pid>/status."""
    text = read_proc_file(pid, "status")
    if text is None:
        return {}

    values: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def demonstrate_procfs() -> None:
    heading("2. Inspecting a process through /proc")

    if not require_linux():
        return

    pid = os.getpid()
    print(f"Inspecting PID {pid}")

    status = parse_proc_status(pid)

    interesting_keys = [
        "Name",
        "State",
        "Pid",
        "PPid",
        "Uid",
        "Gid",
        "Threads",
        "VmSize",
        "VmRSS",
        "VmPeak",
        "FDSize",
    ]

    for key in interesting_keys:
        if key in status:
            print(f"{key:12}: {status[key]}")

    cmdline = read_proc_file(pid, "cmdline")
    if cmdline is not None:
        print("Cmdline     :", cmdline.replace("\x00", " ").strip())

    environ = read_proc_file(pid, "environ")
    if environ is not None:
        variables = environ.split("\x00")
        print("Environment variables visible:", len([x for x in variables if x]))

    fd_directory = Path("/proc") / str(pid) / "fd"
    try:
        descriptors = list(fd_directory.iterdir())
        print("Open file descriptors:", len(descriptors))
    except PermissionError:
        print("Open file descriptors: permission denied")


# ---------------------------------------------------------------------------
# ps
# ---------------------------------------------------------------------------

def demonstrate_ps() -> None:
    heading("3. Process inspection with ps")

    if not require_linux():
        return

    examples = [
        ["ps", "aux"],
        ["ps", "-ef"],
        ["ps", "-eo", "pid,ppid,user,stat,%cpu,%mem,etime,comm", "--sort=-%cpu"],
    ]

    for command in examples:
        subheading("$ " + " ".join(command))
        result = run_command(command, timeout=5)
        if result.returncode == 0:
            # Keep terminal output manageable.
            lines = result.stdout.splitlines()
            for line in lines[:20]:
                print(line)
            if len(lines) > 20:
                print(f"... {len(lines) - 20} additional lines omitted.")
        else:
            print_command_result(result)

    print(
        """
Common ps concepts:
  PID   Process identifier.
  PPID  Parent process identifier.
  STAT  Process state and additional flags.
  %CPU  Recent CPU utilization estimate.
  %MEM  Percentage of physical memory.
  TTY   Controlling terminal.
  TIME  Accumulated CPU time.
  CMD   Command used to start the process.

Useful forms:
  ps
  ps aux
  ps -ef
  ps -p <PID> -o pid,ppid,stat,cmd
  ps --forest
  ps -eo pid,ppid,user,stat,%cpu,%mem,cmd
"""
    )


# ---------------------------------------------------------------------------
# top
# ---------------------------------------------------------------------------

def demonstrate_top() -> None:
    heading("4. Real-time process monitoring with top")

    if not require_linux():
        return

    result = run_command(
        ["top", "-b", "-n", "1", "-w", "120"],
        timeout=5,
    )

    if result.returncode != 0:
        print_command_result(result)
        return

    lines = result.stdout.splitlines()
    for line in lines[:25]:
        print(line)

    print(
        """
top is interactive when run normally.

Important concepts:
  * load average
  * total, used, free and available memory
  * CPU user/system/idle time
  * process CPU consumption
  * process memory consumption
  * process states
  * process priority and nice value

For a production system, a single snapshot is rarely sufficient. Trends,
historical metrics and workload context are needed before diagnosing a
performance problem.
"""
    )


# ---------------------------------------------------------------------------
# Process states
# ---------------------------------------------------------------------------

def explain_process_states() -> None:
    heading("5. Linux process states")

    states = {
        "R": "Running or runnable.",
        "S": "Interruptible sleeping.",
        "D": "Uninterruptible sleep, commonly waiting on I/O.",
        "T": "Stopped, for example by job-control or a stop signal.",
        "Z": "Zombie: execution ended but the parent has not collected status.",
        "I": "Idle kernel thread state in applicable contexts.",
    }

    for code, meaning in states.items():
        print(f"{code:2}  {meaning}")

    print(
        """
A zombie is not a process consuming normal CPU execution. Its process-table
entry remains so that the parent can retrieve the child's termination status
using wait-related system calls.

A large number of zombies usually indicates a parent-process lifecycle bug,
not simply a need to kill the zombies directly. The parent must normally
reap them, or the process hierarchy must be corrected.
"""
    )


# ---------------------------------------------------------------------------
# Process creation
# ---------------------------------------------------------------------------

def child_process_example() -> None:
    heading("6. Creating and observing a child process")

    if not require_linux():
        return

    code = (
        "import os, time; "
        "print(f'child PID={os.getpid()} PPID={os.getppid()}', flush=True); "
        "time.sleep(2)"
    )

    process = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    print(f"Parent created child PID: {process.pid}")

    # Before wait(), the parent has not yet collected the child's exit status.
    stdout, stderr = process.communicate(timeout=5)

    print("Child output:")
    print(stdout.rstrip())

    if stderr.strip():
        print("Child error:")
        print(stderr.rstrip())

    print(f"Child return code: {process.returncode}")


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def explain_signals() -> None:
    heading("7. Signals")

    signal_descriptions = [
        ("SIGTERM", "15", "Polite termination request; applications can handle it."),
        ("SIGKILL", "9", "Immediate termination; cannot be caught or ignored."),
        ("SIGINT", "2", "Interrupt, commonly generated by Ctrl+C."),
        ("SIGHUP", "1", "Hangup; traditionally terminal related and often used to request reloads."),
        ("SIGSTOP", "19 on many architectures", "Stop execution; cannot be caught."),
        ("SIGCONT", "18 on many architectures", "Continue a stopped process."),
        ("SIGCHLD", "17 on many architectures", "Child state changed; relevant to parent process management."),
    ]

    for name, number, description in signal_descriptions:
        print(f"{name:8} {number:>3}  {description}")

    print(
        """
SIGTERM should normally be attempted before SIGKILL. A well-designed
application can use SIGTERM to stop accepting new work, finish safe work,
close resources and exit.

SIGKILL is a kernel-enforced termination mechanism. Because the target
cannot execute cleanup code, it should not be the normal graceful-shutdown
mechanism.
"""
    )


def graceful_signal_example() -> None:
    heading("8. Graceful termination using SIGTERM")

    if not require_linux():
        return

    worker_code = r"""
import os
import signal
import time

running = True

def handle_sigterm(signum, frame):
    global running
    print(f"received signal {signum}", flush=True)
    running = False

signal.signal(signal.SIGTERM, handle_sigterm)

print(f"worker PID={os.getpid()}", flush=True)

while running:
    time.sleep(0.2)

print("cleanup completed; exiting", flush=True)
"""

    worker = subprocess.Popen(
        [sys.executable, "-c", worker_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    first_line = worker.stdout.readline().strip() if worker.stdout else ""
    print(first_line)

    print(f"Sending SIGTERM to PID {worker.pid}")
    os.kill(worker.pid, signal.SIGTERM)

    stdout, stderr = worker.communicate(timeout=5)

    if stdout.strip():
        print(stdout.rstrip())

    if stderr.strip():
        print(stderr.rstrip())

    print("Return code:", worker.returncode)


# ---------------------------------------------------------------------------
# Process groups
# ---------------------------------------------------------------------------

def process_group_example() -> None:
    heading("9. Process groups and sessions")

    if not require_linux():
        return

    print("Current PID :", os.getpid())
    print("Process PGID:", os.getpgrp())
    print("Session ID  :", os.getsid(0))

    print(
        """
A process group is a collection of related processes. Signals can be sent
to a process group, which is useful for controlling a complete workload.

A session contains one or more process groups and can be associated with a
controlling terminal.

This distinction becomes important when applications create subprocess
trees, terminal jobs, containers, supervisors and service workers.
"""
    )


# ---------------------------------------------------------------------------
# Resource measurement
# ---------------------------------------------------------------------------

def cpu_time_measurement() -> None:
    heading("10. Measuring process CPU time")

    start_wall = time.perf_counter()
    start_cpu = time.process_time()

    total = 0
    for number in range(1, 1_000_001):
        total += number * number

    elapsed_wall = time.perf_counter() - start_wall
    elapsed_cpu = time.process_time() - start_cpu

    print("Calculation result:", total)
    print(f"Wall-clock time   : {elapsed_wall:.6f} seconds")
    print(f"Process CPU time  : {elapsed_cpu:.6f} seconds")

    print(
        """
Wall-clock time measures elapsed real time. CPU process time measures CPU
time consumed by the current process.

A workload blocked on I/O may have relatively high wall-clock time but low
CPU time. A CPU-bound loop usually consumes substantial CPU time.
"""
    )


# ---------------------------------------------------------------------------
# Subprocess lifecycle and failures
# ---------------------------------------------------------------------------

def subprocess_failure_example() -> None:
    heading("11. Subprocess lifecycle and failure handling")

    if not require_linux():
        return

    cases = [
        ["sh", "-c", "printf 'successful command\\n'"],
        ["sh", "-c", "printf 'failure on stderr\\n' >&2; exit 7"],
    ]

    for command in cases:
        print("\nCommand:", command)
        result = run_command(command)
        print("Return code:", result.returncode)
        print("stdout:", result.stdout.strip())
        print("stderr:", result.stderr.strip())

    print(
        """
A non-zero exit status is application-level information. It does not
necessarily mean the operating system could not execute the program.

When invoking external commands:
  * validate arguments
  * avoid shell=True unless shell interpretation is required
  * capture output when appropriate
  * enforce timeouts
  * handle missing executables
  * inspect return codes
  * avoid leaking sensitive command arguments
"""
    )


# ---------------------------------------------------------------------------
# Service concepts
# ---------------------------------------------------------------------------

def explain_services_and_daemons() -> None:
    heading("12. Services and daemons")

    print(
        textwrap.dedent(
            """
            A service is a long-running function provided by a system or
            application.

            A daemon is a background process designed to provide such a
            function without requiring an interactive terminal.

            Examples include:
              * SSH server
              * web server
              * database server
              * scheduler
              * logging service
              * network service

            Modern Linux distributions commonly use systemd as the system
            and service manager.

            A systemd service unit describes how a service is started,
            stopped, supervised and integrated with the boot and dependency
            model.
            """
        ).strip()
    )


# ---------------------------------------------------------------------------
# systemctl
# ---------------------------------------------------------------------------

def demonstrate_systemctl() -> None:
    heading("13. systemctl")

    if not require_linux():
        return

    result = run_command(["systemctl", "--version"])
    if result.returncode != 0:
        print(
            "systemctl is not available in this environment. "
            "This can occur in containers or non-systemd environments."
        )
        print_command_result(result)
        return

    print("systemctl version information:")
    print(result.stdout.strip())

    commands = [
        ["systemctl", "is-system-running"],
        ["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend"],
    ]

    for command in commands:
        subheading("$ " + " ".join(command))
        result = run_command(command, timeout=5)
        if result.stdout.strip():
            lines = result.stdout.splitlines()
            for line in lines[:20]:
                print(line)
            if len(lines) > 20:
                print(f"... {len(lines) - 20} additional lines omitted.")
        elif result.stderr.strip():
            print(result.stderr.rstrip())

    print(
        """
Common administrative commands:

  systemctl status SERVICE
  systemctl start SERVICE
  systemctl stop SERVICE
  systemctl restart SERVICE
  systemctl reload SERVICE
  systemctl enable SERVICE
  systemctl disable SERVICE
  systemctl is-active SERVICE
  systemctl is-enabled SERVICE
  systemctl list-units --type=service
  systemctl list-unit-files --type=service

Commands that modify system services normally require appropriate
privileges, often through sudo.
"""
    )


# ---------------------------------------------------------------------------
# Unit files
# ---------------------------------------------------------------------------

def show_unit_file_structure() -> None:
    heading("14. Anatomy of a systemd service unit")

    unit = """
[Unit]
Description=Example Application Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=example
Group=example
ExecStart=/opt/example/bin/server
Restart=on-failure
RestartSec=5
Environment=APP_ENV=production

[Install]
WantedBy=multi-user.target
""".strip()

    print(unit)

    print(
        """
[Unit] describes identity and relationships.

[Service] defines execution behavior.

[Install] describes how the unit participates in enablement targets.

Important directives include:
  ExecStart
  ExecStop
  User
  Group
  WorkingDirectory
  Environment
  EnvironmentFile
  Restart
  RestartSec
  TimeoutStartSec
  TimeoutStopSec
  Type

A service should run with the least privilege required to perform its job.
"""
    )


# ---------------------------------------------------------------------------
# Service lifecycle
# ---------------------------------------------------------------------------

@dataclass
class ServiceObservation:
    name: str
    active: str
    enabled: str
    load: str
    substate: str


def inspect_service(name: str) -> Optional[ServiceObservation]:
    """Collect selected service state using systemctl show."""
    if not is_linux():
        return None

    result = run_command(
        [
            "systemctl",
            "show",
            name,
            "--no-pager",
            "--property=LoadState,ActiveState,SubState,UnitFileState",
        ],
        timeout=5,
    )

    if result.returncode != 0:
        return None

    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    return ServiceObservation(
        name=name,
        active=values.get("ActiveState", "unknown"),
        enabled=values.get("UnitFileState", "unknown"),
        load=values.get("LoadState", "unknown"),
        substate=values.get("SubState", "unknown"),
    )


def demonstrate_service_observation() -> None:
    heading("15. Service state observation")

    if not require_linux():
        return

    candidate_services = ["ssh.service", "sshd.service", "cron.service", "systemd-journald.service"]

    found = False
    for service in candidate_services:
        observation = inspect_service(service)
        if observation is None:
            continue

        found = True
        print(
            f"{observation.name:32} "
            f"load={observation.load:10} "
            f"active={observation.active:10} "
            f"sub={observation.substate:12} "
            f"enabled={observation.enabled}"
        )

    if not found:
        print("No sample service from the candidate list was available.")


# ---------------------------------------------------------------------------
# Journald
# ---------------------------------------------------------------------------

def demonstrate_journalctl() -> None:
    heading("16. Service logs and journalctl")

    if not require_linux():
        return

    result = run_command(
        ["journalctl", "-n", "15", "--no-pager"],
        timeout=5,
    )

    if result.returncode == 0:
        lines = result.stdout.splitlines()
        for line in lines[-15:]:
            print(line)
    else:
        print(
            "journalctl could not be queried. "
            "This may happen in restricted containers."
        )
        if result.stderr.strip():
            print(result.stderr.rstrip())

    print(
        """
Useful journalctl forms:

  journalctl -u SERVICE
  journalctl -u SERVICE -n 100
  journalctl -u SERVICE -f
  journalctl --since "1 hour ago"
  journalctl -p warning
  journalctl -b

The journal provides structured system and service logs. Access can depend
on user privileges and distribution configuration.
"""
    )


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def explain_security() -> None:
    heading("17. Security considerations")

    principles = [
        "Run services as dedicated non-root users whenever possible.",
        "Use least privilege for files, directories, devices and network access.",
        "Do not place secrets directly in command-line arguments.",
        "Protect service unit files from unauthorized modification.",
        "Validate external input before passing it to subprocesses.",
        "Prefer direct argument arrays over shell command strings.",
        "Use systemd sandboxing controls where appropriate.",
        "Restrict network exposure with appropriate firewall and service configuration.",
        "Review service dependencies and startup behavior.",
        "Monitor unexpected process creation and privilege changes.",
    ]

    for number, principle in enumerate(principles, 1):
        print(f"{number:2}. {principle}")

    print(
        """
A particularly important distinction is SIGTERM versus SIGKILL. A program
that receives SIGTERM can execute its signal handler, while SIGKILL is
enforced by the kernel and prevents application cleanup.

Security controls should be selected according to the service's actual
requirements. Excessive restrictions can break legitimate functionality,
while insufficient restrictions increase attack impact.
"""
    )


# ---------------------------------------------------------------------------
# Service-monitoring application
# ---------------------------------------------------------------------------

@dataclass
class ProcessRecord:
    pid: int
    ppid: int
    name: str
    state: str
    memory_kb: int
    threads: int


def collect_process_records(limit: int = 30) -> list[ProcessRecord]:
    """Build a small process inventory directly from /proc."""
    if not is_linux():
        return []

    records: list[ProcessRecord] = []

    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue

        pid = int(entry.name)
        status = parse_proc_status(pid)

        if not status:
            continue

        try:
            state_text = status.get("State", "")
            state = state_text[:1] if state_text else "?"
            records.append(
                ProcessRecord(
                    pid=pid,
                    ppid=int(status.get("PPid", "0")),
                    name=status.get("Name", "?"),
                    state=state,
                    memory_kb=int(status.get("VmRSS", "0").split()[0]),
                    threads=int(status.get("Threads", "0")),
                )
            )
        except ValueError:
            continue

    records.sort(key=lambda item: item.memory_kb, reverse=True)
    return records[:limit]


def process_monitor_case_study() -> None:
    heading("18. Mini process-monitoring case study")

    if not require_linux():
        return

    records = collect_process_records(20)

    print(
        f"{'PID':>7} {'PPID':>7} {'STATE':>5} "
        f"{'RSS KiB':>10} {'THREADS':>8} NAME"
    )
    print("-" * 70)

    for record in records:
        print(
            f"{record.pid:7} "
            f"{record.ppid:7} "
            f"{record.state:>5} "
            f"{record.memory_kb:10} "
            f"{record.threads:8} "
            f"{record.name[:30]}"
        )

    print(
        """
This demonstrates an important systems-programming pattern: the application
can collect operating-system state from a standard kernel interface and
convert it into structured records.

The implementation intentionally reads /proc instead of parsing human-oriented
terminal output. Structured interfaces are usually less fragile than relying
on column formatting intended for interactive display.
"""
    )


# ---------------------------------------------------------------------------
# Service health model
# ---------------------------------------------------------------------------

@dataclass
class HealthResult:
    healthy: bool
    reasons: list[str]


def evaluate_service_health(
    *,
    active_state: str,
    sub_state: str,
    restart_count: int,
    memory_kb: int,
    memory_limit_kb: int,
) -> HealthResult:
    """Apply explicit, deterministic service-health rules."""
    reasons: list[str] = []

    if active_state != "active":
        reasons.append(f"service is not active: {active_state}")

    if sub_state not in {"running", "listening", "exited"}:
        reasons.append(f"unexpected substate: {sub_state}")

    if restart_count > 5:
        reasons.append("restart count exceeds configured observation threshold")

    if memory_kb > memory_limit_kb:
        reasons.append(
            f"memory usage {memory_kb} KiB exceeds "
            f"limit {memory_limit_kb} KiB"
        )

    return HealthResult(healthy=not reasons, reasons=reasons)


def health_evaluation_examples() -> None:
    heading("19. Deterministic service-health evaluation")

    examples = [
        {
            "active_state": "active",
            "sub_state": "running",
            "restart_count": 0,
            "memory_kb": 100_000,
            "memory_limit_kb": 500_000,
        },
        {
            "active_state": "failed",
            "sub_state": "failed",
            "restart_count": 9,
            "memory_kb": 100_000,
            "memory_limit_kb": 500_000,
        },
        {
            "active_state": "active",
            "sub_state": "running",
            "restart_count": 1,
            "memory_kb": 700_000,
            "memory_limit_kb": 500_000,
        },
    ]

    for index, values in enumerate(examples, 1):
        result = evaluate_service_health(**values)
        print(f"Case {index}: healthy={result.healthy}")
        for reason in result.reasons:
            print("  -", reason)


# ---------------------------------------------------------------------------
# Temporary worker and timeout handling
# ---------------------------------------------------------------------------

def timeout_case() -> None:
    heading("20. Handling an unresponsive child")

    if not require_linux():
        return

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"]
    )

    print("Started PID:", child.pid)

    try:
        child.wait(timeout=0.5)
        print("Child exited naturally:", child.returncode)
    except subprocess.TimeoutExpired:
        print("Child did not finish within the deadline.")
        print("Sending SIGTERM...")
        child.terminate()

        try:
            child.wait(timeout=2)
            print("Child terminated gracefully:", child.returncode)
        except subprocess.TimeoutExpired:
            print("SIGTERM did not stop the process.")
            print("Sending SIGKILL...")
            child.kill()
            child.wait()
            print("Child forcibly terminated:", child.returncode)


# ---------------------------------------------------------------------------
# Configuration and validation
# ---------------------------------------------------------------------------

def validate_service_name(service_name: str) -> bool:
    """
    Validate a conservative systemd unit name.

    This is intentionally stricter than systemd's complete unit-name grammar
    because the function is an educational example for user-controlled input.
    """
    if not service_name:
        return False

    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "._@-"
    )

    return (
        len(service_name) <= 255
        and all(character in allowed for character in service_name)
        and "/" not in service_name
        and "\\" not in service_name
        and ".." not in service_name
    )


def validation_examples() -> None:
    heading("21. Input validation for administrative tooling")

    samples = [
        "ssh.service",
        "cron.service",
        "",
        "../../etc/passwd",
        "service name",
        "my-service@instance.service",
    ]

    for sample in samples:
        print(f"{sample!r:35} valid={validate_service_name(sample)}")

    print(
        """
Validation is not a substitute for authorization. A syntactically valid
service name can still be a service the caller is not permitted to inspect
or control.

Administrative applications should separate:
  1. input validation,
  2. authorization,
  3. command execution,
  4. error handling,
  5. audit logging.
"""
    )


# ---------------------------------------------------------------------------
# Performance concepts
# ---------------------------------------------------------------------------

def performance_considerations() -> None:
    heading("22. Performance considerations")

    print(
        """
Process monitoring has its own resource cost.

Potential sources of overhead:
  * repeatedly scanning /proc
  * starting external ps/systemctl processes
  * collecting too much information too frequently
  * parsing large logs
  * polling instead of using event-driven mechanisms
  * excessive logging

For lightweight monitoring, direct /proc reads can avoid repeatedly spawning
external commands. For service lifecycle management, systemd's native APIs
and commands provide semantics that should not be recreated casually.

Sampling interval is a design parameter. A one-second monitor provides more
detail but consumes more resources than a one-minute monitor.

For large-scale monitoring, process-level observation is normally only one
layer. Metrics, logs, traces, service health checks and system resource
measurements should be considered together.
"""
    )


# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

def run_internal_tests() -> None:
    heading("23. Internal tests")

    assert validate_service_name("ssh.service")
    assert validate_service_name("worker@1.service")
    assert not validate_service_name("")
    assert not validate_service_name("../../passwd")
    assert not validate_service_name("service name")

    healthy = evaluate_service_health(
        active_state="active",
        sub_state="running",
        restart_count=0,
        memory_kb=100,
        memory_limit_kb=1000,
    )
    assert healthy.healthy

    unhealthy = evaluate_service_health(
        active_state="failed",
        sub_state="failed",
        restart_count=0,
        memory_kb=100,
        memory_limit_kb=1000,
    )
    assert not unhealthy.healthy
    assert unhealthy.reasons

    print("All internal tests passed.")


# ---------------------------------------------------------------------------
# Troubleshooting guide
# ---------------------------------------------------------------------------

def troubleshooting_guide() -> None:
    heading("24. Troubleshooting workflow")

    print(
        """
When a service is not working, avoid changing several things at once.

A structured workflow is:

1. Identify the service:
     systemctl status example.service

2. Determine whether systemd loaded the unit:
     systemctl show example.service

3. Read recent service logs:
     journalctl -u example.service -n 100 --no-pager

4. Check the service process:
     ps -ef | grep example

5. Check CPU and memory:
     top
     ps -p PID -o pid,ppid,stat,%cpu,%mem,cmd

6. Inspect dependencies:
     systemctl list-dependencies example.service

7. Check listening sockets when networking is involved:
     ss -lntup

8. Check permissions, users and paths.

9. Validate configuration before restarting.

10. Make one controlled change and observe the result.

Common symptoms:

Service fails immediately
    Inspect ExecStart, permissions, configuration and journal logs.

Service repeatedly restarts
    Inspect the application exit code, Restart policy and logs.

High CPU
    Identify the process and determine whether the workload is expected.

High memory
    Compare RSS over time and determine whether growth is intentional.

Zombie processes
    Investigate parent-process child-reaping behavior.

Service is active but unavailable
    Check sockets, dependencies, firewall rules, bind addresses and
    application-level health.

systemctl does not work
    The environment may not be booted with systemd, especially inside a
    minimal container.
"""
    )


# ---------------------------------------------------------------------------
# Main program
# ---------------------------------------------------------------------------

def main() -> None:
    print("Linux Processes and Services")
    print("============================")
    print("Python:", sys.version.split()[0])
    print("Platform:", platform.platform())

    explain_process_model()
    demonstrate_procfs()
    demonstrate_ps()
    demonstrate_top()
    explain_process_states()
    child_process_example()
    explain_signals()
    graceful_signal_example()
    process_group_example()
    cpu_time_measurement()
    subprocess_failure_example()
    explain_services_and_daemons()
    demonstrate_systemctl()
    show_unit_file_structure()
    demonstrate_service_observation()
    demonstrate_journalctl()
    explain_security()
    process_monitor_case_study()
    health_evaluation_examples()
    timeout_case()
    validation_examples()
    performance_considerations()
    run_internal_tests()
    troubleshooting_guide()

    heading("25. End of executable study")
    print(
        "The program demonstrated process inspection, lifecycle control, "
        "signals, service management, monitoring, security and troubleshooting."
    )


if __name__ == "__main__":
    main()
```
