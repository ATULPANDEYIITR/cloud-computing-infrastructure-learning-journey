import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class StorageGovernanceDemo {

    enum StorageType {
        LOCAL_FILE,
        NETWORK_FILE_SYSTEM,
        DISTRIBUTED_FILE_SYSTEM
    }

    enum NodeStatus {
        ONLINE,
        FAILED
    }

    record StoragePolicy(
            StorageType type,
            long quotaBytes,
            int replicationFactor,
            boolean checksumRequired) {

        StoragePolicy {
            Objects.requireNonNull(type);

            if (quotaBytes <= 0) {
                throw new IllegalArgumentException("Quota must be positive");
            }

            if (type == StorageType.DISTRIBUTED_FILE_SYSTEM
                    && replicationFactor < 2) {
                throw new IllegalArgumentException(
                        "Distributed storage requires replication");
            }
        }
    }

    record FileMetadata(
            String path,
            long size,
            String checksum,
            int version) {
    }

    static final class StorageNode {
        private final String id;
        private NodeStatus status = NodeStatus.ONLINE;
        private final Map<String, byte[]> chunks = new HashMap<>();

        StorageNode(String id) {
            this.id = Objects.requireNonNull(id);
        }

        String id() {
            return id;
        }

        NodeStatus status() {
            return status;
        }

        void fail() {
            status = NodeStatus.FAILED;
        }

        void put(String key, byte[] value) {
            if (status == NodeStatus.FAILED) {
                throw new IllegalStateException(
                        "Cannot write to failed node " + id);
            }

            chunks.put(key, value.clone());
        }

        byte[] get(String key) {
            if (status == NodeStatus.FAILED) {
                return null;
            }

            byte[] value = chunks.get(key);
            return value == null ? null : value.clone();
        }
    }

    static final class StorageService {
        private final StoragePolicy policy;
        private final Map<String, FileMetadata> metadata = new HashMap<>();
        private final Map<String, StorageNode> nodes = new HashMap<>();
        private final int chunkSize = 16;

        StorageService(StoragePolicy policy, List<String> nodeIds) {
            this.policy = Objects.requireNonNull(policy);

            for (String nodeId : nodeIds) {
                nodes.put(nodeId, new StorageNode(nodeId));
            }

            if (policy.type() == StorageType.DISTRIBUTED_FILE_SYSTEM
                    && nodes.size() < policy.replicationFactor()) {
                throw new IllegalArgumentException(
                        "Insufficient nodes for replication policy");
            }
        }

        private static String sha256(byte[] data) {
            try {
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                byte[] result = digest.digest(data);

                StringBuilder hex = new StringBuilder();
                for (byte value : result) {
                    hex.append(String.format("%02x", value));
                }

                return hex.toString();
            } catch (NoSuchAlgorithmException error) {
                throw new IllegalStateException(error);
            }
        }

        private List<StorageNode> selectNodes(int chunkIndex) {
            List<StorageNode> online = nodes.values()
                    .stream()
                    .filter(node -> node.status() == NodeStatus.ONLINE)
                    .toList();

            if (online.size() < policy.replicationFactor()) {
                throw new IllegalStateException(
                        "The current node population cannot satisfy "
                                + "the replication policy");
            }

            List<StorageNode> selected = new ArrayList<>();
            int start = chunkIndex % online.size();

            for (int offset = 0;
                 selected.size() < policy.replicationFactor();
                 offset++) {
                selected.add(online.get((start + offset) % online.size()));
            }

            return selected;
        }

        void store(String path, String text) {
            if (path == null || path.isBlank()) {
                throw new IllegalArgumentException(
                        "Storage path must not be blank");
            }

            byte[] data = text.getBytes(StandardCharsets.UTF_8);

            if (data.length > policy.quotaBytes()) {
                throw new IllegalArgumentException(
                        "Object exceeds storage policy quota");
            }

            if (policy.type() != StorageType.DISTRIBUTED_FILE_SYSTEM) {
                StorageNode node = nodes.values()
                        .stream()
                        .findFirst()
                        .orElseThrow(() ->
                                new IllegalStateException(
                                        "No storage endpoint configured"));

                node.put(path, data);

                metadata.put(
                        path,
                        new FileMetadata(
                                path,
                                data.length,
                                sha256(data),
                                metadata.getOrDefault(
                                        path,
                                        new FileMetadata(
                                                path, 0, "", 0))
                                        .version() + 1));

                return;
            }

            int chunkIndex = 0;

            for (int offset = 0;
                 offset < data.length || (data.length == 0 && chunkIndex == 0);
                 offset += chunkSize) {

                int length = Math.min(
                        chunkSize,
                        data.length - offset);

                byte[] chunk = new byte[length];
                System.arraycopy(data, offset, chunk, 0, length);

                String key = path + "#" + chunkIndex;

                for (StorageNode node : selectNodes(chunkIndex)) {
                    node.put(key, chunk);
                }

                chunkIndex++;
            }

            metadata.put(
                    path,
                    new FileMetadata(
                            path,
                            data.length,
                            sha256(data),
                            metadata.getOrDefault(
                                    path,
                                    new FileMetadata(
                                            path, 0, "", 0))
                                    .version() + 1));
        }

        String read(String path) {
            FileMetadata file = metadata.get(path);

            if (file == null) {
                throw new IllegalArgumentException(
                        "Unknown file: " + path);
            }

            if (policy.type() != StorageType.DISTRIBUTED_FILE_SYSTEM) {
                StorageNode node = nodes.values()
                        .stream()
                        .findFirst()
                        .orElseThrow();

                byte[] data = node.get(path);

                if (data == null) {
                    throw new IllegalStateException(
                            "File is unavailable");
                }

                verify(file, data);
                return new String(data, StandardCharsets.UTF_8);
            }

            List<byte[]> chunks = new ArrayList<>();
            int chunkIndex = 0;
            int expectedChunks =
                    file.size() == 0
                            ? 1
                            : (int) Math.ceil(
                                    (double) file.size() / chunkSize);

            while (chunkIndex < expectedChunks) {
                String key = path + "#" + chunkIndex;
                byte[] recovered = null;

                for (StorageNode node : nodes.values()) {
                    recovered = node.get(key);

                    if (recovered != null) {
                        break;
                    }
                }

                if (recovered == null) {
                    throw new IllegalStateException(
                            "No healthy replica for chunk " + chunkIndex);
                }

                chunks.add(recovered);
                chunkIndex++;
            }

            int total = chunks.stream()
                    .mapToInt(bytes -> bytes.length)
                    .sum();

            byte[] complete = new byte[total];
            int offset = 0;

            for (byte[] chunk : chunks) {
                System.arraycopy(
                        chunk, 0, complete, offset, chunk.length);
                offset += chunk.length;
            }

            verify(file, complete);
            return new String(complete, StandardCharsets.UTF_8);
        }

        private void verify(FileMetadata metadata, byte[] data) {
            if (policy.checksumRequired()
                    && !sha256(data).equals(metadata.checksum())) {
                throw new IllegalStateException(
                        "Content integrity verification failed");
            }
        }

        void failNode(String id) {
            StorageNode node = nodes.get(id);

            if (node == null) {
                throw new IllegalArgumentException(
                        "Unknown storage node: " + id);
            }

            node.fail();
        }

        Set<NodeStatus> nodeStatusSet() {
            return EnumSet.copyOf(
                    nodes.values()
                            .stream()
                            .map(StorageNode::status)
                            .toList());
        }
    }

    private static void demonstrateNetworkStorage() {
        StoragePolicy policy = new StoragePolicy(
                StorageType.NETWORK_FILE_SYSTEM,
                10_000,
                1,
                true);

        StorageService service =
                new StorageService(policy, List.of("file-server-01"));

        service.store(
                "/department/research/experiment.txt",
                "A network file system gives multiple clients "
                        + "a shared file-oriented namespace.");

        System.out.println("Network file content:");
        System.out.println(service.read(
                "/department/research/experiment.txt"));
    }

    private static void demonstrateDistributedStorage() {
        StoragePolicy policy = new StoragePolicy(
                StorageType.DISTRIBUTED_FILE_SYSTEM,
                100_000,
                2,
                true);

        StorageService service = new StorageService(
                policy,
                List.of("storage-a", "storage-b", "storage-c"));

        String content =
                "Distributed storage uses multiple nodes to provide "
                        + "partitioning and replication. A client can "
                        + "continue reading while an individual replica "
                        + "node is unavailable.";

        service.store("/datasets/operations.txt", content);

        System.out.println("\nDistributed content:");
        System.out.println(service.read("/datasets/operations.txt"));

        service.failNode("storage-a");

        System.out.println("\nAfter one storage-node failure:");
        System.out.println(service.read("/datasets/operations.txt"));
        System.out.println("Observed node states: "
                + service.nodeStatusSet());

        service.failNode("storage-b");

        try {
            System.out.println(service.read("/datasets/operations.txt"));
        } catch (IllegalStateException error) {
            System.out.println(
                    "Expected availability failure: "
                            + error.getMessage());
        }
    }

    public static void main(String[] args) {
        demonstrateNetworkStorage();
        demonstrateDistributedStorage();
    }
}
