"use strict";

/*
 * Backup architecture model for Node.js.
 *
 * The implementation uses filesystem copies so that the workflow is
 * executable without external packages. A production implementation would
 * normally delegate snapshots to a storage platform capable of atomic,
 * point-in-time snapshots.
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");
const os = require("node:os");

const BackupType = Object.freeze({
  FULL: "full",
  INCREMENTAL: "incremental",
  SNAPSHOT: "snapshot"
});

const BackupStatus = Object.freeze({
  RUNNING: "running",
  COMPLETED: "completed",
  FAILED: "failed",
  EXPIRED: "expired"
});

class BackupError extends Error {
  constructor(message) {
    super(message);
    this.name = "BackupError";
  }
}

class BackupRepository {
  constructor(source, repository) {
    this.source = path.resolve(source);
    this.repository = path.resolve(repository);
    this.catalogPath = path.join(this.repository, "catalog.json");
    this.catalog = new Map();
  }

  async initialize() {
    const sourceStat = await fs.stat(this.source).catch(() => null);

    if (!sourceStat?.isDirectory()) {
      throw new BackupError(`Source directory does not exist: ${this.source}`);
    }

    await fs.mkdir(this.repository, { recursive: true });

    try {
      const text = await fs.readFile(this.catalogPath, "utf8");
      const records = JSON.parse(text);

      for (const record of records) {
        this.catalog.set(record.backupId, record);
      }
    } catch (error) {
      if (error.code !== "ENOENT") {
        throw new BackupError(`Cannot load catalog: ${error.message}`);
      }
    }
  }

  async saveCatalog() {
    const temporary = `${this.catalogPath}.tmp`;
    const content = JSON.stringify(
      [...this.catalog.values()],
      null,
      2
    );

    // Write and rename as one filesystem operation so an interrupted write
    // does not normally leave the active catalog half-written.
    await fs.writeFile(temporary, content, "utf8");
    await fs.rename(temporary, this.catalogPath);
  }

  async hashFile(filePath) {
    const hash = crypto.createHash("sha256");
    const data = await fs.readFile(filePath);
    hash.update(data);
    return hash.digest("hex");
  }

  async inventory() {
    const result = new Map();

    const walk = async (directory) => {
      const entries = await fs.readdir(directory, { withFileTypes: true });

      for (const entry of entries) {
        const absolute = path.join(directory, entry.name);

        if (entry.isDirectory()) {
          await walk(absolute);
          continue;
        }

        if (!entry.isFile()) {
          continue;
        }

        const relative = path
          .relative(this.source, absolute)
          .split(path.sep)
          .join("/");

        const stat = await fs.stat(absolute);

        result.set(relative, {
          relativePath: relative,
          size: stat.size,
          modifiedAt: stat.mtimeMs,
          checksum: await this.hashFile(absolute)
        });
      }
    };

    await walk(this.source);
    return result;
  }

  makeBackupId(type) {
    const timestamp = new Date()
      .toISOString()
      .replace(/[-:.TZ]/g, "");

    return `${type}-${timestamp}-${crypto
      .randomBytes(4)
      .toString("hex")}`;
  }

  async create(type, parentBackupId = null) {
    if (!Object.values(BackupType).includes(type)) {
      throw new BackupError(`Unsupported backup type: ${type}`);
    }

    if (
      type === BackupType.INCREMENTAL &&
      !parentBackupId
    ) {
      const completed = [...this.catalog.values()]
        .filter((r) => r.status === BackupStatus.COMPLETED)
        .sort(
          (a, b) =>
            new Date(a.createdAt) - new Date(b.createdAt)
        );

      parentBackupId = completed.at(-1)?.backupId ?? null;

      if (!parentBackupId) {
        type = BackupType.FULL;
      }
    }

    const backupId = this.makeBackupId(type);
    const destination = path.join(this.repository, backupId);

    await fs.mkdir(destination, { recursive: true });

    const record = {
      backupId,
      backupType: type,
      createdAt: new Date().toISOString(),
      source: this.source,
      destination,
      parentBackupId,
      status: BackupStatus.RUNNING,
      files: [],
      error: null
    };

    this.catalog.set(backupId, record);

    try {
      const current = await this.inventory();
      let selected = [...current.values()];

      if (type === BackupType.INCREMENTAL) {
        const parent = this.catalog.get(parentBackupId);

        if (!parent) {
          throw new BackupError(
            `Parent backup ${parentBackupId} does not exist`
          );
        }

        const previous = new Map(
          parent.files.map((file) => [file.relativePath, file])
        );

        selected = selected.filter((file) => {
          const old = previous.get(file.relativePath);
          return (
            !old ||
            old.size !== file.size ||
            old.checksum !== file.checksum
          );
        });
      }

      for (const file of selected) {
        const sourceFile = path.join(
          this.source,
          ...file.relativePath.split("/")
        );
        const destinationFile = path.join(
          destination,
          ...file.relativePath.split("/")
        );

        await fs.mkdir(path.dirname(destinationFile), {
          recursive: true
        });

        await fs.copyFile(sourceFile, destinationFile);
      }

      record.files = selected;
      record.status = BackupStatus.COMPLETED;

      await this.saveCatalog();
      return record;
    } catch (error) {
      record.status = BackupStatus.FAILED;
      record.error = error.message;
      await this.saveCatalog();
      await fs.rm(destination, {
        recursive: true,
        force: true
      });

      throw new BackupError(
        `Backup failed: ${error.message}`
      );
    }
  }

  async verify(backupId) {
    const record = this.catalog.get(backupId);

    if (!record) {
      throw new BackupError(`Unknown backup: ${backupId}`);
    }

    const problems = [];

    if (record.status !== BackupStatus.COMPLETED) {
      problems.push(`Status is ${record.status}`);
      return { valid: false, problems };
    }

    for (const file of record.files) {
      const target = path.join(
        record.destination,
        ...file.relativePath.split("/")
      );

      try {
        const stat = await fs.stat(target);

        if (stat.size !== file.size) {
          problems.push(`Size mismatch: ${file.relativePath}`);
          continue;
        }

        const checksum = await this.hashFile(target);

        if (checksum !== file.checksum) {
          problems.push(
            `Checksum mismatch: ${file.relativePath}`
          );
        }
      } catch {
        problems.push(`Missing: ${file.relativePath}`);
      }
    }

    return {
      valid: problems.length === 0,
      problems
    };
  }

  async restore(backupId, destination) {
    const record = this.catalog.get(backupId);

    if (!record) {
      throw new BackupError(`Unknown backup: ${backupId}`);
    }

    const chain = [];
    let current = record;

    while (true) {
      chain.unshift(current);

      if (current.backupType === BackupType.FULL) {
        break;
      }

      if (!current.parentBackupId) {
        throw new BackupError(
          "Incremental backup has no full-backup ancestor"
        );
      }

      current = this.catalog.get(current.parentBackupId);

      if (!current) {
        throw new BackupError(
          "Backup chain is incomplete"
        );
      }
    }

    const target = path.resolve(destination);

    if (target === this.source) {
      throw new BackupError(
        "Restore destination cannot be the live source"
      );
    }

    await fs.mkdir(target, { recursive: true });

    for (const backup of chain) {
      for (const file of backup.files) {
        const sourceFile = path.join(
          backup.destination,
          ...file.relativePath.split("/")
        );
        const targetFile = path.join(
          target,
          ...file.relativePath.split("/")
        );

        await fs.mkdir(path.dirname(targetFile), {
          recursive: true
        });

        await fs.copyFile(sourceFile, targetFile);
      }
    }
  }

  async applyRetention(keepFull = 2, keepDays = 14) {
    if (keepFull < 1 || keepDays < 1) {
      throw new BackupError(
        "Retention values must be positive"
      );
    }

    const completed = [...this.catalog.values()]
      .filter((r) => r.status === BackupStatus.COMPLETED)
      .sort(
        (a, b) =>
          new Date(a.createdAt) - new Date(b.createdAt)
      );

    const fulls = completed.filter(
      (r) => r.backupType === BackupType.FULL
    );

    const retainedFulls = new Set(
      fulls.slice(-keepFull).map((r) => r.backupId)
    );

    const cutoff =
      Date.now() - keepDays * 24 * 60 * 60 * 1000;

    const expired = [];

    for (const record of completed) {
      const recent =
        Date.parse(record.createdAt) >= cutoff;

      if (recent || retainedFulls.has(record.backupId)) {
        continue;
      }

      await fs.rm(record.destination, {
        recursive: true,
        force: true
      });

      record.status = BackupStatus.EXPIRED;
      expired.push(record.backupId);
    }

    await this.saveCatalog();
    return expired;
  }
}

async function createDemoFiles(directory) {
  await fs.mkdir(path.join(directory, "service"), {
    recursive: true
  });

  await fs.writeFile(
    path.join(directory, "service", "config.json"),
    JSON.stringify(
      {
        environment: "production",
        backupRequired: true
      },
      null,
      2
    )
  );

  await fs.writeFile(
    path.join(directory, "service", "records.txt"),
    "record-001\nrecord-002\n"
  );
}

async function main() {
  const workspace = await fs.mkdtemp(
    path.join(os.tmpdir(), "backup-demo-")
  );

  const source = path.join(workspace, "source");
  const repository = path.join(
    workspace,
    "backup-repository"
  );

  try {
    await createDemoFiles(source);

    const manager = new BackupRepository(
      source,
      repository
    );

    await manager.initialize();

    const full = await manager.create(BackupType.FULL);
    console.log(
      "Full backup:",
      full.backupId,
      await manager.verify(full.backupId)
    );

    await fs.writeFile(
      path.join(source, "service", "records.txt"),
      "record-001\nrecord-002\nrecord-003\n"
    );

    await fs.writeFile(
      path.join(source, "service", "new.txt"),
      "new record\n"
    );

    const incremental = await manager.create(
      BackupType.INCREMENTAL,
      full.backupId
    );

    console.log(
      "Incremental backup:",
      incremental.backupId,
      "files:",
      incremental.files.length
    );

    const snapshot = await manager.create(
      BackupType.SNAPSHOT
    );

    console.log(
      "Snapshot:",
      snapshot.backupId,
      "files:",
      snapshot.files.length
    );

    const restored = path.join(
      workspace,
      "restored"
    );

    await manager.restore(
      incremental.backupId,
      restored
    );

    console.log(
      "Restored:",
      (
        await fs.readFile(
          path.join(restored, "service", "records.txt"),
          "utf8"
        )
      ).trim()
    );

    const expired = await manager.applyRetention(1, 1);
    console.log("Expired backups:", expired);
  } finally {
    await fs.rm(workspace, {
      recursive: true,
      force: true
    });
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
