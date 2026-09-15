# Linux users and permissions

## Topic introduction

Linux uses a layered security model in which users, groups, ownership, permission bits, ACLs, privilege mechanisms, and other kernel security controls determine whether an operation can be performed.

The traditional UNIX permission model is built around three permission classes:

- owner
- group
- others

Each class can receive three basic permissions:

- `r` for read
- `w` for write
- `x` for execute

For ordinary files, these permissions control reading data, modifying data, and executing a program. For directories, their meanings are different. Read permission permits directory listing, write permission permits modification of directory entries when the required traversal permissions are present, and execute permission means search or traversal permission.

The three implementations in this repository approach the subject from different directions. Python provides direct access to operating-system metadata and safe filesystem demonstrations. JavaScript provides an application-oriented permission engine and shows how operating-system authorization concepts can be represented in application code. C++ develops a larger permission-aware document service that models identity, resources, ACLs, privileged administration, authorization decisions, and auditing.

## Fundamental concepts

### Users

A Linux user account is represented by a numeric user ID, or UID. Usernames are human-readable names associated with those IDs.

A process operates with user identity information. Important identities include:

- real UID
- effective UID
- real GID
- effective GID
- supplementary group IDs

The effective identity is especially important when access decisions are evaluated.

UID `0` conventionally represents the root account. Root has extensive privileges, but modern Linux security is more complicated than simply treating root as unrestricted. Capabilities, namespaces, Linux Security Modules, mount options, containers, and other mechanisms can impose additional restrictions.

### Groups

Groups provide a mechanism for organizing users and granting shared access.

A user normally has a primary group and may have supplementary groups.

For example, a project directory may belong to group `developers`. Files can then be assigned to that group so authorized developers receive group permissions without granting the same permissions to every user on the system.

Group-based authorization is often preferable to repeatedly granting permissions to individual users.

### UID and GID

A UID identifies a user. A GID identifies a group.

Linux filesystem metadata normally records:

- owner UID
- owning group GID
- permission bits

Commands such as `id`, `groups`, `getent passwd`, `getent group`, `ls -l`, and `stat` are useful for examining this information.

### `/etc/passwd`

Traditional Linux systems commonly maintain local account information in `/etc/passwd`.

The database contains fields such as:

- username
- UID
- primary GID
- account information
- home directory
- login shell

Modern systems do not normally store user password hashes directly in `/etc/passwd`. Password-related information is generally protected separately, commonly through `/etc/shadow`.

Linux can also obtain account and group information from external identity systems through mechanisms such as NSS.

### `/etc/group`

`/etc/group` traditionally stores local group information.

A group record contains a group name, GID, and membership information.

The actual source of identity information on a production Linux system may be more complex because NSS can integrate local and external identity sources.

## Ownership

Every normal Linux filesystem object has an owning user and an owning group.

A file might conceptually have:

`owner = alice`

`group = developers`

`mode = 640`

The ownership information is separate from the permission bits.

Changing permissions with `chmod` does not change ownership.

Ownership is normally changed with tools such as `chown` and `chgrp`, subject to the caller's privileges and the operating system's security rules.

## The `rwx` model

The three ordinary permission bits are:

| Permission | File meaning | Directory meaning |
|---|---|---|
| `r` | Read contents | List directory entries |
| `w` | Modify contents | Create, remove, or rename entries subject to other restrictions |
| `x` | Execute program | Search/traverse directory |

The directory interpretation is one of the most important distinctions in Linux permissions.

A directory with read permission but without execute permission may allow its entries to be listed while preventing useful access to those entries through normal path traversal.

A directory with execute permission but without read permission can sometimes permit access to a known pathname while preventing ordinary directory listing.

## Numeric permissions

Linux permission bits are commonly represented with three octal digits.

Each digit is the sum of:

- read = `4`
- write = `2`
- execute = `1`

Therefore:

| Digit | Symbolic form |
|---:|---|
| `0` | `---` |
| `1` | `--x` |
| `2` | `-w-` |
| `3` | `-wx` |
| `4` | `r--` |
| `5` | `r-x` |
| `6` | `rw-` |
| `7` | `rwx` |

A mode such as `640` means:

- owner: `6` = `rw-`
- group: `4` = `r--`
- others: `0` = `---`

Therefore:

`640 = rw-r-----`

Common examples include:

| Mode | Meaning |
|---:|---|
| `600` | Owner read/write only |
| `640` | Owner read/write, group read |
| `644` | Owner read/write, everyone else read |
| `700` | Owner full access |
| `750` | Owner full access, group read/execute |
| `755` | Owner full access, everyone else read/execute |
| `770` | Owner and group full access |
| `777` | Everyone full access |

Using `777` indiscriminately is generally poor security practice because it grants write access to every user.

## Permission selection

The traditional permission decision can be understood as a class-selection process.

For a non-root user:

1. If the user's UID matches the file owner UID, owner permissions are selected.
2. Otherwise, if the user belongs to the owning group, group permissions are selected.
3. Otherwise, the others permissions are selected.

This is important because the permissions are not simply combined into one large union.

For example, suppose a file is:

`rw-r-----`

If its owner is Alice and Alice is also a member of the owning group, Alice is evaluated using the owner class, not by adding owner and group permissions together.

The Python implementation models this decision explicitly in `permission_class_for()` and `basic_permission_allowed()`.

The JavaScript implementation models the same principle with `selectTraditionalPermissionClass()` and `traditionalAccessDecision()`.

The C++ implementation places the decision in `evaluateAccess()`.

## Python implementation

The Python program is the most closely connected to the actual Linux environment.

It begins by examining process identity through functions such as:

`os.getuid()`

`os.getgid()`

`os.geteuid()`

`os.getegid()`

and:

`os.getgroups()`

It uses the standard-library `pwd` and `grp` modules to inspect user and group databases.

The program also demonstrates filesystem metadata using `pathlib`, `os`, and `stat`.

The `stat.filemode()` function converts a numeric filesystem mode into a representation similar to what appears in `ls -l`.

The script demonstrates:

- UID and GID inspection
- supplementary groups
- passwd and group databases
- numeric permission interpretation
- symbolic permission notation
- permission-class selection
- filesystem ownership
- filesystem mode bits
- file permissions
- directory permissions
- `chmod`
- `umask`
- setuid
- setgid
- sticky bit
- sudo inspection
- POSIX ACL inspection when `getfacl` is installed
- path-component debugging
- safe file creation
- permission-model testing
- security best practices

### Safe filesystem demonstrations

The Python program uses temporary directories for operations that modify permission bits.

This is an important design decision. Educational software should not silently change permissions on system files, alter user accounts, modify `/etc/sudoers`, or change ownership of arbitrary files.

The script changes modes on temporary files with operations such as:

`os.chmod(file_path, 0o640)`

This demonstrates the mechanism without modifying important system resources.

### `chmod`

`chmod` modifies permission bits.

The Python implementation demonstrates equivalent behavior with `os.chmod()`.

For example:

`os.chmod(file_path, 0o640)`

sets owner read/write, group read, and no ordinary permissions for others.

Ownership is a different concept and requires ownership-related operations such as `chown` or `chgrp`.

### Directory permissions

The Python implementation deliberately distinguishes file permissions from directory permissions.

This is essential because a directory's execute bit means search/traversal permission rather than executing the directory as a program.

The script also demonstrates why parent directories matter when diagnosing `Permission denied`.

### `umask`

`umask` controls which permission bits are removed when a new filesystem object is created.

A common conceptual calculation is:

`requested_mode & ~umask`

For example:

`0666 & ~0022 = 0644`

and:

`0777 & ~0022 = 0755`

The Python script demonstrates this calculation without changing the user's actual shell umask.

`umask` affects newly created objects. It does not retroactively modify existing files.

## JavaScript implementation

The JavaScript program takes an application-oriented approach.

JavaScript does not provide a portable API for reproducing Linux's complete kernel permission engine. The implementation therefore models the concepts explicitly.

The main classes are:

- `LinuxUser`
- `LinuxGroup`
- `LinuxFile`
- `AccessControlEntry`
- `ApplicationDocumentService`
- `PrivilegedOperationService`
- `AuditLogger`

### `LinuxUser`

`LinuxUser` stores:

- username
- UID
- primary GID
- supplementary groups

The `belongsToGroup()` method determines whether the user belongs to a particular group.

### `LinuxFile`

`LinuxFile` models:

- path
- owner UID
- group GID
- mode
- resource type
- ACL entries

The `ordinaryPermissions()` method converts the lower nine permission bits into owner, group, and other permission sets.

### Access decisions

`canAccess()` provides a unified interface for access decisions.

The demonstration recognizes a simplified root case, ACL entries, and traditional owner/group/other permissions.

This is intentionally a model rather than an assertion that application code can replace the Linux kernel's authorization mechanism.

### ACLs

Traditional permissions have only three ordinary classes.

ACLs allow more specific rules.

For example, a file with:

`600`

can conceptually grant a named auditor read permission without making the file readable by all users.

POSIX ACLs have additional semantics that are not fully reproduced by the simplified JavaScript model. In particular, the ACL mask is important when determining effective permissions.

The Python implementation is better suited to examining actual ACLs through `getfacl`, while the JavaScript implementation is useful for understanding how an application could represent ACL concepts.

## C++ case study

The C++ program models a multi-user engineering document service.

The scenario contains:

- engineers
- groups
- source files
- finance documents
- ACL entries
- privileged administration
- authorization decisions
- audit logging
- unit tests
- special permission bits
- umask calculations

The implementation is intentionally structured into components rather than placing all logic inside `main()`.

### Problem being modeled

A technical organization stores documents in a shared filesystem.

Different users need different access:

- the owner may modify a document
- members of the owning group may read or execute selected resources
- unrelated users should be denied
- auditors may receive narrowly scoped access through an ACL
- ownership changes should require administrative authority
- security-relevant operations should be logged

This resembles a simplified file service or enterprise document-management subsystem.

### `User`

The `User` structure contains:

- username
- UID
- primary GID
- supplementary GIDs

The `belongsToGroup()` function models group membership.

### `Group`

The `Group` structure contains:

- group name
- GID
- member UIDs

The `addMember()` function records membership.

### `FileResource`

`FileResource` represents a protected resource.

It contains:

- path
- owner UID
- group GID
- permission mode
- resource type
- ACL entries

The methods `ownerPermissions()`, `groupPermissions()`, and `otherPermissions()` decode the three traditional permission classes.

### Access-control algorithm

The central algorithm is `evaluateAccess()`.

The implementation follows this simplified sequence:

1. Check the root identity.
2. Check whether the user owns the resource.
3. Check for a matching named ACL entry.
4. Check owning-group membership.
5. Fall back to the others permission class.

The result is represented by `AccessDecision`.

An access decision contains:

- allowed or denied
- source of authorization
- explanation

Separating the decision from the caller makes the policy easier to test and audit.

### Document service

`DocumentService` represents an application layer that asks the authorization engine whether a user may perform an operation.

It records the decision in `AuditLogger`.

This separation matters in production systems because authentication, authorization, resource management, business logic, and auditing should not be tightly coupled into a single large function.

### Privileged administration

`PrivilegedAdministrationService` models a sensitive ownership-change operation.

The demonstration permits this operation only to the simplified root identity.

Actual Linux ownership operations are governed by kernel rules and relevant capabilities. A production implementation must not assume that UID 0 alone explains every access decision.

### Auditing

`AuditLogger` records:

- timestamp
- actor
- action
- resource
- result

Security-sensitive systems benefit from recording both successful and denied actions.

Audit records can help investigate:

- accidental access failures
- unauthorized attempts
- unexpected group membership
- administrative changes
- compromised accounts
- configuration errors

## Special permissions

Linux provides special permission bits in addition to the ordinary nine permission bits.

### setuid

The setuid bit has numeric value `4000`.

On appropriate executable files, it can cause the process to execute with the file owner's effective UID, subject to Linux security rules.

Setuid programs are security-sensitive because a vulnerability in a privileged executable can potentially produce privilege escalation.

The C++ case study represents a setuid-marked executable as:

`04755`

### setgid

The setgid bit has numeric value `2000`.

On executables it has historical privilege-related behavior. On directories, setgid is particularly useful for collaboration because newly created entries commonly inherit the directory's group.

A collaborative directory may therefore use a mode such as:

`2770`

### Sticky bit

The sticky bit has numeric value `1000`.

A classic example is a shared writable directory:

`1777`

The sticky bit restricts deletion and rename behavior so that users cannot freely remove or rename files belonging to other users.

## `sudo`

`sudo` is a controlled privilege-escalation mechanism.

Common commands include:

`sudo command`

`sudo -u username command`

`sudo -l`

`sudo -k`

`sudo -v`

The policy is commonly defined through `/etc/sudoers` and files under `/etc/sudoers.d/`.

The principle of least privilege should apply to sudo policy.

Granting unrestricted administrative execution when only one specific command is required increases the security impact of account compromise.

The Python program safely attempts `sudo -n -l` for inspection. It does not automatically modify sudo configuration.

## ACLs

POSIX ACLs extend the basic owner/group/other model.

A traditional mode such as:

`640`

provides one owner, one owning group, and one others class.

An ACL can provide additional named-user or named-group entries.

Typical ACL concepts include:

- owner entry
- named user entry
- owning group entry
- named group entry
- ACL mask
- other entry

The ACL mask is important because it limits effective permissions for relevant group and named entries.

The Python implementation can inspect actual ACLs when `getfacl` is available.

The JavaScript and C++ implementations model named ACL concepts to make the policy structure explicit.

## Authentication and authorization

These terms should not be confused.

Authentication answers:

"Who is this subject?"

Authorization answers:

"Is this subject allowed to perform this operation?"

Accounting or auditing records relevant activity.

Linux users and groups contribute to identity and authorization. An application may still need its own authorization rules.

For example, a web server process may have filesystem permission to read a document while the application must deny that document to a particular customer.

Filesystem authorization and application authorization are therefore separate layers.

## Linux security layers

Traditional filesystem permissions are only one part of Linux security.

Relevant layers include:

- owner/group/other permission bits
- POSIX ACLs
- sudo policy
- Linux capabilities
- namespaces
- mount options
- SELinux
- AppArmor
- seccomp
- container isolation
- application-level authorization

A process can therefore encounter `Permission denied` even when ordinary `ls -l` output appears permissive.

The reverse is also important: ordinary filesystem permissions may permit an operation while another security layer prevents it.

## Capabilities

Linux capabilities divide some traditionally privileged root powers into more specific privileges.

Examples include capabilities associated with operations such as:

- changing ownership
- binding to privileged network ports
- manipulating processes
- administering networking

Capabilities support more granular privilege models than treating every administrative action as equivalent to unrestricted root authority.

The implementations mention capabilities conceptually rather than attempting to reproduce kernel capability evaluation.

## Namespaces and containers

Linux namespaces isolate resource views.

Relevant namespaces include those for:

- users
- processes
- mounts
- networks
- IPC
- hostnames and related resources

Containers rely heavily on Linux isolation mechanisms.

UID `0` inside a container should not automatically be interpreted as unrestricted host root. User namespaces and container configuration affect the relationship between container identities and host identities.

## Parent directories and path traversal

A common cause of permission errors is a parent directory.

Consider:

`/srv/project/reports/annual.txt`

Access may depend on permissions on:

- `/srv`
- `/srv/project`
- `/srv/project/reports`
- `annual.txt`

The target file can have apparently permissive mode bits while a parent directory prevents traversal.

Useful debugging commands include:

`namei -l /path/to/file`

`ls -ld /path /path/to /path/to/file`

`stat /path/to/file`

`id username`

`groups username`

`getfacl /path/to/file`

The Python implementation provides a path-component inspection function for the same reason.

## Common permission mistakes

### Using `chmod 777` as a universal fix

This often hides the underlying problem while creating unnecessary write access.

A better approach is to identify the required actor and operation and grant the smallest required permission.

### Confusing permissions with ownership

`chmod` changes permission bits.

`chown` changes ownership.

`chgrp` changes the owning group.

These are separate operations.

### Forgetting directory execute permission

Directory execute means traversal/search.

A user may have read permission on a directory but still be unable to access an entry because the directory lacks search permission.

### Assuming group permissions are additive

The traditional model selects an applicable permission class rather than simply combining owner, group, and other permissions.

### Assuming sudo explains every access problem

`sudo` changes the identity or privilege context under which a command runs.

It does not replace application authorization, ACL analysis, LSM policy analysis, or other security mechanisms.

### Ignoring ACLs

A file can contain ACL entries that are not obvious from a basic interpretation of the ordinary mode bits.

When the ordinary mode does not explain an access decision, inspect ACLs.

### Ignoring parent directories

A protected file can still be inaccessible because the path cannot be traversed.

### Changing permissions after creation

Creating sensitive data with broad permissions and then tightening them can create an unnecessary exposure window.

The Python program demonstrates restrictive creation with mode `600`.

## `umask`

A process can have a umask that removes permission bits from requested creation modes.

A common conceptual example is:

`0666 & ~0022 = 0644`

For directories:

`0777 & ~0022 = 0755`

Other common masks include:

- `0027`
- `0077`

A restrictive umask is often appropriate for sensitive environments.

The exact defaults depend on the program and system configuration.

## Security considerations

### Least privilege

Grant only the access required for the task.

Avoid broad write permissions when read access is sufficient.

### Group design

Use meaningful groups such as:

- developers
- analysts
- finance
- operations

Group-based authorization can be easier to manage than granting individual users broad permissions.

### Sensitive files

Credentials, private keys, tokens, and confidential configuration should not normally be world-readable.

A mode such as `600` may be appropriate for files intended exclusively for their owner, subject to application requirements.

### Privileged programs

Setuid programs require careful security analysis.

A vulnerability in a privileged executable can have a much larger impact than the same vulnerability in an ordinary process.

### Symbolic links

Privileged programs must account for symbolic-link attacks and race conditions.

A program that checks permissions on one pathname and later opens that pathname may be vulnerable to time-of-check/time-of-use issues if the filesystem state can change between the two operations.

### Atomic operations

Security-sensitive programs should prefer atomic filesystem operations and appropriate file-descriptor-based APIs when possible.

### Defense in depth

Filesystem permissions should not be considered the complete security boundary for a production system.

Application authorization, process isolation, secrets management, auditing, network controls, and other security mechanisms may all be required.

## Performance considerations

Traditional owner/group/other permission selection is effectively constant-time because only a small fixed set of permission bits needs to be evaluated.

The simplified ACL implementations search ACL entries sequentially. If there are `A` entries, the straightforward search has O(A) time complexity.

The C++ case study uses a `std::map` for resource lookup. Resource lookup is O(log N), where `N` is the number of stored resources.

The JavaScript example uses `Map`, providing efficient key-based lookup suitable for the demonstration.

Production systems may use more specialized structures and kernel caches. Application developers should not assume that a teaching implementation has the same performance characteristics as the Linux kernel.

## Edge cases

Important edge cases include:

- UID `0`
- supplementary group membership
- owner and group membership at the same time
- directory execute permission
- files with no read permission but execute permission
- shared directories
- sticky directories
- setgid collaborative directories
- ACL entries
- ACL masks
- restrictive parent directories
- symbolic links
- race conditions
- capabilities
- SELinux or AppArmor restrictions
- container user namespaces
- mount options such as `noexec` and `nosuid`

These cases are why permission debugging should be based on the actual security model rather than simply changing a file to `777`.

## Important distinctions

| Concept | Purpose |
|---|---|
| UID | Identifies a user |
| GID | Identifies a group |
| Primary group | User's principal group identity |
| Supplementary groups | Additional group memberships |
| Ownership | Associates a resource with a user and group |
| `chmod` | Changes permission bits |
| `chown` | Changes ownership |
| `chgrp` | Changes group ownership |
| `umask` | Removes permissions from newly requested modes |
| ACL | Provides more detailed access rules |
| sudo | Controls selected privileged command execution |
| Authentication | Establishes identity |
| Authorization | Determines allowed operations |
| Auditing | Records relevant actions |
| Capability | Represents a narrower privileged operation |
| SELinux/AppArmor | Adds mandatory security policy |
| Namespace | Isolates resource views |

## Python, JavaScript, and C++ comparison

| Area | Python | JavaScript | C++ |
|---|---|---|---|
| OS metadata | Strong standard-library support on Linux | Limited portable OS access | Strong platform-specific support |
| Filesystem demonstration | Direct | Primarily modeled | Modeled for portability |
| Permission algorithm | Explicit educational model | Application-oriented model | System-oriented architecture |
| ACL demonstration | Can inspect actual ACL tools | Simplified representation | Simplified representation |
| Testing | Built-in assertions and explicit test functions | Runtime assertions | Explicit test suite |
| Systems programming | Useful scripting layer | Less suited to kernel-facing work | Strong |
| Application modeling | Strong | Strong | Strong |
| Performance control | High-level | JIT/runtime dependent | Fine-grained |
| Security architecture | Easy to prototype | Useful for services | Suitable for low-level systems |

Python is particularly useful for inspecting Linux environments and automating administrative analysis.

JavaScript is useful for demonstrating how permission concepts can be represented inside an application, such as a web service.

C++ is useful for modeling system-oriented architecture where explicit data structures, algorithms, resource management, and performance characteristics matter.

## Implementation design principles

The three implementations deliberately separate:

- identity
- group membership
- resource metadata
- permission decoding
- access evaluation
- application authorization
- privileged operations
- auditing
- testing

This separation makes the security model easier to reason about.

The central design principle is that authorization should be explicit rather than scattered across unrelated operations.

A production authorization function should be deterministic, testable, auditable, and based on clearly defined policy.

## C++ case-study architecture

The C++ implementation uses these primary components:

`User`

Represents identity and group membership.

`Group`

Represents a group and its members.

`PermissionSet`

Represents the three ordinary permission bits.

`AclEntry`

Represents a simplified named ACL rule.

`FileResource`

Represents ownership, permissions, resource type, and ACL information.

`evaluateAccess()`

Centralizes the authorization algorithm.

`DocumentRepository`

Provides resource lookup.

`DocumentService`

Performs application-level access checks and produces audit events.

`PrivilegedAdministrationService`

Represents security-sensitive administrative actions.

`AuditLogger`

Records security decisions.

This structure demonstrates why security logic should be centralized rather than duplicated throughout an application.

## Testing

The Python implementation tests the simplified permission engine using multiple users and permission requests.

The JavaScript implementation tests:

- owner read access
- owner write access
- owner execute denial
- group read access
- group write denial
- outsider denial

The C++ implementation performs equivalent tests and reports the number of successful cases.

Testing permission systems should cover both positive and negative cases. A security test suite that checks only authorized behavior is incomplete.

## Practical Linux debugging workflow

When a user receives `Permission denied`, a useful investigation sequence is:

1. Identify the process user with `id` or `whoami`.
2. Inspect group membership with `groups` or `id`.
3. Inspect the resource with `ls -l` and `stat`.
4. Inspect every parent directory.
5. Use `namei -l` for path-component analysis.
6. Check ACLs with `getfacl`.
7. Check whether sudo or another privilege transition is involved.
8. Consider capabilities.
9. Consider SELinux or AppArmor.
10. Consider namespaces and containers.
11. Consider mount options.
12. Check application-level authorization if the operation is performed by a service.

This method is safer than immediately applying broad permissions.

## Real-world applications

Linux user and permission concepts are fundamental in:

- web servers
- database servers
- cloud infrastructure
- container platforms
- CI/CD systems
- enterprise Linux environments
- shared research systems
- development servers
- file servers
- application deployment
- security monitoring
- DevOps automation
- system administration
- multi-tenant services

A web application may run under a dedicated service account. A deployment directory may be owned by a deployment group. Configuration files may be readable only by the service account. Shared project directories may use setgid to preserve group ownership. Temporary shared directories may use the sticky bit.

These patterns demonstrate how simple permission primitives can become part of larger production security architectures.

## Limitations of the implementations

The Python program interacts with the host operating system but intentionally avoids modifying system accounts, ownership, sudo policy, and sensitive system configuration.

The JavaScript program is an educational permission engine rather than a replacement for the Linux kernel.

The C++ program models Linux authorization concepts rather than making direct system calls to implement an operating-system security policy.

The simplified ACL models do not reproduce every POSIX ACL rule. Real ACL evaluation includes concepts such as the ACL mask.

The simplified root model does not reproduce all Linux exceptions.

None of the three programs attempts to reproduce SELinux, AppArmor, Linux capabilities, namespaces, or the complete kernel VFS permission implementation.

These limitations are deliberate because a clear model is useful for learning the architecture before dealing with the full complexity of the Linux security stack.

## Core command reference

| Command | Purpose |
|---|---|
| `id` | Display UID, GID, and group information |
| `whoami` | Display the effective username |
| `groups` | Display group membership |
| `getent passwd` | Query the passwd identity database |
| `getent group` | Query the group database |
| `ls -l` | Display ownership and ordinary permission bits |
| `stat file` | Display detailed filesystem metadata |
| `chmod 640 file` | Set ordinary permission bits |
| `chown user file` | Change file ownership when authorized |
| `chgrp group file` | Change group ownership when authorized |
| `umask` | Display the current process umask |
| `namei -l path` | Inspect path-component permissions |
| `getfacl file` | Display POSIX ACL information |
| `setfacl` | Modify POSIX ACL information |
| `sudo -l` | Display sudo authorization information |

## Best practices

Use restrictive permissions by default and grant additional access only when required.

Use groups for structured collaboration.

Keep service accounts separate from ordinary human accounts.

Protect sensitive configuration and credential files.

Avoid unnecessary world-writable directories and files.

Audit privileged operations.

Inspect ACLs when standard permission bits do not explain access.

Treat setuid and setgid executables as security-sensitive.

Do not use filesystem permissions as a substitute for application authorization.

Do not assume root is the only relevant security boundary on modern Linux.

When debugging access failures, inspect the complete path and all applicable security layers.

Keep permission policy explicit, testable, and centralized in application code.

Avoid race-prone security checks in privileged programs.

Use least privilege as the governing design principle for users, groups, services, and administrative operations.
