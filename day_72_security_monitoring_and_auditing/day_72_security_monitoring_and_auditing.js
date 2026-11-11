"use strict";

/*
 * Security Monitoring and Auditing
 * Node.js 18+
 *
 * Event-driven security monitoring with:
 * - Structured audit events
 * - Access monitoring
 * - Hash-chained audit records
 * - Security alert generation
 * - Sliding-window anomaly detection
 * - Asynchronous event processing
 * - Statistical detection
 * - Alert investigation and resolution
 *
 * No external npm dependencies.
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const { EventEmitter } = require("node:events");

// ============================================================
// CONSTANTS
// ============================================================

const EventType = Object.freeze({
    LOGIN_SUCCESS: "LOGIN_SUCCESS",
    LOGIN_FAILURE: "LOGIN_FAILURE",
    LOGOUT: "LOGOUT",
    ACCESS_GRANTED: "ACCESS_GRANTED",
    ACCESS_DENIED: "ACCESS_DENIED",
    PRIVILEGE_CHANGE: "PRIVILEGE_CHANGE",
    DATA_EXPORT: "DATA_EXPORT",
    CONFIGURATION_CHANGE: "CONFIGURATION_CHANGE",
    PASSWORD_CHANGE: "PASSWORD_CHANGE",
    FIREWALL_CHANGE: "FIREWALL_CHANGE"
});

const Severity = Object.freeze({
    LOW: "LOW",
    MEDIUM: "MEDIUM",
    HIGH: "HIGH",
    CRITICAL: "CRITICAL"
});

const AlertStatus = Object.freeze({
    OPEN: "OPEN",
    INVESTIGATING: "INVESTIGATING",
    RESOLVED: "RESOLVED",
    FALSE_POSITIVE: "FALSE_POSITIVE"
});

const TERMINAL_STATUSES = new Set([
    AlertStatus.RESOLVED,
    AlertStatus.FALSE_POSITIVE
]);

const ALLOWED_ROLES = new Set([
    "administrator",
    "developer",
    "auditor",
    "analyst"
]);

// ============================================================
// VALIDATION
// ============================================================

function requireString(value, field, maximum = 512) {
    if (
        typeof value !== "string" ||
        value.trim().length === 0 ||
        value.length > maximum
    ) {
        throw new TypeError(`Invalid ${field}`);
    }

    return value;
}

function validateTimestamp(timestamp) {
    const value = new Date(timestamp);

    if (!Number.isFinite(value.getTime())) {
        throw new TypeError("Invalid event timestamp");
    }

    return value;
}

function validateIP(ip) {
    requireString(ip, "source IP", 45);

    const ipv4 = /^(?:\d{1,3}\.){3}\d{1,3}$/;

    if (ipv4.test(ip)) {
        const valid = ip.split(".").every(
            part => Number(part) <= 255
        );

        if (!valid) {
            throw new TypeError("Invalid IPv4 address");
        }

        return ip;
    }

    // Basic IPv6 validation. Full canonicalization should be
    // performed by a dedicated network-address library.
    if (
        ip.includes(":") &&
        /^[0-9a-fA-F:]+$/.test(ip)
    ) {
        return ip;
    }

    throw new TypeError("Invalid IP address");
}

function validateEvent(input) {
    if (!input || typeof input !== "object") {
        throw new TypeError("Event must be an object");
    }

    if (!Object.values(EventType).includes(input.type)) {
        throw new TypeError("Unknown event type");
    }

    if (typeof input.success !== "boolean") {
        throw new TypeError("Success must be boolean");
    }

    const details = input.details ?? {};

    if (
        typeof details !== "object" ||
        details === null ||
        Array.isArray(details) ||
        Object.keys(details).length > 30
    ) {
        throw new TypeError("Invalid event details");
    }

    if (
        Buffer.byteLength(JSON.stringify(details), "utf8") > 8192
    ) {
        throw new RangeError("Event details exceed size limit");
    }

    if (input.type === EventType.DATA_EXPORT) {
        const count = details.recordCount;

        if (
            !Number.isSafeInteger(count) ||
            count < 0
        ) {
            throw new TypeError("Invalid export record count");
        }
    }

    return Object.freeze({
        id: input.id ?? crypto.randomUUID(),
        timestamp: validateTimestamp(
            input.timestamp ?? Date.now()
        ).toISOString(),
        type: input.type,
        userId: requireString(input.userId, "user ID", 128),
        sourceIP: validateIP(input.sourceIP),
        resource: requireString(input.resource, "resource"),
        success: input.success,
        details: structuredClone(details)
    });
}

// ============================================================
// CANONICAL SERIALIZATION
// ============================================================

function canonicalize(value) {
    if (value === null || typeof value !== "object") {
        return JSON.stringify(value);
    }

    if (Array.isArray(value)) {
        return `[${value.map(canonicalize).join(",")}]`;
    }

    const keys = Object.keys(value).sort();

    return `{${keys.map(
        key => `${JSON.stringify(key)}:${canonicalize(value[key])}`
    ).join(",")}}`;
}

// ============================================================
// AUDIT LOG SERVICE
// ============================================================

class AuditLog {

    constructor() {
        this.records = [];
        this.previousHash = "0".repeat(64);
        this.identifiers = new Set();
    }

    append(event) {

        if (this.identifiers.has(event.id)) {
            throw new Error("Duplicate audit event");
        }

        const canonical = canonicalize(event);

        const hash = crypto
            .createHash("sha256")
            .update(this.previousHash + canonical)
            .digest("hex");

        const record = Object.freeze({
            event: structuredClone(event),
            previousHash: this.previousHash,
            hash
        });

        this.records.push(record);
        this.identifiers.add(event.id);
        this.previousHash = hash;

        return record;
    }

    verify() {

        let previous = "0".repeat(64);
        const identifiers = new Set();

        for (const record of this.records) {

            if (record.previousHash !== previous) {
                return false;
            }

            if (identifiers.has(record.event.id)) {
                return false;
            }

            const expected = crypto
                .createHash("sha256")
                .update(
                    previous + canonicalize(record.event)
                )
                .digest("hex");

            if (expected !== record.hash) {
                return false;
            }

            previous = record.hash;
            identifiers.add(record.event.id);
        }

        return previous === this.previousHash;
    }

    async exportJSONL(filePath) {

        const lines = this.records.map(
            record => JSON.stringify(record)
        );

        const destination = path.resolve(filePath);

        await fs.mkdir(
            path.dirname(destination),
            { recursive: true }
        );

        await fs.writeFile(
            destination,
            lines.join("\n") + (lines.length ? "\n" : ""),
            {
                encoding: "utf8",
                mode: 0o600,
                flag: "wx"
            }
        );
    }
}

// ============================================================
// ACCESS CONTROL
// ============================================================

class AccessPolicy {

    constructor() {

        this.userRoles = new Map([
            ["alice", new Set(["developer"])],
            ["bob", new Set(["administrator"])],
            ["carol", new Set(["auditor"])],
            ["david", new Set(["analyst"])]
        ]);

        this.permissions = new Map([
            ["/admin", new Set(["administrator"])],
            ["/database", new Set(["administrator", "developer"])],
            ["/credentials", new Set(["administrator"])],
            ["/financial-records", new Set(["administrator", "auditor"])],
            ["/reports", new Set(["administrator", "auditor", "analyst"])],
            ["/application", new Set(["administrator", "developer", "analyst"])]
        ]);
    }

    authorize(userId, resource) {

        const roles = this.userRoles.get(userId);
        const allowed = this.permissions.get(resource);

        if (!roles || !allowed) {
            return false;
        }

        return [...roles].some(role => allowed.has(role));
    }

    changeRole(userId, role) {

        if (!this.userRoles.has(userId)) {
            throw new Error("Unknown user");
        }

        if (!ALLOWED_ROLES.has(role)) {
            throw new Error("Invalid role");
        }

        this.userRoles.set(userId, new Set([role]));
    }
}

// ============================================================
// SLIDING WINDOW ANOMALY DETECTOR
// ============================================================

class AnomalyDetector {

    constructor(options = {}) {

        this.failureThreshold = options.failureThreshold ?? 5;
        this.windowMs = options.windowMs ?? 10 * 60 * 1000;
        this.exportThreshold = options.exportThreshold ?? 1000;
        this.frequencyThreshold = options.frequencyThreshold ?? 30;

        if (
            this.failureThreshold <= 0 ||
            this.windowMs <= 0 ||
            this.exportThreshold <= 0 ||
            this.frequencyThreshold <= 0
        ) {
            throw new RangeError("Invalid detection thresholds");
        }

        this.events = [];
        this.userEventCounts = new Map();
    }

    analyze(event) {

        const currentTime = Date.parse(event.timestamp);
        const cutoff = currentTime - this.windowMs;

        // Remove expired events before evaluating the new event.
        while (
            this.events.length > 0 &&
            Date.parse(this.events[0].timestamp) < cutoff
        ) {
            const expired = this.events.shift();

            const count = this.userEventCounts.get(expired.userId) ?? 0;

            if (count <= 1) {
                this.userEventCounts.delete(expired.userId);
            } else {
                this.userEventCounts.set(
                    expired.userId,
                    count - 1
                );
            }
        }

        this.events.push(event);

        this.userEventCounts.set(
            event.userId,
            (this.userEventCounts.get(event.userId) ?? 0) + 1
        );

        const relevant = this.events.filter(
            item => item.userId === event.userId
        );

        const anomalies = [];
        let score = 0;

        const failedLogins = relevant.filter(
            item => item.type === EventType.LOGIN_FAILURE
        ).length;

        if (failedLogins >= this.failureThreshold) {
            anomalies.push("REPEATED_FAILED_AUTHENTICATION");
            score += 0.40;
        }

        const ipAddresses = new Set(
            relevant
                .filter(item =>
                    item.type === EventType.LOGIN_SUCCESS ||
                    item.type === EventType.LOGIN_FAILURE
                )
                .map(item => item.sourceIP)
        );

        if (ipAddresses.size >= 3) {
            anomalies.push("MULTIPLE_SOURCE_IP_ADDRESSES");
            score += 0.25;
        }

        if (
            event.type === EventType.ACCESS_DENIED &&
            [
                "/admin",
                "/database",
                "/credentials",
                "/financial-records",
                "/security-configuration"
            ].includes(event.resource)
        ) {
            anomalies.push("SENSITIVE_RESOURCE_ACCESS_DENIED");
            score += 0.30;
        }

        if (event.type === EventType.PRIVILEGE_CHANGE) {
            anomalies.push("PRIVILEGE_CHANGE");
            score += 0.50;
        }

        if (
            event.type === EventType.DATA_EXPORT &&
            event.details.recordCount > this.exportThreshold
        ) {
            anomalies.push("UNUSUAL_DATA_EXPORT");
            score += 0.45;
        }

        if (
            (this.userEventCounts.get(event.userId) ?? 0) >
            this.frequencyThreshold
        ) {
            anomalies.push("HIGH_EVENT_FREQUENCY");
            score += 0.30;
        }

        score = Math.min(score, 1);

        const severity =
            score >= 0.75 ? Severity.CRITICAL :
            score >= 0.50 ? Severity.HIGH :
            score >= 0.25 ? Severity.MEDIUM :
            Severity.LOW;

        return {
            eventId: event.id,
            score: Number(score.toFixed(3)),
            anomalies,
            severity
        };
    }
}

// ============================================================
// ALERT MANAGEMENT
// ============================================================

class AlertManager {

    constructor() {
        this.alerts = new Map();
    }

    create(detection, event) {

        if (detection.anomalies.length === 0) {
            return null;
        }

        const alert = Object.freeze({
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            userId: event.userId,
            severity: detection.severity,
            score: detection.score,
            category: detection.anomalies,
            evidence: [event.id],
            status: AlertStatus.OPEN,
            assignedTo: null
        });

        this.alerts.set(alert.id, alert);

        return alert;
    }

    update(alertId, status, analyst = null) {

        const alert = this.alerts.get(alertId);

        if (!alert) {
            throw new Error("Alert not found");
        }

        if (TERMINAL_STATUSES.has(alert.status)) {
            throw new Error("Alert is already closed");
        }

        if (!Object.values(AlertStatus).includes(status)) {
            throw new Error("Invalid alert status");
        }

        if (
            status === AlertStatus.INVESTIGATING &&
            !analyst
        ) {
            throw new Error("An analyst must be assigned");
        }

        const updated = Object.freeze({
            ...alert,
            status,
            assignedTo: analyst ?? alert.assignedTo
        });

        this.alerts.set(alertId, updated);

        return updated;
    }

    getSummary() {

        const summary = {
            total: this.alerts.size,
            open: 0,
            investigating: 0,
            resolved: 0,
            falsePositive: 0,
            severity: {}
        };

        for (const alert of this.alerts.values()) {

            if (alert.status === AlertStatus.OPEN) {
                summary.open++;
            }

            if (alert.status === AlertStatus.INVESTIGATING) {
                summary.investigating++;
            }

            if (alert.status === AlertStatus.RESOLVED) {
                summary.resolved++;
            }

            if (alert.status === AlertStatus.FALSE_POSITIVE) {
                summary.falsePositive++;
            }

            summary.severity[alert.severity] =
                (summary.severity[alert.severity] ?? 0) + 1;
        }

        return summary;
    }
}

// ============================================================
// EVENT-DRIVEN MONITORING SERVICE
// ============================================================

class SecurityMonitor extends EventEmitter {

    constructor() {
        super();

        this.audit = new AuditLog();
        this.access = new AccessPolicy();
        this.detector = new AnomalyDetector();
        this.alertManager = new AlertManager();

        this.processing = Promise.resolve();
        this.statistics = new Map();
    }

    ingest(input) {

        // Serialize ingestion to preserve audit ordering and
        // deterministic sliding-window behavior.
        const operation = this.processing.then(
            () => this.process(input)
        );

        this.processing = operation.catch(() => {});

        return operation;
    }

    async process(input) {

        const event = validateEvent(input);

        if (event.type === EventType.ACCESS_GRANTED) {

            if (!this.access.authorize(
                event.userId,
                event.resource
            )) {
                throw new Error(
                    "Unauthorized access recorded as granted"
                );
            }
        }

        const record = this.audit.append(event);

        this.statistics.set(
            event.type,
            (this.statistics.get(event.type) ?? 0) + 1
        );

        const detection = this.detector.analyze(event);

        this.emit("audit", record);

        if (detection.anomalies.length === 0) {
            return {
                event,
                alert: null,
                detection
            };
        }

        const alert = this.alertManager.create(
            detection,
            event
        );

        this.emit("security-alert", alert);

        return {
            event,
            alert,
            detection
        };
    }

    async flush() {
        await this.processing;
    }

    report() {

        return {
            events: this.audit.records.length,
            auditIntegrity: this.audit.verify(),
            eventDistribution: Object.fromEntries(this.statistics),
            alerts: this.alertManager.getSummary()
        };
    }
}

// ============================================================
// STATISTICAL ANOMALY DETECTION
// ============================================================

function statisticalAnomalies(values, threshold = 2) {

    if (
        !Array.isArray(values) ||
        values.length < 2 ||
        !Number.isFinite(threshold) ||
        threshold <= 0 ||
        values.some(value => !Number.isFinite(value))
    ) {
        throw new TypeError("Invalid statistical input");
    }

    const mean = values.reduce(
        (sum, value) => sum + value,
        0
    ) / values.length;

    const variance = values.reduce(
        (sum, value) => sum + (value - mean) ** 2,
        0
    ) / values.length;

    const deviation = Math.sqrt(variance);

    if (deviation === 0) {
        return [];
    }

    return values
        .map((value, index) => ({
            index,
            zScore: (value - mean) / deviation
        }))
        .filter(item => Math.abs(item.zScore) > threshold);
}

// ============================================================
// SAMPLE DATA
// ============================================================

function createSamples() {

    const base = Date.now();

    const events = [];

    events.push({
        type: EventType.LOGIN_SUCCESS,
        userId: "alice",
        sourceIP: "192.168.1.10",
        resource: "/authentication",
        success: true,
        timestamp: base
    });

    events.push({
        type: EventType.ACCESS_GRANTED,
        userId: "alice",
        sourceIP: "192.168.1.10",
        resource: "/application",
        success: true,
        timestamp: base + 5000
    });

    for (let index = 0; index < 6; index++) {
        events.push({
            type: EventType.LOGIN_FAILURE,
            userId: "david",
            sourceIP: "203.0.113.50",
            resource: "/authentication",
            success: false,
            details: { attempt: index + 1 },
            timestamp: base + 60000 + index * 1000
        });
    }

    events.push({
        type: EventType.ACCESS_DENIED,
        userId: "alice",
        sourceIP: "192.168.1.10",
        resource: "/credentials",
        success: false,
        timestamp: base + 120000
    });

    events.push({
        type: EventType.PRIVILEGE_CHANGE,
        userId: "bob",
        sourceIP: "192.168.1.20",
        resource: "/admin",
        success: true,
        details: {
            targetUser: "alice",
            newRole: "administrator"
        },
        timestamp: base + 180000
    });

    events.push({
        type: EventType.DATA_EXPORT,
        userId: "david",
        sourceIP: "203.0.113.50",
        resource: "/financial-records",
        success: true,
        details: { recordCount: 5000 },
        timestamp: base + 240000
    });

    return events;
}

// ============================================================
// TESTS
// ============================================================

async function runTests() {

    const monitor = new SecurityMonitor();

    const alertEvents = [];

    monitor.on("security-alert", alert => {
        alertEvents.push(alert);
    });

    const samples = createSamples();

    for (const event of samples) {
        await monitor.ingest(event);
    }

    await monitor.flush();

    if (monitor.audit.records.length !== samples.length) {
        throw new Error("Audit count test failed");
    }

    if (!monitor.audit.verify()) {
        throw new Error("Audit integrity test failed");
    }

    if (alertEvents.length < 3) {
        throw new Error("Alert generation test failed");
    }

    if (!monitor.access.authorize("alice", "/application")) {
        throw new Error("Authorization test failed");
    }

    if (monitor.access.authorize("alice", "/credentials")) {
        throw new Error("Unauthorized access test failed");
    }

    if (
        statisticalAnomalies([10, 10, 10, 100], 1.5).length !== 1
    ) {
        throw new Error("Statistical detection test failed");
    }

    const firstAlert = alertEvents[0];

    monitor.alertManager.update(
        firstAlert.id,
        AlertStatus.INVESTIGATING,
        "security-analyst-01"
    );

    let duplicateRejected = false;

    try {
        await monitor.ingest(samples[0]);
    } catch {
        duplicateRejected = true;
    }

    if (!duplicateRejected) {
        throw new Error("Duplicate event test failed");
    }

    console.log("All JavaScript security tests passed.");
}

// ============================================================
// MAIN
// ============================================================

async function main() {

    const monitor = new SecurityMonitor();

    monitor.on("security-alert", alert => {
        console.log(
            `[${alert.severity}]`,
            alert.category.join(", "),
            `User: ${alert.userId}`
        );
    });

    monitor.on("audit", record => {
        console.log(
            `AUDIT ${record.event.type} ${record.event.userId}`
        );
    });

    for (const event of createSamples()) {
        await monitor.ingest(event);
    }

    await monitor.flush();

    console.log("\nSECURITY REPORT");

    console.log(
        JSON.stringify(monitor.report(), null, 2)
    );

    console.log("\nSTATISTICAL ANOMALIES");

    console.log(
        statisticalAnomalies(
            [12, 13, 11, 12, 14, 13, 90]
        )
    );

    await runTests();

    // The audit file is created with exclusive creation.
    // Existing files are not silently overwritten.
    const output = path.join(
        process.cwd(),
        "security-audit.jsonl"
    );

    try {
        await monitor.audit.exportJSONL(output);
        console.log(`Audit exported to ${output}`);
    } catch (error) {
        if (error.code === "EEXIST") {
            console.log(
                "Audit export skipped: destination already exists."
            );
        } else {
            throw error;
        }
    }
}

if (require.main === module) {
    main().catch(error => {
        console.error("Monitoring failure:", error.message);
        process.exitCode = 1;
    });
}

module.exports = {
    EventType,
    Severity,
    AlertStatus,
    AuditLog,
    AccessPolicy,
    AnomalyDetector,
    AlertManager,
    SecurityMonitor,
    statisticalAnomalies,
    validateEvent
};
