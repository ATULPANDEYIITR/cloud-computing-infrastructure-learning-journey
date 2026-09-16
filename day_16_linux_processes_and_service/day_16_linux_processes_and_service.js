```javascript
"use strict";

/*
 * Linux Processes and Services
 *
 * Complete Node.js demonstration covering:
 *   - Process IDs and parent processes
 *   - Child processes
 *   - Signals
 *   - ps, top and systemctl
 *   - Services and daemons
 *   - systemd inspection
 *   - /proc monitoring
 *   - Async process execution
 *   - Timeouts and graceful termination
 *   - Validation
 *   - Health checks
 *   - A practical service-monitoring case study
 *
 * Run on Linux with:
 *   node linux_processes_services.js
 *
 * Node.js is used here because its child_process API exposes operating-system
 * process management directly while its asynchronous programming model makes
 * monitoring and supervision patterns easy to demonstrate.
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const {
    execFile,
    spawn,
    execFileSync,
} = require("child_process");

function heading(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function subheading(title) {
    console.log("\n" + "-".repeat(78));
    console.log(title);
    console.log("-".repeat(78));
}

function isLinux() {
    return process.platform === "linux";
}

function requireLinux() {
    if (!isLinux()) {
        console.log(`This demonstration requires Linux. Detected: ${process.platform}`);
        return false;
    }
    return true;
}

function runCommand(command, args = [], options = {}) {
    return new Promise((resolve) => {
        execFile(command, args, {
            encoding: "utf8",
            timeout: options.timeout ?? 5000,
            maxBuffer: options.maxBuffer ?? 1024 * 1024,
        }, (error, stdout, stderr) => {
            resolve({
                error,
                stdout: stdout || "",
                stderr: stderr || "",
                status: error && typeof error.code === "number"
                    ? error.code
                    : error
                        ? 1
                        : 0,
            });
        });
    });
}

function runCommandSync(command, args = []) {
    try {
        return {
            status: 0,
            stdout: execFileSync(command, args, {
                encoding: "utf8",
                timeout: 5000,
                maxBuffer: 1024 * 1024,
            }),
            stderr: "",
        };
    } catch (error) {
        return {
            status: typeof error.status === "number" ? error.status : 1,
            stdout: error.stdout?.toString() ?? "",
            stderr: error.stderr?.toString() ?? error.message,
        };
    }
}

// ---------------------------------------------------------------------------
// Fundamental process information
// ---------------------------------------------------------------------------

function processIdentity() {
    heading("1. Node.js process identity");

    console.log("Current PID       :", process.pid);
    console.log("Parent PID        :", process.ppid);
    console.log("Platform          :", process.platform);
    console.log("Architecture      :", process.arch);
    console.log("Node.js version   :", process.version);
    console.log("CPU count         :", os.cpus().length);
    console.log("Working directory :", process.cwd());

    console.log("\nSelected environment variables:");
    for (const name of ["PATH", "HOME", "USER", "SHELL"]) {
        if (process.env[name]) {
            console.log(`${name}: ${process.env[name]}`);
        }
    }
}

// ---------------------------------------------------------------------------
// Child process creation
// ---------------------------------------------------------------------------

async function childProcessExample() {
    heading("2. Creating a child process");

    const result = await runCommand(
        process.execPath,
        [
            "-e",
            "console.log(`child PID=${process.pid} parent=${process.ppid}`);"
        ]
    );

    console.log("stdout:", result.stdout.trim());
    console.log("stderr:", result.stderr.trim());
    console.log("exit status:", result.status);

    console.log(
        `
Node's child_process module provides several patterns.

execFile:
  Runs an executable without requiring a shell.

spawn:
  Streams data and is useful for long-running commands.

exec:
  Runs a command through a shell and collects output. It requires additional
  care when input is influenced by users.

The distinction matters for both performance and security.
`
    );
}

// ---------------------------------------------------------------------------
// ps
// ---------------------------------------------------------------------------

async function demonstratePs() {
    heading("3. Inspecting processes with ps");

    if (!requireLinux()) return;

    const result = await runCommand(
        "ps",
        ["-eo", "pid,ppid,user,stat,%cpu,%mem,etime,comm", "--sort=-%cpu"]
    );

    if (result.status !== 0) {
        console.log(result.stderr);
        return;
    }

    const lines = result.stdout.trim().split("\n");
    for (const line of lines.slice(0, 20)) {
        console.log(line);
    }

    if (lines.length > 20) {
        console.log(`... ${lines.length - 20} additional lines omitted.`);
    }
}

// ---------------------------------------------------------------------------
// top
// ---------------------------------------------------------------------------

async function demonstrateTop() {
    heading("4. Batch-mode top");

    if (!requireLinux()) return;

    const result = await runCommand(
        "top",
        ["-b", "-n", "1", "-w", "120"]
    );

    if (result.status !== 0) {
        console.log(result.stderr);
        return;
    }

    const lines = result.stdout.trim().split("\n");
    for (const line of lines.slice(0, 25)) {
        console.log(line);
    }

    console.log(
        `
top provides a real-time operational view of CPU, memory, load and
individual processes. Batch mode is useful when another program needs a
snapshot, although structured interfaces such as /proc are generally less
fragile than parsing interactive command output.
`
    );
}

// ---------------------------------------------------------------------------
// /proc
// ---------------------------------------------------------------------------

function parseProcStatus(pid) {
    if (!isLinux()) return null;

    const filename = `/proc/${pid}/status`;

    try {
        const text = fs.readFileSync(filename, "utf8");
        const values = {};

        for (const line of text.split("\n")) {
            const separator = line.indexOf(":");
            if (separator === -1) continue;

            const key = line.slice(0, separator);
            const value = line.slice(separator + 1).trim();
            values[key] = value;
        }

        return values;
    } catch (error) {
        return null;
    }
}

function demonstrateProcfs() {
    heading("5. Reading process information from /proc");

    if (!requireLinux()) return;

    const status = parseProcStatus(process.pid);

    if (!status) {
        console.log("Unable to read /proc for this process.");
        return;
    }

    for (const key of [
        "Name",
        "State",
        "Pid",
        "PPid",
        "Uid",
        "Gid",
        "Threads",
        "VmSize",
        "VmRSS",
        "FDSize",
    ]) {
        if (status[key] !== undefined) {
            console.log(`${key.padEnd(10)}: ${status[key]}`);
        }
    }

    try {
        const descriptors = fs.readdirSync(`/proc/${process.pid}/fd`);
        console.log("Open file descriptors:", descriptors.length);
    } catch {
        console.log("Open file descriptors: unavailable");
    }
}

// ---------------------------------------------------------------------------
// Signals
// ---------------------------------------------------------------------------

function explainSignals() {
    heading("6. Signals");

    const signals = [
        ["SIGTERM", "Graceful termination request."],
        ["SIGKILL", "Kernel-enforced termination; application cannot catch it."],
        ["SIGINT", "Interrupt, commonly associated with Ctrl+C."],
        ["SIGHUP", "Hangup; applications sometimes use it to request reload."],
        ["SIGSTOP", "Stops execution and cannot be caught."],
        ["SIGCONT", "Continues a stopped process."],
    ];

    for (const [name, description] of signals) {
        console.log(`${name.padEnd(8)} ${description}`);
    }

    console.log(
        `
Node allows signal handlers such as:

process.on("SIGTERM", handler)

A process should normally treat SIGTERM as a controlled shutdown request.
SIGKILL is different because the process cannot execute cleanup logic after
the kernel terminates it.
`
    );
}

// ---------------------------------------------------------------------------
// Graceful worker
// ---------------------------------------------------------------------------

function gracefulWorkerExample() {
    heading("7. Graceful child termination");

    const childScript = `
        let running = true;

        process.on("SIGTERM", () => {
            console.log("worker received SIGTERM");
            running = false;
        });

        console.log("worker PID=" + process.pid);

        const timer = setInterval(() => {
            if (!running) {
                clearInterval(timer);
                console.log("worker cleanup completed");
                process.exit(0);
            }
        }, 100);
    `;

    const child = spawn(process.execPath, ["-e", childScript], {
        stdio: ["ignore", "pipe", "pipe"],
    });

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");

    child.stdout.on("data", (data) => {
        process.stdout.write(`[child stdout] ${data}`);
    });

    child.stderr.on("data", (data) => {
        process.stderr.write(`[child stderr] ${data}`);
    });

    child.on("spawn", () => {
        console.log("Started child PID:", child.pid);

        setTimeout(() => {
            console.log("Sending SIGTERM...");
            child.kill("SIGTERM");
        }, 500);
    });

    child.on("close", (code, signal) => {
        console.log("Child close event:", { code, signal });
    });
}

// ---------------------------------------------------------------------------
// Timeout supervision
// ---------------------------------------------------------------------------

function supervisedChildExample() {
    heading("8. Supervising an unresponsive process");

    const child = spawn(
        process.execPath,
        ["-e", "setTimeout(() => {}, 30000)"],
        { stdio: "ignore" }
    );

    console.log("Started PID:", child.pid);

    let finished = false;

    const forceKillTimer = setTimeout(() => {
        if (!finished) {
            console.log("Graceful termination exceeded deadline.");
            console.log("Sending SIGKILL...");
            child.kill("SIGKILL");
        }
    }, 2000);

    const gracefulTimer = setTimeout(() => {
        if (!finished) {
            console.log("Sending SIGTERM...");
            child.kill("SIGTERM");
        }
    }, 500);

    child.on("close", (code, signal) => {
        finished = true;
        clearTimeout(gracefulTimer);
        clearTimeout(forceKillTimer);
        console.log("Child ended:", { code, signal });
    });
}

// ---------------------------------------------------------------------------
// Service concepts
// ---------------------------------------------------------------------------

function explainServices() {
    heading("9. Services, daemons and systemd");

    console.log(
        `
A service is a long-running system capability.

A daemon is a background process that provides a service.

systemd commonly acts as:
  * PID 1 on systems booted with systemd
  * service manager
  * dependency manager
  * process supervisor
  * boot transaction manager
  * logging integration point
  * resource-control interface

A service unit describes how a long-running program should be managed.
`
    );
}

// ---------------------------------------------------------------------------
// systemctl
// ---------------------------------------------------------------------------

async function demonstrateSystemctl() {
    heading("10. systemctl");

    if (!requireLinux()) return;

    const version = await runCommand("systemctl", ["--version"]);

    if (version.status !== 0) {
        console.log("systemctl is unavailable in this environment.");
        console.log(version.stderr);
        return;
    }

    console.log(version.stdout.trim());

    const running = await runCommand(
        "systemctl",
        ["is-system-running"]
    );

    console.log("\nis-system-running:");
    console.log(running.stdout.trim() || running.stderr.trim());

    const services = await runCommand(
        "systemctl",
        ["list-units", "--type=service", "--no-pager", "--no-legend"]
    );

    console.log("\nServices:");
    console.log(
        services.stdout
            .trim()
            .split("\n")
            .slice(0, 20)
            .join("\n")
    );
}

// ---------------------------------------------------------------------------
// Service inspection
// ---------------------------------------------------------------------------

async function inspectService(serviceName) {
    const result = await runCommand(
        "systemctl",
        [
            "show",
            serviceName,
            "--no-pager",
            "--property=LoadState,ActiveState,SubState,UnitFileState,MainPID"
        ]
    );

    if (result.status !== 0) {
        return null;
    }

    const values = {};

    for (const line of result.stdout.trim().split("\n")) {
        const index = line.indexOf("=");

        if (index !== -1) {
            values[line.slice(0, index)] = line.slice(index + 1);
        }
    }

    return {
        name: serviceName,
        loadState: values.LoadState ?? "unknown",
        activeState: values.ActiveState ?? "unknown",
        subState: values.SubState ?? "unknown",
        unitFileState: values.UnitFileState ?? "unknown",
        mainPid: values.MainPID ?? "0",
    };
}

async function demonstrateServiceInspection() {
    heading("11. Inspecting service state");

    if (!requireLinux()) return;

    const candidates = [
        "ssh.service",
        "sshd.service",
        "cron.service",
        "systemd-journald.service",
    ];

    let found = false;

    for (const service of candidates) {
        const state = await inspectService(service);

        if (!state) continue;

        found = true;

        console.log(
            `${state.name.padEnd(32)} ` +
            `active=${state.activeState.padEnd(10)} ` +
            `sub=${state.subState.padEnd(12)} ` +
            `enabled=${state.unitFileState.padEnd(12)} ` +
            `pid=${state.mainPid}`
        );
    }

    if (!found) {
        console.log("No candidate service was available.");
    }
}

// ---------------------------------------------------------------------------
// journalctl
// ---------------------------------------------------------------------------

async function demonstrateJournalctl() {
    heading("12. Reading service logs");

    if (!requireLinux()) return;

    const result = await runCommand(
        "journalctl",
        ["-n", "15", "--no-pager"]
    );

    if (result.status === 0) {
        console.log(result.stdout.trim());
    } else {
        console.log(
            "journalctl could not be queried. " +
            "This is common in restricted containers."
        );
        console.log(result.stderr.trim());
    }
}

// ---------------------------------------------------------------------------
// Process inventory
// ---------------------------------------------------------------------------

function collectProcessInventory(limit = 20) {
    heading("13. Process inventory through /proc");

    if (!requireLinux()) return [];

    let entries;

    try {
        entries = fs.readdirSync("/proc");
    } catch (error) {
        console.log("Unable to read /proc:", error.message);
        return [];
    }

    const records = [];

    for (const entry of entries) {
        if (!/^\d+$/.test(entry)) continue;

        const status = parseProcStatus(Number(entry));
        if (!status) continue;

        const memoryMatch = /^(\d+)/.exec(status.VmRSS ?? "0");
        const memoryKb = memoryMatch ? Number(memoryMatch[1]) : 0;

        records.push({
            pid: Number(status.Pid ?? entry),
            ppid: Number(status.PPid ?? 0),
            name: status.Name ?? "?",
            state: (status.State ?? "?")[0],
            memoryKb,
            threads: Number(status.Threads ?? 0),
        });
    }

    records.sort((a, b) => b.memoryKb - a.memoryKb);

    console.log(
        "PID".padStart(7),
        "PPID".padStart(7),
        "STATE".padStart(7),
        "RSS KiB".padStart(10),
        "THREADS".padStart(9),
        "NAME"
    );

    for (const record of records.slice(0, limit)) {
        console.log(
            String(record.pid).padStart(7),
            String(record.ppid).padStart(7),
            record.state.padStart(7),
            String(record.memoryKb).padStart(10),
            String(record.threads).padStart(9),
            record.name.slice(0, 30)
        );
    }

    return records;
}

// ---------------------------------------------------------------------------
// Health evaluation
// ---------------------------------------------------------------------------

function evaluateServiceHealth({
    activeState,
    subState,
    restartCount,
    memoryKb,
    memoryLimitKb,
}) {
    const reasons = [];

    if (activeState !== "active") {
        reasons.push(`service is not active: ${activeState}`);
    }

    if (!["running", "listening", "exited"].includes(subState)) {
        reasons.push(`unexpected substate: ${subState}`);
    }

    if (restartCount > 5) {
        reasons.push("restart count exceeds threshold");
    }

    if (memoryKb > memoryLimitKb) {
        reasons.push(
            `memory ${memoryKb} KiB exceeds ${memoryLimitKb} KiB`
        );
    }

    return {
        healthy: reasons.length === 0,
        reasons,
    };
}

function healthExamples() {
    heading("14. Service-health evaluation");

    const cases = [
        {
            activeState: "active",
            subState: "running",
            restartCount: 0,
            memoryKb: 100000,
            memoryLimitKb: 500000,
        },
        {
            activeState: "failed",
            subState: "failed",
            restartCount: 9,
            memoryKb: 100000,
            memoryLimitKb: 500000,
        },
        {
            activeState: "active",
            subState: "running",
            restartCount: 1,
            memoryKb: 700000,
            memoryLimitKb: 500000,
        },
    ];

    cases.forEach((testCase, index) => {
        const result = evaluateServiceHealth(testCase);
        console.log(`Case ${index + 1}: healthy=${result.healthy}`);

        for (const reason of result.reasons) {
            console.log("  -", reason);
        }
    });
}

// ---------------------------------------------------------------------------
// Input validation
// ---------------------------------------------------------------------------

function validateServiceName(serviceName) {
    if (typeof serviceName !== "string") return false;
    if (serviceName.length === 0 || serviceName.length > 255) return false;

    if (serviceName.includes("/") ||
        serviceName.includes("\\") ||
        serviceName.includes("..")) {
        return false;
    }

    return /^[A-Za-z0-9._@-]+$/.test(serviceName);
}

function validationExamples() {
    heading("15. Service-name validation");

    const samples = [
        "ssh.service",
        "cron.service",
        "worker@1.service",
        "",
        "../../etc/passwd",
        "service name",
    ];

    for (const sample of samples) {
        console.log(
            `${JSON.stringify(sample).padEnd(30)} ` +
            `valid=${validateServiceName(sample)}`
        );
    }

    console.log(
        `
Validation prevents malformed input from reaching the command layer.
It does not grant permission to control a service. Authorization remains a
separate security requirement.
`
    );
}

// ---------------------------------------------------------------------------
// Process metrics
// ---------------------------------------------------------------------------

function processResourceInformation() {
    heading("16. Node.js resource information");

    console.log("process.memoryUsage():");
    console.table(process.memoryUsage());

    console.log("os.loadavg():", os.loadavg());
    console.log("os.totalmem():", os.totalmem());
    console.log("os.freemem():", os.freemem());

    console.log(
        `
Node's process.memoryUsage() reports memory used by the Node process itself.
Linux /proc exposes a wider operating-system view of processes.

loadavg is not a direct percentage of CPU usage. It represents the average
number of tasks in runnable or uninterruptible states over time on Linux.
`
    );
}

// ---------------------------------------------------------------------------
// Service unit example
// ---------------------------------------------------------------------------

function showUnitFile() {
    heading("17. Example systemd unit structure");

    const unit = [
        "[Unit]",
        "Description=Example Application Service",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=simple",
        "User=example",
        "Group=example",
        "ExecStart=/opt/example/bin/server",
        "Restart=on-failure",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ].join("\n");

    console.log(unit);

    console.log(
        `
The [Unit] section establishes relationships and metadata.

The [Service] section controls process execution.

The [Install] section defines relationships used when enabling a unit.

Running a service under a dedicated account reduces the impact of a
compromise compared with unnecessarily running application code as root.
`
    );
}

// ---------------------------------------------------------------------------
// Safe command construction
// ---------------------------------------------------------------------------

async function safeAdministrativeLookup(serviceName) {
    heading("18. Safe command construction");

    if (!validateServiceName(serviceName)) {
        throw new Error("Invalid service name");
    }

    // execFile passes arguments without invoking a shell. This avoids shell
    // metacharacter interpretation for the supplied service name.
    const result = await runCommand(
        "systemctl",
        ["show", serviceName, "--property=ActiveState", "--no-pager"]
    );

    console.log(result.stdout.trim() || result.stderr.trim());
}

// ---------------------------------------------------------------------------
// Async monitoring loop
// ---------------------------------------------------------------------------

async function monitorProcess(pid, iterations = 3, intervalMs = 1000) {
    heading(`19. Asynchronous monitoring of PID ${pid}`);

    if (!requireLinux()) return;

    for (let iteration = 1; iteration <= iterations; iteration++) {
        const status = parseProcStatus(pid);

        if (!status) {
            console.log("Process no longer exists or cannot be inspected.");
            return;
        }

        console.log(
            `sample=${iteration} ` +
            `state=${status.State ?? "?"} ` +
            `rss=${status.VmRSS ?? "?"} ` +
            `threads=${status.Threads ?? "?"}`
        );

        await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
}

// ---------------------------------------------------------------------------
// Testing
// ---------------------------------------------------------------------------

function runTests() {
    heading("20. Internal tests");

    console.assert(
        validateServiceName("ssh.service"),
        "Expected valid service name"
    );

    console.assert(
        validateServiceName("worker@1.service"),
        "Expected valid service name"
    );

    console.assert(
        !validateServiceName("../../passwd"),
        "Expected traversal-style name to fail"
    );

    console.assert(
        !validateServiceName("service name"),
        "Expected whitespace to fail"
    );

    const healthy = evaluateServiceHealth({
        activeState: "active",
        subState: "running",
        restartCount: 0,
        memoryKb: 100,
        memoryLimitKb: 1000,
    });

    console.assert(healthy.healthy, "Expected healthy service");

    const unhealthy = evaluateServiceHealth({
        activeState: "failed",
        subState: "failed",
        restartCount: 0,
        memoryKb: 100,
        memoryLimitKb: 1000,
    });

    console.assert(!unhealthy.healthy, "Expected unhealthy service");

    console.log("Tests completed.");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
    processIdentity();
    demonstrateProcfs();
    processResourceInformation();

    await childProcessExample();
    await demonstratePs();
    await demonstrateTop();

    explainSignals();
    gracefulWorkerExample();

    // Allow the asynchronous child example to produce output before starting
    // other sections. This also demonstrates event-driven process handling.
    await new Promise((resolve) => setTimeout(resolve, 1000));

    supervisedChildExample();
    explainServices();

    await demonstrateSystemctl();
    showUnitFile();
    await demonstrateServiceInspection();
    await demonstrateJournalctl();

    collectProcessInventory(20);
    healthExamples();
    validationExamples();
    runTests();

    // Only monitor ourselves when /proc is available.
    await monitorProcess(process.pid, 2, 500);

    console.log("\nLinux process and service study completed.");
}

main().catch((error) => {
    console.error("Fatal error:", error.message);
    process.exitCode = 1;
});
```
