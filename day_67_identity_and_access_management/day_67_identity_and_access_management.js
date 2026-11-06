"use strict";

/*
 * Identity and Access Management
 *
 * Event-driven Node.js implementation featuring:
 * - Identity lifecycle
 * - Group membership
 * - Role-based authorization
 * - Attribute-aware policy conditions
 * - Explicit deny precedence
 * - Permission inheritance through groups
 * - Temporary privilege elevation
 * - Policy change events
 * - Access decision logging
 * - Asynchronous access requests
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

class IAMError extends Error {
    constructor(message) {
        super(message);
        this.name = this.constructor.name;
    }
}

class ValidationError extends IAMError {}
class NotFoundError extends IAMError {}
class AccessDeniedError extends IAMError {}

const Effect = Object.freeze({
    ALLOW: "ALLOW",
    DENY: "DENY"
});

const Decision = Object.freeze({
    ALLOW: "ALLOW",
    DENY: "DENY"
});

function validateIdentifier(value, label) {
    if (
        typeof value !== "string" ||
        !/^[A-Za-z0-9_-]{2,64}$/.test(value)
    ) {
        throw new ValidationError(`Invalid ${label}.`);
    }
}

function validatePermission(permission) {
    if (
        !permission ||
        typeof permission.resource !== "string" ||
        typeof permission.action !== "string" ||
        !permission.resource.trim() ||
        !permission.action.trim()
    ) {
        throw new ValidationError("Invalid permission.");
    }

    if (
        permission.resource !== "*" &&
        !permission.resource.split("/").every(
            part => part && part !== "." && part !== ".."
        )
    ) {
        throw new ValidationError("Invalid resource path.");
    }

    if (
        permission.action !== "*" &&
        !/^[a-z][a-z0-9_]*$/.test(permission.action)
    ) {
        throw new ValidationError("Invalid action.");
    }
}

function matches(permission, request) {
    const resourceMatch =
        permission.resource === "*" ||
        permission.resource === request.resource ||
        (
            permission.resource.endsWith("/*") &&
            request.resource.startsWith(
                permission.resource.slice(0, -1)
            )
        );

    const actionMatch =
        permission.action === "*" ||
        permission.action === request.action;

    return resourceMatch && actionMatch;
}

function normalizeExpiry(expiresAt) {
    if (expiresAt === null || expiresAt === undefined) {
        return null;
    }

    const date = new Date(expiresAt);

    if (Number.isNaN(date.getTime())) {
        throw new ValidationError("Invalid expiration timestamp.");
    }

    if (date.getTime() <= Date.now()) {
        throw new ValidationError("Expiration must be in the future.");
    }

    return date;
}

class IdentityStore extends EventEmitter {
    constructor() {
        super();

        this.users = new Map();
        this.groups = new Map();
        this.roles = new Map();
        this.policies = new Map();
        this.assignments = new Map();

        this.auditLog = [];
        this.revision = 0;
    }

    addUser({ id, email, attributes = {} }) {
        validateIdentifier(id, "user ID");

        if (this.users.has(id)) {
            throw new ValidationError("User already exists.");
        }

        if (
            typeof email !== "string" ||
            !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
        ) {
            throw new ValidationError("Invalid email.");
        }

        this.users.set(id, {
            id,
            email,
            active: true,
            attributes: Object.freeze({ ...attributes }),
            groups: new Set()
        });

        this.changed("user.created", { userId: id });
    }

    addGroup({ id, name }) {
        validateIdentifier(id, "group ID");

        if (this.groups.has(id)) {
            throw new ValidationError("Group already exists.");
        }

        if (!name || !name.trim()) {
            throw new ValidationError("Group name is required.");
        }

        this.groups.set(id, {
            id,
            name,
            roles: new Set()
        });

        this.changed("group.created", { groupId: id });
    }

    addRole({ id, name, permissions }) {
        validateIdentifier(id, "role ID");

        if (this.roles.has(id)) {
            throw new ValidationError("Role already exists.");
        }

        if (!Array.isArray(permissions) || permissions.length === 0) {
            throw new ValidationError("A role needs permissions.");
        }

        permissions.forEach(validatePermission);

        this.roles.set(id, {
            id,
            name,
            permissions: permissions.map(p => Object.freeze({ ...p }))
        });

        this.changed("role.created", { roleId: id });
    }

    addMembership(userId, groupId) {
        const user = this.getUser(userId);
        this.getGroup(groupId);

        if (user.groups.has(groupId)) {
            throw new ValidationError("Membership already exists.");
        }

        user.groups.add(groupId);

        this.changed("membership.created", { userId, groupId });
    }

    removeMembership(userId, groupId) {
        const user = this.getUser(userId);
        this.getGroup(groupId);

        if (!user.groups.delete(groupId)) {
            throw new ValidationError("Membership does not exist.");
        }

        this.changed("membership.removed", { userId, groupId });
    }

    addRoleToGroup(groupId, roleId) {
        const group = this.getGroup(groupId);
        this.getRole(roleId);

        if (group.roles.has(roleId)) {
            throw new ValidationError("Role already assigned.");
        }

        group.roles.add(roleId);

        this.changed("group.role.assigned", { groupId, roleId });
    }

    assignTemporaryRole(userId, roleId, expiresAt) {
        this.getUser(userId);
        this.getRole(roleId);

        const expiry = normalizeExpiry(expiresAt);
        const assignmentId = crypto.randomUUID();

        this.assignments.set(assignmentId, {
            id: assignmentId,
            userId,
            roleId,
            expiresAt: expiry
        });

        this.changed("role.assigned", {
            userId,
            roleId,
            assignmentId,
            temporary: expiry !== null
        });

        return assignmentId;
    }

    revokeRole(assignmentId) {
        if (!this.assignments.delete(assignmentId)) {
            throw new NotFoundError("Role assignment not found.");
        }

        this.changed("role.revoked", { assignmentId });
    }

    deactivateUser(userId) {
        const user = this.getUser(userId);
        user.active = false;

        this.changed("user.deactivated", { userId });
    }

    addPolicy({
        id,
        effect,
        permission,
        userIds = [],
        groupIds = [],
        conditions = {},
        expiresAt = null
    }) {
        validateIdentifier(id, "policy ID");

        if (this.policies.has(id)) {
            throw new ValidationError("Policy already exists.");
        }

        if (!Object.values(Effect).includes(effect)) {
            throw new ValidationError("Invalid policy effect.");
        }

        validatePermission(permission);

        userIds.forEach(userId => this.getUser(userId));
        groupIds.forEach(groupId => this.getGroup(groupId));

        if (userIds.length === 0 && groupIds.length === 0) {
            throw new ValidationError("Policy needs a principal.");
        }

        if (
            conditions.department !== undefined &&
            typeof conditions.department !== "string"
        ) {
            throw new ValidationError("Invalid department condition.");
        }

        this.policies.set(id, {
            id,
            effect,
            permission: Object.freeze({ ...permission }),
            userIds: new Set(userIds),
            groupIds: new Set(groupIds),
            conditions: Object.freeze({ ...conditions }),
            expiresAt: normalizeExpiry(expiresAt),
            active: true
        });

        this.changed("policy.created", { policyId: id });
    }

    getUser(id) {
        const user = this.users.get(id);
        if (!user) throw new NotFoundError(`Unknown user: ${id}`);
        return user;
    }

    getGroup(id) {
        const group = this.groups.get(id);
        if (!group) throw new NotFoundError(`Unknown group: ${id}`);
        return group;
    }

    getRole(id) {
        const role = this.roles.get(id);
        if (!role) throw new NotFoundError(`Unknown role: ${id}`);
        return role;
    }

    effectiveRoles(userId, now = new Date()) {
        const user = this.getUser(userId);

        if (!user.active) return new Set();

        const roleIds = new Set();

        for (const groupId of user.groups) {
            for (const roleId of this.getGroup(groupId).roles) {
                roleIds.add(roleId);
            }
        }

        for (const assignment of this.assignments.values()) {
            if (
                assignment.userId === userId &&
                (
                    assignment.expiresAt === null ||
                    now < assignment.expiresAt
                )
            ) {
                roleIds.add(assignment.roleId);
            }
        }

        return roleIds;
    }

    evaluate(request) {
        const { userId, resource, action, context = {} } = request;

        if (!resource || !action) {
            throw new ValidationError("Resource and action are required.");
        }

        const user = this.getUser(userId);
        const now = new Date();

        const result = {
            requestId: crypto.randomUUID(),
            userId,
            resource,
            action,
            decision: Decision.DENY,
            reason: "",
            matchedRoles: [],
            matchedPolicies: [],
            revision: this.revision
        };

        if (!user.active) {
            result.reason = "Inactive identity.";
            return this.record(result);
        }

        const roles = this.effectiveRoles(userId, now);

        for (const roleId of roles) {
            const role = this.getRole(roleId);

            if (role.permissions.some(
                permission => matches(permission, request)
            )) {
                result.matchedRoles.push(role.name);
            }
        }

        let allowed = result.matchedRoles.length > 0;
        let denied = false;

        for (const policy of this.policies.values()) {
            if (
                !policy.active ||
                (policy.expiresAt && now >= policy.expiresAt)
            ) {
                continue;
            }

            const principalMatch =
                policy.userIds.has(userId) ||
                [...policy.groupIds].some(
                    groupId => user.groups.has(groupId)
                );

            if (!principalMatch) continue;

            const conditionsMatch = Object.entries(
                policy.conditions
            ).every(([key, value]) => context[key] === value);

            if (
                !conditionsMatch ||
                !matches(policy.permission, request)
            ) {
                continue;
            }

            result.matchedPolicies.push(policy.id);

            if (policy.effect === Effect.DENY) {
                denied = true;
            } else {
                allowed = true;
            }
        }

        if (denied) {
            result.reason = "Explicit deny overrides grants.";
        } else if (allowed) {
            result.decision = Decision.ALLOW;
            result.reason = "Matching authorization grant.";
        } else {
            result.reason = "No matching authorization grant.";
        }

        return this.record(result);
    }

    async authorize(request) {
        // Simulate an asynchronous authorization boundary.
        await Promise.resolve();

        const result = this.evaluate(request);

        if (result.decision === Decision.DENY) {
            throw new AccessDeniedError(
                `${result.reason} Request: ${result.requestId}`
            );
        }

        return result;
    }

    record(result) {
        this.auditLog.push(Object.freeze({ ...result }));

        this.emit("access.decision", result);

        return result;
    }

    changed(event, payload) {
        this.revision++;

        this.emit(event, {
            ...payload,
            revision: this.revision,
            timestamp: new Date().toISOString()
        });
    }

    auditUser(userId, requests) {
        return requests.map(request => this.evaluate({
            ...request,
            userId
        }));
    }

    getAuditReport() {
        return {
            total: this.auditLog.length,
            allowed: this.auditLog.filter(
                entry => entry.decision === Decision.ALLOW
            ).length,
            denied: this.auditLog.filter(
                entry => entry.decision === Decision.DENY
            ).length
        };
    }
}

async function main() {
    const iam = new IdentityStore();

    iam.on("access.decision", event => {
        console.log(
            `[AUDIT] ${event.userId} ${event.action} ` +
            `${event.resource}: ${event.decision}`
        );
    });

    iam.on("role.assigned", event => {
        console.log(
            `[EVENT] Role ${event.roleId} assigned to ${event.userId}`
        );
    });

    iam.addUser({
        id: "USER01",
        email: "alice@enterprise.example",
        attributes: { department: "engineering" }
    });

    iam.addUser({
        id: "USER02",
        email: "bob@enterprise.example",
        attributes: { department: "security" }
    });

    iam.addGroup({ id: "GROUP01", name: "Developers" });
    iam.addGroup({ id: "GROUP02", name: "SecurityTeam" });

    iam.addRole({
        id: "ROLE01",
        name: "ApplicationDeveloper",
        permissions: [
            { resource: "apps/project-a", action: "read" },
            { resource: "apps/project-a", action: "write" }
        ]
    });

    iam.addRole({
        id: "ROLE02",
        name: "SecurityAuditor",
        permissions: [
            { resource: "security/logs", action: "read" },
            { resource: "security/reports", action: "read" }
        ]
    });

    iam.addRole({
        id: "ROLE03",
        name: "IncidentAdministrator",
        permissions: [
            { resource: "*", action: "*" }
        ]
    });

    iam.addMembership("USER01", "GROUP01");
    iam.addMembership("USER02", "GROUP02");

    iam.addRoleToGroup("GROUP01", "ROLE01");
    iam.addRoleToGroup("GROUP02", "ROLE02");

    const temporaryAssignment = iam.assignTemporaryRole(
        "USER02",
        "ROLE03",
        new Date(Date.now() + 30 * 60 * 1000)
    );

    iam.addPolicy({
        id: "POLICY01",
        effect: Effect.DENY,
        permission: {
            resource: "production/secrets",
            action: "*"
        },
        groupIds: ["GROUP01"]
    });

    iam.addPolicy({
        id: "POLICY02",
        effect: Effect.ALLOW,
        permission: {
            resource: "deployment/reports",
            action: "read"
        },
        userIds: ["USER01"],
        conditions: {
            department: "engineering"
        }
    });

    const requests = [
        {
            userId: "USER01",
            resource: "apps/project-a",
            action: "read"
        },
        {
            userId: "USER01",
            resource: "production/secrets",
            action: "read"
        },
        {
            userId: "USER01",
            resource: "deployment/reports",
            action: "read",
            context: { department: "engineering" }
        },
        {
            userId: "USER01",
            resource: "deployment/reports",
            action: "read",
            context: { department: "finance" }
        },
        {
            userId: "USER02",
            resource: "security/logs",
            action: "read"
        }
    ];

    console.log("\nACCESS EVALUATION");

    for (const request of requests) {
        try {
            const result = await iam.authorize(request);

            console.log(
                `${request.userId}: ${result.decision} - ${result.reason}`
            );
        } catch (error) {
            if (error instanceof AccessDeniedError) {
                console.log(
                    `${request.userId}: DENIED - ${error.message}`
                );
            } else {
                throw error;
            }
        }
    }

    console.log("\nLEAST-PRIVILEGE AUDIT");

    const audit = iam.auditUser("USER01", [
        { resource: "apps/project-a", action: "read" },
        { resource: "apps/project-a", action: "delete" },
        { resource: "production/secrets", action: "read" },
        { resource: "security/logs", action: "read" }
    ]);

    for (const entry of audit) {
        console.log(
            `${entry.resource}:${entry.action} => ${entry.decision}`
        );
    }

    console.log("\nREVOCATION");

    iam.revokeRole(temporaryAssignment);

    const afterRevocation = iam.evaluate({
        userId: "USER02",
        resource: "production/secrets",
        action: "read"
    });

    console.log(
        `Access after role revocation: ${afterRevocation.decision}`
    );

    console.log("\nAUDIT COUNTS");
    console.log(iam.getAuditReport());

    console.log("\nVALIDATION TESTS");

    try {
        iam.addMembership("UNKNOWN", "GROUP01");
    } catch (error) {
        console.log(`Expected failure: ${error.message}`);
    }

    try {
        iam.addUser({
            id: "USER01",
            email: "duplicate@enterprise.example"
        });
    } catch (error) {
        console.log(`Expected failure: ${error.message}`);
    }

    try {
        iam.addRole({
            id: "ROLE04",
            name: "InvalidRole",
            permissions: []
        });
    } catch (error) {
        console.log(`Expected failure: ${error.message}`);
    }
}

main().catch(error => {
    console.error("IAM execution failed:", error.message);
    process.exitCode = 1;
});
