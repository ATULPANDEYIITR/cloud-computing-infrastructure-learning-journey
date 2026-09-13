"""
Linux File System: A comprehensive Python study script
=======================================================

Topic:
    Filesystem hierarchy, directories, paths, files, symbolic links, mounts

Purpose:
    This executable study file teaches Linux filesystem concepts from beginner
    to advanced level. The demonstrations use Python's standard library and
    temporary directories so that experiments do not modify important parts
    of the host filesystem.

Important Linux concepts covered:
    - Filesystem and filesystem hierarchy
    - Absolute and relative paths
    - Root directory (/)
    - Common directories such as /bin, /etc, /home, /tmp, /var, /usr, /dev,
      /proc, /sys, /run, /boot, /mnt, and /media
    - Directories and directory entries
    - Regular files
    - Symbolic links
    - Hard links
    - Inodes
    - File metadata
    - Permissions and ownership concepts
    - Mount points
    - Filesystem types
    - /proc and /sys
    - Mount namespaces
    - Path normalization
    - Relative path resolution
    - Dangling symbolic links
    - Broken links
    - Link-versus-target behavior
    - Filesystem boundaries
    - Device files and special files
    - Linux pseudo-filesystems
    - Mount information
    - Disk usage concepts
    - Safe filesystem programming
    - Race conditions and TOCTOU considerations
    - Path traversal
    - Atomic file replacement
    - Temporary files
    - Recursive traversal
    - File descriptor concepts
    - Error handling
    - Testing and verification

The script deliberately avoids requiring root privileges. Operations that would
normally require root privileges are represented through inspection and
simulation rather than destructive system changes.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional


# ============================================================================
# 1. INTRODUCTION
# ============================================================================

def print_title(title: str) -> None:
    """Print a consistent section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_subtitle(title: str) -> None:
    """Print a smaller subsection heading."""
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def explain(text: str) -> None:
    """Print explanatory text with predictable wrapping."""
    print(textwrap.fill(text.strip(), width=78))


print_title("LINUX FILE SYSTEM")
explain(
    """
    Linux exposes files, directories, devices, processes, kernel interfaces,
    and other resources through a unified filesystem namespace. The starting
    point of this namespace is the root directory, written as /.

    A path identifies a location in that namespace. A directory contains
    directory entries that associate names with filesystem objects. A regular
    file contains data. A symbolic link contains a path referring to another
    filesystem object. A mount attaches another filesystem into an existing
    directory in the namespace.

    Python provides several useful interfaces for studying these concepts:
    pathlib for object-oriented path manipulation, os for filesystem
    operations, stat for metadata and file types, tempfile for safe temporary
    experiments, and shutil for higher-level file operations.
    """
)


# ============================================================================
# 2. BASIC TERMINOLOGY
# ============================================================================

print_title("2. BASIC FILESYSTEM TERMINOLOGY")

terminology = {
    "filesystem": (
        "A structure and set of rules used to store, organize, name, and "
        "retrieve data."
    ),
    "filesystem hierarchy": (
        "The tree-shaped namespace beginning at the Linux root directory /."
    ),
    "root directory": (
        "The top of the Linux filesystem namespace. It is written as /."
    ),
    "directory": (
        "A filesystem object containing names that refer to other objects."
    ),
    "path": (
        "A sequence of directory names and separators used to identify a "
        "filesystem location."
    ),
    "absolute path": (
        "A path beginning at / and therefore independent of the current "
        "working directory."
    ),
    "relative path": (
        "A path interpreted relative to the process's current working "
        "directory or another explicitly selected base directory."
    ),
    "inode": (
        "A filesystem data structure containing metadata about an object and "
        "references to its data, depending on filesystem implementation."
    ),
    "directory entry": (
        "A name-to-filesystem-object association stored by a directory."
    ),
    "symbolic link": (
        "A special filesystem object containing a pathname that points to "
        "another object."
    ),
    "hard link": (
        "Another directory entry referring to the same underlying inode."
    ),
    "mount point": (
        "A directory where another filesystem is attached to the namespace."
    ),
    "pseudo-filesystem": (
        "A kernel-provided filesystem such as procfs or sysfs that exposes "
        "system information rather than ordinary persistent disk data."
    ),
}

for term, definition in terminology.items():
    print(f"{term:20} : {definition}")


# ============================================================================
# 3. THE LINUX FILESYSTEM TREE
# ============================================================================

print_title("3. THE LINUX FILESYSTEM HIERARCHY")

hierarchy = {
    "/": "Root of the entire filesystem namespace.",
    "/bin": "Essential user command binaries on systems where this path exists.",
    "/boot": "Files needed during boot, including kernels and bootloader data.",
    "/dev": "Device nodes representing devices and kernel-provided interfaces.",
    "/etc": "System-wide configuration files.",
    "/home": "Home directories for ordinary users.",
    "/lib": "Essential shared libraries and kernel modules on applicable layouts.",
    "/media": "Common mount location for removable media.",
    "/mnt": "Traditional temporary/manual mount location.",
    "/opt": "Optional application software.",
    "/proc": "Virtual procfs exposing process and kernel information.",
    "/root": "Home directory of the root user.",
    "/run": "Volatile runtime state created since boot.",
    "/sbin": "System administration binaries on systems where this path exists.",
    "/srv": "Data intended to be served by system services.",
    "/sys": "Virtual sysfs exposing kernel device and subsystem information.",
    "/tmp": "Temporary files, subject to system-specific cleanup policies.",
    "/usr": "Most userland programs, libraries, documentation, and shared data.",
    "/var": "Variable data such as logs, caches, queues, and databases.",
}

for directory, purpose in hierarchy.items():
    print(f"{directory:8} {purpose}")

explain(
    """
    Modern Linux distributions can use merged-usr layouts. In such systems,
    paths such as /bin and /sbin may be symbolic links to locations under
    /usr. The exact layout depends on the distribution and configuration, so
    software should not assume that every historical directory layout remains
    physically distinct.

    The hierarchy is a namespace, not necessarily a single physical disk.
    Different parts of the hierarchy can be backed by different filesystems
    through mounts.
    """
)


# ============================================================================
# 4. ROOT DIRECTORY
# ============================================================================

print_title("4. THE ROOT DIRECTORY /")

root = Path("/")

print("Path object:", root)
print("Exists:", root.exists())
print("Is directory:", root.is_dir())
print("Absolute:", root.is_absolute())

try:
    root_entries = sorted(root.iterdir(), key=lambda path: path.name)
    print("\nTop-level entries visible from this system:")
    for entry in root_entries:
        marker = "/" if entry.is_dir() else ""
        print(f"  {entry.name}{marker}")
except PermissionError:
    print("Permission denied while listing the root directory.")
except OSError as exc:
    print("Could not list root directory:", exc)


# ============================================================================
# 5. CURRENT WORKING DIRECTORY
# ============================================================================

print_title("5. CURRENT WORKING DIRECTORY")

current_directory = Path.cwd()

print("Path.cwd():", current_directory)
print("os.getcwd():", os.getcwd())
print("Absolute path:", current_directory.absolute())
print("Resolved path:", current_directory.resolve())

explain(
    """
    A relative path is normally interpreted using the process's current
    working directory. The current working directory is process state. It is
    not necessarily the directory containing the Python script.

    This distinction matters when a program is launched from a different
    directory, through a service manager, from a scheduler, or by another
    application.
    """
)


# ============================================================================
# 6. ABSOLUTE AND RELATIVE PATHS
# ============================================================================

print_title("6. ABSOLUTE AND RELATIVE PATHS")

example_absolute = Path("/var/log/system.log")
example_relative = Path("logs/system.log")

print("Absolute example:", example_absolute)
print("Is absolute:", example_absolute.is_absolute())

print("\nRelative example:", example_relative)
print("Is absolute:", example_relative.is_absolute())

print("\nRelative path interpreted from current directory:")
print(current_directory / example_relative)

explain(
    """
    An absolute path starts with /. For example, /etc/hosts refers to a
    location beginning at the root of the namespace.

    A relative path does not begin at /. For example, reports/data.csv is
    interpreted relative to a base directory.

    Path joining should use Path objects or os.path.join rather than manually
    concatenating strings. This avoids incorrect separators and makes intent
    clearer.
    """
)

joined_path = current_directory / "data" / "reports" / "annual.txt"
print("Pathlib joining:", joined_path)

joined_with_os = os.path.join(str(current_directory), "data", "reports", "annual.txt")
print("os.path.join:", joined_with_os)


# ============================================================================
# 7. SPECIAL PATH COMPONENTS
# ============================================================================

print_title("7. SPECIAL PATH COMPONENTS: . AND ..")

special_paths = [
    Path("."),
    Path(".."),
    Path("data/./report.txt"),
    Path("data/archive/../report.txt"),
    Path("/var/log/../tmp/example"),
]

for path in special_paths:
    print(f"\nOriginal : {path}")
    print(f"Absolute : {path.absolute()}")
    print(f"Resolved : {path.resolve(strict=False)}")

explain(
    """
    A single dot represents the current directory. Two dots represent the
    parent directory.

    Pure lexical normalization and filesystem-aware resolution are different.
    Path.resolve() can consult the filesystem and can resolve symbolic links.
    A normalization routine that only removes . and .. does not necessarily
    describe the final filesystem object.
    """
)


# ============================================================================
# 8. PATH COMPONENTS
# ============================================================================

print_title("8. PATH COMPONENTS")

sample_path = Path("/home/student/projects/linux-study/notes.txt")

print("Full path:", sample_path)
print("Name:", sample_path.name)
print("Stem:", sample_path.stem)
print("Suffix:", sample_path.suffix)
print("Parent:", sample_path.parent)
print("Parents:")

for parent in sample_path.parents:
    print(" ", parent)

print("Parts:", sample_path.parts)
print("Anchor:", sample_path.anchor)


# ============================================================================
# 9. PATH EXISTENCE AND TYPE
# ============================================================================

print_title("9. FILESYSTEM OBJECT TYPES")

with tempfile.TemporaryDirectory(prefix="linux_fs_study_") as temp_directory:
    base = Path(temp_directory)

    regular_file = base / "document.txt"
    directory = base / "documents"
    directory.mkdir()
    regular_file.write_text("Linux filesystem study\n", encoding="utf-8")

    symlink = base / "document-link"
    symlink.symlink_to(regular_file)

    print("Regular file:")
    print("  exists:", regular_file.exists())
    print("  is_file:", regular_file.is_file())
    print("  is_dir:", regular_file.is_dir())
    print("  is_symlink:", regular_file.is_symlink())

    print("\nDirectory:")
    print("  exists:", directory.exists())
    print("  is_file:", directory.is_file())
    print("  is_dir:", directory.is_dir())
    print("  is_symlink:", directory.is_symlink())

    print("\nSymbolic link:")
    print("  exists:", symlink.exists())
    print("  is_file:", symlink.is_file())
    print("  is_dir:", symlink.is_dir())
    print("  is_symlink:", symlink.is_symlink())


# ============================================================================
# 10. FILE CREATION AND READING
# ============================================================================

print_title("10. REGULAR FILES")

with tempfile.TemporaryDirectory(prefix="linux_files_") as temp_directory:
    base = Path(temp_directory)
    file_path = base / "example.txt"

    file_path.write_text(
        "First line\n"
        "Second line\n"
        "Linux files contain bytes.\n",
        encoding="utf-8",
    )

    print("Created:", file_path)
    print("Text content:")
    print(file_path.read_text(encoding="utf-8"))

    print("Size in bytes:", file_path.stat().st_size)

    binary_path = base / "binary.dat"
    binary_path.write_bytes(bytes([0, 1, 2, 127, 128, 255]))

    print("Binary size:", binary_path.stat().st_size)
    print("Binary content:", binary_path.read_bytes())


# ============================================================================
# 11. FILES ARE BYTE SEQUENCES
# ============================================================================

print_title("11. FILES, BYTES, AND TEXT ENCODING")

with tempfile.TemporaryDirectory(prefix="linux_bytes_") as temp_directory:
    base = Path(temp_directory)
    path = base / "encoding.txt"

    text = "Linux: फ़ाइल प्रणाली\n"
    encoded = text.encode("utf-8")

    path.write_bytes(encoded)

    print("Text:", text)
    print("UTF-8 bytes:", encoded)
    print("Decoded again:", path.read_bytes().decode("utf-8"))

explain(
    """
    A regular file is fundamentally a sequence of bytes. Text is an
    interpretation of those bytes using an encoding such as UTF-8.

    Linux does not require a regular file to contain text. It can contain
    executable machine code, images, databases, compressed data, archives, or
    arbitrary binary content.
    """
)


# ============================================================================
# 12. DIRECTORIES AND DIRECTORY ENTRIES
# ============================================================================

print_title("12. DIRECTORIES AND DIRECTORY ENTRIES")

with tempfile.TemporaryDirectory(prefix="linux_directories_") as temp_directory:
    base = Path(temp_directory)

    (base / "alpha.txt").write_text("alpha", encoding="utf-8")
    (base / "beta.txt").write_text("beta", encoding="utf-8")
    (base / "subdirectory").mkdir()

    print("Directory:", base)
    print("\nEntries:")
    for entry in sorted(base.iterdir()):
        print(" ", entry.name)

explain(
    """
    A directory should be understood as a container of names that refer to
    filesystem objects. The exact on-disk representation of directories is
    filesystem-specific.

    A filename is not the same thing as the underlying inode. Multiple names
    can refer to the same inode through hard links.
    """
)


# ============================================================================
# 13. MKDIR AND MKDIRS
# ============================================================================

print_title("13. CREATING DIRECTORIES")

with tempfile.TemporaryDirectory(prefix="linux_mkdir_") as temp_directory:
    base = Path(temp_directory)

    one_level = base / "reports"
    one_level.mkdir()

    nested = base / "data" / "2026" / "september"
    nested.mkdir(parents=True)

    print("Created:", one_level)
    print("Created nested path:", nested)

    print("Exists:", nested.exists())
    print("Is directory:", nested.is_dir())


# ============================================================================
# 14. RECURSIVE TRAVERSAL
# ============================================================================

print_title("14. RECURSIVE DIRECTORY TRAVERSAL")

with tempfile.TemporaryDirectory(prefix="linux_walk_") as temp_directory:
    base = Path(temp_directory)

    for relative_path in [
        "documents/readme.txt",
        "documents/reports/annual.txt",
        "images/logo.bin",
        "logs/app.log",
    ]:
        target = base / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"Example: {relative_path}\n", encoding="utf-8")

    for path in sorted(base.rglob("*")):
        relative = path.relative_to(base)
        kind = "directory" if path.is_dir() else "file"
        print(f"{relative:35} {kind}")


# ============================================================================
# 15. os.walk
# ============================================================================

print_title("15. os.walk")

with tempfile.TemporaryDirectory(prefix="linux_os_walk_") as temp_directory:
    base = Path(temp_directory)

    (base / "a").mkdir()
    (base / "b").mkdir()
    (base / "a" / "one.txt").write_text("one", encoding="utf-8")
    (base / "b" / "two.txt").write_text("two", encoding="utf-8")

    for root_directory, directories, files in os.walk(base):
        print("\nRoot:", root_directory)
        print("Directories:", directories)
        print("Files:", files)


# ============================================================================
# 16. SYMBOLIC LINKS
# ============================================================================

print_title("16. SYMBOLIC LINKS")

with tempfile.TemporaryDirectory(prefix="linux_symlink_") as temp_directory:
    base = Path(temp_directory)

    target = base / "original.txt"
    link = base / "shortcut.txt"

    target.write_text("This is the target.\n", encoding="utf-8")
    link.symlink_to(target)

    print("Target:", target)
    print("Link:", link)
    print("Link target:", link.readlink())
    print("Link is symbolic link:", link.is_symlink())
    print("Link exists through target:", link.exists())
    print("Link content:", link.read_text(encoding="utf-8"))

explain(
    """
    A symbolic link is a filesystem object whose contents identify another
    path. The operating system follows the link during many path operations.

    The link itself and its target are distinct objects. This distinction is
    important when deleting or inspecting links.
    """
)


# ============================================================================
# 17. RELATIVE SYMBOLIC LINKS
# ============================================================================

print_title("17. RELATIVE SYMBOLIC LINKS")

with tempfile.TemporaryDirectory(prefix="linux_relative_symlink_") as temp_directory:
    base = Path(temp_directory)
    data_directory = base / "data"
    links_directory = base / "links"

    data_directory.mkdir()
    links_directory.mkdir()

    target = data_directory / "report.txt"
    target.write_text("Important report\n", encoding="utf-8")

    relative_target = os.path.relpath(target, start=links_directory)
    link = links_directory / "report-link.txt"
    link.symlink_to(relative_target)

    print("Target:", target)
    print("Relative target stored in link:", link.readlink())
    print("Resolved content:", link.read_text(encoding="utf-8"))

explain(
    """
    A relative symbolic link is interpreted relative to the directory
    containing the symbolic link, not relative to the process's current
    working directory.

    Relative links are useful when an entire directory tree should remain
    relocatable.
    """
)


# ============================================================================
# 18. ABSOLUTE SYMBOLIC LINKS
# ============================================================================

print_title("18. ABSOLUTE SYMBOLIC LINKS")

with tempfile.TemporaryDirectory(prefix="linux_absolute_symlink_") as temp_directory:
    base = Path(temp_directory)
    target = base / "target.txt"
    link = base / "absolute-link.txt"

    target.write_text("Absolute-link target\n", encoding="utf-8")
    link.symlink_to(target.resolve())

    print("Stored target:", link.readlink())
    print("Resolved link:", link.resolve())
    print("Content:", link.read_text(encoding="utf-8"))

explain(
    """
    Absolute symbolic links store an absolute pathname. They continue to
    identify that absolute location when the containing directory tree is
    moved.

    This can be useful for fixed system locations but can make applications
    less portable.
    """
)


# ============================================================================
# 19. DANGLING SYMBOLIC LINKS
# ============================================================================

print_title("19. DANGLING SYMBOLIC LINKS")

with tempfile.TemporaryDirectory(prefix="linux_dangling_link_") as temp_directory:
    base = Path(temp_directory)

    target = base / "missing.txt"
    link = base / "broken-link"

    link.symlink_to(target)

    print("Link itself exists:", link.lexists() if hasattr(link, "lexists") else os.path.lexists(link))
    print("Target exists:", target.exists())
    print("Path.exists() on link:", link.exists())
    print("Path.is_symlink() on link:", link.is_symlink())
    print("Stored link target:", link.readlink())

    print("\nThe link exists, but its target does not.")


# ============================================================================
# 20. os.path.lexists
# ============================================================================

print_title("20. exists() VERSUS lexists()")

with tempfile.TemporaryDirectory(prefix="linux_lexists_") as temp_directory:
    base = Path(temp_directory)
    missing = base / "missing"
    link = base / "dangling"

    link.symlink_to(missing)

    print("os.path.exists(link):", os.path.exists(link))
    print("os.path.lexists(link):", os.path.lexists(link))
    print("link.is_symlink():", link.is_symlink())

explain(
    """
    os.path.exists() follows the link and therefore returns False for a
    dangling link. os.path.lexists() checks whether the directory entry
    itself exists, including a dangling symbolic link.

    This distinction is important when link management software needs to
    detect and remove broken links.
    """
)


# ============================================================================
# 21. HARD LINKS
# ============================================================================

print_title("21. HARD LINKS")

with tempfile.TemporaryDirectory(prefix="linux_hard_link_") as temp_directory:
    base = Path(temp_directory)

    original = base / "original.txt"
    hard_link = base / "second-name.txt"

    original.write_text("One inode, two names.\n", encoding="utf-8")
    os.link(original, hard_link)

    original_stat = os.stat(original)
    hard_link_stat = os.stat(hard_link)

    print("Original inode:", original_stat.st_ino)
    print("Hard-link inode:", hard_link_stat.st_ino)
    print("Same inode:", original_stat.st_ino == hard_link_stat.st_ino)
    print("Original link count:", original_stat.st_nlink)
    print("Hard-link link count:", hard_link_stat.st_nlink)

    hard_link.write_text("Modified through second name.\n", encoding="utf-8")

    print("Original now contains:")
    print(original.read_text(encoding="utf-8"))

explain(
    """
    A hard link is another directory entry for the same underlying inode.
    Changing the file through either name changes the same underlying object.

    The inode's link count records how many directory entries refer to it.
    When one hard link is removed, the underlying object remains accessible
    through its other hard links. The data is reclaimed only after the final
    directory entry is removed and no process still holds the file open.
    """
)


# ============================================================================
# 22. SYMBOLIC LINK VERSUS HARD LINK
# ============================================================================

print_title("22. SYMBOLIC LINKS VERSUS HARD LINKS")

comparison = [
    ("Underlying object", "Separate link object", "Same inode"),
    ("Stores", "A pathname", "Directory entry to same inode"),
    ("Can cross filesystem", "Yes", "Normally no"),
    ("Can normally link directories", "Yes", "Normally prohibited"),
    ("Can become dangling", "Yes", "No, as a pathname reference"),
    ("Affected by target rename", "Can break", "Still refers to inode"),
]

print(f"{'Property':28} {'Symbolic link':28} {'Hard link':28}")
print("-" * 84)
for row in comparison:
    print(f"{row[0]:28} {row[1]:28} {row[2]:28}")


# ============================================================================
# 23. INODES
# ============================================================================

print_title("23. INODES")

with tempfile.TemporaryDirectory(prefix="linux_inode_") as temp_directory:
    base = Path(temp_directory)
    first = base / "first.txt"
    second = base / "second.txt"

    first.write_text("same filesystem, different files", encoding="utf-8")
    os.link(first, second)

    first_stat = os.stat(first)
    second_stat = os.stat(second)

    print("first inode :", first_stat.st_ino)
    print("second inode:", second_stat.st_ino)
    print("same inode  :", first_stat.st_ino == second_stat.st_ino)
    print("device ID   :", first_stat.st_dev)
    print("link count  :", first_stat.st_nlink)
    print("file size   :", first_stat.st_size)

explain(
    """
    An inode commonly contains metadata such as file type, permissions,
    ownership identifiers, timestamps, size, link count, and references to
    data blocks. Exact inode structure is filesystem-specific.

    A pathname is a namespace concept. An inode is a filesystem-internal
    object. A directory entry connects a name to an inode.
    """
)


# ============================================================================
# 24. stat() VERSUS lstat()
# ============================================================================

print_title("24. stat() VERSUS lstat()")

with tempfile.TemporaryDirectory(prefix="linux_stat_lstat_") as temp_directory:
    base = Path(temp_directory)
    target = base / "target.txt"
    link = base / "link.txt"

    target.write_text("target", encoding="utf-8")
    link.symlink_to(target)

    followed = os.stat(link)
    link_stat = os.lstat(link)

    print("os.stat(link):")
    print("  mode:", oct(followed.st_mode))
    print("  inode:", followed.st_ino)
    print("  size:", followed.st_size)

    print("\nos.lstat(link):")
    print("  mode:", oct(link_stat.st_mode))
    print("  inode:", link_stat.st_ino)
    print("  size:", link_stat.st_size)

    print("\nTarget inode:", os.stat(target).st_ino)
    print("os.stat(link) inode:", followed.st_ino)
    print("os.lstat(link) inode:", link_stat.st_ino)

explain(
    """
    os.stat() follows symbolic links by default. os.lstat() reports metadata
    about the link object itself.

    This distinction is essential for programs that inspect or manage
    symbolic links.
    """
)


# ============================================================================
# 25. FILE TYPE BITS
# ============================================================================

print_title("25. FILE TYPE DETECTION USING stat")

with tempfile.TemporaryDirectory(prefix="linux_file_types_") as temp_directory:
    base = Path(temp_directory)
    regular = base / "regular.txt"
    directory = base / "directory"
    link = base / "link"

    regular.write_text("data", encoding="utf-8")
    directory.mkdir()
    link.symlink_to(regular)

    objects = [regular, directory, link]

    for path in objects:
        metadata = os.lstat(path)
        mode = metadata.st_mode

        print(f"\n{path.name}")
        print("  regular:", stat.S_ISREG(mode))
        print("  directory:", stat.S_ISDIR(mode))
        print("  symlink:", stat.S_ISLNK(mode))
        print("  character device:", stat.S_ISCHR(mode))
        print("  block device:", stat.S_ISBLK(mode))
        print("  FIFO:", stat.S_ISFIFO(mode))
        print("  socket:", stat.S_ISSOCK(mode))


# ============================================================================
# 26. FILE METADATA
# ============================================================================

print_title("26. FILE METADATA")

with tempfile.TemporaryDirectory(prefix="linux_metadata_") as temp_directory:
    path = Path(temp_directory) / "metadata.txt"
    path.write_text("Metadata example\n", encoding="utf-8")

    metadata = path.stat()

    metadata_values = {
        "st_mode": metadata.st_mode,
        "st_ino": metadata.st_ino,
        "st_dev": metadata.st_dev,
        "st_nlink": metadata.st_nlink,
        "st_uid": metadata.st_uid,
        "st_gid": metadata.st_gid,
        "st_size": metadata.st_size,
        "st_atime": metadata.st_atime,
        "st_mtime": metadata.st_mtime,
        "st_ctime": metadata.st_ctime,
    }

    for name, value in metadata_values.items():
        print(f"{name:12}: {value}")


# ============================================================================
# 27. TIMESTAMPS
# ============================================================================

print_title("27. FILE TIMESTAMPS")

with tempfile.TemporaryDirectory(prefix="linux_timestamps_") as temp_directory:
    path = Path(temp_directory) / "timestamps.txt"
    path.write_text("timestamp data", encoding="utf-8")

    metadata = path.stat()

    print("Access time :", time.ctime(metadata.st_atime))
    print("Modify time :", time.ctime(metadata.st_mtime))
    print("Change time :", time.ctime(metadata.st_ctime))

explain(
    """
    Linux filesystem timestamps have distinct meanings. The modification
    time represents modification of file content. Access time relates to
    access. Change time represents a change to inode metadata.

    On Linux, st_ctime is not a creation-time field. It is commonly called
    inode change time. Filesystem-specific birth or creation timestamps may
    exist but are not represented portably by Python's basic stat interface.
    """
)


# ============================================================================
# 28. PERMISSIONS
# ============================================================================

print_title("28. UNIX FILE PERMISSIONS")

permission_examples = {
    "0400": "owner read",
    "0200": "owner write",
    "0100": "owner execute",
    "0040": "group read",
    "0020": "group write",
    "0010": "group execute",
    "0004": "others read",
    "0002": "others write",
    "0001": "others execute",
}

for octal_mode, meaning in permission_examples.items():
    print(f"{octal_mode} -> {meaning}")


# ============================================================================
# 29. chmod
# ============================================================================

print_title("29. CHANGING PERMISSIONS WITH chmod")

with tempfile.TemporaryDirectory(prefix="linux_permissions_") as temp_directory:
    path = Path(temp_directory) / "permissions.txt"
    path.write_text("permission example", encoding="utf-8")

    path.chmod(0o640)

    mode = stat.S_IMODE(path.stat().st_mode)
    print("Configured mode:", oct(mode))

    print("\nPermission breakdown:")
    print("Owner:", stat.filemode(path.stat().st_mode)[1:4])
    print("Group:", stat.filemode(path.stat().st_mode)[4:7])
    print("Other:", stat.filemode(path.stat().st_mode)[7:10])


# ============================================================================
# 30. EXECUTE PERMISSION ON DIRECTORIES
# ============================================================================

print_title("30. DIRECTORY EXECUTE PERMISSION")

explain(
    """
    Directory permissions have meanings different from ordinary file
    permissions.

    Read permission on a directory allows listing names in the directory.
    Write permission permits creation or removal of entries when other
    conditions allow it. Execute permission allows traversal or lookup
    through the directory.

    Therefore, directory access often depends on combinations such as
    read-plus-execute or execute-without-read.
    """
)


# ============================================================================
# 31. OWNERSHIP
# ============================================================================

print_title("31. USER AND GROUP OWNERSHIP")

with tempfile.TemporaryDirectory(prefix="linux_ownership_") as temp_directory:
    path = Path(temp_directory) / "ownership.txt"
    path.write_text("ownership", encoding="utf-8")

    metadata = path.stat()

    print("UID:", metadata.st_uid)
    print("GID:", metadata.st_gid)

explain(
    """
    Linux files have numeric user and group ownership identifiers. Name
    resolution to usernames and group names is handled separately by system
    identity databases and configuration.

    Changing ownership normally requires appropriate privileges, so this
    study script only inspects ownership.
    """
)


# ============================================================================
# 32. UMASK
# ============================================================================

print_title("32. UMASK")

current_umask = os.umask(0)
os.umask(current_umask)

print("Current process umask:", oct(current_umask))

explain(
    """
    The process umask removes permission bits from permissions requested
    during creation. It is not itself a permission mode.

    For example, a program requesting 0666 may create a file with fewer
    permissions because the umask masks selected bits.
    """
)


# ============================================================================
# 33. SAFE TEMPORARY DIRECTORIES
# ============================================================================

print_title("33. TEMPORARY DIRECTORIES")

with tempfile.TemporaryDirectory(prefix="linux_safe_") as temporary_directory:
    path = Path(temporary_directory)
    print("Temporary directory:", path)
    print("Exists during context:", path.exists())

print("Exists after context:", path.exists())

explain(
    """
    TemporaryDirectory automatically removes the temporary tree when the
    context exits. This is safer for demonstrations than manually selecting
    a shared directory such as /tmp and constructing predictable names.
    """
)


# ============================================================================
# 34. FILE DESCRIPTORS
# ============================================================================

print_title("34. FILE DESCRIPTORS")

with tempfile.TemporaryDirectory(prefix="linux_fd_") as temp_directory:
    path = Path(temp_directory) / "descriptor.txt"
    path.write_text("file descriptor example\n", encoding="utf-8")

    with path.open("r", encoding="utf-8") as file_object:
        descriptor = file_object.fileno()
        print("Python file object:", file_object)
        print("File descriptor:", descriptor)
        print("Read:", file_object.readline().rstrip())

explain(
    """
    A file descriptor is a small integer used by a process to refer to an
    open file or another kernel-managed I/O object.

    Standard descriptors conventionally include 0 for standard input, 1 for
    standard output, and 2 for standard error.

    A pathname is used to locate an object. A file descriptor represents an
    already-open kernel resource.
    """
)


# ============================================================================
# 35. OPEN FILES AND UNLINK
# ============================================================================

print_title("35. UNLINKING AN OPEN FILE")

if os.name == "posix":
    with tempfile.TemporaryDirectory(prefix="linux_unlink_open_") as temp_directory:
        path = Path(temp_directory) / "open-file.txt"

        file_object = path.open("w+", encoding="utf-8")
        file_object.write("This remains accessible through the open descriptor.")
        file_object.flush()

        descriptor = file_object.fileno()
        os.unlink(path)

        print("Directory entry exists:", path.exists())
        print("File descriptor remains usable:", descriptor >= 0)

        file_object.seek(0)
        print("Content through open descriptor:")
        print(file_object.read())

        file_object.close()

explain(
    """
    On typical Unix-like systems, unlink removes a directory entry rather
    than immediately destroying data. If a process still has the file open,
    the process can continue using it until the final reference disappears.

    This behavior is commonly used for temporary resources that should not
    remain visible in the directory namespace.
    """)


# ============================================================================
# 36. RENAME AND ATOMIC REPLACEMENT
# ============================================================================

print_title("36. RENAME AND ATOMIC FILE REPLACEMENT")

with tempfile.TemporaryDirectory(prefix="linux_atomic_") as temp_directory:
    base = Path(temp_directory)
    final_path = base / "configuration.txt"
    temporary_path = base / "configuration.tmp"

    final_path.write_text("old configuration\n", encoding="utf-8")
    temporary_path.write_text("new configuration\n", encoding="utf-8")

    os.replace(temporary_path, final_path)

    print("Final content:")
    print(final_path.read_text(encoding="utf-8"))
    print("Temporary path exists:", temporary_path.exists())

explain(
    """
    A common safe-update pattern is to write a complete new file and then
    replace the old directory entry using os.replace(). On appropriate local
    filesystems, the namespace operation is atomic, meaning observers do not
    normally see a partially written replacement.

    Atomic replacement does not automatically provide durability after power
    loss. Applications with strict durability requirements may need explicit
    file and directory synchronization using low-level interfaces.
    """
)


# ============================================================================
# 37. COPY VERSUS MOVE
# ============================================================================

print_title("37. COPY VERSUS MOVE")

with tempfile.TemporaryDirectory(prefix="linux_copy_move_") as temp_directory:
    base = Path(temp_directory)

    source = base / "source.txt"
    copied = base / "copied.txt"
    moved = base / "moved.txt"

    source.write_text("source data", encoding="utf-8")
    shutil.copy2(source, copied)
    shutil.move(str(source), str(moved))

    print("Source exists:", source.exists())
    print("Copied exists:", copied.exists())
    print("Moved exists:", moved.exists())
    print("Copied content:", copied.read_text(encoding="utf-8"))
    print("Moved content:", moved.read_text(encoding="utf-8"))


# ============================================================================
# 38. COPY METADATA
# ============================================================================

print_title("38. shutil.copy2")

explain(
    """
    shutil.copy2 copies file content and attempts to preserve metadata such
    as modification time. Metadata preservation is not identical to a full
    filesystem-level clone, and support for individual metadata fields can
    depend on the operating system and filesystem.
    """)


# ============================================================================
# 39. PATH NORMALIZATION AND RESOLUTION
# ============================================================================

print_title("39. NORMALIZATION VERSUS RESOLUTION")

with tempfile.TemporaryDirectory(prefix="linux_resolution_") as temp_directory:
    base = Path(temp_directory)
    directory = base / "directory"
    directory.mkdir()

    target = directory / "target.txt"
    target.write_text("resolved target", encoding="utf-8")

    link = base / "link"
    link.symlink_to(directory)

    path = link / ".." / "link" / "target.txt"

    print("Constructed path:", path)
    print("Absolute:", path.absolute())
    print("Resolved:", path.resolve())

explain(
    """
    Path resolution can involve symbolic links, mount points, parent
    traversal, and filesystem existence. A path that looks simple as a string
    can have complex semantics when interpreted by the kernel.
    """
)


# ============================================================================
# 40. MOUNT POINTS
# ============================================================================

print_title("40. MOUNT POINTS")

if hasattr(os.path, "ismount"):
    for candidate in ["/", "/tmp", "/proc", "/sys", "/dev", "/run"]:
        try:
            print(f"{candidate:8} mount point: {os.path.ismount(candidate)}")
        except OSError as exc:
            print(f"{candidate:8} could not inspect: {exc}")

explain(
    """
    A mount attaches a filesystem at a directory in the existing namespace.
    That directory becomes a mount point.

    A mount does not create a second root namespace by itself. It inserts
    another filesystem into an existing path hierarchy.
    """
)


# ============================================================================
# 41. MOUNT CONCEPTUAL MODEL
# ============================================================================

print_title("41. CONCEPTUAL MOUNT MODEL")

explain(
    """
    Imagine a directory /mnt/storage exists on a root filesystem. A second
    filesystem can be mounted there.

        root filesystem
        /
        ├── etc
        ├── home
        └── mnt
            └── storage   <-- mount point

    Before the mount, storage may be an ordinary directory in the root
    filesystem. After the mount, path lookup through /mnt/storage enters the
    mounted filesystem.

    The underlying directory is still part of the mount-point mechanism, but
    normal path traversal sees the mounted filesystem instead.
    """
)


# ============================================================================
# 42. FINDING MOUNT INFORMATION
# ============================================================================

print_title("42. READING /PROC/SELF/MOUNTINFO")

mountinfo_path = Path("/proc/self/mountinfo")

if mountinfo_path.exists():
    try:
        lines = mountinfo_path.read_text(encoding="utf-8", errors="replace").splitlines()
        print("Mount entries:", len(lines))

        print("\nFirst 10 mount entries:")
        for line in lines[:10]:
            print(line)
    except PermissionError:
        print("Permission denied while reading mountinfo.")
else:
    print("/proc/self/mountinfo is not available on this system.")


# ============================================================================
# 43. PARSING MOUNTINFO
# ============================================================================

@dataclass
class MountInfo:
    """Selected fields from Linux /proc/self/mountinfo."""

    mount_id: int
    parent_id: int
    major_minor: str
    root: str
    mount_point: str
    options: str
    filesystem_type: str
    source: str
    super_options: str


def parse_mountinfo_line(line: str) -> Optional[MountInfo]:
    """
    Parse the stable high-level fields from one mountinfo line.

    Linux mountinfo places a separator '-' before filesystem-specific fields.
    The fields before the separator have a documented structure.
    """
    if " - " not in line:
        return None

    left, right = line.split(" - ", 1)
    left_fields = left.split()
    right_fields = right.split()

    if len(left_fields) < 6 or len(right_fields) < 3:
        return None

    try:
        mount_id = int(left_fields[0])
        parent_id = int(left_fields[1])
    except ValueError:
        return None

    return MountInfo(
        mount_id=mount_id,
        parent_id=parent_id,
        major_minor=left_fields[2],
        root=left_fields[3],
        mount_point=left_fields[4],
        options=left_fields[5],
        filesystem_type=right_fields[0],
        source=right_fields[1],
        super_options=right_fields[2],
    )


if mountinfo_path.exists():
    print_subtitle("Parsed mount information")

    parsed_mounts: list[MountInfo] = []

    try:
        for line in mountinfo_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            item = parse_mountinfo_line(line)
            if item is not None:
                parsed_mounts.append(item)
    except OSError as exc:
        print("Could not parse mountinfo:", exc)
    else:
        for mount in parsed_mounts[:15]:
            print(
                f"{mount.mount_point:35} "
                f"{mount.filesystem_type:12} "
                f"{mount.source}"
            )


# ============================================================================
# 44. COMMON PSEUDO-FILESYSTEMS
# ============================================================================

print_title("44. COMMON LINUX PSEUDO-FILESYSTEMS")

pseudo_filesystems = {
    "proc": "/proc",
    "sysfs": "/sys",
    "devtmpfs": "/dev",
    "tmpfs": "/run and often other volatile locations",
    "cgroup2": "/sys/fs/cgroup on systems using unified cgroups",
    "devpts": "/dev/pts for pseudo-terminals",
}

for filesystem, location in pseudo_filesystems.items():
    print(f"{filesystem:12} -> {location}")

explain(
    """
    These filesystems expose kernel-managed information or temporary runtime
    state. They should not be treated as ordinary persistent application data.

    For example, /proc exposes process and kernel information, while /sys
    exposes devices, drivers, and kernel subsystems.
    """
)


# ============================================================================
# 45. /PROC
# ============================================================================

print_title("45. /PROC")

proc = Path("/proc")

if proc.exists():
    interesting_proc_entries = [
        "cpuinfo",
        "meminfo",
        "mounts",
        "self",
        "version",
        "uptime",
    ]

    for name in interesting_proc_entries:
        path = proc / name
        print(f"{path}: exists={path.exists()}")

    for name in ["version", "uptime"]:
        path = proc / name
        if path.exists() and path.is_file():
            try:
                print(f"\n{name}:")
                print(path.read_text(encoding="utf-8", errors="replace")[:500])
            except OSError as exc:
                print("Could not read:", exc)


# ============================================================================
# 46. /PROC/SELF
# ============================================================================

print_title("46. /PROC/SELF")

proc_self = Path("/proc/self")

if proc_self.exists():
    print("/proc/self points to information about the current process.")
    try:
        print("Resolved:", proc_self.resolve())
    except OSError as exc:
        print("Could not resolve:", exc)

    print("Current Python PID:", os.getpid())


# ============================================================================
# 47. /SYS
# ============================================================================

print_title("47. /SYS")

sysfs = Path("/sys")

if sysfs.exists():
    print("sysfs exists:", sysfs.exists())
    print("sysfs is directory:", sysfs.is_dir())

    try:
        entries = list(sysfs.iterdir())
        print("Top-level entries:")
        for entry in entries[:20]:
            print(" ", entry.name)
    except OSError as exc:
        print("Could not list /sys:", exc)


# ============================================================================
# 48. /DEV
# ============================================================================

print_title("48. /DEV")

dev = Path("/dev")

if dev.exists():
    print("/dev exists:", dev.exists())
    print("/dev is directory:", dev.is_dir())

    common_devices = ["null", "zero", "random", "urandom", "tty"]

    for device_name in common_devices:
        path = dev / device_name
        if path.exists():
            mode = os.lstat(path).st_mode
            print(
                f"{path}: "
                f"character={stat.S_ISCHR(mode)}, "
                f"block={stat.S_ISBLK(mode)}"
            )


# ============================================================================
# 49. SPECIAL FILES
# ============================================================================

print_title("49. SPECIAL FILES")

explain(
    """
    Linux supports special filesystem objects.

    Character devices provide stream-oriented device interfaces. Block
    devices provide block-oriented storage interfaces. FIFOs provide
    named-pipe communication. Unix-domain sockets provide local IPC.

    The filesystem namespace therefore contains much more than ordinary
    persistent documents.
    """
)


# ============================================================================
# 50. DEVICE NUMBERS
# ============================================================================

if dev.exists():
    print_subtitle("Device numbers")

    for name in ["null", "zero", "random"]:
        path = dev / name

        if path.exists():
            try:
                metadata = path.stat()
                print(
                    f"{name:8} "
                    f"major={os.major(metadata.st_rdev)} "
                    f"minor={os.minor(metadata.st_rdev)}"
                )
            except (OSError, ValueError) as exc:
                print(name, ":", exc)


# ============================================================================
# 51. FILESYSTEM DEVICE AND MOUNT BOUNDARY
# ============================================================================

print_title("51. FILESYSTEM DEVICE IDs")

for candidate in [Path("/"), Path("/tmp"), Path("/proc"), Path("/sys")]:
    try:
        metadata = candidate.stat()
        print(f"{candidate:8} st_dev={metadata.st_dev}")
    except OSError as exc:
        print(f"{candidate}: {exc}")

explain(
    """
    st_dev identifies the device/filesystem containing an object from the
    perspective of the operating system interface. Comparing st_dev values
    can help identify filesystem boundaries.

    A mount point can therefore cause a path traversal to move from one
    filesystem to another.
    """
)


# ============================================================================
# 52. DISK USAGE
# ============================================================================

print_title("52. DISK SPACE")

for candidate in [Path("/"), Path.cwd(), Path("/tmp")]:
    if candidate.exists():
        try:
            usage = shutil.disk_usage(candidate)
            print(f"\n{candidate}")
            print("  total :", usage.total)
            print("  used  :", usage.used)
            print("  free  :", usage.free)
        except OSError as exc:
            print(f"Could not inspect {candidate}: {exc}")


# ============================================================================
# 53. FILESYSTEM CAPACITY VERSUS FILE SIZE
# ============================================================================

print_title("53. FILE SIZE VERSUS FILESYSTEM CAPACITY")

explain(
    """
    A file's st_size describes the logical size of that file. Filesystem
    capacity describes available storage in the filesystem containing it.

    Sparse files demonstrate why these concepts differ. A sparse file can
    have a large logical size while consuming substantially fewer physical
    storage blocks.
    """)


# ============================================================================
# 54. SPARSE FILE
# ============================================================================

print_title("54. SPARSE FILE DEMONSTRATION")

if os.name == "posix":
    with tempfile.TemporaryDirectory(prefix="linux_sparse_") as temp_directory:
        path = Path(temp_directory) / "sparse.bin"

        with path.open("wb") as file_object:
            file_object.seek(1024 * 1024)
            file_object.write(b"X")

        metadata = path.stat()

        print("Logical size:", metadata.st_size)
        print("Allocated 512-byte blocks:", metadata.st_blocks)
        print("Approximate allocated bytes:", metadata.st_blocks * 512)

explain(
    """
    The exact allocation-unit semantics are filesystem-dependent, but
    st_blocks can illustrate that logical size and allocated storage need not
    be equal.
    """)


# ============================================================================
# 55. FILESYSTEM TYPES
# ============================================================================

print_title("55. COMMON FILESYSTEM TYPES")

filesystem_types = {
    "ext4": "Common Linux general-purpose filesystem.",
    "XFS": "High-performance journaling filesystem.",
    "Btrfs": "Copy-on-write filesystem with advanced storage features.",
    "tmpfs": "Memory-backed temporary filesystem.",
    "proc": "Process and kernel information pseudo-filesystem.",
    "sysfs": "Kernel device and subsystem information pseudo-filesystem.",
    "overlayfs": "Union filesystem commonly used by containers.",
    "NFS": "Network filesystem protocol/filesystem support.",
    "FAT32": "Widely supported filesystem often used on removable media.",
    "exFAT": "Filesystem commonly used for removable storage.",
}

for name, description in filesystem_types.items():
    print(f"{name:10} {description}")


# ============================================================================
# 56. FILESYSTEM HIERARCHY DOES NOT MEAN ONE DISK
# ============================================================================

print_title("56. ONE NAMESPACE, MULTIPLE FILESYSTEMS")

explain(
    """
    A Linux installation can have one visible directory tree while using
    multiple filesystems underneath it.

    For example:

        /
        ├── /home       -> separate filesystem
        ├── /var        -> separate filesystem
        ├── /boot       -> separate filesystem
        └── /data       -> separate filesystem

    Applications normally access these locations through ordinary paths.
    Mount operations hide the underlying physical arrangement behind a
    unified namespace.
    """
)


# ============================================================================
# 57. MOUNT COMMAND CONCEPTS
# ============================================================================

print_title("57. MOUNT COMMAND CONCEPTS")

mount_commands = [
    "mount",
    "findmnt",
    "df -h",
    "lsblk",
    "cat /proc/self/mountinfo",
    "cat /proc/mounts",
    "mountpoint /mnt/data",
    "umount /mnt/data",
]

for command in mount_commands:
    print(command)

explain(
    """
    These are Linux command-line concepts for examining or managing mounts.

    Mounting a real block device or changing system mounts can require root
    privileges and can affect system availability. This script does not
    execute mount or unmount commands automatically.
    """
)


# ============================================================================
# 58. MOUNT OPTIONS
# ============================================================================

print_title("58. COMMON MOUNT OPTIONS")

mount_options = {
    "ro": "Read-only mount.",
    "rw": "Read-write mount.",
    "nosuid": "Ignore set-user-ID and set-group-ID bits.",
    "nodev": "Do not interpret device nodes on the mounted filesystem.",
    "noexec": "Prevent execution of programs from the mount in applicable contexts.",
    "relatime": "Update access times with reduced frequency.",
    "bind": "Expose an existing directory at another path.",
    "remount": "Change options of an existing mount when supported.",
}

for option, meaning in mount_options.items():
    print(f"{option:10} {meaning}")


# ============================================================================
# 59. BIND MOUNTS
# ============================================================================

print_title("59. BIND MOUNTS")

explain(
    """
    A bind mount makes an existing directory or filesystem object available
    at another location in the namespace.

    Conceptually:

        /data/project
        /mnt/project

    can refer to the same underlying directory tree through a bind mount.

    Bind mounts are important in container systems and service isolation.
    Creating one normally requires appropriate Linux privileges, so the
    demonstration remains conceptual.
    """)


# ============================================================================
# 60. MOUNT NAMESPACES
# ============================================================================

print_title("60. MOUNT NAMESPACES")

explain(
    """
    Linux mount namespaces allow different processes to have different views
    of the mount hierarchy.

    Containers commonly use namespaces to provide isolated views of
    filesystem mounts. A process in one namespace may see a mount that is
    hidden from a process in another namespace.

    This is a namespace-level isolation mechanism. It does not mean the
    underlying storage is duplicated.
    """)


# ============================================================================
# 61. CONTAINER OVERLAY FILESYSTEMS
# ============================================================================

print_title("61. OVERLAY FILESYSTEMS")

explain(
    """
    Overlay filesystems combine multiple directory trees into a unified view.
    Container engines commonly use an overlay-style filesystem arrangement.

    A simplified conceptual model is:

        lower layer  -> base image
        upper layer  -> container changes
        merged view  -> visible filesystem

    A modification can be represented in the writable upper layer while
    unchanged content continues to come from lower layers.

    Exact implementation details depend on the container runtime and storage
    driver.
    """)


# ============================================================================
# 62. PATH TRAVERSAL
# ============================================================================

print_title("62. PATH TRAVERSAL SECURITY")

explain(
    """
    Path traversal occurs when untrusted input is allowed to escape an
    intended directory through components such as ../ or through symbolic
    links.

    A dangerous conceptual design is:

        base_directory / user_supplied_filename

    followed by unrestricted access.

    Even if the resulting string appears to begin with the intended base,
    symbolic links and path semantics can make security checks more complex.
    """)


# ============================================================================
# 63. SECURE PATH VALIDATION
# ============================================================================

def safe_child_path(base_directory: Path, user_path: str) -> Path:
    """
    Return a resolved path only when it remains under the resolved base.

    This is a useful educational pattern, but high-security applications
    should consider race conditions, filesystem-specific behavior, symlinks,
    and openat-style APIs as discussed later.
    """
    base = base_directory.resolve()
    candidate = (base / user_path).resolve()

    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError("Path escapes the permitted directory") from exc

    return candidate


print_subtitle("Safe path validation example")

with tempfile.TemporaryDirectory(prefix="linux_path_security_") as temp_directory:
    base = Path(temp_directory)
    (base / "public").mkdir()

    permitted = safe_child_path(base / "public", "notes/readme.txt")
    print("Permitted path:", permitted)

    try:
        blocked = safe_child_path(base / "public", "../../outside.txt")
        print(blocked)
    except ValueError as exc:
        print("Blocked:", exc)


# ============================================================================
# 64. SYMLINK SECURITY LIMITATION
# ============================================================================

print_title("64. WHY PATH CHECKING ALONE IS NOT ALWAYS ENOUGH")

explain(
    """
    A check-then-use design can be vulnerable to a time-of-check-to-time-of-
    use race, commonly called TOCTOU.

    Example:

        1. Program verifies that a path is inside /safe.
        2. Another process changes a symbolic link.
        3. Program opens the path.
        4. The opened object is no longer the object that was validated.

    For security-sensitive applications, Linux provides descriptor-relative
    APIs and flags that can reduce these risks. Python exposes some low-level
    functionality through os.open and related interfaces, but exact secure
    design depends on the threat model.
    """)


# ============================================================================
# 65. OPENAT CONCEPT
# ============================================================================

print_title("65. DESCRIPTOR-RELATIVE PATH OPERATIONS")

explain(
    """
    Linux supports APIs such as openat(), which resolves a pathname relative
    to an already-open directory file descriptor.

    Conceptually:

        directory_fd = open("/safe", ...)
        openat(directory_fd, "file.txt", ...)

    This can reduce dependence on a process-wide current directory and can
    make security boundaries more explicit.

    Modern Linux also provides stronger resolution controls through
    interfaces such as openat2(), including restrictions on symbolic links
    and path traversal. Availability and Python-level support vary by
    environment.
    """)


# ============================================================================
# 66. BASIC SECURE FILE OPENING
# ============================================================================

print_title("66. LOW-LEVEL FILE OPENING")

with tempfile.TemporaryDirectory(prefix="linux_open_") as temp_directory:
    path = Path(temp_directory) / "low-level.txt"

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    mode = 0o600

    descriptor = os.open(path, flags, mode)

    try:
        os.write(descriptor, b"Created with a low-level file descriptor.\n")
    finally:
        os.close(descriptor)

    print("Created:", path)
    print("Content:", path.read_text(encoding="utf-8"))
    print("Mode:", oct(stat.S_IMODE(path.stat().st_mode)))


# ============================================================================
# 67. O_EXCL
# ============================================================================

print_title("67. O_EXCL")

explain(
    """
    O_CREAT combined with O_EXCL requests exclusive creation. If the path
    already exists, creation fails rather than silently replacing it.

    This is safer than manually checking exists() and then creating the file,
    because the check-and-create sequence can otherwise contain a race.
    """)

with tempfile.TemporaryDirectory(prefix="linux_exclusive_") as temp_directory:
    path = Path(temp_directory) / "unique.txt"

    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)

    try:
        os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print("Second exclusive creation correctly failed.")


# ============================================================================
# 68. ERROR HANDLING
# ============================================================================

print_title("68. FILESYSTEM ERROR HANDLING")

with tempfile.TemporaryDirectory(prefix="linux_errors_") as temp_directory:
    base = Path(temp_directory)
    missing = base / "does-not-exist.txt"

    try:
        missing.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        print("FileNotFoundError:", exc)
        print("errno:", exc.errno)
        print("ENOENT:", errno.ENOENT)


# ============================================================================
# 69. COMMON ERRORS
# ============================================================================

print_title("69. COMMON FILESYSTEM ERRORS")

filesystem_errors = {
    "ENOENT": "No such file or directory.",
    "EACCES": "Permission denied.",
    "EEXIST": "File already exists.",
    "ENOTDIR": "A path component that should be a directory is not.",
    "EISDIR": "An operation expected a non-directory but found a directory.",
    "ENOSPC": "No space left on device.",
    "EROFS": "Read-only filesystem.",
    "EXDEV": "Cross-device link.",
    "ENOTEMPTY": "Directory is not empty.",
    "ELOOP": "Too many symbolic-link levels.",
}

for name, meaning in filesystem_errors.items():
    value = getattr(errno, name, None)
    if value is not None:
        print(f"{name:8} ({value:3}) {meaning}")
    else:
        print(f"{name:8}       {meaning}")


# ============================================================================
# 70. CROSS-FILESYSTEM MOVE
# ============================================================================

print_title("70. CROSS-FILESYSTEM MOVES")

explain(
    """
    A rename operation generally requires source and destination to be on the
    same filesystem. A cross-filesystem rename can fail with EXDEV.

    High-level operations such as shutil.move() can implement a move across
    filesystems by copying data and then removing the original. That is not
    equivalent to a single atomic rename.
    """)


# ============================================================================
# 71. FILE NAMES AND SPECIAL CHARACTERS
# ============================================================================

print_title("71. FILE NAMES ARE NOT COMMANDS")

with tempfile.TemporaryDirectory(prefix="linux_names_") as temp_directory:
    base = Path(temp_directory)

    names = [
        "normal.txt",
        "file with spaces.txt",
        "file-with-dash.txt",
        "file'quote.txt",
        "file[brackets].txt",
        "unicode-फ़ाइल.txt",
    ]

    for name in names:
        path = base / name
        path.write_text(name, encoding="utf-8")

    for path in sorted(base.iterdir(), key=lambda item: item.name):
        print(repr(path.name))

explain(
    """
    Linux filenames are byte strings subject to filesystem and API
    restrictions. They may contain spaces and many characters that have
    special meanings to shells.

    Shell syntax and filesystem naming are different layers. A filename with
    spaces is not intrinsically problematic for the filesystem; it becomes
    significant when passed through shell parsing.
    """
)


# ============================================================================
# 72. NULL BYTE
# ============================================================================

print_title("72. PATH LIMITATION: NUL BYTE")

try:
    Path("invalid\0name")
except ValueError as exc:
    print("Python rejects NUL in a path:", exc)

explain(
    """
    A NUL byte cannot be part of a normal Linux pathname. This limitation
    originates from the C-style pathname interfaces used by the kernel ABI.
    """)


# ============================================================================
# 73. CASE SENSITIVITY
# ============================================================================

print_title("73. CASE SENSITIVITY")

with tempfile.TemporaryDirectory(prefix="linux_case_") as temp_directory:
    base = Path(temp_directory)

    upper = base / "File.txt"
    lower = base / "file.txt"

    upper.write_text("uppercase name", encoding="utf-8")
    lower.write_text("lowercase name", encoding="utf-8")

    print("Both can coexist on typical Linux filesystems:")
    print(upper.exists(), upper)
    print(lower.exists(), lower)


# ============================================================================
# 74. HIDDEN FILES
# ============================================================================

print_title("74. HIDDEN FILES")

with tempfile.TemporaryDirectory(prefix="linux_hidden_") as temp_directory:
    base = Path(temp_directory)

    (base / ".config").write_text("hidden-style filename", encoding="utf-8")
    (base / "visible.txt").write_text("visible filename", encoding="utf-8")

    print("All directory entries:")
    for entry in sorted(base.iterdir()):
        print(" ", entry.name)

explain(
    """
    Linux does not have a special hidden-file flag equivalent to a separate
    filesystem object type. A common convention is simply that filenames
    beginning with a dot are hidden by normal directory-listing tools.
    """)


# ============================================================================
# 75. ROOT-OWNED SYSTEM PATHS
# ============================================================================

print_title("75. SYSTEM PATHS AND PRIVILEGES")

explain(
    """
    Many directories under / are owned or controlled by root and are not
    intended for arbitrary modification by ordinary users.

    Examples include /etc, /usr, /boot, /dev, /proc, and /sys.

    Read access and write access are separate concerns. A program should
    request only the privileges required for its task.
    """)


# ============================================================================
# 76. SUDO CONCEPT
# ============================================================================

print_title("76. PRIVILEGED FILESYSTEM OPERATIONS")

explain(
    """
    Commands such as mounting filesystems, changing ownership, modifying
    protected system configuration, or accessing restricted device interfaces
    may require elevated privileges.

    The principle of least privilege recommends performing normal application
    work as an unprivileged user and elevating only narrowly controlled
    operations when necessary.
    """)


# ============================================================================
# 77. FILESYSTEM SECURITY PERMISSIONS
# ============================================================================

print_title("77. SECURITY MODEL")

security_dimensions = [
    "User ownership",
    "Group ownership",
    "Read/write/execute permission bits",
    "Special permission bits",
    "ACLs",
    "Mount options",
    "Namespaces",
    "Capabilities",
    "SELinux/AppArmor policy where configured",
]

for item in security_dimensions:
    print("•", item)


# ============================================================================
# 78. SPECIAL PERMISSION BITS
# ============================================================================

print_title("78. SPECIAL PERMISSION BITS")

special_modes = {
    "setuid": "4xxx",
    "setgid": "2xxx",
    "sticky": "1xxx",
}

for name, notation in special_modes.items():
    print(f"{name:8}: {notation}")

explain(
    """
    The setuid and setgid bits can affect the effective identity of an
    executable under appropriate conditions. The sticky bit on a directory
    restricts deletion or renaming of entries in common shared-directory
    scenarios.

    These mechanisms have security implications and should be treated
    carefully.
    """)


# ============================================================================
# 79. /TMP AND STICKY BIT
# ============================================================================

print_title("79. /TMP")

tmp_path = Path("/tmp")

if tmp_path.exists():
    try:
        metadata = tmp_path.stat()
        print("/tmp mode:", stat.filemode(metadata.st_mode))
        print("Octal permissions:", oct(stat.S_IMODE(metadata.st_mode)))
    except OSError as exc:
        print("Could not inspect /tmp:", exc)


# ============================================================================
# 80. ACL CONCEPT
# ============================================================================

print_title("80. ACCESS CONTROL LISTS")

explain(
    """
    Traditional Unix permission bits represent owner, group, and other
    permissions. Access Control Lists can express more detailed rules for
    individual users and groups.

    ACL support depends on the filesystem and system configuration. Python's
    basic pathlib interface does not provide a complete portable ACL API, so
    ACL inspection is normally performed through Linux-specific tools or
    extended system interfaces.
    """)


# ============================================================================
# 81. EXTENDED ATTRIBUTES
# ============================================================================

print_title("81. EXTENDED ATTRIBUTES")

explain(
    """
    Linux filesystems can support extended attributes, commonly called xattrs.
    They store additional name-value metadata outside the traditional Unix
    permission fields.

    Security frameworks, file managers, container systems, and applications
    may use xattrs. Their availability and semantics depend on the filesystem
    and mount configuration.
    """)


# ============================================================================
# 82. FILESYSTEM JOURNALING
# ============================================================================

print_title("82. JOURNALING")

explain(
    """
    Journaling filesystems record metadata or other filesystem operations in
    a journal so that the filesystem can recover to a consistent state after
    certain failures.

    Journaling does not mean that every application write is automatically
    durable immediately after write() returns. Application-level durability
    requirements can require explicit synchronization.
    """)


# ============================================================================
# 83. fsync
# ============================================================================

print_title("83. fsync AND DURABILITY")

with tempfile.TemporaryDirectory(prefix="linux_fsync_") as temp_directory:
    path = Path(temp_directory) / "durable.txt"

    with path.open("w", encoding="utf-8") as file_object:
        file_object.write("data intended for synchronization\n")
        file_object.flush()
        os.fsync(file_object.fileno())

    print("File written and fsynced:", path)

explain(
    """
    fsync asks the operating system to synchronize file state with the
    storage device as appropriate. Exact guarantees depend on the storage
    stack and filesystem.

    High-durability applications also need to consider directory metadata
    synchronization after creating or replacing directory entries.
    """)


# ============================================================================
# 84. DIRECTORY FSYNC CONCEPT
# ============================================================================

print_title("84. DIRECTORY SYNCHRONIZATION CONCEPT")

explain(
    """
    When a program atomically replaces a file, the file's contents and the
    directory entry are distinct pieces of filesystem state.

    A strict durability sequence can therefore involve:

        1. Write temporary file.
        2. Flush file.
        3. fsync file.
        4. Replace target.
        5. Open containing directory.
        6. fsync directory.

    The exact sequence depends on application requirements and filesystem
    semantics.
    """)


# ============================================================================
# 85. DIRECTORY FILE DESCRIPTOR
# ============================================================================

if os.name == "posix":
    print_title("85. DIRECTORY FILE DESCRIPTOR")

    with tempfile.TemporaryDirectory(prefix="linux_dir_fd_") as temp_directory:
        flags = os.O_RDONLY

        try:
            directory_fd = os.open(temp_directory, flags)
        except OSError as exc:
            print("Could not open directory:", exc)
        else:
            try:
                print("Directory descriptor:", directory_fd)
            finally:
                os.close(directory_fd)


# ============================================================================
# 86. FOLLOWING SYMLINKS
# ============================================================================

print_title("86. FOLLOWING OR NOT FOLLOWING SYMBOLIC LINKS")

with tempfile.TemporaryDirectory(prefix="linux_follow_") as temp_directory:
    base = Path(temp_directory)
    target = base / "target.txt"
    link = base / "link.txt"

    target.write_text("target", encoding="utf-8")
    link.symlink_to(target)

    print("os.stat follows link:", os.stat(link).st_ino == os.stat(target).st_ino)
    print("os.lstat describes link:", os.lstat(link).st_ino != os.stat(target).st_ino)


# ============================================================================
# 87. READING A LINK WITHOUT FOLLOWING
# ============================================================================

print_title("87. readlink")

with tempfile.TemporaryDirectory(prefix="linux_readlink_") as temp_directory:
    base = Path(temp_directory)
    target = base / "target.txt"
    link = base / "link.txt"

    target.write_text("target", encoding="utf-8")
    link.symlink_to(target)

    print("Path.readlink():", link.readlink())
    print("os.readlink():", os.readlink(link))


# ============================================================================
# 88. DELETING A SYMBOLIC LINK
# ============================================================================

print_title("88. REMOVING A SYMBOLIC LINK")

with tempfile.TemporaryDirectory(prefix="linux_remove_link_") as temp_directory:
    base = Path(temp_directory)
    target = base / "target.txt"
    link = base / "link.txt"

    target.write_text("preserve me", encoding="utf-8")
    link.symlink_to(target)

    link.unlink()

    print("Link exists:", link.exists())
    print("Target still exists:", target.exists())
    print("Target content:", target.read_text(encoding="utf-8"))


# ============================================================================
# 89. REMOVING DIRECTORIES
# ============================================================================

print_title("89. rmdir VERSUS rmtree")

with tempfile.TemporaryDirectory(prefix="linux_remove_dirs_") as temp_directory:
    base = Path(temp_directory)

    empty_directory = base / "empty"
    empty_directory.mkdir()
    empty_directory.rmdir()

    print("Empty directory removed:", not empty_directory.exists())

    nonempty_directory = base / "nonempty"
    nonempty_directory.mkdir()
    (nonempty_directory / "file.txt").write_text("data", encoding="utf-8")

    try:
        nonempty_directory.rmdir()
    except OSError as exc:
        print("rmdir on non-empty directory failed:", exc)

    shutil.rmtree(nonempty_directory)
    print("Recursive removal complete:", not nonempty_directory.exists())


# ============================================================================
# 90. DESTRUCTIVE OPERATIONS
# ============================================================================

print_title("90. SAFE USE OF DESTRUCTIVE OPERATIONS")

explain(
    """
    unlink(), rmdir(), shutil.rmtree(), chmod(), chown(), mount(), and
    umount() can have significant consequences.

    Production programs should validate paths, apply least privilege, handle
    errors, consider symbolic links, and avoid constructing shell commands
    from untrusted input.
    """)


# ============================================================================
# 91. A SAFE FILE INVENTORY FUNCTION
# ============================================================================

def inventory_tree(root_directory: Path) -> list[dict[str, object]]:
    """
    Build a metadata inventory without following symbolic links.

    lstat() is deliberately used so that the inventory describes links
    themselves rather than silently replacing them with their targets.
    """
    inventory: list[dict[str, object]] = []

    for path in root_directory.rglob("*"):
        try:
            metadata = path.lstat()
        except OSError as exc:
            inventory.append(
                {
                    "path": str(path),
                    "error": str(exc),
                }
            )
            continue

        mode = metadata.st_mode

        if stat.S_ISLNK(mode):
            object_type = "symlink"
        elif stat.S_ISDIR(mode):
            object_type = "directory"
        elif stat.S_ISREG(mode):
            object_type = "regular file"
        elif stat.S_ISCHR(mode):
            object_type = "character device"
        elif stat.S_ISBLK(mode):
            object_type = "block device"
        elif stat.S_ISFIFO(mode):
            object_type = "FIFO"
        elif stat.S_ISSOCK(mode):
            object_type = "socket"
        else:
            object_type = "other"

        inventory.append(
            {
                "path": str(path.relative_to(root_directory)),
                "type": object_type,
                "size": metadata.st_size,
                "inode": metadata.st_ino,
                "device": metadata.st_dev,
                "links": metadata.st_nlink,
                "mode": stat.filemode(mode),
            }
        )

    return inventory


print_title("92. FILESYSTEM INVENTORY")

with tempfile.TemporaryDirectory(prefix="linux_inventory_") as temp_directory:
    base = Path(temp_directory)

    (base / "docs").mkdir()
    (base / "docs" / "one.txt").write_text("one", encoding="utf-8")
    (base / "docs" / "two.txt").write_text("two", encoding="utf-8")
    (base / "docs-link").symlink_to(base / "docs")

    for item in inventory_tree(base):
        print(json.dumps(item, ensure_ascii=False))


# ============================================================================
# 93. FINDING LARGE FILES
# ============================================================================

def find_files_larger_than(
    root_directory: Path,
    minimum_size: int,
) -> Iterator[tuple[Path, int]]:
    """
    Yield regular files larger than the requested number of bytes.

    Symbolic links are skipped deliberately to avoid following arbitrary
    targets during traversal.
    """
    for path in root_directory.rglob("*"):
        try:
            metadata = path.lstat()
        except OSError:
            continue

        if stat.S_ISREG(metadata.st_mode) and metadata.st_size > minimum_size:
            yield path, metadata.st_size


print_title("93. FINDING LARGE FILES")

with tempfile.TemporaryDirectory(prefix="linux_large_files_") as temp_directory:
    base = Path(temp_directory)

    (base / "small.txt").write_text("small", encoding="utf-8")
    (base / "large.txt").write_bytes(b"X" * 100)
    (base / "directory").mkdir()
    (base / "directory" / "large2.bin").write_bytes(b"Y" * 200)

    for path, size in find_files_larger_than(base, 50):
        print(path.relative_to(base), "->", size, "bytes")


# ============================================================================
# 94. CHECKING INODES
# ============================================================================

def inode_information(path: Path) -> dict[str, int]:
    """Return selected inode-related metadata."""
    metadata = path.stat()
    return {
        "inode": metadata.st_ino,
        "device": metadata.st_dev,
        "links": metadata.st_nlink,
        "size": metadata.st_size,
    }


print_title("94. INODE INFORMATION")

with tempfile.TemporaryDirectory(prefix="linux_inode_function_") as temp_directory:
    base = Path(temp_directory)
    path = base / "file.txt"
    path.write_text("inode data", encoding="utf-8")

    print(inode_information(path))


# ============================================================================
# 95. DUPLICATE CONTENT VERSUS SAME INODE
# ============================================================================

print_title("95. SAME CONTENT DOES NOT MEAN SAME INODE")

with tempfile.TemporaryDirectory(prefix="linux_same_content_") as temp_directory:
    base = Path(temp_directory)

    first = base / "first.txt"
    second = base / "second.txt"

    first.write_text("identical content", encoding="utf-8")
    second.write_text("identical content", encoding="utf-8")

    first_stat = first.stat()
    second_stat = second.stat()

    print("Same content:", first.read_bytes() == second.read_bytes())
    print("Same inode:", first_stat.st_ino == second_stat.st_ino)
    print("First inode:", first_stat.st_ino)
    print("Second inode:", second_stat.st_ino)


# ============================================================================
# 96. HARD LINK SAME INODE
# ============================================================================

print_title("96. HARD LINKS SHARE THE INODE")

with tempfile.TemporaryDirectory(prefix="linux_hard_inode_") as temp_directory:
    base = Path(temp_directory)

    original = base / "original"
    link = base / "hard-link"

    original.write_text("shared inode", encoding="utf-8")
    os.link(original, link)

    print("Same inode:", original.stat().st_ino == link.stat().st_ino)
    print("Link count:", original.stat().st_nlink)


# ============================================================================
# 97. SYMBOLIC LINKS HAVE THEIR OWN INODE
# ============================================================================

print_title("97. SYMBOLIC LINKS HAVE THEIR OWN OBJECT")

with tempfile.TemporaryDirectory(prefix="linux_symlink_inode_") as temp_directory:
    base = Path(temp_directory)

    target = base / "target"
    link = base / "link"

    target.write_text("target", encoding="utf-8")
    link.symlink_to(target)

    print("Target inode:", target.stat().st_ino)
    print("Link inode:", link.lstat().st_ino)
    print("os.stat(link) inode:", link.stat().st_ino)
    print("lstat link equals target inode:", link.lstat().st_ino == target.stat().st_ino)


# ============================================================================
# 98. LINK COUNT AFTER UNLINK
# ============================================================================

print_title("98. LINK COUNT CHANGES")

with tempfile.TemporaryDirectory(prefix="linux_link_count_") as temp_directory:
    base = Path(temp_directory)

    original = base / "original"
    hard_link = base / "hard"

    original.write_text("link count", encoding="utf-8")
    os.link(original, hard_link)

    print("Before unlink:", original.stat().st_nlink)

    hard_link.unlink()

    print("After unlink:", original.stat().st_nlink)


# ============================================================================
# 99. FILESYSTEM TREE SIMULATION
# ============================================================================

print_title("99. SIMULATED LINUX FILESYSTEM TREE")

simulated_tree = {
    "/": {
        "etc": {
            "app.conf": None,
        },
        "home": {
            "student": {
                "notes.txt": None,
            }
        },
        "var": {
            "log": {
                "app.log": None,
            }
        },
        "tmp": {},
    }
}


def print_tree(tree: dict, prefix: str = "") -> None:
    """Print a nested dictionary as a simple filesystem tree."""
    items = list(tree.items())

    for index, (name, value) in enumerate(items):
        last = index == len(items) - 1
        connector = "└── " if last else "├── "
        print(prefix + connector + name)

        if isinstance(value, dict):
            child_prefix = prefix + ("    " if last else "│   ")
            print_tree(value, child_prefix)


print_tree(simulated_tree)


# ============================================================================
# 100. PATH ALGORITHM
# ============================================================================

print_title("100. CONCEPTUAL PATH RESOLUTION")

def conceptual_join(base: str, relative: str) -> str:
    """
    Demonstrate a simplified lexical path join.

    This is not a replacement for the Linux kernel's pathname resolution.
    It deliberately demonstrates only string-level normalization.
    """
    combined = Path(base) / relative
    return os.path.normpath(str(combined))


examples = [
    ("/home/student", "documents/report.txt"),
    ("/home/student", "../shared/data.txt"),
    ("/var/log", "./application.log"),
]

for base, relative in examples:
    print(f"{base!r} + {relative!r} -> {conceptual_join(base, relative)!r}")


# ============================================================================
# 101. PATH RESOLUTION ALGORITHM CONCEPTS
# ============================================================================

print_title("101. WHAT PATH RESOLUTION INVOLVES")

resolution_steps = [
    "Start with the process namespace and root/current directory.",
    "Interpret absolute or relative path.",
    "Walk path components from left to right.",
    "Check directory permissions required for traversal.",
    "Resolve directory entries.",
    "Handle . and .. according to pathname semantics.",
    "Follow symbolic links subject to limits and flags.",
    "Cross mount points when path lookup encounters them.",
    "Return the requested filesystem object.",
]

for number, step in enumerate(resolution_steps, start=1):
    print(f"{number}. {step}")


# ============================================================================
# 102. SYMBOLIC LINK LOOP
# ============================================================================

print_title("102. SYMBOLIC LINK LOOPS")

with tempfile.TemporaryDirectory(prefix="linux_symlink_loop_") as temp_directory:
    base = Path(temp_directory)

    first = base / "first"
    second = base / "second"

    first.symlink_to(second)
    second.symlink_to(first)

    try:
        first.resolve(strict=True)
    except RuntimeError as exc:
        print("Symlink loop detected:", exc)
    except OSError as exc:
        print("Filesystem error:", exc)


# ============================================================================
# 103. SYMLINK DEPTH
# ============================================================================

print_title("103. SYMBOLIC LINK DEPTH LIMITS")

explain(
    """
    Operating systems impose limits on symbolic-link traversal to prevent
    infinite resolution. A chain containing too many links can fail with an
    ELOOP-style error.

    Applications should not assume that arbitrary link chains can be
    resolved successfully.
    """)


# ============================================================================
# 104. BROKEN DIRECTORY COMPONENT
# ============================================================================

print_title("104. ENOTDIR")

with tempfile.TemporaryDirectory(prefix="linux_enotdir_") as temp_directory:
    base = Path(temp_directory)
    file_path = base / "not-a-directory"
    file_path.write_text("regular file", encoding="utf-8")

    invalid_child = file_path / "child.txt"

    try:
        invalid_child.exists()
    except OSError as exc:
        print("Filesystem error:", exc)

    try:
        invalid_child.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        print("Access failed:", type(exc).__name__, exc)


# ============================================================================
# 105. RENAME SEMANTICS
# ============================================================================

print_title("105. RENAME SEMANTICS")

with tempfile.TemporaryDirectory(prefix="linux_rename_") as temp_directory:
    base = Path(temp_directory)

    old_name = base / "old.txt"
    new_name = base / "new.txt"

    old_name.write_text("rename demonstration", encoding="utf-8")
    old_name.rename(new_name)

    print("Old exists:", old_name.exists())
    print("New exists:", new_name.exists())
    print("New content:", new_name.read_text(encoding="utf-8"))


# ============================================================================
# 106. DIRECTORY RENAME
# ============================================================================

print_title("106. DIRECTORY RENAME")

with tempfile.TemporaryDirectory(prefix="linux_dir_rename_") as temp_directory:
    base = Path(temp_directory)

    old_directory = base / "old-directory"
    new_directory = base / "new-directory"

    old_directory.mkdir()
    (old_directory / "file.txt").write_text("data", encoding="utf-8")

    old_directory.rename(new_directory)

    print("New directory exists:", new_directory.exists())
    print(
        "Moved file:",
        (new_directory / "file.txt").read_text(encoding="utf-8"),
    )


# ============================================================================
# 107. SYMLINK TO DIRECTORY
# ============================================================================

print_title("107. SYMBOLIC LINK TO A DIRECTORY")

with tempfile.TemporaryDirectory(prefix="linux_dir_symlink_") as temp_directory:
    base = Path(temp_directory)

    real_directory = base / "real"
    link_directory = base / "link"

    real_directory.mkdir()
    (real_directory / "data.txt").write_text("directory link", encoding="utf-8")
    link_directory.symlink_to(real_directory, target_is_directory=True)

    print("Link is directory through target:", link_directory.is_dir())
    print(
        "Read through link:",
        (link_directory / "data.txt").read_text(encoding="utf-8"),
    )


# ============================================================================
# 108. DIRECTORY LINK REMOVAL
# ============================================================================

print_title("108. NEVER USE rmtree BLINDLY ON SYMLINKS")

explain(
    """
    A symbolic link to a directory is not itself the directory. Programs that
    recursively remove trees must distinguish links from directories.

    A robust tree-removal algorithm generally uses lstat-style inspection
    and carefully controls whether links are followed.
    """)


# ============================================================================
# 109. WALKING WITHOUT FOLLOWING SYMLINKS
# ============================================================================

def safe_walk(root_directory: Path) -> Iterator[Path]:
    """
    Yield filesystem entries without deliberately following symbolic links.

    pathlib.rglob itself does not recursively follow directory symlinks in
    the same way as a naive recursive implementation might. This function
    additionally makes the policy explicit.
    """
    for path in root_directory.rglob("*"):
        try:
            if path.is_symlink():
                yield path
            else:
                yield path
        except OSError:
            continue


print_title("109. SAFE WALK POLICY")

with tempfile.TemporaryDirectory(prefix="linux_safe_walk_") as temp_directory:
    base = Path(temp_directory)
    directory = base / "directory"
    directory.mkdir()
    (directory / "file.txt").write_text("data", encoding="utf-8")
    (base / "directory-link").symlink_to(directory, target_is_directory=True)

    for path in safe_walk(base):
        print(path.relative_to(base), "symlink=" + str(path.is_symlink()))


# ============================================================================
# 110. MOUNT POINT DETECTION
# ============================================================================

print_title("110. MOUNT POINT DETECTION WITH os.path.ismount")

for candidate in ["/", "/proc", "/sys", "/dev", "/tmp", str(Path.cwd())]:
    try:
        print(f"{candidate:35} -> {os.path.ismount(candidate)}")
    except OSError as exc:
        print(f"{candidate:35} -> error: {exc}")


# ============================================================================
# 111. DF CONCEPT
# ============================================================================

print_title("111. df CONCEPT")

explain(
    """
    df reports filesystem-level capacity and usage. It answers questions
    such as how much space remains on the filesystem containing a path.

    du answers a different question: how much space is consumed by files and
    directories under a path.

    A mounted filesystem can make df and du appear to describe different
    layers of the hierarchy.
    """)


# ============================================================================
# 112. DISK USAGE COMPARISON
# ============================================================================

print_title("112. df VERSUS du")

comparison = {
    "df": "Filesystem-level free/used capacity.",
    "du": "Directory/file tree disk usage.",
    "stat st_size": "Logical file size.",
    "st_blocks": "Allocated blocks reported by stat.",
}

for command, meaning in comparison.items():
    print(f"{command:15}: {meaning}")


# ============================================================================
# 113. DIRECTORY SIZE
# ============================================================================

print_title("113. DIRECTORY SIZE IS NOT RECURSIVE CONTENT SIZE")

with tempfile.TemporaryDirectory(prefix="linux_dir_size_") as temp_directory:
    base = Path(temp_directory)
    directory = base / "directory"
    directory.mkdir()

    (directory / "large.txt").write_bytes(b"X" * 10000)

    print("Directory st_size:", directory.stat().st_size)
    print("File st_size:", (directory / "large.txt").stat().st_size)

explain(
    """
    The size reported for a directory itself is metadata/storage used for
    the directory structure. It is not the sum of the sizes of all files
    underneath it.
    """)


# ============================================================================
# 114. FILE DESCRIPTOR DUPLICATION
# ============================================================================

print_title("114. DUPLICATING FILE DESCRIPTORS")

with tempfile.TemporaryDirectory(prefix="linux_dup_") as temp_directory:
    path = Path(temp_directory) / "duplicate-fd.txt"
    path.write_text("descriptor duplication", encoding="utf-8")

    with path.open("r", encoding="utf-8") as file_object:
        duplicate_fd = os.dup(file_object.fileno())

        try:
            with os.fdopen(duplicate_fd, "r", encoding="utf-8") as duplicate:
                print("Original FD:", file_object.fileno())
                print("Duplicate FD:", duplicate.fileno())
                print("Duplicate read:", duplicate.read())
        except OSError:
            os.close(duplicate_fd)


# ============================================================================
# 115. FILE OBJECT AND INODE
# ============================================================================

print_title("115. PATHNAME, INODE, FILE DESCRIPTOR")

explain(
    """
    Three layers should be distinguished:

    PATHNAME
        A name used during path lookup.

    INODE / FILE OBJECT
        The underlying filesystem object and its metadata.

    FILE DESCRIPTOR
        A process-specific reference to an open kernel file object.

    Multiple pathnames can refer to one inode through hard links. Multiple
    descriptors can refer to the same open file description.
    """)


# ============================================================================
# 116. FILE DESCRIPTOR AFTER UNLINK
# ============================================================================

if os.name == "posix":
    print_title("116. DESCRIPTOR SURVIVAL AFTER UNLINK")

    with tempfile.TemporaryDirectory(prefix="linux_fd_unlink_") as temp_directory:
        path = Path(temp_directory) / "temporary.txt"

        with path.open("w+", encoding="utf-8") as file_object:
            file_object.write("private temporary data")
            file_object.flush()

            path.unlink()

            print("Path visible:", path.exists())

            file_object.seek(0)
            print("Open descriptor content:", file_object.read())


# ============================================================================
# 117. OPEN FILE TABLE CONCEPT
# ============================================================================

print_title("117. OPEN FILE TABLE CONCEPT")

explain(
    """
    Linux maintains kernel data structures for open file descriptions.
    Processes contain file-descriptor tables that refer to these structures.

    This architecture explains why a file descriptor can remain valid after
    its pathname is removed and why descriptor duplication can refer to the
    same open state.
    """)


# ============================================================================
# 118. FILE LOCKING CONCEPT
# ============================================================================

print_title("118. FILE LOCKING")

explain(
    """
    Multiple processes can access the same filesystem objects concurrently.
    Applications may need coordination through mechanisms such as advisory
    file locks, lock files created atomically, databases, or transactional
    update patterns.

    A filesystem does not automatically provide application-level mutual
    exclusion for arbitrary read-modify-write workflows.
    """)


# ============================================================================
# 119. ATOMIC CREATE AS LOCKING BUILDING BLOCK
# ============================================================================

print_title("119. ATOMIC EXCLUSIVE CREATION")

with tempfile.TemporaryDirectory(prefix="linux_lockfile_") as temp_directory:
    base = Path(temp_directory)
    lock_path = base / "application.lock"

    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError:
        print("Lock already exists.")
    else:
        try:
            os.write(descriptor, f"PID={os.getpid()}\n".encode())
            print("Lock acquired:", lock_path)
        finally:
            os.close(descriptor)
            lock_path.unlink()


# ============================================================================
# 120. FILESYSTEM CACHE
# ============================================================================

print_title("120. PAGE CACHE CONCEPT")

explain(
    """
    Linux uses memory to cache filesystem data. Reading a file does not
    necessarily mean that every byte is fetched directly from physical
    storage for every read.

    The page cache can make repeated access much faster, but cache behavior
    should not be confused with permanent durability.
    """)


# ============================================================================
# 121. BUFFERING
# ============================================================================

print_title("121. PYTHON BUFFERING")

with tempfile.TemporaryDirectory(prefix="linux_buffering_") as temp_directory:
    path = Path(temp_directory) / "buffered.txt"

    with path.open("w", encoding="utf-8") as file_object:
        print("Python buffering object:", type(file_object))
        file_object.write("Buffered output\n")
        file_object.flush()

    print(path.read_text(encoding="utf-8"))


# ============================================================================
# 122. TEXT MODE VERSUS BINARY MODE
# ============================================================================

print_title("122. TEXT MODE VERSUS BINARY MODE")

with tempfile.TemporaryDirectory(prefix="linux_modes_") as temp_directory:
    base = Path(temp_directory)

    text_path = base / "text.txt"
    binary_path = base / "binary.bin"

    text_path.write_text("hello\n", encoding="utf-8")
    binary_path.write_bytes(b"\x00\x01\x02")

    print("Text read:", text_path.read_text(encoding="utf-8"))
    print("Binary read:", binary_path.read_bytes())


# ============================================================================
# 123. ENCODING ERRORS
# ============================================================================

print_title("123. ENCODING IS AN APPLICATION CONCERN")

with tempfile.TemporaryDirectory(prefix="linux_encoding_error_") as temp_directory:
    path = Path(temp_directory) / "bytes.bin"
    path.write_bytes(b"\xff\xfe\xfd")

    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        print("UTF-8 decoding failed:", exc)

    print("Raw bytes:", path.read_bytes())


# ============================================================================
# 124. FILE BUFFERING AND fsync
# ============================================================================

print_title("124. FLUSH IS NOT THE SAME AS fsync")

explain(
    """
    file_object.flush() transfers buffered Python data to the operating
    system's file descriptor.

    os.fsync() requests synchronization of the descriptor's file state to
    storage.

    Therefore:

        Python buffer -> flush -> kernel -> fsync -> storage synchronization

    is a useful conceptual model. Real storage stacks can contain additional
    caching layers.
    """)


# ============================================================================
# 125. FILESYSTEM MOUNTS AND CURRENT PROCESS
# ============================================================================

print_title("125. PROCESS-SPECIFIC MOUNT VIEW")

if mountinfo_path.exists():
    print("The current process reads /proc/self/mountinfo.")
    print("PID:", os.getpid())
    explain(
        """
        The use of /proc/self rather than a hard-coded process number is a
        useful Linux pattern. It refers to the calling process.
        """
    )


# ============================================================================
# 126. MOUNT TABLE COMPARISON
# ============================================================================

print_title("126. /PROC/MOUNTS AND MOUNTINFO")

for path in [Path("/proc/mounts"), Path("/proc/self/mountinfo")]:
    print(path, "exists:", path.exists())

explain(
    """
    /proc/mounts presents mount information in a traditional format.
    /proc/self/mountinfo provides richer mount-namespace and mount hierarchy
    information.

    Modern programs should choose the interface appropriate to the exact
    information they require.
    """)


# ============================================================================
# 127. FILESYSTEM HIERARCHY AND APPLICATION DESIGN
# ============================================================================

print_title("127. APPLICATION DATA LOCATIONS")

application_locations = {
    "configuration": "/etc or application-specific configuration location",
    "user data": "/home/<user> or platform-specific user data directory",
    "temporary data": "/tmp or application-managed temporary directory",
    "runtime state": "/run for system services",
    "logs": "/var/log or service-specific logging system",
    "persistent service data": "/var/lib/<service>",
    "cache": "/var/cache/<service>",
}

for category, location in application_locations.items():
    print(f"{category:22}: {location}")


# ============================================================================
# 128. /VAR/LIB
# ============================================================================

print_title("128. /VAR/LIB")

explain(
    """
    /var/lib is traditionally used for persistent state maintained by
    applications and services, such as package databases, service databases,
    and other machine-local application state.

    It is distinct from /var/log, which conventionally stores logs, and
    /var/cache, which contains data that can generally be regenerated.
    """)


# ============================================================================
# 129. /VAR/LOG
# ============================================================================

print_title("129. /VAR/LOG")

var_log = Path("/var/log")

print("/var/log exists:", var_log.exists())
if var_log.exists() and var_log.is_dir():
    try:
        for entry in sorted(var_log.iterdir())[:15]:
            print(" ", entry.name)
    except OSError as exc:
        print("Could not list /var/log:", exc)


# ============================================================================
# 130. /ETC
# ============================================================================

print_title("130. /ETC")

etc = Path("/etc")

if etc.exists():
    print("/etc exists:", etc.exists())
    print("/etc is directory:", etc.is_dir())

    common_configuration_files = [
        "hosts",
        "passwd",
        "group",
        "fstab",
        "hostname",
    ]

    for filename in common_configuration_files:
        path = etc / filename
        print(f"{path}: exists={path.exists()}")


# ============================================================================
# 131. /HOME
# ============================================================================

print_title("131. /HOME")

home = Path("/home")

if home.exists():
    print("/home exists:", home.exists())
    try:
        for entry in sorted(home.iterdir()):
            print(" ", entry.name)
    except PermissionError:
        print("Permission denied while listing /home.")


# ============================================================================
# 132. /BOOT
# ============================================================================

print_title("132. /BOOT")

boot = Path("/boot")

if boot.exists():
    print("/boot exists:", boot.exists())
    print("/boot is directory:", boot.is_dir())


# ============================================================================
# 133. /RUN
# ============================================================================

print_title("133. /RUN")

run_directory = Path("/run")

if run_directory.exists():
    print("/run exists:", run_directory.exists())
    print("/run is directory:", run_directory.is_dir())

explain(
    """
    /run commonly contains volatile runtime state such as process IDs,
    sockets, service state, and other information that is meaningful during
    the current boot.
    """)


# ============================================================================
# 134. /MEDIA AND /MNT
# ============================================================================

print_title("134. /MEDIA AND /MNT")

for path in [Path("/media"), Path("/mnt")]:
    print(path, "exists:", path.exists())
    if path.exists():
        try:
            print(" entries:", [entry.name for entry in path.iterdir()][:10])
        except OSError as exc:
            print(" could not list:", exc)


# ============================================================================
# 135. PATH ENVIRONMENT VARIABLE
# ============================================================================

print_title("135. PATH ENVIRONMENT VARIABLE")

environment_path = os.environ.get("PATH", "")
path_entries = environment_path.split(os.pathsep)

print("PATH contains", len(path_entries), "entries.")

for entry in path_entries[:15]:
    print(" ", entry)

explain(
    """
    The PATH environment variable is not the Linux filesystem hierarchy.
    It is a list of directories searched by command interpreters and process
    launch mechanisms when resolving executable command names.
    """)


# ============================================================================
# 136. PATH NAME COLLISION
# ============================================================================

print_title("136. COMMAND PATH VERSUS FILE PATH")

explain(
    """
    Consider the command:

        python

    A shell can search directories listed in PATH to find an executable.

    A filesystem path such as:

        /usr/bin/python

    identifies a specific namespace location.

    These concepts are related but should not be conflated.
    """)


# ============================================================================
# 137. ENVIRONMENT VARIABLE INSPECTION
# ============================================================================

print_title("137. ENVIRONMENT VARIABLES")

for variable in ["HOME", "PWD", "PATH", "TMPDIR"]:
    print(f"{variable}: {os.environ.get(variable)}")


# ============================================================================
# 138. HOME DIRECTORY
# ============================================================================

print_title("138. HOME DIRECTORY")

home_from_expanduser = Path("~").expanduser()

print("Expanded ~:", home_from_expanduser)
print("Exists:", home_from_expanduser.exists())

explain(
    """
    The tilde character is primarily shell syntax. Python's Path.expanduser()
    explicitly performs home-directory expansion.

    A program should not assume that ~ is automatically expanded by pathlib
    path construction.
    """)


# ============================================================================
# 139. USER CONFIGURATION
# ============================================================================

print_title("139. USER CONFIGURATION PATHS")

user_home = Path.home()

print("Path.home():", user_home)
print("Example configuration path:", user_home / ".config" / "example")


# ============================================================================
# 140. HIDDEN CONFIGURATION FILES
# ============================================================================

print_title("140. DOTFILES")

explain(
    """
    User-level configuration often uses filenames beginning with a dot,
    historically called dotfiles. Modern applications may also use
    structured directories such as ~/.config.

    A leading dot is a naming convention, not a distinct filesystem type.
    """)


# ============================================================================
# 141. FILESYSTEM TESTING
# ============================================================================

print_title("141. TESTING FILESYSTEM CODE")

def create_test_tree(root_directory: Path) -> None:
    """Create a deterministic filesystem tree for tests."""
    (root_directory / "data").mkdir(parents=True)
    (root_directory / "data" / "input.txt").write_text(
        "test input",
        encoding="utf-8",
    )
    (root_directory / "data" / "empty.txt").write_text(
        "",
        encoding="utf-8",
    )
    (root_directory / "data-link").symlink_to(
        root_directory / "data",
        target_is_directory=True,
    )


def count_regular_files(root_directory: Path) -> int:
    """Count regular files without following symbolic links."""
    count = 0

    for path in root_directory.rglob("*"):
        try:
            if path.is_symlink():
                continue
            if path.is_file():
                count += 1
        except OSError:
            continue

    return count


with tempfile.TemporaryDirectory(prefix="linux_test_tree_") as temp_directory:
    base = Path(temp_directory)
    create_test_tree(base)

    print("Regular files:", count_regular_files(base))


# ============================================================================
# 142. ASSERTIONS FOR FILESYSTEM TESTS
# ============================================================================

print_title("142. FILESYSTEM ASSERTIONS")

with tempfile.TemporaryDirectory(prefix="linux_assertions_") as temp_directory:
    base = Path(temp_directory)

    file_path = base / "test.txt"
    file_path.write_text("test", encoding="utf-8")

    assert file_path.exists()
    assert file_path.is_file()
    assert file_path.read_text(encoding="utf-8") == "test"

    print("Filesystem assertions passed.")


# ============================================================================
# 143. EDGE CASE: EMPTY FILE
# ============================================================================

print_title("143. EDGE CASE: EMPTY FILE")

with tempfile.TemporaryDirectory(prefix="linux_empty_") as temp_directory:
    path = Path(temp_directory) / "empty"

    path.touch()

    print("Exists:", path.exists())
    print("Is file:", path.is_file())
    print("Size:", path.stat().st_size)


# ============================================================================
# 144. EDGE CASE: EMPTY DIRECTORY
# ============================================================================

print_title("144. EDGE CASE: EMPTY DIRECTORY")

with tempfile.TemporaryDirectory(prefix="linux_empty_dir_") as temp_directory:
    path = Path(temp_directory) / "empty"
    path.mkdir()

    print("Entries:", list(path.iterdir()))
    print("Can remove with rmdir:", end=" ")

    path.rmdir()
    print("yes")


# ============================================================================
# 145. EDGE CASE: SAME PATH
# ============================================================================

print_title("145. EDGE CASE: SAME PATH")

with tempfile.TemporaryDirectory(prefix="linux_same_path_") as temp_directory:
    path = Path(temp_directory) / "file.txt"
    path.write_text("data", encoding="utf-8")

    print("resolve() == resolve():", path.resolve() == path.resolve())
    print("inode:", path.stat().st_ino)


# ============================================================================
# 146. EDGE CASE: MULTIPLE SLASHES
# ============================================================================

print_title("146. MULTIPLE SLASHES")

paths = [
    "/tmp/example",
    "/tmp//example",
    "/tmp///example",
]

for path in paths:
    print(path, "->", os.path.normpath(path))

explain(
    """
    Linux path parsing has specific rules for repeated separators. Application
    code should generally use pathlib or os.path rather than implementing
    its own path parser.
    """)


# ============================================================================
# 147. EDGE CASE: TRAILING SLASH
# ============================================================================

print_title("147. TRAILING SLASH")

with tempfile.TemporaryDirectory(prefix="linux_trailing_") as temp_directory:
    base = Path(temp_directory)
    directory = base / "directory"
    directory.mkdir()

    trailing = Path(str(directory) + "/")

    print("Path:", trailing)
    print("Exists:", trailing.exists())
    print("Is directory:", trailing.is_dir())


# ============================================================================
# 148. EDGE CASE: PERMISSION FAILURE
# ============================================================================

print_title("148. PERMISSION ERRORS")

explain(
    """
    A filesystem operation can fail because the user lacks permission even
    when the path exists.

    Testing permission failures reliably is difficult when running as root,
    because root privileges can bypass many normal permission checks. Good
    tests should therefore control the test environment rather than assuming
    a particular host permission configuration.
    """)


# ============================================================================
# 149. EDGE CASE: RACE CONDITIONS
# ============================================================================

print_title("149. FILESYSTEM RACE CONDITIONS")

explain(
    """
    Filesystem state can change between two operations.

    This is unsafe in principle:

        if path.exists():
            path.read_text()

    Another process can remove, replace, or redirect the path between the
    existence check and the read.

    Prefer performing the operation directly and handling its exception.
    """)


# ============================================================================
# 150. EAFP STYLE
# ============================================================================

print_title("150. EAFP FILESYSTEM PROGRAMMING")

def read_text_if_available(path: Path) -> Optional[str]:
    """
    Attempt the operation and handle the failure.

    This follows Python's EAFP style: Easier to Ask Forgiveness than
    Permission.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except PermissionError:
        return None


with tempfile.TemporaryDirectory(prefix="linux_eafp_") as temp_directory:
    path = Path(temp_directory) / "missing.txt"
    print("Result:", read_text_if_available(path))


# ============================================================================
# 151. LBYL VERSUS EAFP
# ============================================================================

print_title("151. LBYL VERSUS EAFP")

comparison = [
    (
        "LBYL",
        "Look Before You Leap",
        "Check state first, then perform operation.",
    ),
    (
        "EAFP",
        "Easier to Ask Forgiveness",
        "Perform operation and handle exception.",
    ),
]

for style, expansion, description in comparison:
    print(f"{style:6} {expansion:28} {description}")


# ============================================================================
# 152. RENAME WITH CONFLICT
# ============================================================================

print_title("152. REPLACEMENT SEMANTICS")

with tempfile.TemporaryDirectory(prefix="linux_replace_") as temp_directory:
    base = Path(temp_directory)

    source = base / "source"
    destination = base / "destination"

    source.write_text("source", encoding="utf-8")
    destination.write_text("destination", encoding="utf-8")

    os.replace(source, destination)

    print("Source exists:", source.exists())
    print("Destination content:", destination.read_text(encoding="utf-8"))


# ============================================================================
# 153. PATH OBJECT COMPARISON
# ============================================================================

print_title("153. PATH STRING COMPARISON")

paths = [
    Path("/tmp/example"),
    Path("/tmp/./example"),
    Path("/tmp/example/../example"),
]

for path in paths:
    print(path, "->", path.resolve(strict=False))


# ============================================================================
# 154. RESOLVE STRICTNESS
# ============================================================================

print_title("154. resolve(strict=False)")

with tempfile.TemporaryDirectory(prefix="linux_resolve_strict_") as temp_directory:
    base = Path(temp_directory)
    missing = base / "missing" / "file.txt"

    print("Non-strict resolution:", missing.resolve(strict=False))

    try:
        print("Strict resolution:", missing.resolve(strict=True))
    except FileNotFoundError as exc:
        print("Strict resolution failed:", exc)


# ============================================================================
# 155. DIRECTORY FILE DESCRIPTOR AND RELATIVE OPERATIONS
# ============================================================================

print_title("155. DIRECTORY-RELATIVE OPEN")

if os.name == "posix":
    with tempfile.TemporaryDirectory(prefix="linux_dir_relative_") as temp_directory:
        base = Path(temp_directory)
        file_path = base / "relative.txt"
        file_path.write_text("directory-relative access", encoding="utf-8")

        try:
            directory_fd = os.open(base, os.O_RDONLY)
        except OSError as exc:
            print("Could not open directory:", exc)
        else:
            try:
                file_fd = os.open("relative.txt", os.O_RDONLY, dir_fd=directory_fd)

                try:
                    with os.fdopen(file_fd, "r", encoding="utf-8") as file_object:
                        print(file_object.read())
                except OSError:
                    os.close(file_fd)
            finally:
                os.close(directory_fd)


# ============================================================================
# 156. NOFOLLOW CONCEPT
# ============================================================================

print_title("156. O_NOFOLLOW CONCEPT")

if hasattr(os, "O_NOFOLLOW"):
    print("This system exposes os.O_NOFOLLOW:", os.O_NOFOLLOW)
else:
    print("os.O_NOFOLLOW is unavailable in this Python environment.")

explain(
    """
    O_NOFOLLOW can be used on supported systems to prevent a final symbolic
    link from being followed during an open operation.

    It is one component of secure path handling, not a universal solution to
    every filesystem race or traversal problem.
    """)


# ============================================================================
# 157. NOFOLLOW DEMONSTRATION
# ============================================================================

if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
    print_title("157. O_NOFOLLOW DEMONSTRATION")

    with tempfile.TemporaryDirectory(prefix="linux_nofollow_") as temp_directory:
        base = Path(temp_directory)
        target = base / "target.txt"
        link = base / "link.txt"

        target.write_text("target", encoding="utf-8")
        link.symlink_to(target)

        try:
            descriptor = os.open(link, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            print("Opening final symlink without following failed:", exc)
        else:
            os.close(descriptor)


# ============================================================================
# 158. FILESYSTEM LIMITATIONS
# ============================================================================

print_title("158. IMPORTANT LIMITATIONS")

limitations = [
    "Filesystem semantics vary between Linux filesystem implementations.",
    "Not every Linux installation uses the same directory layout.",
    "Permissions can be supplemented by ACLs and security frameworks.",
    "Mount behavior depends on namespaces and mount options.",
    "Network filesystems can have different consistency characteristics.",
    "Distributed filesystems can differ substantially from local filesystems.",
    "Pathlib cannot abstract every Linux-specific filesystem feature.",
    "File timestamps have filesystem-specific precision and semantics.",
    "Durability guarantees depend on the entire storage stack.",
]

for limitation in limitations:
    print("•", limitation)


# ============================================================================
# 159. PERFORMANCE CONSIDERATIONS
# ============================================================================

print_title("159. PERFORMANCE CONSIDERATIONS")

performance_points = [
    "Avoid unnecessary repeated stat calls.",
    "Use scandir-style directory iteration for large trees when appropriate.",
    "Do not recursively traverse huge trees without considering cost.",
    "Avoid reading an entire large file when streaming is sufficient.",
    "Use buffered I/O for sequential large-file processing.",
    "Batch related operations when possible.",
    "Avoid excessive path resolution when the same path can be reused safely.",
    "Consider filesystem and network-filesystem latency.",
    "Use appropriate atomic-update patterns for frequently modified files.",
]

for point in performance_points:
    print("•", point)


# ============================================================================
# 160. os.scandir PERFORMANCE
# ============================================================================

print_title("160. os.scandir")

with tempfile.TemporaryDirectory(prefix="linux_scandir_") as temp_directory:
    base = Path(temp_directory)

    for index in range(5):
        (base / f"file-{index}.txt").write_text(
            str(index),
            encoding="utf-8",
        )

    with os.scandir(base) as entries:
        for entry in entries:
            print(
                entry.name,
                "directory=",
                entry.is_dir(follow_symlinks=False),
                "file=",
                entry.is_file(follow_symlinks=False),
            )

explain(
    """
    os.scandir can provide directory entries with cached metadata information
    on many systems and is often preferable to repeatedly constructing paths
    and calling separate stat operations when processing large directories.
    """)


# ============================================================================
# 161. STREAMING LARGE FILES
# ============================================================================

print_title("161. STREAMING FILE CONTENT")

with tempfile.TemporaryDirectory(prefix="linux_stream_") as temp_directory:
    path = Path(temp_directory) / "large-log.txt"

    path.write_text(
        "\n".join(f"log line {index}" for index in range(100)),
        encoding="utf-8",
    )

    line_count = 0

    with path.open("r", encoding="utf-8") as file_object:
        for line in file_object:
            line_count += 1

    print("Lines processed without read_text():", line_count)


# ============================================================================
# 162. HASHING A FILE
# ============================================================================

print_title("162. STREAMING HASH CONCEPT")

import hashlib


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-256 without loading the entire file into memory."""
    digest = hashlib.sha256()

    with path.open("rb") as file_object:
        while True:
            chunk = file_object.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


with tempfile.TemporaryDirectory(prefix="linux_hash_") as temp_directory:
    path = Path(temp_directory) / "data.txt"
    path.write_text("filesystem hashing example", encoding="utf-8")

    print("SHA-256:", sha256_file(path))


# ============================================================================
# 163. HASHING AND FILE IDENTITY
# ============================================================================

print_title("163. HASH EQUALITY VERSUS FILE IDENTITY")

explain(
    """
    Two files with the same SHA-256 hash are content-equivalent with very
    high probability, but they are not necessarily the same filesystem
    object.

    Conversely, two hard links are the same underlying inode even though
    their pathnames differ.
    """)


# ============================================================================
# 164. CHECKSUM DEMONSTRATION
# ============================================================================

with tempfile.TemporaryDirectory(prefix="linux_hash_compare_") as temp_directory:
    base = Path(temp_directory)

    first = base / "first"
    second = base / "second"

    first.write_text("same content", encoding="utf-8")
    second.write_text("same content", encoding="utf-8")

    print("Same hash:", sha256_file(first) == sha256_file(second))
    print("Same inode:", first.stat().st_ino == second.stat().st_ino)


# ============================================================================
# 165. MOUNT BOUNDARIES AND HARD LINKS
# ============================================================================

print_title("165. HARD LINKS AND FILESYSTEM BOUNDARIES")

explain(
    """
    Hard links generally cannot cross filesystem boundaries. A hard link
    identifies an inode in a particular filesystem.

    This is one reason a hard link cannot normally be created between
    unrelated mounted filesystems. A cross-filesystem attempt commonly fails
    with EXDEV.
    """)


# ============================================================================
# 166. SYMBOLIC LINKS CAN CROSS FILESYSTEMS
# ============================================================================

print_title("166. SYMBOLIC LINKS AND FILESYSTEM BOUNDARIES")

explain(
    """
    Symbolic links store pathnames rather than directly referring to an inode.
    Therefore a symbolic link can refer to a path located on another
    filesystem, provided that the target path is valid from the link's
    namespace.
    """)


# ============================================================================
# 167. MOUNT HIDING
# ============================================================================

print_title("167. MOUNT POINT HIDING")

explain(
    """
    If an ordinary directory contains files and another filesystem is mounted
    on that directory, normal path traversal enters the mounted filesystem.
    The original underlying directory contents are hidden from that path while
    the mount is active.

    Unmounting reveals the underlying directory again.
    """)


# ============================================================================
# 168. MOUNTED FILESYSTEM UNAVAILABLE
# ============================================================================

print_title("168. UNMOUNT CONSEQUENCES")

explain(
    """
    Applications should not assume that a mounted path remains available
    forever. Removable storage can disappear, network filesystems can become
    unavailable, and administrators can change mounts.

    Robust programs handle I/O errors even after a path was successfully
    accessed earlier.
    """)


# ============================================================================
# 169. NETWORK FILESYSTEMS
# ============================================================================

print_title("169. NETWORK FILESYSTEMS")

explain(
    """
    NFS and other network filesystems expose remote data through filesystem
    paths.

    Network filesystem behavior can differ from local filesystems in latency,
    caching, failure modes, locking behavior, and consistency guarantees.

    Code that performs many small filesystem operations can be especially
    sensitive to network latency.
    """)


# ============================================================================
# 170. CONTAINER FILESYSTEM VIEW
# ============================================================================

print_title("170. CONTAINERS AND THE FILESYSTEM")

explain(
    """
    Containers usually share the host kernel while receiving isolated
    namespaces and filesystem views.

    A container filesystem may combine image layers, writable layers, bind
    mounts, named volumes, pseudo-filesystems, and temporary filesystems.

    A path such as / inside a container therefore represents the root of that
    container's filesystem view, not necessarily the physical host root.
    """)


# ============================================================================
# 171. CHROOT CONCEPT
# ============================================================================

print_title("171. CHROOT")

explain(
    """
    chroot changes the apparent root directory for a process and its
    descendants.

    It is useful as a filesystem namespace mechanism in certain contexts,
    but chroot alone is not a complete security boundary. Modern isolation
    systems generally use namespaces, capabilities, filesystem restrictions,
    and other controls.
    """)


# ============================================================================
# 172. MOUNT NAMESPACE VERSUS CHROOT
# ============================================================================

print_title("172. MOUNT NAMESPACE VERSUS CHROOT")

comparison = [
    ("chroot", "Changes apparent root for pathname lookup."),
    ("mount namespace", "Provides an independent view of mounts."),
    ("container", "Usually combines several isolation mechanisms."),
]

for concept, description in comparison:
    print(f"{concept:20}: {description}")


# ============================================================================
# 173. /PROC AND CONTAINERS
# ============================================================================

print_title("173. /PROC IN CONTAINERS")

explain(
    """
    A container can receive a namespace-specific /proc view. This is one
    reason that reading /proc/self and similar paths can provide information
    specific to the current process and its namespace context.
    """)


# ============================================================================
# 174. FILESYSTEM MOUNTS AS TREE EDGES
# ============================================================================

print_title("174. MOUNTS AS NAMESPACE TRANSITIONS")

explain(
    """
    A useful mental model is to think of a filesystem hierarchy as a tree in
    which mount points act as transitions into another filesystem tree.

        root tree
            |
            +-- /data  ---> mounted filesystem tree
                                |
                                +-- documents
                                +-- images

    Path traversal remains uniform from the application's perspective.
    """)


# ============================================================================
# 175. PRACTICAL FILE COPY
# ============================================================================

print_title("175. PRACTICAL FILE BACKUP")

def copy_file_with_metadata(source: Path, destination: Path) -> None:
    """Copy one regular file while preserving supported metadata."""
    if not source.is_file():
        raise ValueError(f"Source is not a regular file: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


with tempfile.TemporaryDirectory(prefix="linux_backup_") as temp_directory:
    base = Path(temp_directory)

    source = base / "source" / "important.txt"
    backup = base / "backup" / "important.txt"

    source.parent.mkdir(parents=True)
    source.write_text("backup data", encoding="utf-8")

    copy_file_with_metadata(source, backup)

    print("Backup created:", backup)
    print("Backup content:", backup.read_text(encoding="utf-8"))


# ============================================================================
# 176. PRACTICAL SAFE WRITE
# ============================================================================

print_title("176. PRACTICAL SAFE WRITE")

def atomic_write_text(
    destination: Path,
    content: str,
    encoding: str = "utf-8",
) -> None:
    """
    Write content to a temporary sibling and atomically replace destination.

    This example demonstrates namespace-level atomic replacement. A
    production durability-sensitive application may also need fsync calls.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_name = destination.with_name(
        f".{destination.name}.tmp-{os.getpid()}"
    )

    try:
        with temporary_name.open("w", encoding=encoding) as file_object:
            file_object.write(content)
            file_object.flush()
            os.fsync(file_object.fileno())

        os.replace(temporary_name, destination)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary_name.unlink()


with tempfile.TemporaryDirectory(prefix="linux_atomic_write_") as temp_directory:
    path = Path(temp_directory) / "settings.conf"

    atomic_write_text(
        path,
        "theme=dark\n"
        "language=en\n",
    )

    print(path.read_text(encoding="utf-8"))


# ============================================================================
# 177. PRACTICAL DIRECTORY INVENTORY
# ============================================================================

print_title("177. PRACTICAL DIRECTORY INVENTORY")

def directory_summary(path: Path) -> dict[str, int]:
    """Count directories, regular files, symbolic links, and other objects."""
    summary = {
        "directories": 0,
        "regular_files": 0,
        "symbolic_links": 0,
        "other": 0,
    }

    for entry in path.rglob("*"):
        try:
            metadata = entry.lstat()
        except OSError:
            continue

        mode = metadata.st_mode

        if stat.S_ISDIR(mode):
            summary["directories"] += 1
        elif stat.S_ISREG(mode):
            summary["regular_files"] += 1
        elif stat.S_ISLNK(mode):
            summary["symbolic_links"] += 1
        else:
            summary["other"] += 1

    return summary


with tempfile.TemporaryDirectory(prefix="linux_summary_") as temp_directory:
    base = Path(temp_directory)

    (base / "a").mkdir()
    (base / "b").mkdir()
    (base / "a" / "one").write_text("1", encoding="utf-8")
    (base / "b" / "two").write_text("2", encoding="utf-8")
    (base / "link").symlink_to(base / "a")

    print(directory_summary(base))


# ============================================================================
# 178. BEST PRACTICES
# ============================================================================

print_title("178. FILESYSTEM BEST PRACTICES")

best_practices = [
    "Use pathlib for clear path manipulation.",
    "Use absolute paths where a fixed system location is genuinely required.",
    "Use relative paths when an application should remain relocatable.",
    "Do not concatenate path strings manually.",
    "Handle FileNotFoundError, PermissionError, OSError, and related failures.",
    "Avoid check-then-use filesystem races.",
    "Use O_CREAT|O_EXCL for exclusive creation when appropriate.",
    "Use atomic replacement for configuration updates.",
    "Avoid following untrusted symbolic links unintentionally.",
    "Do not run recursive deletion on untrusted paths without strict validation.",
    "Use temporary directories for tests.",
    "Do not assume /bin, /sbin, /lib, and /lib64 are always independent directories.",
    "Do not assume every filesystem is local or writable.",
    "Treat /proc, /sys, and /dev as special system interfaces.",
    "Request only the privileges required for the operation.",
]

for practice in best_practices:
    print("•", practice)


# ============================================================================
# 179. COMMON MISTAKES
# ============================================================================

print_title("179. COMMON MISTAKES")

mistakes = [
    (
        "Using / as a normal application working directory",
        "Use an application-specific writable directory.",
    ),
    (
        "Assuming exists() guarantees the next operation will succeed",
        "Perform the operation and handle exceptions.",
    ),
    (
        "Using rmtree() without understanding symbolic links",
        "Inspect links and define an explicit traversal policy.",
    ),
    (
        "Treating symlink metadata as target metadata",
        "Use lstat() when the link itself matters.",
    ),
    (
        "Assuming ctime means creation time",
        "On Linux, ctime normally represents inode metadata change time.",
    ),
    (
        "Assuming file size equals allocated storage",
        "Consider sparse files, filesystem blocks, and metadata.",
    ),
    (
        "Assuming the filesystem hierarchy is one disk",
        "Mounts can combine many filesystems into one namespace.",
    ),
    (
        "Assuming all files are persistent disk files",
        "procfs, sysfs, tmpfs, devices, sockets, and FIFOs also exist.",
    ),
    (
        "Using shell commands for every filesystem task",
        "Use direct Python APIs when appropriate.",
    ),
]

for mistake, correction in mistakes:
    print(f"\nMistake : {mistake}")
    print(f"Better  : {correction}")


# ============================================================================
# 180. PRODUCTION DESIGN CHECKLIST
# ============================================================================

print_title("180. PRODUCTION FILESYSTEM DESIGN CHECKLIST")

checklist = [
    "Define the intended root directory.",
    "Define whether symbolic links are allowed.",
    "Define whether cross-filesystem access is allowed.",
    "Validate untrusted path components.",
    "Consider TOCTOU races.",
    "Use descriptor-relative operations for high-security boundaries.",
    "Handle permission and availability failures.",
    "Use atomic replacement for critical updates.",
    "Consider durability requirements.",
    "Define cleanup behavior.",
    "Avoid uncontrolled recursive deletion.",
    "Consider filesystem capacity and quotas.",
    "Consider network filesystem behavior.",
    "Test on the actual Linux filesystem types that matter.",
    "Document required privileges.",
]

for item in checklist:
    print("[ ]", item)


# ============================================================================
# 181. CONCEPTUAL RELATIONSHIP MAP
# ============================================================================

print_title("181. CONCEPTUAL RELATIONSHIP MAP")

explain(
    """
    The major concepts fit together as follows:

        Linux namespace
              |
              +-- paths
              |     |
              |     +-- directories
              |     +-- directory entries
              |     +-- symbolic links
              |
              +-- filesystems
              |     |
              |     +-- inodes
              |     +-- data blocks
              |     +-- metadata
              |
              +-- mounts
                    |
                    +-- attach filesystems into namespace
                    +-- create filesystem boundaries
                    +-- interact with namespaces

    Hard links connect multiple directory entries to one inode. Symbolic
    links are separate objects containing pathnames. Mounts connect another
    filesystem into the path namespace.
    """
)


# ============================================================================
# 182. INTEGRATED DEMONSTRATION
# ============================================================================

print_title("182. INTEGRATED FILESYSTEM DEMONSTRATION")

with tempfile.TemporaryDirectory(prefix="linux_integrated_") as temp_directory:
    root_directory = Path(temp_directory)

    # Build an application-style directory hierarchy.
    config_directory = root_directory / "etc"
    data_directory = root_directory / "var" / "lib" / "application"
    log_directory = root_directory / "var" / "log"
    user_directory = root_directory / "home" / "student"

    for directory in [
        config_directory,
        data_directory,
        log_directory,
        user_directory,
    ]:
        directory.mkdir(parents=True)

    # Create files.
    config = config_directory / "application.conf"
    database = data_directory / "database.dat"
    log = log_directory / "application.log"
    notes = user_directory / "notes.txt"

    config.write_text("mode=production\n", encoding="utf-8")
    database.write_text("database state\n", encoding="utf-8")
    log.write_text("application started\n", encoding="utf-8")
    notes.write_text("filesystem notes\n", encoding="utf-8")

    # Create a symbolic link.
    latest_log = user_directory / "latest.log"
    latest_log.symlink_to(log)

    # Create a hard link to demonstrate inode sharing.
    database_backup = data_directory / "database.backup"
    os.link(database, database_backup)

    print("Hierarchy:")
    for path in sorted(root_directory.rglob("*")):
        relative = path.relative_to(root_directory)

        if path.is_symlink():
            description = f"symlink -> {path.readlink()}"
        elif path.is_dir():
            description = "directory"
        elif path.is_file():
            description = "regular file"
        else:
            description = "other"

        print(f"  {relative} [{description}]")

    print("\nDatabase inode:")
    print("  database:", database.stat().st_ino)
    print("  backup  :", database_backup.stat().st_ino)
    print("  same    :", database.stat().st_ino == database_backup.stat().st_ino)

    print("\nLatest log:")
    print("  link target:", latest_log.readlink())
    print("  content:", latest_log.read_text(encoding="utf-8").strip())


# ============================================================================
# 183. MINI FILESYSTEM INSPECTOR
# ============================================================================

print_title("183. MINI FILESYSTEM INSPECTOR")

def inspect_path(path: Path) -> None:
    """Print useful metadata for one filesystem path."""
    try:
        link_metadata = path.lstat()
    except FileNotFoundError:
        print("Path does not exist:", path)
        return
    except OSError as exc:
        print("Could not inspect:", exc)
        return

    mode = link_metadata.st_mode

    if stat.S_ISLNK(mode):
        object_type = "symbolic link"
    elif stat.S_ISDIR(mode):
        object_type = "directory"
    elif stat.S_ISREG(mode):
        object_type = "regular file"
    elif stat.S_ISCHR(mode):
        object_type = "character device"
    elif stat.S_ISBLK(mode):
        object_type = "block device"
    elif stat.S_ISFIFO(mode):
        object_type = "FIFO"
    elif stat.S_ISSOCK(mode):
        object_type = "socket"
    else:
        object_type = "other"

    print("Path:", path)
    print("Type:", object_type)
    print("Mode:", stat.filemode(mode))
    print("Size:", link_metadata.st_size)
    print("Inode:", link_metadata.st_ino)
    print("Device:", link_metadata.st_dev)
    print("Links:", link_metadata.st_nlink)
    print("UID:", link_metadata.st_uid)
    print("GID:", link_metadata.st_gid)

    if stat.S_ISLNK(mode):
        print("Link target:", path.readlink())


with tempfile.TemporaryDirectory(prefix="linux_inspector_") as temp_directory:
    base = Path(temp_directory)
    path = base / "example.txt"
    path.write_text("inspect me", encoding="utf-8")

    link = base / "example-link"
    link.symlink_to(path)

    inspect_path(path)
    print()
    inspect_path(link)


# ============================================================================
# 184. MINI MOUNT INSPECTOR
# ============================================================================

print_title("184. MINI MOUNT INSPECTOR")

def get_mounts() -> list[MountInfo]:
    """Return parsed mount information for the current Linux process."""
    path = Path("/proc/self/mountinfo")

    if not path.exists():
        return []

    mounts: list[MountInfo] = []

    try:
        lines = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError:
        return []

    for line in lines:
        item = parse_mountinfo_line(line)
        if item is not None:
            mounts.append(item)

    return mounts


mounts = get_mounts()

if mounts:
    print("Number of mounts visible to this process:", len(mounts))

    for mount in mounts[:20]:
        print(
            f"{mount.mount_point:40} "
            f"{mount.filesystem_type:12} "
            f"{mount.source}"
        )
else:
    print("No Linux mountinfo data available.")


# ============================================================================
# 185. FILESYSTEM KNOWLEDGE TESTS
# ============================================================================

print_title("185. KNOWLEDGE CHECK")

questions = [
    (
        "What is the root directory?",
        "The top of the Linux filesystem namespace, written as /.",
    ),
    (
        "What does an absolute path provide?",
        "A location beginning at / rather than depending on the current directory.",
    ),
    (
        "What is an inode?",
        "A filesystem object containing metadata and references to stored data.",
    ),
    (
        "What does a hard link reference?",
        "The same underlying inode as another directory entry.",
    ),
    (
        "What does a symbolic link contain?",
        "A pathname referring to another object.",
    ),
    (
        "Can symbolic links cross filesystem boundaries?",
        "Yes, because they store pathnames rather than inode references.",
    ),
    (
        "Can hard links normally cross filesystem boundaries?",
        "No.",
    ),
    (
        "What is a mount point?",
        "A directory where another filesystem is attached to the namespace.",
    ),
    (
        "What is /proc?",
        "A virtual filesystem exposing process and kernel information.",
    ),
    (
        "What does lstat do?",
        "It returns metadata for the link itself rather than following a symbolic link.",
    ),
]

for question, answer in questions:
    print("\nQuestion:", question)
    print("Answer  :", answer)


# ============================================================================
# 186. ADVANCED DESIGN PRINCIPLES
# ============================================================================

print_title("186. ADVANCED DESIGN PRINCIPLES")

principles = [
    (
        "Namespace abstraction",
        "Treat paths as names in a namespace rather than physical disk addresses.",
    ),
    (
        "Object identity",
        "Distinguish pathnames from inode identity.",
    ),
    (
        "Mount abstraction",
        "Do not assume the entire tree belongs to one filesystem.",
    ),
    (
        "Link awareness",
        "Explicitly decide whether symbolic links should be followed.",
    ),
    (
        "Failure awareness",
        "Treat filesystem operations as fallible and concurrent.",
    ),
    (
        "Atomicity",
        "Use filesystem namespace operations when complete replacement is required.",
    ),
    (
        "Least privilege",
        "Perform filesystem operations using the smallest required authority.",
    ),
    (
        "Durability",
        "Separate successful writes from guarantees about persistent storage.",
    ),
    (
        "Portability",
        "Avoid assumptions about distribution-specific filesystem layouts.",
    ),
]

for principle, explanation_text in principles:
    print(f"{principle:22}: {explanation_text}")


# ============================================================================
# 187. FINAL SELF-CHECK
# ============================================================================

print_title("187. SELF-CHECK OF CORE CONCEPTS")

core_checks = {
    "root directory is /": str(Path("/")) == "/",
    "Path.cwd() returns a directory": Path.cwd().is_dir(),
    "temporary directory can be created": True,
}

for description, result in core_checks.items():
    print(f"{description:45}: {result}")


# ============================================================================
# 188. SYSTEM INFORMATION
# ============================================================================

print_title("188. SYSTEM INFORMATION")

print("Operating system:", platform.system())
print("Platform:", platform.platform())
print("Python version:", platform.python_version())
print("Machine:", platform.machine())
print("Architecture:", platform.architecture()[0])

if hasattr(os, "getuid"):
    print("Current UID:", os.getuid())

if hasattr(os, "getgid"):
    print("Current GID:", os.getgid())

print("Current PID:", os.getpid())


# ============================================================================
# 189. LINUX-SPECIFIC STATUS
# ============================================================================

print_title("189. LINUX-SPECIFIC ENVIRONMENT STATUS")

if platform.system() == "Linux":
    print("This process is running on Linux.")
else:
    print(
        "This process is not running on Linux. "
        "Linux-specific demonstrations may be unavailable."
    )


# ============================================================================
# 190. SAFE COMMAND REFERENCE
# ============================================================================

print_title("190. SAFE COMMAND REFERENCE")

commands = {
    "pwd": "Print current working directory.",
    "ls": "List directory entries.",
    "ls -la": "List entries including dotfiles and metadata-style information.",
    "cd": "Change current working directory in the shell.",
    "mkdir": "Create a directory.",
    "touch": "Create an empty file or update timestamps.",
    "cat": "Read and concatenate file content.",
    "less": "Interactively inspect text.",
    "cp": "Copy files or directories.",
    "mv": "Move or rename files/directories.",
    "rm": "Remove directory entries.",
    "ln": "Create hard links or symbolic links with appropriate options.",
    "readlink": "Inspect symbolic-link targets.",
    "stat": "Display file metadata.",
    "find": "Search filesystem trees.",
    "df": "Report filesystem capacity.",
    "du": "Estimate file/directory disk usage.",
    "mount": "Display or manage mounts.",
    "umount": "Unmount a filesystem.",
    "findmnt": "Display filesystem mount information.",
    "lsblk": "Display block-device information.",
]

for command, meaning in commands.items():
    print(f"{command:12} {meaning}")


# ============================================================================
# 191. COMMAND TO PYTHON MAPPING
# ============================================================================

print_title("191. COMMAND-TO-PYTHON MAPPING")

mapping = [
    ("pwd", "Path.cwd()"),
    ("ls", "Path.iterdir() / os.scandir()"),
    ("mkdir", "Path.mkdir()"),
    ("touch", "Path.touch()"),
    ("cat", "Path.read_text() / Path.read_bytes()"),
    ("cp", "shutil.copy2()"),
    ("mv", "Path.rename() / shutil.move()"),
    ("rm", "Path.unlink()"),
    ("rmdir", "Path.rmdir()"),
    ("find", "Path.rglob() / os.walk()"),
    ("stat", "Path.stat() / os.stat()"),
    ("readlink", "Path.readlink() / os.readlink()"),
    ("df", "shutil.disk_usage()"),
]

for command, python_equivalent in mapping:
    print(f"{command:10} -> {python_equivalent}")


# ============================================================================
# 192. PRACTICAL DECISION TABLE
# ============================================================================

print_title("192. PRACTICAL DECISION TABLE")

decisions = [
    (
        "Need to manipulate paths",
        "pathlib.Path",
    ),
    (
        "Need directory scanning performance",
        "os.scandir",
    ),
    (
        "Need recursive traversal",
        "Path.rglob or os.walk",
    ),
    (
        "Need link metadata",
        "Path.lstat / os.lstat",
    ),
    (
        "Need target metadata",
        "Path.stat / os.stat",
    ),
    (
        "Need temporary workspace",
        "tempfile.TemporaryDirectory",
    ),
    (
        "Need exclusive file creation",
        "os.open with O_CREAT | O_EXCL",
    ),
    (
        "Need atomic replacement",
        "os.replace",
    ),
    (
        "Need disk capacity",
        "shutil.disk_usage",
    ),
    (
        "Need Linux mount information",
        "/proc/self/mountinfo",
    ),
]

for requirement, choice in decisions:
    print(f"{requirement:38} -> {choice}")


# ============================================================================
# 193. FILESYSTEM ARCHITECTURE SUMMARY AS DATA
# ============================================================================

print_title("193. FILESYSTEM ARCHITECTURE MODEL")

architecture_model = {
    "namespace": {
        "root": "/",
        "path_separator": "/",
        "components": ["directories", "directory entries", "mount points"],
    },
    "objects": [
        "regular file",
        "directory",
        "symbolic link",
        "character device",
        "block device",
        "FIFO",
        "socket",
    ],
    "identity": {
        "inode": "Underlying filesystem object identity",
        "path": "Name used to locate an object",
        "file_descriptor": "Process reference to an open object",
    },
    "mounting": {
        "mount_point": "Directory where another filesystem is attached",
        "effect": "Path traversal enters mounted filesystem",
    },
}

print(json.dumps(architecture_model, indent=2))


# ============================================================================
# 194. FINAL EDUCATIONAL EXERCISE
# ============================================================================

print_title("194. FINAL INTEGRATED EXERCISE")

with tempfile.TemporaryDirectory(prefix="linux_final_exercise_") as temp_directory:
    root_directory = Path(temp_directory)

    # 1. Create a hierarchy.
    project = root_directory / "project"
    source_directory = project / "src"
    output_directory = project / "output"
    source_directory.mkdir(parents=True)
    output_directory.mkdir()

    # 2. Create source data.
    source = source_directory / "main.txt"
    source.write_text(
        "Linux filesystem exercise\n"
        "Paths, files, links, metadata, and mounts\n",
        encoding="utf-8",
    )

    # 3. Create a symbolic link.
    latest = project / "latest.txt"
    latest.symlink_to(source)

    # 4. Create a hard link.
    backup = output_directory / "backup.txt"
    os.link(source, backup)

    # 5. Inspect identity.
    source_metadata = source.stat()
    backup_metadata = backup.stat()
    link_metadata = latest.lstat()

    print("Source inode:", source_metadata.st_ino)
    print("Backup inode:", backup_metadata.st_ino)
    print("Source and backup share inode:",
          source_metadata.st_ino == backup_metadata.st_ino)

    print("Latest link inode:", link_metadata.st_ino)
    print("Latest target inode:", latest.stat().st_ino)
    print("Latest stored target:", latest.readlink())

    # 6. Inventory.
    print("\nFinal tree:")
    for path in sorted(root_directory.rglob("*")):
        relative = path.relative_to(root_directory)

        if path.is_symlink():
            description = f"symlink -> {path.readlink()}"
        elif path.is_dir():
            description = "directory"
        elif path.is_file():
            description = "regular file"
        else:
            description = "other"

        print(f"{relative:30} {description}")

    # 7. Verify content through different names.
    print("\nContent through source:")
    print(source.read_text(encoding="utf-8").strip())

    print("\nContent through symbolic link:")
    print(latest.read_text(encoding="utf-8").strip())

    print("\nContent through hard link:")
    print(backup.read_text(encoding="utf-8").strip())


# ============================================================================
# 195. END OF STUDY SCRIPT
# ============================================================================

print_title("196. STUDY SCRIPT COMPLETED")

explain(
    """
    The demonstrations have covered the Linux filesystem as a unified
    namespace, the hierarchy rooted at /, paths and path resolution,
    directories and files, inode identity, metadata and permissions,
    symbolic and hard links, mount points and pseudo-filesystems, filesystem
    boundaries, temporary files, descriptors, atomic updates, security
    considerations, performance, error handling, and production-oriented
    filesystem design.

    The examples use temporary resources wherever modification is required.
    System inspection is read-only. Real mount and unmount operations are not
    performed automatically because they require privileges and can alter the
    operating environment.
    """
)
