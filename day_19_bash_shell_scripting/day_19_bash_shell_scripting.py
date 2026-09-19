#!/usr/bin/env python3
"""
Bash Shell Scripting Study Companion
====================================

This Python program models and demonstrates the major ideas used in Bash shell
scripting:

- Variables and environment variables
- Quoting and expansion concepts
- Conditions and comparisons
- Loops and iteration
- Functions
- Positional arguments and command-line interfaces
- Arrays and associative mappings
- Input validation
- Exit status and error handling
- Pipelines and command-oriented thinking
- Automation workflows
- Logging
- Configuration
- Dry-run behavior
- File-system operations
- Process-oriented automation
- Dependency checks
- Retry logic
- Idempotency
- Security considerations
- Testing concepts
- Production-oriented script design

The program does not execute arbitrary shell commands. Instead, it implements
safe Python equivalents and simulators so that the Bash concepts can be studied
without accidentally modifying the host system.

Run:
    python bash_shell_scripting_study.py

The program accepts optional demonstration arguments:
    python bash_shell_scripting_study.py --section variables
    python bash_shell_scripting_study.py --section conditions
    python bash_shell_scripting_study.py --section loops
    python bash_shell_scripting_study.py --section functions
    python bash_shell_scripting_study.py --section arguments
    python bash_shell_scripting_study.py --section automation
    python bash_shell_scripting_study.py --all
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_title(title: str) -> None:
    """Print a readable section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_subtitle(title: str) -> None:
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def print_key_value(key: str, value: object) -> None:
    print(f"{key:<28}: {value}")


# ---------------------------------------------------------------------------
# Bash syntax reference
# ---------------------------------------------------------------------------

BASH_SYNTAX_REFERENCE = {
    "variable_assignment": "name=value",
    "variable_read": "$name or ${name}",
    "quoted_read": '"$name"',
    "command_substitution": "$(command)",
    "arithmetic_expansion": "$((expression))",
    "condition": 'if [[ "$value" == "expected" ]]; then ... fi',
    "for_loop": 'for item in "${items[@]}"; do ... done',
    "while_loop": 'while condition; do ... done',
    "function": 'function_name() { ... }',
    "argument": "$1, $2, ...",
    "all_arguments": '"$@"',
    "argument_count": "$#",
    "script_name": "$0",
    "exit_status": "$?",
    "exit": "exit N",
}


def demonstrate_bash_syntax() -> None:
    print_title("Bash syntax map")

    for concept, syntax in BASH_SYNTAX_REFERENCE.items():
        print_key_value(concept, syntax)

    print(
        """
Important distinction:
Bash variables are assigned without spaces around '='. The expression
'count=10' is assignment, while 'count = 10' is parsed as a command.

Bash normally performs word splitting and pathname expansion on unquoted
expansions. Double quotes are therefore central to reliable shell scripting.

Prefer:
    "$filename"
    "${array[@]}"
    "$@"

rather than unquoted expansions when preserving argument boundaries matters.
"""
    )


# ---------------------------------------------------------------------------
# Variables and expansion
# ---------------------------------------------------------------------------

def demonstrate_variables() -> None:
    print_title("1. Variables")

    # Bash variables are dynamically typed. The same conceptual variable may
    # contain text or a number. Arithmetic contexts interpret numeric strings.
    username = "atul"
    project_name = "automation-lab"
    file_count = 7
    enabled = True

    print_key_value("username", username)
    print_key_value("project_name", project_name)
    print_key_value("file_count", file_count)
    print_key_value("enabled", enabled)

    # Bash-like default-value expansion:
    # ${VAR:-default} means use default when VAR is unset or empty.
    configured_port = ""
    effective_port = configured_port or "8080"
    print_key_value("effective_port", effective_port)

    # ${VAR:=default} assigns the default as well.
    retry_limit: Optional[int] = None
    if retry_limit is None:
        retry_limit = 3
    print_key_value("retry_limit", retry_limit)

    # Environment variables are inherited by child processes.
    print_subtitle("Environment variables")

    home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "unknown")
    path_value = os.environ.get("PATH", "")

    print_key_value("home", home)
    print_key_value("PATH entries", len(path_value.split(os.pathsep)))

    # Read-only variables in Bash are similar in intent to constants.
    readonly_configuration = {
        "APP_NAME": "automation-lab",
        "LOG_LEVEL": "INFO",
        "MAX_RETRIES": 3,
    }

    print("\nConceptual readonly configuration:")
    for key, value in readonly_configuration.items():
        print(f"  {key}={value}")

    print(
        """
Bash examples:

name="Atul"
count=10
echo "$name"
echo "$count"

readonly APP_NAME="automation-lab"

export API_MODE="production"

The 'export' operation makes a variable available to child processes.
Without export, a normal shell variable remains local to the current shell
environment.
"""
    )


# ---------------------------------------------------------------------------
# Quoting and expansion
# ---------------------------------------------------------------------------

def demonstrate_quoting() -> None:
    print_title("2. Quoting and expansion")

    filename = "annual report.txt"

    # Python's shlex.split approximates shell-like tokenization and is useful
    # for demonstrating why whitespace matters.
    import shlex

    unquoted_command = f"cat {filename}"
    quoted_command = f'cat "{filename}"'

    print_key_value("conceptual unquoted command", unquoted_command)
    print_key_value("conceptual quoted command", quoted_command)

    print("\nTokenization:")
    print("  Unquoted :", shlex.split(unquoted_command))
    print("  Quoted   :", shlex.split(quoted_command))

    variable = "hello world"
    print("\nString length:", len(variable))

    print(
        """
Bash quoting rules:

Single quotes:
    '$HOME'
preserve the literal characters. Variable expansion does not occur.

Double quotes:
    "$HOME"
allow variable and command substitution while preserving the value as one
shell word.

Backslash:
    \\$
can escape a special character.

Command substitution:
    current_date="$(date)"

Arithmetic expansion:
    total=$((price * quantity))

A major production rule is to quote variable expansions unless intentional
word splitting or pathname expansion is required.
"""
    )


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

@dataclass
class UserRecord:
    username: str
    age: int
    active: bool
    role: str


def bash_like_numeric_condition(age: int) -> str:
    if age >= 18:
        return "adult"
    return "minor"


def demonstrate_conditions() -> None:
    print_title("3. Conditions and decision making")

    users = [
        UserRecord("alice", 24, True, "admin"),
        UserRecord("bob", 16, True, "student"),
        UserRecord("carol", 31, False, "operator"),
        UserRecord("dave", 42, True, "operator"),
    ]

    for user in users:
        if not user.active:
            status = "inactive"
        elif user.role == "admin":
            status = "administrator"
        elif user.age >= 18:
            status = "adult user"
        else:
            status = "minor user"

        print(f"{user.username:<8} -> {status}")

    print_subtitle("Comparison categories")

    print(
        """
Bash commonly uses:

String:
    [[ "$a" == "$b" ]]
    [[ "$a" != "$b" ]]
    [[ -z "$a" ]]
    [[ -n "$a" ]]

Numeric:
    [[ "$a" -eq "$b" ]]
    [[ "$a" -ne "$b" ]]
    [[ "$a" -lt "$b" ]]
    [[ "$a" -le "$b" ]]
    [[ "$a" -gt "$b" ]]
    [[ "$a" -ge "$b" ]]

File:
    [[ -e "$file" ]]   exists
    [[ -f "$file" ]]   regular file
    [[ -d "$dir" ]]    directory
    [[ -r "$file" ]]   readable
    [[ -w "$file" ]]   writable
    [[ -x "$file" ]]   executable

Logical:
    [[ condition1 && condition2 ]]
    [[ condition1 || condition2 ]]
    [[ ! condition ]]

For modern Bash scripts, [[ ... ]] is generally preferable to the older
[ ... ] form because it has safer parsing behavior and more expressive
pattern matching.
"""
    )

    print_subtitle("File tests")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        example_file = root / "example.txt"
        example_directory = root / "data"
        example_file.write_text("Bash study file\n", encoding="utf-8")
        example_directory.mkdir()

        tests = {
            "-e exists": example_file.exists(),
            "-f regular file": example_file.is_file(),
            "-d directory": example_directory.is_dir(),
            "-r readable": os.access(example_file, os.R_OK),
            "-w writable": os.access(example_file, os.W_OK),
        }

        for name, result in tests.items():
            print(f"{name:<22} -> {result}")


# ---------------------------------------------------------------------------
# Loops
# ---------------------------------------------------------------------------

def demonstrate_loops() -> None:
    print_title("4. Loops")

    print_subtitle("For loop")

    services = ["database", "api", "worker", "frontend"]

    for service in services:
        print(f"Checking service: {service}")

    print_subtitle("Numeric loop")

    for number in range(1, 6):
        print(f"Iteration {number}")

    print_subtitle("While loop")

    remaining_attempts = 3

    while remaining_attempts > 0:
        print(f"Attempts remaining: {remaining_attempts}")
        remaining_attempts -= 1

    print_subtitle("Continue and break")

    for number in range(1, 11):
        if number % 2 == 0:
            continue
        if number > 7:
            break
        print(f"Processed odd value: {number}")

    print_subtitle("Iterating safely over filenames")

    filenames = [
        "report one.txt",
        "report two.txt",
        "backup.tar.gz",
        "README.md",
    ]

    for filename in filenames:
        # Bash equivalent:
        # for filename in "${files[@]}"; do
        #     printf '%s\n' "$filename"
        # done
        print(f"Filename: {filename}")

    print(
        """
Useful Bash loop patterns:

for item in "${items[@]}"; do
    printf '%s\\n' "$item"
done

for ((i=0; i<10; i++)); do
    printf '%d\\n' "$i"
done

while read -r line; do
    printf 'Line: %s\\n' "$line"
done < input.txt

while condition; do
    ...
done

Avoid parsing filenames with:
    for file in $(find ...)

because command substitution and word splitting can corrupt names containing
spaces, tabs, or newlines. Prefer null-delimited processing such as
find ... -print0 combined with read -d '' when appropriate.
"""
    )


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def calculate_disk_usage(file_sizes: Iterable[int]) -> int:
    """Return the total size represented by an iterable of file sizes."""
    return sum(file_sizes)


def validate_username(username: str) -> bool:
    """Validate a simple shell-friendly username."""
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username))


def retry_operation(
    operation: Callable[[], bool],
    attempts: int,
    delay_seconds: float = 0.0,
) -> bool:
    """Execute an operation repeatedly until it succeeds or attempts end."""
    if attempts <= 0:
        raise ValueError("attempts must be greater than zero")

    for attempt in range(1, attempts + 1):
        print(f"Attempt {attempt}/{attempts}")
        if operation():
            return True
        if delay_seconds > 0 and attempt < attempts:
            time.sleep(delay_seconds)

    return False


def demonstrate_functions() -> None:
    print_title("5. Functions")

    sizes = [120, 300, 80, 500]
    total = calculate_disk_usage(sizes)

    print_key_value("sizes", sizes)
    print_key_value("total", total)

    usernames = ["atul", "admin_user", "invalid user", "a", "deploy-01"]

    for username in usernames:
        print(f"{username!r:<20} valid={validate_username(username)}")

    print_subtitle("Retry function")

    state = {"attempts": 0}

    def simulated_service_check() -> bool:
        state["attempts"] += 1
        return state["attempts"] >= 3

    succeeded = retry_operation(simulated_service_check, attempts=5)
    print_key_value("operation succeeded", succeeded)

    print(
        """
Bash functions:

greet() {
    local name="$1"
    printf 'Hello, %s\\n' "$name"
}

greet "Atul"

Important function concepts:

- Parameters are accessed as $1, $2, ...
- "$@" represents all arguments as separate words.
- "$*" has different quoting behavior and should not normally replace "$@".
- local variables should use 'local'.
- Bash functions return an integer status from 0 to 255.
- 'return 0' means success.
- Data can be printed to stdout and captured with command substitution.
- A function can fail by returning a non-zero status.

Do not confuse a function's return status with returning arbitrary strings.
"""
    )


# ---------------------------------------------------------------------------
# Arguments and CLI behavior
# ---------------------------------------------------------------------------

def parse_argument_demo(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Study Bash command-line argument concepts."
    )
    parser.add_argument(
        "--section",
        choices=[
            "variables",
            "conditions",
            "loops",
            "functions",
            "arguments",
            "automation",
            "all",
        ],
        default="all",
    )
    parser.add_argument(
        "--name",
        default="Atul",
        help="Name used by the argument demonstration.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show how dry-run automation behaves.",
    )
    return parser.parse_args(arguments)


def demonstrate_arguments(name: str) -> None:
    print_title("6. Command-line arguments")

    # Bash automatically provides:
    # $0  script name
    # $1  first argument
    # $#  number of arguments
    # "$@" all arguments as separate words
    # $?  previous command's exit status
    #
    # Python's sys.argv provides a similar command-line input model.

    print_key_value("script/program name", Path(sys.argv[0]).name)
    print_key_value("provided Python arguments", sys.argv[1:])
    print_key_value("demonstration name", name)

    print(
        """
Typical Bash script:

#!/usr/bin/env bash

name="${1:-Guest}"

printf 'Script: %s\\n' "$0"
printf 'First argument: %s\\n' "$1"
printf 'Argument count: %s\\n' "$#"

for argument in "$@"; do
    printf 'Argument: %s\\n' "$argument"
done

For scripts accepting many options, 'getopts' is preferable to manually
parsing every argument.

Example conceptual interface:

./backup.sh -s /srv/app -d /backup --dry-run

For long-option interfaces, Bash scripts may use manual parsing, a dedicated
argument parser, or a wrapper around getopts depending on requirements.
"""
    )


# ---------------------------------------------------------------------------
# Exit status and error handling
# ---------------------------------------------------------------------------

def run_safely(operation: Callable[[], object]) -> tuple[bool, object | None]:
    """Convert exceptions into a success/failure result."""
    try:
        return True, operation()
    except Exception as exc:
        return False, exc


def demonstrate_error_handling() -> None:
    print_title("7. Exit status and error handling")

    def successful_operation() -> str:
        return "operation completed"

    def failing_operation() -> None:
        raise RuntimeError("simulated failure")

    for operation in (successful_operation, failing_operation):
        success, result = run_safely(operation)
        print(f"success={success}, result={result}")

    print(
        """
Bash commands communicate success primarily through exit status.

Convention:
    0       success
    nonzero failure

Common pattern:

if command; then
    printf 'Success\\n'
else
    printf 'Failure\\n' >&2
    exit 1
fi

Production scripts commonly begin with:

set -Eeuo pipefail

Meaning:

-e  exit when an unhandled command fails
-E  propagate ERR traps through functions and some contexts
-u  treat unset variables as errors
-o pipefail  make a pipeline fail when an element fails

These options improve failure detection, but they do not make a script
automatically correct. Bash has contexts where -e behaves differently than
a beginner might expect, so critical scripts should still use explicit error
handling and testing.
"""
    )


# ---------------------------------------------------------------------------
# Arrays
# ---------------------------------------------------------------------------

def demonstrate_arrays() -> None:
    print_title("8. Indexed and associative arrays")

    services = ["api", "database", "worker"]

    print("Indexed array:")
    for index, service in enumerate(services):
        print(f"  index={index}, value={service}")

    service_ports = {
        "api": 8080,
        "database": 5432,
        "worker": 9000,
    }

    print("\nAssociative mapping:")
    for service, port in service_ports.items():
        print(f"  {service} -> {port}")

    print(
        """
Bash indexed arrays:

services=("api" "database" "worker")

printf '%s\\n' "${services[0]}"
printf '%s\\n' "${services[@]}"
printf '%s\\n' "${#services[@]}"

Associative arrays require:

declare -A ports
ports[api]=8080
ports[database]=5432

printf '%s\\n' "${ports[api]}"

Use "${array[@]}" when you want each array element to remain a separate word.
"""
    )


# ---------------------------------------------------------------------------
# Pipelines and data processing
# ---------------------------------------------------------------------------

def normalize_lines(lines: Iterable[str]) -> list[str]:
    """Approximate a simple shell pipeline: trim, filter, sort."""
    return sorted(line.strip().lower() for line in lines if line.strip())


def demonstrate_pipeline_thinking() -> None:
    print_title("9. Pipelines and stream-oriented processing")

    lines = [
        " Bash ",
        "",
        "Automation",
        "SCRIPTING",
        "  functions ",
        "Loops",
    ]

    normalized = normalize_lines(lines)

    print("Input:")
    for line in lines:
        print(repr(line))

    print("\nConceptual pipeline output:")
    for line in normalized:
        print(line)

    print(
        """
A classic Unix design is:

producer | transformer | transformer | consumer

For example:

cat access.log | grep 'ERROR' | cut -d' ' -f1 | sort | uniq -c

Each command receives standard input and writes standard output.

Bash pipelines are powerful because small tools can be composed into larger
workflows. Their weaknesses include portability differences, quoting
complexity, process overhead, and difficulty maintaining large pipelines.

When data processing becomes complex, a dedicated Python, Go, Java, or other
application can provide clearer types, tests, structured error handling, and
better maintainability.
"""
    )


# ---------------------------------------------------------------------------
# Safe automation model
# ---------------------------------------------------------------------------

@dataclass
class AutomationConfig:
    source_directory: Path
    backup_directory: Path
    dry_run: bool = True
    max_retries: int = 3


@dataclass
class AutomationResult:
    copied_files: int
    skipped_files: int
    failed_files: int
    bytes_processed: int


class BackupAutomation:
    """
    A filesystem automation case study.

    The implementation deliberately stays inside a temporary or explicitly
    supplied directory and supports dry-run behavior. It demonstrates the
    same architecture commonly implemented in Bash automation scripts.
    """

    def __init__(self, config: AutomationConfig) -> None:
        self.config = config
        self.copied_files = 0
        self.skipped_files = 0
        self.failed_files = 0
        self.bytes_processed = 0

    def validate(self) -> None:
        if not self.config.source_directory.exists():
            raise FileNotFoundError(
                f"Source directory does not exist: "
                f"{self.config.source_directory}"
            )

        if not self.config.source_directory.is_dir():
            raise NotADirectoryError(
                f"Source is not a directory: {self.config.source_directory}"
            )

        if self.config.max_retries < 1:
            raise ValueError("max_retries must be at least 1")

    def discover_files(self) -> list[Path]:
        """
        Discover regular files recursively.

        Bash equivalent concepts include:
            find "$SOURCE" -type f
        """
        return [
            path
            for path in self.config.source_directory.rglob("*")
            if path.is_file()
        ]

    def destination_for(self, source: Path) -> Path:
        relative = source.relative_to(self.config.source_directory)
        return self.config.backup_directory / relative

    def copy_file(self, source: Path, destination: Path) -> bool:
        try:
            size = source.stat().st_size

            if destination.exists():
                # Idempotency rule:
                # If the destination already has the same size, this simple
                # demonstration treats it as already synchronized.
                if destination.stat().st_size == size:
                    self.skipped_files += 1
                    return True

            if self.config.dry_run:
                print(f"[DRY-RUN] COPY {source} -> {destination}")
                self.copied_files += 1
                self.bytes_processed += size
                return True

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

            self.copied_files += 1
            self.bytes_processed += size
            return True

        except OSError as exc:
            print(f"[ERROR] Could not process {source}: {exc}")
            self.failed_files += 1
            return False

    def run(self) -> AutomationResult:
        self.validate()

        files = self.discover_files()

        for source in files:
            destination = self.destination_for(source)
            self.copy_file(source, destination)

        return AutomationResult(
            copied_files=self.copied_files,
            skipped_files=self.skipped_files,
            failed_files=self.failed_files,
            bytes_processed=self.bytes_processed,
        )


def create_demo_source_tree(root: Path) -> None:
    (root / "reports").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)

    (root / "README.txt").write_text(
        "Automation demonstration\n",
        encoding="utf-8",
    )
    (root / "reports" / "monthly.txt").write_text(
        "Monthly report\n",
        encoding="utf-8",
    )
    (root / "logs" / "application.log").write_text(
        "INFO application started\nERROR example event\n",
        encoding="utf-8",
    )


def demonstrate_automation(dry_run: bool) -> None:
    print_title("10. Automation script case study")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        source = root / "source"
        backup = root / "backup"

        source.mkdir()
        create_demo_source_tree(source)

        config = AutomationConfig(
            source_directory=source,
            backup_directory=backup,
            dry_run=dry_run,
        )

        automation = BackupAutomation(config)
        result = automation.run()

        print_subtitle("Automation result")

        print_key_value("copied files", result.copied_files)
        print_key_value("skipped files", result.skipped_files)
        print_key_value("failed files", result.failed_files)
        print_key_value("bytes processed", result.bytes_processed)

        if not dry_run:
            print("\nCreated backup files:")
            for path in sorted(backup.rglob("*")):
                if path.is_file():
                    print(f"  {path.relative_to(backup)}")

    print(
        """
A production Bash backup script might conceptually perform:

1. Parse source and destination arguments.
2. Validate required directories.
3. Create a log file.
4. Discover files.
5. Copy files safely.
6. Check command exit statuses.
7. Retry transient operations.
8. Report failures.
9. Exit with an appropriate status.

Important automation property: idempotency.

An idempotent operation can be run repeatedly without causing unintended
additional effects. For example, a synchronization script should not create
a new duplicate backup every time it executes if the desired state already
exists.
"""
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class SimpleLogger:
    """Small logger corresponding to common Bash logging functions."""

    def info(self, message: str) -> None:
        print(f"[INFO] {message}")

    def warning(self, message: str) -> None:
        print(f"[WARN] {message}")

    def error(self, message: str) -> None:
        print(f"[ERROR] {message}")


def demonstrate_logging() -> None:
    print_title("11. Logging patterns")

    logger = SimpleLogger()

    logger.info("Automation started")
    logger.warning("A simulated optional file is missing")
    logger.error("A simulated operation failed")

    print(
        """
Bash logging functions are often implemented as:

log_info() {
    printf '[INFO] %s\\n' "$*" >&2
}

log_error() {
    printf '[ERROR] %s\\n' "$*" >&2
}

Using stderr for diagnostic messages keeps stdout available for data that
another command may consume through a pipeline.

For production scripts, logs should contain enough context to diagnose a
failure without exposing secrets.
"""
    )


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------

def check_dependencies(commands: Iterable[str]) -> dict[str, bool]:
    return {command: shutil.which(command) is not None for command in commands}


def demonstrate_dependencies() -> None:
    print_title("12. Dependency and environment checks")

    commands = ["python", "bash", "git", "definitely-not-a-real-command"]
    results = check_dependencies(commands)

    for command, available in results.items():
        print(f"{command:<32} available={available}")

    print(
        """
Bash commonly checks dependencies with:

command -v git >/dev/null 2>&1 || {
    printf 'git is required\\n' >&2
    exit 1
}

A robust script should validate assumptions before performing destructive or
expensive operations.
"""
    )


# ---------------------------------------------------------------------------
# Security considerations
# ---------------------------------------------------------------------------

def shell_safe_filename(filename: str) -> bool:
    """
    Conservative validation example.

    This is not a universal security policy. It demonstrates the principle
    that externally supplied strings should be validated before they influence
    filesystem or command operations.
    """
    if not filename:
        return False
    if filename in {".", ".."}:
        return False
    if "/" in filename or "\\" in filename:
        return False
    if "\x00" in filename:
        return False
    return True


def demonstrate_security() -> None:
    print_title("13. Bash security principles")

    candidates = [
        "report.txt",
        "annual report.txt",
        "../secret.txt",
        "safe.log",
        "",
    ]

    for candidate in candidates:
        print(f"{candidate!r:<24} safe_simple_name={shell_safe_filename(candidate)}")

    print(
        """
Important Bash security principles:

1. Quote variable expansions.
2. Never construct shell commands from untrusted text unless necessary.
3. Prefer arrays over strings when building command arguments.
4. Do not use eval on untrusted input.
5. Avoid unnecessary shell=True-style execution from other languages.
6. Validate paths before filesystem operations.
7. Use least privilege.
8. Do not place passwords or tokens directly in source code.
9. Protect temporary files from race conditions.
10. Be careful with command substitution and filename expansion.
11. Treat environment variables as untrusted input when they originate outside
    the controlled execution environment.
12. Use secure permissions for sensitive files.
13. Test destructive operations using dry-run modes.

Safer conceptual pattern:

args=("git" "status" "--short")
"${args[@]}"

This preserves argument boundaries.

Riskier pattern:

command="git status --short $USER_INPUT"
eval "$command"

The second pattern introduces an unnecessary code-parsing boundary.
"""
    )


# ---------------------------------------------------------------------------
# Advanced Bash behavior
# ---------------------------------------------------------------------------

def demonstrate_advanced_concepts() -> None:
    print_title("14. Advanced Bash concepts")

    print(
        """
Shell execution model:

The shell reads commands, performs parsing and expansions, and then invokes
commands or shell functions/builtins. Important expansion stages include
parameter expansion, command substitution, arithmetic expansion, pathname
expansion, and word splitting in relevant contexts.

Subshell:
    ( command1; command2 )

A subshell gets a separate execution environment. Changes to ordinary shell
variables made inside it do not normally modify the parent shell.

Command grouping:
    { command1; command2; }

This groups commands in the current shell, subject to shell syntax rules.

Process substitution:
    diff <(sort file1) <(sort file2)

Here the shell exposes command output through a file-like interface supported
by the shell and operating system.

Here documents:
    cat <<EOF
    generated text
    EOF

Here strings:
    grep 'word' <<< "$text"

Traps:
    trap 'cleanup' EXIT

Traps allow scripts to react to signals or shell lifecycle events.

Signals:
    SIGINT is commonly generated by Ctrl+C.
    SIGTERM is commonly used for graceful process termination.
    SIGKILL cannot be caught or handled by the target process.

Temporary-resource cleanup is often implemented with an EXIT trap:

tmp_dir="$(mktemp -d)"
cleanup() {
    rm -rf -- "$tmp_dir"
}
trap cleanup EXIT

The '--' convention helps prevent a pathname beginning with '-' from being
interpreted as an option by commands that support it.

Advanced Bash scripts may also use:
- getopts
- trap
- namerefs
- associative arrays
- coprocesses
- process substitution
- job control
- shell options
- programmable completion
- sourceable libraries
- command substitution
- pipelines
- redirections
"""
    )


# ---------------------------------------------------------------------------
# Performance considerations
# ---------------------------------------------------------------------------

def compare_loop_processing(values: list[int]) -> tuple[int, int]:
    """Compare two equivalent in-memory aggregation strategies."""
    explicit_total = 0
    for value in values:
        explicit_total += value

    functional_total = sum(values)
    return explicit_total, functional_total


def demonstrate_performance() -> None:
    print_title("15. Performance considerations")

    values = list(range(1, 10001))
    explicit_total, optimized_total = compare_loop_processing(values)

    print_key_value("explicit loop total", explicit_total)
    print_key_value("sum() total", optimized_total)

    print(
        """
Shell performance is often dominated by process creation and external
commands rather than by simple shell syntax.

For example, repeatedly doing:

for file in ...; do
    grep ...
done

may create many processes.

A single carefully designed pipeline can be faster, but readability and
correctness matter.

For large data sets:
- avoid unnecessary subprocesses
- avoid repeatedly invoking expensive commands
- use builtins when appropriate
- use arrays carefully
- avoid storing huge streams in shell variables
- consider awk, sed, grep, or dedicated applications for data processing
- move complex algorithms into a language with stronger data structures

Bash is excellent as an orchestration language. It becomes less attractive
when the script turns into a large application with complex state, data
models, concurrency, or extensive error handling.
"""
    )


# ---------------------------------------------------------------------------
# Testing concepts
# ---------------------------------------------------------------------------

def run_test(name: str, test_function: Callable[[], None]) -> bool:
    try:
        test_function()
        print(f"PASS  {name}")
        return True
    except AssertionError as exc:
        print(f"FAIL  {name}: {exc}")
        return False


def demonstrate_testing() -> None:
    print_title("16. Testing shell automation")

    def test_username_validation() -> None:
        assert validate_username("valid-user")
        assert not validate_username("bad user")

    def test_backup_discovery() -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "a.txt").write_text("A", encoding="utf-8")
            (source / "b.txt").write_text("B", encoding="utf-8")

            config = AutomationConfig(source, root / "backup")
            automation = BackupAutomation(config)
            assert len(automation.discover_files()) == 2

    passed = 0
    passed += run_test("username validation", test_username_validation)
    passed += run_test("backup discovery", test_backup_discovery)

    print_key_value("tests passed", passed)
    print_key_value("tests total", 2)

    print(
        """
Shell testing should verify:
- successful execution
- invalid arguments
- missing files
- empty inputs
- permission failures
- command failures
- signal handling
- repeated execution
- dry-run behavior
- destructive-operation safeguards

A shell test framework can make larger script suites easier to maintain, but
even simple scripts benefit from explicit test cases and isolated temporary
directories.
"""
    )


# ---------------------------------------------------------------------------
# Production checklist
# ---------------------------------------------------------------------------

def demonstrate_production_design() -> None:
    print_title("17. Production-oriented Bash design")

    checklist = [
        "Use an explicit shebang such as #!/usr/bin/env bash",
        "Use strict-mode options deliberately",
        "Quote variable expansions",
        "Validate arguments",
        "Validate dependencies",
        "Use functions to separate responsibilities",
        "Send diagnostics to stderr",
        "Use meaningful exit statuses",
        "Implement cleanup with trap where appropriate",
        "Support dry-run mode for destructive automation",
        "Avoid eval",
        "Avoid parsing ls output",
        "Handle filenames safely",
        "Make repeated execution predictable",
        "Protect secrets",
        "Log important state transitions",
        "Test failure paths",
        "Document required environment assumptions",
    ]

    for item in checklist:
        print(f"[ ] {item}")

    print(
        """
A maintainable automation script often has this architecture:

Configuration
    ↓
Argument parsing
    ↓
Dependency validation
    ↓
Input validation
    ↓
Core functions
    ↓
Error handling
    ↓
Cleanup
    ↓
Exit status

The script should have one clear responsibility or a tightly related group
of responsibilities. When logic becomes highly stateful or algorithmically
complex, moving that logic into a general-purpose programming language can
make the system easier to test and maintain.
"""
    )


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def run_section(section: str, name: str, dry_run: bool) -> None:
    if section in {"all", "variables"}:
        demonstrate_variables()
        demonstrate_quoting()
        demonstrate_bash_syntax()

    if section in {"all", "conditions"}:
        demonstrate_conditions()

    if section in {"all", "loops"}:
        demonstrate_loops()

    if section in {"all", "functions"}:
        demonstrate_functions()

    if section in {"all", "arguments"}:
        demonstrate_arguments(name)

    if section == "all":
        demonstrate_arrays()
        demonstrate_pipeline_thinking()
        demonstrate_error_handling()
        demonstrate_logging()
        demonstrate_dependencies()
        demonstrate_security()
        demonstrate_advanced_concepts()
        demonstrate_performance()
        demonstrate_testing()
        demonstrate_production_design()

    if section in {"all", "automation"}:
        demonstrate_automation(dry_run)


def main() -> int:
    args = parse_argument_demo(sys.argv[1:])

    print_title("Bash Shell Scripting: Variables, Conditions, Loops, Functions, Arguments, Automation")

    try:
        run_section(args.section, args.name, args.dry_run)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    print_title("Execution completed")
    print("The demonstrations completed without executing arbitrary shell commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
