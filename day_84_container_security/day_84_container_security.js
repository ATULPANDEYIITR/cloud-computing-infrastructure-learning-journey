'use strict';

/*
 * Container Security Policy Engine
 *
 * Node.js 18+
 *
 * Engineering perspective:
 * - Asynchronous image assessment
 * - Event-driven runtime monitoring
 * - Concurrent vulnerability evaluation
 * - Image provenance validation
 * - Secret exposure detection
 * - Deployment admission control
 * - Immutable policy configuration
 */

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const EventEmitter = require('node:events');

const Severity = Object.freeze({
    CRITICAL: 5,
    HIGH: 4,
    MEDIUM: 3,
    LOW: 2,
    UNKNOWN: 1
});

const Decision = Object.freeze({
    ALLOW: 'ALLOW',
    DENY: 'DENY',
    REVIEW: 'REVIEW'
});

class SecurityError extends Error {
    constructor(message, code = 'SECURITY_VIOLATION') {
        super(message);
        this.name = 'SecurityError';
        this.code = code;
    }
}

class ImageManifest {
    constructor(data) {
        this.name = data.name;
        this.tag = data.tag;
        this.digest = data.digest;
        this.baseImage = data.baseImage;
        this.packages = Object.freeze([...data.packages]);
        this.vulnerabilities = Object.freeze(
            data.vulnerabilities.map(v => Object.freeze({ ...v }))
        );
        this.userId = data.userId;
        this.sizeMB = data.sizeMB;
        this.privileged = Boolean(data.privileged);
        this.containsShell = Boolean(data.containsShell);
        this.secrets = Object.freeze([...(data.secrets || [])]);
        this.signatureVerified = Boolean(data.signatureVerified);

        this.validate();
        Object.freeze(this);
    }

    validate() {
        if (!this.name || !this.tag) {
            throw new SecurityError('Image name and tag are required');
        }

        if (!/^sha256:[a-f0-9]{64}$/.test(this.digest)) {
            throw new SecurityError('Invalid image digest');
        }

        if (!Number.isInteger(this.userId) || this.userId < 0) {
            throw new SecurityError('Invalid container user ID');
        }

        if (!Number.isFinite(this.sizeMB) || this.sizeMB <= 0) {
            throw new SecurityError('Invalid image size');
        }

        for (const vulnerability of this.vulnerabilities) {
            if (!/^CVE-\d{4}-\d{4,}$/.test(vulnerability.cveId)) {
                throw new SecurityError('Invalid CVE identifier');
            }

            if (!(vulnerability.severity in Severity)) {
                throw new SecurityError('Invalid vulnerability severity');
            }
        }
    }
}

class SecurityPolicy {
    constructor(options = {}) {
        this.maxCritical = options.maxCritical ?? 0;
        this.maxHigh = options.maxHigh ?? 0;
        this.maxMedium = options.maxMedium ?? 5;
        this.maxImageSizeMB = options.maxImageSizeMB ?? 200;

        this.requireNonRoot = options.requireNonRoot ?? true;
        this.forbidPrivileged = options.forbidPrivileged ?? true;
        this.forbidShell = options.forbidShell ?? false;
        this.requireSignature = options.requireSignature ?? true;
        this.requireNoSecrets = options.requireNoSecrets ?? true;
        this.requireFixedVulnerabilities =
            options.requireFixedVulnerabilities ?? false;

        for (const value of [
            this.maxCritical,
            this.maxHigh,
            this.maxMedium
        ]) {
            if (!Number.isInteger(value) || value < 0) {
                throw new SecurityError('Invalid vulnerability threshold');
            }
        }

        Object.freeze(this);
    }
}

class VulnerabilityScanner {
    constructor(policy) {
        this.policy = policy;
    }

    async scan(image) {
        const findings = [];

        const counts = Object.fromEntries(
            Object.keys(Severity).map(key => [key, 0])
        );

        // Parallel analysis keeps independent CVE checks from blocking each other.
        const vulnerabilityFindings = await Promise.all(
            image.vulnerabilities.map(async vulnerability => {
                counts[vulnerability.severity]++;

                const result = {
                    control: 'CVE',
                    severity: vulnerability.severity,
                    cveId: vulnerability.cveId,
                    package: vulnerability.package,
                    fixedVersion: vulnerability.fixedVersion || null
                };

                if (
                    this.policy.requireFixedVulnerabilities &&
                    !vulnerability.fixedVersion
                ) {
                    result.unfixed = true;
                }

                return result;
            })
        );

        findings.push(...vulnerabilityFindings);

        const add = (control, severity, message) => {
            findings.push({ control, severity, message });
        };

        if (this.policy.requireNonRoot && image.userId === 0) {
            add(
                'NON_ROOT',
                'HIGH',
                'Container runs as root'
            );
        }

        if (this.policy.forbidPrivileged && image.privileged) {
            add(
                'PRIVILEGED',
                'CRITICAL',
                'Privileged container execution detected'
            );
        }

        if (this.policy.forbidShell && image.containsShell) {
            add(
                'MINIMAL_IMAGE',
                'MEDIUM',
                'Shell found in runtime image'
            );
        }

        if (image.sizeMB > this.policy.maxImageSizeMB) {
            add(
                'IMAGE_SIZE',
                'MEDIUM',
                'Image exceeds permitted size'
            );
        }

        if (this.policy.requireSignature && !image.signatureVerified) {
            add(
                'PROVENANCE',
                'HIGH',
                'Image signature verification failed'
            );
        }

        if (this.policy.requireNoSecrets && image.secrets.length > 0) {
            add(
                'SECRET_EXPOSURE',
                'CRITICAL',
                'Potential embedded credentials detected'
            );
        }

        for (const vulnerability of image.vulnerabilities) {
            if (
                vulnerability.severity === 'UNKNOWN' &&
                vulnerability.blockUnknown !== false
            ) {
                add(
                    'UNKNOWN_SEVERITY',
                    'HIGH',
                    `Unclassified vulnerability: ${vulnerability.cveId}`
                );
            }

            if (
                this.policy.requireFixedVulnerabilities &&
                !vulnerability.fixedVersion
            ) {
                add(
                    'UNFIXED_CVE',
                    vulnerability.severity,
                    `No fix available for ${vulnerability.cveId}`
                );
            }
        }

        const limits = {
            CRITICAL: this.policy.maxCritical,
            HIGH: this.policy.maxHigh,
            MEDIUM: this.policy.maxMedium
        };

        for (const [severity, maximum] of Object.entries(limits)) {
            if (counts[severity] > maximum) {
                add(
                    'CVE_THRESHOLD',
                    severity,
                    `${counts[severity]} ${severity} vulnerabilities; maximum ${maximum}`
                );
            }
        }

        const denyControls = new Set([
            'NON_ROOT',
            'PRIVILEGED',
            'PROVENANCE',
            'SECRET_EXPOSURE',
            'UNKNOWN_SEVERITY',
            'UNFIXED_CVE'
        ]);

        const denied = findings.some(finding =>
            denyControls.has(finding.control) ||
            (
                finding.control === 'CVE_THRESHOLD' &&
                ['CRITICAL', 'HIGH'].includes(finding.severity)
            )
        );

        const decision = denied
            ? Decision.DENY
            : findings.length
                ? Decision.REVIEW
                : Decision.ALLOW;

        return Object.freeze({
            image: `${image.name}:${image.tag}`,
            digest: image.digest,
            timestamp: new Date().toISOString(),
            counts: Object.freeze({ ...counts }),
            findings: Object.freeze(findings),
            decision
        });
    }
}

class RuntimeSecurityMonitor extends EventEmitter {
    constructor() {
        super();

        this.events = [];
        this.blockedProcesses = new Set([
            'nc',
            'ncat',
            'socat',
            'tcpdump'
        ]);
    }

    observe(event) {
        if (
            !event.containerId ||
            !event.process ||
            !Number.isInteger(event.userId)
        ) {
            throw new SecurityError('Malformed runtime event');
        }

        const processName = path.basename(event.process).toLowerCase();

        let decision = Decision.ALLOW;

        if (
            event.userId === 0 ||
            event.type === 'PRIVILEGED_PROCESS' ||
            event.type === 'SHELL_EXECUTION' ||
            this.blockedProcesses.has(processName)
        ) {
            decision = Decision.DENY;
        } else if (
            event.type === 'SECRET_ACCESS' ||
            event.type === 'FILESYSTEM_WRITE'
        ) {
            decision = Decision.REVIEW;
        }

        const record = Object.freeze({
            ...event,
            timestamp: new Date().toISOString(),
            decision
        });

        this.events.push(record);
        this.emit('security-event', record);

        return record;
    }

    statistics() {
        const result = {};

        for (const event of this.events) {
            result[event.type] = (result[event.type] || 0) + 1;
        }

        return result;
    }
}

class SecretDetector {
    constructor() {
        this.patterns = new Map([
            [
                'AWS_ACCESS_KEY',
                /\bAKIA[0-9A-Z]{16}\b/
            ],
            [
                'PRIVATE_KEY',
                /-----BEGIN (?:RSA |EC )?PRIVATE KEY-----/
            ],
            [
                'GITHUB_TOKEN',
                /\bgh[pousr]_[A-Za-z0-9]{30,}\b/
            ],
            [
                'PASSWORD',
                /(?:password|passwd|secret)\s*[:=]\s*['"]?[^'"\s]{8,}/i
            ]
        ]);
    }

    inspect(content) {
        if (typeof content !== 'string') {
            throw new SecurityError('Content must be a string');
        }

        const findings = [];

        for (const [name, pattern] of this.patterns) {
            if (pattern.test(content)) {
                findings.push(name);
            }
        }

        return findings;
    }

    inspectEnvironment(environment) {
        const findings = [];

        for (const [key, value] of Object.entries(environment)) {
            if (
                /password|secret|token|private_key|api_key/i.test(key) &&
                typeof value === 'string' &&
                value.length > 0
            ) {
                findings.push(key);
            }
        }

        return findings;
    }
}

class AdmissionController {
    constructor(scanner) {
        this.scanner = scanner;
        this.auditLog = [];
        this.deployedDigests = new Set();
    }

    async evaluate(image) {
        const report = await this.scanner.scan(image);

        this.auditLog.push(report);

        if (report.decision !== Decision.ALLOW) {
            throw new SecurityError(
                `Deployment rejected for ${image.name}: ${report.decision}`,
                'ADMISSION_REJECTED'
            );
        }

        if (this.deployedDigests.has(image.digest)) {
            return {
                decision: Decision.ALLOW,
                message: 'Identical immutable image already deployed',
                report
            };
        }

        this.deployedDigests.add(image.digest);

        return {
            decision: Decision.ALLOW,
            message: 'Image passed admission policy',
            report
        };
    }

    async exportAudit(filename) {
        const temporary = `${filename}.tmp`;

        await fs.writeFile(
            temporary,
            JSON.stringify(this.auditLog, null, 2),
            { encoding: 'utf8', mode: 0o600 }
        );

        await fs.rename(temporary, filename);
    }
}

function createImage(overrides = {}) {
    return new ImageManifest({
        name: 'inventory-api',
        tag: '2.1.0',
        digest: `sha256:${'b'.repeat(64)}`,
        baseImage: 'distroless/nodejs',
        packages: ['nodejs-runtime', 'application'],
        vulnerabilities: [
            {
                cveId: 'CVE-2024-12345',
                package: 'example-library',
                severity: 'LOW',
                fixedVersion: '2.0.1'
            }
        ],
        userId: 10001,
        sizeMB: 55,
        privileged: false,
        containsShell: false,
        secrets: [],
        signatureVerified: true,
        ...overrides
    });
}

async function main() {
    const policy = new SecurityPolicy({
        maxCritical: 0,
        maxHigh: 0,
        maxMedium: 3,
        maxImageSizeMB: 100,
        requireNonRoot: true,
        forbidPrivileged: true,
        forbidShell: true,
        requireSignature: true,
        requireNoSecrets: true
    });

    const scanner = new VulnerabilityScanner(policy);
    const admission = new AdmissionController(scanner);

    console.log('\nIMAGE SECURITY ASSESSMENT');

    const image = createImage();
    const report = await scanner.scan(image);

    console.log(JSON.stringify(report, null, 2));

    console.log('\nDEPLOYMENT ADMISSION');

    console.log(await admission.evaluate(image));

    console.log('\nMALICIOUS IMAGE TEST');

    const malicious = createImage({
        name: 'untrusted-api',
        tag: 'latest',
        userId: 0,
        privileged: true,
        secrets: ['PRIVATE_KEY'],
        signatureVerified: false,
        vulnerabilities: [
            {
                cveId: 'CVE-2024-99999',
                package: 'unsafe-package',
                severity: 'CRITICAL',
                fixedVersion: null
            }
        ]
    });

    try {
        await admission.evaluate(malicious);
    } catch (error) {
        console.log(error.code, error.message);
    }

    console.log('\nRUNTIME MONITORING');

    const monitor = new RuntimeSecurityMonitor();

    monitor.on('security-event', event => {
        console.log(
            `EVENT ${event.type}: ${event.decision}`
        );
    });

    monitor.observe({
        containerId: 'container-100',
        type: 'PROCESS_EXECUTION',
        process: 'node',
        userId: 10001
    });

    monitor.observe({
        containerId: 'container-100',
        type: 'SHELL_EXECUTION',
        process: '/bin/sh',
        userId: 10001
    });

    monitor.observe({
        containerId: 'container-100',
        type: 'SECRET_ACCESS',
        process: 'node',
        userId: 10001
    });

    console.log('Statistics:', monitor.statistics());

    console.log('\nSECRET DETECTION');

    const detector = new SecretDetector();

    console.log(
        detector.inspect('password=ExampleSecret123456')
    );

    console.log(
        detector.inspectEnvironment({
            DATABASE_PASSWORD: 'example',
            PORT: '8080'
        })
    );

    console.log('\nVALIDATION');

    console.assert(report.decision === Decision.ALLOW);
    console.assert(
        (await scanner.scan(malicious)).decision === Decision.DENY
    );

    console.log('Security checks completed.');
}

main().catch(error => {
    console.error('Security engine failure:', error.message);
    process.exitCode = 1;
});
