"use strict";

/*
 * Event-driven object storage model.
 *
 * Demonstrates bucket-scoped authorization, metadata validation, conditional
 * writes, version-aware deletion, event processing, and lifecycle evaluation.
 *
 * Run with Node.js 18 or later:
 *   node object_storage_events.js
 *
 * The implementation is an in-memory teaching model, not a cloud SDK.
 */

const { createHash, randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");

class StorageError extends Error {}
class AccessDenied extends StorageError {}
class ObjectNotFound extends StorageError {}
class PreconditionFailed extends StorageError {}
class InvalidStorageRequest extends StorageError {}

const Versioning = Object.freeze({
  ENABLED: "Enabled",
  SUSPENDED: "Suspended",
  DISABLED: "Disabled",
});

const StorageClass = Object.freeze({
  STANDARD: "STANDARD",
  INFREQUENT_ACCESS: "INFREQUENT_ACCESS",
  ARCHIVE: "ARCHIVE",
});

const LifecycleAction = Object.freeze({
  TRANSITION: "TRANSITION",
  EXPIRE: "EXPIRE",
  DELETE_NONCURRENT: "DELETE_NONCURRENT",
});

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function validateObjectKey(key) {
  if (typeof key !== "string" || key.length === 0) {
    throw new InvalidStorageRequest("Object key must be a nonempty string.");
  }
  if (key.startsWith("/") || key.includes("\0")) {
    throw new InvalidStorageRequest("Object key must be relative and contain no NUL.");
  }
  if (Buffer.byteLength(key, "utf8") > 1024) {
    throw new InvalidStorageRequest("Object key exceeds 1024 UTF-8 bytes.");
  }
  if (key.split("/").includes("..")) {
    throw new InvalidStorageRequest("Parent-directory segments are prohibited.");
  }
}

function normalizeMetadata(input = {}) {
  const result = Object.create(null);

  for (const [rawName, rawValue] of Object.entries(input)) {
    const name = rawName.toLowerCase();
    if (!/^[a-z0-9-]{1,64}$/.test(name)) {
      throw new InvalidStorageRequest(`Invalid metadata key: ${rawName}`);
    }
    if (typeof rawValue !== "string" || Buffer.byteLength(rawValue) > 2048) {
      throw new InvalidStorageRequest(`Invalid metadata value: ${rawName}`);
    }
    if (Object.hasOwn(result, name)) {
      throw new InvalidStorageRequest(`Duplicate metadata key after normalization: ${name}`);
    }
    result[name] = rawValue;
  }

  return Object.freeze(result);
}

class Bucket {
  constructor({ name, owner, versioning = Versioning.DISABLED }) {
    if (!/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(name)) {
      throw new InvalidStorageRequest(`Invalid bucket name: ${name}`);
    }

    this.name = name;
    this.owner = owner;
    this.versioning = versioning;
    this.policy = [];
    this.objects = new Map();
    this.lifecycleRules = [];
  }
}

class ObjectStorageService extends EventEmitter {
  constructor() {
    super();
    this.buckets = new Map();
    this.audit = [];
    this.sequence = 0;

    // A single event listener centralizes audit handling. Consumers can attach
    // independent listeners for metrics, alerts, or asynchronous processing.
    this.on("storage:event", (event) => {
      this.audit.push(Object.freeze({ ...event }));
    });
  }

  createBucket(name, owner, versioning = Versioning.DISABLED) {
    if (this.buckets.has(name)) {
      throw new InvalidStorageRequest(`Bucket already exists: ${name}`);
    }

    const bucket = new Bucket({ name, owner, versioning });
    this.buckets.set(name, bucket);
    this.emitEvent(owner, "bucket:create", name, null, "ALLOWED");
    return bucket;
  }

  bucket(name) {
    const bucket = this.buckets.get(name);
    if (!bucket) throw new ObjectNotFound(`Bucket not found: ${name}`);
    return bucket;
  }

  emitEvent(principal, action, bucket, key, outcome, details = {}) {
    this.emit("storage:event", {
      eventId: ++this.sequence,
      timestamp: new Date().toISOString(),
      principal: principal.name,
      action,
      bucket,
      key,
      outcome,
      details,
    });
  }

  setPolicy(principal, bucketName, statements) {
    const bucket = this.bucket(bucketName);

    if (principal.name !== bucket.owner.name) {
      throw new AccessDenied("Only the bucket owner can replace this teaching model's policy.");
    }

    for (const statement of statements) {
      if (!["Allow", "Deny"].includes(statement.effect)) {
        throw new InvalidStorageRequest("Policy effect must be Allow or Deny.");
      }
      if (
        !Array.isArray(statement.actions) ||
        !Array.isArray(statement.resources) ||
        !Array.isArray(statement.principals)
      ) {
        throw new InvalidStorageRequest("Policy statements require action, resource, and principal arrays.");
      }
    }

    bucket.policy = statements.map((statement) =>
      Object.freeze({
        effect: statement.effect,
        actions: Object.freeze([...statement.actions]),
        resources: Object.freeze([...statement.resources]),
        principals: Object.freeze([...statement.principals]),
        conditions: Object.freeze({ ...(statement.conditions || {}) }),
      })
    );

    this.emitEvent(principal, "bucket:policy", bucketName, null, "ALLOWED");
  }

  matches(pattern, value) {
    if (pattern === "*") return true;
    if (pattern.endsWith("*")) return value.startsWith(pattern.slice(0, -1));
    return pattern === value;
  }

  isAllowed(principal, bucket, action, key = null, context = {}) {
    if (!principal || principal.authenticated !== true) return false;
    if (principal.name === bucket.owner.name) return true;

    const resource = key === null
      ? `arn:object:${bucket.name}`
      : `arn:object:${bucket.name}/${key}`;

    const matches = bucket.policy.filter((statement) => {
      const principalMatch =
        statement.principals.includes("*") ||
        statement.principals.includes(principal.name) ||
        principal.roles?.some((role) => statement.principals.includes(role));

      const actionMatch = statement.actions.some((item) =>
        this.matches(item, action)
      );
      const resourceMatch = statement.resources.some((item) =>
        this.matches(item, resource)
      );
      const conditionMatch = Object.entries(statement.conditions).every(
        ([name, expected]) => context[name] === expected
      );

      return principalMatch && actionMatch && resourceMatch && conditionMatch;
    });

    if (matches.some((statement) => statement.effect === "Deny")) return false;
    return matches.some((statement) => statement.effect === "Allow");
  }

  requirePermission(principal, bucket, action, key, context = {}) {
    if (!this.isAllowed(principal, bucket, action, key, context)) {
      this.emitEvent(principal || { name: "unknown" }, action, bucket.name, key, "DENIED");
      throw new AccessDenied(`${action} denied for ${principal?.name || "unknown"}`);
    }
  }

  currentVersion(bucket, key) {
    const versions = bucket.objects.get(key) || [];
    const latest = versions[0];
    return !latest || latest.deleteMarker ? null : latest;
  }

  putObject(principal, bucketName, key, payload, options = {}) {
    const bucket = this.bucket(bucketName);
    validateObjectKey(key);

    const body = Buffer.isBuffer(payload)
      ? Buffer.from(payload)
      : typeof payload === "string"
        ? Buffer.from(payload, "utf8")
        : null;

    if (!body) {
      throw new InvalidStorageRequest("Payload must be a string or Buffer.");
    }

    const userMetadata = normalizeMetadata(options.metadata);
    this.requirePermission(principal, bucket, "object:Put", key, options.context);

    const oldCurrent = this.currentVersion(bucket, key);
    if (options.ifNoneMatch === true && oldCurrent) {
      throw new PreconditionFailed("Object already exists.");
    }
    if (options.ifMatch !== undefined &&
        (!oldCurrent || oldCurrent.etag !== options.ifMatch)) {
      throw new PreconditionFailed("ETag does not match the current object.");
    }

    const now = new Date();
    const versionId = bucket.versioning === Versioning.ENABLED
      ? randomUUID()
      : "null";

    const version = {
      key,
      versionId,
      body,
      size: body.length,
      etag: createHash("md5").update(body).digest("hex"),
      sha256: sha256(body),
      contentType: options.contentType || "application/octet-stream",
      metadata: userMetadata,
      createdAt: now,
      noncurrentSince: null,
      storageClass: StorageClass.STANDARD,
      deleteMarker: false,
      retentionUntil: options.retentionDays > 0
        ? new Date(now.getTime() + options.retentionDays * 86400000)
        : null,
    };

    const versions = bucket.objects.get(key) || [];

    if (bucket.versioning === Versioning.ENABLED) {
      for (const item of versions) {
        if (!item.deleteMarker && item.noncurrentSince === null) {
          item.noncurrentSince = now;
        }
      }
      versions.unshift(version);
    } else if (bucket.versioning === Versioning.SUSPENDED) {
      const remaining = versions.filter((item) => item.versionId !== "null");
      for (const item of remaining) {
        if (!item.deleteMarker && item.noncurrentSince === null) {
          item.noncurrentSince = now;
        }
      }
      remaining.unshift(version);
      versions.splice(0, versions.length, ...remaining);
    } else {
      versions.splice(0, versions.length, version);
    }

    bucket.objects.set(key, versions);
    this.emitEvent(principal, "object:put", bucketName, key, "ALLOWED", {
      versionId,
      bytes: body.length,
      sha256: version.sha256,
    });

    return version;
  }

  getObject(principal, bucketName, key, versionId = null) {
    const bucket = this.bucket(bucketName);
    validateObjectKey(key);

    this.requirePermission(
      principal,
      bucket,
      versionId === null ? "object:Get" : "object:GetVersion",
      key
    );

    const versions = bucket.objects.get(key) || [];
    const version = versionId === null
      ? this.currentVersion(bucket, key)
      : versions.find((item) => item.versionId === versionId);

    if (!version || version.deleteMarker) {
      throw new ObjectNotFound(`No retrievable object version for ${key}`);
    }
    if (version.storageClass === StorageClass.ARCHIVE) {
      throw new InvalidStorageRequest("Archived object requires restoration.");
    }

    if (sha256(version.body) !== version.sha256) {
      throw new StorageError("Stored payload failed SHA-256 integrity verification.");
    }

    return {
      body: Buffer.from(version.body),
      versionId: version.versionId,
      contentType: version.contentType,
      metadata: version.metadata,
      etag: version.etag,
    };
  }

  deleteObject(principal, bucketName, key, versionId = null) {
    const bucket = this.bucket(bucketName);
    validateObjectKey(key);

    this.requirePermission(
      principal,
      bucket,
      versionId === null ? "object:Delete" : "object:DeleteVersion",
      key
    );

    const versions = bucket.objects.get(key) || [];
    const now = new Date();

    if (versionId !== null) {
      const index = versions.findIndex((item) => item.versionId === versionId);
      if (index < 0) throw new ObjectNotFound(`Version ${versionId} does not exist.`);

      const target = versions[index];
      if (target.retentionUntil && now < target.retentionUntil) {
        throw new InvalidStorageRequest("Retention policy prevents deletion.");
      }
      versions.splice(index, 1);
    } else if (bucket.versioning === Versioning.ENABLED) {
      for (const item of versions) {
        if (!item.deleteMarker && item.noncurrentSince === null) {
          item.noncurrentSince = now;
        }
      }

      versions.unshift({
        key,
        versionId: randomUUID(),
        body: Buffer.alloc(0),
        size: 0,
        etag: "",
        sha256: "",
        contentType: "application/x-delete-marker",
        metadata: Object.freeze({}),
        createdAt: now,
        noncurrentSince: null,
        storageClass: StorageClass.STANDARD,
        deleteMarker: true,
        retentionUntil: null,
      });
    } else {
      const current = this.currentVersion(bucket, key);
      if (!current) throw new ObjectNotFound(`Object ${key} does not exist.`);
      if (current.retentionUntil && now < current.retentionUntil) {
        throw new InvalidStorageRequest("Retention policy prevents deletion.");
      }
      versions.length = 0;
    }

    if (versions.length === 0) bucket.objects.delete(key);
    this.emitEvent(principal, "object:delete", bucketName, key, "ALLOWED");
  }

  listObjects(principal, bucketName, prefix = "") {
    const bucket = this.bucket(bucketName);
    this.requirePermission(principal, bucket, "bucket:ListObjects", null);

    return [...bucket.objects.keys()]
      .filter((key) => key.startsWith(prefix))
      .sort()
      .map((key) => this.currentVersion(bucket, key))
      .filter(Boolean)
      .map((item) => Object.freeze({
        key: item.key,
        versionId: item.versionId,
        size: item.size,
        storageClass: item.storageClass,
        lastModified: item.createdAt.toISOString(),
      }));
  }

  applyLifecycle(bucketName, now = new Date()) {
    const bucket = this.bucket(bucketName);
    const counts = {
      transitioned: 0,
      expired: 0,
      noncurrentDeleted: 0,
    };

    for (const [key, versions] of bucket.objects) {
      const rules = bucket.lifecycleRules.filter(
        (rule) => rule.enabled !== false && key.startsWith(rule.prefix || "")
      );

      for (const version of [...versions]) {
        if (version.deleteMarker) continue;

        const ageDays = (now - version.createdAt) / 86400000;
        const noncurrentDays = version.noncurrentSince
          ? (now - version.noncurrentSince) / 86400000
          : null;

        for (const rule of rules) {
          if (
            rule.transitionAfterDays !== undefined &&
            ageDays >= rule.transitionAfterDays &&
            version.storageClass === StorageClass.STANDARD
          ) {
            version.storageClass = rule.targetStorageClass || StorageClass.INFREQUENT_ACCESS;
            counts.transitioned++;
          }

          if (
            rule.noncurrentExpireAfterDays !== undefined &&
            noncurrentDays !== null &&
            noncurrentDays >= rule.noncurrentExpireAfterDays
          ) {
            if (!version.retentionUntil || now >= version.retentionUntil) {
              const index = versions.indexOf(version);
              if (index >= 0) versions.splice(index, 1);
              counts.noncurrentDeleted++;
            }
            break;
          }

          const isCurrent = versions[0] === version && version.noncurrentSince === null;
          if (
            isCurrent &&
            rule.expireAfterDays !== undefined &&
            ageDays >= rule.expireAfterDays &&
            (!version.retentionUntil || now >= version.retentionUntil)
          ) {
            if (bucket.versioning === Versioning.ENABLED) {
              version.noncurrentSince = now;
              versions.unshift({
                key,
                versionId: randomUUID(),
                body: Buffer.alloc(0),
                size: 0,
                etag: "",
                sha256: "",
                contentType: "application/x-delete-marker",
                metadata: Object.freeze({}),
                createdAt: now,
                noncurrentSince: null,
                storageClass: StorageClass.STANDARD,
                deleteMarker: true,
                retentionUntil: null,
              });
            } else {
              const index = versions.indexOf(version);
              if (index >= 0) versions.splice(index, 1);
            }
            counts.expired++;
            break;
          }
        }
      }

      if (versions.length === 0) bucket.objects.delete(key);
    }

    this.emitEvent(bucket.owner, "lifecycle:execute", bucketName, null, "ALLOWED", counts);
    return counts;
  }
}

async function demonstrateStorageWorkflow() {
  const storage = new ObjectStorageService();

  const owner = {
    name: "platform-owner",
    roles: ["storage-admin"],
    authenticated: true,
  };
  const developer = {
    name: "report-service",
    roles: ["report-writer"],
    authenticated: true,
  };
  const auditor = {
    name: "audit-reader",
    roles: ["audit"],
    authenticated: true,
  };
  const anonymous = {
    name: "anonymous",
    roles: [],
    authenticated: false,
  };

  const bucket = storage.createBucket(
    "analytics-reports-prod",
    owner,
    Versioning.ENABLED
  );

  storage.setPolicy(owner, bucket.name, [
    {
      effect: "Allow",
      actions: ["object:Get", "object:GetVersion", "object:ListVersions"],
      resources: [`arn:object:${bucket.name}/reports/*`],
      principals: ["audit"],
    },
    {
      effect: "Allow",
      actions: ["object:Get", "object:Put", "object:Delete"],
      resources: [`arn:object:${bucket.name}/reports/*`],
      principals: ["report-writer"],
      conditions: { transport: "tls" },
    },
    {
      effect: "Deny",
      actions: ["object:Delete", "object:DeleteVersion"],
      resources: [`arn:object:${bucket.name}/reports/legal/*`],
      principals: ["*"],
    },
  ]);

  bucket.lifecycleRules = [
    {
      id: "archive-old-reports",
      prefix: "reports/archive/",
      transitionAfterDays: 30,
      targetStorageClass: StorageClass.ARCHIVE,
      noncurrentExpireAfterDays: 180,
      enabled: true,
    },
    {
      id: "temporary-cleanup",
      prefix: "tmp/",
      expireAfterDays: 7,
      enabled: true,
    },
  ];

  const original = storage.putObject(
    developer,
    bucket.name,
    "reports/monthly.json",
    JSON.stringify({ month: "2026-09", incidents: 18 }),
    {
      contentType: "application/json",
      metadata: { department: "operations", classification: "internal" },
      context: { transport: "tls" },
    }
  );

  const revised = storage.putObject(
    developer,
    bucket.name,
    "reports/monthly.json",
    JSON.stringify({ month: "2026-09", incidents: 16 }),
    {
      contentType: "application/json",
      metadata: { department: "operations", revision: "verified" },
      ifMatch: original.etag,
      context: { transport: "tls" },
    }
  );

  console.log("Original version:", original.versionId);
  console.log("Revised version:", revised.versionId);
  console.log("Current objects:", storage.listObjects(owner, bucket.name, "reports/"));

  const historical = storage.getObject(
    auditor,
    bucket.name,
    "reports/monthly.json",
    original.versionId
  );
  console.log("Historical payload:", historical.body.toString("utf8"));

  try {
    storage.putObject(
      developer,
      bucket.name,
      "reports/monthly.json",
      "stale overwrite",
      {
        ifMatch: "not-the-current-etag",
        context: { transport: "tls" },
      }
    );
  } catch (error) {
    if (!(error instanceof PreconditionFailed)) throw error;
    console.log("Conditional update rejected:", error.message);
  }

  try {
    storage.putObject(
      anonymous,
      bucket.name,
      "reports/anonymous.json",
      "unauthorized"
    );
  } catch (error) {
    if (!(error instanceof AccessDenied)) throw error;
    console.log("Anonymous access rejected:", error.message);
  }

  try {
    storage.deleteObject(
      developer,
      bucket.name,
      "reports/legal/retention-record.csv"
    );
  } catch (error) {
    if (!(error instanceof AccessDenied)) throw error;
    console.log("Explicit deny enforced:", error.message);
  }

  storage.deleteObject(developer, bucket.name, "reports/monthly.json", null);
  try {
    storage.getObject(owner, bucket.name, "reports/monthly.json");
  } catch (error) {
    if (!(error instanceof ObjectNotFound)) throw error;
    console.log("Delete marker hides the current key.");
  }

  console.log("Historical version survives:", storage.getObject(
    owner,
    bucket.name,
    "reports/monthly.json",
    revised.versionId
  ).body.toString("utf8"));

  console.log("Audit events:", storage.audit.length);
}

demonstrateStorageWorkflow().catch((error) => {
  console.error("Storage demonstration failed:", error);
  process.exitCode = 1;
});
