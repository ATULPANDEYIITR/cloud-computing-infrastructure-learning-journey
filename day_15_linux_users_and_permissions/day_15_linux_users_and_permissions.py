"""
Linux Users and Permissions
===========================

A standalone study and demonstration program covering:

- Users and user identities
- Groups and supplementary groups
- UID/GID concepts
- /etc/passwd and /etc/group
- File ownership
- rwx permissions
- Numeric and symbolic permission notation
- Directory permissions
- Special permissions: setuid, setgid, sticky bit
- sudo and privilege separation
- Access-control decisions
- umask
- ACL concepts and practical inspection
- Permission inheritance
- Common permission failures
- Security principles
- Debugging and auditing
- Linux command demonstrations

The script is designed to run on Linux. Most educational demonstrations also
work on other Unix-like systems. System-changing operations are intentionally
not performed automatically.
"""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# 1. Fundamental terminology
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_identity_basics() -> None:
    print_section("1. User and group identity")

    uid = os.getuid() if hasattr(os, "getuid") else None
    gid = os.getgid() if hasattr(os, "getgid") else None
    euid = os.geteuid() if hasattr(os, "geteuid") else None
    egid = os.getegid() if hasattr(os, "getegid") else None

    print("UID  :", uid)
    print("GID  :", gid)
    print("EUID :", euid)
    print("EGID :", egid)

    if uid is not None:
        try:
            current_user = pwd.getpwuid(uid)
            print("Login name:", current_user.pw_name)
            print("Home      :", current_user.pw_dir)
            print("Shell     :", current_user.pw_shell)
        except KeyError:
            print("The current UID has no local passwd entry.")

    if hasattr(os, "getgroups"):
        print("Supplementary group IDs:", os.getgroups())

    print(
        """
A Linux process normally has a real identity and an effective identity.

UID:
  Identifies a user account.

GID:
  Identifies the process's primary group.

Supplementary groups:
  Additional groups that may grant access.

EUID:
  The effective UID is especially important when the kernel evaluates
  permissions and when a process is running with elevated privileges.

Root:
  UID 0 conventionally represents the superuser. Root bypasses many ordinary
  permission checks, although modern Linux security mechanisms such as
  capabilities, namespaces, SELinux, AppArmor, seccomp, and containers can
  impose additional restrictions.
"""
    )


# ---------------------------------------------------------------------------
# 2. passwd and group databases
# ---------------------------------------------------------------------------

def inspect_account_databases() -> None:
    print_section("2. Users and groups from the system databases")

    print("First five passwd entries:")
    try:
        for index, account in enumerate(pwd.getpwall()):
            if index == 5:
                break
            print(
                f"  name={account.pw_name!r}, uid={account.pw_uid}, "
                f"gid={account.pw_gid}, home={account.pw_dir!r}, "
                f"shell={account.pw_shell!r}"
            )
    except PermissionError as exc:
        print("Cannot inspect passwd database:", exc)

    print("\nFirst five group entries:")
    try:
        for index, group in enumerate(grp.getgrall()):
            if index == 5:
                break
            print(
                f"  name={group.gr_name!r}, gid={group.gr_gid}, "
                f"members={group.gr_mem}"
            )
    except PermissionError as exc:
        print("Cannot inspect group database:", exc)

    print(
        """
Traditional local account databases are commonly:

  /etc/passwd
  /etc/group

Passwords are normally not stored directly in /etc/passwd on modern systems.
Password hashes are commonly stored in /etc/shadow, which is deliberately
more restricted.

Real systems can obtain identities from other sources through NSS
(Name Service Switch), such as LDAP, Active Directory integrations, or other
identity services.
"""
    )


# ---------------------------------------------------------------------------
# 3. Permission model
# ---------------------------------------------------------------------------

PERMISSION_BITS = {
    "r": 4,
    "w": 2,
    "x": 1,
}


@dataclass(frozen=True)
class PermissionSet:
    read: bool = False
    write: bool = False
    execute: bool = False

    @property
    def numeric(self) -> int:
        return (
            (4 if self.read else 0)
            + (2 if self.write else 0)
            + (1 if self.execute else 0)
        )

    @property
    def symbolic(self) -> str:
        return (
            ("r" if self.read else "-")
            + ("w" if self.write else "-")
            + ("x" if self.execute else "-")
        )


def permission_set_from_digit(digit: int) -> PermissionSet:
    if digit < 0 or digit > 7:
        raise ValueError("Permission digit must be between 0 and 7.")
    return PermissionSet(
        read=bool(digit & 4),
        write=bool(digit & 2),
        execute=bool(digit & 1),
    )


def explain_numeric_permissions(mode: int) -> str:
    if mode < 0 or mode > 7:
        raise ValueError("Mode must be between 000 and 777.")

    owner = permission_set_from_digit((mode // 100) % 10)
    group = permission_set_from_digit((mode // 10) % 10)
    other = permission_set_from_digit(mode % 10)

    return (
        f"{mode:03d}: "
        f"owner={owner.symbolic} ({owner.numeric}), "
        f"group={group.symbolic} ({group.numeric}), "
        f"other={other.symbolic} ({other.numeric})"
    )


def demonstrate_permission_notation() -> None:
    print_section("3. rwx permissions and numeric notation")

    examples = [0, 4, 5, 6, 7, 640, 644, 700, 750, 755, 770, 777]

    for mode in examples:
        print(explain_numeric_permissions(mode))

    print(
        """
The three ordinary permission classes are:

  user/owner
  group
  others

The three ordinary permission bits are:

  r = read
  w = write
  x = execute

For a regular file:
  read    -> read file contents
  write   -> modify file contents
  execute -> execute the file as a program, subject to other restrictions

For a directory:
  read    -> list directory entries
  write   -> create/remove/rename directory entries, subject to directory
             execute/search permission and sticky-bit rules
  execute -> search/traverse the directory

This difference is critical. Directory execute permission does not mean
"execute the directory as a program." It means the process can traverse/search
it.

Examples:
  644 = rw-r--r--
  755 = rwxr-xr-x
  700 = rwx------
  750 = rwxr-x---
"""
    )


# ---------------------------------------------------------------------------
# 4. Demonstrating the kernel's basic permission selection
# ---------------------------------------------------------------------------

@dataclass
class Subject:
    uid: int
    primary_gid: int
    supplementary_gids: set[int]


@dataclass
class FileSecurity:
    owner_uid: int
    group_gid: int
    owner_permissions: PermissionSet
    group_permissions: PermissionSet
    other_permissions: PermissionSet


def permission_class_for(
    subject: Subject,
    security: FileSecurity,
) -> str:
    """
    Simplified model of ordinary UNIX permission-class selection.

    Important rule:
    If the subject is the file owner, owner permissions are selected.
    Otherwise, if the subject belongs to the file's group, group permissions
    are selected. Otherwise, other permissions are selected.

    This is intentionally a teaching model and does not attempt to reproduce
    every Linux security layer such as ACLs, capabilities, LSMs, namespaces,
    or mount options.
    """
    if subject.uid == security.owner_uid:
        return "owner"

    if (
        subject.primary_gid == security.group_gid
        or security.group_gid in subject.supplementary_gids
    ):
        return "group"

    return "other"


def basic_permission_allowed(
    subject: Subject,
    security: FileSecurity,
    requested: str,
) -> bool:
    selected_class = permission_class_for(subject, security)

    permission_map = {
        "owner": security.owner_permissions,
        "group": security.group_permissions,
        "other": security.other_permissions,
    }

    selected = permission_map[selected_class]

    for operation in requested:
        if operation == "r" and not selected.read:
            return False
        if operation == "w" and not selected.write:
            return False
        if operation == "x" and not selected.execute:
            return False

    return True


def demonstrate_permission_algorithm() -> None:
    print_section("4. Basic permission decision algorithm")

    alice = Subject(uid=1001, primary_gid=2001, supplementary_gids={3001})
    security = FileSecurity(
        owner_uid=1001,
        group_gid=3001,
        owner_permissions=PermissionSet(read=True, write=True),
        group_permissions=PermissionSet(read=True),
        other_permissions=PermissionSet(),
    )

    for requested in ("r", "w", "rw", "x"):
        print(
            f"Alice requesting {requested!r}:",
            basic_permission_allowed(alice, security, requested),
            "selected class:",
            permission_class_for(alice, security),
        )

    bob = Subject(uid=1002, primary_gid=2002, supplementary_gids={3001})

    print(
        "Bob requesting read:",
        basic_permission_allowed(bob, security, "r"),
        "selected class:",
        permission_class_for(bob, security),
    )

    charlie = Subject(uid=1003, primary_gid=2003, supplementary_gids=set())

    print(
        "Charlie requesting read:",
        basic_permission_allowed(charlie, security, "r"),
        "selected class:",
        permission_class_for(charlie, security),
    )

    print(
        """
This simplified model demonstrates why chmod 640 is meaningful:

  6 -> owner can read/write
  4 -> group can read
  0 -> everyone else has no ordinary permissions

A subtle but important rule is that group membership does not combine with
owner permissions. If the process is the owner, the owner class is selected.
"""
    )


# ---------------------------------------------------------------------------
# 5. Real filesystem metadata
# ---------------------------------------------------------------------------

def mode_to_human(mode: int) -> str:
    return stat.filemode(mode)


def inspect_path(path: Path) -> None:
    print_section(f"5. Filesystem metadata: {path}")

    try:
        information = path.stat()
    except FileNotFoundError:
        print("Path does not exist.")
        return
    except PermissionError:
        print("Permission denied while reading metadata.")
        return

    print("File mode :", mode_to_human(information.st_mode))
    print("Octal mode:", oct(stat.S_IMODE(information.st_mode)))
    print("UID       :", information.st_uid)
    print("GID       :", information.st_gid)
    print("Size      :", information.st_size, "bytes")
    print("Inode     :", information.st_ino)

    try:
        owner = pwd.getpwuid(information.st_uid).pw_name
    except KeyError:
        owner = "<unknown>"

    try:
        group = grp.getgrgid(information.st_gid).gr_name
    except KeyError:
        group = "<unknown>"

    print("Owner     :", owner)
    print("Group     :", group)


# ---------------------------------------------------------------------------
# 6. Safe temporary filesystem demonstrations
# ---------------------------------------------------------------------------

def demonstrate_chmod_and_metadata() -> None:
    print_section("6. chmod and filesystem permission changes")

    with tempfile.TemporaryDirectory(prefix="linux_permissions_") as directory:
        directory_path = Path(directory)
        file_path = directory_path / "report.txt"

        file_path.write_text("Confidential project report\n", encoding="utf-8")

        print("Initial:")
        inspect_path(file_path)

        # 640 means owner rw, group r, others none.
        os.chmod(file_path, 0o640)

        print("\nAfter chmod 640:")
        inspect_path(file_path)

        # Add execute permission for owner only.
        os.chmod(file_path, 0o740)

        print("\nAfter chmod 740:")
        inspect_path(file_path)

        # Return to a conservative non-executable data-file mode.
        os.chmod(file_path, 0o640)

        print("\nFinal safe data-file mode: 640")

    print(
        """
Python's os.chmod() changes the mode bits on systems that implement POSIX
permissions.

The operation changes permissions, not ownership.

Ownership is normally changed with chown/chgrp commands or corresponding
system APIs, and those operations generally require appropriate privileges.
"""
    )


# ---------------------------------------------------------------------------
# 7. Files versus directories
# ---------------------------------------------------------------------------

def demonstrate_directory_permissions() -> None:
    print_section("7. File permissions versus directory permissions")

    with tempfile.TemporaryDirectory(prefix="directory_permissions_") as directory:
        root = Path(directory)
        nested = root / "nested"
        nested.mkdir()

        data = nested / "data.txt"
        data.write_text("directory permission demonstration\n", encoding="utf-8")

        os.chmod(nested, 0o700)

        print("Directory:")
        inspect_path(nested)

        print("File:")
        inspect_path(data)

        print(
            """
A directory normally needs execute/search permission to access entries by
path. Therefore:

  drwx------  -> owner can list, create/delete, and traverse
  d-wx------  -> owner may manipulate known entries but cannot list normally
  dr-x------  -> owner can list and traverse but cannot create/delete

The permissions of every relevant parent directory matter. A file with mode
777 can still be inaccessible if a parent directory cannot be traversed.
"""
        )


# ---------------------------------------------------------------------------
# 8. umask
# ---------------------------------------------------------------------------

def demonstrate_umask_math() -> None:
    print_section("8. umask")

    requested_file_mode = 0o666
    requested_directory_mode = 0o777

    examples = [0o022, 0o027, 0o077]

    for mask in examples:
        file_result = requested_file_mode & ~mask
        directory_result = requested_directory_mode & ~mask

        print(
            f"umask {mask:03o}: "
            f"new file -> {file_result:03o}, "
            f"new directory -> {directory_result:03o}"
        )

    print(
        """
umask is a permission mask applied when programs create new filesystem
objects.

Typical requested defaults are approximately:

  files:       666
  directories: 777

A process umask removes permission bits.

For example:
  666 & ~022 = 644
  777 & ~022 = 755

umask does not normally add permissions. It restricts requested defaults.

A common mistake is expecting umask to retroactively change existing files.
It does not.
"""
    )


# ---------------------------------------------------------------------------
# 9. Symbolic chmod explanation
# ---------------------------------------------------------------------------

def symbolic_chmod_examples() -> None:
    print_section("9. Symbolic chmod notation")

    examples = [
        "u+x",
        "g-w",
        "o-r",
        "u=rw,g=r,o=",
        "a+r",
        "u+x,g+x",
    ]

    for expression in examples:
        print("  chmod", expression, "file")

    print(
        """
Symbolic mode syntax uses:

  u = user/owner
  g = group
  o = others
  a = all

Operators:

  + -> add
  - -> remove
  = -> set exactly

Examples:

  chmod u+x script.sh
  chmod g-w shared.txt
  chmod o-r secret.txt
  chmod u=rw,g=r,o= report.txt

The numeric form is often concise; symbolic form is useful when modifying
specific permission classes without changing unrelated bits.
"""
    )


# ---------------------------------------------------------------------------
# 10. Special permissions
# ---------------------------------------------------------------------------

def explain_special_bits() -> None:
    print_section("10. setuid, setgid, and sticky bit")

    print(
        """
setuid on an executable:
  The process can execute with the file owner's effective UID, subject to
  Linux security rules.

setgid on an executable:
  Historically causes execution with the file's group identity.

setgid on a directory:
  Newly created entries commonly inherit the directory's group, which is
  useful for collaborative project directories.

sticky bit on a directory:
  In a shared writable directory, deletion/rename is restricted so that
  ordinary users cannot freely remove files belonging to other users.

Classic numeric examples:

  4755 -> setuid + 755
  2755 -> setgid + 755
  1777 -> sticky + 777

Symbolic examples:

  chmod u+s program
  chmod g+s shared_directory
  chmod +t shared_directory

Special permissions require careful security review. A setuid-root program
with a vulnerability can become a privilege-escalation path.
"""
    )


def demonstrate_special_bits() -> None:
    print_section("11. Inspecting special permission bits safely")

    with tempfile.TemporaryDirectory(prefix="special_bits_") as directory:
        root = Path(directory)
        shared = root / "shared"
        shared.mkdir()

        # These are demonstrations on a temporary object, not system files.
        os.chmod(shared, 0o1777)

        print("Temporary shared directory:")
        inspect_path(shared)

        executable = root / "demo_program"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(executable, 0o4755)

        print("\nTemporary setuid-marked file:")
        inspect_path(executable)

        print(
            "\nNote: a setuid bit on a script is not a reliable way to obtain "
            "privilege on Linux. Kernel behavior around interpreted scripts "
            "and privilege transitions must not be treated like a compiled "
            "setuid executable."
        )


# ---------------------------------------------------------------------------
# 11. sudo
# ---------------------------------------------------------------------------

def explain_sudo() -> None:
    print_section("12. sudo and controlled privilege escalation")

    print(
        """
sudo allows an authorized user to execute selected commands with another
identity, commonly root.

Typical commands:

  sudo command
  sudo -u anotheruser command
  sudo -l
  sudo -k
  sudo -v

The policy is commonly configured through /etc/sudoers and files under
/etc/sudoers.d/.

Security principle:
  Grant the smallest command set and privileges required.

Dangerous administrative patterns include granting unrestricted command
execution when only one administrative operation is required.

sudo is not itself a replacement for file permissions. It is a mechanism for
controlled privilege transitions and policy enforcement.
"""
    )

    command = ["sudo", "-n", "-l"]
    print("Safe inspection command:", " ".join(command))

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        print("Return code:", result.returncode)
        if result.stdout.strip():
            print(result.stdout[:2000])
        if result.stderr.strip():
            print(result.stderr[:1000])
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError) as exc:
        print("sudo inspection was not executed:", exc)


# ---------------------------------------------------------------------------
# 12. ACL concepts
# ---------------------------------------------------------------------------

def acl_command_available() -> bool:
    try:
        result = subprocess.run(
            ["getfacl", "--version"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return False


def demonstrate_acl_if_available() -> None:
    print_section("13. POSIX ACLs")

    if not acl_command_available():
        print(
            "getfacl is not installed. The standard UNIX owner/group/other "
            "model is demonstrated instead."
        )
        return

    with tempfile.TemporaryDirectory(prefix="acl_demo_") as directory:
        path = Path(directory) / "acl_file.txt"
        path.write_text("ACL demonstration\n", encoding="utf-8")
        os.chmod(path, 0o640)

        result = subprocess.run(
            ["getfacl", "--absolute-names", str(path)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )

        print(result.stdout)

        print(
            """
ACLs extend the basic owner/group/other model.

An ACL can express permissions for a specific named user or group without
changing the file's single owning user and owning group.

A POSIX ACL can contain:
  user::...
  user:alice:...
  group::...
  group:developers:...
  mask::...
  other::...

The ACL mask is important because it limits effective permissions for
named users, named groups, and the owning group entry.

Tools commonly include:
  getfacl
  setfacl

Always inspect ACLs when ordinary ls -l output does not explain an access
decision.
"""
        )


# ---------------------------------------------------------------------------
# 13. Path-based debugging
# ---------------------------------------------------------------------------

def inspect_path_components(path: Path) -> None:
    print_section("14. Path traversal debugging")

    absolute_path = path.resolve()
    print("Resolved path:", absolute_path)

    current = Path(absolute_path.anchor)

    for component in absolute_path.parts:
        if component == absolute_path.anchor:
            continue

        current = current / component

        try:
            information = current.stat()
            print(
                f"{current}: {mode_to_human(information.st_mode)} "
                f"uid={information.st_uid} gid={information.st_gid}"
            )
        except PermissionError:
            print(f"{current}: metadata access denied")
            break
        except FileNotFoundError:
            print(f"{current}: does not exist")
            break

    print(
        """
When debugging "Permission denied", inspect every parent directory.

Useful real-world commands include:

  namei -l /path/to/file
  ls -ld /path /path/to /path/to/file
  id username
  groups username
  getfacl /path/to/file
  stat /path/to/file

The problem may be on a parent directory rather than the target file.
"""
    )


# ---------------------------------------------------------------------------
# 14. Permission test simulation
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    subject_name: str
    subject: Subject
    security: FileSecurity
    requested: str
    expected: bool


def run_permission_tests() -> None:
    print_section("15. Permission-model tests")

    owner = Subject(uid=1000, primary_gid=100, supplementary_gids=set())
    group_member = Subject(uid=1001, primary_gid=200, supplementary_gids={100})
    outsider = Subject(uid=1002, primary_gid=300, supplementary_gids=set())

    security = FileSecurity(
        owner_uid=1000,
        group_gid=100,
        owner_permissions=PermissionSet(True, True, False),
        group_permissions=PermissionSet(True, False, False),
        other_permissions=PermissionSet(False, False, False),
    )

    cases = [
        TestCase("owner", owner, security, "rw", True),
        TestCase("owner", owner, security, "x", False),
        TestCase("group member", group_member, security, "r", True),
        TestCase("group member", group_member, security, "w", False),
        TestCase("outsider", outsider, security, "r", False),
    ]

    passed = 0

    for case in cases:
        actual = basic_permission_allowed(
            case.subject,
            case.security,
            case.requested,
        )
        success = actual == case.expected
        passed += int(success)

        print(
            f"{case.subject_name:14} "
            f"request={case.requested:2} "
            f"expected={case.expected!s:5} "
            f"actual={actual!s:5} "
            f"{'PASS' if success else 'FAIL'}"
        )

    print(f"\n{passed}/{len(cases)} tests passed.")


# ---------------------------------------------------------------------------
# 15. Common mistakes and security reasoning
# ---------------------------------------------------------------------------

def explain_common_mistakes() -> None:
    print_section("16. Common mistakes")

    mistakes = {
        "chmod 777 everywhere": (
            "Creates unnecessary write/execute access and increases the impact "
            "of compromised accounts or vulnerable applications."
        ),
        "chmod changes ownership": (
            "chmod changes mode bits; chown/chgrp deal with ownership."
        ),
        "directory read means full access": (
            "Listing and traversal are separate directory permissions."
        ),
        "group membership always combines permissions": (
            "The basic owner/group/other selection is class-based; it is not "
            "simply a union of all three classes."
        ),
        "sudo fixes every permission problem": (
            "sudo changes the identity under which a command executes; it "
            "does not explain application-level authorization or every kernel "
            "security mechanism."
        ),
        "permissions are the only Linux security layer": (
            "Linux also has ACLs, capabilities, namespaces, LSMs, mount "
            "options, seccomp, containers, and application authorization."
        ),
        "execute on a file means read": (
            "Execute permission and read permission are independent."
        ),
        "umask modifies old files": (
            "umask influences creation; it is not a bulk permission editor."
        ),
    }

    for mistake, correction in mistakes.items():
        print(f"\nMistake: {mistake}\nWhy it matters: {correction}")


def explain_security_best_practices() -> None:
    print_section("17. Security and production considerations")

    print(
        """
Least privilege:
  Give users, services, containers, and processes only the access required.

Separation of duties:
  Avoid using one powerful account for unrelated activities.

Group-based authorization:
  Prefer well-defined groups over repeatedly granting broad permissions.

Avoid world-writable files:
  Especially avoid writable executable paths and sensitive configuration
  files.

Protect secrets:
  Configuration containing credentials should not normally be world-readable.

Review privileged executables:
  setuid programs deserve particularly careful auditing.

Audit changes:
  Track ownership, permissions, group membership, sudo policy, and ACLs.

Understand application authorization:
  File permissions do not replace authentication and authorization inside
  web applications, databases, APIs, or business systems.

Protect parent directories:
  Sensitive files require secure directory traversal and ownership.

Use service accounts carefully:
  A service should generally run under a dedicated account rather than root.

Check symbolic links:
  Privileged applications must account for race conditions and symlink attacks.

Use atomic operations:
  Security-sensitive programs should avoid time-of-check/time-of-use
  (TOCTOU) patterns.

Remember defense in depth:
  File permissions are one layer in a broader operating-system security model.
"""
    )


# ---------------------------------------------------------------------------
# 16. Linux command reference
# ---------------------------------------------------------------------------

def command_reference() -> None:
    print_section("18. Practical Linux command reference")

    commands = [
        ("id", "Display current user IDs and group membership"),
        ("whoami", "Display effective username"),
        ("groups", "Display group membership"),
        ("getent passwd", "Query the NSS passwd database"),
        ("getent group", "Query the NSS group database"),
        ("ls -l", "Display ownership and ordinary permission bits"),
        ("stat file", "Display detailed filesystem metadata"),
        ("chmod 640 file", "Set ordinary permission bits"),
        ("chown user file", "Change file owner, with appropriate privilege"),
        ("chgrp group file", "Change file group"),
        ("umask", "Display current process umask"),
        ("namei -l path", "Inspect permissions on path components"),
        ("getfacl file", "Display POSIX ACL information"),
        ("setfacl", "Modify POSIX ACL information"),
        ("sudo -l", "Display sudo permissions"),
    ]

    width = max(len(command) for command, _ in commands)

    for command, explanation in commands:
        print(f"{command:<{width}}  {explanation}")


# ---------------------------------------------------------------------------
# 17. Access-control matrix example
# ---------------------------------------------------------------------------

def demonstrate_access_matrix() -> None:
    print_section("19. Access-control matrix")

    roles = {
        "owner": PermissionSet(True, True, True),
        "developer_group": PermissionSet(True, True, False),
        "other": PermissionSet(True, False, False),
    }

    print(f"{'Role':<20} {'Read':<8} {'Write':<8} {'Execute':<8}")
    print("-" * 48)

    for role, permissions in roles.items():
        print(
            f"{role:<20} "
            f"{str(permissions.read):<8} "
            f"{str(permissions.write):<8} "
            f"{str(permissions.execute):<8}"
        )

    print(
        """
An access-control matrix maps subjects or roles to operations.

Traditional UNIX mode bits compress this model into three classes:
  owner, group, other

ACLs make the model more expressive by adding named users and groups.

Application systems often use richer role-based access control (RBAC) or
attribute-based access control (ABAC), which operate at a different layer.
"""
    )


# ---------------------------------------------------------------------------
# 18. Advanced conceptual distinctions
# ---------------------------------------------------------------------------

def explain_advanced_distinctions() -> None:
    print_section("20. Advanced distinctions")

    print(
        """
Authentication:
  Establishes who a subject is.

Authorization:
  Determines what that subject may do.

Accounting/auditing:
  Records relevant actions and security events.

Discretionary access control (DAC):
  Traditional UNIX ownership and mode bits are primarily a DAC mechanism.

ACL:
  Extends traditional permissions with more specific entries.

Capabilities:
  Linux capabilities divide some traditional root powers into distinct
  privileges such as CAP_NET_BIND_SERVICE or CAP_CHOWN.

SELinux/AppArmor:
  Mandatory-access-control frameworks can constrain processes even when
  ordinary UNIX permissions would permit an operation.

Namespaces:
  Isolate process, mount, network, user, and other resources, forming an
  important foundation for containers.

Container identity:
  UID 0 inside a container is not automatically equivalent to unrestricted
  host root. User namespaces and container configuration affect the result.

Mount options:
  Options such as nosuid, nodev, and noexec can influence filesystem behavior.

ACLs, capabilities, LSM policies, namespaces, and ordinary mode bits can all
interact. Debugging a production access failure therefore requires identifying
which security layer is responsible.
"""
    )


# ---------------------------------------------------------------------------
# 19. Safe file creation with least privilege
# ---------------------------------------------------------------------------

def demonstrate_secure_file_creation() -> None:
    print_section("21. Least-privilege file creation")

    with tempfile.TemporaryDirectory(prefix="secure_creation_") as directory:
        path = Path(directory) / "private.txt"

        # os.open allows permissions to be specified at creation time.
        # The process umask may still remove bits.
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_WRONLY | os.O_EXCL,
            0o600,
        )

        try:
            os.write(descriptor, b"Private application data\n")
        finally:
            os.close(descriptor)

        inspect_path(path)

        print(
            """
Mode 600 is commonly appropriate for data intended only for its owner:

  rw-------

Creating a file with restrictive permissions first is often safer than
creating a broadly accessible file and fixing permissions later, particularly
when another process could observe the object during the transition.
"""
        )


# ---------------------------------------------------------------------------
# 20. Main program
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comprehensive Linux users and permissions study program."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Path used for filesystem metadata and traversal demonstrations.",
    )
    args = parser.parse_args()

    explain_identity_basics()
    inspect_account_databases()
    demonstrate_permission_notation()
    demonstrate_permission_algorithm()
    inspect_path(args.path)
    demonstrate_chmod_and_metadata()
    demonstrate_directory_permissions()
    demonstrate_umask_math()
    symbolic_chmod_examples()
    explain_special_bits()
    demonstrate_special_bits()
    explain_sudo()
    demonstrate_acl_if_available()
    inspect_path_components(args.path)
    run_permission_tests()
    demonstrate_access_matrix()
    explain_common_mistakes()
    explain_security_best_practices()
    command_reference()
    explain_advanced_distinctions()
    demonstrate_secure_file_creation()

    print_section("Study complete")
    print(
        "The demonstrations intentionally avoid modifying real system users, "
        "groups, ownership, sudo policy, or system configuration."
    )


if __name__ == "__main__":
    main()
