#!/usr/bin/env python3
"""
Introduction to Linux: A comprehensive study script

This standalone Python program teaches Linux from absolute beginner level
through practical and advanced introductory concepts.

Topics covered:
    1. Linux history and philosophy
    2. Kernel, user space, distributions, GNU, and shell
    3. Ubuntu and the terminal
    4. Command-line fundamentals
    5. Filesystem hierarchy
    6. Paths, files, directories, permissions, and ownership
    7. Common Linux commands
    8. Redirection, pipes, wildcards, quoting, and command substitution
    9. Processes, jobs, signals, and system information
    10. Environment variables and PATH
    11. Package management with APT
    12. Users, groups, sudo, and security
    13. Networking and SSH concepts
    14. Linux servers and cloud environments
    15. Logs, services, systemd, and diagnostics
    16. Shell scripting concepts
    17. Python-to-Linux integration
    18. Performance, reliability, security, and production practices
    19. Common mistakes and edge cases
    20. Safe hands-on demonstrations and self-tests

The program intentionally avoids destructive commands such as:
    rm -rf /
    mkfs
    shutdown
    reboot
    poweroff
    destructive disk operations

Most demonstrations use read-only commands so that the script can be
safely executed on Ubuntu or another Linux distribution.

Run:
    python3 linux_introduction.py

Some demonstrations are platform-dependent. When the host is not Linux,
the program explains the concept without attempting Linux-specific actions.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Callable, Iterable, Optional


# ============================================================================
# Presentation helpers
# ============================================================================

WIDTH = 88


def title(text: str) -> None:
    """Print a major section heading."""
    print("\n" + "=" * WIDTH)
    print(text)
    print("=" * WIDTH)


def subsection(text: str) -> None:
    """Print a subsection heading."""
    print("\n" + "-" * WIDTH)
    print(text)
    print("-" * WIDTH)


def explain(text: str) -> None:
    """Print educational text with readable wrapping."""
    print(textwrap.fill(text, width=WIDTH))


def show_code(code: str) -> None:
    """Display a shell or Python example without executing it."""
    print("\nExample:")
    print(textwrap.indent(text.strip("\n"), "    "))


def run_command(
    command: list[str],
    *,
    timeout: float = 5.0,
    allow_failure: bool = True,
) -> Optional[subprocess.CompletedProcess[str]]:
    """
    Execute a command safely and display its output.

    A list is used instead of shell=True for demonstrations that do not need
    shell syntax. This avoids accidental shell interpretation of arguments.
    """
    print(f"\n$ {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        print(f"Command not available: {command[0]}")
        return None
    except subprocess.TimeoutExpired:
        print("Command timed out.")
        return None
    except OSError as error:
        print(f"Operating-system error: {error}")
        return None

    if result.stdout:
        print(result.stdout.rstrip())

    if result.stderr and (result.returncode != 0 or not allow_failure):
        print(result.stderr.rstrip(), file=sys.stderr)

    print(f"[exit code: {result.returncode}]")

    if result.returncode != 0 and not allow_failure:
        raise RuntimeError(f"Command failed: {command}")

    return result


def command_exists(command: str) -> bool:
    """Return True when a command can be found through PATH."""
    return shutil.which(command) is not None


def linux_only() -> bool:
    """Return whether this program is currently running on Linux."""
    return platform.system().lower() == "linux"


# ============================================================================
# 1. Linux history and terminology
# ============================================================================

def section_history() -> None:
    title("1. Linux history and foundational terminology")

    explain(
        "Linux is an operating-system kernel created by Linus Torvalds in 1991. "
        "The word Linux technically refers to the kernel, not to every component "
        "normally found in a complete Linux operating system. A usable Linux "
        "environment combines the kernel with system libraries, utilities, a shell, "
        "applications, package-management tools, and often a graphical desktop."
    )

    subsection("Important historical milestones")

    milestones = [
        ("1969", "Unix development begins at AT&T Bell Labs."),
        ("1970s", "Unix spreads through universities and research environments."),
        ("1983", "The GNU Project begins developing a free Unix-like operating system."),
        ("1987", "Andrew Tanenbaum develops MINIX as an educational Unix-like system."),
        ("1991", "Linus Torvalds releases the first Linux kernel."),
        ("1992", "Linux is relicensed under the GNU General Public License."),
        ("1990s", "Linux distributions become increasingly practical for general use."),
        ("2004", "Ubuntu releases its first version and becomes a major desktop/server distribution."),
        ("2000s–2010s", "Linux becomes central to web servers, virtualization, embedded systems, and cloud computing."),
        ("2020s", "Linux remains dominant across servers, cloud infrastructure, containers, supercomputing, and embedded systems."),
    ]

    for year, event in milestones:
        print(f"{year:12} {event}")

    subsection("Kernel versus operating system")

    explain(
        "The kernel is the privileged core responsible for managing hardware and "
        "system resources. It handles processes, memory, device drivers, networking, "
        "filesystems, and system calls. User applications normally do not communicate "
        "with hardware directly. They request services from the kernel through system "
        "calls and supporting libraries."
    )

    show_code(
        """
        Application
            |
            v
        C/Python/other libraries
            |
            v
        System calls
            |
            v
        Linux kernel
            |
            +--> CPU
            +--> Memory
            +--> Storage
            +--> Network devices
            +--> Other hardware
        """
    )

    subsection("GNU and Linux")

    explain(
        "The GNU Project supplied many foundational Unix-like utilities and libraries, "
        "including tools commonly found in Linux environments. The Linux kernel provides "
        "the kernel itself. A complete system may therefore contain Linux, GNU utilities, "
        "a shell, libraries, package-management software, and distribution-specific tools."
    )

    subsection("Free software and open source")

    explain(
        "Linux is strongly associated with open-source development. Open-source software "
        "makes source code available under licenses that define how the software can be "
        "used, modified, and redistributed. Open source does not automatically mean that "
        "every individual software package is under the same license or has no restrictions."
    )


# ============================================================================
# 2. Kernel, user space, shell, terminal
# ============================================================================

def section_architecture() -> None:
    title("2. Linux architecture: kernel, user space, shell, and terminal")

    concepts = {
        "Kernel": (
            "The privileged core that manages CPU scheduling, memory, devices, "
            "networking, filesystems, and other system resources."
        ),
        "User space": (
            "The area in which ordinary applications and utilities execute with "
            "restricted privileges."
        ),
        "Shell": (
            "A command interpreter that reads commands and starts programs. Bash "
            "is one of the most widely used Linux shells."
        ),
        "Terminal emulator": (
            "A graphical application that provides a text-based interface to a shell."
        ),
        "Command": (
            "An instruction entered into a shell. It may invoke an executable, "
            "shell builtin, alias, function, or other shell feature."
        ),
        "System call": (
            "A controlled interface through which user-space programs request "
            "services from the kernel."
        ),
    }

    for name, description in concepts.items():
        print(f"\n{name}:")
        explain(description)

    subsection("Terminal versus shell")

    explain(
        "A terminal and a shell are not the same thing. The terminal emulator is the "
        "interface window. The shell is the program interpreting commands inside that "
        "window. A terminal can launch Bash, Zsh, Fish, or another shell."
    )

    subsection("Interactive command flow")

    show_code(
        """
        You type:
            ls -la /tmp

        Terminal emulator
            |
            v
        Shell parses the command
            |
            v
        Shell finds the ls executable
            |
            v
        Process starts
            |
            v
        Kernel provides filesystem information
            |
            v
        Output returns to the terminal
        """
    )

    subsection("Useful Linux identity commands")

    if linux_only():
        run_command(["uname", "-a"])
        run_command(["id"])
        run_command(["whoami"])
        run_command(["pwd"])
    else:
        explain(
            "These commands are Linux-specific. This script is currently running on "
            f"{platform.system()}, so they are not executed."
        )


# ============================================================================
# 3. Ubuntu and distributions
# ============================================================================

def section_distributions() -> None:
    title("3. Linux distributions and Ubuntu")

    explain(
        "A Linux distribution packages the Linux kernel together with user-space "
        "software, libraries, installers, package repositories, configuration tools, "
        "documentation, and release policies. Different distributions make different "
        "choices about software versions, defaults, security updates, package formats, "
        "desktop environments, and system administration."
    )

    distributions = [
        ("Ubuntu", "Debian-based; uses APT and commonly uses DEB packages."),
        ("Debian", "Community distribution known for stability and broad package availability."),
        ("Fedora", "Red Hat-sponsored distribution with relatively current software."),
        ("RHEL", "Enterprise distribution from Red Hat with commercial support options."),
        ("Rocky Linux", "Enterprise-oriented distribution compatible with the RHEL ecosystem."),
        ("AlmaLinux", "Community enterprise Linux distribution in the RHEL ecosystem."),
        ("Arch Linux", "Rolling-release distribution emphasizing user control and simplicity."),
        ("openSUSE", "Distribution family offering tools such as YaST and multiple release models."),
        ("Alpine Linux", "Small distribution frequently used in containers and minimal environments."),
    ]

    for name, description in distributions:
        print(f"\n{name}: {description}")

    subsection("Why Ubuntu is important for beginners")

    explain(
        "Ubuntu has a large ecosystem, extensive documentation, a familiar package "
        "management workflow, desktop and server editions, and broad use in cloud "
        "environments. Ubuntu Server is commonly used for web applications, APIs, "
        "databases, automation, and development environments."
    )

    subsection("Distribution does not change the basic Linux model")

    explain(
        "Commands and configuration locations can vary between distributions, but "
        "fundamental concepts remain similar: processes, permissions, filesystems, "
        "users, groups, networking, system calls, shells, and package management."
    )

    if linux_only():
        subsection("Detect the current distribution")

        if Path("/etc/os-release").exists():
            print(Path("/etc/os-release").read_text(encoding="utf-8").strip())
        else:
            print("/etc/os-release is not available.")

        if command_exists("lsb_release"):
            run_command(["lsb_release", "-a"])


# ============================================================================
# 4. Command-line fundamentals
# ============================================================================

def section_command_line() -> None:
    title("4. Command-line fundamentals")

    explain(
        "The Linux command line provides a text interface for controlling the system. "
        "A typical command has a program name followed by zero or more options and "
        "arguments. Options change behavior; arguments identify the objects on which "
        "the command operates."
    )

    show_code(
        """
        ls -lah /var/log
        |  |    |
        |  |    +-- argument: target directory
        |  +------- options: -l, -a, -h
        +---------- command
        """
    )

    subsection("Common beginner commands")

    commands = [
        ("pwd", "Print the current working directory."),
        ("ls", "List directory contents."),
        ("cd", "Change the current directory. This is normally a shell builtin."),
        ("mkdir", "Create directories."),
        ("touch", "Create an empty file or update file timestamps."),
        ("cp", "Copy files or directories."),
        ("mv", "Move or rename files and directories."),
        ("cat", "Display file contents."),
        ("less", "Read text interactively page by page."),
        ("head", "Display the beginning of a file."),
        ("tail", "Display the end of a file."),
        ("wc", "Count lines, words, and bytes."),
        ("sort", "Sort lines."),
        ("uniq", "Report or filter repeated adjacent lines."),
        ("grep", "Search text using patterns."),
        ("find", "Search for filesystem objects."),
        ("file", "Identify the type of a file."),
        ("stat", "Display detailed file metadata."),
        ("du", "Estimate filesystem space used by files."),
        ("df", "Display filesystem disk-space information."),
    ]

    for command, meaning in commands:
        print(f"{command:10} {meaning}")

    subsection("Safe demonstrations")

    if linux_only():
        for command in [
            ["pwd"],
            ["ls", "-la", "."],
            ["file", "/etc/passwd"],
            ["stat", "/etc/passwd"],
            ["df", "-h"],
        ]:
            if command_exists(command[0]):
                run_command(command)

    subsection("Absolute and relative paths")

    explain(
        "An absolute path begins at the root directory and starts with /. A relative "
        "path is interpreted from the current working directory. The special path . "
        "means the current directory and .. means the parent directory. The tilde ~ "
        "usually represents the current user's home directory when expanded by the shell."
    )

    show_code(
        """
        Absolute:
            /etc/hosts

        Relative:
            documents/report.txt

        Current directory:
            .

        Parent directory:
            ..

        Home directory in an interactive shell:
            ~
        """
    )

    subsection("Command discovery")

    if linux_only():
        for command in ["bash", "python3", "ls", "grep", "ssh"]:
            if command_exists(command):
                run_command(["command", "-v", command])


# ============================================================================
# 5. Filesystem hierarchy
# ============================================================================

def section_filesystem() -> None:
    title("5. Linux filesystem hierarchy")

    explain(
        "Linux presents filesystems through a single directory tree rooted at /. "
        "Devices, pseudo-filesystems, disks, partitions, and remote filesystems can "
        "be mounted at locations within this hierarchy."
    )

    hierarchy = [
        ("/", "Root of the entire filesystem tree."),
        ("/bin", "Essential user command binaries on systems that retain this traditional path."),
        ("/boot", "Bootloader files and Linux kernel-related boot files."),
        ("/dev", "Device nodes representing hardware and virtual devices."),
        ("/etc", "System-wide configuration files."),
        ("/home", "Home directories for ordinary users."),
        ("/lib", "Essential shared libraries and kernel modules on traditional layouts."),
        ("/media", "Common mount location for removable media."),
        ("/mnt", "Traditional temporary mount location."),
        ("/opt", "Optional third-party application software."),
        ("/proc", "Virtual filesystem exposing process and kernel information."),
        ("/root", "Home directory of the root user."),
        ("/run", "Volatile runtime state created during system operation."),
        ("/sbin", "System administration binaries on traditional layouts."),
        ("/srv", "Data served by system services."),
        ("/sys", "Virtual filesystem exposing kernel and device information."),
        ("/tmp", "Temporary files."),
        ("/usr", "Most user-space applications, libraries, documentation, and shared data."),
        ("/var", "Variable data such as logs, caches, queues, and databases."),
    ]

    for path, description in hierarchy:
        print(f"{path:10} {description}")

    subsection("Why /proc and /sys are unusual")

    explain(
        "/proc and /sys are commonly virtual filesystems. Their entries represent "
        "kernel-maintained information rather than ordinary persistent files stored "
        "like documents on a disk. Reading them is useful for diagnostics, but their "
        "contents and exact behavior depend on the kernel and system configuration."
    )

    if linux_only():
        subsection("Inspect selected virtual filesystem information")

        for path in ["/proc/cpuinfo", "/proc/meminfo", "/proc/uptime"]:
            if Path(path).exists():
                print(f"\n--- {path} ---")
                try:
                    content = Path(path).read_text(encoding="utf-8", errors="replace")
                    print("\n".join(content.splitlines()[:12]))
                except PermissionError:
                    print("Permission denied.")


# ============================================================================
# 6. Files, metadata, links, permissions
# ============================================================================

def section_files_permissions() -> None:
    title("6. Files, metadata, permissions, ownership, and links")

    explain(
        "Linux treats many resources through file-like interfaces. Regular files and "
        "directories have metadata such as permissions, ownership, timestamps, and "
        "size. The filesystem also supports links, including hard links and symbolic "
        "links."
    )

    subsection("File type indicators")

    explain(
        "In output from ls -l, the first character often identifies the file type. "
        "A '-' normally represents a regular file, 'd' a directory, 'l' a symbolic "
        "link, and other characters represent special filesystem objects."
    )

    subsection("Permissions")

    show_code(
        """
        -rwxr-xr--

        owner:  rwx
        group:  r-x
        others: r--

        r = read
        w = write
        x = execute
        """
    )

    explain(
        "For a regular file, read permits reading contents, write permits modifying "
        "contents, and execute permits execution when the operating system and file "
        "type allow it. Directory permissions have different meanings: read permits "
        "listing directory entries, write permits creating or removing entries, and "
        "execute permits traversing or accessing entries when other permissions allow it."
    )

    subsection("Octal permissions")

    permissions = [
        ("0", "---", "no permission"),
        ("1", "--x", "execute"),
        ("2", "-w-", "write"),
        ("3", "-wx", "write + execute"),
        ("4", "r--", "read"),
        ("5", "r-x", "read + execute"),
        ("6", "rw-", "read + write"),
        ("7", "rwx", "read + write + execute"),
    ]

    for number, symbolic, meaning in permissions:
        print(f"{number}  {symbolic}  {meaning}")

    show_code(
        """
        chmod 755 script.sh

        7 = owner: rwx
        5 = group: r-x
        5 = others: r-x
        """
    )

    subsection("Ownership")

    explain(
        "Every filesystem object can have an owning user and group. Access checks "
        "consider the relevant permission class. Administrative operations may use "
        "root privileges, commonly obtained temporarily through sudo."
    )

    subsection("Hard links versus symbolic links")

    explain(
        "A hard link is another directory entry referring to the same underlying inode "
        "on filesystems that support it. A symbolic link is a separate filesystem object "
        "containing a path reference. Symbolic links can cross filesystem boundaries and "
        "can point to directories, but they can become dangling when the target disappears."
    )

    subsection("Safe Python demonstration of file metadata")

    with tempfile.TemporaryDirectory(prefix="linux-study-") as temporary_directory:
        directory = Path(temporary_directory)
        file_path = directory / "example.txt"
        file_path.write_text("Linux file demonstration\n", encoding="utf-8")

        metadata = file_path.stat()

        print(f"Temporary directory: {directory}")
        print(f"File: {file_path}")
        print(f"Size: {metadata.st_size} bytes")
        print(f"Permissions: {oct(metadata.st_mode & 0o777)}")
        print(f"User ID: {metadata.st_uid}")
        print(f"Group ID: {metadata.st_gid}")
        print(f"Modified time: {time.ctime(metadata.st_mtime)}")

        link_path = directory / "example-link.txt"
        try:
            link_path.symlink_to(file_path)
            print(f"Symbolic link created: {link_path}")
            print(f"Link resolves to: {link_path.resolve()}")
        except (OSError, NotImplementedError) as error:
            print(f"Symbolic link demonstration unavailable: {error}")


# ============================================================================
# 7. Shell syntax: quoting, expansion, pipes, redirection, wildcards
# ============================================================================

def section_shell_syntax() -> None:
    title("7. Shell syntax and command composition")

    subsection("Quoting")

    explain(
        "Shell quoting controls how special characters are interpreted. Single quotes "
        "usually preserve characters literally. Double quotes allow variable expansion "
        "and command substitution while preserving many other characters. Backslash can "
        "escape individual characters."
    )

    show_code(
        """
        name="Linux"
        echo "$name"

        echo '$name'

        echo "A path with spaces"

        printf '%s\\n' "safe text"
        """
    )

    subsection("Variables")

    show_code(
        """
        username="student"
        echo "$username"

        export APP_ENV="development"
        echo "$APP_ENV"
        """
    )

    subsection("Command substitution")

    show_code(
        """
        current_directory="$(pwd)"
        echo "$current_directory"
        """
    )

    explain(
        "Command substitution runs a command and substitutes its standard output into "
        "the surrounding command. The modern form $(command) is easier to nest and read "
        "than the older backtick form."
    )

    subsection("Pipes")

    explain(
        "A pipe connects the standard output of one process to the standard input of "
        "another. Pipes allow small programs to be combined into processing pipelines."
    )

    show_code(
        """
        ps aux | grep python
        """

    )

    subsection("Redirection")

    show_code(
        """
        command > output.txt
        command >> output.txt
        command < input.txt
        command 2> errors.txt
        command > output.txt 2>&1
        """

    )

    explain(
        "The standard streams are standard input (file descriptor 0), standard output "
        "(1), and standard error (2). Redirection changes where these streams go. A single "
        '>' generally replaces a destination file, while >> appends.'
    )

    subsection("Wildcards and globbing")

    show_code(
        """
        *.txt
        data-?.csv
        report-[0-9].txt
        """

    )

    explain(
        "Globbing is performed by the shell before many commands receive their arguments. "
        "It is different from regular expressions. For example, *.txt is a shell glob "
        "matching names ending in .txt, while ^.*\\.txt$ is a regular-expression pattern."
    )

    subsection("Why quoting matters")

    show_code(
        """
        filename="Annual Report.txt"

        # Correctly pass the complete filename as one argument:
        cat "$filename"

        # Without quotes, the shell may split the filename into two arguments:
        # cat $filename
        """

    )


# ============================================================================
# 8. Searching and text processing
# ============================================================================

def section_text_processing() -> None:
    title("8. Searching, filtering, and text processing")

    explain(
        "Linux administration relies heavily on text processing. Configuration files, "
        "logs, command output, and application data are frequently inspected through "
        "tools such as grep, sed, awk, sort, cut, tr, head, tail, and wc."
    )

    subsection("grep")

    show_code(
        """
        grep "ERROR" application.log
        grep -i "error" application.log
        grep -n "ERROR" application.log
        grep -R "database" /etc/myapp/
        """

    )

    subsection("Regular expressions")

    explain(
        "Regular expressions provide pattern matching. grep commonly supports basic "
        "regular expressions, while grep -E enables extended regular expressions. "
        "Regular expressions are distinct from shell globs."
    )

    show_code(
        r"""
        grep -E '^[0-9]+$' numbers.txt
        grep -E '^[A-Za-z_][A-Za-z0-9_]*$' identifiers.txt
        """

    )

    subsection("head, tail, and logs")

    show_code(
        """
        head -n 20 application.log
        tail -n 50 application.log
        tail -f application.log
        """

    )

    explain(
        "tail -f is commonly used to observe a growing log file. In production, log "
        "collection systems may be preferable to manually following individual files."
    )

    subsection("sort, uniq, and wc")

    show_code(
        """
        sort names.txt
        sort names.txt | uniq
        sort names.txt | uniq -c
        wc -l names.txt
        """

    )

    subsection("find")

    show_code(
        """
        find /var/log -type f -name "*.log"
        find . -type f -size +10M
        find . -type f -mtime -7
        """

    )

    explain(
        "find evaluates conditions against filesystem objects. It is powerful because "
        "conditions can be combined with actions. Destructive actions should be treated "
        "carefully, especially when paths contain spaces, unusual characters, or symbolic links."
    )


# ============================================================================
# 9. Processes and jobs
# ============================================================================

def section_processes() -> None:
    title("9. Processes, jobs, signals, and resource usage")

    explain(
        "A process is a running instance of a program. The kernel assigns each process "
        "a process ID (PID) and manages scheduling, memory, resources, credentials, "
        "signals, and relationships with other processes."
    )

    subsection("Important process concepts")

    process_terms = {
        "PID": "Process identifier.",
        "PPID": "Parent process identifier.",
        "Foreground process": "A process associated with the shell's current interactive job.",
        "Background process": "A process running without occupying the interactive foreground job slot.",
        "Exit status": "A numeric status returned when a process terminates; conventionally 0 means success.",
        "Signal": "A kernel-mediated notification sent to a process or process group.",
        "Zombie": "A terminated process whose exit status has not yet been collected by its parent.",
        "Daemon/service": "A long-running background process commonly providing a system or application service.",
    }

    for term, definition in process_terms.items():
        print(f"\n{term}:")
        explain(definition)

    subsection("Inspect processes")

    if linux_only():
        if command_exists("ps"):
            run_command(["ps", "aux"], timeout=5.0)

        if command_exists("uptime"):
            run_command(["uptime"])

        if command_exists("free"):
            run_command(["free", "-h"])

    subsection("Process tree")

    show_code(
        """
        systemd (PID 1)
          |
          +-- sshd
          |    +-- shell
          |         +-- python3
          |
          +-- application-service
               +-- worker
        """

    )

    subsection("Signals")

    signals = [
        ("SIGTERM", "Requests graceful termination."),
        ("SIGKILL", "Forces termination and cannot be caught or handled by the target."),
        ("SIGINT", "Commonly generated by Ctrl+C in an interactive terminal."),
        ("SIGHUP", "Historically associated with terminal hangup; often used by services to reload configuration."),
        ("SIGSTOP", "Stops a process; unlike ordinary signals, it cannot be caught or ignored."),
        ("SIGCONT", "Continues a stopped process."),
    ]

    for name, meaning in signals:
        print(f"{name:10} {meaning}")

    explain(
        "SIGTERM is generally preferable for graceful shutdown because applications can "
        "perform cleanup. SIGKILL should be reserved for situations in which graceful "
        "termination does not work."
    )

    subsection("Shell job control")

    show_code(
        """
        long_command &
        jobs
        fg
        bg
        Ctrl+C
        Ctrl+Z
        """

    )

    explain(
        "An ampersand starts a command as a background job in an interactive shell. "
        "Ctrl+C usually sends SIGINT to the foreground process group. Ctrl+Z commonly "
        "stops the foreground job, after which bg or fg can continue or foreground it."
    )


# ============================================================================
# 10. Environment and PATH
# ============================================================================

def section_environment() -> None:
    title("10. Environment variables, PATH, and shell environment")

    explain(
        "Environment variables are name-value pairs inherited by child processes. "
        "They are commonly used to configure applications, identify directories, "
        "select environments, and control program behavior."
    )

    subsection("Common variables")

    variables = [
        ("PATH", "Directories searched for executable commands."),
        ("HOME", "User's home directory."),
        ("USER", "Common variable identifying the current user."),
        ("SHELL", "Commonly records the user's configured shell."),
        ("PWD", "Current working directory in many shells."),
        ("LANG", "Locale configuration."),
        ("EDITOR", "Preferred command-line editor in many tools."),
    ]

    for name, meaning in variables:
        print(f"{name:10} {meaning}")

    subsection("PATH resolution")

    if linux_only():
        print(f"PATH = {os.environ.get('PATH', '')}")
        print(f"HOME = {os.environ.get('HOME', '')}")
        print(f"SHELL = {os.environ.get('SHELL', '')}")
        print(f"USER = {os.environ.get('USER', '')}")

    show_code(
        """
        echo "$PATH"
        command -v python3
        """

    )

    explain(
        "If a command is not found, check whether its executable directory appears in "
        "PATH. A common security principle is to avoid placing the current directory "
        "implicitly at the front of PATH on privileged systems."
    )

    subsection("Python environment access")

    print("\nPython sees environment variables through os.environ:")
    print(f"Current PATH exists: {'PATH' in os.environ}")
    print(f"Current HOME: {os.environ.get('HOME', '(not set)')}")


# ============================================================================
# 11. Package management
# ============================================================================

def section_packages() -> None:
    title("11. Software packages and APT")

    explain(
        "Package managers install, update, remove, and track software. On Ubuntu, "
        "APT is the high-level package-management system commonly used with Debian "
        "package repositories. Packages contain software and metadata such as versions, "
        "dependencies, and installation information."
    )

    subsection("APT vocabulary")

    terms = {
        "Repository": "A source from which packages and metadata can be obtained.",
        "Package": "A software distribution unit containing files and metadata.",
        "Dependency": "Another package or component required by software.",
        "APT": "High-level package-management interface used by Debian-based systems.",
        "dpkg": "Lower-level Debian package management system.",
        "Update": "Refreshes local repository metadata.",
        "Upgrade": "Installs newer versions of installed packages when available.",
    }

    for term, meaning in terms.items():
        print(f"\n{term}:")
        explain(meaning)

    subsection("Common APT commands")

    show_code(
        """
        sudo apt update
        sudo apt upgrade
        sudo apt install nginx
        sudo apt remove nginx
        apt search python3
        apt show python3
        """

    )

    explain(
        "sudo is important here because modifying the system package database normally "
        "requires administrative privileges. apt update downloads current repository "
        "metadata; it does not itself upgrade installed packages."
    )

    subsection("Why package managers matter")

    explain(
        "Manual software installation can create dependency conflicts, make updates "
        "harder, and complicate auditing. Distribution package managers provide a "
        "consistent mechanism for installation, updates, dependency resolution, and "
        "software inventory."
    )

    subsection("Security considerations")

    explain(
        "Package repositories should be trusted and configured correctly. Administrators "
        "should avoid blindly executing installation commands from untrusted sources. "
        "Production systems should have controlled update policies and should monitor "
        "security advisories relevant to their installed software."
    )

    if linux_only() and command_exists("apt"):
        subsection("Read-only package information")

        run_command(["apt", "--version"])
        result = run_command(["apt", "show", "bash"], timeout=5.0)
        if result and result.returncode == 0:
            pass


# ============================================================================
# 12. Users, groups, sudo, security
# ============================================================================

def section_users_security() -> None:
    title("12. Users, groups, root, sudo, and Linux security")

    explain(
        "Linux is a multi-user operating system. Users and groups form a basic part of "
        "its access-control model. The root account has extensive administrative authority, "
        "so ordinary work should generally be performed without root privileges."
    )

    subsection("Identity concepts")

    concepts = [
        ("User ID (UID)", "Numeric identity associated with a user account."),
        ("Group ID (GID)", "Numeric identity associated with a group."),
        ("Primary group", "The principal group associated with a user process."),
        ("Supplementary groups", "Additional groups whose permissions may be inherited."),
        ("root", "The traditional privileged administrative account, normally UID 0."),
        ("sudo", "A mechanism for running authorized commands with elevated privileges."),
    ]

    for name, meaning in concepts:
        print(f"{name:22} {meaning}")

    subsection("Identity inspection")

    if linux_only():
        run_command(["id"])
        run_command(["whoami"])
        run_command(["groups"])

    subsection("Principle of least privilege")

    explain(
        "Least privilege means granting only the permissions necessary for a task. "
        "Running every program as root increases the impact of bugs, compromised "
        "dependencies, malicious input, and accidental commands."
    )

    subsection("Common security mistakes")

    mistakes = [
        "Running unknown scripts with sudo.",
        "Using chmod 777 as a generic solution to permission problems.",
        "Storing passwords directly in shell history.",
        "Exposing SSH with weak authentication.",
        "Using the root account for routine application execution.",
        "Leaving unnecessary network services listening.",
        "Ignoring security updates.",
        "Using secrets directly in source-control repositories.",
        "Trusting filenames or input without validation.",
    ]

    for mistake in mistakes:
        print(f"- {mistake}")

    subsection("Password and secret handling")

    explain(
        "Secrets should be protected according to the deployment environment. Application "
        "credentials should not be committed to source control. Environment variables can "
        "be useful, but they are not automatically a secure secret-management system. "
        "Production environments often use dedicated secret-management facilities, access "
        "controls, rotation policies, and auditing."
    )


# ============================================================================
# 13. Networking
# ============================================================================

def section_networking() -> None:
    title("13. Linux networking fundamentals")

    explain(
        "Linux provides a complete networking stack. Common administration tasks include "
        "inspecting interfaces, addresses, routes, DNS configuration, listening sockets, "
        "and connectivity."
    )

    subsection("Core networking terms")

    terms = {
        "IP address": "Logical network address assigned to an interface.",
        "IPv4": "Internet Protocol version using 32-bit addresses.",
        "IPv6": "Internet Protocol version using 128-bit addresses.",
        "MAC address": "Link-layer hardware or virtual interface identifier.",
        "Subnet": "A logical division of an IP network.",
        "Default gateway": "Router used for traffic outside the local network.",
        "DNS": "System that maps names such as example.com to network records.",
        "TCP": "Connection-oriented transport protocol.",
        "UDP": "Connectionless transport protocol.",
        "Port": "Numeric endpoint identifier used by transport protocols.",
        "Socket": "Communication endpoint associated with an address and transport protocol.",
        "Route": "Rule describing where network traffic should be sent.",
    }

    for name, meaning in terms.items():
        print(f"\n{name}:")
        explain(meaning)

    subsection("Useful commands")

    show_code(
        """
        ip addr
        ip route
        ss -tulpn
        ping example.com
        curl https://example.com
        dig example.com
        """

    )

    explain(
        "Modern Linux systems commonly use the ip command for network configuration and "
        "inspection. ss is useful for examining sockets. curl is an application-level "
        "client for HTTP and many other protocols. ping tests IP-level reachability using "
        "ICMP where allowed, but failure does not always prove that a host is completely "
        "unreachable because firewalls may block ICMP."
    )

    subsection("Safe local networking demonstration")

    try:
        host_name = socket.gethostname()
        print(f"Hostname: {host_name}")
        addresses = socket.getaddrinfo(host_name, None)
        unique_addresses = sorted(
            {
                entry[4][0]
                for entry in addresses
                if entry[4] and entry[4][0]
            }
        )
        print(f"Resolved local addresses: {unique_addresses}")
    except socket.gaierror as error:
        print(f"Hostname lookup failed: {error}")


# ============================================================================
# 14. SSH and remote Linux
# ============================================================================

def section_ssh() -> None:
    title("14. SSH and remote Linux administration")

    explain(
        "SSH, or Secure Shell, provides encrypted remote communication. It is widely "
        "used to administer Linux servers, transfer files through related protocols, "
        "create secure tunnels, and automate remote operations."
    )

    subsection("Typical SSH workflow")

    show_code(
        """
        ssh username@server.example.com

        # Specify a private key:
        ssh -i ~/.ssh/id_ed25519 username@server.example.com

        # Copy a file:
        scp report.txt username@server.example.com:/home/username/
        """

    )

    subsection("SSH keys")

    explain(
        "Public-key authentication uses a key pair. The private key remains with the "
        "client and must be protected. The corresponding public key can be placed in "
        "the server user's authorized_keys configuration. Possession of a private key "
        "can provide access, so private keys should be protected with appropriate "
        "permissions and, when practical, passphrases."
    )

    subsection("SSH security practices")

    for practice in [
        "Use key-based authentication where appropriate.",
        "Protect private keys and avoid sharing them.",
        "Use strong authentication and account controls.",
        "Keep the SSH server and operating system updated.",
        "Restrict network exposure when possible.",
        "Monitor authentication logs.",
        "Avoid unnecessary direct root login.",
        "Use firewall rules and network controls appropriate to the environment.",
    ]:
        print(f"- {practice}")

    subsection("SSH is not the same as a terminal")

    explain(
        "SSH is a secure network protocol. A remote interactive session may provide a "
        "terminal connected to a shell, but SSH itself is the transport and authentication "
        "mechanism. Commands execute on the remote machine, not on the local computer."
    )


# ============================================================================
# 15. Cloud Linux servers
# ============================================================================

def section_cloud_linux() -> None:
    title("15. Linux servers in cloud environments")

    explain(
        "Cloud providers commonly offer virtual machines running Linux distributions. "
        "The basic operating-system concepts remain the same as on a local Linux machine, "
        "but the infrastructure is remotely managed and commonly automated."
    )

    subsection("Typical cloud server architecture")

    show_code(
        """
        User / Developer
              |
              | SSH / HTTPS
              v
        Cloud network
              |
              v
        Virtual machine
        +---------------------------+
        | Linux kernel              |
        | systemd / services        |
        | application               |
        | runtime                   |
        | filesystem                |
        +---------------------------+
              |
              v
        Cloud storage / database / other services
        """
    )

    subsection("Typical server setup sequence")

    steps = [
        "Create or provision a virtual machine.",
        "Select an operating-system image such as Ubuntu Server.",
        "Configure network access and firewall rules.",
        "Authenticate through SSH or another approved management mechanism.",
        "Update package metadata and security patches.",
        "Create or configure a non-root administrative user.",
        "Install application dependencies.",
        "Configure the application as a service.",
        "Configure logging and monitoring.",
        "Back up important data.",
        "Apply least-privilege and network-security controls.",
    ]

    for index, step in enumerate(steps, 1):
        print(f"{index:2}. {step}")

    subsection("Cloud-specific considerations")

    explain(
        "Cloud systems add concerns such as identity and access management, security "
        "groups or network policies, virtual networks, load balancers, object storage, "
        "managed databases, autoscaling, availability zones, snapshots, observability, "
        "and infrastructure automation. Linux administration remains the foundation "
        "inside the virtual machine."
    )

    subsection("Server versus desktop Linux")

    comparison = [
        ("Interface", "Desktop often uses GUI + terminal", "Server often primarily uses SSH + terminal"),
        ("Workload", "Interactive applications", "Services, APIs, databases, workloads"),
        ("Resource focus", "User experience and graphics", "Reliability, networking, compute, storage"),
        ("Administration", "Local user may manage system", "Remote and automated administration is common"),
        ("Uptime", "Often user-driven", "Often designed for continuous operation"),
    ]

    for category, desktop, server in comparison:
        print(f"\n{category}")
        print(f"  Desktop: {desktop}")
        print(f"  Server:  {server}")


# ============================================================================
# 16. systemd and services
# ============================================================================

def section_systemd() -> None:
    title("16. Services and systemd")

    explain(
        "systemd is a widely used Linux system and service manager. It can start services "
        "during boot, manage service lifecycles, track dependencies, provide logging through "
        "journald, and coordinate system targets."
    )

    subsection("Common systemctl operations")

    show_code(
        """
        systemctl status ssh
        sudo systemctl start nginx
        sudo systemctl stop nginx
        sudo systemctl restart nginx
        sudo systemctl enable nginx
        sudo systemctl disable nginx
        """

    )

    explain(
        "start and stop affect the current runtime state. enable and disable affect whether "
        "a service is configured to start automatically under the relevant boot target. "
        "restart stops and starts a service, while reload requests configuration reloading "
        "when the service supports it."
    )

    subsection("Inspecting services safely")

    if linux_only() and command_exists("systemctl"):
        run_command(["systemctl", "--version"])

        if Path("/run/systemd/system").exists():
            run_command(["systemctl", "is-system-running"])
        else:
            print("systemd is not the active init system in this environment.")

    subsection("Unit files")

    explain(
        "systemd manages units such as services, sockets, timers, mounts, and targets. "
        "A service unit describes how a long-running process should be started and managed."
    )


# ============================================================================
# 17. Logs and diagnostics
# ============================================================================

def section_logs() -> None:
    title("17. Logs, diagnostics, and troubleshooting")

    explain(
        "Troubleshooting is a systematic process of collecting evidence, narrowing the "
        "problem, testing hypotheses, and verifying the result. Linux systems expose "
        "information through logs, process state, resource metrics, network tools, and "
        "configuration files."
    )

    subsection("Diagnostic sequence")

    sequence = [
        "Define the symptom precisely.",
        "Determine when the problem started.",
        "Check whether the service or process is running.",
        "Check recent logs.",
        "Check CPU, memory, storage, and network resources.",
        "Check configuration changes.",
        "Check permissions and ownership.",
        "Check dependencies.",
        "Test connectivity where relevant.",
        "Apply the smallest justified change.",
        "Verify the result.",
        "Record the cause and corrective action.",
    ]

    for index, step in enumerate(sequence, 1):
        print(f"{index:2}. {step}")

    subsection("Useful diagnostic commands")

    show_code(
        """
        systemctl status service-name
        journalctl -u service-name
        journalctl -b
        dmesg
        ps aux
        top
        free -h
        df -h
        du -sh /path
        ss -tulpn
        ip addr
        ip route
        """

    )

    subsection("Common symptoms and first checks")

    diagnostics = [
        ("Command not found", "Check spelling, PATH, package installation, and executable permissions."),
        ("Permission denied", "Check user identity, ownership, permissions, ACLs, and filesystem mount options."),
        ("No space left on device", "Check df -h, inode usage, large files, logs, and application-generated data."),
        ("Application not reachable", "Check process/service status, listening sockets, firewall, DNS, and network routing."),
        ("High CPU", "Identify processes consuming CPU and determine whether the workload is expected."),
        ("High memory", "Inspect memory consumers, caches, swap, application behavior, and possible leaks."),
        ("Service starts then exits", "Inspect service status, logs, configuration, permissions, and dependencies."),
    ]

    for symptom, first_check in diagnostics:
        print(f"\n{symptom}:")
        explain(first_check)


# ============================================================================
# 18. Shell scripting
# ============================================================================

def section_shell_scripting() -> None:
    title("18. Bash shell scripting fundamentals")

    explain(
        "A shell script is a text file containing commands interpreted by a shell. "
        "Scripts automate repetitive administration and data-processing tasks. Good "
        "scripts validate inputs, quote variables, handle failures, and avoid dangerous "
        "assumptions."
    )

    subsection("Minimal Bash script")

    show_code(
        """
        #!/usr/bin/env bash
        set -euo pipefail

        name="Linux"
        printf 'Studying %s\\n' "$name"
        """

    )

    explain(
        "The shebang identifies the interpreter used when the script is executed directly. "
        "set -euo pipefail is a commonly used safety-oriented combination, although its "
        "exact behavior has important edge cases and should not be treated as a substitute "
        "for deliberate error handling."
    )

    subsection("Variables and arguments")

    show_code(
        """
        #!/usr/bin/env bash

        name="${1:-Guest}"
        printf 'Hello, %s\\n' "$name"
        """

    )

    subsection("Conditions")

    show_code(
        """
        if [[ -f "$file" ]]; then
            echo "Regular file exists"
        elif [[ -d "$file" ]]; then
            echo "Directory exists"
        else
            echo "Path does not exist"
        fi
        """

    )

    subsection("Loops")

    show_code(
        """
        for file in *.log; do
            [[ -e "$file" ]] || continue
            printf '%s\\n' "$file"
        done
        """

    )

    subsection("Functions")

    show_code(
        """
        check_file() {
            local file="$1"

            if [[ -f "$file" ]]; then
                printf '%s exists\\n' "$file"
                return 0
            fi

            printf '%s does not exist\\n' "$file"
            return 1
        }
        """

    )

    subsection("Shell scripting hazards")

    hazards = [
        "Unquoted variables can undergo word splitting and pathname expansion.",
        "rm and similar destructive commands require extreme care.",
        "Parsing ls output is unreliable for arbitrary filenames.",
        "Command output may contain spaces, tabs, newlines, or unusual characters.",
        "set -e has exceptions and does not eliminate the need for explicit error handling.",
        "Using eval can turn data into executable shell code and create command-injection risks.",
        "User-controlled strings should not be inserted into shell commands without careful handling.",
    ]

    for hazard in hazards:
        print(f"- {hazard}")


# ============================================================================
# 19. Python and Linux integration
# ============================================================================

def section_python_integration() -> None:
    title("19. Using Python with Linux")

    explain(
        "Python programs frequently run on Linux servers. Python can access files, "
        "environment variables, processes, sockets, and operating-system interfaces. "
        "The standard library is sufficient for many administration and automation tasks."
    )

    subsection("Filesystem operations with pathlib")

    with tempfile.TemporaryDirectory(prefix="python-linux-") as temporary_directory:
        root = Path(temporary_directory)
        logs = root / "logs"
        logs.mkdir()

        first_log = logs / "application.log"
        second_log = logs / "worker.log"

        first_log.write_text("INFO application started\nERROR database unavailable\n", encoding="utf-8")
        second_log.write_text("INFO worker started\nINFO worker stopped\n", encoding="utf-8")

        print(f"Working directory: {root}")
        print("Log files:")
        for path in sorted(logs.glob("*.log")):
            print(f"  {path.name}: {path.stat().st_size} bytes")

    subsection("Calling Linux commands from Python")

    explain(
        "The subprocess module can execute external programs. Passing a list of arguments "
        "and leaving shell=False as the default avoids unnecessary shell interpretation. "
        "If a program genuinely needs shell syntax such as pipes or redirection, that "
        "should be designed carefully and inputs must never be blindly interpolated."
    )

    if linux_only():
        run_command(["python3", "-c", "print('Python can launch another process')"])

    subsection("Safer subprocess example")

    show_code(
        """
        import subprocess

        result = subprocess.run(
            ["uname", "-s"],
            capture_output=True,
            text=True,
            check=True,
        )

        print(result.stdout.strip())
        """

    )

    subsection("Environment variables from Python")

    print(f"Python version: {sys.version.split()[0]}")
    print(f"Operating system: {platform.system()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Current working directory: {Path.cwd()}")
    print(f"PATH configured: {'PATH' in os.environ}")


# ============================================================================
# 20. Storage and filesystems
# ============================================================================

def section_storage() -> None:
    title("20. Storage, filesystems, mounts, and disk space")

    explain(
        "Linux can work with many filesystem types. A filesystem organizes persistent "
        "data into structures such as directories, inodes, metadata, and data blocks. "
        "A filesystem becomes accessible in the directory tree when it is mounted."
    )

    subsection("Important storage concepts")

    storage_terms = {
        "Block device": "Device interface commonly representing storage at block granularity.",
        "Partition": "A defined region of a storage device.",
        "Filesystem": "Data structure and rules used to organize files and metadata.",
        "Mount": "Attaching a filesystem to a directory in the filesystem tree.",
        "Unmount": "Detaching a mounted filesystem.",
        "Inode": "Filesystem metadata structure representing a file or related object.",
        "Free space": "Unused data blocks available to the filesystem.",
        "Inodes available": "Unused metadata structures available for new filesystem objects.",
    }

    for name, meaning in storage_terms.items():
        print(f"\n{name}:")
        explain(meaning)

    subsection("Disk space versus inode exhaustion")

    explain(
        "A filesystem can have free bytes but still fail to create files if it has "
        "exhausted its available inodes. This distinction is important when diagnosing "
        "errors such as 'No space left on device'."
    )

    if linux_only():
        if command_exists("df"):
            run_command(["df", "-h"])
            run_command(["df", "-i"])


# ============================================================================
# 21. Permissions laboratory
# ============================================================================

def section_permission_lab() -> None:
    title("21. Practical permissions laboratory")

    explain(
        "This laboratory uses a temporary directory created by Python. It demonstrates "
        "file modes without changing permanent system files."
    )

    with tempfile.TemporaryDirectory(prefix="permissions-lab-") as temporary_directory:
        root = Path(temporary_directory)
        private_file = root / "private.txt"
        public_file = root / "public.txt"

        private_file.write_text("Private demonstration data\n", encoding="utf-8")
        public_file.write_text("Public demonstration data\n", encoding="utf-8")

        try:
            private_file.chmod(0o600)
            public_file.chmod(0o644)
        except OSError as error:
            print(f"Could not change permissions: {error}")

        for path in [private_file, public_file]:
            mode = path.stat().st_mode & 0o777
            print(f"{path.name:15} mode={oct(mode)}")

        explain(
            "Mode 600 normally means the owner can read and write while group and "
            "other users have no permissions. Mode 644 normally means the owner can "
            "read and write while group and other users can read."
        )


# ============================================================================
# 22. Performance
# ============================================================================

def section_performance() -> None:
    title("22. Linux performance fundamentals")

    explain(
        "Performance analysis should measure the actual bottleneck rather than relying "
        "on assumptions. CPU, memory, storage, and networking can each become limiting "
        "resources."
    )

    subsection("Four broad resource categories")

    resources = [
        ("CPU", "Compute capacity, scheduling, load, and per-process CPU consumption."),
        ("Memory", "RAM usage, caches, buffers, virtual memory, and swap."),
        ("Storage", "Capacity, I/O throughput, IOPS, latency, and filesystem behavior."),
        ("Network", "Bandwidth, latency, packet loss, connections, and socket capacity."),
    ]

    for resource, description in resources:
        print(f"\n{resource}:")
        explain(description)

    subsection("Load average")

    explain(
        "Linux load average represents the number of tasks that are runnable or waiting "
        "for certain uninterruptible resources. It is not simply a CPU utilization percentage. "
        "Interpretation depends on the number of CPU cores and the workload."
    )

    if linux_only():
        if command_exists("uptime"):
            run_command(["uptime"])

        if command_exists("free"):
            run_command(["free", "-h"])

    subsection("Performance principles")

    for principle in [
        "Measure before optimizing.",
        "Identify the bottleneck first.",
        "Distinguish average behavior from latency spikes.",
        "Monitor resource saturation and errors together.",
        "Avoid premature optimization.",
        "Test performance under representative workloads.",
        "Consider cost, complexity, reliability, and maintainability alongside raw speed.",
    ]:
        print(f"- {principle}")


# ============================================================================
# 23. Security and production considerations
# ============================================================================

def section_production_security() -> None:
    title("23. Production Linux: reliability and security")

    subsection("Baseline production controls")

    controls = [
        "Keep the operating system and packages patched.",
        "Use least-privilege accounts.",
        "Use SSH keys or another strong authentication mechanism.",
        "Restrict unnecessary network exposure.",
        "Use firewalls and security groups appropriately.",
        "Store secrets securely.",
        "Centralize or reliably retain important logs.",
        "Monitor service health and system resources.",
        "Back up important data and test restoration.",
        "Document configuration and operational procedures.",
        "Automate repeatable infrastructure changes.",
        "Test changes before production deployment.",
        "Use change management appropriate to the environment.",
    ]

    for control in controls:
        print(f"- {control}")

    subsection("Defense in depth")

    explain(
        "No single security mechanism should be expected to protect an entire system. "
        "A practical Linux deployment can combine identity controls, file permissions, "
        "application authentication, network filtering, patch management, logging, "
        "monitoring, backups, segmentation, and secure configuration."
    )

    subsection("Availability and reliability")

    explain(
        "A server being reachable is not the same as an application being reliable. "
        "Production reliability includes correct startup behavior, dependency management, "
        "resource capacity, graceful failure, restart behavior, backups, observability, "
        "and recovery procedures."
    )


# ============================================================================
# 24. Common mistakes and edge cases
# ============================================================================

def section_mistakes() -> None:
    title("24. Common Linux mistakes and edge cases")

    mistakes = [
        (
            "Confusing Linux with a distribution",
            "Linux is the kernel; Ubuntu, Debian, Fedora, and others are distributions.",
        ),
        (
            "Confusing terminal with shell",
            "The terminal emulator hosts an interactive shell; they are different components.",
        ),
        (
            "Using sudo for everything",
            "Privilege should be elevated only when needed.",
        ),
        (
            "Using chmod 777",
            "This often grants unnecessary access instead of solving the underlying ownership or permission issue.",
        ),
        (
            "Forgetting spaces in paths",
            "Quote paths such as \"$HOME/My Documents/report.txt\".",
        ),
        (
            "Confusing globbing and regular expressions",
            "*.txt is a shell glob; it is not equivalent to a regular expression.",
        ),
        (
            "Ignoring exit status",
            "A command can fail while producing useful-looking output.",
        ),
        (
            "Assuming ping proves application health",
            "ICMP reachability does not prove that the application port or service is working.",
        ),
        (
            "Deleting files without verifying paths",
            "Shell expansion can transform a short command into many unintended arguments.",
        ),
        (
            "Editing system files without backups",
            "A configuration mistake can prevent services or even system components from operating correctly.",
        ),
        (
            "Hard-coding cloud IP addresses",
            "Cloud resources may change; DNS, service discovery, or managed infrastructure may be more appropriate.",
        ),
        (
            "Treating logs as the only diagnostic source",
            "Process state, resources, network state, configuration, and filesystem state may also matter.",
        ),
    ]

    for mistake, explanation in mistakes:
        print(f"\n{mistake}:")
        explain(explanation)


# ============================================================================
# 25. Linux command exit status
# ============================================================================

def section_exit_status() -> None:
    title("25. Exit status and reliable automation")

    explain(
        "Unix-like programs conventionally return status code 0 for success and a "
        "non-zero value for failure. Shell scripts can use this status in conditions "
        "and automation."
    )

    if linux_only():
        if command_exists("true"):
            run_command(["true"])

        if command_exists("false"):
            run_command(["false"])

    subsection("Shell examples")

    show_code(
        """
        if command; then
            echo "Success"
        else
            echo "Failure"
        fi

        command
        status=$?
        printf 'Exit status: %s\\n' "$status"
        """

    )

    subsection("Python equivalent")

    show_code(
        """
        import subprocess

        result = subprocess.run(["true"], check=False)

        if result.returncode == 0:
            print("Success")
        else:
            print("Failure")
        """

    )

    explain(
        "Reliable automation checks explicit outcomes instead of assuming that a command "
        "worked because it printed something. subprocess.run(check=True) is useful when "
        "a non-zero exit status should immediately raise CalledProcessError."
    )


# ============================================================================
# 26. Linux environment inspection
# ============================================================================

def section_system_inspection() -> None:
    title("26. System inspection laboratory")

    if not linux_only():
        explain(
            "The following inspection commands are specific to Linux and are therefore "
            "not executed on this host."
        )
        return

    checks: list[tuple[str, list[str]]] = [
        ("Kernel", ["uname", "-r"]),
        ("Kernel architecture", ["uname", "-m"]),
        ("Hostname", ["hostname"]),
        ("Current user", ["whoami"]),
        ("Identity", ["id"]),
        ("Working directory", ["pwd"]),
        ("Uptime", ["uptime"]),
        ("Disk space", ["df", "-h"]),
    ]

    for label, command in checks:
        subsection(label)
        if command_exists(command[0]):
            run_command(command)

    if command_exists("free"):
        subsection("Memory")
        run_command(["free", "-h"])

    if command_exists("ip"):
        subsection("Network addresses")
        run_command(["ip", "addr", "show"])

    if command_exists("ip"):
        subsection("Routing table")
        run_command(["ip", "route", "show"])


# ============================================================================
# 27. A miniature Linux administration simulation
# ============================================================================

class LinuxServerSimulation:
    """
    A simple in-memory simulation of common server concepts.

    This does not modify the operating system. It is designed to connect
    abstract Linux concepts with practical administration decisions.
    """

    def __init__(self, hostname: str, memory_gb: float, disk_gb: float) -> None:
        self.hostname = hostname
        self.memory_gb = memory_gb
        self.disk_gb = disk_gb
        self.services: dict[str, str] = {}
        self.users: set[str] = set()
        self.open_ports: set[int] = set()
        self.logs: list[str] = []

    def add_user(self, username: str) -> None:
        if not username or username.isspace():
            raise ValueError("Username cannot be empty.")
        self.users.add(username)
        self.logs.append(f"user created: {username}")

    def install_service(self, service: str, port: Optional[int] = None) -> None:
        if not service:
            raise ValueError("Service name cannot be empty.")

        self.services[service] = "installed"

        if port is not None:
            if not 1 <= port <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
            self.open_ports.add(port)

        self.logs.append(f"service installed: {service}")

    def start_service(self, service: str) -> None:
        if service not in self.services:
            raise KeyError(f"Service is not installed: {service}")

        self.services[service] = "running"
        self.logs.append(f"service started: {service}")

    def stop_service(self, service: str) -> None:
        if service not in self.services:
            raise KeyError(f"Service is not installed: {service}")

        self.services[service] = "stopped"
        self.logs.append(f"service stopped: {service}")

    def status(self) -> dict[str, object]:
        return {
            "hostname": self.hostname,
            "memory_gb": self.memory_gb,
            "disk_gb": self.disk_gb,
            "users": sorted(self.users),
            "services": dict(self.services),
            "open_ports": sorted(self.open_ports),
            "log_count": len(self.logs),
        }


def section_server_simulation() -> None:
    title("27. Linux server administration simulation")

    explain(
        "This simulation models users, services, ports, resources, and logs. It is "
        "not a replacement for a real Linux server. Its purpose is to demonstrate "
        "how an administrator thinks about system state."
    )

    server = LinuxServerSimulation(
        hostname="ubuntu-server",
        memory_gb=8,
        disk_gb=80,
    )

    server.add_user("administrator")
    server.add_user("developer")

    server.install_service("nginx", port=80)
    server.install_service("application", port=8000)

    server.start_service("nginx")
    server.start_service("application")

    print("\nServer state:")
    for key, value in server.status().items():
        print(f"{key}: {value}")

    print("\nAdministrative log:")
    for entry in server.logs:
        print(f"  {entry}")


# ============================================================================
# 28. Practical automation example
# ============================================================================

def analyze_directory(path: Path) -> dict[str, int]:
    """
    Analyze a directory recursively without deleting or modifying anything.

    Returns:
        files: number of regular files
        directories: number of directories
        bytes: total size of regular files that can be stat'ed
    """
    files = 0
    directories = 0
    total_bytes = 0

    for current_path in path.rglob("*"):
        try:
            if current_path.is_dir():
                directories += 1
            elif current_path.is_file():
                files += 1
                total_bytes += current_path.stat().st_size
        except OSError:
            # A real administration tool should log inaccessible paths rather
            # than silently ignoring them. The example keeps the interface simple.
            continue

    return {
        "files": files,
        "directories": directories,
        "bytes": total_bytes,
    }


def section_automation() -> None:
    title("28. Practical Linux automation with Python")

    explain(
        "Automation is valuable when a task is repeated, predictable, and sufficiently "
        "well-defined. A good automation script should be idempotent when practical, "
        "validate inputs, handle errors, produce useful logs, and avoid destructive "
        "behavior unless explicitly required."
    )

    with tempfile.TemporaryDirectory(prefix="automation-lab-") as temporary_directory:
        root = Path(temporary_directory)

        (root / "logs").mkdir()
        (root / "data").mkdir()

        (root / "logs" / "app.log").write_text("INFO\nERROR\n", encoding="utf-8")
        (root / "logs" / "worker.log").write_text("INFO\n", encoding="utf-8")
        (root / "data" / "records.csv").write_text("id,name\n1,Alice\n", encoding="utf-8")

        result = analyze_directory(root)

        print(f"Directory: {root}")
        print(f"Files: {result['files']}")
        print(f"Directories: {result['directories']}")
        print(f"Total bytes: {result['bytes']}")

    subsection("Automation design principles")

    principles = [
        "Validate inputs.",
        "Prefer explicit paths.",
        "Quote shell variables when writing shell scripts.",
        "Avoid shell=True in Python unless shell features are actually required.",
        "Use dry-run modes for potentially destructive automation.",
        "Log important actions.",
        "Return meaningful exit statuses.",
        "Make repeated execution safe when possible.",
        "Handle partial failures.",
        "Test against unusual filenames and permissions.",
    ]

    for principle in principles:
        print(f"- {principle}")


# ============================================================================
# 29. Containers and Linux
# ============================================================================

def section_containers() -> None:
    title("29. Linux and containers")

    explain(
        "Containers are closely connected to Linux kernel capabilities such as namespaces "
        "and control groups. A container is not normally a complete virtual machine. "
        "Containers generally share the host kernel while providing process, filesystem, "
        "network, and resource isolation."
    )

    subsection("Virtual machine versus container")

    comparisons = [
        ("Kernel", "VM generally runs its own guest kernel", "Containers share the host kernel"),
        ("Isolation", "Hardware-level virtualization boundary", "Kernel-level isolation mechanisms"),
        ("Startup", "Usually heavier and slower", "Usually lightweight and fast"),
        ("Operating system", "Full guest OS is typical", "Container image usually contains user-space filesystem"),
        ("Use cases", "Strong isolation, different kernels/OS environments", "Application packaging and scalable workloads"),
    ]

    for category, virtual_machine, container in comparisons:
        print(f"\n{category}")
        print(f"  VM:        {virtual_machine}")
        print(f"  Container: {container}")

    subsection("Linux primitives involved")

    for primitive, meaning in [
        ("Namespaces", "Isolate views of processes, networks, mounts, users, and other resources."),
        ("cgroups", "Control and account for resource usage such as CPU and memory."),
        ("Capabilities", "Split aspects of root privilege into more granular permissions."),
        ("Union/overlay filesystems", "Support layered filesystem representations commonly used by container systems."),
    ]:
        print(f"\n{primitive}:")
        explain(meaning)


# ============================================================================
# 30. Linux architecture review quiz
# ============================================================================

def section_quiz() -> None:
    title("30. Knowledge check")

    questions = [
        (
            "What is Linux?",
            "The Linux kernel is the core kernel; a complete Linux environment also includes user-space components."
        ),
        (
            "What is Ubuntu?",
            "A Linux distribution based on Debian and commonly using APT and DEB packages."
        ),
        (
            "What is Bash?",
            "A shell that interprets commands and provides shell programming features."
        ),
        (
            "What does / mean?",
            "The root of the Linux filesystem hierarchy."
        ),
        (
            "What does sudo do?",
            "It runs an authorized command with elevated privileges."
        ),
        (
            "What is a PID?",
            "A process identifier assigned to a running process."
        ),
        (
            "What does a pipe do?",
            "It connects one command's standard output to another command's standard input."
        ),
        (
            "What is SSH?",
            "A secure protocol for remote login and other encrypted communication."
        ),
        (
            "What is APT?",
            "A high-level package-management system commonly used on Debian-based distributions."
        ),
        (
            "Why is least privilege important?",
            "It reduces the impact of mistakes, vulnerabilities, and unauthorized actions."
        ),
    ]

    for question, answer in questions:
        print(f"\nQuestion: {question}")
        print(f"Answer:   {answer}")


# ============================================================================
# 31. Safe command reference
# ============================================================================

def section_command_reference() -> None:
    title("31. Practical Linux command reference")

    reference = [
        ("pwd", "Show current directory", "pwd"),
        ("ls -la", "List detailed directory contents including hidden entries", "ls -la"),
        ("cd /path", "Change directory", "cd /var/log"),
        ("mkdir -p path", "Create directories including missing parents", "mkdir -p project/data"),
        ("touch file", "Create file or update timestamp", "touch notes.txt"),
        ("cp source destination", "Copy a file", "cp source.txt backup.txt"),
        ("mv source destination", "Move or rename", "mv old.txt new.txt"),
        ("cat file", "Display a small text file", "cat notes.txt"),
        ("less file", "Read a file interactively", "less application.log"),
        ("head file", "Display beginning", "head notes.txt"),
        ("tail file", "Display end", "tail application.log"),
        ("grep pattern file", "Search text", "grep ERROR application.log"),
        ("find path ...", "Search filesystem objects", "find . -type f -name '*.txt'"),
        ("chmod mode file", "Change permissions", "chmod 640 report.txt"),
        ("chown user:group file", "Change ownership", "sudo chown user:group file"),
        ("ps aux", "List processes", "ps aux"),
        ("kill PID", "Send a signal to a process", "kill 1234"),
        ("df -h", "Show filesystem capacity", "df -h"),
        ("du -sh path", "Estimate path usage", "du -sh /var/log"),
        ("ip addr", "Inspect network addresses", "ip addr"),
        ("ip route", "Inspect routing", "ip route"),
        ("ss -tulpn", "Inspect listening/network sockets", "ss -tulpn"),
        ("systemctl status service", "Inspect a service", "systemctl status ssh"),
        ("journalctl -u service", "Inspect service logs", "journalctl -u ssh"),
    ]

    print(f"{'Command':30} {'Purpose':45} Example")
    print("-" * WIDTH)

    for command, purpose, example in reference:
        print(f"{command:30} {purpose:45} {example}")


# ============================================================================
# 32. Final system report
# ============================================================================

def section_final_report() -> None:
    title("32. Current environment report")

    report = {
        "Operating system": platform.system(),
        "OS release": platform.release(),
        "Architecture": platform.machine(),
        "Python": platform.python_version(),
        "Hostname": socket.gethostname(),
        "Working directory": str(Path.cwd()),
        "Linux host": linux_only(),
        "Bash available": command_exists("bash"),
        "SSH client available": command_exists("ssh"),
        "Git available": command_exists("git"),
        "Python 3 executable": shutil.which("python3") or shutil.which("python") or "not found",
    }

    for name, value in report.items():
        print(f"{name:24}: {value}")

    explain(
        "This report demonstrates an important Linux administration habit: establish "
        "the environment before making assumptions. Operating-system version, architecture, "
        "available commands, privileges, filesystem layout, and active services can affect "
        "the correct command or troubleshooting approach."
    )


# ============================================================================
# Main program
# ============================================================================

def main() -> None:
    """Run the complete Linux learning program."""
    print("=" * WIDTH)
    print("INTRODUCTION TO LINUX")
    print("=" * WIDTH)
    explain(
        "This program is a standalone practical study guide covering Linux fundamentals "
        "through introductory server and production administration concepts. Most live "
        "commands are read-only. The demonstrations are designed to be safe on a normal "
        "development system."
    )

    sections: list[Callable[[], None]] = [
        section_history,
        section_architecture,
        section_distributions,
        section_command_line,
        section_filesystem,
        section_files_permissions,
        section_shell_syntax,
        section_text_processing,
        section_processes,
        section_environment,
        section_packages,
        section_users_security,
        section_networking,
        section_ssh,
        section_cloud_linux,
        section_systemd,
        section_logs,
        section_shell_scripting,
        section_python_integration,
        section_storage,
        section_permission_lab,
        section_performance,
        section_production_security,
        section_mistakes,
        section_exit_status,
        section_system_inspection,
        section_server_simulation,
        section_automation,
        section_containers,
        section_quiz,
        section_command_reference,
        section_final_report,
    ]

    for section in sections:
        try:
            section()
        except KeyboardInterrupt:
            print("\n\nExecution interrupted by the user.")
            return
        except Exception as error:
            print(f"\nSection error: {type(error).__name__}: {error}")
            print("The program will continue with the remaining sections.")

    title("End of Linux study program")
    explain(
        "The examples covered Linux as a complete operating environment: its history, "
        "kernel architecture, distributions, Ubuntu, terminal and shell usage, filesystem "
        "management, permissions, processes, networking, package management, SSH, cloud "
        "servers, services, logs, automation, security, performance, and containers."
    )


if __name__ == "__main__":
    main()
