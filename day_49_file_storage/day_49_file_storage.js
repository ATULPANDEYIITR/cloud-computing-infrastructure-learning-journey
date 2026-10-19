"use strict";

/*
 * File Storage, Network File Systems, and Distributed File Systems
 *
 * This Node.js program focuses on JavaScript-specific event-driven behavior.
 * It models a shared file service as asynchronous operations and uses events
 * to expose storage lifecycle changes without coupling callers to the storage
 * implementation.
 */

const fs = require("fs/promises");
const path = require("path");
const crypto = require("crypto");
const os = require("os");
const { EventEmitter } = require("events");

function checksum(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function validateRelativePath(filePath) {
  if (typeof filePath !== "string" || filePath.trim() === "") {
    throw new TypeError("A non-empty relative path is required");
  }

  const normalized = path.posix.normalize(filePath.replaceAll("\\", "/"));

  if (
    normalized === ".." ||
    normalized.startsWith("../") ||
    path.posix.isAbsolute(normalized)
  ) {
    throw new Error("Path traversal is not permitted");
  }

  return normalized;
}

class LocalFileStore extends EventEmitter {
  constructor(rootDirectory, quotaBytes = Infinity) {
    super();
    this.rootDirectory = rootDirectory;
    this.quotaBytes = quotaBytes;
    this.metadata = new Map();
  }

  async initialize() {
    await fs.mkdir(this.rootDirectory, { recursive: true });
  }

  resolveSafe(relativePath) {
    const safePath = validateRelativePath(relativePath);
    const absolute = path.resolve(this.rootDirectory, safePath);
    const root = path.resolve(this.rootDirectory);

    if (absolute !== root && !absolute.startsWith(`${root}${path.sep}`)) {
      throw new Error("Resolved path escapes storage root");
    }

    return absolute;
  }

  usedBytes() {
    let total = 0;
    for (const metadata of this.metadata.values()) {
      total += metadata.size;
    }
    return total;
  }

  async write(relativePath, content) {
    const safePath = validateRelativePath(relativePath);
    const target = this.resolveSafe(safePath);
    const buffer = Buffer.isBuffer(content)
      ? content
      : Buffer.from(String(content), "utf8");

    const previous = this.metadata.get(safePath);
    const previousSize = previous?.size ?? 0;

    if (
      this.usedBytes() - previousSize + buffer.length >
      this.quotaBytes
    ) {
      throw new Error("Storage quota exceeded");
    }

    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, buffer);

    const record = {
      path: safePath,
      size: buffer.length,
      checksum: checksum(buffer),
      version: (previous?.version ?? 0) + 1,
      modifiedAt: new Date().toISOString(),
    };

    this.metadata.set(safePath, record);
    this.emit("stored", record);
    return record;
  }

  async read(relativePath) {
    const safePath = validateRelativePath(relativePath);
    const expected = this.metadata.get(safePath);

    if (!expected) {
      throw new Error(`File does not exist: ${safePath}`);
    }

    const data = await fs.readFile(this.resolveSafe(safePath));

    if (checksum(data) !== expected.checksum) {
      throw new Error(`Integrity verification failed: ${safePath}`);
    }

    this.emit("read", expected);
    return data;
  }

  async remove(relativePath) {
    const safePath = validateRelativePath(relativePath);

    if (!this.metadata.has(safePath)) {
      throw new Error(`File does not exist: ${safePath}`);
    }

    await fs.rm(this.resolveSafe(safePath));
    const record = this.metadata.get(safePath);
    this.metadata.delete(safePath);
    this.emit("deleted", record);
  }
}

class NetworkFileClient extends EventEmitter {
  constructor(server, artificialLatencyMs = 5) {
    super();
    this.server = server;
    this.artificialLatencyMs = artificialLatencyMs;
  }

  async delay() {
    await new Promise((resolve) =>
      setTimeout(resolve, this.artificialLatencyMs)
    );
  }

  async write(pathName, content) {
    await this.delay();
    const result = await this.server.write(pathName, content);
    this.emit("remote-write", result);
    return result;
  }

  async read(pathName) {
    await this.delay();
    const result = await this.server.read(pathName);
    this.emit("remote-read", { path: pathName, size: result.length });
    return result;
  }
}

class DistributedStore {
  constructor(nodeNames, replicationFactor = 2) {
    if (nodeNames.length === 0) {
      throw new Error("Distributed storage requires at least one node");
    }

    if (
      replicationFactor < 1 ||
      replicationFactor > nodeNames.length
    ) {
      throw new Error("Invalid replication factor");
    }

    this.nodes = new Map(
      nodeNames.map((name) => [name, new Map()])
    );

    this.replicationFactor = replicationFactor;
    this.chunkSize = 12;
    this.metadata = new Map();
  }

  chooseNodes(chunkIndex) {
    const names = [...this.nodes.keys()];
    const start = chunkIndex % names.length;

    return [...names.slice(start), ...names.slice(0, start)].slice(
      0,
      this.replicationFactor
    );
  }

  put(filePath, content) {
    const buffer = Buffer.isBuffer(content)
      ? content
      : Buffer.from(content, "utf8");

    const chunks = [];

    if (buffer.length === 0) {
      chunks.push(Buffer.alloc(0));
    } else {
      for (let offset = 0; offset < buffer.length; offset += this.chunkSize) {
        chunks.push(buffer.subarray(offset, offset + this.chunkSize));
      }
    }

    const fileMetadata = [];

    chunks.forEach((chunk, index) => {
      const replicas = this.chooseNodes(index);
      const key = `${filePath}:${index}`;
      const digest = checksum(chunk);

      for (const node of replicas) {
        this.nodes.get(node).set(key, Buffer.from(chunk));
      }

      fileMetadata.push({
        index,
        key,
        checksum: digest,
        replicas,
      });
    });

    this.metadata.set(filePath, fileMetadata);
  }

  get(filePath) {
    const fileMetadata = this.metadata.get(filePath);

    if (!fileMetadata) {
      throw new Error(`Unknown distributed file: ${filePath}`);
    }

    const chunks = [];

    for (const metadata of fileMetadata) {
      let recovered = null;

      for (const node of metadata.replicas) {
        const storageNode = this.nodes.get(node);
        if (storageNode?.has(metadata.key)) {
          recovered = storageNode.get(metadata.key);
          break;
        }
      }

      if (!recovered) {
        throw new Error(`All replicas unavailable for ${metadata.key}`);
      }

      if (checksum(recovered) !== metadata.checksum) {
        throw new Error(`Corrupt distributed chunk: ${metadata.key}`);
      }

      chunks.push(recovered);
    }

    return Buffer.concat(chunks);
  }

  failNode(nodeName) {
    if (!this.nodes.delete(nodeName)) {
      throw new Error(`Unknown node: ${nodeName}`);
    }
  }

  report(filePath) {
    return (this.metadata.get(filePath) ?? []).map((metadata) => ({
      chunk: metadata.index,
      replicas: metadata.replicas,
      available: metadata.replicas.filter((node) =>
        this.nodes.get(node)?.has(metadata.key)
      ),
    }));
  }
}

async function run() {
  const temporaryRoot = await fs.mkdtemp(
    path.join(os.tmpdir(), "storage-demo-")
  );

  try {
    console.log("=== Local file storage ===");

    const store = new LocalFileStore(
      path.join(temporaryRoot, "shared"),
      4096
    );

    store.on("stored", (record) => {
      console.log(
        `stored event: ${record.path}, version=${record.version}`
      );
    });

    store.on("read", (record) => {
      console.log(`read event: ${record.path}`);
    });

    await store.initialize();

    await store.write(
      "engineering/design.txt",
      "A file-oriented namespace maps names to byte content."
    );

    const localData = await store.read("engineering/design.txt");
    console.log(localData.toString());

    console.log("\n=== Network file access ===");

    const networkClient = new NetworkFileClient(store, 3);

    networkClient.on("remote-write", (record) => {
      console.log(`remote-write event: ${record.path}`);
    });

    await networkClient.write(
      "shared/reports/status.txt",
      "A network filesystem gives remote clients file semantics."
    );

    console.log(
      (await networkClient.read("shared/reports/status.txt")).toString()
    );

    console.log("\n=== Distributed storage ===");

    const distributed = new DistributedStore(
      ["storage-a", "storage-b", "storage-c"],
      2
    );

    const distributedContent =
      "Large objects can be divided into chunks and replicated across storage nodes.";

    distributed.put("logs/application.log", distributedContent);

    console.table(distributed.report("logs/application.log"));

    distributed.failNode("storage-a");

    console.log("After storage-a failure:");
    console.table(distributed.report("logs/application.log"));

    console.log(
      "Recovered content:",
      distributed.get("logs/application.log").toString()
    );

    console.log("\n=== Failure validation ===");

    try {
      await store.read("../private.txt");
    } catch (error) {
      console.log("Traversal rejected:", error.message);
    }

    try {
      await store.write("large.bin", Buffer.alloc(5000));
    } catch (error) {
      console.log("Quota rejection:", error.message);
    }
  } finally {
    await fs.rm(temporaryRoot, { recursive: true, force: true });
  }
}

run().catch((error) => {
  console.error("Storage demonstration failed:", error);
  process.exitCode = 1;
});
