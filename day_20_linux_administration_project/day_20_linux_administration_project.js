#!/usr/bin/env node
"use strict";

/*
 * Linux Administration Project
 *
 * This JavaScript implementation complements the Python laboratory by
 * concentrating on:
 *
 * - system command integration
 * - service inspection
 * - SSH configuration parsing
 * - permission interpretation
 * - structured log analysis
 * - configuration validation
 * - asynchronous file operations
 * - automation and idempotency
 *
 * It is intentionally non-destructive. It does not create users, modify
 * sshd_config, restart services, or change real system permissions.
 *
 * Run:
 *     node linux-admin-project.js
 */

const fs = require("fs");
const fsp = fs.promises;
const os = require("os");
const path = require("path");
const { execFile } = require("child_process");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);


// ---------------------------------------------------------------------------
// 1. Basic system information
// ---------------------------------------------------------------------------

function getSystemInformation() {
    return {
        hostname: os.hostname(),
        platform: process.platform,
        operatingSystem: `${os.type()} ${os.release()}`,
        architecture: os.arch(),
        nodeVersion: process.version,
        cpuCount: os.cpus().length,
        memoryGiB: (os.totalmem() / 1024 ** 3).toFixed(2),
        currentUser:
            process.env.USER ||
            process.env.USERNAME ||
            "unknown",
    };
}

function printSystemInformation() {
    console.log("\nSYSTEM INFORMATION");
    console.log("=".repeat(70));

    for (const [key, value] of Object.entries(getSystemInformation())) {
        console.log(`${key.padEnd(20)}: ${value}`);
    }
}


// ---------------------------------------------------------------------------
// 2. Command execution
// ---------------------------------------------------------------------------

async function runCommand(command, args = [], options = {}) {
    /*
     * execFile avoids invoking a shell by default. This is preferable to
     * constructing a single shell command string with untrusted input.
     */
    const started = process.hrtime.bigint();

    try {
        const result = await execFileAsync(command, args, {
            timeout: options.timeout ?? 10000,
            maxBuffer: options.maxBuffer ?? 1024 * 1024,
        });

        const elapsedMilliseconds =
            Number(process.hrtime.bigint() - started) / 1_000_000;

        return {
            command: [command, ...args].join(" "),
            success: true,
            code: 0,
            stdout: result.stdout.trim(),
            stderr: result.stderr.trim(),
            elapsedMilliseconds,
        };
    } catch (error) {
        const elapsedMilliseconds =
            Number(process.hrtime.bigint() - started) / 1_000_000;

        return {
            command: [command, ...args].join(" "),
            success: false,
            code: typeof error.code === "number" ? error.code : 1,
            stdout: (error.stdout || "").toString().trim(),
            stderr: (error.stderr || error.message || "").toString().trim(),
            elapsedMilliseconds,
        };
    }
}


// ---------------------------------------------------------------------------
// 3. Users and groups
// ---------------------------------------------------------------------------

async function readLinuxUsers() {
    /*
     * /etc/passwd contains account metadata in the traditional format:
     *
     * username:x:UID:GID:GECOS:home:shell
     *
     * It normally does not contain plaintext passwords.
     */
    const passwdPath = "/etc/passwd";

    try {
        const content = await fsp.readFile(passwdPath, "utf8");

        return content
            .split(/\r?\n/)
            .filter(Boolean)
            .map(line => line.split(":"))
            .filter(fields => fields.length === 7)
            .map(fields => ({
                username: fields[0],
                uid: Number(fields[2]),
                gid: Number(fields[3]),
                home: fields[5],
                shell: fields[6],
            }));
    } catch {
        return [];
    }
}

function classifyUser(user) {
    if (user.uid === 0) return "root";
    if (user.uid < 1000) return "system/service account";
    return "regular user";
}

async function showUsers() {
    const users = await readLinuxUsers();

    console.log("\nLOCAL ACCOUNT INVENTORY");
    console.log("=".repeat(90));
    console.log(
        `${"USER".padEnd(20)}${"UID".padEnd(8)}${"GID".padEnd(8)}${"TYPE".padEnd(24)}SHELL`
    );
    console.log("-".repeat(90));

    for (const user of users.slice(0, 25)) {
        console.log(
            `${user.username.padEnd(20)}` +
            `${String(user.uid).padEnd(8)}` +
            `${String(user.gid).padEnd(8)}` +
            `${classifyUser(user).padEnd(24)}` +
            user.shell
        );
    }
}


// ---------------------------------------------------------------------------
// 4. Linux permission interpretation
// ---------------------------------------------------------------------------

function permissionDigit(bits) {
    let value = 0;

    if (bits.includes("r")) value += 4;
    if (bits.includes("w")) value += 2;
    if (bits.includes("x")) value += 1;

    return value;
}

function symbolicToNumeric(permission) {
    if (!/^[rwx-]{9}$/.test(permission)) {
        throw new Error("Expected nine characters containing r, w, x, or -.");
    }

    return [
        permissionDigit(permission.slice(0, 3)),
        permissionDigit(permission.slice(3, 6)),
        permissionDigit(permission.slice(6, 9)),
    ].join("");
}

function explainPermission(permission) {
    const numeric = symbolicToNumeric(permission);

    return {
        numeric,
        owner: permission.slice(0, 3),
        group: permission.slice(3, 6),
        other: permission.slice(6, 9),
        worldWritable: permission[8] === "w",
        ownerWritable: permission[1] === "w",
    };
}

function demonstratePermissions() {
    console.log("\nPERMISSION MODEL");
    console.log("=".repeat(80));

    for (const permission of [
        "rw-------",
        "rw-r-----",
        "rwxr-x---",
        "rw-r--r--",
        "rwxrwxrwx",
    ]) {
        const explanation = explainPermission(permission);

        console.log(
            `${permission} -> ${explanation.numeric} ` +
            `(owner=${explanation.owner}, group=${explanation.group}, ` +
            `other=${explanation.other})`
        );
    }
}


// ---------------------------------------------------------------------------
// 5. SSH configuration parsing
// ---------------------------------------------------------------------------

function parseSshConfig(text) {
    /*
     * This parser intentionally handles the ordinary global form.
     * OpenSSH also supports Match blocks, Include directives and more
     * advanced syntax, so a production parser should not assume this small
     * parser represents every possible sshd configuration.
     */
    const settings = new Map();

    for (const line of text.split(/\r?\n/)) {
        const trimmed = line.trim();

        if (!trimmed || trimmed.startsWith("#")) {
            continue;
        }

        const match = trimmed.match(/^(\S+)\s+(.+)$/);

        if (match) {
            settings.set(match[1].toLowerCase(), match[2].trim());
        }
    }

    return settings;
}

function auditSshConfig(text) {
    const settings = parseSshConfig(text);
    const findings = [];

    if ((settings.get("permitrootlogin") || "prohibit-password") === "yes") {
        findings.push({
            severity: "HIGH",
            message: "Direct root SSH login is enabled.",
        });
    }

    if ((settings.get("passwordauthentication") || "yes") === "yes") {
        findings.push({
            severity: "MEDIUM",
            message: "Password authentication is enabled.",
        });
    }

    if ((settings.get("pubkeyauthentication") || "yes") === "no") {
        findings.push({
            severity: "HIGH",
            message: "Public-key authentication is disabled.",
        });
    }

    if ((settings.get("permitemptypasswords") || "no") === "yes") {
        findings.push({
            severity: "CRITICAL",
            message: "Empty-password authentication is enabled.",
        });
    }

    const maxAuthTries = Number(settings.get("maxauthtries") || 6);

    if (!Number.isInteger(maxAuthTries) || maxAuthTries <= 0) {
        findings.push({
            severity: "WARNING",
            message: "MaxAuthTries is invalid.",
        });
    } else if (maxAuthTries > 6) {
        findings.push({
            severity: "MEDIUM",
            message: `MaxAuthTries is ${maxAuthTries}; review the value.`,
        });
    }

    return findings;
}

function demonstrateSshAudit() {
    console.log("\nSSH HARDENING AUDIT");
    console.log("=".repeat(80));

    const sample = `
Port 22
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication no
PermitEmptyPasswords no
MaxAuthTries 10
`;

    for (const finding of auditSshConfig(sample)) {
        console.log(`[${finding.severity}] ${finding.message}`);
    }
}


// ---------------------------------------------------------------------------
// 6. Service inspection
// ---------------------------------------------------------------------------

async function inspectService(serviceName) {
    if (process.platform !== "linux") {
        return {
            serviceName,
            supported: false,
            active: null,
            message: "systemd service inspection requires Linux.",
        };
    }

    const result = await runCommand("systemctl", [
        "is-active",
        serviceName,
    ]);

    return {
        serviceName,
        supported: true,
        active: result.success,
        output: result.stdout || result.stderr,
    };
}

async function demonstrateServiceInspection() {
    console.log("\nSERVICE INSPECTION");
    console.log("=".repeat(80));

    const result = await inspectService("ssh");

    console.log(`Service : ${result.serviceName}`);
    console.log(`Supported: ${result.supported}`);
    console.log(`Active  : ${result.active}`);
    console.log(`Output  : ${result.output || result.message}`);
}


// ---------------------------------------------------------------------------
// 7. Idempotent automation
// ---------------------------------------------------------------------------

async function ensureDirectory(directoryPath, mode = 0o750) {
    let created = false;

    try {
        const information = await fsp.stat(directoryPath);

        if (!information.isDirectory()) {
            throw new Error(`${directoryPath} exists but is not a directory.`);
        }
    } catch (error) {
        if (error.code !== "ENOENT") {
            throw error;
        }

        await fsp.mkdir(directoryPath, {
            recursive: true,
            mode,
        });

        created = true;
    }

    await fsp.chmod(directoryPath, mode);

    return created;
}

async function ensureFile(filePath, content, mode = 0o640) {
    let current = null;

    try {
        current = await fsp.readFile(filePath, "utf8");
    } catch (error) {
        if (error.code !== "ENOENT") {
            throw error;
        }
    }

    const changed = current !== content;

    if (changed) {
        await fsp.writeFile(filePath, content, {
            encoding: "utf8",
            mode,
        });
    }

    await fsp.chmod(filePath, mode);

    return changed;
}

async function demonstrateAutomation() {
    console.log("\nIDEMPOTENT AUTOMATION");
    console.log("=".repeat(80));

    const temporaryDirectory = await fsp.mkdtemp(
        path.join(os.tmpdir(), "linux-admin-js-")
    );

    try {
        const configurationDirectory =
            path.join(temporaryDirectory, "etc", "example-service");

        const configurationFile =
            path.join(configurationDirectory, "service.conf");

        const desiredConfiguration =
            "service_name=example-service\n" +
            "listen_address=127.0.0.1\n" +
            "listen_port=8080\n" +
            "enabled=true\n";

        const firstDirectoryChange =
            await ensureDirectory(configurationDirectory);

        const secondDirectoryChange =
            await ensureDirectory(configurationDirectory);

        const firstFileChange =
            await ensureFile(configurationFile, desiredConfiguration);

        const secondFileChange =
            await ensureFile(configurationFile, desiredConfiguration);

        console.log(`First directory run : changed=${firstDirectoryChange}`);
        console.log(`Second directory run: changed=${secondDirectoryChange}`);
        console.log(`First file run      : changed=${firstFileChange}`);
        console.log(`Second file run     : changed=${secondFileChange}`);
    } finally {
        /*
         * Removing only the temporary laboratory directory is safe because
         * it was created by this program.
         */
        await fsp.rm(temporaryDirectory, {
            recursive: true,
            force: true,
        });
    }
}


// ---------------------------------------------------------------------------
// 8. Structured log processing
// ---------------------------------------------------------------------------

class AuditLogger {
    constructor() {
        this.entries = [];
    }

    record(level, component, message) {
        this.entries.push({
            timestamp: new Date().toISOString(),
            level: String(level).toUpperCase(),
            component,
            message,
        });
    }

    countByLevel() {
        const counts = {};

        for (const entry of this.entries) {
            counts[entry.level] = (counts[entry.level] || 0) + 1;
        }

        return counts;
    }

    filter(level) {
        return this.entries.filter(
            entry => entry.level === String(level).toUpperCase()
        );
    }

    async save(filePath) {
        await fsp.writeFile(
            filePath,
            JSON.stringify(this.entries, null, 2),
            "utf8"
        );
    }
}

async function demonstrateLogging() {
    console.log("\nSTRUCTURED LOGGING");
    console.log("=".repeat(80));

    const logger = new AuditLogger();

    logger.record(
        "INFO",
        "identity",
        "Account inventory inspected."
    );

    logger.record(
        "INFO",
        "ssh",
        "SSH configuration inspected."
    );

    logger.record(
        "WARNING",
        "permissions",
        "World-writable file detected."
    );

    logger.record(
        "INFO",
        "backup",
        "Backup completed."
    );

    console.table(logger.entries);
    console.log("Counts:", logger.countByLevel());
    console.log("Warnings:", logger.filter("warning").length);
}


// ---------------------------------------------------------------------------
// 9. Configuration validation
// ---------------------------------------------------------------------------

function validateUsername(username) {
    if (!/^[a-z_][a-z0-9_-]{0,31}$/.test(username)) {
        return {
            valid: false,
            reason: "Username contains invalid characters or length.",
        };
    }

    return {
        valid: true,
        reason: "Username format is acceptable.",
    };
}

function validatePort(port) {
    return {
        valid: Number.isInteger(port) && port >= 1 && port <= 65535,
        reason:
            Number.isInteger(port) && port >= 1 && port <= 65535
                ? "Valid network port."
                : "Port must be an integer from 1 through 65535.",
    };
}

function validateHostname(hostname) {
    const valid =
        typeof hostname === "string" &&
        hostname.length >= 1 &&
        hostname.length <= 253 &&
        /^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$/.test(
            hostname
        );

    return {
        valid,
        reason: valid
            ? "Valid hostname format."
            : "Invalid hostname format.",
    };
}

function demonstrateValidation() {
    console.log("\nCONFIGURATION VALIDATION");
    console.log("=".repeat(80));

    const tests = [
        ["username", "deploy_user", validateUsername("deploy_user")],
        ["username", "Bad User", validateUsername("Bad User")],
        ["port", 443, validatePort(443)],
        ["port", 70000, validatePort(70000)],
        ["hostname", "server01.example.com", validateHostname("server01.example.com")],
        ["hostname", "bad host", validateHostname("bad host")],
    ];

    for (const [type, value, result] of tests) {
        console.log(
            `${result.valid ? "PASS" : "FAIL"} ` +
            `${type.padEnd(10)} ${String(value).padEnd(25)} ${result.reason}`
        );
    }
}


// ---------------------------------------------------------------------------
// 10. Resource information
// ---------------------------------------------------------------------------

function showResourceInformation() {
    console.log("\nRESOURCE INFORMATION");
    console.log("=".repeat(80));

    const freeGiB = os.freemem() / 1024 ** 3;
    const totalGiB = os.totalmem() / 1024 ** 3;

    console.log(`Memory total: ${totalGiB.toFixed(2)} GiB`);
    console.log(`Memory free : ${freeGiB.toFixed(2)} GiB`);
    console.log(
        `Memory used : ${(totalGiB - freeGiB).toFixed(2)} GiB`
    );

    console.log("\nLoad averages:");
    console.log(os.loadavg());
}


// ---------------------------------------------------------------------------
// 11. Security baseline
// ---------------------------------------------------------------------------

function printSecurityBaseline() {
    console.log("\nSECURITY BASELINE");
    console.log("=".repeat(80));

    const controls = [
        "Least privilege for users and services",
        "Strong SSH authentication",
        "Restricted direct root access",
        "Controlled network exposure",
        "Regular security updates",
        "Auditable configuration changes",
        "Centralized and protected logs",
        "Backups with tested restoration",
        "Protection of private keys and credentials",
        "Monitoring of storage, memory, processes, and services",
    ];

    controls.forEach((control, index) => {
        console.log(`${String(index + 1).padStart(2)}. ${control}`);
    });
}


// ---------------------------------------------------------------------------
// 12. Performance demonstration
// ---------------------------------------------------------------------------

function benchmarkPermissionParsing(iterations = 100000) {
    const permission = "rwxr-x---";
    const started = process.hrtime.bigint();

    let result = "";

    for (let i = 0; i < iterations; i++) {
        result = symbolicToNumeric(permission);
    }

    const elapsedMilliseconds =
        Number(process.hrtime.bigint() - started) / 1_000_000;

    console.log("\nPERFORMANCE DEMONSTRATION");
    console.log("=".repeat(80));
    console.log(`Iterations: ${iterations}`);
    console.log(`Result    : ${result}`);
    console.log(`Time      : ${elapsedMilliseconds.toFixed(3)} ms`);
}


// ---------------------------------------------------------------------------
// 13. Self tests
// ---------------------------------------------------------------------------

async function runTests() {
    console.log("\nSELF TESTS");
    console.log("=".repeat(80));

    const tests = [
        [
            "permission conversion",
            () => symbolicToNumeric("rwxr-x---") === "750",
        ],
        [
            "permission rejection",
            () => {
                try {
                    symbolicToNumeric("invalid");
                    return false;
                } catch {
                    return true;
                }
            },
        ],
        [
            "SSH audit",
            () => {
                const findings = auditSshConfig(
                    "PermitRootLogin yes\n" +
                    "PasswordAuthentication yes\n" +
                    "PubkeyAuthentication no\n" +
                    "PermitEmptyPasswords yes\n" +
                    "MaxAuthTries 20\n"
                );

                return findings.length === 5;
            },
        ],
        [
            "port validation",
            () => validatePort(22).valid && !validatePort(70000).valid,
        ],
        [
            "username validation",
            () =>
                validateUsername("deploy_user").valid &&
                !validateUsername("Bad User").valid,
        ],
    ];

    let passed = 0;

    for (const [name, test] of tests) {
        try {
            if (await test()) {
                console.log(`PASS  ${name}`);
                passed++;
            } else {
                console.log(`FAIL  ${name}`);
            }
        } catch (error) {
            console.log(`FAIL  ${name}: ${error.message}`);
        }
    }

    console.log(`\n${passed}/${tests.length} tests passed.`);
}


// ---------------------------------------------------------------------------
// 14. Main educational workflow
// ---------------------------------------------------------------------------

async function main() {
    console.log("=".repeat(80));
    console.log("LINUX ADMINISTRATION JAVASCRIPT LABORATORY");
    console.log("=".repeat(80));

    printSystemInformation();

    demonstratePermissions();
    demonstrateSshAudit();
    demonstrateValidation();

    await demonstrateServiceInspection();
    await demonstrateAutomation();
    await demonstrateLogging();

    showResourceInformation();
    printSecurityBaseline();

    benchmarkPermissionParsing();
    await runTests();

    console.log("\nLAB COMPLETE");
    console.log("=".repeat(80));
}

main().catch(error => {
    console.error(`Fatal error: ${error.message}`);
    process.exitCode = 1;
});
