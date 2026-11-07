"use strict";

/*
 * Authentication and Authorization
 * Node.js 18+
 *
 * Passwords, MFA, signed tokens, sessions, OAuth PKCE,
 * RBAC and ABAC using Node.js standard libraries.
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const assert = require("node:assert/strict");

// ============================================================
// Errors
// ============================================================

class AuthenticationError extends Error {}
class AuthorizationError extends Error {}
class ValidationError extends Error {}

// ============================================================
// Password service
// ============================================================

class PasswordService {
    static ITERATIONS = 600000;

    static validate(password) {
        if (typeof password !== "string" ||
            password.length < 12 ||
            !/[A-Z]/.test(password) ||
            !/[a-z]/.test(password) ||
            !/[0-9]/.test(password) ||
            !/[^A-Za-z0-9]/.test(password)) {
            throw new ValidationError("Password policy violation.");
        }
    }

    static async hash(password) {
        this.validate(password);

        const salt = crypto.randomBytes(16);

        const derived = await new Promise((resolve, reject) => {
            crypto.pbkdf2(
                password,
                salt,
                this.ITERATIONS,
                32,
                "sha256",
                (error, key) => {
                    if (error) reject(error);
                    else resolve(key);
                }
            );
        });

        return {
            algorithm: "pbkdf2-sha256",
            iterations: this.ITERATIONS,
            salt: salt.toString("base64"),
            hash: derived.toString("base64")
        };
    }

    static async verify(password, record) {
        if (!record || record.algorithm !== "pbkdf2-sha256" ||
            !Number.isInteger(record.iterations) ||
            record.iterations < 100000 ||
            record.iterations > 2000000) {
            return false;
        }

        try {
            const salt = Buffer.from(record.salt, "base64");
            const expected = Buffer.from(record.hash, "base64");

            if (salt.length !== 16 || expected.length !== 32) {
                return false;
            }

            const actual = await new Promise((resolve, reject) => {
                crypto.pbkdf2(
                    password,
                    salt,
                    record.iterations,
                    32,
                    "sha256",
                    (error, key) => {
                        if (error) reject(error);
                        else resolve(key);
                    }
                );
            });

            return crypto.timingSafeEqual(actual, expected);
        } catch {
            return false;
        }
    }
}

// ============================================================
// TOTP multifactor authentication
// ============================================================

class MFAService {
    static PERIOD = 30;

    static generateSecret() {
        return crypto.randomBytes(20);
    }

    static generate(secret, timestamp = Date.now()) {
        const counter = Math.floor(
            timestamp / 1000 / this.PERIOD
        );

        const message = Buffer.alloc(8);
        message.writeBigUInt64BE(BigInt(counter));

        const digest = crypto
            .createHmac("sha1", secret)
            .update(message)
            .digest();

        const offset = digest[digest.length - 1] & 0x0f;

        const value =
            ((digest[offset] & 0x7f) << 24) |
            ((digest[offset + 1] & 0xff) << 16) |
            ((digest[offset + 2] & 0xff) << 8) |
            (digest[offset + 3] & 0xff);

        return String(value % 1000000).padStart(6, "0");
    }

    static verify(secret, code, timestamp = Date.now()) {
        if (!/^\d{6}$/.test(code)) return false;

        return [-1, 0, 1].some(offset => {
            const expected = this.generate(
                secret,
                timestamp + offset * this.PERIOD * 1000
            );

            return crypto.timingSafeEqual(
                Buffer.from(expected),
                Buffer.from(code)
            );
        });
    }
}

// ============================================================
// Access-token service
// ============================================================

class AccessTokenService {
    constructor(secret) {
        if (!Buffer.isBuffer(secret) || secret.length < 32) {
            throw new ValidationError("Invalid signing key.");
        }

        this.secret = secret;
    }

    static encode(value) {
        return Buffer.from(JSON.stringify(value))
            .toString("base64url");
    }

    issue(user, lifetimeSeconds = 900) {
        if (!Number.isInteger(lifetimeSeconds) ||
            lifetimeSeconds < 1 ||
            lifetimeSeconds > 3600) {
            throw new ValidationError("Invalid token lifetime.");
        }

        const header = {
            alg: "HS256",
            typ: "JWT"
        };

        const payload = {
            sub: user.id,
            roles: [...user.roles],
            iat: Math.floor(Date.now() / 1000),
            exp: Math.floor(Date.now() / 1000) + lifetimeSeconds,
            iss: "identity.example",
            aud: "api.example",
            jti: crypto.randomUUID()
        };

        const content =
            `${AccessTokenService.encode(header)}.` +
            `${AccessTokenService.encode(payload)}`;

        const signature = crypto
            .createHmac("sha256", this.secret)
            .update(content)
            .digest("base64url");

        return `${content}.${signature}`;
    }

    verify(token) {
        const parts = token.split(".");

        if (parts.length !== 3) {
            throw new AuthenticationError("Malformed token.");
        }

        const content = `${parts[0]}.${parts[1]}`;

        const expected = crypto
            .createHmac("sha256", this.secret)
            .update(content)
            .digest();

        let supplied;

        try {
            supplied = Buffer.from(parts[2], "base64url");
        } catch {
            throw new AuthenticationError("Invalid signature.");
        }

        if (supplied.length !== expected.length ||
            !crypto.timingSafeEqual(supplied, expected)) {
            throw new AuthenticationError("Invalid signature.");
        }

        try {
            const header = JSON.parse(
                Buffer.from(parts[0], "base64url").toString()
            );

            const payload = JSON.parse(
                Buffer.from(parts[1], "base64url").toString()
            );

            if (header.alg !== "HS256" ||
                header.typ !== "JWT" ||
                payload.iss !== "identity.example" ||
                payload.aud !== "api.example" ||
                typeof payload.sub !== "string" ||
                !Number.isInteger(payload.exp) ||
                !Array.isArray(payload.roles)) {
                throw new AuthenticationError("Invalid claims.");
            }

            if (payload.exp <= Math.floor(Date.now() / 1000)) {
                throw new AuthenticationError("Expired token.");
            }

            return payload;
        } catch (error) {
            if (error instanceof AuthenticationError) throw error;
            throw new AuthenticationError("Invalid token payload.");
        }
    }
}

// ============================================================
// RBAC policy engine
// ============================================================

class RBACPolicy {
    constructor() {
        this.permissions = new Map([
            ["employee", new Set([
                "profile:read",
                "profile:update"
            ])],
            ["analyst", new Set([
                "profile:read",
                "reports:read"
            ])],
            ["admin", new Set([
                "profile:read",
                "profile:update",
                "reports:read",
                "users:manage",
                "security:manage"
            ])]
        ]);
    }

    allows(roles, permission) {
        return roles.some(role =>
            this.permissions.get(role)?.has(permission) ?? false
        );
    }
}

// ============================================================
// ABAC policy engine
// ============================================================

class ABACPolicy {
    evaluate(subject, resource, action, environment) {
        if (subject.status !== "active" ||
            environment.mfaVerified !== true ||
            environment.riskScore > 70) {
            return false;
        }

        if (action === "read") {
            return subject.department === resource.department ||
                subject.roles.includes("admin");
        }

        if (action === "approve") {
            return subject.department === resource.department &&
                subject.clearance >= resource.classification &&
                subject.id !== resource.ownerId;
        }

        return false;
    }
}

// ============================================================
// OAuth authorization code with PKCE
// ============================================================

class OAuthService {
    constructor() {
        this.clients = new Map();
        this.codes = new Map();
    }

    registerClient(clientId, redirectUris) {
        if (!clientId || !Array.isArray(redirectUris) ||
            redirectUris.length === 0) {
            throw new ValidationError("Invalid client registration.");
        }

        this.clients.set(clientId, new Set(redirectUris));
    }

    createChallenge(verifier) {
        if (typeof verifier !== "string" ||
            verifier.length < 43 ||
            verifier.length > 128 ||
            !/^[A-Za-z0-9._~-]+$/.test(verifier)) {
            throw new ValidationError("Invalid PKCE verifier.");
        }

        return crypto.createHash("sha256")
            .update(verifier)
            .digest("base64url");
    }

    authorize(clientId, redirectUri, state, challenge) {
        const client = this.clients.get(clientId);

        if (!client || !client.has(redirectUri)) {
            throw new AuthorizationError("Invalid OAuth client or redirect.");
        }

        if (typeof state !== "string" || state.length < 16) {
            throw new ValidationError("Invalid state parameter.");
        }

        if (!/^[A-Za-z0-9_-]{43}$/.test(challenge)) {
            throw new ValidationError("Invalid challenge.");
        }

        const code = crypto.randomBytes(32).toString("base64url");

        this.codes.set(code, {
            clientId,
            redirectUri,
            state,
            challenge,
            expiresAt: Date.now() + 300000,
            used: false
        });

        return code;
    }

    exchange(code, clientId, redirectUri, verifier) {
        const record = this.codes.get(code);

        if (!record || record.used ||
            record.expiresAt <= Date.now()) {
            throw new AuthenticationError("Invalid authorization code.");
        }

        if (record.clientId !== clientId ||
            record.redirectUri !== redirectUri) {
            throw new AuthenticationError("OAuth client mismatch.");
        }

        const challenge = this.createChallenge(verifier);

        if (challenge !== record.challenge) {
            throw new AuthenticationError("PKCE verification failed.");
        }

        record.used = true;

        return crypto.randomBytes(32).toString("base64url");
    }
}

// ============================================================
// Event-driven session management
// ============================================================

class SessionManager extends EventEmitter {
    constructor() {
        super();
        this.sessions = new Map();
        this.ttl = 30 * 60 * 1000;
    }

    create(userId) {
        const id = crypto.randomBytes(32).toString("base64url");

        const session = {
            id,
            userId,
            createdAt: Date.now(),
            expiresAt: Date.now() + this.ttl,
            status: "active"
        };

        this.sessions.set(id, session);
        this.emit("session.created", {
            userId,
            sessionId: id
        });

        return session;
    }

    validate(id) {
        const session = this.sessions.get(id);

        if (!session || session.status !== "active") {
            throw new AuthenticationError("Invalid session.");
        }

        if (session.expiresAt <= Date.now()) {
            session.status = "expired";
            this.emit("session.expired", { userId: session.userId });
            throw new AuthenticationError("Session expired.");
        }

        return session;
    }

    revoke(id) {
        const session = this.sessions.get(id);

        if (!session || session.status !== "active") {
            return false;
        }

        session.status = "revoked";

        this.emit("session.revoked", {
            userId: session.userId
        });

        return true;
    }

    revokeAll(userId) {
        let count = 0;

        for (const session of this.sessions.values()) {
            if (session.userId === userId &&
                session.status === "active") {
                this.revoke(session.id);
                count++;
            }
        }

        return count;
    }
}

// ============================================================
// Integrated identity service
// ============================================================

class IdentityService {
    constructor() {
        this.users = new Map();
        this.usernames = new Map();
        this.sessions = new SessionManager();
        this.rbac = new RBACPolicy();
        this.abac = new ABACPolicy();
    }

    async register(username, password, roles, department) {
        username = username.trim().toLowerCase();

        if (!/^[a-z0-9_.-]{3,40}$/.test(username)) {
            throw new ValidationError("Invalid username.");
        }

        if (this.usernames.has(username)) {
            throw new ValidationError("Duplicate username.");
        }

        if (!Array.isArray(roles) ||
            roles.length === 0 ||
            roles.some(role =>
                !this.rbac.permissions.has(role)
            )) {
            throw new ValidationError("Invalid roles.");
        }

        const user = {
            id: crypto.randomUUID(),
            username,
            password: await PasswordService.hash(password),
            roles: [...new Set(roles)],
            department,
            status: "active",
            mfaSecret: null,
            failedAttempts: 0
        };

        this.users.set(user.id, user);
        this.usernames.set(username, user.id);

        return user;
    }

    enrollMFA(userId) {
        const user = this.users.get(userId);

        if (!user || user.status !== "active") {
            throw new AuthenticationError("Account unavailable.");
        }

        user.mfaSecret = MFAService.generateSecret();
        return user.mfaSecret;
    }

    async authenticate(username, password, mfaCode = null) {
        const userId = this.usernames.get(username.toLowerCase());
        const user = this.users.get(userId);

        if (!user || user.status !== "active") {
            throw new AuthenticationError("Invalid credentials.");
        }

        if (user.failedAttempts >= 5) {
            user.status = "locked";
            throw new AuthenticationError("Account locked.");
        }

        if (!await PasswordService.verify(password, user.password)) {
            user.failedAttempts++;

            if (user.failedAttempts >= 5) {
                user.status = "locked";
            }

            throw new AuthenticationError("Invalid credentials.");
        }

        if (user.mfaSecret) {
            if (!mfaCode ||
                !MFAService.verify(user.mfaSecret, mfaCode)) {
                throw new AuthenticationError("MFA verification failed.");
            }
        }

        user.failedAttempts = 0;

        return this.sessions.create(user.id);
    }

    authorizeRole(userId, permission) {
        const user = this.users.get(userId);

        if (!user || user.status !== "active" ||
            !this.rbac.allows(user.roles, permission)) {
            throw new AuthorizationError("Permission denied.");
        }

        return true;
    }
}

// ============================================================
// Demonstration and tests
// ============================================================

async function main() {
    console.log("AUTHENTICATION AND AUTHORIZATION");
    console.log("================================");

    const identity = new IdentityService();

    const alice = await identity.register(
        "alice",
        "StrongPassword#2026",
        ["employee"],
        "engineering"
    );

    const bob = await identity.register(
        "bob",
        "Administrator#2026",
        ["admin"],
        "security"
    );

    console.log("\n1. Password authentication");

    const session = await identity.authenticate(
        "alice",
        "StrongPassword#2026"
    );

    console.log("Session:", session.status);

    console.log("\n2. RBAC");

    console.log(
        "Read profile:",
        identity.rbac.allows(alice.roles, "profile:read")
    );

    console.log(
        "Manage users:",
        identity.rbac.allows(alice.roles, "users:manage")
    );

    console.log(
        "Administrator permission:",
        identity.rbac.allows(bob.roles, "users:manage")
    );

    console.log("\n3. ABAC");

    console.log(
        "Department access:",
        identity.abac.evaluate(
            {
                id: alice.id,
                status: "active",
                department: "engineering",
                roles: alice.roles,
                clearance: 2
            },
            {
                department: "engineering",
                classification: 1,
                ownerId: "another-user"
            },
            "read",
            {
                mfaVerified: true,
                riskScore: 15
            }
        )
    );

    console.log("\n4. MFA");

    const secret = MFAService.generateSecret();
    const code = MFAService.generate(secret);

    console.log("Valid TOTP:", MFAService.verify(secret, code));

    console.log("\n5. Signed access token");

    const tokens = new AccessTokenService(
        crypto.randomBytes(32)
    );

    const token = tokens.issue(alice);

    console.log("Token subject:", tokens.verify(token).sub);

    console.log("\n6. OAuth 2.0 and PKCE");

    const oauth = new OAuthService();

    oauth.registerClient(
        "web-client",
        ["https://client.example/callback"]
    );

    const verifier = crypto.randomBytes(32).toString("base64url");
    const challenge = oauth.createChallenge(verifier);

    const authorizationCode = oauth.authorize(
        "web-client",
        "https://client.example/callback",
        crypto.randomBytes(24).toString("base64url"),
        challenge
    );

    const oauthToken = oauth.exchange(
        authorizationCode,
        "web-client",
        "https://client.example/callback",
        verifier
    );

    console.log("OAuth exchange successful:", !!oauthToken);

    console.log("\n7. Session events");

    identity.sessions.on("session.revoked", event => {
        console.log("Session revoked for:", event.userId);
    });

    identity.sessions.validate(session.id);
    identity.sessions.revoke(session.id);

    console.log("\n8. Failure handling");

    assert.equal(
        await PasswordService.verify(
            "WrongPassword#2026",
            alice.password
        ),
        false
    );

    assert.throws(
        () => identity.authorizeRole(alice.id, "users:manage"),
        AuthorizationError
    );

    assert.throws(
        () => tokens.verify(token + "tampered"),
        AuthenticationError
    );

    assert.throws(
        () => oauth.exchange(
            authorizationCode,
            "web-client",
            "https://client.example/callback",
            verifier
        ),
        AuthenticationError
    );

    console.log("Invalid password rejected.");
    console.log("Unauthorized operation rejected.");
    console.log("Tampered token rejected.");
    console.log("Reused authorization code rejected.");

    console.log("\nAll tests passed.");
}

main().catch(error => {
    console.error("Execution failed:", error.message);
    process.exitCode = 1;
});
