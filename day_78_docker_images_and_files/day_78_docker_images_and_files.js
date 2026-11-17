"use strict";

/**
 * Docker Images and Dockerfiles
 *
 * Event-driven Dockerfile analysis, layer dependency modeling,
 * build-cache simulation, optimization scoring, and policy evaluation.
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const EventEmitter = require("node:events");

class DockerError extends Error {
    constructor(message, code = "DOCKER_ERROR") {
        super(message);
        this.name = "DockerError";
        this.code = code;
    }
}

const INSTRUCTIONS = new Set([
    "FROM",
    "RUN",
    "COPY",
    "ADD",
    "WORKDIR",
    "ENV",
    "ARG",
    "EXPOSE",
    "USER",
    "CMD",
    "ENTRYPOINT",
    "LABEL",
    "HEALTHCHECK",
    "VOLUME",
    "SHELL"
]);

const LAYER_CREATORS = new Set([
    "FROM",
    "RUN",
    "COPY",
    "ADD"
]);

class DockerfileParser {
    parse(source) {
        if (typeof source !== "string" || !source.trim()) {
            throw new DockerError(
                "Dockerfile must contain non-empty text.",
                "EMPTY_DOCKERFILE"
            );
        }

        const logicalLines = [];
        let buffer = "";

        for (const raw of source.split(/\r?\n/)) {
            const line = raw.trim();

            if (!line || line.startsWith("#")) {
                continue;
            }

            if (line.endsWith("\\")) {
                buffer += line.slice(0, -1) + " ";
            } else {
                buffer += line;
                logicalLines.push(buffer.trim());
                buffer = "";
            }
        }

        if (buffer.trim()) {
            throw new DockerError(
                "Incomplete Dockerfile continuation."
            );
        }

        const result = logicalLines.map((line, index) => {
            const match = line.match(/^([A-Za-z]+)\s+(.+)$/);

            if (!match) {
                throw new DockerError(
                    `Invalid instruction at logical line ${index + 1}.`
                );
            }

            const command = match[1].toUpperCase();
            const argumentsText = match[2].trim();

            if (!INSTRUCTIONS.has(command)) {
                throw new DockerError(
                    `Unsupported instruction: ${command}`
                );
            }

            return Object.freeze({
                line: index + 1,
                command,
                arguments: argumentsText,
                createsLayer: LAYER_CREATORS.has(command)
            });
        });

        if (result[0]?.command !== "FROM") {
            throw new DockerError(
                "The first instruction must be FROM."
            );
        }

        return result;
    }
}

class Layer {
    constructor(index, instruction, parentHash) {
        this.index = index;
        this.instruction = instruction;
        this.parentHash = parentHash;

        this.hash = crypto
            .createHash("sha256")
            .update(
                `${parentHash}:${instruction.command}:${instruction.arguments}`
            )
            .digest("hex");

        Object.freeze(this);
    }
}

class BuildCache {
    constructor() {
        this.entries = new Map();
    }

    get(hash) {
        return this.entries.get(hash);
    }

    set(hash, value) {
        this.entries.set(hash, value);
    }

    has(hash) {
        return this.entries.has(hash);
    }

    get size() {
        return this.entries.size;
    }

    clear() {
        this.entries.clear();
    }
}

class BuildEngine extends EventEmitter {
    constructor() {
        super();

        this.cache = new BuildCache();

        this.layerSizes = new Map([
            ["FROM", 120],
            ["RUN", 15],
            ["COPY", 10],
            ["ADD", 10]
        ]);
    }

    build(instructions, options = {}) {
        const image = options.image || "application:local";

        if (!Array.isArray(instructions) || !instructions.length) {
            throw new DockerError(
                "A build requires parsed Dockerfile instructions."
            );
        }

        let parentHash = "empty";
        let totalSize = 0;
        let cacheHits = 0;
        let cacheMisses = 0;

        const layers = [];

        for (const instruction of instructions) {
            if (!instruction.createsLayer) {
                continue;
            }

            const layer = new Layer(
                layers.length + 1,
                instruction,
                parentHash
            );

            const cacheable = !(
                instruction.command === "RUN" &&
                /--no-cache/.test(instruction.arguments)
            );

            let size;

            if (cacheable && this.cache.has(layer.hash)) {
                size = this.cache.get(layer.hash);
                cacheHits++;

                this.emit("cache-hit", {
                    image,
                    layer: layer.index,
                    hash: layer.hash
                });
            } else {
                size = this.layerSizes.get(
                    instruction.command
                ) || 0;

                cacheMisses++;

                if (cacheable) {
                    this.cache.set(layer.hash, size);
                }

                this.emit("layer-built", {
                    image,
                    layer: layer.index,
                    size
                });
            }

            totalSize += size;

            layers.push({
                index: layer.index,
                command: instruction.command,
                arguments: instruction.arguments,
                hash: layer.hash,
                size,
                cacheable
            });

            parentHash = layer.hash;
        }

        const report = Object.freeze({
            image,
            layers,
            totalSize,
            cacheHits,
            cacheMisses,
            createdAt: new Date().toISOString()
        });

        this.emit("build-complete", report);

        return report;
    }
}

class SecurityPolicy {
    constructor(configuration = {}) {
        this.requireNonRoot = configuration.requireNonRoot ?? true;
        this.requireExplicitStart = configuration.requireExplicitStart ?? true;
        this.rejectLatest = configuration.rejectLatest ?? true;
        this.rejectSecrets = configuration.rejectSecrets ?? true;
    }

    evaluate(instructions) {
        const findings = [];

        const hasUser = instructions.some(
            item => item.command === "USER"
        );

        const hasStart = instructions.some(
            item =>
                item.command === "CMD" ||
                item.command === "ENTRYPOINT"
        );

        for (const instruction of instructions) {
            const args = instruction.arguments;

            if (
                this.rejectLatest &&
                instruction.command === "FROM" &&
                /:latest(?:\s|$)/i.test(args)
            ) {
                findings.push({
                    code: "MUTABLE_BASE_TAG",
                    severity: "WARNING",
                    line: instruction.line,
                    message: "Use a controlled base image version or digest."
                });
            }

            if (
                this.rejectSecrets &&
                instruction.command === "ENV" &&
                /(PASSWORD|SECRET|TOKEN|API_KEY)/i.test(args)
            ) {
                findings.push({
                    code: "SECRET_IN_ENV",
                    severity: "ERROR",
                    line: instruction.line,
                    message: "Do not store credentials in image environment variables."
                });
            }

            if (instruction.command === "ADD") {
                findings.push({
                    code: "ADD_REVIEW",
                    severity: "INFO",
                    line: instruction.line,
                    message: "Review whether COPY is sufficient."
                });
            }

            if (
                instruction.command === "RUN" &&
                /curl|wget/i.test(args) &&
                /\|\s*(sh|bash)/i.test(args)
            ) {
                findings.push({
                    code: "REMOTE_SCRIPT_PIPE",
                    severity: "WARNING",
                    line: instruction.line,
                    message: "Verify remote scripts before execution."
                });
            }

            if (
                instruction.command === "RUN" &&
                /apt-get update/i.test(args) &&
                !/rm\s+-rf\s+\/var\/lib\/apt\/lists/i.test(args)
            ) {
                findings.push({
                    code: "PACKAGE_CACHE",
                    severity: "WARNING",
                    line: instruction.line,
                    message: "Clean package-manager metadata."
                });
            }
        }

        if (this.requireNonRoot && !hasUser) {
            findings.push({
                code: "ROOT_RUNTIME",
                severity: "ERROR",
                message: "An explicit non-root runtime user is required."
            });
        }

        if (this.requireNonRoot && hasUser) {
            const lastUser = [...instructions]
                .reverse()
                .find(item => item.command === "USER");

            if (/^(root|0)$/i.test(lastUser.arguments)) {
                findings.push({
                    code: "ROOT_RUNTIME",
                    severity: "ERROR",
                    line: lastUser.line,
                    message: "The final runtime user must not be root."
                });
            }
        }

        if (this.requireExplicitStart && !hasStart) {
            findings.push({
                code: "MISSING_START_COMMAND",
                severity: "ERROR",
                message: "Define CMD or ENTRYPOINT."
            });
        }

        return findings;
    }
}

class OptimizationAnalyzer {
    analyze(instructions) {
        const recommendations = [];
        const runInstructions = instructions.filter(
            item => item.command === "RUN"
        );

        const copies = instructions.filter(
            item => item.command === "COPY"
        );

        const fromInstructions = instructions.filter(
            item => item.command === "FROM"
        );

        if (runInstructions.length > 5) {
            recommendations.push(
                "Review RUN commands and combine related operations."
            );
        }

        if (
            runInstructions.some(
                item => /apt-get update/i.test(item.arguments)
            ) &&
            !runInstructions.some(
                item => /apt-get clean|rm\s+-rf\s+\/var\/lib\/apt\/lists/i.test(item.arguments)
            )
        ) {
            recommendations.push(
                "Clean package-manager metadata to reduce image size."
            );
        }

        if (copies.some(item => item.arguments.startsWith("."))) {
            recommendations.push(
                "Use .dockerignore to exclude unnecessary build-context files."
            );
        }

        if (fromInstructions.length === 1) {
            recommendations.push(
                "Evaluate multi-stage builds for separating build and runtime dependencies."
            );
        }

        if (
            instructions.some(item => item.command === "COPY") &&
            instructions.some(item => item.command === "RUN")
        ) {
            const firstCopy = instructions.findIndex(
                item => item.command === "COPY"
            );

            const firstRun = instructions.findIndex(
                item => item.command === "RUN"
            );

            if (firstCopy < firstRun) {
                recommendations.push(
                    "Copy dependency manifests before frequently changing application source."
                );
            }
        }

        return recommendations;
    }
}

class DockerPipeline extends EventEmitter {
    constructor() {
        super();

        this.parser = new DockerfileParser();
        this.engine = new BuildEngine();
        this.security = new SecurityPolicy();
        this.optimizer = new OptimizationAnalyzer();

        this.engine.on("layer-built", event => {
            this.emit("progress", event);
        });

        this.engine.on("cache-hit", event => {
            this.emit("cache", event);
        });

        this.engine.on("build-complete", event => {
            this.emit("complete", event);
        });
    }

    execute(source, image) {
        const instructions = this.parser.parse(source);

        const findings = this.security.evaluate(
            instructions
        );

        const recommendations = this.optimizer.analyze(
            instructions
        );

        const build = this.engine.build(
            instructions,
            { image }
        );

        return {
            instructions,
            findings,
            recommendations,
            build,
            mergeBlocked: findings.some(
                finding => finding.severity === "ERROR"
            )
        };
    }
}

class DockerCLI {
    static execute(args, options = {}) {
        const result = spawnSync(
            "docker",
            args,
            {
                encoding: "utf8",
                timeout: options.timeout || 600000,
                shell: false,
                cwd: options.cwd || process.cwd(),
                maxBuffer: 10 * 1024 * 1024
            }
        );

        if (result.error) {
            throw new DockerError(
                result.error.message,
                "DOCKER_PROCESS_ERROR"
            );
        }

        if (result.status !== 0) {
            throw new DockerError(
                result.stderr || "Docker command failed.",
                "DOCKER_COMMAND_FAILED"
            );
        }

        return result.stdout;
    }

    static build(context, dockerfile, tag) {
        if (!fs.existsSync(context) || !fs.statSync(context).isDirectory()) {
            throw new DockerError("Invalid build context.");
        }

        if (!tag || !/^[a-zA-Z0-9._/:@-]+$/.test(tag)) {
            throw new DockerError("Invalid image tag.");
        }

        const dockerfilePath = path.resolve(dockerfile);
        const contextPath = path.resolve(context);

        if (!fs.existsSync(dockerfilePath)) {
            throw new DockerError("Dockerfile does not exist.");
        }

        return this.execute([
            "build",
            "--file",
            dockerfilePath,
            "--tag",
            tag,
            contextPath
        ]);
    }

    static inspect(image) {
        const output = this.execute([
            "image",
            "inspect",
            image
        ]);

        return JSON.parse(output);
    }

    static history(image) {
        return this.execute([
            "image",
            "history",
            image
        ]);
    }
}

const SAMPLE_DOCKERFILE = `
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci

COPY . .

RUN npm run build

FROM node:22-alpine AS runtime

ENV NODE_ENV=production

WORKDIR /app

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package.json ./

USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s CMD node -e "process.exit(0)"

CMD ["node", "dist/server.js"]
`;

function demonstrate() {
    const pipeline = new DockerPipeline();

    pipeline.on("progress", event => {
        process.stdout.write(
            `Built layer ${event.layer}: ${event.size} MB\n`
        );
    });

    pipeline.on("cache", event => {
        process.stdout.write(
            `Cache hit: layer ${event.layer}\n`
        );
    });

    pipeline.on("complete", event => {
        process.stdout.write(
            `Build complete: ${event.image}\n`
        );
    });

    const report = pipeline.execute(
        SAMPLE_DOCKERFILE,
        "inventory-api:1.0"
    );

    console.log("\nSecurity findings:");

    console.table(report.findings);

    console.log("\nOptimization recommendations:");

    for (const recommendation of report.recommendations) {
        console.log(`- ${recommendation}`);
    }

    console.log("\nLayer report:");

    console.table(report.build.layers);

    console.log("\nBuild metrics:");

    console.log({
        image: report.build.image,
        estimatedSizeMB: report.build.totalSize,
        layers: report.build.layers.length,
        cacheHits: report.build.cacheHits,
        cacheMisses: report.build.cacheMisses,
        mergeBlocked: report.mergeBlocked
    });

    console.log("\nSecond build:");

    const second = pipeline.execute(
        SAMPLE_DOCKERFILE,
        "inventory-api:1.1"
    );

    console.log({
        cacheHits: second.build.cacheHits,
        cacheMisses: second.build.cacheMisses
    });

    console.log("\nValidation example:");

    try {
        pipeline.execute(
            "FROM node:latest\nENV API_KEY=secret\nCMD node app.js",
            "unsafe:1"
        );
    } catch (error) {
        console.error(error.message);
    }
}

function main() {
    const args = process.argv.slice(2);

    try {
        if (args.includes("--docker-build")) {
            const context = args[args.indexOf("--docker-build") + 1];
            const dockerfile = args[args.indexOf("--file") + 1];
            const tag = args[args.indexOf("--tag") + 1];

            if (!context || !dockerfile || !tag) {
                throw new DockerError(
                    "Provide context, --file, and --tag."
                );
            }

            console.log(
                DockerCLI.build(context, dockerfile, tag)
            );

            return;
        }

        if (args.includes("--inspect")) {
            const image = args[args.indexOf("--inspect") + 1];

            if (!image) {
                throw new DockerError("Specify an image name.");
            }

            console.log(
                JSON.stringify(
                    DockerCLI.inspect(image),
                    null,
                    2
                )
            );

            return;
        }

        if (args.includes("--analyze")) {
            const file = args[args.indexOf("--analyze") + 1];

            if (!file || !fs.existsSync(file)) {
                throw new DockerError("Dockerfile not found.");
            }

            const source = fs.readFileSync(file, "utf8");

            const pipeline = new DockerPipeline();

            const result = pipeline.execute(
                source,
                "analyzed:local"
            );

            console.log(
                JSON.stringify(result, null, 2)
            );

            return;
        }

        demonstrate();

    } catch (error) {
        console.error(
            `[${error.code || "ERROR"}] ${error.message}`
        );

        process.exitCode = 1;
    }
}

if (require.main === module) {
    main();
}

module.exports = {
    DockerfileParser,
    BuildEngine,
    BuildCache,
    SecurityPolicy,
    OptimizationAnalyzer,
    DockerPipeline,
    DockerCLI
};
