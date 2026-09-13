# Linux file system

## Introduction

The Linux file system is the unified namespace through which Linux exposes files, directories, devices, process information, kernel interfaces, temporary state, and mounted filesystems.

The namespace begins at the root directory, represented by `/`. Unlike a simple view of one disk containing folders, the Linux filesystem hierarchy can combine many independent filesystems into one directory tree. Mount points determine where additional filesystems become visible.

The Python study script demonstrates these concepts using the standard library. Temporary directories are used for operations that create, modify, link, or delete filesystem objects, while system-level locations such as `/proc`, `/sys`, `/dev`, `/etc`, and `/var/log` are inspected without intentionally modifying them.

## Filesystem terminology

A **filesystem** is the structure and set of rules used to store and retrieve data. Linux supports many filesystem implementations, including ext4, XFS, Btrfs, tmpfs, procfs, sysfs, overlayfs, and network filesystems.

A **filesystem hierarchy** is the tree-shaped namespace visible to processes.

A **path** identifies a location in that namespace.

A **directory** is a filesystem object containing names that refer to other filesystem objects.

A **directory entry** associates a name in a directory with an underlying filesystem object.

An **inode** represents filesystem object metadata and references to stored data. The exact internal structure depends on the filesystem implementation.

A **symbolic link** is a special filesystem object containing a pathname that refers to another object.

A **hard link** is another directory entry referring to the same underlying inode.

A **mount point** is a directory at which another filesystem is attached to the namespace.

A **pseudo-filesystem** is a kernel-provided filesystem that exposes system or runtime information rather than ordinary persistent application files. `/proc` and `/sys` are important examples.

## The Linux filesystem hierarchy

The root directory `/` is the top of the entire namespace.

Common directories include:

| Directory | Typical purpose |
|---|---|
| `/` | Root of the filesystem namespace |
| `/bin` | Essential user command binaries on applicable layouts |
| `/boot` | Boot-related files such as kernels and bootloader data |
| `/dev` | Device nodes and device-related interfaces |
| `/etc` | System-wide configuration |
| `/home` | Home directories for ordinary users |
| `/lib` | Essential libraries and related system components |
| `/media` | Common location for removable media |
| `/mnt` | Traditional location for temporary or manual mounts |
| `/opt` | Optional application software |
| `/proc` | Process and kernel information |
| `/root` | Root user's home directory |
| `/run` | Volatile runtime state |
| `/sbin` | System administration binaries on applicable layouts |
| `/srv` | Data intended to be served by system services |
| `/sys` | Kernel device and subsystem information |
| `/tmp` | Temporary files |
| `/usr` | Most userland programs, libraries, documentation, and shared data |
| `/var` | Variable application and system data |

The exact physical arrangement varies between distributions. Modern Linux systems can use merged-`usr` layouts in which paths such as `/bin`, `/sbin`, and `/lib` are symbolic links into `/usr`.

Applications should therefore avoid unnecessary assumptions about the physical organization of these directories.

## The root directory

The root directory is written as `/`.

It is not the same concept as the root user's home directory, which is conventionally `/root`.

An absolute path such as `/etc/hosts` starts at the root directory. A relative path such as `documents/report.txt` begins from a contextual base, normally the process's current working directory.

## Current working directory

A process has a current working directory. Python exposes it through `Path.cwd()` and `os.getcwd()`.

The current working directory is process state. It is not necessarily the directory containing the Python source file.

This distinction matters when software is launched:

- from another directory
- by a service manager
- by a scheduler
- from an IDE
- by another application
- inside a container

Programs that depend on a specific directory should establish that directory explicitly rather than assuming the current working directory.

## Absolute paths and relative paths

An absolute path begins with `/`.

Examples include:

- `/etc/hosts`
- `/var/log`
- `/home/student/data.csv`

A relative path does not begin with `/`.

Examples include:

- `data.csv`
- `reports/annual.txt`
- `../shared/config.json`

`pathlib.Path` is generally preferable to manual string concatenation because it provides clear path operations and handles platform-specific path syntax appropriately.

## Path components

A path such as:

`/home/student/projects/report.txt`

contains several components:

- `/` is the root
- `home` is a directory component
- `student` is another directory component
- `projects` is another directory component
- `report.txt` is the final component

Python's `Path` object exposes useful attributes such as:

- `name`
- `stem`
- `suffix`
- `parent`
- `parents`
- `parts`
- `anchor`

These attributes describe the path lexically and do not automatically mean that every referenced filesystem object exists.

## The special components `.` and `..`

The component `.` represents the current directory.

The component `..` represents the parent directory.

For example:

`reports/../data/file.txt`

contains a parent-directory traversal.

Path normalization and filesystem resolution are different concepts. Pure normalization can remove syntactic components, while resolution can also involve symbolic links and actual filesystem state.

Python's `Path.resolve()` performs filesystem-aware resolution.

## Files

A regular file is a sequence of bytes. Linux does not require those bytes to represent text.

Regular files can contain:

- text
- images
- executable programs
- databases
- compressed data
- archives
- serialized objects
- arbitrary binary information

Python provides both text and binary interfaces.

Text operations should specify an encoding when the encoding is known. UTF-8 is a common choice for modern text files.

Binary operations use bytes directly and do not apply character decoding.

## Directories

Directories organize names in the filesystem namespace.

Python can inspect a directory with:

- `Path.iterdir()`
- `os.scandir()`
- `os.walk()`
- `Path.rglob()`

A directory's own `st_size` is not the recursive sum of the sizes of everything underneath it. Directory storage contains information used to represent directory entries.

## Recursive traversal

`Path.rglob("*")` provides convenient recursive traversal.

`os.walk()` provides a traditional directory-tree traversal interface.

`os.scandir()` can be more efficient for large directory-processing tasks because directory entries can provide metadata information without requiring a separate stat operation for every attribute in every situation.

Recursive traversal must be designed carefully when symbolic links are involved. Following arbitrary links can cause cycles, unexpected traversal outside an intended tree, or excessive work.

## Symbolic links

A symbolic link is a filesystem object that stores a pathname pointing to another object.

For example, a symbolic link can point from:

`/home/student/latest.log`

to:

`/var/log/application.log`

The link and target are separate filesystem objects.

Operations such as `stat()` normally follow symbolic links, while `lstat()` reports metadata for the link itself.

Python's `Path.is_symlink()` can determine whether a path is a symbolic link.

`Path.readlink()` retrieves the target stored by the link.

## Absolute symbolic links

An absolute symbolic link stores an absolute pathname.

An absolute link can continue to refer to the same absolute location even when the directory containing the link is moved.

This is useful for fixed system locations but can reduce portability.

## Relative symbolic links

A relative symbolic link stores a relative pathname.

The relative target is interpreted relative to the directory containing the symbolic link.

This makes relative links useful for relocatable directory trees.

For example, if:

`project/links/report`

points to:

`../data/report.txt`

the link can remain valid when the entire `project` directory is moved.

## Dangling symbolic links

A symbolic link can exist even when its target does not.

Such a link is called a dangling or broken symbolic link.

This creates an important distinction:

- `os.path.lexists()` can identify the link entry
- `os.path.exists()` follows the link and can return `False`

Similarly, `Path.is_symlink()` can still report that the object is a symbolic link even when its target is missing.

## Hard links

A hard link is another directory entry referring to the same inode.

If:

`original.txt`

and:

`second-name.txt`

are hard links, both names refer to the same underlying filesystem object.

Changing the contents through one name changes what is visible through the other.

The inode's link count records the number of directory entries referring to it.

Removing one hard link does not necessarily remove the underlying data. The inode and its data remain available through other hard links. The object is normally reclaimed only after the final directory reference has disappeared and no process still has it open.

## Hard links versus symbolic links

| Property | Symbolic link | Hard link |
|---|---|---|
| Underlying object | Separate link object | Same inode |
| Stores | Pathname | Reference to same inode |
| Can cross filesystem boundaries | Yes | Normally no |
| Can become dangling | Yes | No in the pathname-reference sense |
| Target rename behavior | Can break | Still refers to inode |
| Has its own inode | Yes | No separate inode for the linked object |

Hard links generally cannot cross filesystem boundaries because an inode belongs to a particular filesystem.

Symbolic links can cross filesystem boundaries because they store pathnames.

## Inodes

An inode commonly contains information such as:

- file type
- permissions
- ownership identifiers
- timestamps
- size
- link count
- references to stored data

The exact implementation is filesystem-specific.

An inode is not the same thing as a pathname.

A pathname is a name used during path lookup.

A directory entry connects a name to an inode.

This distinction explains why multiple hard-link names can refer to one inode.

## Pathname, inode, and file descriptor

These three concepts should be kept separate.

### Pathname

A pathname is used to locate an object.

### Inode

An inode represents the underlying filesystem object and its metadata.

### File descriptor

A file descriptor is a process-specific integer referring to an open kernel-managed resource.

The relationships can be visualized conceptually as:

`pathname -> directory entry -> inode`

and:

`process -> file descriptor -> open file description -> filesystem object`

Multiple pathnames can refer to the same inode through hard links.

Multiple file descriptors can refer to the same open file state.

## `stat()` and `lstat()`

`os.stat()` follows symbolic links.

`os.lstat()` reports metadata about the symbolic link itself.

Suppose:

`link -> target`

Then:

- `os.stat(link)` describes `target`
- `os.lstat(link)` describes `link`

This distinction is fundamental when writing filesystem inventory, backup, security, and cleanup programs.

## File metadata

Python's `Path.stat()` and `os.stat()` expose metadata including:

- `st_mode`
- `st_ino`
- `st_dev`
- `st_nlink`
- `st_uid`
- `st_gid`
- `st_size`
- `st_atime`
- `st_mtime`
- `st_ctime`

`st_mode` contains both file-type information and permission bits.

`st_ino` represents the inode number where the platform exposes one.

`st_dev` identifies the device or filesystem context associated with the object.

`st_nlink` is the link count.

`st_uid` and `st_gid` represent numeric ownership identifiers.

`st_size` is the logical file size.

## File types

Linux supports several filesystem object types.

Important categories include:

- regular files
- directories
- symbolic links
- character devices
- block devices
- FIFOs
- sockets

Python's `stat` module provides predicates such as:

- `stat.S_ISREG`
- `stat.S_ISDIR`
- `stat.S_ISLNK`
- `stat.S_ISCHR`
- `stat.S_ISBLK`
- `stat.S_ISFIFO`
- `stat.S_ISSOCK`

Using `lstat()` is important when the distinction between a symbolic link and its target matters.

## File timestamps

Linux exposes several timestamps through the standard stat interface.

`st_mtime` represents modification time.

`st_atime` represents access time.

`st_ctime` on Linux normally represents inode metadata change time. It should not be interpreted as a portable file-creation timestamp.

Filesystem-specific creation or birth timestamps may exist, but their availability and Python-level representation are not universally consistent.

## Unix permissions

Traditional Unix permissions divide access into:

- owner
- group
- others

Each category can have:

- read
- write
- execute

A common representation is octal notation.

For example:

`0640`

means, conceptually:

- owner: read and write
- group: read
- others: no permissions

For a regular file:

- read allows reading
- write allows modification
- execute allows execution when other conditions permit

Directory permissions have different semantics.

For directories:

- read generally permits listing directory names
- write generally permits creating or removing entries
- execute permits traversal and lookup through the directory

The combination of these permissions determines practical access.

## Ownership

Files have numeric user and group ownership identifiers.

Python exposes them through `st_uid` and `st_gid`.

Converting numeric IDs into usernames or group names involves the operating system's identity databases and configuration.

Changing ownership generally requires appropriate privileges and should not be performed casually.

## `chmod`

Python's `Path.chmod()` can change permission bits.

For example, a mode such as:

`0o640`

sets owner read/write permissions, group read permission, and no permissions for others.

Programs should not assume that the requested mode will always be the final mode because creation-time permission behavior is also affected by the process umask.

## Umask

The umask is a process-level permission mask.

It removes selected permission bits from requested creation modes.

A program might request a mode such as `0666`, but the resulting file permissions can be more restrictive because of the process's umask.

Umask is therefore not itself a permission setting. It modifies the permissions requested during object creation.

## Special permission bits

Unix also supports special permission bits:

- setuid
- setgid
- sticky bit

The setuid and setgid mechanisms can affect process identity when executing programs under appropriate conditions.

The sticky bit is particularly important for shared directories. It can restrict which users may remove or rename entries within the directory.

These mechanisms have significant security implications.

## The `/tmp` directory

`/tmp` is conventionally used for temporary files.

Temporary resources should preferably be created using Python's `tempfile` module rather than manually constructing predictable filenames.

`tempfile.TemporaryDirectory()` provides automatic cleanup.

This avoids common problems involving filename collisions, stale temporary data, and insecure predictable names.

## File descriptors

A file descriptor is a small integer used by a process to refer to an open kernel resource.

The conventional standard descriptors are:

- `0` for standard input
- `1` for standard output
- `2` for standard error

When Python opens a file, the resulting file object ultimately uses a file descriptor.

A pathname identifies an object through path lookup. A file descriptor refers to an already-open resource.

## Unlinking an open file

On typical Unix systems, `unlink()` removes a directory entry.

If a process already has the file open, it can continue accessing the object through its file descriptor even though the pathname is no longer visible.

This explains a common Unix temporary-file technique:

1. Create a file.
2. Open it.
3. Remove its directory entry.
4. Continue using the open descriptor.
5. Allow the data to disappear automatically when the final reference closes.

The exact behavior of removing open files can differ on non-Unix systems.

## Rename and atomic replacement

Renaming is a fundamental filesystem operation.

Python provides `Path.rename()` and `os.replace()`.

A useful configuration-update pattern is:

1. Write the new contents to a temporary file.
2. Flush the application buffer.
3. Synchronize the file when durability matters.
4. Atomically replace the old directory entry.

`os.replace()` is particularly useful when complete replacement is desired.

Atomic namespace replacement does not automatically guarantee persistence after a power failure. Strict durability requirements can also require `fsync()` and consideration of the containing directory.

## `fsync`

`flush()` transfers buffered Python data toward the operating system.

`os.fsync()` requests synchronization of the file descriptor's state with storage as appropriate.

These are different operations.

A useful conceptual model is:

`Python buffer -> flush -> kernel -> fsync -> storage synchronization`

The actual storage stack may contain additional caching layers.

## Sparse files

A sparse file can have a large logical size while consuming substantially less physical storage.

Seeking forward and writing a small amount of data can create a sparse region.

This demonstrates why:

- logical file size
- allocated storage
- filesystem capacity

are separate concepts.

## Filesystem capacity

`shutil.disk_usage()` provides filesystem capacity information.

The three common values are:

- total
- used
- free

Filesystem capacity is different from the size of an individual file.

A file's `st_size` describes its logical size. Filesystem capacity describes storage available within the filesystem containing that file.

## `df` versus `du`

These commands answer different questions.

`df` reports filesystem-level capacity and usage.

`du` estimates usage associated with files and directories in a tree.

A directory tree can contain mount points, so `du` and `df` can appear to describe different storage layers.

## `/proc`

`/proc` is a virtual procfs filesystem.

It exposes information about:

- processes
- CPU state
- memory
- mounts
- kernel information
- runtime process state

`/proc/self` refers to the current process.

This makes `/proc/self` useful for process-specific inspection.

The contents of `/proc` are not ordinary persistent disk files even though they are accessed through ordinary paths.

## `/sys`

`/sys` is associated with sysfs.

It exposes information about:

- devices
- drivers
- kernel subsystems
- device relationships
- system configuration interfaces

It is a kernel interface rather than a conventional application data directory.

## `/dev`

`/dev` contains device nodes and related interfaces.

Important examples include:

- `/dev/null`
- `/dev/zero`
- `/dev/random`
- `/dev/urandom`
- `/dev/tty`

Device nodes can represent character or block devices.

The Linux filesystem namespace therefore includes interfaces to devices, not just persistent documents.

## Pseudo-filesystems

Common Linux pseudo-filesystems include:

| Filesystem | Typical location | Purpose |
|---|---|---|
| procfs | `/proc` | Processes and kernel information |
| sysfs | `/sys` | Devices and kernel subsystems |
| devtmpfs | `/dev` | Device nodes |
| tmpfs | `/run`, other locations | Volatile memory-backed storage |
| devpts | `/dev/pts` | Pseudo-terminals |
| cgroup2 | `/sys/fs/cgroup` | Control groups |
| overlayfs | Container environments | Layered filesystem views |

These filesystems can behave differently from ordinary persistent disk filesystems.

## Mounts

A Linux system can expose many physical or logical filesystems through one namespace.

For example:

`/`

can contain:

- `/home`
- `/var`
- `/boot`
- `/data`

where each directory may be a mount point for a separate filesystem.

The application still accesses all of them using ordinary paths.

## Mount point

A mount point is a directory at which another filesystem is attached.

Before a mount, a directory may contain ordinary files belonging to the parent filesystem.

After a filesystem is mounted there, path traversal through that directory enters the mounted filesystem.

The underlying directory contents become hidden from normal path traversal while the mount is active.

When the filesystem is unmounted, the underlying directory becomes visible again.

## Mount information

Linux exposes detailed information about the current process's mounts through:

`/proc/self/mountinfo`

The study script parses selected fields including:

- mount ID
- parent mount ID
- device identifier
- root
- mount point
- mount options
- filesystem type
- source
- superblock options

Mount information is process- and namespace-sensitive.

## Mount options

Common mount options include:

| Option | Meaning |
|---|---|
| `ro` | Read-only |
| `rw` | Read-write |
| `nosuid` | Ignore setuid/setgid effects |
| `nodev` | Do not interpret device nodes |
| `noexec` | Restrict execution from the mount where applicable |
| `relatime` | Reduce frequency of access-time updates |
| `bind` | Make an existing directory available at another path |
| `remount` | Change options of an existing mount where supported |

Mount operations can require elevated privileges and can affect system availability. The study script therefore does not automatically mount or unmount real filesystems.

## Bind mounts

A bind mount exposes an existing directory at another location.

Conceptually:

`/data/project`

and:

`/mnt/project`

can provide access to the same underlying directory tree through different paths.

Bind mounts are important in containers and service isolation.

## Mount namespaces

Linux mount namespaces allow different processes to have different views of the mount hierarchy.

A process in one mount namespace can see mounts that are hidden from another namespace.

This is an important component of container isolation.

A mount namespace does not necessarily duplicate storage. It provides a different view of how filesystems are attached to the namespace.

## Containers and filesystems

Containers commonly combine several filesystem technologies:

- image layers
- writable layers
- bind mounts
- volumes
- temporary filesystems
- pseudo-filesystems
- mount namespaces

Overlay filesystems can present several directory trees as one merged view.

A simplified conceptual structure is:

`lower layer -> base content`

`upper layer -> changes`

`merged view -> visible filesystem`

This is one reason container filesystem behavior can differ from a traditional single-filesystem installation.

## Filesystem types

Important Linux filesystem types include:

### ext4

A widely used general-purpose Linux filesystem.

### XFS

A high-performance journaling filesystem commonly used for large storage systems.

### Btrfs

A copy-on-write filesystem offering features such as snapshots and advanced storage management.

### tmpfs

A volatile filesystem backed primarily by memory and swap mechanisms.

### procfs

A virtual filesystem for process and kernel information.

### sysfs

A virtual filesystem for kernel device and subsystem information.

### overlayfs

A union-style filesystem useful for layered filesystem views.

### NFS

A network filesystem technology used to access remote storage.

The exact capabilities and semantics depend on the filesystem implementation and configuration.

## Filesystem boundaries

`st_dev` can help identify whether objects belong to different filesystem/device contexts.

Filesystem boundaries matter for operations such as hard linking and renaming.

A hard link generally cannot cross filesystem boundaries.

A rename generally cannot move an object across filesystems as one namespace operation. Such an attempt can produce `EXDEV`.

High-level tools such as `shutil.move()` can implement a cross-filesystem move using copying and deletion, but this is fundamentally different from an atomic rename.

## Symbolic links and filesystem boundaries

Symbolic links can refer to targets located on another filesystem.

The reason is that a symbolic link stores a pathname rather than directly identifying an inode.

The path can therefore resolve into another mounted filesystem.

## Path traversal security

Filesystem paths become security-sensitive when any part of the path is influenced by untrusted input.

A basic problem is path traversal through components such as:

`../`

A more subtle problem involves symbolic links.

A program might validate a path and then use it later. Another process can modify a symbolic link between validation and use.

This is a TOCTOU race:

**Time of check to time of use**

The path that was validated may not be the object that is eventually opened.

## Path validation

A common defensive technique is to resolve a candidate path and verify that it remains under an intended base directory.

The study script demonstrates this with `Path.resolve()` and `relative_to()`.

This is useful, but it should not be treated as a universal security solution.

High-security applications may require descriptor-relative operations, symbolic-link restrictions, or Linux-specific APIs such as `openat()` and `openat2()`.

## Descriptor-relative operations

Linux provides APIs that allow pathname resolution relative to an already-open directory descriptor.

Conceptually:

`directory_fd = open("/safe")`

followed by:

`openat(directory_fd, "file.txt")`

reduces dependence on a process-wide current working directory and can make security boundaries more explicit.

Linux's `openat2()` provides additional path-resolution controls on supported systems.

## `O_CREAT` and `O_EXCL`

A common race-prone pattern is:

1. Check whether a file exists.
2. Create it if it does not.

Another process can act between these operations.

`O_CREAT | O_EXCL` provides an atomic exclusive-creation request.

If the target already exists, creation fails.

This makes it useful for:

- lock files
- unique temporary files
- one-time resource creation

## `O_NOFOLLOW`

Where supported, `O_NOFOLLOW` can prevent the final pathname component from being followed when it is a symbolic link.

This can be useful for security-sensitive file opening.

It is only one component of a broader secure path-resolution strategy.

## Common filesystem errors

Important error conditions include:

| Error | Meaning |
|---|---|
| `ENOENT` | No such file or directory |
| `EACCES` | Permission denied |
| `EEXIST` | File already exists |
| `ENOTDIR` | A path component expected to be a directory is not |
| `EISDIR` | An operation expected a non-directory found a directory |
| `ENOSPC` | No space left on device |
| `EROFS` | Read-only filesystem |
| `EXDEV` | Cross-device or cross-filesystem operation |
| `ENOTEMPTY` | Directory is not empty |
| `ELOOP` | Too many symbolic-link levels |

Filesystem code should handle errors explicitly rather than assuming that a path remains valid after it has been observed.

## EAFP and filesystem programming

Python commonly follows the EAFP principle:

**Easier to Ask Forgiveness than Permission**

Instead of:

1. checking whether a file exists
2. assuming the subsequent operation will succeed

a program can perform the operation and handle the exception.

For example, attempting to read a file and handling `FileNotFoundError` is generally more robust than assuming that an earlier `exists()` check guarantees the read.

Filesystem state can change concurrently.

## Race conditions

Filesystem operations are not automatically isolated from other processes.

This pattern can be unsafe:

`if path.exists():`

followed by:

`path.read_text()`

The path can be removed or replaced between the two operations.

Other race-sensitive patterns include:

- check permissions, then open
- check ownership, then write
- check whether a link points somewhere safe, then use it
- check whether a file exists, then create it

Atomic filesystem operations and descriptor-based APIs can reduce these risks.

## Atomic file updates

A reliable configuration update commonly uses:

1. a temporary file in the same directory
2. complete content writing
3. flushing
4. optional `fsync()`
5. `os.replace()`

Keeping the temporary file in the same directory is useful because atomic rename semantics are tied to the same filesystem.

For applications with strict crash-durability requirements, the containing directory may also need synchronization.

## File locking

Multiple processes may access the same filesystem objects simultaneously.

Coordination can use:

- advisory file locks
- lock files
- databases
- atomic creation
- transactional update patterns

Atomic exclusive creation can be used as a building block for simple lock-file schemes.

A filesystem does not automatically make arbitrary read-modify-write application workflows mutually exclusive.

## Temporary files

Temporary files should be created with mechanisms such as Python's `tempfile` module.

`TemporaryDirectory` is useful for:

- tests
- isolated experiments
- intermediate data
- temporary build output

Predictable temporary filenames can create security and collision problems.

## File names

Linux filenames can contain spaces and many characters that shells treat specially.

For example, the filesystem can contain names such as:

- `file with spaces.txt`
- `file'quote.txt`
- `file[brackets].txt`
- `unicode-फ़ाइल.txt`

Shell parsing and filesystem naming are different layers.

A filename containing spaces is not inherently problematic to the filesystem.

The NUL byte cannot be part of a normal Linux pathname.

## Hidden files

Linux does not require a special hidden-file object type.

A common convention is that filenames beginning with `.` are hidden by ordinary directory-listing tools.

Examples include:

- `.config`
- `.bashrc`
- `.profile`

The leading dot is a naming convention.

## Case sensitivity

Typical Linux filesystems are case-sensitive.

Therefore these names can coexist:

- `File.txt`
- `file.txt`

Applications should not assume case-insensitive behavior unless they explicitly target a filesystem with such semantics.

## `/etc`

`/etc` conventionally contains system-wide configuration.

Examples can include:

- `/etc/hosts`
- `/etc/passwd`
- `/etc/group`
- `/etc/fstab`
- `/etc/hostname`

The exact files vary between distributions.

## `/var`

`/var` contains variable system and application state.

Important areas include:

- `/var/log` for logs
- `/var/lib` for persistent application state
- `/var/cache` for regenerable cached data

## `/run`

`/run` generally contains volatile runtime state created during the current boot.

It can contain:

- process identifiers
- service state
- runtime sockets
- other temporary system state

It should not be treated as a general persistent data directory.

## `/home`

`/home` commonly contains the home directories of ordinary users.

A user can have a home such as:

`/home/student`

User-specific configuration and data can live below that directory.

## `/boot`

`/boot` contains boot-related files such as kernels and bootloader information on systems that use a separate or visible `/boot` hierarchy.

The exact layout depends on the system.

## `/media` and `/mnt`

`/media` is commonly associated with automatically managed removable media.

`/mnt` has traditionally been used for manually mounted or temporary filesystems.

Neither directory has an immutable universal purpose across every Linux environment.

## `PATH` environment variable

The environment variable `PATH` is different from the filesystem hierarchy.

`PATH` is a list of directories used when resolving executable command names.

For example, a shell can search:

`/usr/local/bin`

and:

`/usr/bin`

when the user enters a command such as `python`.

The filesystem path:

`/usr/bin/python`

is a specific namespace location.

The environment variable `PATH` is a search configuration.

## Performance considerations

Filesystem operations can be expensive, especially when they involve:

- large directory trees
- network filesystems
- repeated metadata requests
- storage with high latency
- unnecessary path resolution
- reading large files into memory

Useful practices include:

- using `os.scandir()` for efficient directory iteration
- streaming large files instead of reading them all at once
- avoiding unnecessary repeated `stat()` calls
- batching operations where possible
- avoiding uncontrolled recursive traversal
- considering filesystem-specific behavior

## Streaming files

For large files, reading line by line or in chunks avoids loading the entire file into memory.

A streaming pattern is especially useful for:

- log processing
- backups
- hashing
- data transformation
- large text files

The study script includes a chunked SHA-256 function to demonstrate this principle.

## File identity versus content identity

Two different files can contain identical bytes while having different inodes.

Conversely, two hard-link names can have different pathnames while referring to exactly the same inode.

Therefore:

**same content does not imply same filesystem object**

and:

**different pathname does not imply different filesystem object**

A cryptographic hash such as SHA-256 can compare content. Inode information can compare filesystem identity within the relevant filesystem context.

## Journaling

Journaling filesystems maintain additional information that assists recovery after certain failures.

Journaling helps preserve filesystem consistency, but it does not mean that every application write is immediately durable after a normal write call.

Application-level durability requirements may require explicit synchronization.

## Security model

Filesystem security can involve multiple layers:

- user ownership
- group ownership
- permission bits
- special permission bits
- ACLs
- mount options
- namespaces
- Linux capabilities
- SELinux
- AppArmor
- filesystem-specific security mechanisms

Traditional permission bits are only one part of the complete Linux security model.

## Least privilege

Filesystem programs should request only the privileges they actually require.

Operations that commonly require elevated privileges include:

- mounting filesystems
- unmounting filesystems
- changing ownership
- modifying protected system configuration
- accessing restricted device interfaces

Normal application processing should generally operate without unnecessary elevated privileges.

## Filesystem namespaces and `chroot`

`chroot` changes the apparent root directory for a process and its descendants.

It should not be treated as a complete security boundary.

Modern isolation mechanisms can combine:

- mount namespaces
- user namespaces
- process namespaces
- network namespaces
- capabilities
- filesystem restrictions
- security policies

Containers normally combine multiple mechanisms rather than depending on a single filesystem feature.

## Network filesystems

Network filesystems such as NFS expose remote storage through filesystem paths.

They can differ from local filesystems in:

- latency
- caching
- locking
- consistency
- availability
- failure behavior

Programs that perform many small filesystem operations can experience significant performance differences on network-mounted storage.

## Important limitations

Filesystem behavior is not completely uniform across all Linux environments.

Important variations include:

- filesystem type
- kernel version
- distribution
- mount options
- security policy
- namespace configuration
- network filesystem implementation
- storage hardware
- container environment

Software should therefore avoid relying on undocumented filesystem behavior.

## Common mistakes

### Assuming `/` represents one physical disk

The Linux namespace can combine many filesystems through mounts.

### Treating `st_ctime` as creation time

On Linux, it normally represents inode metadata change time.

### Treating a symbolic link as its target

Use `lstat()` when the link itself matters.

### Assuming `exists()` prevents races

Filesystem state can change immediately after the check.

### Following all symbolic links during recursive traversal

This can produce cycles or unexpected access outside the intended tree.

### Building paths through string concatenation

Use `pathlib` or `os.path`.

### Assuming file size equals disk consumption

Sparse files and filesystem allocation behavior make this distinction important.

### Assuming every filesystem is writable

A filesystem may be mounted read-only or may reject a particular operation.

### Assuming a directory is always on the same filesystem

Mount points can change the filesystem encountered during traversal.

### Performing system-wide modifications without privilege analysis

Changes to mounts, ownership, permissions, devices, and protected configuration can affect the entire system.

## Production filesystem design

A production application should define:

- its intended data directory
- its configuration directory
- its temporary storage location
- its logging location
- its cleanup policy
- whether symbolic links are permitted
- whether cross-filesystem access is permitted
- its durability requirements
- its privilege requirements
- its expected filesystem types
- its behavior when storage becomes unavailable
- its behavior when storage becomes full

Security-sensitive applications should also define their path-resolution policy and determine whether descriptor-relative operations are required.

## Practical Python interfaces

| Requirement | Python interface |
|---|---|
| Path manipulation | `pathlib.Path` |
| Current directory | `Path.cwd()` |
| Home directory | `Path.home()` |
| Directory listing | `Path.iterdir()` |
| Efficient directory scanning | `os.scandir()` |
| Recursive traversal | `Path.rglob()` / `os.walk()` |
| Create directory | `Path.mkdir()` |
| Read text | `Path.read_text()` |
| Read bytes | `Path.read_bytes()` |
| Write text | `Path.write_text()` |
| Write bytes | `Path.write_bytes()` |
| Metadata | `Path.stat()` |
| Link metadata | `Path.lstat()` |
| Read symbolic-link target | `Path.readlink()` |
| Create symbolic link | `Path.symlink_to()` |
| Create hard link | `os.link()` |
| Remove file/link | `Path.unlink()` |
| Rename | `Path.rename()` |
| Atomic replacement | `os.replace()` |
| Disk usage | `shutil.disk_usage()` |
| Temporary directory | `tempfile.TemporaryDirectory()` |
| Low-level open | `os.open()` |
| Synchronize file | `os.fsync()` |

## Command-line concepts

Linux administrators commonly use commands such as:

| Command | Purpose |
|---|---|
| `pwd` | Display current working directory |
| `ls` | List directory entries |
| `ls -la` | List entries including dotfiles |
| `cd` | Change shell working directory |
| `mkdir` | Create directories |
| `touch` | Create files or update timestamps |
| `cat` | Display file content |
| `cp` | Copy files |
| `mv` | Move or rename files |
| `rm` | Remove directory entries |
| `ln` | Create links |
| `readlink` | Inspect symbolic links |
| `stat` | Display metadata |
| `find` | Search directory trees |
| `df` | Display filesystem capacity |
| `du` | Estimate directory usage |
| `mount` | Display or manage mounts |
| `umount` | Unmount filesystems |
| `findmnt` | Display mount information |
| `lsblk` | Display block-device information |

Equivalent Python interfaces are useful when filesystem operations need to be integrated directly into application logic without launching shell commands.

## Mount inspection

The study script uses `/proc/self/mountinfo` to inspect the mount hierarchy visible to the current process.

This demonstrates an important Linux principle: the filesystem hierarchy visible to a process is a namespace abstraction.

A mount is not merely a physical storage device. It is a relationship between a filesystem and a location in a namespace.

## Filesystem object model

The main relationships can be represented conceptually as:

`pathname -> directory entry -> inode`

A symbolic link is a separate inode-like filesystem object containing a pathname.

A hard link is another directory entry pointing to an existing inode.

A mount connects another filesystem tree into the pathname namespace.

A file descriptor provides a process-level reference to an already-open resource.

These relationships explain many otherwise surprising Linux behaviors.

## Edge cases

Important filesystem edge cases include:

- dangling symbolic links
- symbolic-link loops
- missing intermediate directories
- paths containing spaces
- Unicode filenames
- filenames beginning with `.`
- empty files
- empty directories
- sparse files
- read-only filesystems
- filesystem-full conditions
- permission failures
- cross-filesystem rename attempts
- filesystem disappearance
- network filesystem failures
- concurrent modifications
- mounted directories
- special device files

A robust filesystem application should treat these as normal possibilities rather than exceptional impossibilities.

## Testing filesystem code

Filesystem code should be tested in isolated temporary directories.

`tempfile.TemporaryDirectory()` is useful because it provides:

- isolation
- automatic cleanup
- deterministic test structure
- reduced risk of modifying real system files

Tests should cover:

- missing paths
- empty files
- empty directories
- permissions
- symbolic links
- dangling links
- nested paths
- existing destinations
- concurrent-operation assumptions
- filesystem boundaries when relevant
- large files when performance matters

Testing only the happy path is insufficient for filesystem software.

## Integrated example

The study script creates a miniature application hierarchy containing conceptual equivalents of:

- configuration
- persistent application data
- logs
- user data

It then creates:

- regular files
- a symbolic link
- a hard link

The example verifies that the hard-link names share an inode while the symbolic link has its own filesystem object and points to the target through a pathname.

This demonstrates the difference between namespace identity and filesystem-object identity.

## Production considerations

Filesystem operations should be designed with several independent questions in mind.

**Where is the object?**

This is a path and namespace question.

**What object does the path identify?**

This involves directory entries, symbolic links, mounts, and inodes.

**Can the process access it?**

This involves permissions, ownership, ACLs, capabilities, and security policies.

**Can the object disappear or change?**

Yes. Other processes, mounts, removable storage, and network filesystems can change filesystem state.

**Does a successful write mean the data is durable?**

Not necessarily. Buffering, caching, filesystem behavior, and storage hardware all matter.

**Can the operation cross a filesystem boundary?**

Some operations can, while others cannot. Hard links and atomic rename operations generally have filesystem-boundary restrictions.

**Can an attacker influence the path?**

If yes, symbolic links, traversal, race conditions, mount namespaces, and descriptor-relative resolution must be considered.

## Core conceptual distinctions

The most important distinctions are:

| Distinction | Meaning |
|---|---|
| Root directory vs root user | `/` is the namespace root; `/root` is the root user's home |
| Absolute vs relative path | Absolute begins at `/`; relative depends on a base |
| Pathname vs inode | A pathname identifies; an inode represents the underlying object |
| Hard link vs symbolic link | Hard link shares an inode; symbolic link stores a pathname |
| `stat` vs `lstat` | `stat` follows links; `lstat` describes the link |
| File size vs disk usage | Logical size can differ from allocated storage |
| Filesystem hierarchy vs physical disk | One namespace can combine many filesystems |
| `flush` vs `fsync` | Buffer flushing differs from storage synchronization |
| `df` vs `du` | Filesystem capacity differs from directory-tree usage |
| File descriptor vs pathname | Descriptor references an open resource; pathname performs lookup |
| `chroot` vs mount namespace | They provide different forms of filesystem isolation |
| Persistent filesystem vs pseudo-filesystem | Persistent files store data; pseudo-filesystems expose kernel/runtime interfaces |

## Real-world relevance

Linux filesystem knowledge is fundamental to:

- system administration
- backend development
- DevOps
- cloud infrastructure
- containerization
- Kubernetes
- database deployment
- web servers
- logging systems
- backup systems
- security engineering
- storage engineering
- build systems
- CI/CD environments
- application deployment

Understanding the hierarchy alone is not enough. Reliable Linux software also requires knowledge of path resolution, permissions, links, mount boundaries, filesystem metadata, failure handling, atomicity, and security.
