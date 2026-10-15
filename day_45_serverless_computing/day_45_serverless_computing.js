"use strict";

/*
 * Serverless event processing with JavaScript-specific mechanisms:
 * asynchronous handlers, event-loop execution, AbortController timeouts,
 * immutable event envelopes, bounded concurrency, and retry classification.
 *
 * Run with Node.js 18 or later:
 *     node serverless_runtime.js
 */

const { performance } = require("node:perf_hooks");
const { randomUUID } = require("node:crypto");

class FunctionConfigurationError extends Error {}
class InvocationTimeoutError extends Error {}
class InvocationRejectedError extends Error {}

function createEvent(source, type, payload) {
  if (typeof source !== "string" || !source.trim()) {
    throw new TypeError("Event source must be a non-empty string.");
  }
  if (typeof type !== "string" || !type.trim()) {
    throw new TypeError("Event type must be a non-empty string.");
  }
  if (
    payload === null ||
    typeof payload !== "object" ||
    Array.isArray(payload)
  ) {
    throw new TypeError("Event payload must be an object.");
  }

  return Object.freeze({
    id: randomUUID(),
    source,
    type,
    payload: Object.freeze({ ...payload }),
    createdAt: Date.now(),
  });
}

function validateConfiguration(config) {
  const requiredPositive = [
    "memoryMb",
    "timeoutMs",
    "maxConcurrency",
    "maxRetries",
  ];

  for (const key of requiredPositive) {
    if (!Number.isFinite(config[key]) || config[key] < 0) {
      throw new FunctionConfigurationError(
        `${key} must be a finite non-negative number.`,
      );
    }
  }

  if (config.memoryMb < 128 || config.timeoutMs === 0) {
    throw new FunctionConfigurationError(
      "Memory must be at least 128 MB and timeout must be positive.",
    );
  }
  if (config.maxConcurrency < 1) {
    throw new FunctionConfigurationError(
      "maxConcurrency must be at least one.",
    );
  }
  if (!Number.isInteger(config.maxRetries)) {
    throw new FunctionConfigurationError(
      "maxRetries must be an integer.",
    );
  }
}

function delay(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new InvocationTimeoutError("Invocation was aborted."));
      return;
    }

    const timer = setTimeout(() => {
      cleanup();
      resolve();
    }, milliseconds);

    function onAbort() {
      clearTimeout(timer);
      cleanup();
      reject(new InvocationTimeoutError("Invocation was aborted."));
    }

    function cleanup() {
      signal?.removeEventListener("abort", onAbort);
    }

    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

class ExecutionEnvironment {
  constructor(id, createdAt) {
    this.id = id;
    this.createdAt = createdAt;
    this.lastUsedAt = createdAt;
    this.invocations = 0;
    this.busy = false;
  }
}

class ServerlessFunction {
  constructor(name, config, handler) {
    if (typeof handler !== "function") {
      throw new TypeError("A function handler is required.");
    }

    this.name = name;
    this.config = {
      memoryMb: 256,
      timeoutMs: 1000,
      initializationMs: 80,
      maxConcurrency: 5,
      maxRetries: 1,
      idleTtlMs: 300_000,
      ...config,
    };

    validateConfiguration(this.config);

    if (
      !Number.isFinite(this.config.initializationMs) ||
      this.config.initializationMs < 0 ||
      !Number.isFinite(this.config.idleTtlMs) ||
      this.config.idleTtlMs < 0
    ) {
      throw new FunctionConfigurationError(
        "Initialization and idle TTL must be finite and non-negative.",
      );
    }

    this.handler = handler;
    this.environments = [];
    this.activeInvocations = 0;
    this.idempotencyStore = new Map();
    this.metrics = {
      invocations: 0,
      successes: 0,
      failures: 0,
      coldStarts: 0,
      timeouts: 0,
      retries: 0,
      throttles: 0,
      durationsMs: [],
    };
  }

  acquireEnvironment() {
    const now = Date.now();

    this.environments = this.environments.filter(
      (environment) =>
        environment.busy ||
        now - environment.lastUsedAt <= this.config.idleTtlMs,
    );

    const idle = this.environments.find(
      (environment) => !environment.busy,
    );

    if (idle) {
      idle.busy = true;
      return { environment: idle, coldStart: false };
    }

    if (this.activeInvocations >= this.config.maxConcurrency) {
      this.metrics.throttles += 1;
      throw new InvocationRejectedError(
        `${this.name} exceeded its concurrency limit.`,
      );
    }

    const environment = new ExecutionEnvironment(
      randomUUID().slice(0, 8),
      now,
    );
    environment.busy = true;
    this.environments.push(environment);

    return { environment, coldStart: true };
  }

  async invoke(event, options = {}) {
    const startedAt = performance.now();
    this.metrics.invocations += 1;

    const key = options.idempotencyKey;
    if (key && this.idempotencyStore.has(key)) {
      this.metrics.successes += 1;
      return {
        success: true,
        deduplicated: true,
        result: this.idempotencyStore.get(key),
        durationMs: 0,
      };
    }

    if (key && options.idempotencyKeyInProgress?.has(key)) {
      throw new InvocationRejectedError(
        "The same idempotency key is already being processed.",
      );
    }

    let attempts = 0;
    let coldStart = false;
    let lastError;

    for (
      let attempt = 0;
      attempt <= this.config.maxRetries;
      attempt += 1
    ) {
      attempts += 1;
      let lease;

      try {
        lease = this.acquireEnvironment();
        this.activeInvocations += 1;

        const { environment } = lease;
        coldStart ||= lease.coldStart;

        if (lease.coldStart) {
          this.metrics.coldStarts += 1;
        }

        const controller = new AbortController();
        const timeout = setTimeout(
          () => controller.abort(),
          this.config.timeoutMs,
        );

        let result;

        try {
          if (lease.coldStart) {
            await delay(
              this.config.initializationMs,
              controller.signal,
            );
          }

          // Promise.race is avoided here because aborting the handler's
          // signal makes cooperative asynchronous work stop when possible.
          // A handler that ignores its signal cannot be forcibly terminated
          // safely in the same Node.js process.
          result = await this.handler(event, {
            functionName: this.name,
            environmentId: environment.id,
            memoryMb: this.config.memoryMb,
            coldStart: lease.coldStart,
            attempt: attempts,
            signal: controller.signal,
          });

          if (controller.signal.aborted) {
            throw new InvocationTimeoutError(
              "Handler exceeded the execution timeout.",
            );
          }
        } finally {
          clearTimeout(timeout);
        }

        environment.invocations += 1;
        environment.lastUsedAt = Date.now();

        if (key) {
          this.idempotencyStore.set(key, result);
        }

        this.metrics.successes += 1;
        const durationMs = performance.now() - startedAt;
        this.metrics.durationsMs.push(durationMs);

        return {
          success: true,
          result,
          attempts,
          coldStart,
          durationMs,
          environmentId: environment.id,
        };
      } catch (error) {
        lastError = error;

        if (error instanceof InvocationTimeoutError) {
          this.metrics.timeouts += 1;
        }

        // Input errors are not transient, so retrying them wastes capacity.
        if (
          error instanceof TypeError ||
          error instanceof FunctionConfigurationError ||
          error instanceof InvocationRejectedError
        ) {
          break;
        }

        if (attempt < this.config.maxRetries) {
          this.metrics.retries += 1;
          await delay(Math.min(25 * 2 ** attempt, 250));
        }
      } finally {
        if (lease) {
          lease.environment.busy = false;
          lease.environment.lastUsedAt = Date.now();
          this.activeInvocations -= 1;
        }
      }
    }

    this.metrics.failures += 1;
    return {
      success: false,
      attempts,
      coldStart,
      durationMs: performance.now() - startedAt,
      error: lastError?.message ?? "Unknown invocation failure",
    };
  }

  snapshot() {
    const durations = [...this.metrics.durationsMs].sort(
      (a, b) => a - b,
    );
    const percentile95 =
      durations.length === 0
        ? 0
        : durations[Math.ceil(durations.length * 0.95) - 1];

    return {
      name: this.name,
      ...this.metrics,
      durationsMs: undefined,
      environmentCount: this.environments.length,
      p95DurationMs: Number(percentile95.toFixed(2)),
      averageDurationMs: Number(
        (
          this.metrics.durationsMs.reduce((sum, value) => sum + value, 0) /
          Math.max(1, this.metrics.durationsMs.length)
        ).toFixed(2),
      ),
    };
  }
}

class EventBus {
  constructor() {
    this.subscribers = new Map();
    this.deadLetters = [];
  }

  subscribe(eventType, serverlessFunction) {
    if (!this.subscribers.has(eventType)) {
      this.subscribers.set(eventType, []);
    }

    this.subscribers.get(eventType).push(serverlessFunction);
  }

  async publish(event) {
    const subscribers = this.subscribers.get(event.type) ?? [];

    if (subscribers.length === 0) {
      this.deadLetters.push({
        eventId: event.id,
        reason: "No matching event subscription.",
      });
      return [];
    }

    // Independent subscribers execute concurrently. Each function has its
    // own capacity limit, so fan-out does not imply unlimited throughput.
    const results = await Promise.all(
      subscribers.map(async (subscriber) => {
        const result = await subscriber.invoke(event, {
          idempotencyKey: event.payload.idempotencyKey,
        });

        if (!result.success) {
          this.deadLetters.push({
            eventId: event.id,
            functionName: subscriber.name,
            reason: result.error,
          });
        }

        return {
          functionName: subscriber.name,
          ...result,
        };
      }),
    );

    return results;
  }
}

async function main() {
  const bus = new EventBus();

  const orderFunction = new ServerlessFunction(
    "order-validation",
    {
      memoryMb: 256,
      timeoutMs: 800,
      initializationMs: 40,
      maxConcurrency: 4,
      maxRetries: 1,
    },
    async (event, context) => {
      await delay(15, context.signal);

      const { orderId, amount } = event.payload;
      if (typeof orderId !== "string" || !orderId.trim()) {
        throw new TypeError("orderId is required.");
      }
      if (!Number.isFinite(amount) || amount <= 0) {
        throw new TypeError("amount must be positive and finite.");
      }

      return {
        orderId,
        amount,
        state: "validated",
        environmentId: context.environmentId,
      };
    },
  );

  const auditFunction = new ServerlessFunction(
    "order-audit",
    {
      memoryMb: 128,
      timeoutMs: 500,
      initializationMs: 15,
      maxConcurrency: 8,
      maxRetries: 0,
    },
    async (event, context) => ({
      eventId: event.id,
      recordedAt: new Date().toISOString(),
      eventType: event.type,
      environmentId: context.environmentId,
    }),
  );

  bus.subscribe("order.created", orderFunction);
  bus.subscribe("order.created", auditFunction);

  const events = [
    createEvent("checkout", "order.created", {
      orderId: "ORD-7001",
      amount: 245.75,
      idempotencyKey: "order:ORD-7001",
    }),
    createEvent("checkout", "order.created", {
      orderId: "ORD-7002",
      amount: 0,
      idempotencyKey: "order:ORD-7002",
    }),
    createEvent("checkout", "order.created", {
      orderId: "ORD-7001",
      amount: 245.75,
      idempotencyKey: "order:ORD-7001",
    }),
  ];

  for (const event of events) {
    const results = await bus.publish(event);
    console.log(
      JSON.stringify(
        {
          eventId: event.id,
          eventType: event.type,
          results,
        },
        null,
        2,
      ),
    );
  }

  console.log("\nFunction metrics");
  console.log(JSON.stringify(orderFunction.snapshot(), null, 2));
  console.log(JSON.stringify(auditFunction.snapshot(), null, 2));
  console.log("\nDead-letter records");
  console.log(JSON.stringify(bus.deadLetters, null, 2));

  console.log("\nConcurrency demonstration");
  const boundedFunction = new ServerlessFunction(
    "bounded-io-task",
    {
      timeoutMs: 1000,
      maxConcurrency: 2,
      maxRetries: 0,
      initializationMs: 0,
    },
    async (_event, context) => {
      await delay(100, context.signal);
      return context.environmentId;
    },
  );

  const concurrentEvents = Array.from({ length: 5 }, (_, index) =>
    createEvent("load-generator", "task.execute", {
      taskId: `TASK-${index + 1}`,
    }),
  );

  const concurrentResults = await Promise.all(
    concurrentEvents.map((event) => boundedFunction.invoke(event)),
  );

  console.log(
    JSON.stringify(
      concurrentResults.map((result) => ({
        success: result.success,
        error: result.error,
        environmentId: result.environmentId,
      })),
      null,
      2,
    ),
  );
  console.log(JSON.stringify(boundedFunction.snapshot(), null, 2));
}

main().catch((error) => {
  console.error("Serverless demonstration failed:", error);
  process.exitCode = 1;
});
