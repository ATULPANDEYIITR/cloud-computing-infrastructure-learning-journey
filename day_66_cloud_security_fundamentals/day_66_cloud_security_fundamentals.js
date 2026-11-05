"use strict";

/*
 * Cloud Security Fundamentals
 *
 * Event-driven cloud security assessment system.
 *
 * Features:
 * - Provider-specific shared responsibility
 * - Asset discovery
 * - Attack surface classification
 * - Asynchronous security checks
 * - IAM and network policy evaluation
 * - Threat detection
 * - Risk prioritization
 * - Security event notifications
 * - JSON reporting
 *
 * Runtime: Node.js 18+
 */

const { EventEmitter } = require("node:events");
const fs = require("node:fs/promises");
const crypto = require("node:crypto");

const Provider = Object.freeze({
    AWS: "AWS",
    AZURE: "AZURE",
    GCP: "GCP"
});

const AssetType = Object.freeze({
    COMPUTE: "COMPUTE",
    STORAGE: "STORAGE",
    DATABASE: "DATABASE",
    IDENTITY: "IDENTITY",
    NETWORK: "NETWORK",
    SERVERLESS: "SERVERLESS"
});

const Severity = Object.freeze({
    CRITICAL: 4,
    HIGH: 3,
    MEDIUM: 2,
    LOW: 1
});

const Rules = Object.freeze({
    PUBLIC_STORAGE: {
        severity: "CRITICAL",
        score: 40,
        remediation: "Disable public access and restrict storage policies."
    },
    PUBLIC_DATABASE: {
        severity: "CRITICAL",
        score: 40,
        remediation: "Remove public database endpoints and use private networking."
    },
    EXCESSIVE_IAM: {
        severity: "HIGH",
        score: 25,
        remediation: "Remove wildcard permissions and implement least privilege."
    },
    NO_MFA: {
        severity: "HIGH",
        score: 25,
        remediation: "Require MFA for privileged identities."
    },
    NO_ENCRYPTION: {
        severity: "CRITICAL",
        score: 35,
        remediation: "Enable encryption at rest."
    },
    NO_TLS: {
        severity: "HIGH",
        score: 25,
        remediation: "Require TLS for data in transit."
    },
    NO_LOGGING: {
        severity: "HIGH",
        score: 20,
        remediation: "Enable protected centralized audit logging."
    },
    OPEN_NETWORK: {
        severity: "HIGH",
        score: 20,
        remediation: "Restrict inbound and outbound network traffic."
    },
    NO_BACKUP: {
        severity: "MEDIUM",
        score: 15,
        remediation: "Configure encrypted backups and recovery testing."
    }
});

class SecurityError extends Error {
    constructor(message) {
        super(message);
        this.name = "SecurityError";
    }
}

class CloudAsset {
    constructor({
        id,
        name,
        provider,
        type,
        region,
        publicAccess = false,
        encryptedAtRest = true,
        tlsRequired = true,
        logging = true,
        mfa = true,
        leastPrivilege = true,
        restrictedNetwork = true,
        backup = true,
        sensitive = false,
        active = true,
        permissions = []
    }) {
        this.id = id;
        this.name = name;
        this.provider = provider;
        this.type = type;
        this.region = region;
        this.publicAccess = publicAccess;
        this.encryptedAtRest = encryptedAtRest;
        this.tlsRequired = tlsRequired;
        this.logging = logging;
        this.mfa = mfa;
        this.leastPrivilege = leastPrivilege;
        this.restrictedNetwork = restrictedNetwork;
        this.backup = backup;
        this.sensitive = sensitive;
        this.active = active;
        this.permissions = permissions;

        this.validate();
    }

    validate() {
        if (
            typeof this.id !== "string" ||
            !this.id.trim() ||
            typeof this.name !== "string" ||
            !this.name.trim() ||
            typeof this.region !== "string" ||
            !this.region.trim()
        ) {
            throw new SecurityError("Asset identity and region are required.");
        }

        if (!Object.values(Provider).includes(this.provider)) {
            throw new SecurityError("Unsupported cloud provider.");
        }

        if (!Object.values(AssetType).includes(this.type)) {
            throw new SecurityError("Unsupported asset type.");
        }

        if (!Array.isArray(this.permissions)) {
            throw new SecurityError("Permissions must be an array.");
        }

        if (
            this.permissions.some(
                permission =>
                    typeof permission !== "string" ||
                    !permission.trim()
            )
        ) {
            throw new SecurityError("Invalid IAM permission.");
        }
    }
}

class ResponsibilityEngine {
    constructor() {
        this.controls = new Map([
            ["physical_infrastructure", "PROVIDER"],
            ["hypervisor", "PROVIDER"],
            ["physical_network", "PROVIDER"],
            ["guest_os", "CUSTOMER"],
            ["application_code", "CUSTOMER"],
            ["data", "CUSTOMER"],
            ["identity_access", "CUSTOMER"],
            ["network_configuration", "CUSTOMER"],
            ["managed_runtime", "SHARED"],
            ["security_monitoring", "SHARED"],
            ["incident_response", "SHARED"]
        ]);
    }

    getOwner(control) {
        if (!this.controls.has(control)) {
            throw new SecurityError(`Unknown control: ${control}`);
        }

        return this.controls.get(control);
    }

    evaluateServiceModel(model) {
        const models = {
            IAAS: [
                "physical_infrastructure",
                "hypervisor"
            ],
            PAAS: [
                "physical_infrastructure",
                "hypervisor",
                "managed_runtime"
            ],
            SAAS: [
                "physical_infrastructure",
                "hypervisor",
                "managed_runtime"
            ]
        };

        if (!models[model]) {
            throw new SecurityError("Unknown service model.");
        }

        return {
            serviceModel: model,
            customerResponsibilities: [
                "data",
                "identity_access",
                "network_configuration"
            ],
            providerManagedControls: models[model],
            sharedControls: ["security_monitoring", "incident_response"]
        };
    }
}

class SecurityEventBus extends EventEmitter {
    publish(finding) {
        this.emit("security:finding", Object.freeze({ ...finding }));
    }
}

class CloudSecurityEngine {
    constructor({ concurrency = 4 } = {}) {
        if (!Number.isInteger(concurrency) || concurrency < 1) {
            throw new SecurityError("Concurrency must be positive.");
        }

        this.assets = new Map();
        this.findings = [];
        this.concurrency = concurrency;
        this.events = new SecurityEventBus();
        this.scanId = crypto.randomUUID();
    }

    registerAsset(asset) {
        if (!(asset instanceof CloudAsset)) {
            throw new SecurityError("Invalid asset object.");
        }

        if (this.assets.has(asset.id)) {
            throw new SecurityError(`Duplicate asset: ${asset.id}`);
        }

        this.assets.set(asset.id, asset);
    }

    discoverAttackSurface() {
        const surface = {
            internetExposed: [],
            identitySensitive: [],
            dataSensitive: [],
            networkBoundaries: [],
            inactive: []
        };

        for (const asset of this.assets.values()) {
            if (!asset.active) {
                surface.inactive.push(asset.id);
                continue;
            }

            if (asset.publicAccess) {
                surface.internetExposed.push(asset.id);
            }

            if (asset.type === AssetType.IDENTITY) {
                surface.identitySensitive.push(asset.id);
            }

            if (asset.sensitive) {
                surface.dataSensitive.push(asset.id);
            }

            if (asset.type === AssetType.NETWORK) {
                surface.networkBoundaries.push(asset.id);
            }
        }

        return surface;
    }

    async checkAsset(asset) {
        // Simulates an asynchronous provider inventory inspection.
        await Promise.resolve();

        const checks = [];

        const add = (ruleId, description) => {
            const rule = Rules[ruleId];

            checks.push({
                id: crypto.randomUUID(),
                assetId: asset.id,
                provider: asset.provider,
                ruleId,
                description,
                severity: rule.severity,
                riskScore: rule.score,
                remediation: rule.remediation,
                detectedAt: new Date().toISOString()
            });
        };

        if (asset.publicAccess && asset.type === AssetType.STORAGE) {
            add("PUBLIC_STORAGE", "Storage is publicly accessible.");
        }

        if (asset.publicAccess && asset.type === AssetType.DATABASE) {
            add("PUBLIC_DATABASE", "Database has public network exposure.");
        }

        if (asset.sensitive && !asset.encryptedAtRest) {
            add("NO_ENCRYPTION", "Sensitive data lacks encryption at rest.");
        }

        if (!asset.tlsRequired) {
            add("NO_TLS", "Secure transport is not enforced.");
        }

        if (!asset.leastPrivilege || asset.permissions.includes("*")) {
            add("EXCESSIVE_IAM", "IAM policy violates least privilege.");
        }

        if (!asset.mfa) {
            add("NO_MFA", "Multi-factor authentication is disabled.");
        }

        if (!asset.logging) {
            add("NO_LOGGING", "Audit logging is disabled.");
        }

        if (!asset.restrictedNetwork) {
            add("OPEN_NETWORK", "Network restrictions are insufficient.");
        }

        if (!asset.backup) {
            add("NO_BACKUP", "Backup protection is disabled.");
        }

        return checks;
    }

    async scan() {
        const activeAssets = [...this.assets.values()]
            .filter(asset => asset.active);

        const results = [];

        // Bounded concurrency prevents excessive simultaneous API requests.
        for (
            let offset = 0;
            offset < activeAssets.length;
            offset += this.concurrency
        ) {
            const batch = activeAssets.slice(
                offset,
                offset + this.concurrency
            );

            const batchResults = await Promise.all(
                batch.map(asset => this.checkAsset(asset))
            );

            results.push(...batchResults.flat());
        }

        results.sort((a, b) => b.riskScore - a.riskScore);

        this.findings = results;

        for (const finding of results) {
            this.events.publish(finding);
        }

        return results;
    }

    generateReport() {
        const distribution = Object.fromEntries(
            Object.keys(Severity).map(severity => [severity, 0])
        );

        for (const finding of this.findings) {
            distribution[finding.severity]++;
        }

        return {
            scanId: this.scanId,
            generatedAt: new Date().toISOString(),
            assetCount: this.assets.size,
            findingCount: this.findings.length,
            severityDistribution: distribution,
            attackSurface: this.discoverAttackSurface(),
            findings: this.findings
        };
    }

    async saveReport(filename) {
        const report = this.generateReport();

        await fs.writeFile(
            filename,
            JSON.stringify(report, null, 2),
            {
                encoding: "utf8",
                mode: 0o600
            }
        );

        return filename;
    }
}

async function runTests() {
    const engine = new CloudSecurityEngine({ concurrency: 2 });

    const storage = new CloudAsset({
        id: "AWS-S3-001",
        name: "Customer Documents",
        provider: Provider.AWS,
        type: AssetType.STORAGE,
        region: "ap-south-1",
        publicAccess: true,
        encryptedAtRest: false,
        sensitive: true,
        permissions: ["*"],
        mfa: false,
        logging: false
    });

    engine.registerAsset(storage);

    let eventCount = 0;

    engine.events.on("security:finding", () => {
        eventCount++;
    });

    const findings = await engine.scan();

    if (findings.length !== 5) {
        throw new Error("Security rule evaluation failed.");
    }

    if (eventCount !== findings.length) {
        throw new Error("Security event delivery failed.");
    }

    if (findings[0].severity !== "CRITICAL") {
        throw new Error("Risk prioritization failed.");
    }

    try {
        engine.registerAsset(storage);
        throw new Error("Duplicate asset was accepted.");
    } catch (error) {
        if (!(error instanceof SecurityError)) {
            throw error;
        }
    }

    const responsibility = new ResponsibilityEngine();

    if (responsibility.getOwner("data") !== "CUSTOMER") {
        throw new Error("Responsibility evaluation failed.");
    }

    console.log("All JavaScript security tests passed.");
}

async function main() {
    const engine = new CloudSecurityEngine({ concurrency: 3 });

    engine.events.on("security:finding", finding => {
        console.log(
            `[${finding.severity}] ${finding.ruleId}: ${finding.assetId}`
        );
    });

    const assets = [
        new CloudAsset({
            id: "AWS-S3-001",
            name: "Customer Storage",
            provider: Provider.AWS,
            type: AssetType.STORAGE,
            region: "ap-south-1",
            publicAccess: true,
            encryptedAtRest: false,
            sensitive: true,
            permissions: ["*"],
            logging: false
        }),

        new CloudAsset({
            id: "AZURE-VM-001",
            name: "Application VM",
            provider: Provider.AZURE,
            type: AssetType.COMPUTE,
            region: "centralindia",
            mfa: false,
            restrictedNetwork: false,
            backup: false
        }),

        new CloudAsset({
            id: "GCP-DB-001",
            name: "Production Database",
            provider: Provider.GCP,
            type: AssetType.DATABASE,
            region: "asia-south1",
            publicAccess: true,
            sensitive: true,
            encryptedAtRest: true
        })
    ];

    for (const asset of assets) {
        engine.registerAsset(asset);
    }

    const responsibility = new ResponsibilityEngine();

    console.log("\nSERVICE MODEL:");
    console.log(
        JSON.stringify(
            responsibility.evaluateServiceModel("IAAS"),
            null,
            2
        )
    );

    console.log("\nATTACK SURFACE:");
    console.log(
        JSON.stringify(engine.discoverAttackSurface(), null, 2)
    );

    console.log("\nSECURITY SCAN:");

    await engine.scan();

    console.log("\nREPORT:");
    console.log(JSON.stringify(engine.generateReport(), null, 2));

    await engine.saveReport("cloud_security_report.json");

    console.log("\nReport saved successfully.");

    await runTests();
}

main().catch(error => {
    console.error("Cloud security assessment failed:", error.message);
    process.exitCode = 1;
});
