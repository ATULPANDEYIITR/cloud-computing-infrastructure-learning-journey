"use strict";

/*
 * Cloud Governance and Compliance Engine
 *
 * Event-driven governance assessment for cloud resources.
 *
 * Features:
 * - Resource inventory
 * - Policy evaluation
 * - Data residency
 * - Regulatory control mapping
 * - Risk prioritization
 * - Asynchronous audit processing
 * - Remediation workflows
 * - Compliance reporting
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const EventEmitter = require("node:events");

// ============================================================
// ENUMERATIONS
// ============================================================

const ResourceType = Object.freeze({
    STORAGE: "STORAGE",
    DATABASE: "DATABASE",
    COMPUTE: "COMPUTE",
    NETWORK: "NETWORK"
});

const Classification = Object.freeze({
    PUBLIC: "PUBLIC",
    INTERNAL: "INTERNAL",
    CONFIDENTIAL: "CONFIDENTIAL",
    RESTRICTED: "RESTRICTED"
});

const Severity = Object.freeze({
    LOW: 1,
    MEDIUM: 2,
    HIGH: 3,
    CRITICAL: 4
});

const Status = Object.freeze({
    COMPLIANT: "COMPLIANT",
    NON_COMPLIANT: "NON_COMPLIANT",
    NOT_APPLICABLE: "NOT_APPLICABLE"
});

// ============================================================
// DOMAIN ERRORS
// ============================================================

class GovernanceError extends Error {}

class ValidationError extends GovernanceError {}

class NotFoundError extends GovernanceError {}

class AuthorizationError extends GovernanceError {}

// ============================================================
// VALIDATION
// ============================================================

function requireString(value, field) {
    if (
        typeof value !== "string" ||
        value.trim().length === 0
    ) {
        throw new ValidationError(
            `${field} must be a non-empty string.`
        );
    }
}

function requireBoolean(value, field) {
    if (typeof value !== "boolean") {
        throw new ValidationError(
            `${field} must be a boolean.`
        );
    }
}

// ============================================================
// CLOUD RESOURCE
// ============================================================

class CloudResource {

    constructor(data) {

        requireString(data.id, "Resource ID");
        requireString(data.name, "Resource name");
        requireString(data.owner, "Resource owner");
        requireString(data.region, "Resource region");
        requireString(data.provider, "Provider");

        if (!Object.values(ResourceType).includes(data.type)) {
            throw new ValidationError("Invalid resource type.");
        }

        if (
            !Object.values(Classification).includes(
                data.classification
            )
        ) {
            throw new ValidationError(
                "Invalid data classification."
            );
        }

        requireBoolean(data.encrypted, "encrypted");
        requireBoolean(data.publicAccess, "publicAccess");
        requireBoolean(data.backupEnabled, "backupEnabled");

        this.id = data.id;
        this.name = data.name;
        this.owner = data.owner;
        this.type = data.type;
        this.provider = data.provider;
        this.region = data.region;
        this.classification = data.classification;

        this.encrypted = data.encrypted;
        this.publicAccess = data.publicAccess;
        this.backupEnabled = data.backupEnabled;

        this.tags = Object.freeze({
            ...(data.tags || {})
        });

        this.createdAt = new Date().toISOString();
    }
}

// ============================================================
// GOVERNANCE POLICY
// ============================================================

class Policy {

    constructor({
        id,
        name,
        severity,
        encrypted = false,
        prohibitPublic = false,
        backup = false,
        allowedRegions = [],
        classifications = []
    }) {

        requireString(id, "Policy ID");
        requireString(name, "Policy name");

        if (!Object.values(Severity).includes(severity)) {
            throw new ValidationError(
                "Invalid policy severity."
            );
        }

        this.id = id;
        this.name = name;
        this.severity = severity;
        this.encrypted = encrypted;
        this.prohibitPublic = prohibitPublic;
        this.backup = backup;

        this.allowedRegions = new Set(allowedRegions);
        this.classifications = new Set(classifications);
    }

    appliesTo(resource) {
        return (
            this.classifications.size === 0 ||
            this.classifications.has(resource.classification)
        );
    }

    evaluate(resource) {

        if (!this.appliesTo(resource)) {
            return {
                policyId: this.id,
                status: Status.NOT_APPLICABLE,
                violations: []
            };
        }

        const violations = [];

        if (this.encrypted && !resource.encrypted) {
            violations.push("Encryption requirement failed.");
        }

        if (
            this.prohibitPublic &&
            resource.publicAccess
        ) {
            violations.push("Public access is prohibited.");
        }

        if (this.backup && !resource.backupEnabled) {
            violations.push("Backup requirement failed.");
        }

        if (
            this.allowedRegions.size > 0 &&
            !this.allowedRegions.has(resource.region)
        ) {
            violations.push(
                `Region ${resource.region} is not permitted.`
            );
        }

        return {
            policyId: this.id,
            policyName: this.name,
            severity: this.severity,
            status: violations.length
                ? Status.NON_COMPLIANT
                : Status.COMPLIANT,
            violations
        };
    }
}

// ============================================================
// AUDIT SERVICE
// ============================================================

class AuditService {

    constructor() {
        this.events = [];
        this.previousHash = "GENESIS";
    }

    async record(action, actor, resourceId, details) {

        requireString(actor, "Audit actor");

        const event = {
            id: crypto.randomUUID(),
            action,
            actor,
            resourceId,
            details,
            timestamp: new Date().toISOString(),
            previousHash: this.previousHash
        };

        const canonical = JSON.stringify(event);

        event.hash = crypto
            .createHash("sha256")
            .update(canonical)
            .digest("hex");

        this.previousHash = event.hash;
        this.events.push(Object.freeze(event));

        return event;
    }

    verify() {

        let previousHash = "GENESIS";

        for (const event of this.events) {

            if (event.previousHash !== previousHash) {
                return false;
            }

            const {
                hash,
                ...payload
            } = event;

            const calculated = crypto
                .createHash("sha256")
                .update(JSON.stringify(payload))
                .digest("hex");

            if (calculated !== hash) {
                return false;
            }

            previousHash = hash;
        }

        return true;
    }

    async export(filepath) {

        await fs.writeFile(
            filepath,
            JSON.stringify(this.events, null, 2),
            {
                encoding: "utf8",
                mode: 0o600
            }
        );
    }
}

// ============================================================
// DATA RESIDENCY SERVICE
// ============================================================

class ResidencyService {

    constructor(regulations) {
        this.regulations = new Map();

        for (const regulation of regulations) {

            requireString(regulation.id, "Regulation ID");

            if (
                !Array.isArray(regulation.regions) ||
                regulation.regions.length === 0
            ) {
                throw new ValidationError(
                    "A regulation needs permitted regions."
                );
            }

            this.regulations.set(
                regulation.id,
                new Set(regulation.regions)
            );
        }
    }

    evaluate(resource, regulationId) {

        const permitted = this.regulations.get(regulationId);

        if (!permitted) {
            throw new NotFoundError(
                `Unknown regulation: ${regulationId}`
            );
        }

        return {
            resourceId: resource.id,
            regulationId,
            region: resource.region,
            compliant: permitted.has(resource.region)
        };
    }
}

// ============================================================
// GOVERNANCE EVENT BUS
// ============================================================

class GovernanceEventBus extends EventEmitter {

    constructor() {
        super({
            captureRejections: true
        });

        this.on("error", error => {
            console.error("Event processing error:", error.message);
        });
    }

    async publish(event, payload) {

        // Await listeners so failures are visible to the caller.
        const listeners = this.listeners(event);

        for (const listener of listeners) {
            await listener(payload);
        }
    }
}

// ============================================================
// GOVERNANCE ENGINE
// ============================================================

class GovernanceEngine {

    constructor(policies, auditService, residencyService) {

        this.policies = policies;
        this.audit = auditService;
        this.residency = residencyService;

        this.resources = new Map();
        this.latestAssessments = new Map();

        this.events = new GovernanceEventBus();

        this.events.on(
            "violation",
            async event => {
                console.warn(
                    `[ALERT] ${event.resourceId}: ${event.policyId}`
                );
            }
        );
    }

    async register(resource, actor) {

        if (!(resource instanceof CloudResource)) {
            throw new ValidationError(
                "Expected a CloudResource instance."
            );
        }

        if (this.resources.has(resource.id)) {
            throw new ValidationError(
                "Duplicate resource ID."
            );
        }

        this.resources.set(resource.id, resource);

        await this.audit.record(
            "RESOURCE_REGISTERED",
            actor,
            resource.id,
            {
                name: resource.name,
                region: resource.region
            }
        );
    }

    getResource(id) {

        const resource = this.resources.get(id);

        if (!resource) {
            throw new NotFoundError(
                `Resource ${id} does not exist.`
            );
        }

        return resource;
    }

    async evaluate(id, actor) {

        const resource = this.getResource(id);

        const policyResults = this.policies.map(
            policy => policy.evaluate(resource)
        );

        const residencyResults = [
            ...this.residency.regulations.keys()
        ].map(regulationId =>
            this.residency.evaluate(resource, regulationId)
        );

        const violations = policyResults.filter(
            result => result.status === Status.NON_COMPLIANT
        );

        const residencyViolations = residencyResults.filter(
            result => !result.compliant
        );

        const assessment = {
            resourceId: id,
            evaluatedAt: new Date().toISOString(),
            policyResults,
            residencyResults,
            compliant:
                violations.length === 0 &&
                residencyViolations.length === 0
        };

        this.latestAssessments.set(id, assessment);

        await this.audit.record(
            "POLICY_EVALUATED",
            actor,
            id,
            {
                policyViolations: violations.length,
                residencyViolations: residencyViolations.length
            }
        );

        for (const violation of violations) {
            await this.audit.record(
                "VIOLATION_DETECTED",
                actor,
                id,
                violation
            );

            await this.events.publish(
                "violation",
                {
                    resourceId: id,
                    policyId: violation.policyId
                }
            );
        }

        return assessment;
    }

    async remediate(id, actor, actions) {

        if (actor !== "governance-admin") {
            throw new AuthorizationError(
                "Remediation requires governance-admin."
            );
        }

        const resource = this.getResource(id);

        const before = {
            encrypted: resource.encrypted,
            publicAccess: resource.publicAccess,
            backupEnabled: resource.backupEnabled
        };

        // Update a candidate state and validate before committing.
        const candidate = {
            ...before,
            ...actions
        };

        for (const key of [
            "encrypted",
            "publicAccess",
            "backupEnabled"
        ]) {
            if (typeof candidate[key] !== "boolean") {
                throw new ValidationError(
                    `Invalid remediation value: ${key}`
                );
            }
        }

        resource.encrypted = candidate.encrypted;
        resource.publicAccess = candidate.publicAccess;
        resource.backupEnabled = candidate.backupEnabled;

        try {
            await this.audit.record(
                "REMEDIATION_APPLIED",
                actor,
                id,
                {
                    before,
                    after: candidate
                }
            );
        } catch (error) {
            Object.assign(resource, before);
            throw error;
        }

        return resource;
    }

    report() {

        const assessments = [
            ...this.latestAssessments.values()
        ];

        const policyResults = assessments.flatMap(
            item => item.policyResults
        );

        const applicable = policyResults.filter(
            item => item.status !== Status.NOT_APPLICABLE
        );

        const compliant = applicable.filter(
            item => item.status === Status.COMPLIANT
        );

        const violations = applicable.filter(
            item => item.status === Status.NON_COMPLIANT
        );

        const residencyFailures = assessments.reduce(
            (total, item) =>
                total + item.residencyResults.filter(
                    result => !result.compliant
                ).length,
            0
        );

        return {
            resources: this.resources.size,
            assessedResources: assessments.length,
            policyEvaluations: policyResults.length,
            compliantPolicies: compliant.length,
            policyViolations: violations.length,
            residencyViolations: residencyFailures,
            complianceRate: applicable.length
                ? Number(
                    (
                        compliant.length /
                        applicable.length *
                        100
                    ).toFixed(2)
                )
                : 100
        };
    }
}

// ============================================================
// SAMPLE POLICY CONFIGURATION
// ============================================================

function createPolicies() {

    return [
        new Policy({
            id: "ENC-001",
            name: "Sensitive Data Encryption",
            severity: Severity.CRITICAL,
            encrypted: true,
            classifications: [
                Classification.CONFIDENTIAL,
                Classification.RESTRICTED
            ]
        }),

        new Policy({
            id: "PUB-001",
            name: "Prevent Public Exposure",
            severity: Severity.CRITICAL,
            prohibitPublic: true,
            classifications: [
                Classification.CONFIDENTIAL,
                Classification.RESTRICTED
            ]
        }),

        new Policy({
            id: "BKP-001",
            name: "Restricted Data Backup",
            severity: Severity.HIGH,
            backup: true,
            classifications: [
                Classification.RESTRICTED
            ]
        }),

        new Policy({
            id: "REG-001",
            name: "Approved Storage Regions",
            severity: Severity.CRITICAL,
            allowedRegions: [
                "ap-south-1",
                "ap-south-2"
            ],
            classifications: [
                Classification.RESTRICTED
            ]
        })
    ];
}

// ============================================================
// APPLICATION
// ============================================================

async function main() {

    const audit = new AuditService();

    const residency = new ResidencyService([
        {
            id: "ORG-RESIDENCY",
            regions: ["ap-south-1", "ap-south-2"]
        }
    ]);

    const engine = new GovernanceEngine(
        createPolicies(),
        audit,
        residency
    );

    const resources = [
        new CloudResource({
            id: "CLOUD-001",
            name: "Customer Database",
            owner: "data-team",
            provider: "AWS",
            type: ResourceType.DATABASE,
            region: "ap-south-1",
            classification: Classification.RESTRICTED,
            encrypted: false,
            publicAccess: true,
            backupEnabled: false
        }),

        new CloudResource({
            id: "CLOUD-002",
            name: "Application Compute",
            owner: "engineering-team",
            provider: "AWS",
            type: ResourceType.COMPUTE,
            region: "ap-south-1",
            classification: Classification.INTERNAL,
            encrypted: true,
            publicAccess: false,
            backupEnabled: true
        }),

        new CloudResource({
            id: "CLOUD-003",
            name: "Analytics Database",
            owner: "analytics-team",
            provider: "Azure",
            type: ResourceType.DATABASE,
            region: "centralindia",
            classification: Classification.RESTRICTED,
            encrypted: true,
            publicAccess: false,
            backupEnabled: true
        })
    ];

    for (const resource of resources) {
        await engine.register(
            resource,
            "governance-admin"
        );
    }

    console.log("\nCLOUD GOVERNANCE ASSESSMENT");
    console.log("===========================");

    for (const resource of resources) {

        const assessment = await engine.evaluate(
            resource.id,
            "compliance-service"
        );

        console.log(
            `\n${resource.name}:`,
            assessment.compliant
                ? "COMPLIANT"
                : "NON_COMPLIANT"
        );

        for (const result of assessment.policyResults) {
            if (result.status === Status.NON_COMPLIANT) {
                console.log(
                    result.policyId,
                    result.violations
                );
            }
        }

        for (const result of assessment.residencyResults) {
            console.log(
                result.regulationId,
                result.compliant
                    ? "RESIDENCY COMPLIANT"
                    : "RESIDENCY VIOLATION"
            );
        }
    }

    console.log("\nAUTHORIZED REMEDIATION");

    await engine.remediate(
        "CLOUD-001",
        "governance-admin",
        {
            encrypted: true,
            publicAccess: false,
            backupEnabled: true
        }
    );

    await engine.evaluate(
        "CLOUD-001",
        "compliance-service"
    );

    console.log("\nCOMPLIANCE REPORT");

    console.table(engine.report());

    console.log(
        "Audit integrity:",
        audit.verify()
    );

    if (!audit.verify()) {
        throw new GovernanceError(
            "Audit integrity verification failed."
        );
    }

    await audit.export("cloud_governance_audit.json");

    await fs.writeFile(
        "cloud_governance_report.json",
        JSON.stringify(engine.report(), null, 2),
        {
            encoding: "utf8",
            mode: 0o600
        }
    );

    // Negative test: unauthorized remediation.
    try {
        await engine.remediate(
            "CLOUD-002",
            "untrusted-user",
            { publicAccess: true }
        );
    } catch (error) {
        console.log(
            "Expected security rejection:",
            error.message
        );
    }

    console.log("\nGovernance execution completed.");
}

main().catch(error => {
    console.error("Fatal governance error:", error.message);
    process.exitCode = 1;
});
