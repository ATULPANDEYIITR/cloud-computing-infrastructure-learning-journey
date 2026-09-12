"""
Linux Installation and Environment
Virtual Machines, Linux Installation, Terminal Environment, SSH Basics,
and Remote Server Access

This standalone study script progresses from absolute beginner concepts to
advanced practical administration and remote-access techniques.

The demonstrations are intentionally safe:
- No destructive filesystem commands are executed automatically.
- No real remote host, password, private key, or credential is required.
- SSH examples show commands and configuration concepts without connecting
  to an unknown machine.
- VirtualBox and Ubuntu installation steps are represented as structured
  study data and validation examples.
"""

from __future__ import annotations

import getpass
import hashlib
import ipaddress
import os
import platform
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional


# ============================================================================
# 1. Learning helper
# ============================================================================

def section(title: str) -> None:
    """Print a clearly separated study section."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain(term: str, definition: str) -> None:
    """Print a compact definition used throughout the demonstrations."""
    print(f"{term}: {definition}")


# ============================================================================
# 2. Core Linux terminology
# ============================================================================

LINUX_TERMINOLOGY = {
    "Linux kernel": (
        "The core software responsible for hardware interaction, process "
        "management, memory management, networking, and other system services."
    ),
    "Distribution": (
        "A complete operating-system package built around the Linux kernel, "
        "including user-space software, package management, installers, and tools."
    ),
    "Ubuntu": (
        "A Debian-based Linux distribution commonly used on desktops, servers, "
        "cloud systems, development machines, and virtual machines."
    ),
    "Virtual machine": (
        "A software-defined computer running as a guest inside a host computer."
    ),
    "Hypervisor": (
        "Software that creates and manages virtual machines."
    ),
    "Terminal": (
        "A text-based interface through which a user interacts with a shell."
    ),
    "Shell": (
        "A command interpreter that reads commands and launches programs. "
        "Bash is a widely used Linux shell."
    ),
    "SSH": (
        "Secure Shell, a protocol for encrypted remote login, command execution, "
        "file transfer, tunneling, and related secure administration tasks."
    ),
    "Daemon": (
        "A background service process. The SSH server commonly runs as sshd."
    ),
    "Package manager": (
        "Software that installs, updates, removes, and tracks packages and dependencies."
    ),
}


# ============================================================================
# 3. Operating-system architecture
# ============================================================================

def demonstrate_linux_architecture() -> None:
    section("Linux system architecture")

    layers = [
        ("Hardware", "CPU, RAM, storage, network interfaces, USB devices"),
        ("Firmware", "BIOS or UEFI initializes hardware and starts the boot process"),
        ("Bootloader", "GRUB commonly loads the Linux kernel"),
        ("Kernel", "Manages CPU, memory, devices, networking, and processes"),
        ("System services", "Background services such as networking and SSH"),
        ("User space", "Libraries, utilities, applications, shells, and daemons"),
        ("Shell", "Interprets commands such as ls, cd, cp, and ssh"),
        ("Applications", "Editors, browsers, compilers, servers, and other programs"),
    ]

    for layer, purpose in layers:
        print(f"{layer:<20} -> {purpose}")

    print(
        "\nImportant distinction: Linux is technically the kernel. "
        "Ubuntu is a distribution that packages the Linux kernel with a complete "
        "user-space environment."
    )


# ============================================================================
# 4. Virtual machine fundamentals
# ============================================================================

@dataclass
class VirtualMachineSpecification:
    """Represent the important resources assigned to a virtual machine."""

    name: str
    operating_system: str
    cpu_cores: int
    memory_gb: float
    disk_gb: int
    network_mode: str = "NAT"
    virtualization_enabled: bool = True

    def validate(self, host_memory_gb: float) -> list[str]:
        errors = []

        if self.cpu_cores < 1:
            errors.append("A virtual machine requires at least one virtual CPU.")

        if self.memory_gb <= 0:
            errors.append("Virtual memory must be greater than zero.")

        if self.memory_gb >= host_memory_gb:
            errors.append(
                "Do not allocate all host RAM to the guest; the host also needs memory."
            )

        if self.disk_gb < 10:
            errors.append(
                "A modern Ubuntu installation normally needs more than a tiny disk."
            )

        valid_network_modes = {
            "NAT",
            "Bridged Adapter",
            "Host-only Adapter",
            "Internal Network",
        }

        if self.network_mode not in valid_network_modes:
            errors.append(f"Unsupported network mode: {self.network_mode}")

        if not self.virtualization_enabled:
            errors.append(
                "Hardware virtualization should normally be enabled for good VM performance."
            )

        return errors


def demonstrate_virtual_machine() -> None:
    section("Virtual machines and hypervisors")

    explain(
        "Host",
        "The physical computer on which the virtualization software runs.",
    )
    explain(
        "Guest",
        "The operating system running inside the virtual machine.",
    )
    explain(
        "Virtual CPU",
        "A portion of the host CPU capacity presented to the guest.",
    )
    explain(
        "Virtual disk",
        "A file or storage object that behaves like a disk to the guest OS.",
    )
    explain(
        "Snapshot",
        "A saved point-in-time state that can be used for rollback.",
    )
    explain(
        "NAT",
        "The guest reaches external networks through address translation performed by the host.",
    )
    explain(
        "Bridged networking",
        "The VM appears as a separate machine on the same network as the host.",
    )
    explain(
        "Host-only networking",
        "The VM can communicate with the host and selected virtual peers but normally not directly with the external LAN.",
    )

    vm = VirtualMachineSpecification(
        name="ubuntu-study",
        operating_system="Ubuntu Linux",
        cpu_cores=2,
        memory_gb=4,
        disk_gb=40,
        network_mode="NAT",
    )

    print("\nExample VM specification:")
    print(vm)

    errors = vm.validate(host_memory_gb=16)

    if errors:
        print("\nVM configuration problems:")
        for error in errors:
            print(f"- {error}")
    else:
        print("\nVM configuration passes the basic study validation.")


# ============================================================================
# 5. VirtualBox conceptual installation workflow
# ============================================================================

VIRTUALBOX_INSTALLATION_STEPS = [
    "Install Oracle VirtualBox on the host operating system.",
    "Download an Ubuntu ISO image from the official Ubuntu distribution source.",
    "Create a new virtual machine in VirtualBox.",
    "Select Linux and the appropriate Ubuntu 64-bit profile.",
    "Assign reasonable CPU and RAM without starving the host.",
    "Create a virtual disk using a suitable dynamically allocated disk format.",
    "Choose the VM network mode, commonly NAT for beginner installations.",
    "Attach the Ubuntu ISO to the VM's virtual optical drive.",
    "Start the VM and boot from the ISO.",
    "Select the Ubuntu installation option.",
    "Configure keyboard layout, networking, user account, timezone, and disk installation.",
    "Allow the installer to copy the operating system to the virtual disk.",
    "Restart the VM and detach the ISO when requested.",
    "Update the installed operating system after the first successful boot.",
]


def demonstrate_virtualbox_workflow() -> None:
    section("VirtualBox and Ubuntu installation workflow")

    for number, step in enumerate(VIRTUALBOX_INSTALLATION_STEPS, start=1):
        print(f"{number:02d}. {step}")

    print(
        "\nImportant distinction: the ISO is installation media. "
        "After installation, Ubuntu normally boots from the VM's virtual disk."
    )


# ============================================================================
# 6. Boot process
# ============================================================================

def demonstrate_boot_process() -> None:
    section("Linux boot process")

    boot_stages = [
        "Power-on",
        "BIOS/UEFI initialization",
        "Bootloader selection",
        "Linux kernel loading",
        "Initial RAM filesystem initialization",
        "Kernel hardware and subsystem initialization",
        "systemd initialization on a typical modern Ubuntu installation",
        "System services starting",
        "Login manager or text console",
        "User session and shell",
    ]

    for index, stage in enumerate(boot_stages, start=1):
        print(f"{index:02d}. {stage}")


# ============================================================================
# 7. Terminal and shell fundamentals
# ============================================================================

SAFE_COMMANDS = {
    "pwd": "Print the current working directory.",
    "ls": "List directory contents.",
    "ls -la": "List visible and hidden entries with detailed metadata.",
    "whoami": "Print the current username.",
    "id": "Display user and group identity information.",
    "uname -a": "Display kernel and system information.",
    "date": "Display the system date and time.",
    "hostname": "Display the machine hostname.",
    "df -h": "Display filesystem capacity using human-readable units.",
    "free -h": "Display memory usage using human-readable units.",
    "ps aux": "Display running processes.",
    "ip addr": "Display network interfaces and IP addresses.",
    "ip route": "Display the routing table.",
}


def demonstrate_terminal_commands() -> None:
    section("Terminal environment and fundamental commands")

    print("Common commands:")
    for command, purpose in SAFE_COMMANDS.items():
        print(f"{command:<18} -> {purpose}")

    print(
        "\nShell commands generally have this conceptual structure:\n"
        "command [options] [arguments]\n"
        "Example: ls -la /var/log"
    )


# ============================================================================
# 8. Running safe local commands from Python
# ============================================================================

def run_command(
    command: list[str],
    timeout: int = 10,
) -> tuple[int, str, str]:
    """
    Execute a command without invoking a shell.

    Using a list of arguments instead of shell=True avoids shell parsing and
    reduces command-injection risk when arguments originate from user input.
    """
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    return completed.returncode, completed.stdout, completed.stderr


def demonstrate_local_environment() -> None:
    section("Inspecting the current environment with Python")

    print(f"Operating system: {platform.system()}")
    print(f"Platform: {platform.platform()}")
    print(f"Python version: {platform.python_version()}")
    print(f"Machine architecture: {platform.machine()}")
    print(f"Current user: {getpass.getuser()}")
    print(f"Current directory: {Path.cwd()}")

    command = ["uname", "-s"]

    if shutil_available_for_command(command[0]):
        code, output, error = run_command(command)

        print("\nSafe subprocess example:")
        print(f"Command: {shlex.join(command)}")
        print(f"Return code: {code}")
        print(f"Output: {output.strip()}")

        if error.strip():
            print(f"Error output: {error.strip()}")
    else:
        print(
            "\nThe current operating system does not provide the uname command. "
            "This script continues normally."
        )


def shutil_available_for_command(command_name: str) -> bool:
    """Return True when a command exists in PATH."""
    import shutil

    return shutil.which(command_name) is not None


# ============================================================================
# 9. Linux filesystem hierarchy
# ============================================================================

FILESYSTEM_HIERARCHY = {
    "/": "Filesystem root.",
    "/bin": "Essential user commands; on modern Ubuntu this may be linked into /usr/bin.",
    "/boot": "Bootloader files, kernels, and related boot data.",
    "/dev": "Device files representing hardware and virtual devices.",
    "/etc": "System-wide configuration files.",
    "/home": "Regular users' home directories.",
    "/lib": "Essential shared libraries and kernel-related modules; often integrated with /usr.",
    "/media": "Common mount location for removable media.",
    "/mnt": "Temporary or manually managed mount point.",
    "/opt": "Optional third-party application software.",
    "/proc": "Virtual filesystem exposing process and kernel information.",
    "/root": "Home directory of the root administrator account.",
    "/run": "Volatile runtime data created during boot and system operation.",
    "/sbin": "System administration commands; often linked into /usr/sbin.",
    "/srv": "Data served by system services.",
    "/sys": "Virtual filesystem exposing kernel device and subsystem information.",
    "/tmp": "Temporary files.",
    "/usr": "Most user-space applications, libraries, documentation, and shared data.",
    "/var": "Variable data such as logs, caches, queues, and databases.",
}


def demonstrate_filesystem() -> None:
    section("Linux filesystem hierarchy")

    for path, purpose in FILESYSTEM_HIERARCHY.items():
        print(f"{path:<8} -> {purpose}")

    print(
        "\nLinux uses a single directory tree rooted at /. "
        "Windows-style drive letters are not used as the normal filesystem model."
    )


# ============================================================================
# 10. Paths
# ============================================================================

def demonstrate_paths() -> None:
    section("Absolute and relative paths")

    examples = {
        "/home/student/projects": "Absolute path because it begins at /.",
        "~/projects": "Home-directory shorthand interpreted by the shell.",
        "./script.py": "Relative path referring to script.py in the current directory.",
        "../data": "Relative path referring to data in the parent directory.",
    }

    for path, explanation in examples.items():
        print(f"{path:<30} -> {explanation}")

    print("\nPython pathlib demonstration:")

    current = Path.cwd()
    child = current / "example" / "data.txt"

    print(f"Current directory: {current}")
    print(f"Constructed path: {child}")
    print(f"Parent: {child.parent}")
    print(f"Filename: {child.name}")
    print(f"Suffix: {child.suffix}")


# ============================================================================
# 11. File operations
# ============================================================================

def demonstrate_file_operations() -> None:
    section("Creating and inspecting files safely")

    with tempfile.TemporaryDirectory(prefix="linux-study-") as temporary_directory:
        directory = Path(temporary_directory)
        file_path = directory / "notes.txt"

        file_path.write_text(
            "Linux terminal practice\n"
            "SSH study\n"
            "Virtual machine notes\n",
            encoding="utf-8",
        )

        print(f"Temporary directory: {directory}")
        print(f"File created: {file_path}")
        print(f"File contents:\n{file_path.read_text(encoding='utf-8')}")

        information = file_path.stat()

        print(f"File size: {information.st_size} bytes")
        print(f"Permissions: {stat.filemode(information.st_mode)}")

        copied_path = directory / "notes-copy.txt"
        copied_path.write_bytes(file_path.read_bytes())

        print(f"Copied file: {copied_path}")

    print(
        "\nTemporaryDirectory automatically removes the demonstration directory "
        "when the context exits."
    )


# ============================================================================
# 12. Linux permissions
# ============================================================================

@dataclass
class PermissionSet:
    """Represent symbolic Unix permissions."""

    owner: str
    group: str
    others: str

    def numeric(self) -> int:
        mapping = {"r": 4, "w": 2, "x": 1, "-": 0}

        def value(permission: str) -> int:
            if len(permission) != 3:
                raise ValueError("Each permission group must contain three characters.")

            return sum(mapping[character] for character in permission)

        return value(self.owner) * 100 + value(self.group) * 10 + value(self.others)


def demonstrate_permissions() -> None:
    section("Linux permissions")

    permissions = [
        PermissionSet("rwx", "r-x", "r--"),
        PermissionSet("rw-", "r--", "---"),
        PermissionSet("r-x", "---", "---"),
    ]

    for item in permissions:
        print(
            f"{item.owner} {item.group} {item.others} "
            f"-> chmod {item.numeric():03d}"
        )

    print(
        "\nPermission meanings:\n"
        "r = read\n"
        "w = write\n"
        "x = execute\n"
        "The three groups are owner, group, and others."
    )

    print(
        "\nFor directories, x means the ability to traverse/access entries by name, "
        "so directory permissions have semantics different from ordinary files."
    )


# ============================================================================
# 13. Users, groups, root, sudo
# ============================================================================

def demonstrate_users_and_privileges() -> None:
    section("Users, groups, root, and sudo")

    explain(
        "Regular user",
        "An account intended for normal work with limited privileges.",
    )
    explain(
        "root",
        "The Unix superuser with broad administrative authority.",
    )
    explain(
        "sudo",
        "A mechanism allowing an authorized user to run selected commands with elevated privileges.",
    )
    explain(
        "Group",
        "A collection of users used to organize permissions and access.",
    )

    print(
        "\nGood administrative practice:\n"
        "1. Use a normal account for everyday work.\n"
        "2. Elevate only when required.\n"
        "3. Prefer targeted sudo commands over permanently operating as root.\n"
        "4. Protect administrative credentials and SSH keys.\n"
        "5. Review permissions before granting broad access."
    )


# ============================================================================
# 14. Package management with APT
# ============================================================================

APT_COMMANDS = {
    "sudo apt update": "Refresh package-index metadata.",
    "apt search package-name": "Search available packages.",
    "apt show package-name": "Display package metadata.",
    "sudo apt install package-name": "Install a package.",
    "sudo apt upgrade": "Upgrade installed packages.",
    "sudo apt remove package-name": "Remove a package while retaining some configuration data.",
    "sudo apt purge package-name": "Remove a package and its package-managed configuration.",
    "sudo apt autoremove": "Remove packages that are no longer required as dependencies.",
}


def demonstrate_apt() -> None:
    section("Ubuntu package management with APT")

    for command, purpose in APT_COMMANDS.items():
        print(f"{command:<45} -> {purpose}")

    print(
        "\nAPT manages Debian-family packages and resolves dependencies. "
        "Running apt update does not itself install updates; it refreshes package indexes."
    )


# ============================================================================
# 15. Environment variables and PATH
# ============================================================================

def demonstrate_environment_variables() -> None:
    section("Environment variables and PATH")

    path_value = os.environ.get("PATH", "")

    print("HOME:", os.environ.get("HOME", "<not available>"))
    print("USER:", os.environ.get("USER", "<not available>"))
    print("SHELL:", os.environ.get("SHELL", "<not available>"))

    path_entries = path_value.split(os.pathsep)

    print("\nPATH entries:")
    for entry in path_entries[:10]:
        print(f"- {entry}")

    if len(path_entries) > 10:
        print(f"- ... {len(path_entries) - 10} additional entries")

    print(
        "\nPATH tells the shell where to search for executable commands. "
        "A malicious directory placed early in PATH can cause an unintended executable "
        "to run, so PATH should be treated as security-sensitive configuration."
    )


# ============================================================================
# 16. Shell redirection and pipelines
# ============================================================================

def demonstrate_shell_concepts() -> None:
    section("Shell redirection and pipelines")

    examples = [
        ("command > output.txt", "Redirect standard output and overwrite the file."),
        ("command >> output.txt", "Append standard output."),
        ("command < input.txt", "Use a file as standard input."),
        ("command 2> errors.txt", "Redirect standard error."),
        ("command1 | command2", "Pipe standard output from one command into another."),
    ]

    for syntax, meaning in examples:
        print(f"{syntax:<30} -> {meaning}")

    print(
        "\nExample concept:\n"
        "ps aux | grep ssh\n"
        "The first command produces process information and the pipe passes that "
        "output to grep for filtering."
    )


# ============================================================================
# 17. Processes and signals
# ============================================================================

@dataclass
class ProcessConcept:
    pid: int
    parent_pid: int
    state: str
    command: str


def demonstrate_processes() -> None:
    section("Processes and process management")

    process = ProcessConcept(
        pid=4242,
        parent_pid=1000,
        state="running",
        command="python application.py",
    )

    print(process)

    print(
        "\nCommon process concepts:\n"
        "PID  = process identifier\n"
        "PPID = parent process identifier\n"
        "CPU time = processor time consumed by a process\n"
        "RSS = resident memory currently held in RAM\n"
        "Signal = asynchronous notification sent to a process"
    )

    signals = {
        "SIGTERM": "Request graceful termination.",
        "SIGKILL": "Force termination; the process cannot handle this signal.",
        "SIGHUP": "Historically associated with terminal hangup; commonly used by services to request configuration reload.",
        "SIGINT": "Interrupt, commonly generated by Ctrl+C in a terminal.",
    }

    for name, meaning in signals.items():
        print(f"{name:<8} -> {meaning}")


# ============================================================================
# 18. Networking fundamentals
# ============================================================================

def demonstrate_networking_basics() -> None:
    section("Networking fundamentals for SSH")

    explain("IP address", "A logical address used to identify a network interface.")
    explain("IPv4", "A 32-bit address system commonly written in dotted decimal notation.")
    explain("IPv6", "A 128-bit address system designed to provide a much larger address space.")
    explain("Port", "A numbered endpoint used to distinguish network services.")
    explain("TCP", "A connection-oriented transport protocol used by SSH.")
    explain("DNS", "A naming system that maps domain names to IP-related records.")
    explain("Gateway", "A router through which traffic can reach other networks.")
    explain("Subnet", "A logical division of an IP network.")

    addresses = [
        "127.0.0.1",
        "192.168.1.20",
        "10.0.0.15",
        "172.16.5.10",
    ]

    for address in addresses:
        ip = ipaddress.ip_address(address)
        print(f"{address:<16} -> IPv{ip.version}")

    print(
        "\n127.0.0.1 is the IPv4 loopback address. "
        "It refers to the local machine rather than another host."
    )


# ============================================================================
# 19. Subnetting demonstration
# ============================================================================

def demonstrate_subnetting() -> None:
    section("Subnetting example")

    network = ipaddress.ip_network("192.168.10.0/24")

    print(f"Network: {network}")
    print(f"Network address: {network.network_address}")
    print(f"Broadcast address: {network.broadcast_address}")
    print(f"Prefix length: {network.prefixlen}")
    print(f"Total addresses: {network.num_addresses}")

    hosts = list(network.hosts())

    print(f"First usable host: {hosts[0]}")
    print(f"Last usable host: {hosts[-1]}")

    smaller_networks = list(network.subnets(new_prefix=26))

    print("\nSplitting /24 into /26 networks:")
    for subnet in smaller_networks:
        print(f"- {subnet}")

    print(
        "\nCIDR notation such as /24 describes how many leading bits belong "
        "to the network prefix."
    )


# ============================================================================
# 20. SSH architecture
# ============================================================================

@dataclass
class SSHConnection:
    username: str
    hostname: str
    port: int = 22

    @property
    def destination(self) -> str:
        return f"{self.username}@{self.hostname}"

    def command(self) -> str:
        return f"ssh -p {self.port} {self.destination}"


def demonstrate_ssh_basics() -> None:
    section("SSH fundamentals")

    explain(
        "SSH client",
        "The program initiating an SSH connection, commonly the ssh command.",
    )
    explain(
        "SSH server",
        "The service accepting SSH connections, commonly OpenSSH sshd.",
    )
    explain(
        "Host key",
        "A server identity key used by SSH to help detect unexpected server identity changes.",
    )
    explain(
        "Public key",
        "A key that can be shared and is used as part of public-key authentication.",
    )
    explain(
        "Private key",
        "A secret key that must be protected and should never be distributed publicly.",
    )
    explain(
        "Known hosts",
        "A client-side record used to remember server host keys.",
    )

    connection = SSHConnection(
        username="student",
        hostname="server.example.com",
        port=22,
    )

    print("\nBasic connection representation:")
    print(connection.command())

    print(
        "\nConceptual connection sequence:\n"
        "Client -> TCP connection -> SSH protocol negotiation -> "
        "server host-key verification -> user authentication -> encrypted session"
    )


# ============================================================================
# 21. SSH key generation concepts
# ============================================================================

SSH_KEY_COMMANDS = [
    "ssh-keygen -t ed25519 -C 'student@example'",
    "ssh-keygen -lf ~/.ssh/id_ed25519.pub",
    "ssh-add ~/.ssh/id_ed25519",
    "ssh-copy-id student@server.example.com",
]


def demonstrate_ssh_keys() -> None:
    section("SSH public-key authentication")

    for command in SSH_KEY_COMMANDS:
        print(command)

    print(
        "\nTypical key pair:\n"
        "~/.ssh/id_ed25519      -> private key; protect it carefully\n"
        "~/.ssh/id_ed25519.pub  -> public key; can be installed on a server"
    )

    print(
        "\nThe server normally stores authorized public keys in:\n"
        "~/.ssh/authorized_keys"
    )

    print(
        "\nA passphrase on the private key protects the key if the private-key "
        "file is copied by an attacker."
    )


# ============================================================================
# 22. Demonstrating fingerprints safely
# ============================================================================

def public_key_fingerprint(public_key: str) -> str:
    """
    Compute a SHA-256 digest of text representing a public key.

    This is a simplified educational fingerprint demonstration, not a complete
    OpenSSH key parser.
    """
    digest = hashlib.sha256(public_key.encode("utf-8")).hexdigest()
    return digest


def demonstrate_fingerprint() -> None:
    section("SSH fingerprints")

    sample_key = "ssh-ed25519 AAAA_SAMPLE_PUBLIC_KEY student@example"
    fingerprint = public_key_fingerprint(sample_key)

    print(f"Sample fingerprint: SHA256-like demonstration value {fingerprint}")

    print(
        "\nIn actual SSH administration, use OpenSSH's own fingerprint tools "
        "rather than treating this simplified hash as an OpenSSH fingerprint format."
    )


# ============================================================================
# 23. SSH configuration
# ============================================================================

SSH_CONFIG_EXAMPLE = """
Host study-server
    HostName server.example.com
    User student
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
"""

SSH_DAEMON_SETTINGS = {
    "Port": "The TCP port on which sshd listens.",
    "PermitRootLogin": "Controls direct SSH login as root.",
    "PasswordAuthentication": "Controls password-based SSH authentication.",
    "PubkeyAuthentication": "Controls public-key authentication.",
    "AllowUsers": "Restricts SSH logins to specified users.",
    "AllowGroups": "Restricts SSH logins to members of specified groups.",
    "MaxAuthTries": "Limits authentication attempts per connection.",
}


def demonstrate_ssh_configuration() -> None:
    section("SSH client and server configuration")

    print("Example client configuration:")
    print(SSH_CONFIG_EXAMPLE.strip())

    print("\nImportant sshd configuration concepts:")
    for setting, meaning in SSH_DAEMON_SETTINGS.items():
        print(f"{setting:<22} -> {meaning}")

    print(
        "\nAfter changing SSH server configuration, validate the configuration "
        "before restarting the service when the environment supports it. "
        "A syntax error can prevent the service from starting."
    )


# ============================================================================
# 24. SSH connection validation
# ============================================================================

def validate_hostname(hostname: str) -> bool:
    """Basic hostname validation for an educational example."""
    if not hostname or len(hostname) > 253:
        return False

    if hostname.startswith(".") or hostname.endswith("."):
        return False

    labels = hostname.rstrip(".").split(".")

    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not all(character.isalnum() or character == "-" for character in label):
            return False

    return True


def validate_ssh_port(port: int) -> bool:
    return 1 <= port <= 65535


def demonstrate_ssh_validation() -> None:
    section("Validating SSH connection inputs")

    test_hosts = [
        "server.example.com",
        "ubuntu.local",
        "",
        "-invalid.example",
        "server with spaces.example",
    ]

    for hostname in test_hosts:
        print(f"{hostname!r:<35} -> {validate_hostname(hostname)}")

    print("\nPort validation:")
    for port in [22, 2222, 0, 65535, 65536, -1]:
        print(f"{port:>6} -> {validate_ssh_port(port)}")


# ============================================================================
# 25. SSH connectivity concepts
# ============================================================================

def check_tcp_port(hostname: str, port: int, timeout: float = 2.0) -> bool:
    """
    Attempt a TCP connection.

    This function is intentionally opt-in and is not automatically used
    against external systems by the study script.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        try:
            connection.connect((hostname, port))
            return True
        except OSError:
            return False


def demonstrate_connectivity_diagnostics() -> None:
    section("SSH connectivity troubleshooting")

    diagnostic_order = [
        "Check that the client has network connectivity.",
        "Resolve the hostname using DNS or the intended local naming mechanism.",
        "Check that the destination IP is the expected server.",
        "Confirm the server is powered on and reachable.",
        "Confirm sshd is running on the server.",
        "Confirm the expected TCP port is listening.",
        "Check local and server-side firewall rules.",
        "Check routing and subnet configuration.",
        "Check SSH host-key verification.",
        "Check username and authentication method.",
        "Inspect server authentication logs.",
    ]

    for step in diagnostic_order:
        print(f"- {step}")

    print(
        "\nUseful commands include:\n"
        "getent hosts server.example.com\n"
        "ip addr\n"
        "ip route\n"
        "ping server.example.com\n"
        "ss -tln\n"
        "ssh -v student@server.example.com"
    )

    print(
        "\nThe Python TCP checker defined in this script can be used only when "
        "you intentionally provide a host and port that you are authorized to test."
    )


# ============================================================================
# 26. SSH verbose diagnostics
# ============================================================================

SSH_VERBOSE_LEVELS = {
    "-v": "Verbose diagnostics.",
    "-vv": "More detailed diagnostics.",
    "-vvv": "Maximum commonly used SSH client diagnostic verbosity.",
}


def demonstrate_ssh_debugging() -> None:
    section("SSH debugging")

    for option, description in SSH_VERBOSE_LEVELS.items():
        print(f"{option:<5} -> {description}")

    print(
        "\nExample:\n"
        "ssh -vvv student@server.example.com\n"
        "Verbose output can reveal DNS, connection, key-exchange, authentication, "
        "and configuration problems."
    )


# ============================================================================
# 27. SSH remote command execution
# ============================================================================

def demonstrate_remote_commands() -> None:
    section("Executing commands remotely")

    examples = [
        "ssh student@server.example.com 'hostname'",
        "ssh student@server.example.com 'uname -a'",
        "ssh student@server.example.com 'df -h'",
        "ssh student@server.example.com 'systemctl status ssh'",
    ]

    for command in examples:
        print(command)

    print(
        "\nRemote command execution means the command is executed on the server, "
        "while its output is returned to the client terminal."
    )

    print(
        "\nSecurity consideration: if a remote command incorporates untrusted input, "
        "careless shell interpolation can introduce command injection. "
        "Prefer structured argument handling and strict validation."
    )


# ============================================================================
# 28. Secure file transfer
# ============================================================================

def demonstrate_file_transfer() -> None:
    section("SSH-based file transfer")

    commands = [
        "scp local.txt student@server.example.com:/home/student/",
        "scp student@server.example.com:/home/student/report.txt ./",
        "scp -r project/ student@server.example.com:/home/student/",
        "sftp student@server.example.com",
        "rsync -av project/ student@server.example.com:/home/student/project/",
    ]

    for command in commands:
        print(command)

    print(
        "\nscp is simple for straightforward copies. "
        "SFTP provides an interactive file-transfer protocol over SSH. "
        "rsync is particularly useful for synchronizing directory trees efficiently."
    )


# ============================================================================
# 29. SSH tunneling
# ============================================================================

def demonstrate_ssh_tunneling() -> None:
    section("SSH tunneling")

    examples = {
        "Local forwarding": (
            "ssh -L 8080:127.0.0.1:8080 student@server.example.com"
        ),
        "Remote forwarding": (
            "ssh -R 9000:127.0.0.1:9000 student@server.example.com"
        ),
        "Dynamic SOCKS proxy": (
            "ssh -D 1080 student@server.example.com"
        ),
    }

    for tunnel_type, command in examples.items():
        print(f"{tunnel_type}:")
        print(f"  {command}")

    print(
        "\nLocal forwarding maps a local listening port to a destination reachable "
        "from the SSH server. Remote forwarding creates a listening endpoint on "
        "the server side. Dynamic forwarding creates a SOCKS proxy."
    )

    print(
        "\nTunneling is powerful and should be permitted only when it matches the "
        "organization's security policy. Uncontrolled forwarding can bypass network "
        "segmentation and monitoring."
    )


# ============================================================================
# 30. SSH agent
# ============================================================================

def demonstrate_ssh_agent() -> None:
    section("SSH agent")

    print(
        "The SSH agent can hold decrypted private keys in memory so that the user "
        "does not have to repeatedly enter the private-key passphrase."
    )

    commands = [
        "eval \"$(ssh-agent -s)\"",
        "ssh-add ~/.ssh/id_ed25519",
        "ssh-add -l",
        "ssh-add -D",
    ]

    for command in commands:
        print(command)

    print(
        "\nAgent forwarding, commonly requested with ssh -A, requires extra care. "
        "A compromised remote host can potentially use forwarded agent capabilities "
        "while the forwarding session is active."
    )


# ============================================================================
# 31. DNS and hostname resolution
# ============================================================================

def demonstrate_dns() -> None:
    section("DNS and hostname resolution")

    hostnames = [
        "localhost",
        "example.com",
    ]

    for hostname in hostnames:
        try:
            addresses = socket.getaddrinfo(
                hostname,
                None,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )

            unique_addresses = sorted(
                {entry[4][0] for entry in addresses}
            )

            print(f"{hostname}:")
            for address in unique_addresses:
                print(f"  {address}")

        except socket.gaierror as error:
            print(f"{hostname}: DNS/host lookup failed: {error}")


# ============================================================================
# 32. System services and systemd
# ============================================================================

SYSTEMD_COMMANDS = {
    "systemctl status ssh": "Inspect SSH service state.",
    "sudo systemctl start ssh": "Start the SSH service.",
    "sudo systemctl stop ssh": "Stop the SSH service.",
    "sudo systemctl restart ssh": "Restart the SSH service.",
    "sudo systemctl enable ssh": "Configure the service to start at boot.",
    "sudo systemctl disable ssh": "Prevent automatic startup at boot.",
    "journalctl -u ssh": "Inspect logs associated with the SSH service.",
}


def demonstrate_systemd() -> None:
    section("systemd and Linux services")

    for command, meaning in SYSTEMD_COMMANDS.items():
        print(f"{command:<35} -> {meaning}")

    print(
        "\nsystemd commonly acts as PID 1 on modern Ubuntu installations and "
        "coordinates services, startup dependencies, logging integration, and more."
    )


# ============================================================================
# 33. Logs
# ============================================================================

def demonstrate_logs() -> None:
    section("Linux logs")

    print(
        "Logs help distinguish configuration, authentication, networking, and "
        "application failures."
    )

    log_commands = [
        "journalctl",
        "journalctl -b",
        "journalctl -u ssh",
        "journalctl -u ssh --since '1 hour ago'",
        "journalctl -p warning",
    ]

    for command in log_commands:
        print(f"- {command}")

    print(
        "\nA useful troubleshooting principle is to correlate the timestamp of "
        "the observed failure with the server logs."
    )


# ============================================================================
# 34. Firewall fundamentals
# ============================================================================

def demonstrate_firewall() -> None:
    section("Firewall fundamentals")

    explain(
        "Firewall",
        "A security control that permits or blocks network traffic according to rules.",
    )
    explain(
        "UFW",
        "Uncomplicated Firewall, a user-friendly interface commonly used to manage host firewall rules on Ubuntu.",
    )

    commands = [
        "sudo ufw status",
        "sudo ufw allow ssh",
        "sudo ufw allow 22/tcp",
        "sudo ufw enable",
    ]

    for command in commands:
        print(command)

    print(
        "\nWhen changing firewall rules on a remote server, maintain a safe recovery "
        "path. Accidentally blocking SSH can lock an administrator out."
    )


# ============================================================================
# 35. SSH security hardening
# ============================================================================

SSH_HARDENING = [
    "Use current OpenSSH packages and apply security updates.",
    "Prefer public-key authentication where practical.",
    "Protect private keys with appropriate filesystem permissions and passphrases.",
    "Disable direct root login when it is not required.",
    "Restrict allowed users or groups when practical.",
    "Use strong authentication policies.",
    "Avoid exposing SSH unnecessarily to the public internet.",
    "Use firewall rules and network-level access controls.",
    "Monitor authentication logs.",
    "Use multi-factor authentication where the environment supports it.",
    "Protect host keys and investigate unexpected host-key changes.",
    "Do not blindly bypass host-key verification warnings.",
]


def demonstrate_ssh_hardening() -> None:
    section("SSH security hardening")

    for item in SSH_HARDENING:
        print(f"- {item}")

    print(
        "\nA common misconception is that changing SSH from port 22 to another port "
        "is sufficient security. It may reduce unsophisticated automated noise, "
        "but it does not replace authentication, patching, firewalling, and monitoring."
    )


# ============================================================================
# 36. File permissions for SSH
# ============================================================================

def demonstrate_ssh_file_permissions() -> None:
    section("SSH filesystem permissions")

    recommended_permissions = {
        "~/.ssh": "700",
        "~/.ssh/id_ed25519": "600",
        "~/.ssh/id_ed25519.pub": "644",
        "~/.ssh/authorized_keys": "600",
    }

    for path, permission in recommended_permissions.items():
        print(f"{path:<30} -> commonly used permission {permission}")

    print(
        "\nExact requirements can vary with implementation and operating-system "
        "configuration, but private keys should never be world-readable."
    )


# ============================================================================
# 37. SSH known_hosts and host-key verification
# ============================================================================

def demonstrate_known_hosts() -> None:
    section("SSH host-key verification")

    print(
        "On first connection to a server, SSH may ask whether the presented host "
        "key should be trusted. The user should verify the fingerprint through "
        "a trusted channel before accepting an unexpected key."
    )

    print(
        "\nKnown-host concepts:\n"
        "1. Client connects to hostname.\n"
        "2. Server presents its host key.\n"
        "3. Client compares it with previously stored information.\n"
        "4. A mismatch may indicate server replacement, reconfiguration, "
        "DNS/IP changes, or a potential man-in-the-middle attack."
    )

    print(
        "\nDo not solve a host-key warning by blindly deleting the known-host entry. "
        "First determine why the server identity changed."
    )


# ============================================================================
# 38. Remote server architecture
# ============================================================================

@dataclass
class RemoteServer:
    hostname: str
    ip_address: str
    ssh_port: int
    operating_system: str
    purpose: str
    firewall_enabled: bool
    public_key_authentication: bool

    def security_score(self) -> int:
        score = 0

        if self.firewall_enabled:
            score += 1

        if self.public_key_authentication:
            score += 1

        if 1 <= self.ssh_port <= 65535:
            score += 1

        return score


def demonstrate_remote_server() -> None:
    section("Remote server access model")

    server = RemoteServer(
        hostname="ubuntu-server.example",
        ip_address="192.168.10.50",
        ssh_port=22,
        operating_system="Ubuntu Server",
        purpose="Development server",
        firewall_enabled=True,
        public_key_authentication=True,
    )

    print(server)
    print(f"Basic configuration score: {server.security_score()}/3")

    print(
        "\nA production server should be assessed with a much broader threat model. "
        "This simple score is only an educational representation."
    )


# ============================================================================
# 39. Environment variables and secrets
# ============================================================================

def demonstrate_secret_handling() -> None:
    section("Credentials and secret handling")

    print(
        "Avoid hard-coding passwords, private keys, API tokens, or other secrets "
        "inside source code."
    )

    print(
        "\nPrefer mechanisms such as:\n"
        "- SSH key files with appropriate permissions\n"
        "- OS credential stores\n"
        "- Environment variables for suitable non-persistent configuration\n"
        "- Dedicated secret-management systems in production\n"
        "- Restricted configuration files"
    )

    print(
        "\nDo not print secret environment variables merely for debugging. "
        "Logs frequently have a much longer lifetime than expected."
    )


# ============================================================================
# 40. Shell injection demonstration
# ============================================================================

def unsafe_command_construction_example(user_input: str) -> str:
    """
    Educational demonstration of what NOT to do.

    It returns a command string rather than executing it.
    """
    return f"grep {user_input} application.log"


def safe_command_construction_example(user_input: str) -> list[str]:
    """Build command arguments without shell interpretation."""
    return ["grep", user_input, "application.log"]


def demonstrate_command_injection() -> None:
    section("Shell injection and safe command construction")

    user_input = "error"

    unsafe = unsafe_command_construction_example(user_input)
    safe = safe_command_construction_example(user_input)

    print("Conceptual unsafe string:")
    print(unsafe)

    print("\nSafer argument representation:")
    print(safe)

    print(
        "\nThe safe form should be executed with subprocess.run(..., shell=False), "
        "which is the default. The key security principle is to avoid allowing "
        "untrusted text to become shell syntax."
    )


# ============================================================================
# 41. Virtual machine networking comparison
# ============================================================================

NETWORK_MODES = {
    "NAT": (
        "Simple internet access for the guest; inbound access from external "
        "machines normally requires explicit port forwarding."
    ),
    "Bridged Adapter": (
        "Guest behaves like another machine on the physical network."
    ),
    "Host-only Adapter": (
        "Private network between host and VM; useful for isolated development labs."
    ),
    "Internal Network": (
        "Private virtual network between selected VMs without direct host access."
    ),
}


def demonstrate_vm_networking() -> None:
    section("VirtualBox networking modes")

    for mode, description in NETWORK_MODES.items():
        print(f"{mode:<22} -> {description}")

    print(
        "\nFor beginner Ubuntu installation, NAT is often the simplest starting point. "
        "For multi-VM server labs, host-only or internal networking can provide more "
        "controlled isolation."
    )


# ============================================================================
# 42. Port forwarding for a VM
# ============================================================================

@dataclass
class PortForward:
    host_port: int
    guest_port: int
    protocol: str = "tcp"

    def validate(self) -> list[str]:
        errors = []

        if not (1 <= self.host_port <= 65535):
            errors.append("Host port is outside the valid TCP/UDP port range.")

        if not (1 <= self.guest_port <= 65535):
            errors.append("Guest port is outside the valid TCP/UDP port range.")

        if self.protocol.lower() not in {"tcp", "udp"}:
            errors.append("Protocol must be TCP or UDP.")

        return errors


def demonstrate_vm_ssh_port_forwarding() -> None:
    section("VirtualBox SSH port forwarding")

    forwarding = PortForward(
        host_port=2222,
        guest_port=22,
        protocol="tcp",
    )

    print(forwarding)
    print("Validation:", forwarding.validate() or "valid")

    print(
        "\nA common lab design is:\n"
        "Host localhost:2222 -> VM guest:22\n\n"
        "The SSH client can then use:\n"
        "ssh -p 2222 student@127.0.0.1"
    )

    print(
        "\nPort forwarding is a networking rule. It does not by itself configure "
        "or enable the SSH server inside the guest."
    )


# ============================================================================
# 43. Ubuntu server versus Ubuntu desktop
# ============================================================================

def demonstrate_ubuntu_variants() -> None:
    section("Ubuntu Desktop versus Ubuntu Server")

    comparison = [
        ("Primary interface", "Desktop GUI", "Primarily command-line/server-oriented"),
        ("Typical workload", "Desktop applications and development", "Services, applications, remote administration"),
        ("Resource usage", "Usually higher", "Can be lower without a desktop environment"),
        ("Remote administration", "Possible through SSH", "SSH is commonly central to administration"),
        ("Typical use", "Workstation, learning, development", "Web servers, databases, cloud workloads, infrastructure"),
    ]

    print(f"{'Aspect':<25} | {'Desktop':<35} | {'Server'}")
    print("-" * 100)

    for aspect, desktop, server in comparison:
        print(f"{aspect:<25} | {desktop:<35} | {server}")


# ============================================================================
# 44. Virtualization performance
# ============================================================================

def demonstrate_vm_performance() -> None:
    section("Virtual machine performance considerations")

    factors = {
        "CPU allocation": "Too few vCPUs limit compute performance; too many can reduce host responsiveness.",
        "RAM allocation": "Insufficient guest memory causes swapping and poor responsiveness.",
        "Storage": "SSD-backed virtual disks usually perform better than slow physical storage.",
        "Disk format": "Dynamic disks save host space but may have different allocation behavior from fixed-size disks.",
        "Guest tools": "VirtualBox Guest Additions can improve integration and usability.",
        "Nested virtualization": "Running VMs inside a VM can add complexity and performance overhead.",
        "Background workloads": "Host applications compete with the guest for CPU, RAM, disk, and network resources.",
    }

    for factor, explanation in factors.items():
        print(f"{factor:<22} -> {explanation}")


# ============================================================================
# 45. Snapshots and backups
# ============================================================================

def demonstrate_snapshots() -> None:
    section("VM snapshots versus backups")

    print(
        "A snapshot records VM state for convenient rollback. "
        "It should not be treated as a complete disaster-recovery backup."
    )

    print(
        "\nExample workflow:\n"
        "1. Install Ubuntu.\n"
        "2. Update the system.\n"
        "3. Verify networking and SSH.\n"
        "4. Create a snapshot before experimental changes.\n"
        "5. Perform the experiment.\n"
        "6. Revert if the lab becomes unusable."
    )

    print(
        "\nBackups should be stored independently enough that corruption or loss "
        "of the VM does not automatically destroy the only backup."
    )


# ============================================================================
# 46. System resource monitoring
# ============================================================================

def demonstrate_resource_monitoring() -> None:
    section("Linux resource monitoring")

    commands = {
        "top": "Interactive process and resource monitor.",
        "htop": "Enhanced interactive process viewer when installed.",
        "free -h": "RAM and swap usage.",
        "df -h": "Filesystem capacity.",
        "du -sh directory": "Approximate disk usage of a directory.",
        "uptime": "System uptime and load information.",
        "vmstat": "Virtual-memory and system activity statistics.",
        "iostat": "CPU and I/O statistics when the required package is installed.",
    }

    for command, purpose in commands.items():
        print(f"{command:<25} -> {purpose}")


# ============================================================================
# 47. CPU load and performance reasoning
# ============================================================================

def explain_load_average() -> None:
    section("Linux load average")

    print(
        "Load average represents the amount of work waiting for or using relevant "
        "system resources. It is not simply a percentage of CPU utilization."
    )

    print(
        "\nA machine with 4 logical CPUs and a load average around 4 can be very "
        "different from a single-core machine with the same load value."
    )

    print(
        "\nWhen diagnosing load, inspect CPU utilization, I/O wait, memory pressure, "
        "process state, and the number of available CPU cores rather than relying "
        "on load average alone."
    )


# ============================================================================
# 48. Filesystem capacity reasoning
# ============================================================================

def demonstrate_storage_diagnostics() -> None:
    section("Storage diagnostics")

    print(
        "df answers: how much space is available in a filesystem?\n"
        "du answers: which files and directories are consuming space?"
    )

    print(
        "\nExample workflow:\n"
        "df -h\n"
        "sudo du -xhd1 /var\n"
        "sudo du -xhd1 /var/log"
    )

    print(
        "\nThe -x option can prevent du from crossing into other mounted filesystems, "
        "which can make analysis more meaningful."
    )


# ============================================================================
# 49. Environment initialization
# ============================================================================

def demonstrate_shell_startup() -> None:
    section("Shell startup and configuration")

    files = {
        "~/.bashrc": "Common interactive Bash configuration for user sessions.",
        "~/.profile": "Login-session environment initialization.",
        "/etc/profile": "System-wide login shell configuration.",
        "/etc/environment": "System-level environment configuration on Ubuntu-style systems.",
    }

    for path, purpose in files.items():
        print(f"{path:<20} -> {purpose}")

    print(
        "\nThe exact files loaded depend on whether the shell is interactive, "
        "login-based, graphical, or launched by another process."
    )


# ============================================================================
# 50. Shell aliases and functions
# ============================================================================

def demonstrate_shell_customization() -> None:
    section("Shell aliases and functions")

    examples = {
        "alias ll='ls -alF'": "Creates a shorthand command.",
        "alias grep='grep --color=auto'": "Customizes a command invocation.",
        "mkcd() { mkdir -p \"$1\" && cd \"$1\"; }": "Defines a shell function.",
    }

    for command, explanation in examples.items():
        print(f"{command:<55} -> {explanation}")

    print(
        "\nAliases improve convenience but can create portability problems. "
        "A script should generally not depend on interactive aliases."
    )


# ============================================================================
# 51. SSH config parser
# ============================================================================

def parse_basic_ssh_config(config_text: str) -> dict[str, dict[str, str]]:
    """
    Parse a small educational subset of SSH client configuration.

    This is intentionally not a replacement for OpenSSH's parser.
    """
    hosts: dict[str, dict[str, str]] = {}
    current_host: Optional[str] = None

    for raw_line in config_text.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        parts = line.split()

        if parts[0].lower() == "host" and len(parts) >= 2:
            current_host = parts[1]
            hosts[current_host] = {}
            continue

        if current_host is None or len(parts) < 2:
            continue

        key = parts[0]
        value = " ".join(parts[1:])
        hosts[current_host][key] = value

    return hosts


def demonstrate_ssh_config_parser() -> None:
    section("Parsing SSH configuration conceptually")

    config = """
    Host lab-server
        HostName 192.168.10.50
        User student
        Port 2222
        IdentityFile ~/.ssh/id_ed25519

    Host production
        HostName production.example.com
        User administrator
        Port 22
    """

    parsed = parse_basic_ssh_config(config)

    for host, values in parsed.items():
        print(f"{host}:")
        for key, value in values.items():
            print(f"  {key} = {value}")


# ============================================================================
# 52. SSH command builder
# ============================================================================

def build_ssh_command(
    username: str,
    hostname: str,
    port: int = 22,
    identity_file: Optional[str] = None,
) -> list[str]:
    """
    Build an SSH argument list.

    Returning a list makes it suitable for subprocess execution without
    shell parsing.
    """
    if not validate_hostname(hostname):
        raise ValueError(f"Invalid hostname: {hostname!r}")

    if not validate_ssh_port(port):
        raise ValueError(f"Invalid SSH port: {port}")

    if not username:
        raise ValueError("Username must not be empty.")

    command = ["ssh", "-p", str(port)]

    if identity_file:
        command.extend(["-i", identity_file])

    command.append(f"{username}@{hostname}")

    return command


def demonstrate_safe_ssh_command_builder() -> None:
    section("Safe SSH command construction")

    command = build_ssh_command(
        username="student",
        hostname="server.example.com",
        port=22,
        identity_file="~/.ssh/id_ed25519",
    )

    print("Argument list:")
    print(command)

    print("\nShell representation:")
    print(shlex.join(command))

    print(
        "\nThis function constructs arguments but deliberately does not connect "
        "to the server."
    )


# ============================================================================
# 53. SSH automation considerations
# ============================================================================

def demonstrate_ssh_automation() -> None:
    section("SSH automation considerations")

    print(
        "Automating remote administration requires more than simply placing an "
        "ssh command inside a loop."
    )

    considerations = [
        "Use key-based authentication rather than embedding passwords.",
        "Validate target hostnames and ports.",
        "Set connection and command timeouts.",
        "Capture stdout and stderr separately.",
        "Check process return codes.",
        "Retry only operations that are safe to retry.",
        "Avoid exposing private keys in logs.",
        "Use least-privilege accounts.",
        "Record useful audit information without logging secrets.",
        "Handle partial failures explicitly.",
    ]

    for item in considerations:
        print(f"- {item}")


# ============================================================================
# 54. Retry strategy
# ============================================================================

def retry_operation(
    operation,
    attempts: int = 3,
    delay_seconds: float = 0.5,
):
    """
    Generic retry helper for transient failures.

    Production retry policies should normally use bounded exponential backoff,
    jitter, and clear classification of retryable versus non-retryable errors.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_error: Optional[Exception] = None

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            last_error = error

            if attempt == attempts - 1:
                break

            time.sleep(delay_seconds)

    assert last_error is not None
    raise last_error


def demonstrate_retry_logic() -> None:
    section("Retry logic for remote operations")

    attempts = {"count": 0}

    def temporary_operation() -> str:
        attempts["count"] += 1

        if attempts["count"] < 2:
            raise ConnectionError("Simulated transient failure.")

        return "Operation succeeded."

    result = retry_operation(temporary_operation)

    print(result)
    print(f"Attempts used: {attempts['count']}")

    print(
        "\nDo not retry every error. Authentication failures, invalid configuration, "
        "permission errors, and malformed commands often require correction rather "
        "than repeated attempts."
    )


# ============================================================================
# 55. Testing SSH-related utilities
# ============================================================================

def test_validate_ssh_port() -> None:
    assert validate_ssh_port(22)
    assert validate_ssh_port(65535)
    assert not validate_ssh_port(0)
    assert not validate_ssh_port(65536)


def test_validate_hostname() -> None:
    assert validate_hostname("server.example.com")
    assert validate_hostname("ubuntu.local")
    assert not validate_hostname("")
    assert not validate_hostname("-server.example")
    assert not validate_hostname("server name")


def test_permission_set() -> None:
    assert PermissionSet("rwx", "r-x", "r--").numeric() == 754
    assert PermissionSet("rw-", "r--", "---").numeric() == 640


def test_port_forward() -> None:
    assert PortForward(2222, 22).validate() == []
    assert PortForward(0, 22).validate()
    assert PortForward(2222, 65536).validate()


def demonstrate_tests() -> None:
    section("Testing the educational utilities")

    tests = [
        test_validate_ssh_port,
        test_validate_hostname,
        test_permission_set,
        test_port_forward,
    ]

    passed = 0

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
        passed += 1

    print(f"\n{passed}/{len(tests)} tests passed.")


# ============================================================================
# 56. Common SSH failure classification
# ============================================================================

SSH_FAILURES = {
    "Connection timed out": [
        "Routing problem",
        "Firewall dropping traffic",
        "Server unavailable",
        "Wrong IP address",
    ],
    "Connection refused": [
        "Nothing listening on the destination port",
        "SSH service stopped",
        "Wrong port",
        "Firewall actively rejecting traffic",
    ],
    "Could not resolve hostname": [
        "DNS problem",
        "Incorrect hostname",
        "Local name-resolution configuration problem",
    ],
    "Permission denied": [
        "Wrong username",
        "Wrong authentication method",
        "Missing authorized public key",
        "Incorrect file permissions",
        "Account restrictions",
    ],
    "Host key verification failed": [
        "Unexpected host-key change",
        "Wrong server",
        "DNS/IP reassignment",
        "Potential man-in-the-middle attack",
    ],
}


def demonstrate_failure_classification() -> None:
    section("SSH error interpretation")

    for failure, causes in SSH_FAILURES.items():
        print(f"\n{failure}")
        for cause in causes:
            print(f"  - {cause}")


# ============================================================================
# 57. Remote administration workflow
# ============================================================================

def demonstrate_remote_administration_workflow() -> None:
    section("Structured remote administration workflow")

    workflow = [
        "Identify the correct server and authorized account.",
        "Verify network reachability.",
        "Verify DNS or IP resolution.",
        "Connect using SSH.",
        "Verify the remote hostname and account.",
        "Inspect system state before making changes.",
        "Make the smallest necessary change.",
        "Validate the change.",
        "Inspect logs if behavior is unexpected.",
        "Document the change.",
    ]

    for index, step in enumerate(workflow, start=1):
        print(f"{index:02d}. {step}")

    print(
        "\nA useful habit after connecting to an unfamiliar shell is to run "
        "'hostname' and 'whoami' before executing administrative commands. "
        "This reduces the chance of operating on the wrong machine or account."
    )


# ============================================================================
# 58. Production considerations
# ============================================================================

def demonstrate_production_considerations() -> None:
    section("Production Linux server considerations")

    categories = {
        "Identity": "Individual accounts, least privilege, key management, MFA where supported.",
        "Patching": "Regular operating-system and application security updates.",
        "Networking": "Segmentation, firewalling, restricted management paths.",
        "Monitoring": "CPU, memory, storage, service health, authentication activity.",
        "Logging": "Centralized and retained logs appropriate to operational and compliance needs.",
        "Backups": "Tested backups with appropriate recovery objectives.",
        "Configuration": "Documented and repeatable server configuration.",
        "Secrets": "Protected credentials and key material.",
        "Availability": "Redundancy and recovery procedures where required.",
        "Change management": "Controlled changes, validation, and rollback plans.",
    }

    for category, practice in categories.items():
        print(f"{category:<18} -> {practice}")


# ============================================================================
# 59. Security threat model
# ============================================================================

def demonstrate_security_threat_model() -> None:
    section("Threat model for SSH and remote Linux access")

    threats = {
        "Credential theft": "Attacker obtains passwords or private keys.",
        "Brute-force authentication": "Attacker repeatedly attempts credentials.",
        "Man-in-the-middle": "Attacker interferes with communication or impersonates a host.",
        "Exposed service": "An unnecessarily public SSH service increases attack surface.",
        "Privilege escalation": "A compromised account gains unauthorized administrative privileges.",
        "Lateral movement": "An attacker uses one compromised system to access others.",
        "Secret leakage": "Keys or passwords appear in source code, logs, shell history, or backups.",
    }

    for threat, description in threats.items():
        print(f"{threat:<25} -> {description}")

    print(
        "\nSecurity controls should be layered. No single SSH setting eliminates all "
        "remote-access risks."
    )


# ============================================================================
# 60. Least privilege example
# ============================================================================

@dataclass
class UserAccessProfile:
    username: str
    groups: set[str] = field(default_factory=set)
    can_use_sudo: bool = False

    def has_access(self, required_group: str) -> bool:
        return required_group in self.groups


def demonstrate_least_privilege() -> None:
    section("Least privilege")

    developer = UserAccessProfile(
        username="developer",
        groups={"developers"},
        can_use_sudo=False,
    )

    administrator = UserAccessProfile(
        username="administrator",
        groups={"developers", "sysadmin"},
        can_use_sudo=True,
    )

    print(developer)
    print(administrator)

    print(
        "\nThe principle of least privilege means accounts should receive only "
        "the permissions necessary for their legitimate responsibilities."
    )


# ============================================================================
# 61. File ownership
# ============================================================================

@dataclass
class FileOwnership:
    path: str
    owner: str
    group: str
    mode: str


def demonstrate_ownership() -> None:
    section("Linux file ownership")

    examples = [
        FileOwnership("/home/student/project", "student", "student", "drwxr-xr-x"),
        FileOwnership("/etc/ssh/sshd_config", "root", "root", "-rw-r--r--"),
        FileOwnership("/home/student/.ssh/id_ed25519", "student", "student", "-rw-------"),
    ]

    for item in examples:
        print(
            f"{item.path:<35} owner={item.owner:<15} "
            f"group={item.group:<15} mode={item.mode}"
        )

    print(
        "\nOwnership and permission bits work together. A file's owner, group, "
        "and permission mode determine which identities can read, modify, or "
        "execute it."
    )


# ============================================================================
# 62. Links
# ============================================================================

def demonstrate_links() -> None:
    section("Hard links and symbolic links")

    print(
        "Symbolic link:\n"
        "A filesystem entry that points to another path.\n\n"
        "Hard link:\n"
        "Another directory entry referring to the same underlying inode on "
        "a compatible filesystem."
    )

    print(
        "\nCommon commands:\n"
        "ln source target\n"
        "ln -s source target"
    )

    print(
        "\nSymbolic links can become broken when their target path disappears. "
        "Hard links generally cannot cross filesystem boundaries."
    )


# ============================================================================
# 63. Package dependency reasoning
# ============================================================================

def demonstrate_dependencies() -> None:
    section("Package dependencies")

    print(
        "Software packages frequently depend on shared libraries or other packages. "
        "APT resolves dependency relationships so that required components are installed."
    )

    dependency_graph = {
        "web-application": {"runtime", "database-client"},
        "runtime": {"libc", "openssl"},
        "database-client": {"libc"},
        "openssl": {"libc"},
        "libc": set(),
    }

    for package, dependencies in dependency_graph.items():
        print(f"{package:<20} -> {sorted(dependencies)}")

    print(
        "\nDependency management is one reason manual copying of binaries can be "
        "less reliable than using the distribution's package-management system."
    )


# ============================================================================
# 64. Exit codes
# ============================================================================

def demonstrate_exit_codes() -> None:
    section("Command exit codes")

    print(
        "Unix commands normally return an integer status code.\n"
        "0 generally indicates success.\n"
        "A non-zero value generally indicates some kind of failure or special condition."
    )

    command = ["python", "-c", "print('hello from subprocess')"]

    if shutil_available_for_command("python"):
        code, output, error = run_command(command)
        print(f"\nCommand: {shlex.join(command)}")
        print(f"Return code: {code}")
        print(f"Output: {output.strip()}")
        print(f"Error: {error.strip()!r}")


# ============================================================================
# 65. Signal-safe subprocess handling
# ============================================================================

def demonstrate_subprocess_best_practices() -> None:
    section("Subprocess best practices")

    practices = [
        "Use subprocess.run with argument lists.",
        "Avoid shell=True unless shell semantics are explicitly required.",
        "Set timeouts for operations that can hang.",
        "Capture stdout and stderr when diagnostics are needed.",
        "Check return codes.",
        "Do not place passwords directly in command-line arguments.",
        "Do not log sensitive command arguments.",
        "Use absolute executable paths in high-assurance environments when appropriate.",
    ]

    for practice in practices:
        print(f"- {practice}")


# ============================================================================
# 66. SSH host key algorithms
# ============================================================================

def demonstrate_ssh_cryptography() -> None:
    section("SSH cryptographic concepts")

    concepts = {
        "Host keys": "Identify the SSH server to clients.",
        "Key exchange": "Establishes shared cryptographic session material.",
        "Symmetric encryption": "Efficiently protects the established SSH session.",
        "Message authentication": "Helps detect unauthorized modification of protected data.",
        "Public-key authentication": "Allows a user to prove possession of a private key without sending that private key to the server.",
    }

    for name, meaning in concepts.items():
        print(f"{name:<28} -> {meaning}")

    print(
        "\nSSH is a protocol suite rather than simply an encryption command. "
        "Its security depends on correct cryptographic negotiation, identity verification, "
        "authentication, key protection, and configuration."
    )


# ============================================================================
# 67. SSH multiplexing
# ============================================================================

def demonstrate_ssh_multiplexing() -> None:
    section("SSH connection multiplexing")

    print(
        "OpenSSH can reuse an existing encrypted connection for multiple sessions "
        "using connection multiplexing."
    )

    example = """
Host lab-server
    HostName server.example.com
    User student
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 5m
"""

    print(example.strip())

    print(
        "\nMultiplexing can reduce repeated connection setup overhead, but the "
        "control socket becomes an important local security artifact and should "
        "be protected appropriately."
    )


# ============================================================================
# 68. SSH jump hosts
# ============================================================================

def demonstrate_jump_hosts() -> None:
    section("SSH jump hosts")

    print(
        "A jump host provides an intermediate SSH path to a server that is not "
        "directly reachable from the client."
    )

    command = (
        "ssh -J bastion.example.com student@internal-server.example.com"
    )

    print(command)

    print(
        "\nThe jump-host model is useful for segmented networks because internal "
        "servers can remain inaccessible directly from the public network."
    )


# ============================================================================
# 69. SSH configuration precedence
# ============================================================================

def demonstrate_ssh_configuration_precedence() -> None:
    section("SSH configuration management")

    print(
        "SSH configuration can come from command-line options, user configuration, "
        "and system configuration. Exact precedence and option behavior should be "
        "verified against the installed OpenSSH implementation."
    )

    print(
        "\nUseful inspection command:\n"
        "ssh -G host-alias"
    )

    print(
        "\nssh -G can show the effective client configuration after configuration "
        "processing, which is valuable when a connection behaves differently from expected."
    )


# ============================================================================
# 70. Locale and terminal encoding
# ============================================================================

def demonstrate_locale() -> None:
    section("Locale and terminal environment")

    locale_variables = [
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_TIME",
        "LC_NUMERIC",
    ]

    for variable in locale_variables:
        print(f"{variable:<12} -> {os.environ.get(variable, '<not set>')}")

    print(
        "\nLocale settings influence language, character encoding, sorting, "
        "dates, numbers, and application behavior."
    )


# ============================================================================
# 71. SSH and terminal sessions
# ============================================================================

def demonstrate_terminal_sessions() -> None:
    section("Interactive SSH sessions")

    print(
        "An interactive SSH session normally provides a remote shell connected "
        "to the local terminal."
    )

    print(
        "\nConceptual path:\n"
        "Local keyboard -> SSH client -> encrypted network channel -> SSH server -> shell"
    )

    print(
        "\nWhen the network disconnects, programs tied to the terminal may terminate. "
        "Tools such as tmux or screen can preserve terminal sessions on the server."
    )


# ============================================================================
# 72. tmux concept
# ============================================================================

def demonstrate_tmux() -> None:
    section("Persistent terminal sessions")

    commands = [
        "tmux",
        "tmux new -s development",
        "tmux attach -t development",
        "tmux ls",
    ]

    for command in commands:
        print(command)

    print(
        "\ntmux provides a terminal multiplexer. A process can continue running "
        "inside a server-side session even after the SSH connection is disconnected."
    )


# ============================================================================
# 73. Time synchronization
# ============================================================================

def demonstrate_time_sync() -> None:
    section("Time synchronization")

    print(
        "Accurate system time is important for logs, authentication systems, "
        "TLS-related operations, scheduled jobs, distributed systems, and incident analysis."
    )

    commands = [
        "timedatectl status",
        "date",
    ]

    for command in commands:
        print(command)

    print(
        "\nIn production, consistent time synchronization across systems is an "
        "important operational requirement."
    )


# ============================================================================
# 74. Disk mounting concepts
# ============================================================================

def demonstrate_mounts() -> None:
    section("Linux mounts")

    print(
        "Linux makes storage available by mounting filesystems into the directory tree."
    )

    commands = [
        "findmnt",
        "lsblk",
        "df -h",
        "mount",
    ]

    for command in commands:
        print(command)

    print(
        "\nA device such as a virtual disk partition is not automatically equivalent "
        "to a usable directory. A filesystem must be mounted into the directory tree."
    )


# ============================================================================
# 75. Virtual disks
# ============================================================================

def demonstrate_virtual_disks() -> None:
    section("Virtual disk concepts")

    concepts = {
        "VDI": "A VirtualBox disk-image format commonly associated with VirtualBox.",
        "Dynamic allocation": "The virtual disk file grows as guest storage is used.",
        "Fixed allocation": "Host storage is allocated more fully at creation time.",
        "Virtual controller": "The VM presents a virtual storage controller to the guest.",
        "Partition": "A logical region of a disk.",
        "Filesystem": "A structure used to organize files and directories on storage.",
    }

    for name, meaning in concepts.items():
        print(f"{name:<20} -> {meaning}")


# ============================================================================
# 76. Ubuntu installation partitioning
# ============================================================================

def demonstrate_partitioning() -> None:
    section("Ubuntu partitioning concepts")

    print(
        "Typical Linux installations use a filesystem such as ext4 for the main "
        "Linux filesystem. Modern systems may also use a separate EFI System Partition "
        "when booting through UEFI."
    )

    print(
        "\nImportant terms:\n"
        "/       -> root filesystem\n"
        "/home   -> user data location when separately partitioned\n"
        "swap    -> disk-backed memory mechanism\n"
        "EFI     -> firmware boot partition used by UEFI systems"
    )

    print(
        "\nFor a beginner VM, the Ubuntu installer can generally manage partitioning "
        "automatically. Manual partitioning becomes more important when designing "
        "specialized server storage layouts."
    )


# ============================================================================
# 77. Networking configuration
# ============================================================================

def demonstrate_network_configuration() -> None:
    section("Ubuntu networking concepts")

    print(
        "Modern Ubuntu systems commonly use Netplan for declarative network configuration, "
        "with backend services such as systemd-networkd or NetworkManager depending on the environment."
    )

    examples = [
        "ip addr",
        "ip route",
        "resolvectl status",
        "hostnamectl",
    ]

    for command in examples:
        print(command)

    print(
        "\nWhen diagnosing a network problem, separate the layers:\n"
        "link -> IP address -> route -> DNS -> TCP port -> application protocol"
    )


# ============================================================================
# 78. Layered network troubleshooting
# ============================================================================

def demonstrate_layered_troubleshooting() -> None:
    section("Layered SSH troubleshooting")

    layers = [
        ("Physical/virtual link", "Is the network interface operational?"),
        ("IP configuration", "Does the machine have an appropriate IP address?"),
        ("Routing", "Is there a route to the destination?"),
        ("Name resolution", "Does the hostname resolve correctly?"),
        ("Transport", "Is the TCP port reachable?"),
        ("SSH protocol", "Does sshd negotiate correctly?"),
        ("Authentication", "Is the account authorized?"),
        ("Authorization", "Does the account have the required permissions?"),
        ("Application", "Does the intended remote service work?"),
    ]

    for layer, question in layers:
        print(f"{layer:<25} -> {question}")


# ============================================================================
# 79. Backup strategy
# ============================================================================

@dataclass
class BackupPolicy:
    frequency: str
    retention: str
    offsite_copy: bool
    restoration_tested: bool

    def is_reasonable(self) -> bool:
        return self.offsite_copy and self.restoration_tested


def demonstrate_backup_policy() -> None:
    section("Backup and recovery")

    policy = BackupPolicy(
        frequency="Daily",
        retention="30 days",
        offsite_copy=True,
        restoration_tested=True,
    )

    print(policy)
    print(f"Basic policy check: {policy.is_reasonable()}")

    print(
        "\nA backup that has never been restored in a test is not strong evidence "
        "that recovery will succeed when needed."
    )


# ============================================================================
# 80. Disaster recovery
# ============================================================================

def demonstrate_disaster_recovery() -> None:
    section("Disaster recovery concepts")

    concepts = {
        "RPO": "Recovery Point Objective: how much recent data loss is acceptable.",
        "RTO": "Recovery Time Objective: how quickly a service should be restored.",
        "Backup": "A recoverable copy of data or system state.",
        "Restore": "The process of recovering data or system state.",
        "Failover": "Switching service operation to another available system.",
    }

    for name, meaning in concepts.items():
        print(f"{name:<10} -> {meaning}")


# ============================================================================
# 81. Installation checklist
# ============================================================================

def demonstrate_installation_checklist() -> None:
    section("Ubuntu VM installation checklist")

    checklist = [
        ("Host virtualization support", True),
        ("VirtualBox installed", True),
        ("Ubuntu ISO available", True),
        ("VM CPU allocation reviewed", True),
        ("VM memory allocation reviewed", True),
        ("Virtual disk created", True),
        ("Network mode selected", True),
        ("Ubuntu installation completed", True),
        ("VM boots without ISO", True),
        ("System packages updated", True),
        ("Hostname verified", True),
        ("IP configuration verified", True),
        ("SSH server installed if required", True),
        ("SSH service status verified", True),
        ("SSH key authentication configured if required", True),
        ("Firewall reviewed", True),
        ("Snapshot/backup strategy considered", True),
    ]

    for item, completed in checklist:
        print(f"[{'x' if completed else ' '}] {item}")


# ============================================================================
# 82. Practical lab simulation
# ============================================================================

@dataclass
class LinuxLab:
    vm: VirtualMachineSpecification
    ssh_port: int
    username: str

    def describe(self) -> None:
        print(f"VM name: {self.vm.name}")
        print(f"Operating system: {self.vm.operating_system}")
        print(f"CPU: {self.vm.cpu_cores} vCPU")
        print(f"RAM: {self.vm.memory_gb} GB")
        print(f"Disk: {self.vm.disk_gb} GB")
        print(f"Network: {self.vm.network_mode}")
        print(f"SSH user: {self.username}")
        print(f"SSH guest port: {self.ssh_port}")


def demonstrate_practical_lab() -> None:
    section("Complete practical VM and SSH lab")

    lab = LinuxLab(
        vm=VirtualMachineSpecification(
            name="ubuntu-lab",
            operating_system="Ubuntu",
            cpu_cores=2,
            memory_gb=4,
            disk_gb=40,
            network_mode="NAT",
        ),
        ssh_port=22,
        username="student",
    )

    lab.describe()

    print(
        "\nSuggested controlled sequence:\n"
        "1. Create the VM.\n"
        "2. Install Ubuntu.\n"
        "3. Open the terminal.\n"
        "4. Run whoami, hostname, pwd, and uname -a.\n"
        "5. Run ip addr and ip route.\n"
        "6. Update packages.\n"
        "7. Install and enable OpenSSH server if remote administration is required.\n"
        "8. Generate an SSH key on the client.\n"
        "9. Install the public key for the intended user.\n"
        "10. Connect using SSH.\n"
        "11. Verify hostname and username after login.\n"
        "12. Test a harmless remote command.\n"
        "13. Inspect SSH logs.\n"
        "14. Review firewall and account permissions."
    )


# ============================================================================
# 83. Common mistakes
# ============================================================================

COMMON_MISTAKES = {
    "Allocating too much RAM": "The host becomes slow because the VM consumes resources needed by the host.",
    "Ignoring snapshots/backups": "Experimental configuration changes can become difficult to reverse.",
    "Running everything as root": "A mistake or compromised process has much greater potential impact.",
    "Using passwords in scripts": "Credentials can leak through source code, shell history, process listings, or logs.",
    "Ignoring host-key warnings": "A genuine server identity problem may be hidden.",
    "Opening SSH broadly": "An unnecessarily exposed management service increases attack surface.",
    "Confusing NAT with bridged networking": "The guest has different reachability characteristics in each mode.",
    "Forgetting the VM's IP address": "Remote access requires knowing how the client can reach the guest.",
    "Using shell=True carelessly": "Untrusted input can become executable shell syntax.",
    "Treating snapshots as backups": "A snapshot is not a substitute for independent recovery copies.",
    "Changing firewall rules without a recovery path": "Remote administrators can lock themselves out.",
    "Editing SSH configuration without validation": "A configuration error can make SSH unavailable.",
}


def demonstrate_common_mistakes() -> None:
    section("Common mistakes and their consequences")

    for mistake, consequence in COMMON_MISTAKES.items():
        print(f"{mistake}\n  -> {consequence}\n")


# ============================================================================
# 84. Edge cases
# ============================================================================

def demonstrate_edge_cases() -> None:
    section("Important edge cases")

    cases = [
        (
            "Hostname resolves to multiple addresses",
            "SSH may attempt one address and fail while another is reachable; DNS and address selection matter.",
        ),
        (
            "Server IP changes",
            "Known-host records can trigger identity warnings even when the hostname remains unchanged.",
        ),
        (
            "SSH works locally but not remotely",
            "The issue may be firewalling, routing, NAT, port forwarding, or network segmentation.",
        ),
        (
            "SSH connects but commands behave differently",
            "Non-interactive shells can have different environment initialization than interactive login sessions.",
        ),
        (
            "Disk has free space but writes fail",
            "Inodes, permissions, quotas, read-only mounts, or filesystem errors may be responsible.",
        ),
        (
            "RAM appears mostly used",
            "Linux uses memory for filesystem cache; high memory usage alone does not necessarily mean a problem.",
        ),
        (
            "Load is high while CPU is not fully utilized",
            "Processes may be blocked on I/O or other resources.",
        ),
        (
            "Private key works on one machine but not another",
            "Permissions, SSH agent state, path configuration, user identity, or OpenSSH configuration may differ.",
        ),
    ]

    for title, explanation in cases:
        print(f"{title}:\n  {explanation}\n")


# ============================================================================
# 85. Comparison of remote access approaches
# ============================================================================

def demonstrate_remote_access_comparison() -> None:
    section("Remote access comparison")

    comparison = [
        ("SSH", "Encrypted shell and administration", "Linux/Unix servers", "Strong and widely supported"),
        ("RDP", "Graphical remote desktop", "Windows and Linux GUI environments", "Useful for GUI administration"),
        ("VNC", "Remote graphical display", "Cross-platform GUI access", "Requires careful security configuration"),
        ("VPN", "Private network connectivity", "Network-level remote access", "Useful for secure network segmentation"),
        ("Cloud console", "Provider-managed server access", "Cloud virtual machines", "Useful when network SSH is unavailable"),
    ]

    print(f"{'Technology':<12} | {'Primary purpose':<32} | {'Typical use':<28} | {'Key characteristic'}")
    print("-" * 115)

    for row in comparison:
        print(f"{row[0]:<12} | {row[1]:<32} | {row[2]:<28} | {row[3]}")


# ============================================================================
# 86. Linux command categories
# ============================================================================

def demonstrate_command_categories() -> None:
    section("Linux command categories")

    categories = {
        "Navigation": "pwd, cd, ls",
        "Files": "touch, cp, mv, rm, mkdir, find",
        "Text": "cat, less, head, tail, grep, sed, awk",
        "Processes": "ps, top, kill, pgrep",
        "Storage": "lsblk, df, du, mount, findmnt",
        "Networking": "ip, ss, ping, traceroute/tracepath, resolvectl",
        "Services": "systemctl, journalctl",
        "Packages": "apt",
        "Identity": "whoami, id, groups",
        "Remote access": "ssh, scp, sftp, rsync",
    }

    for category, commands in categories.items():
        print(f"{category:<18} -> {commands}")


# ============================================================================
# 87. Command composition
# ============================================================================

def demonstrate_command_composition() -> None:
    section("Command composition")

    operators = {
        "&&": "Run the next command only if the previous command succeeds.",
        "||": "Run the next command if the previous command fails.",
        ";": "Run the next command regardless of the previous command's status.",
        "|": "Pass standard output into another command.",
    }

    for operator, meaning in operators.items():
        print(f"{operator:<4} -> {meaning}")

    print(
        "\nExample:\n"
        "mkdir -p backup && cp notes.txt backup/\n"
        "The copy occurs only if the directory creation command succeeds."
    )


# ============================================================================
# 88. SSH aliases
# ============================================================================

def demonstrate_ssh_aliases() -> None:
    section("SSH aliases")

    print(
        "A client configuration can make long connection details easier to manage."
    )

    print(
        "\nExample concept:\n"
        "Host lab\n"
        "    HostName 192.168.10.50\n"
        "    User student\n"
        "    Port 2222\n"
        "    IdentityFile ~/.ssh/id_ed25519\n\n"
        "The user can then connect with:\n"
        "ssh lab"
    )


# ============================================================================
# 89. Remote command exit status
# ============================================================================

def demonstrate_remote_exit_status() -> None:
    section("Remote command exit status")

    print(
        "When an SSH command executes a remote program, the SSH client's exit "
        "status generally reflects the remote command's status, making SSH useful "
        "for automation and deployment scripts."
    )

    print(
        "\nConceptual example:\n"
        "ssh server.example.com 'test -f /etc/hosts'\n"
        "A script can inspect the resulting exit status to determine whether the file exists."
    )


# ============================================================================
# 90. Idempotence
# ============================================================================

def demonstrate_idempotence() -> None:
    section("Idempotence in server administration")

    print(
        "An operation is idempotent when applying it multiple times results in "
        "the same intended state rather than repeatedly causing additional changes."
    )

    examples = [
        (
            "Ensure a directory exists",
            "mkdir -p /some/directory",
        ),
        (
            "Ensure a package is installed",
            "Use package-management state operations rather than blindly repeating manual installation steps.",
        ),
        (
            "Ensure a configuration value exists",
            "Use controlled configuration management instead of repeatedly appending duplicate lines.",
        ),
    ]

    for concept, example in examples:
        print(f"{concept}: {example}")

    print(
        "\nIdempotence is particularly important when remote administration becomes automated."
    )


# ============================================================================
# 91. Configuration drift
# ============================================================================

def demonstrate_configuration_drift() -> None:
    section("Configuration drift")

    print(
        "Configuration drift occurs when machines that were intended to remain "
        "similar gradually acquire different settings, packages, permissions, or services."
    )

    causes = [
        "Manual changes",
        "Untracked package installations",
        "Different patch levels",
        "Different configuration files",
        "Emergency changes that were never documented",
    ]

    for cause in causes:
        print(f"- {cause}")

    print(
        "\nRepeatable configuration, documentation, automation, and regular auditing "
        "help reduce drift."
    )


# ============================================================================
# 92. Resource limits
# ============================================================================

def demonstrate_resource_limits() -> None:
    section("Linux resource limits")

    print(
        "Processes can be constrained by operating-system resource limits. "
        "This becomes important for production services that create many files, "
        "connections, processes, or open file descriptors."
    )

    print(
        "\nUseful command:\n"
        "ulimit -a"
    )

    print(
        "\nA service that reaches its open-file limit can fail even when CPU and "
        "memory appear healthy."
    )


# ============================================================================
# 93. Open file descriptors
# ============================================================================

def demonstrate_file_descriptors() -> None:
    section("File descriptors")

    print(
        "Linux represents open files, sockets, pipes, and other I/O resources "
        "using file descriptors within a process."
    )

    print(
        "\nCommon standard descriptors:\n"
        "0 -> standard input\n"
        "1 -> standard output\n"
        "2 -> standard error"
    )

    print(
        "\nSSH sessions, network services, and automation systems can consume many "
        "file descriptors, making limits an important production consideration."
    )


# ============================================================================
# 94. Process environment
# ============================================================================

def demonstrate_process_environment() -> None:
    section("Process environment")

    print(
        "A process receives an environment containing variables such as PATH, "
        "HOME, LANG, and application-specific configuration."
    )

    print(
        "\nThe environment can differ between:\n"
        "- Interactive terminal sessions\n"
        "- SSH sessions\n"
        "- systemd services\n"
        "- cron jobs\n"
        "- Containers\n"
        "- GUI-launched applications"
    )

    print(
        "\nThis explains many cases where a command works interactively but fails "
        "when executed as a service or automation job."
    )


# ============================================================================
# 95. Production SSH architecture
# ============================================================================

def demonstrate_production_ssh_architecture() -> None:
    section("Example production SSH architecture")

    print(
        "Internet or corporate network\n"
        "        |\n"
        "        v\n"
        "   Firewall / VPN\n"
        "        |\n"
        "        v\n"
        "    Bastion host\n"
        "        |\n"
        "        v\n"
        " Internal Linux servers\n"
        "        |\n"
        "        +--> application services\n"
        "        +--> databases\n"
        "        +--> monitoring"
    )

    print(
        "\nThe architecture separates the public management boundary from "
        "internal servers and allows access controls to be concentrated at "
        "appropriate network boundaries."
    )


# ============================================================================
# 96. Secure operational checklist
# ============================================================================

def demonstrate_secure_operations() -> None:
    section("Secure Linux and SSH operational checklist")

    checklist = [
        "Use unique user accounts.",
        "Use least privilege.",
        "Use public-key authentication where appropriate.",
        "Protect private keys.",
        "Patch the operating system.",
        "Review firewall rules.",
        "Restrict network exposure.",
        "Verify SSH host keys.",
        "Monitor authentication logs.",
        "Keep tested backups.",
        "Document important changes.",
        "Validate configuration before service restarts.",
        "Avoid secrets in source code and logs.",
        "Use controlled automation for repetitive administration.",
    ]

    for item in checklist:
        print(f"[ ] {item}")


# ============================================================================
# 97. Practical command reference
# ============================================================================

def demonstrate_command_reference() -> None:
    section("Practical command reference")

    commands = [
        ("pwd", "Where am I?"),
        ("ls -la", "What is here?"),
        ("cd /path", "Move to a directory."),
        ("mkdir -p project/data", "Create directories."),
        ("cp source destination", "Copy data."),
        ("mv source destination", "Move or rename data."),
        ("rm file", "Remove a file; use carefully."),
        ("cat file", "Print a small file."),
        ("less file", "Read a file interactively."),
        ("grep pattern file", "Search text."),
        ("find path -name pattern", "Find filesystem entries."),
        ("whoami", "Which user am I?"),
        ("id", "Which IDs and groups do I have?"),
        ("hostname", "Which machine is this?"),
        ("uname -a", "What kernel/system is running?"),
        ("ip addr", "What network interfaces and addresses exist?"),
        ("ip route", "What routes exist?"),
        ("ss -tln", "Which TCP ports are listening?"),
        ("df -h", "How much filesystem space is available?"),
        ("free -h", "How much RAM/swap is available?"),
        ("ps aux", "Which processes are running?"),
        ("systemctl status ssh", "What is the SSH service state?"),
        ("journalctl -u ssh", "What does the SSH service log say?"),
        ("ssh user@host", "Open a remote SSH session."),
        ("scp file user@host:/path/", "Copy a file through SSH."),
        ("sftp user@host", "Open an SFTP session."),
    ]

    for command, question in commands:
        print(f"{command:<40} -> {question}")


# ============================================================================
# 98. Integrated study scenario
# ============================================================================

def demonstrate_integrated_scenario() -> None:
    section("Integrated scenario: Ubuntu VM as an SSH server")

    scenario = [
        "A Windows, macOS, or Linux host runs VirtualBox.",
        "VirtualBox hosts an Ubuntu virtual machine.",
        "Ubuntu receives CPU, RAM, virtual disk, and a virtual network adapter.",
        "Ubuntu boots through the virtual boot process.",
        "The user opens the terminal and verifies the environment.",
        "The network interface receives an address.",
        "OpenSSH server is installed if remote administration is required.",
        "The SSH daemon listens on the configured TCP port.",
        "A client generates an SSH key pair.",
        "The public key is placed in the target account's authorized_keys.",
        "The client verifies the server host key.",
        "An encrypted SSH session is established.",
        "The remote shell executes commands under the authenticated account.",
        "Linux permissions and sudo determine what that account can do.",
        "Logs record relevant service and authentication activity.",
        "Firewall and network configuration determine who can reach SSH.",
    ]

    for index, step in enumerate(scenario, start=1):
        print(f"{index:02d}. {step}")


# ============================================================================
# 99. Final knowledge checks
# ============================================================================

def knowledge_check() -> None:
    section("Knowledge checks")

    questions = [
        (
            "What is the difference between a Linux kernel and an Ubuntu distribution?",
            "The kernel is the core operating-system component; Ubuntu packages the kernel with user-space software and distribution infrastructure.",
        ),
        (
            "What is a virtual machine?",
            "A software-defined computer whose guest operating system runs using virtualized hardware provided by a hypervisor.",
        ),
        (
            "What is the purpose of SSH?",
            "To provide secure remote communication, commonly including encrypted shell access and authenticated command execution.",
        ),
        (
            "What is the difference between a public and private SSH key?",
            "The public key can be installed on servers; the private key proves possession and must remain secret.",
        ),
        (
            "Why is host-key verification important?",
            "It helps the client detect unexpected changes to the identity of the server it is contacting.",
        ),
        (
            "Why should shell=True be avoided with untrusted input?",
            "Because shell metacharacters can transform input into executable commands.",
        ),
        (
            "What is NAT in a VM?",
            "A networking mode where the guest commonly reaches external networks through address translation performed by the host.",
        ),
        (
            "Why is a snapshot not a complete backup?",
            "A snapshot depends on the VM's storage and is mainly intended for point-in-time rollback rather than independent disaster recovery.",
        ),
    ]

    for question, answer in questions:
        print(f"\nQuestion: {question}")
        print(f"Answer:   {answer}")


# ============================================================================
# 100. Main execution
# ============================================================================

def main() -> None:
    """Run the complete Linux installation and SSH study program."""

    demonstrations = [
        demonstrate_linux_architecture,
        demonstrate_virtual_machine,
        demonstrate_virtualbox_workflow,
        demonstrate_boot_process,
        demonstrate_terminal_commands,
        demonstrate_local_environment,
        demonstrate_filesystem,
        demonstrate_paths,
        demonstrate_file_operations,
        demonstrate_permissions,
        demonstrate_users_and_privileges,
        demonstrate_apt,
        demonstrate_environment_variables,
        demonstrate_shell_concepts,
        demonstrate_processes,
        demonstrate_networking_basics,
        demonstrate_subnetting,
        demonstrate_ssh_basics,
        demonstrate_ssh_keys,
        demonstrate_fingerprint,
        demonstrate_ssh_configuration,
        demonstrate_ssh_validation,
        demonstrate_connectivity_diagnostics,
        demonstrate_ssh_debugging,
        demonstrate_remote_commands,
        demonstrate_file_transfer,
        demonstrate_ssh_tunneling,
        demonstrate_ssh_agent,
        demonstrate_dns,
        demonstrate_systemd,
        demonstrate_logs,
        demonstrate_firewall,
        demonstrate_ssh_hardening,
        demonstrate_ssh_file_permissions,
        demonstrate_known_hosts,
        demonstrate_remote_server,
        demonstrate_secret_handling,
        demonstrate_command_injection,
        demonstrate_vm_networking,
        demonstrate_vm_ssh_port_forwarding,
        demonstrate_ubuntu_variants,
        demonstrate_vm_performance,
        demonstrate_snapshots,
        demonstrate_resource_monitoring,
        explain_load_average,
        demonstrate_storage_diagnostics,
        demonstrate_shell_startup,
        demonstrate_shell_customization,
        demonstrate_ssh_config_parser,
        demonstrate_safe_ssh_command_builder,
        demonstrate_ssh_automation,
        demonstrate_retry_logic,
        demonstrate_tests,
        demonstrate_failure_classification,
        demonstrate_remote_administration_workflow,
        demonstrate_production_considerations,
        demonstrate_security_threat_model,
        demonstrate_least_privilege,
        demonstrate_ownership,
        demonstrate_links,
        demonstrate_dependencies,
        demonstrate_exit_codes,
        demonstrate_subprocess_best_practices,
        demonstrate_ssh_cryptography,
        demonstrate_ssh_multiplexing,
        demonstrate_jump_hosts,
        demonstrate_ssh_configuration_precedence,
        demonstrate_locale,
        demonstrate_terminal_sessions,
        demonstrate_tmux,
        demonstrate_time_sync,
        demonstrate_mounts,
        demonstrate_virtual_disks,
        demonstrate_partitioning,
        demonstrate_network_configuration,
        demonstrate_layered_troubleshooting,
        demonstrate_backup_policy,
        demonstrate_disaster_recovery,
        demonstrate_installation_checklist,
        demonstrate_practical_lab,
        demonstrate_common_mistakes,
        demonstrate_edge_cases,
        demonstrate_remote_access_comparison,
        demonstrate_command_categories,
        demonstrate_command_composition,
        demonstrate_ssh_aliases,
        demonstrate_remote_exit_status,
        demonstrate_idempotence,
        demonstrate_configuration_drift,
        demonstrate_resource_limits,
        demonstrate_file_descriptors,
        demonstrate_process_environment,
        demonstrate_production_ssh_architecture,
        demonstrate_secure_operations,
        demonstrate_command_reference,
        demonstrate_integrated_scenario,
        knowledge_check,
    ]

    print("=" * 78)
    print("LINUX INSTALLATION AND ENVIRONMENT")
    print("Virtual Machines | Ubuntu | Terminal | SSH | Remote Server Access")
    print("=" * 78)

    for demonstration in demonstrations:
        try:
            demonstration()
        except KeyboardInterrupt:
            print("\nStudy session interrupted by the user.")
            break
        except Exception as error:
            print(
                f"\n[{demonstration.__name__} encountered an unexpected error: "
                f"{error}]"
            )

    print("\n" + "=" * 78)
    print("END OF LINUX INSTALLATION AND SSH STUDY SCRIPT")
    print("=" * 78)


if __name__ == "__main__":
    main()
