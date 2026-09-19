#!/usr/bin/env node

/*
 * Bash Shell Scripting Companion in JavaScript
 * ---------------------------------------------
 *
 * This file complements the Python implementation by showing how JavaScript
 * can model shell-script concepts while also demonstrating JavaScript's own
 * strengths in asynchronous and application-level automation.
 *
 * Topics:
 *   - variables
 *   - conditions
 *   - loops
 *   - functions
 *   - arguments
 *   - arrays and objects
 *   - exit-status concepts
 *   - command execution concepts
 *   - asynchronous automation
 *   - retries
 *   - validation
 *   - logging
 *   - dry-run behavior
 *   - filesystem automation
 *   - idempotency
 *   - security
 *
 * Run:
 *   node bash_shell_scripting.js
 *
 * Optional:
 *   node bash_shell_scripting.js --section automation --dry-run
 */

"use strict";

const fs = require("fs");
const fsp = fs.promises;
const path = require("path");
const os = require("os");
const { execFile, spawn } = require("child_process");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);

// ---------------------------------------------------------------------------
// Output helpers
// ---------------------------------------------------------------------------

function title(text) {
    console.log("\n" + "=".repeat(78));
    console.log(text);
    console.log("=".repeat(78));
}

function subtitle(text) {
    console.log("\n" + "-".repeat(78));
    console.log(text);
    console.log("-".repeat(78));
}

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

function demonstrateVariables() {
    title("1. Variables and environment variables");

    // JavaScript has explicit declarations. Bash variables are dynamically
    // typed and normally assigned with name=value.
    const username = "atul";
    let fileCount = 7;
    const projectName = "automation-lab";

    console.log({ username, fileCount, projectName });

    // process.env corresponds conceptually to the environment inherited by
    // a process. It is similar to Bash's environment-variable interface.
    const home = process.env.HOME || process.env.USERPROFILE || "unknown";
    const shell = process.env.SHELL || "unknown";

    console.log("HOME:", home);
    console.log("SHELL:", shell);

    // Bash:
    //   port="${PORT:-8080}"
    //
    // JavaScript equivalent:
    const port = process.env.PORT || "8080";
    console.log("Effective port:", port);

    console.log(`
Bash:
    name="Atul"
    count=10
    export APP_ENV="production"

JavaScript:
    const name = "Atul";
    let count = 10;
    process.env.APP_ENV = "production";

Bash variables and JavaScript variables have different execution semantics,
but both are frequently used to hold configuration and runtime state.
`);
}

// ---------------------------------------------------------------------------
// Conditions
// ---------------------------------------------------------------------------

function demonstrateConditions() {
    title("2. Conditions");

    const users = [
        { name: "alice", age: 24, active: true, role: "admin" },
        { name: "bob", age: 16, active: true, role: "student" },
        { name: "carol", age: 31, active: false, role: "operator" },
        { name: "dave", age: 42, active: true, role: "operator" }
    ];

    for (const user of users) {
        let status;

        if (!user.active) {
            status = "inactive";
        } else if (user.role === "admin") {
            status = "administrator";
        } else if (user.age >= 18) {
            status = "adult user";
        } else {
            status = "minor user";
        }

        console.log(`${user.name.padEnd(8)} -> ${status}`);
    }

    console.log(`
Bash string comparison:
    [[ "$role" == "admin" ]]

Bash numeric comparison:
    [[ "$age" -ge 18 ]]

Bash file tests:
    [[ -f "$file" ]]
    [[ -d "$directory" ]]
    [[ -r "$file" ]]

JavaScript uses operators such as ===, !==, >=, &&, || and !.
`);
}

// ---------------------------------------------------------------------------
// Loops
// ---------------------------------------------------------------------------

function demonstrateLoops() {
    title("3. Loops");

    const services = ["api", "database", "worker", "frontend"];

    subtitle("for...of");
    for (const service of services) {
        console.log(`Checking service: ${service}`);
    }

    subtitle("Numeric loop");
    for (let index = 1; index <= 5; index += 1) {
        console.log(`Iteration ${index}`);
    }

    subtitle("while loop");
    let attempts = 3;
    while (attempts > 0) {
        console.log(`Attempts remaining: ${attempts}`);
        attempts -= 1;
    }

    subtitle("continue and break");
    for (let number = 1; number <= 10; number += 1) {
        if (number % 2 === 0) {
            continue;
        }

        if (number > 7) {
            break;
        }

        console.log(`Processed: ${number}`);
    }

    console.log(`
Bash:
    for service in "\${services[@]}"; do
        printf '%s\\n' "$service"
    done

    while condition; do
        ...
    done

Both Bash and JavaScript support several loop forms, but Bash loops are
especially useful for iterating over shell words, command output, arrays,
and filesystem-oriented data.
`);
}

// ---------------------------------------------------------------------------
// Functions
// ---------------------------------------------------------------------------

function calculateTotal(values) {
    return values.reduce((total, value) => total + value, 0);
}

function validateUsername(username) {
    return /^[A-Za-z0-9_.-]{3,32}$/.test(username);
}

async function retry(operation, attempts, delayMilliseconds = 0) {
    if (!Number.isInteger(attempts) || attempts < 1) {
        throw new RangeError("attempts must be at least 1");
    }

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
        console.log(`Attempt ${attempt}/${attempts}`);

        try {
            const result = await operation();
            return result;
        } catch (error) {
            if (attempt === attempts) {
                throw error;
            }

            if (delayMilliseconds > 0) {
                await new Promise((resolve) =>
                    setTimeout(resolve, delayMilliseconds)
                );
            }
        }
    }

    throw new Error("Unreachable retry state");
}

async function demonstrateFunctions() {
    title("4. Functions");

    const values = [120, 300, 80, 500];

    console.log("Values:", values);
    console.log("Total:", calculateTotal(values));

    for (const username of [
        "atul",
        "admin_user",
        "invalid user",
        "a",
        "deploy-01"
    ]) {
        console.log(username, "valid=", validateUsername(username));
    }

    let operationCount = 0;

    const result = await retry(async () => {
        operationCount += 1;

        if (operationCount < 3) {
            throw new Error("Simulated transient failure");
        }

        return "Service became available";
    }, 5);

    console.log(result);

    console.log(`
Bash functions:
    check_service() {
        local service="$1"
        ...
    }

    check_service "api"

A Bash function communicates success or failure primarily through its exit
status. It can also write data to stdout for command substitution.
`);
}

// ---------------------------------------------------------------------------
// Arguments
// ---------------------------------------------------------------------------

function parseArguments(argv) {
    const configuration = {
        section: "all",
        name: "Atul",
        dryRun: false
    };

    for (let index = 0; index < argv.length; index += 1) {
        const argument = argv[index];

        if (argument === "--section") {
            configuration.section = argv[index + 1];
            index += 1;
        } else if (argument === "--name") {
            configuration.name = argv[index + 1];
            index += 1;
        } else if (argument === "--dry-run") {
            configuration.dryRun = true;
        } else if (argument === "--help") {
            console.log(`
Usage:
  node bash_shell_scripting.js
  node bash_shell_scripting.js --section variables
  node bash_shell_scripting.js --section automation --dry-run
  node bash_shell_scripting.js --name Atul
`);
            process.exit(0);
        } else {
            throw new Error(`Unknown argument: ${argument}`);
        }
    }

    const validSections = new Set([
        "all",
        "variables",
        "conditions",
        "loops",
        "functions",
        "arguments",
        "automation"
    ]);

    if (!validSections.has(configuration.section)) {
        throw new Error(`Invalid section: ${configuration.section}`);
    }

    return configuration;
}

function demonstrateArguments(name) {
    title("5. Command-line arguments");

    console.log("Node executable:", process.argv[0]);
    console.log("Script path:", process.argv[1]);
    console.log("Application arguments:", process.argv.slice(2));
    console.log("Demonstration name:", name);

    console.log(`
Bash automatically exposes:
    $0   script name
    $1   first argument
    $2   second argument
    $#   argument count
    "$@" all arguments as separate words
    $?   previous command exit status

JavaScript exposes process.argv as an array.

The important shared idea is that automation programs should validate their
external inputs rather than assuming callers always provide valid data.
`);
}

// ---------------------------------------------------------------------------
// Arrays and mappings
// ---------------------------------------------------------------------------

function demonstrateArraysAndMappings() {
    title("6. Arrays and associative data");

    const services = ["api", "database", "worker"];

    services.forEach((service, index) => {
        console.log(`index=${index}, service=${service}`);
    });

    // JavaScript objects provide a common equivalent to simple Bash
    // associative arrays.
    const servicePorts = {
        api: 8080,
        database: 5432,
        worker: 9000
    };

    for (const [service, port] of Object.entries(servicePorts)) {
        console.log(`${service} -> ${port}`);
    }

    console.log(`
Bash indexed array:
    services=("api" "database" "worker")

Bash associative array:
    declare -A ports
    ports[api]=8080

JavaScript arrays and objects offer richer application-level data structures,
which becomes useful as automation logic grows.
`);
}

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

const logger = {
    info(message) {
        console.log(`[INFO] ${message}`);
    },

    warning(message) {
        console.warn(`[WARN] ${message}`);
    },

    error(message) {
        console.error(`[ERROR] ${message}`);
    }
};

function demonstrateLogging() {
    title("7. Logging");

    logger.info("Automation started");
    logger.warning("Optional configuration was not provided");
    logger.error("Simulated operation failure");

    console.log(`
In Bash, diagnostics can be written to stderr:

printf '[ERROR] %s\\n' "$message" >&2

Keeping diagnostic output separate from data output makes scripts easier to
compose into pipelines.
`);
}

// ---------------------------------------------------------------------------
// Safe command execution
// ---------------------------------------------------------------------------

async function executeProgram(program, argumentsList, options = {}) {
    /*
     * execFile avoids invoking a shell to parse the argument string.
     *
     * This is conceptually safer than:
     *     exec(`${program} ${untrustedText}`)
     *
     * when the program and its arguments are controlled separately.
     */
    const result = await execFileAsync(program, argumentsList, {
        ...options,
        windowsHide: true
    });

    return {
        stdout: result.stdout,
        stderr: result.stderr
    };
}

async function demonstrateCommandExecution() {
    title("8. Process execution and exit status");

    const command = process.platform === "win32" ? "node" : "node";

    const result = await executeProgram(
        command,
        ["-e", "process.stdout.write('child process completed\\n')"]
    );

    console.log("Child stdout:", result.stdout.trim());

    console.log(`
Bash:
    command
    status=$?
    printf 'status=%s\\n' "$status"

JavaScript:
    child_process can expose stdout, stderr, and process errors.

The shared concept is that an automation program launches another process,
collects its result, and decides whether the workflow should continue.
`);
}

// ---------------------------------------------------------------------------
// Filesystem automation
// ---------------------------------------------------------------------------

async function ensureDirectory(directory) {
    await fsp.mkdir(directory, { recursive: true });
}

async function discoverFiles(directory) {
    const entries = await fsp.readdir(directory, { withFileTypes: true });
    const files = [];

    for (const entry of entries) {
        const entryPath = path.join(directory, entry.name);

        if (entry.isDirectory()) {
            files.push(...await discoverFiles(entryPath));
        } else if (entry.isFile()) {
            files.push(entryPath);
        }
    }

    return files;
}

async function copyIfNeeded(source, destination, dryRun) {
    const sourceStats = await fsp.stat(source);

    try {
        const destinationStats = await fsp.stat(destination);

        // A deliberately simple idempotency rule: equal file sizes are treated
        // as already synchronized. Production synchronization should normally
        // compare timestamps, hashes, metadata, or use a purpose-built method.
        if (destinationStats.size === sourceStats.size) {
            return {
                action: "skipped",
                bytes: 0
            };
        }
    } catch (error) {
        if (error.code !== "ENOENT") {
            throw error;
        }
    }

    if (dryRun) {
        console.log(`[DRY-RUN] COPY ${source} -> ${destination}`);

        return {
            action: "copied",
            bytes: sourceStats.size
        };
    }

    await ensureDirectory(path.dirname(destination));
    await fsp.copyFile(source, destination);

    return {
        action: "copied",
        bytes: sourceStats.size
    };
}

async function runBackupAutomation(configuration) {
    const {
        sourceDirectory,
        backupDirectory,
        dryRun = true
    } = configuration;

    const sourceStats = await fsp.stat(sourceDirectory);

    if (!sourceStats.isDirectory()) {
        throw new Error("Source path is not a directory");
    }

    const files = await discoverFiles(sourceDirectory);

    let copied = 0;
    let skipped = 0;
    let failed = 0;
    let bytes = 0;

    for (const source of files) {
        const relativePath = path.relative(sourceDirectory, source);
        const destination = path.join(backupDirectory, relativePath);

        try {
            const result = await copyIfNeeded(
                source,
                destination,
                dryRun
            );

            if (result.action === "copied") {
                copied += 1;
                bytes += result.bytes;
            } else {
                skipped += 1;
            }
        } catch (error) {
            failed += 1;
            logger.error(`Failed to process ${source}: ${error.message}`);
        }
    }

    return {
        copied,
        skipped,
        failed,
        bytes
    };
}

async function createDemoTree(root) {
    await ensureDirectory(path.join(root, "reports"));
    await ensureDirectory(path.join(root, "logs"));

    await fsp.writeFile(
        path.join(root, "README.txt"),
        "Automation demonstration\n",
        "utf8"
    );

    await fsp.writeFile(
        path.join(root, "reports", "monthly.txt"),
        "Monthly report\n",
        "utf8"
    );

    await fsp.writeFile(
        path.join(root, "logs", "application.log"),
        "INFO application started\nERROR example event\n",
        "utf8"
    );
}

async function demonstrateAutomation(dryRun) {
    title("9. Automation case study");

    const temporaryRoot = await fsp.mkdtemp(
        path.join(os.tmpdir(), "bash-study-")
    );

    const sourceDirectory = path.join(temporaryRoot, "source");
    const backupDirectory = path.join(temporaryRoot, "backup");

    try {
        await ensureDirectory(sourceDirectory);
        await createDemoTree(sourceDirectory);

        const result = await runBackupAutomation({
            sourceDirectory,
            backupDirectory,
            dryRun
        });

        console.log("\nAutomation result:");
        console.table(result);

        if (!dryRun) {
            const backupFiles = await discoverFiles(backupDirectory);
            console.log("\nBackup files:");

            for (const file of backupFiles) {
                console.log(
                    path.relative(backupDirectory, file)
                );
            }
        }
    } finally {
        // finally is conceptually similar to a Bash EXIT trap used for cleanup.
        await fsp.rm(temporaryRoot, {
            recursive: true,
            force: true
        });
    }

    console.log(`
Bash cleanup pattern:

tmp_dir="$(mktemp -d)"

cleanup() {
    rm -rf -- "$tmp_dir"
}

trap cleanup EXIT

This ensures cleanup logic runs when the shell reaches normal exit and for
many termination paths.
`);
}

// ---------------------------------------------------------------------------
// Security
// ---------------------------------------------------------------------------

function validateSimpleFilename(filename) {
    if (!filename || filename === "." || filename === "..") {
        return false;
    }

    if (filename.includes("/") || filename.includes("\\0")) {
        return false;
    }

    return true;
}

function demonstrateSecurity() {
    title("10. Security considerations");

    const filenames = [
        "report.txt",
        "annual report.txt",
        "../secret.txt",
        "safe.log",
        ""
    ];

    for (const filename of filenames) {
        console.log(
            JSON.stringify(filename),
            "safeSimpleName=",
            validateSimpleFilename(filename)
        );
    }

    console.log(`
Important Bash security rules:

- Quote variable expansions.
- Avoid eval.
- Do not build shell commands by concatenating untrusted strings.
- Prefer arrays for command arguments.
- Validate paths and filenames.
- Avoid unnecessary privileged execution.
- Keep credentials outside source code.
- Use restrictive permissions for sensitive files.
- Provide dry-run support for destructive automation.

Safer Bash:
    args=("git" "status" "--short")
    "\${args[@]}"

Riskier:
    command="git status $USER_INPUT"
    eval "$command"

The second form converts data into shell code and creates an unnecessary
injection boundary.
`);
}

// ---------------------------------------------------------------------------
// Asynchronous scheduling
// ---------------------------------------------------------------------------

function sleep(milliseconds) {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function demonstrateAsyncAutomation() {
    title("11. Asynchronous automation");

    async function checkService(name, milliseconds) {
        await sleep(milliseconds);
        return {
            service: name,
            status: "healthy"
        };
    }

    // Promise.all resembles launching independent checks and waiting for all
    // of them. Bash can perform parallel work with '&' and later synchronize
    // using wait, but process management is more explicit there.
    const checks = await Promise.all([
        checkService("api", 40),
        checkService("database", 60),
        checkService("worker", 20)
    ]);

    console.table(checks);

    console.log(`
Bash parallelism:

check_api &
check_database &
check_worker &

wait

Bash background jobs use operating-system processes or jobs. JavaScript
commonly uses an event loop and asynchronous APIs. The two mechanisms are not
identical, but both can coordinate independent automation tasks.
`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
    const configuration = parseArguments(process.argv.slice(2));

    title(
        "Bash Shell Scripting: Variables, Conditions, Loops, Functions, Arguments, Automation"
    );

    const section = configuration.section;

    if (section === "all" || section === "variables") {
        demonstrateVariables();
    }

    if (section === "all" || section === "conditions") {
        demonstrateConditions();
    }

    if (section === "all" || section === "loops") {
        demonstrateLoops();
    }

    if (section === "all" || section === "functions") {
        await demonstrateFunctions();
    }

    if (section === "all" || section === "arguments") {
        demonstrateArguments(configuration.name);
    }

    if (section === "all") {
        demonstrateArraysAndMappings();
        demonstrateLogging();
        await demonstrateCommandExecution();
        await demonstrateAsyncAutomation();
        demonstrateSecurity();
    }

    if (section === "all" || section === "automation") {
        await demonstrateAutomation(configuration.dryRun);
    }

    title("Execution completed");
}

main().catch((error) => {
    console.error(`[FATAL] ${error.message}`);
    process.exitCode = 1;
});
