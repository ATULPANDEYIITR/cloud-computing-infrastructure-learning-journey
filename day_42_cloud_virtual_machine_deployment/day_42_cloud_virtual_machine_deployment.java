import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

public class CloudVmDeployment {

    enum Lifecycle {
        PENDING, RUNNING, STOPPED, FAILED, TERMINATED
    }

    enum ImageStatus {
        AVAILABLE, DEPRECATED, DISABLED
    }

    enum Architecture {
        X86_64, ARM64
    }

    static final class DeploymentException extends RuntimeException {
        DeploymentException(String message) {
            super(message);
        }
    }

    static final class InvalidTransitionException extends DeploymentException {
        InvalidTransitionException(String message) {
            super(message);
        }
    }

    record Image(
        String id,
        String publisher,
        String version,
        Architecture architecture,
        ImageStatus status,
        int minimumDiskGiB,
        boolean trusted
    ) {
        Image {
            Objects.requireNonNull(id);
            Objects.requireNonNull(publisher);
            Objects.requireNonNull(version);
            Objects.requireNonNull(architecture);
            Objects.requireNonNull(status);
            if (minimumDiskGiB < 1) {
                throw new DeploymentException("Image minimum disk must be positive.");
            }
        }

        void validateFor(Architecture requestedArchitecture, int diskGiB) {
            if (status != ImageStatus.AVAILABLE || !trusted) {
                throw new DeploymentException("Image is unavailable or untrusted.");
            }
            if (architecture != requestedArchitecture) {
                throw new DeploymentException("Image architecture mismatch.");
            }
            if (diskGiB < minimumDiskGiB) {
                throw new DeploymentException("Root disk is smaller than the image minimum.");
            }
        }
    }

    record MachineType(
        String name,
        Architecture architecture,
        int vcpus,
        int memoryGiB,
        double hourlyCost
    ) {
        MachineType {
            Objects.requireNonNull(name);
            Objects.requireNonNull(architecture);
            if (vcpus < 1 || memoryGiB < 1 ||
                !Double.isFinite(hourlyCost) || hourlyCost < 0) {
                throw new DeploymentException("Invalid machine type capacity or cost.");
            }
        }
    }

    record SshKey(String name, String publicKey, String fingerprint) {
        private static final Pattern NAME_PATTERN =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,62}");

        SshKey {
            Objects.requireNonNull(name);
            Objects.requireNonNull(publicKey);
            Objects.requireNonNull(fingerprint);
            if (!NAME_PATTERN.matcher(name).matches() || fingerprint.isBlank()) {
                throw new DeploymentException("Invalid SSH key registration.");
            }
            String[] fields = publicKey.trim().split("\\s+");
            if (fields.length < 2 ||
                !(fields[0].equals("ssh-ed25519") ||
                  fields[0].equals("ssh-rsa") ||
                  fields[0].equals("ecdsa-sha2-nistp256"))) {
                throw new DeploymentException("Unsupported SSH public key format.");
            }
        }
    }

    record InboundRule(
        String protocol,
        int fromPort,
        int toPort,
        String sourceCidr,
        String description
    ) {
        InboundRule {
            if (!protocol.equals("tcp") && !protocol.equals("udp")) {
                throw new DeploymentException("Unsupported security-group protocol.");
            }
            if (fromPort < 1 || toPort > 65535 || fromPort > toPort) {
                throw new DeploymentException("Invalid inbound port range.");
            }
            Objects.requireNonNull(sourceCidr);
            if (description == null || description.isBlank()) {
                throw new DeploymentException("Security rules require descriptions.");
            }
            if (protocol.equals("tcp") && fromPort <= 22 && toPort >= 22 &&
                (sourceCidr.equals("0.0.0.0/0") || sourceCidr.equals("::/0"))) {
                throw new DeploymentException("SSH cannot be exposed to the entire internet.");
            }
        }

        boolean covers(String requestedProtocol, int port) {
            return protocol.equals(requestedProtocol) &&
                port >= fromPort && port <= toPort;
        }
    }

    static final class SecurityGroup {
        private final String name;
        private final List<InboundRule> inboundRules;

        SecurityGroup(String name, List<InboundRule> rules) {
            if (name == null || name.isBlank()) {
                throw new DeploymentException("Security group name is required.");
            }
            this.name = name;
            this.inboundRules = List.copyOf(rules);
        }

        String name() {
            return name;
        }

        boolean allows(String protocol, int port, String sourceCidr) {
            // This model expects a caller-supplied CIDR matching a rule exactly.
            return inboundRules.stream().anyMatch(
                rule -> rule.covers(protocol, port) &&
                        rule.sourceCidr().equals(sourceCidr)
            );
        }

        List<InboundRule> rules() {
            return inboundRules;
        }
    }

    record DeploymentPolicy(
        int minimumDiskGiB,
        double maximumHourlyCost,
        boolean requireEncryptedDisk,
        boolean requireTrustedImage,
        boolean requireAdministratorSshRule
    ) {
        DeploymentPolicy {
            if (minimumDiskGiB < 1 || !Double.isFinite(maximumHourlyCost) ||
                maximumHourlyCost < 0) {
                throw new DeploymentException("Invalid deployment policy.");
            }
        }
    }

    record AuditEvent(
        String eventId,
        String instanceId,
        String action,
        Lifecycle previous,
        Lifecycle current,
        Instant occurredAt,
        String detail
    ) {}

    static final class VirtualMachine {
        private static final Map<Lifecycle, Set<Lifecycle>> ALLOWED =
            createTransitions();

        private final String id = "vm-" + UUID.randomUUID().toString().substring(0, 12);
        private final String name;
        private final String region;
        private final Image image;
        private final MachineType machine;
        private final SshKey sshKey;
        private final SecurityGroup securityGroup;
        private final int diskGiB;
        private final boolean encrypted;
        private final Map<String, String> tags;
        private final List<AuditEvent> audit = new ArrayList<>();

        private Lifecycle state = Lifecycle.PENDING;
        private String publicAddress;
        private long revision;

        VirtualMachine(
            String name,
            String region,
            Image image,
            MachineType machine,
            SshKey sshKey,
            SecurityGroup securityGroup,
            int diskGiB,
            boolean encrypted,
            Map<String, String> tags
        ) {
            this.name = name;
            this.region = region;
            this.image = image;
            this.machine = machine;
            this.sshKey = sshKey;
            this.securityGroup = securityGroup;
            this.diskGiB = diskGiB;
            this.encrypted = encrypted;
            this.tags = Collections.unmodifiableMap(new HashMap<>(tags));
            record("creation_requested", null, "Instance accepted for provisioning.");
        }

        private static Map<Lifecycle, Set<Lifecycle>> createTransitions() {
            EnumMap<Lifecycle, Set<Lifecycle>> map = new EnumMap<>(Lifecycle.class);
            map.put(Lifecycle.PENDING, Set.of(
                Lifecycle.RUNNING, Lifecycle.FAILED, Lifecycle.TERMINATED
            ));
            map.put(Lifecycle.RUNNING, Set.of(
                Lifecycle.STOPPED, Lifecycle.FAILED, Lifecycle.TERMINATED
            ));
            map.put(Lifecycle.STOPPED, Set.of(
                Lifecycle.RUNNING, Lifecycle.TERMINATED
            ));
            map.put(Lifecycle.FAILED, Set.of(Lifecycle.TERMINATED));
            map.put(Lifecycle.TERMINATED, Set.of());
            return Collections.unmodifiableMap(map);
        }

        private void record(String action, Lifecycle previous, String detail) {
            audit.add(new AuditEvent(
                UUID.randomUUID().toString(),
                id,
                action,
                previous,
                state,
                Instant.now(),
                detail
            ));
        }

        private void transition(Lifecycle target, String detail) {
            if (!ALLOWED.get(state).contains(target)) {
                throw new InvalidTransitionException(
                    "Cannot transition " + state + " to " + target
                );
            }
            Lifecycle previous = state;
            state = target;
            revision++;
            record("state_changed", previous, detail);
        }

        void boot() {
            transition(Lifecycle.RUNNING, "Boot and health checks succeeded.");
            publicAddress = "192.0.2.60";
        }

        void failBoot(String reason) {
            transition(Lifecycle.FAILED, reason);
            publicAddress = null;
        }

        void stop() {
            transition(Lifecycle.STOPPED, "Operator requested stop.");
            publicAddress = null;
        }

        void start() {
            transition(Lifecycle.RUNNING, "Operator requested restart.");
            publicAddress = "192.0.2.61";
        }

        void terminate() {
            transition(Lifecycle.TERMINATED, "Decommission approved.");
            publicAddress = null;
        }

        double monthlyComputeCost(double hours) {
            if (!Double.isFinite(hours) || hours < 0) {
                throw new DeploymentException("Invalid billing duration.");
            }
            return state == Lifecycle.RUNNING ? machine.hourlyCost() * hours : 0;
        }

        String report() {
            return """
                Instance: %s (%s)
                Region: %s
                Image: %s %s
                Machine: %s, %d vCPU, %d GiB RAM
                Root disk: %d GiB, encrypted=%s
                Security group: %s
                SSH key fingerprint: %s
                State: %s, revision=%d
                Tags: %s
                Estimated monthly compute: $%.2f
                Audit events: %d
                """.formatted(
                    id, name, region, image.id(), image.version(),
                    machine.name(), machine.vcpus(), machine.memoryGiB(),
                    diskGiB, encrypted, securityGroup.name(),
                    sshKey.fingerprint(), state, revision, tags,
                    monthlyComputeCost(730), audit.size()
                );
        }

        String id() {
            return id;
        }

        Lifecycle state() {
            return state;
        }

        List<AuditEvent> auditEvents() {
            return List.copyOf(audit);
        }
    }

    static final class DeploymentService {
        private final Map<String, Image> images = new HashMap<>();
        private final Map<String, MachineType> machines = new HashMap<>();
        private final Map<String, SshKey> keys = new HashMap<>();
        private final Map<String, SecurityGroup> groups = new HashMap<>();
        private final Map<String, VirtualMachine> instances = new HashMap<>();
        private final DeploymentPolicy policy;

        DeploymentService(DeploymentPolicy policy) {
            this.policy = policy;
        }

        void registerImage(Image image) {
            if (images.putIfAbsent(image.id(), image) != null) {
                throw new DeploymentException("Image ID already registered.");
            }
        }

        void registerMachine(MachineType machine) {
            if (machines.putIfAbsent(machine.name(), machine) != null) {
                throw new DeploymentException("Machine type already registered.");
            }
        }

        void registerKey(SshKey key) {
            SshKey existing = keys.putIfAbsent(key.name(), key);
            if (existing != null && !existing.fingerprint().equals(key.fingerprint())) {
                throw new DeploymentException("SSH key name collision.");
            }
        }

        void registerSecurityGroup(SecurityGroup group) {
            groups.put(group.name(), group);
        }

        VirtualMachine deploy(
            String name,
            String region,
            String imageId,
            String machineName,
            String keyName,
            String groupName,
            int diskGiB,
            boolean encrypted,
            Map<String, String> tags,
            boolean simulateBootFailure
        ) {
            if (name == null || !name.matches("[A-Za-z][A-Za-z0-9-]{0,39}")) {
                throw new DeploymentException("Invalid instance name.");
            }

            Image image = Optional.ofNullable(images.get(imageId))
                .orElseThrow(() -> new DeploymentException("Unknown image."));
            MachineType machine = Optional.ofNullable(machines.get(machineName))
                .orElseThrow(() -> new DeploymentException("Unknown machine type."));
            SshKey key = Optional.ofNullable(keys.get(keyName))
                .orElseThrow(() -> new DeploymentException("Unknown SSH key."));
            SecurityGroup group = Optional.ofNullable(groups.get(groupName))
                .orElseThrow(() -> new DeploymentException("Unknown security group."));

            image.validateFor(machine.architecture(), diskGiB);

            if (policy.requireTrustedImage() && !image.trusted()) {
                throw new DeploymentException("Policy requires a trusted image.");
            }
            if (diskGiB < policy.minimumDiskGiB()) {
                throw new DeploymentException("Disk violates enterprise minimum.");
            }
            if (policy.requireEncryptedDisk() && !encrypted) {
                throw new DeploymentException("Encrypted root disk is required.");
            }
            if (machine.hourlyCost() > policy.maximumHourlyCost()) {
                throw new DeploymentException("Machine exceeds the cost ceiling.");
            }
            if (policy.requireAdministratorSshRule() &&
                group.rules().stream().noneMatch(rule ->
                    rule.covers("tcp", 22) &&
                    !rule.sourceCidr().equals("0.0.0.0/0") &&
                    !rule.sourceCidr().equals("::/0"))) {
                throw new DeploymentException("Restricted administrator SSH rule is required.");
            }

            boolean duplicateName = instances.values().stream().anyMatch(vm ->
                vm.name.equals(name) && vm.state() != Lifecycle.TERMINATED
            );
            if (duplicateName) {
                throw new DeploymentException("An active instance already uses this name.");
            }

            VirtualMachine vm = new VirtualMachine(
                name, region, image, machine, key, group,
                diskGiB, encrypted, tags
            );
            instances.put(vm.id(), vm);

            if (simulateBootFailure) {
                vm.failBoot("Image initialization or health check failed.");
            } else {
                vm.boot();
            }
            return vm;
        }

        VirtualMachine instance(String id) {
            return Optional.ofNullable(instances.get(id))
                .orElseThrow(() -> new DeploymentException("Instance not found."));
        }
    }

    public static void main(String[] args) {
        DeploymentPolicy policy = new DeploymentPolicy(
            10, 0.50, true, true, true
        );
        DeploymentService service = new DeploymentService(policy);

        service.registerImage(new Image(
            "ubuntu-2404", "verified-publisher", "24.04",
            Architecture.X86_64, ImageStatus.AVAILABLE, 8, true
        ));
        service.registerImage(new Image(
            "old-image", "verified-publisher", "18.04",
            Architecture.X86_64, ImageStatus.DEPRECATED, 8, true
        ));
        service.registerMachine(new MachineType(
            "general.small", Architecture.X86_64, 2, 4, 0.0416
        ));
        service.registerKey(new SshKey(
            "platform-admin",
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGV4YW1wbGVwdWJsaWNrZXlkYXRh admin",
            "SHA256:demo-fingerprint"
        ));

        SecurityGroup group = new SecurityGroup("staging-web", List.of(
            new InboundRule("tcp", 22, 22, "203.0.113.8/32", "Administrator SSH"),
            new InboundRule("tcp", 443, 443, "0.0.0.0/0", "Public HTTPS")
        ));
        service.registerSecurityGroup(group);

        VirtualMachine vm = service.deploy(
            "staging-api", "us-east-1", "ubuntu-2404",
            "general.small", "platform-admin", "staging-web",
            20, true, Map.of("environment", "staging", "owner", "platform"), false
        );

        System.out.println(vm.report());
        System.out.println("SSH rule matches administrator: " +
            group.allows("tcp", 22, "203.0.113.8/32"));
        System.out.println("SSH rule matches another network: " +
            group.allows("tcp", 22, "198.51.100.0/24"));

        vm.stop();
        System.out.println("Stopped compute estimate: $" + vm.monthlyComputeCost(730));
        vm.start();
        System.out.println("Restarted state: " + vm.state());
        vm.terminate();

        try {
            vm.start();
        } catch (InvalidTransitionException error) {
            System.out.println("Expected lifecycle rejection: " + error.getMessage());
        }

        try {
            service.deploy(
                "unencrypted-api", "us-east-1", "ubuntu-2404",
                "general.small", "platform-admin", "staging-web",
                20, false, Map.of(), false
            );
        } catch (DeploymentException error) {
            System.out.println("Expected enterprise policy rejection: " + error.getMessage());
        }

        VirtualMachine failed = service.deploy(
            "failed-worker", "us-east-1", "ubuntu-2404",
            "general.small", "platform-admin", "staging-web",
            20, true, Map.of("environment", "staging"), true
        );
        System.out.println("Failed deployment state: " + failed.state());
        System.out.println("Failed deployment audit events: " + failed.auditEvents().size());
    }
}
