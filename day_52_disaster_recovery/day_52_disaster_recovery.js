#!/usr/bin/env node

"use strict";

/*
 * Disaster Recovery policy and failover simulator.
 *
 * Focus:
 * - RPO and RTO evaluation
 * - backup recovery points
 * - asynchronous health checks
 * - pilot light, warm standby, active-active
 * - failover events
 * - recovery validation
 *
 * Node.js 18+ is sufficient.
 */

const Architecture = Object.freeze({
    PILOT_LIGHT: "pilot-light",
    WARM_STANDBY: "warm-standby",
    ACTIVE_ACTIVE: "active-active"
});

const NodeState = Object.freeze({
    HEALTHY: "healthy",
    FAILED: "failed",
    RECOVERING: "recovering"
});

class RecoveryPolicy {
    constructor({ service, rpoMinutes, rtoMinutes }) {
        if (!service || !service.trim()) {
            throw new Error("Service name is required.");
        }
        if (!Number.isInteger(rpoMinutes) || rpoMinutes < 0) {
            throw new Error("RPO must be a non-negative integer.");
        }
        if (!Number.isInteger(rtoMinutes) || rtoMinutes <= 0) {
            throw new Error("RTO must be a positive integer.");
        }

        this.service = service;
        this.rpoMinutes = rpoMinutes;
        this.rtoMinutes = rtoMinutes;
    }
}

class Backup {
    constructor({ id, createdAt, version, type, checksum }) {
        if (!id || !createdAt || !Number.isInteger(version) || version <= 0) {
            throw new Error("Invalid backup metadata.");
        }
        if (!["FULL", "INCREMENTAL"].includes(type)) {
            throw new Error(`Unsupported backup type: ${type}`);
        }
        if (!checksum) {
            throw new Error("Backup checksum is required.");
        }

        this.id = id;
        this.createdAt = new Date(createdAt);
        this.version = version;
        this.type = type;
        this.checksum = checksum;
    }
}

class BackupRepository {
    constructor(backups = []) {
        this.backups = [];
        for (const backup of backups) {
            this.add(backup);
        }
    }

    add(backup) {
        if (this.backups.some((item) => item.id === backup.id)) {
            throw new Error(`Duplicate backup ID: ${backup.id}`);
        }
        this.backups.push(backup);
        this.backups.sort((a, b) => a.createdAt - b.createdAt);
    }

    latestAtOrBefore(timestamp) {
        const target = new Date(timestamp);

        let selected = null;
        for (const backup of this.backups) {
            if (backup.createdAt <= target) {
                selected = backup;
            }
        }
        return selected;
    }
}

class RecoveryNode {
    constructor({ id, architecture, running = false }) {
        this.id = id;
        this.architecture = architecture;
        this.state = NodeState.HEALTHY;
        this.running = running;
        this.lastSync = null;
    }

    fail() {
        this.state = NodeState.FAILED;
        this.running = false;
    }

    async healthCheck() {
        await new Promise((resolve) => setTimeout(resolve, 25));
        return this.state === NodeState.HEALTHY && this.running;
    }

    async start() {
        if (this.state === NodeState.FAILED) {
            this.state = NodeState.RECOVERING;
        }

        await new Promise((resolve) => setTimeout(resolve, 50));

        this.state = NodeState.HEALTHY;
        this.running = true;
        return true;
    }
}

class DisasterRecoveryController {
    constructor({ policy, architecture, backups, nodes }) {
        this.policy = policy;
        this.architecture = architecture;
        this.backups = backups;
        this.nodes = nodes;
        this.events = [];
    }

    log(event, details = {}) {
        this.events.push({
            timestamp: new Date().toISOString(),
            event,
            details
        });
    }

    calculateRpo(failureTime) {
        const recoveryPoint = this.backups.latestAtOrBefore(failureTime);

        if (!recoveryPoint) {
            return {
                minutes: null,
                recoveryPoint: null
            };
        }

        const milliseconds =
            new Date(failureTime).getTime() -
            recoveryPoint.createdAt.getTime();

        return {
            minutes: Math.floor(milliseconds / 60000),
            recoveryPoint
        };
    }

    estimateRto() {
        switch (this.architecture) {
            case Architecture.PILOT_LIGHT:
                return 45;
            case Architecture.WARM_STANDBY:
                return 18;
            case Architecture.ACTIVE_ACTIVE:
                return 2;
            default:
                throw new Error(`Unsupported architecture: ${this.architecture}`);
        }
    }

    async validateBackup(backup) {
        if (!backup) {
            return false;
        }

        // Production systems should verify the cryptographic checksum,
        // encryption-key availability, object-lock state, and restore integrity.
        return /^sha256:[a-f0-9]{8,}$/i.test(backup.checksum);
    }

    async restore(failureTime) {
        const { minutes, recoveryPoint } = this.calculateRpo(failureTime);

        if (!recoveryPoint) {
            this.log("restore_failed", {
                reason: "No recovery point exists before failure."
            });

            return {
                success: false,
                rpoMinutes: null,
                rtoMinutes: null,
                version: null
            };
        }

        const backupValid = await this.validateBackup(recoveryPoint);

        if (!backupValid) {
            this.log("restore_failed", {
                reason: "Backup integrity validation failed.",
                backupId: recoveryPoint.id
            });

            return {
                success: false,
                rpoMinutes: minutes,
                rtoMinutes: null,
                version: null
            };
        }

        const rtoMinutes = this.estimateRto();

        this.log("restore_completed", {
            backupId: recoveryPoint.id,
            version: recoveryPoint.version,
            rpoMinutes: minutes,
            rtoMinutes
        });

        return {
            success: true,
            rpoMinutes: minutes,
            rtoMinutes,
            version: recoveryPoint.version,
            recoveryPoint: recoveryPoint.createdAt.toISOString()
        };
    }

    async failover(failedNodeId) {
        const failedNode = this.nodes.find((node) => node.id === failedNodeId);

        if (!failedNode) {
            throw new Error(`Unknown node: ${failedNodeId}`);
        }

        failedNode.fail();
        this.log("node_failed", { nodeId: failedNodeId });

        const healthyNodes = [];

        for (const node of this.nodes) {
            if (node.id === failedNodeId) {
                continue;
            }

            if (await node.healthCheck()) {
                healthyNodes.push(node);
            }
        }

        if (this.architecture === Architecture.ACTIVE_ACTIVE) {
            if (healthyNodes.length === 0) {
                this.log("failover_failed", {
                    reason: "No healthy active node remains."
                });
                return false;
            }

            this.log("traffic_shifted", {
                activeNode: healthyNodes[0].id
            });
            return true;
        }

        await failedNode.start();

        this.log("standby_promoted", {
            nodeId: failedNodeId,
            architecture: this.architecture
        });

        return true;
    }

    evaluate(failureTime, restoreResult) {
        const rpoMet =
            restoreResult.success &&
            restoreResult.rpoMinutes !== null &&
            restoreResult.rpoMinutes <= this.policy.rpoMinutes;

        const rtoMet =
            restoreResult.success &&
            restoreResult.rtoMinutes !== null &&
            restoreResult.rtoMinutes <= this.policy.rtoMinutes;

        return {
            service: this.policy.service,
            architecture: this.architecture,
            failureTime: new Date(failureTime).toISOString(),
            rpoTargetMinutes: this.policy.rpoMinutes,
            observedRpoMinutes: restoreResult.rpoMinutes,
            rpoMet,
            rtoTargetMinutes: this.policy.rtoMinutes,
            observedRtoMinutes: restoreResult.rtoMinutes,
            rtoMet,
            recoverySuccessful: restoreResult.success,
            restoredVersion: restoreResult.version
        };
    }
}

function createBackups() {
    return new BackupRepository([
        new Backup({
            id: "full-001",
            createdAt: "2026-10-22T00:00:00Z",
            version: 500,
            type: "FULL",
            checksum: "sha256:abcd1234"
        }),
        new Backup({
            id: "inc-002",
            createdAt: "2026-10-22T00:30:00Z",
            version: 501,
            type: "INCREMENTAL",
            checksum: "sha256:abcd5678"
        }),
        new Backup({
            id: "inc-003",
            createdAt: "2026-10-22T01:00:00Z",
            version: 502,
            type: "INCREMENTAL",
            checksum: "sha256:abcd9012"
        }),
        new Backup({
            id: "inc-004",
            createdAt: "2026-10-22T01:30:00Z",
            version: 503,
            type: "INCREMENTAL",
            checksum: "sha256:abcd3456"
        })
    ]);
}

async function runScenario(architecture, policy) {
    const nodes = [
        new RecoveryNode({
            id: "region-a",
            architecture,
            running: true
        }),
        new RecoveryNode({
            id: "region-b",
            architecture,
            running: architecture === Architecture.ACTIVE_ACTIVE
        })
    ];

    const controller = new DisasterRecoveryController({
        policy,
        architecture,
        backups: createBackups(),
        nodes
    });

    const failureTime = "2026-10-22T01:45:00Z";

    const restoreResult = await controller.restore(failureTime);
    const evaluation = controller.evaluate(failureTime, restoreResult);

    await controller.failover("region-a");

    return {
        evaluation,
        events: controller.events
    };
}

async function main() {
    const scenarios = [
        {
            architecture: Architecture.PILOT_LIGHT,
            policy: new RecoveryPolicy({
                service: "Payments API",
                rpoMinutes: 30,
                rtoMinutes: 60
            })
        },
        {
            architecture: Architecture.WARM_STANDBY,
            policy: new RecoveryPolicy({
                service: "Payments API",
                rpoMinutes: 30,
                rtoMinutes: 30
            })
        },
        {
            architecture: Architecture.ACTIVE_ACTIVE,
            policy: new RecoveryPolicy({
                service: "Payments API",
                rpoMinutes: 5,
                rtoMinutes: 5
            })
        }
    ];

    for (const scenario of scenarios) {
        const result = await runScenario(
            scenario.architecture,
            scenario.policy
        );

        console.log(`\n=== ${scenario.architecture} ===`);
        console.table(result.evaluation);
        console.log("Events:");
        for (const event of result.events) {
            console.log(event);
        }
    }

    try {
        new RecoveryPolicy({
            service: "",
            rpoMinutes: 10,
            rtoMinutes: 20
        });
    } catch (error) {
        console.error(`Validation failure: ${error.message}`);
    }
}

main().catch((error) => {
    console.error(`Fatal recovery simulation error: ${error.message}`);
    process.exitCode = 1;
});
