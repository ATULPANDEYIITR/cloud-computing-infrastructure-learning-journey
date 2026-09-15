"use strict";

/*
 * Linux Users and Permissions
 * JavaScript companion implementation
 *
 * This file models the core UNIX permission decision process and demonstrates
 * how an application can reason about users, groups, ownership, permissions,
 * ACL-like rules, privileged operations, and audit events.
 *
 * It is intentionally self-contained and does not modify the host operating
 * system. Run with:
 *
 *   node linux_users_permissions.js
 *
 * JavaScript cannot directly reproduce the Linux kernel's permission engine.
 * The permission engine below is therefore an educational model of the
 * traditional owner/group/other model plus a simplified ACL layer.
 */

// -----------------------------------------------------------------------------
// 1. Basic permission representation
// -----------------------------------------------------------------------------

const Permission = Object.freeze({
    READ: "r",
    WRITE: "w",
    EXECUTE: "x"
});

function createPermissions(read = false, write = false, execute = false) {
    return Object.freeze({
        read: Boolean(read),
        write: Boolean(write),
        execute: Boolean(execute)
    });
}

function permissionFromDigit(digit) {
    if (!Number.isInteger(digit) || digit < 0 || digit > 7) {
        throw new RangeError("Permission digit must be an integer from 0 to 7.");
    }

    return createPermissions(
        Boolean(digit & 4),
        Boolean(digit & 2),
        Boolean(digit & 1)
    );
}

function permissionToDigit(permission) {
    return (
        (permission.read ? 4 : 0) +
        (permission.write ? 2 : 0) +
        (permission.execute ? 1 : 0)
    );
}

function permissionToSymbolic(permission) {
    return (
        (permission.read ? "r" : "-") +
        (permission.write ? "w" : "-") +
        (permission.execute ? "x" : "-")
    );
}

function modeToPermissions(mode) {
    if (!Number.isInteger(mode) || mode < 0 || mode > 0o777) {
        throw new RangeError("Mode must be an octal permission mode.");
    }

    return {
        owner: permissionFromDigit((mode >> 6) & 7),
        group: permissionFromDigit((mode >> 3) & 7),
        other: permissionFromDigit(mode & 7)
    };
}

function formatMode(mode) {
    const permissions = modeToPermissions(mode);

    return (
        permissionToSymbolic(permissions.owner) +
        permissionToSymbolic(permissions.group) +
        permissionToSymbolic(permissions.other)
    );
}

// -----------------------------------------------------------------------------
// 2. Users and groups
// -----------------------------------------------------------------------------

class LinuxUser {
    constructor(username, uid, primaryGid, supplementaryGroups = []) {
        if (!username || !Number.isInteger(uid) || !Number.isInteger(primaryGid)) {
            throw new TypeError("A user requires username, UID, and primary GID.");
        }

        this.username = username;
        this.uid = uid;
        this.primaryGid = primaryGid;
        this.supplementaryGroups = new Set(supplementaryGroups);
    }

    belongsToGroup(gid) {
        return (
            this.primaryGid === gid ||
            this.supplementaryGroups.has(gid)
        );
    }
}

class LinuxGroup {
    constructor(name, gid) {
        if (!name || !Number.isInteger(gid)) {
            throw new TypeError("A group requires a name and numeric GID.");
        }

        this.name = name;
        this.gid = gid;
        this.members = new Set();
    }

    addMember(user) {
        this.members.add(user.username);
    }
}

// -----------------------------------------------------------------------------
// 3. File metadata
// -----------------------------------------------------------------------------

class LinuxFile {
    constructor({
        path,
        ownerUid,
        groupGid,
        mode = 0o644,
        type = "file",
        aclEntries = []
    }) {
        this.path = path;
        this.ownerUid = ownerUid;
        this.groupGid = groupGid;
        this.mode = mode;
        this.type = type;
        this.aclEntries = [...aclEntries];
    }

    ordinaryPermissions() {
        return modeToPermissions(this.mode & 0o777);
    }

    isDirectory() {
        return this.type === "directory";
    }
}

// -----------------------------------------------------------------------------
// 4. Traditional owner/group/other access
// -----------------------------------------------------------------------------

function selectTraditionalPermissionClass(user, file) {
    if (user.uid === file.ownerUid) {
        return "owner";
    }

    if (user.belongsToGroup(file.groupGid)) {
        return "group";
    }

    return "other";
}

function permissionAllows(permission, operation) {
    switch (operation) {
        case Permission.READ:
            return permission.read;
        case Permission.WRITE:
            return permission.write;
        case Permission.EXECUTE:
            return permission.execute;
        default:
            throw new Error(`Unknown operation: ${operation}`);
    }
}

function traditionalAccessDecision(user, file, operation) {
    const selectedClass = selectTraditionalPermissionClass(user, file);
    const permissions = file.ordinaryPermissions()[selectedClass];

    return {
        allowed: permissionAllows(permissions, operation),
        source: selectedClass,
        permissions
    };
}

// -----------------------------------------------------------------------------
// 5. Simplified ACL layer
// -----------------------------------------------------------------------------

/*
 * A real POSIX ACL has more details, including an ACL mask. This simplified
 * representation exists to demonstrate why ACLs can express permissions for
 * a named user or group beyond the three traditional classes.
 */
class AccessControlEntry {
    constructor({
        type,
        id,
        permissions
    }) {
        if (!["user", "group"].includes(type)) {
            throw new TypeError("ACL type must be 'user' or 'group'.");
        }

        this.type = type;
        this.id = id;
        this.permissions = permissions;
    }
}

function aclAccessDecision(user, file, operation) {
    const matchingEntry = file.aclEntries.find((entry) => {
        if (entry.type === "user") {
            return entry.id === user.uid;
        }

        if (entry.type === "group") {
            return user.belongsToGroup(entry.id);
        }

        return false;
    });

    if (!matchingEntry) {
        return null;
    }

    return {
        allowed: permissionAllows(matchingEntry.permissions, operation),
        source: `acl:${matchingEntry.type}`,
        permissions: matchingEntry.permissions
    };
}

// -----------------------------------------------------------------------------
// 6. Unified access decision
// -----------------------------------------------------------------------------

function canAccess(user, file, operation) {
    if (user.uid === 0) {
        /*
         * This represents the traditional root model only. Real Linux root
         * behavior has exceptions, including execute checks, filesystem
         * restrictions, capabilities, namespaces, LSM policies, and mount
         * options.
         */
        return {
            allowed: true,
            source: "root-model"
        };
    }

    const aclDecision = aclAccessDecision(user, file, operation);

    if (aclDecision !== null) {
        return aclDecision;
    }

    return traditionalAccessDecision(user, file, operation);
}

// -----------------------------------------------------------------------------
// 7. Directory-specific semantics
// -----------------------------------------------------------------------------

function explainDirectoryOperation(operation) {
    const meanings = {
        r: "read: list directory entries",
        w: "write: create/remove/rename entries when search permission also permits the required path operations",
        x: "execute/search: traverse the directory and access entries by path"
    };

    return meanings[operation] || "unknown operation";
}

// -----------------------------------------------------------------------------
// 8. umask
// -----------------------------------------------------------------------------

function applyUmask(requestedMode, umask) {
    if (
        !Number.isInteger(requestedMode) ||
        !Number.isInteger(umask) ||
        requestedMode < 0 ||
        requestedMode > 0o777 ||
        umask < 0 ||
        umask > 0o777
    ) {
        throw new RangeError("Mode and umask must be valid 000-777 values.");
    }

    return requestedMode & (~umask);
}

function demonstrateUmask() {
    console.log("\nUMASK EXAMPLES");

    for (const umask of [0o022, 0o027, 0o077]) {
        const fileMode = applyUmask(0o666, umask);
        const directoryMode = applyUmask(0o777, umask);

        console.log(
            `umask ${umask.toString(8).padStart(3, "0")} -> ` +
            `file ${fileMode.toString(8).padStart(3, "0")}, ` +
            `directory ${directoryMode.toString(8).padStart(3, "0")}`
        );
    }
}

// -----------------------------------------------------------------------------
// 9. Permission matrix
// -----------------------------------------------------------------------------

function printPermissionMatrix(file, users) {
    console.log(`\nACCESS MATRIX FOR ${file.path}`);
    console.log(
        `${"User".padEnd(14)} ` +
        `${"Class".padEnd(10)} ` +
        `${"Read".padEnd(7)} ` +
        `${"Write".padEnd(7)} ` +
        `${"Execute".padEnd(7)}`
    );

    for (const user of users) {
        const className = selectTraditionalPermissionClass(user, file);
        const permission = file.ordinaryPermissions()[className];

        console.log(
            `${user.username.padEnd(14)} ` +
            `${className.padEnd(10)} ` +
            `${String(permission.read).padEnd(7)} ` +
            `${String(permission.write).padEnd(7)} ` +
            `${String(permission.execute).padEnd(7)}`
        );
    }
}

// -----------------------------------------------------------------------------
// 10. Application authorization versus filesystem authorization
// -----------------------------------------------------------------------------

class ApplicationDocumentService {
    constructor() {
        this.documents = new Map();
    }

    addDocument(document) {
        if (!document.id || !document.ownerUid) {
            throw new Error("Document requires an ID and owner UID.");
        }

        this.documents.set(document.id, {
            ...document
        });
    }

    readDocument(user, documentId) {
        const document = this.documents.get(documentId);

        if (!document) {
            throw new Error("Document not found.");
        }

        /*
         * Application authorization is separate from Linux filesystem
         * authorization. A web application may impose business rules such as
         * "only the owner can read this document", even if the process itself
         * has filesystem access.
         */
        if (document.ownerUid !== user.uid && !user.belongsToGroup(document.groupGid)) {
            throw new Error("Application authorization denied.");
        }

        return document.content;
    }
}

// -----------------------------------------------------------------------------
// 11. Privileged operation simulation
// -----------------------------------------------------------------------------

class PrivilegedOperationService {
    constructor(auditLogger) {
        this.auditLogger = auditLogger;
    }

    deleteSensitiveFile(user, file) {
        if (user.uid !== 0) {
            this.auditLogger.record(
                user.username,
                "DELETE_SENSITIVE_FILE",
                file.path,
                "DENIED"
            );

            throw new Error("Privileged operation requires root in this model.");
        }

        this.auditLogger.record(
            user.username,
            "DELETE_SENSITIVE_FILE",
            file.path,
            "ALLOWED"
        );

        return true;
    }
}

// -----------------------------------------------------------------------------
// 12. Auditing
// -----------------------------------------------------------------------------

class AuditLogger {
    constructor() {
        this.events = [];
    }

    record(actor, action, resource, result) {
        this.events.push({
            timestamp: new Date().toISOString(),
            actor,
            action,
            resource,
            result
        });
    }

    print() {
        console.log("\nAUDIT LOG");

        for (const event of this.events) {
            console.log(
                `${event.timestamp} | ` +
                `${event.actor} | ` +
                `${event.action} | ` +
                `${event.resource} | ` +
                `${event.result}`
            );
        }
    }
}

// -----------------------------------------------------------------------------
// 13. Tests
// -----------------------------------------------------------------------------

function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(
            `${message}: expected ${expected}, received ${actual}`
        );
    }
}

function runTests() {
    console.log("\nRUNNING TESTS");

    const owner = new LinuxUser("alice", 1000, 100);
    const developer = new LinuxUser("bob", 1001, 200, [100]);
    const outsider = new LinuxUser("charlie", 1002, 300);

    const report = new LinuxFile({
        path: "/srv/project/report.txt",
        ownerUid: 1000,
        groupGid: 100,
        mode: 0o640
    });

    assertEqual(
        canAccess(owner, report, Permission.READ).allowed,
        true,
        "Owner should read"
    );

    assertEqual(
        canAccess(owner, report, Permission.WRITE).allowed,
        true,
        "Owner should write"
    );

    assertEqual(
        canAccess(developer, report, Permission.READ).allowed,
        true,
        "Group member should read"
    );

    assertEqual(
        canAccess(developer, report, Permission.WRITE).allowed,
        false,
        "Group member should not write"
    );

    assertEqual(
        canAccess(outsider, report, Permission.READ).allowed,
        false,
        "Outsider should not read"
    );

    console.log("All permission tests passed.");
}

// -----------------------------------------------------------------------------
// 14. Edge cases
// -----------------------------------------------------------------------------

function demonstrateEdgeCases() {
    console.log("\nEDGE CASES");

    const owner = new LinuxUser("owner", 5000, 500);
    const groupMember = new LinuxUser("groupuser", 5001, 501, [500]);
    const outsider = new LinuxUser("outsider", 5002, 502);

    const executable = new LinuxFile({
        path: "/opt/tool",
        ownerUid: 5000,
        groupGid: 500,
        mode: 0o750
    });

    for (const [user, operation] of [
        [owner, "r"],
        [owner, "w"],
        [owner, "x"],
        [groupMember, "r"],
        [groupMember, "w"],
        [groupMember, "x"],
        [outsider, "r"],
        [outsider, "x"]
    ]) {
        const result = canAccess(user, executable, operation);

        console.log(
            `${user.username.padEnd(12)} ` +
            `${operation} -> ${result.allowed} (${result.source})`
        );
    }

    const namedAclUser = new LinuxUser("auditor", 7000, 700);

    const aclFile = new LinuxFile({
        path: "/srv/finance/audit.csv",
        ownerUid: 5000,
        groupGid: 500,
        mode: 0o600,
        aclEntries: [
            new AccessControlEntry({
                type: "user",
                id: namedAclUser.uid,
                permissions: createPermissions(true, false, false)
            })
        ]
    });

    console.log(
        "Named ACL user read:",
        canAccess(namedAclUser, aclFile, Permission.READ)
    );

    console.log(
        "Named ACL user write:",
        canAccess(namedAclUser, aclFile, Permission.WRITE)
    );
}

// -----------------------------------------------------------------------------
// 15. Special bits
// -----------------------------------------------------------------------------

function explainSpecialBits() {
    console.log(`
SPECIAL PERMISSION BITS

setuid:
  Numeric high bit 4000.
  On suitable executables, execution can use the file owner's effective UID.

setgid:
  Numeric high bit 2000.
  On directories, it commonly causes newly created entries to inherit the
  directory's group.

sticky:
  Numeric high bit 1000.
  On shared directories, it restricts deletion and rename of other users'
  entries.

Examples:
  4755 = setuid + 755
  2755 = setgid + 755
  1777 = sticky + 777

These bits are security-sensitive and should not be applied casually.
`);
}

// -----------------------------------------------------------------------------
// 16. Full demonstration
// -----------------------------------------------------------------------------

function main() {
    console.log("LINUX USERS AND PERMISSIONS");
    console.log("===========================");

    console.log("\nBASIC MODES");

    for (const mode of [0o600, 0o640, 0o644, 0o700, 0o750, 0o755, 0o777]) {
        console.log(
            `${mode.toString(8).padStart(3, "0")} -> ${formatMode(mode)}`
        );
    }

    const developers = new LinuxGroup("developers", 100);
    const alice = new LinuxUser("alice", 1000, 100);
    const bob = new LinuxUser("bob", 1001, 200, [100]);
    const charlie = new LinuxUser("charlie", 1002, 300);

    developers.addMember(alice);
    developers.addMember(bob);

    const sourceFile = new LinuxFile({
        path: "/srv/project/main.cpp",
        ownerUid: alice.uid,
        groupGid: developers.gid,
        mode: 0o750
    });

    console.log(
        `\n${sourceFile.path} -> ` +
        `${formatMode(sourceFile.mode)} ` +
        `owner=${sourceFile.ownerUid} group=${sourceFile.groupGid}`
    );

    printPermissionMatrix(sourceFile, [alice, bob, charlie]);

    console.log("\nDETAILED ACCESS DECISIONS");

    for (const user of [alice, bob, charlie]) {
        for (const operation of ["r", "w", "x"]) {
            console.log(
                `${user.username} -> ${operation}:`,
                canAccess(user, sourceFile, operation)
            );
        }
    }

    console.log("\nDIRECTORY SEMANTICS");

    for (const operation of ["r", "w", "x"]) {
        console.log(`${operation}: ${explainDirectoryOperation(operation)}`);
    }

    demonstrateUmask();
    explainSpecialBits();
    demonstrateEdgeCases();

    const documents = new ApplicationDocumentService();

    documents.addDocument({
        id: "DOC-001",
        ownerUid: alice.uid,
        groupGid: developers.gid,
        content: "Quarterly engineering report"
    });

    console.log("\nAPPLICATION AUTHORIZATION");

    console.log(
        "Alice:",
        documents.readDocument(alice, "DOC-001")
    );

    try {
        console.log(
            "Charlie:",
            documents.readDocument(charlie, "DOC-001")
        );
    } catch (error) {
        console.log("Charlie:", error.message);
    }

    const auditLogger = new AuditLogger();
    const privilegedService = new PrivilegedOperationService(auditLogger);

    console.log("\nPRIVILEGED OPERATION");

    try {
        privilegedService.deleteSensitiveFile(charlie, sourceFile);
    } catch (error) {
        console.log("Denied:", error.message);
    }

    const root = new LinuxUser("root", 0, 0);

    console.log(
        "Root operation:",
        privilegedService.deleteSensitiveFile(root, sourceFile)
    );

    auditLogger.print();

    runTests();

    console.log(`
PRODUCTION PRINCIPLES

1. Prefer least privilege.
2. Avoid unnecessary 777 permissions.
3. Protect credentials and private configuration.
4. Use groups for controlled collaboration.
5. Inspect parent-directory permissions when debugging.
6. Inspect ACLs when ordinary mode bits do not explain access.
7. Treat setuid/setgid as security-sensitive.
8. Do not confuse authentication with authorization.
9. Remember that Linux permissions are only one security layer.
10. Audit privileged actions.
11. Validate application authorization separately from filesystem access.
12. Consider race conditions and symlink attacks in privileged programs.
`);
}

main();
