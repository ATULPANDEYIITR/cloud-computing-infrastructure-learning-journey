import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;

public class BackupArchitecture {

    enum BackupType {
        FULL,
        INCREMENTAL,
        SNAPSHOT
    }

    enum BackupStatus {
        RUNNING,
        COMPLETED,
        FAILED,
        EXPIRED
    }

    record FileFingerprint(
        String relativePath,
        long size,
        String checksum,
        Instant modifiedAt
    ) {}

    record RetentionPolicy(
        int minimumFullBackups,
        Duration retentionWindow
    ) {
        RetentionPolicy {
            if (minimumFullBackups < 1) {
                throw new IllegalArgumentException(
                    "At least one full backup is required"
                );
            }

            if (retentionWindow.isNegative()
                || retentionWindow.isZero()) {
                throw new IllegalArgumentException(
                    "Retention window must be positive"
                );
            }
        }
    }

    static final class BackupRecord {
        private final String id;
        private final BackupType type;
        private final Instant createdAt;
        private final Path destination;
        private final String parentBackupId;
        private final List<FileFingerprint> files;

        private BackupStatus status;
        private String error;

        BackupRecord(
            String id,
            BackupType type,
            Instant createdAt,
            Path destination,
            String parentBackupId
        ) {
            this.id = id;
            this.type = type;
            this.createdAt = createdAt;
            this.destination = destination;
            this.parentBackupId = parentBackupId;
            this.files = new ArrayList<>();
            this.status = BackupStatus.RUNNING;
        }

        public String id() {
            return id;
        }

        public BackupType type() {
            return type;
        }

        public Instant createdAt() {
            return createdAt;
        }

        public Path destination() {
            return destination;
        }

        public String parentBackupId() {
            return parentBackupId;
        }

        public List<FileFingerprint> files() {
            return List.copyOf(files);
        }

        public BackupStatus status() {
            return status;
        }

        public String error() {
            return error;
        }

        void complete(Collection<FileFingerprint> selected) {
            files.clear();
            files.addAll(selected);
            status = BackupStatus.COMPLETED;
        }

        void fail(String message) {
            status = BackupStatus.FAILED;
            error = message;
        }

        void expire() {
            status = BackupStatus.EXPIRED;
        }
    }

    static final class BackupException extends RuntimeException {
        BackupException(String message) {
            super(message);
        }

        BackupException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class BackupService {
        private final Path source;
        private final Path repository;
        private final Map<String, BackupRecord> catalog =
            new LinkedHashMap<>();

        BackupService(Path source, Path repository) {
            this.source = source.toAbsolutePath().normalize();
            this.repository = repository.toAbsolutePath().normalize();

            if (!Files.isDirectory(this.source)) {
                throw new BackupException(
                    "Backup source does not exist: " + this.source
                );
            }

            try {
                Files.createDirectories(this.repository);
            } catch (IOException exception) {
                throw new BackupException(
                    "Cannot create backup repository",
                    exception
                );
            }
        }

        private String checksum(Path file) {
            try {
                MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");

                try (var input = Files.newInputStream(file)) {
                    byte[] buffer = new byte[8192];
                    int count;

                    while ((count = input.read(buffer)) != -1) {
                        digest.update(buffer, 0, count);
                    }
                }

                return HexFormat.of().formatHex(
                    digest.digest()
                );
            } catch (
                IOException |
                NoSuchAlgorithmException exception
            ) {
                throw new BackupException(
                    "Unable to calculate file checksum",
                    exception
                );
            }
        }

        private Map<String, FileFingerprint> inventory() {
            try {
                try (var paths = Files.walk(source)) {
                    return paths
                        .filter(Files::isRegularFile)
                        .collect(Collectors.toMap(
                            path -> source
                                .relativize(path)
                                .toString()
                                .replace(
                                    FileSystems
                                        .getDefault()
                                        .getSeparator(),
                                    "/"
                                ),
                            path -> {
                                try {
                                    return new FileFingerprint(
                                        source
                                            .relativize(path)
                                            .toString()
                                            .replace(
                                                FileSystems
                                                    .getDefault()
                                                    .getSeparator(),
                                                "/"
                                            ),
                                        Files.size(path),
                                        checksum(path),
                                        Files.getLastModifiedTime(path)
                                            .toInstant()
                                    );
                                } catch (IOException exception) {
                                    throw new BackupException(
                                        "Cannot inspect " + path,
                                        exception
                                    );
                                }
                            },
                            (left, right) -> right,
                            LinkedHashMap::new
                        ));
                }
            } catch (IOException exception) {
                throw new BackupException(
                    "Cannot inventory source",
                    exception
                );
            }
        }

        private String newBackupId(BackupType type) {
            return type.name().toLowerCase(Locale.ROOT)
                + "-"
                + Instant.now().toString()
                    .replace(":", "")
                + "-"
                + UUID.randomUUID();
        }

        BackupRecord createFull() {
            return create(BackupType.FULL, null);
        }

        BackupRecord createSnapshot() {
            return create(BackupType.SNAPSHOT, null);
        }

        BackupRecord createIncremental() {
            Optional<BackupRecord> parent =
                catalog.values()
                    .stream()
                    .filter(record ->
                        record.status()
                            == BackupStatus.COMPLETED)
                    .max(
                        Comparator.comparing(
                            BackupRecord::createdAt
                        )
                    );

            return parent.isEmpty()
                ? createFull()
                : create(
                    BackupType.INCREMENTAL,
                    parent.get().id()
                );
        }

        private BackupRecord create(
            BackupType type,
            String parentId
        ) {
            String id = newBackupId(type);
            Path destination = repository.resolve(id);

            try {
                Files.createDirectories(destination);
            } catch (IOException exception) {
                throw new BackupException(
                    "Cannot create backup directory",
                    exception
                );
            }

            BackupRecord record = new BackupRecord(
                id,
                type,
                Instant.now(),
                destination,
                parentId
            );

            catalog.put(id, record);

            try {
                Map<String, FileFingerprint> current =
                    inventory();

                Collection<FileFingerprint> selected =
                    current.values();

                if (type == BackupType.INCREMENTAL) {
                    BackupRecord parent =
                        catalog.get(parentId);

                    if (parent == null) {
                        throw new BackupException(
                            "Incremental parent does not exist"
                        );
                    }

                    Map<String, FileFingerprint> previous =
                        parent.files()
                            .stream()
                            .collect(Collectors.toMap(
                                FileFingerprint::relativePath,
                                item -> item
                            ));

                    selected = current.values()
                        .stream()
                        .filter(item -> {
                            FileFingerprint old =
                                previous.get(
                                    item.relativePath()
                                );

                            return old == null
                                || old.size() != item.size()
                                || !old.checksum().equals(
                                    item.checksum()
                                );
                        })
                        .toList();
                }

                for (FileFingerprint file : selected) {
                    Path sourceFile =
                        source.resolve(
                            file.relativePath()
                                .replace(
                                    "/",
                                    FileSystems
                                        .getDefault()
                                        .getSeparator()
                                )
                        );

                    Path targetFile =
                        destination.resolve(
                            file.relativePath()
                                .replace(
                                    "/",
                                    FileSystems
                                        .getDefault()
                                        .getSeparator()
                                )
                        );

                    Files.createDirectories(
                        targetFile.getParent()
                    );

                    Files.copy(
                        sourceFile,
                        targetFile,
                        StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.COPY_ATTRIBUTES
                    );
                }

                record.complete(selected);
                return record;
            } catch (Exception exception) {
                record.fail(exception.getMessage());
                deleteTree(destination);

                throw new BackupException(
                    "Backup failed: " + exception.getMessage(),
                    exception
                );
            }
        }

        boolean verify(String backupId) {
            BackupRecord record = requireBackup(backupId);

            if (record.status()
                != BackupStatus.COMPLETED) {
                return false;
            }

            for (FileFingerprint expected : record.files()) {
                Path path =
                    record.destination().resolve(
                        expected.relativePath()
                            .replace(
                                "/",
                                FileSystems
                                    .getDefault()
                                    .getSeparator()
                            )
                    );

                try {
                    if (!Files.exists(path)
                        || Files.size(path) != expected.size()
                        || !checksum(path).equals(
                            expected.checksum()
                        )) {
                        return false;
                    }
                } catch (IOException exception) {
                    return false;
                }
            }

            return true;
        }

        void restore(
            String backupId,
            Path destination
        ) {
            BackupRecord selected =
                requireBackup(backupId);

            Path target =
                destination.toAbsolutePath().normalize();

            if (target.equals(source)) {
                throw new BackupException(
                    "Restore cannot overwrite source"
                );
            }

            List<BackupRecord> chain = new ArrayList<>();
            BackupRecord current = selected;

            while (true) {
                chain.add(current);

                if (current.type() == BackupType.FULL) {
                    break;
                }

                if (current.parentBackupId() == null) {
                    throw new BackupException(
                        "Incomplete backup chain"
                    );
                }

                current =
                    requireBackup(
                        current.parentBackupId()
                    );
            }

            Collections.reverse(chain);

            try {
                Files.createDirectories(target);

                for (BackupRecord backup : chain) {
                    for (FileFingerprint file :
                        backup.files()) {

                        Path sourceFile =
                            backup.destination().resolve(
                                file.relativePath()
                                    .replace(
                                        "/",
                                        FileSystems
                                            .getDefault()
                                            .getSeparator()
                                    )
                            );

                        Path targetFile =
                            target.resolve(
                                file.relativePath()
                                    .replace(
                                        "/",
                                        FileSystems
                                            .getDefault()
                                            .getSeparator()
                                    )
                            );

                        Files.createDirectories(
                            targetFile.getParent()
                        );

                        Files.copy(
                            sourceFile,
                            targetFile,
                            StandardCopyOption.REPLACE_EXISTING,
                            StandardCopyOption.COPY_ATTRIBUTES
                        );
                    }
                }
            } catch (IOException exception) {
                throw new BackupException(
                    "Restore failed",
                    exception
                );
            }
        }

        List<String> applyRetention(
            RetentionPolicy policy
        ) {
            Instant cutoff =
                Instant.now()
                    .minus(policy.retentionWindow());

            List<BackupRecord> fulls =
                catalog.values()
                    .stream()
                    .filter(record ->
                        record.type() == BackupType.FULL
                        && record.status()
                            == BackupStatus.COMPLETED)
                    .sorted(
                        Comparator.comparing(
                            BackupRecord::createdAt
                        ).reversed()
                    )
                    .toList();

            Set<String> protectedFulls =
                fulls.stream()
                    .limit(policy.minimumFullBackups())
                    .map(BackupRecord::id)
                    .collect(Collectors.toSet());

            List<String> expired = new ArrayList<>();

            for (BackupRecord record : catalog.values()) {
                if (record.status()
                    != BackupStatus.COMPLETED) {
                    continue;
                }

                boolean recent =
                    !record.createdAt().isBefore(cutoff);

                boolean protectedFull =
                    protectedFulls.contains(record.id());

                if (!recent && !protectedFull) {
                    deleteTree(record.destination());
                    record.expire();
                    expired.add(record.id());
                }
            }

            return expired;
        }

        private BackupRecord requireBackup(String id) {
            BackupRecord record = catalog.get(id);

            if (record == null) {
                throw new BackupException(
                    "Unknown backup: " + id
                );
            }

            return record;
        }

        private static void deleteTree(Path root) {
            if (!Files.exists(root)) {
                return;
            }

            try (var paths = Files.walk(root)) {
                paths.sorted(Comparator.reverseOrder())
                    .forEach(path -> {
                        try {
                            Files.deleteIfExists(path);
                        } catch (IOException exception) {
                            throw new BackupException(
                                "Cannot delete " + path,
                                exception
                            );
                        }
                    });
            } catch (IOException exception) {
                throw new BackupException(
                    "Cannot clean backup directory",
                    exception
                );
            }
        }
    }

    private static void createDemoData(Path source)
        throws IOException {

        Files.createDirectories(
            source.resolve("database")
        );

        Files.createDirectories(
            source.resolve("application")
        );

        Files.writeString(
            source.resolve("database/records.txt"),
            "customer-001\ncustomer-002\n"
        );

        Files.writeString(
            source.resolve("application/config.txt"),
            "environment=production\nbackupRequired=true\n"
        );
    }

    public static void main(String[] args)
        throws Exception {

        Path workspace = Files.createTempDirectory(
            "backup-architecture-"
        );

        try {
            Path source =
                workspace.resolve("live-data");

            Path repository =
                workspace.resolve("backup-repository");

            createDemoData(source);

            BackupService service =
                new BackupService(
                    source,
                    repository
                );

            BackupRecord full =
                service.createFull();

            System.out.println(
                "FULL verified=" +
                service.verify(full.id())
            );

            Files.writeString(
                source.resolve("database/records.txt"),
                "customer-001\ncustomer-002\ncustomer-003\n"
            );

            Files.writeString(
                source.resolve("application/audit.log"),
                "backup-created\n"
            );

            BackupRecord incremental =
                service.createIncremental();

            System.out.println(
                "INCREMENTAL files=" +
                incremental.files().size()
            );

            BackupRecord snapshot =
                service.createSnapshot();

            System.out.println(
                "SNAPSHOT files=" +
                snapshot.files().size()
            );

            Path restored =
                workspace.resolve("restored");

            service.restore(
                incremental.id(),
                restored
            );

            System.out.println(
                "RESTORED:");
            System.out.println(
                Files.readString(
                    restored.resolve(
                        "database/records.txt"
                    )
                ).trim()
            );

            List<String> expired =
                service.applyRetention(
                    new RetentionPolicy(
                        1,
                        Duration.ofDays(1)
                    )
                );

            System.out.println(
                "EXPIRED=" + expired.size()
            );
        } finally {
            BackupService.deleteTree(workspace);
        }
    }
}
