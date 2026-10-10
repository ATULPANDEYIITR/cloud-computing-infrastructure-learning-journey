import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Enterprise virtual infrastructure management model.
 *
 * Demonstrates explicit domain types, resource quotas, access control,
 * environment isolation, lifecycle policies, and merge-free infrastructure
 * provisioning through Java 17 standard-library features.
 *
 * Compile:
 *   javac VirtualInfrastructure.java
 *
 * Run:
 *   java VirtualInfrastructure
 *
 * No real VM, network interface, disk, or hypervisor is created.
 */
public class VirtualInfrastructure {

    enum Role {
        VIEWER,
        OPERATOR,
        ADMIN
    }

    enum VmState {
        STOPPED,
        RUNNING,
        SUSPENDED,
        TERMINATED
    }

    enum EnvironmentState {
        ACTIVE,
        SUSPENDED,
        DELETED
    }

    enum Permission {
        READ,
        OPERATE,
        ADMINISTER
    }

    static class InfrastructureException extends RuntimeException {
        InfrastructureException(String message) {
            super(message);
        }
    }

    static class AuthorizationException extends InfrastructureException {
        AuthorizationException(String message) {
            super(message);
        }
    }

    static class CapacityException extends InfrastructureException {
        CapacityException(String message) {
            super(message);
        }
    }

    static class InvalidStateException extends InfrastructureException {
        InvalidStateException(String message) {
            super(message);
        }
    }

    static class NotFoundException extends InfrastructureException {
        NotFoundException(String message) {
            super(message);
        }
    }

    record ResourceRequest(int vcpus, long memoryMiB) {
        ResourceRequest {
            if (vcpus < 1 || vcpus > 128) {
                throw new IllegalArgumentException("vCPUs must be between 1 and 128");
            }
            if (memoryMiB < 128 || memoryMiB > 1_048_576) {
                throw new IllegalArgumentException("Memory is outside supported limits");
            }
        }
    }

    record ResourceQuota(
        int maxVMs,
        int maxVcpus,
        long maxMemoryMiB,
        long maxStorageGiB
    ) {
        ResourceQuota {
            if (maxVMs < 1 || maxVcpus < 1 ||
                maxMemoryMiB < 128 || maxStorageGiB < 1) {
                throw new IllegalArgumentException("Invalid environment quota");
            }
        }
    }

    record AuditEvent(
        Instant timestamp,
        String actor,
        String action,
        String resourceType,
        String resourceId,
        String outcome,
        String details
    ) {}

    static final class AccessPolicy {
        private final Map<Role, Set<Permission>> grants =
            new EnumMap<>(Role.class);

        AccessPolicy() {
            grants.put(Role.VIEWER, Set.of(Permission.READ));
            grants.put(
                Role.OPERATOR,
                Set.of(Permission.READ, Permission.OPERATE)
            );
            grants.put(
                Role.ADMIN,
                Set.of(
                    Permission.READ,
                    Permission.OPERATE,
                    Permission.ADMINISTER
                )
            );
        }

        void require(User user, Permission permission) {
            if (!user.enabled()) {
                throw new AuthorizationException("User account is disabled");
            }
            if (!grants.get(user.role()).contains(permission)) {
                throw new AuthorizationException(
                    "Role " + user.role() + " cannot perform " + permission
                );
            }
        }
    }

    static final class User {
        private final String username;
        private final Role role;
        private final Set<String> environmentIds = new HashSet<>();
        private boolean enabled = true;

        User(String username, Role role) {
            this.username = requireIdentifier(username, "username");
            this.role = Objects.requireNonNull(role);
        }

        String username() {
            return username;
        }

        Role role() {
            return role;
        }

        boolean enabled() {
            return enabled;
        }

        void disable() {
            enabled = false;
        }

        void grantEnvironment(String environmentId) {
            environmentIds.add(environmentId);
        }

        boolean canAccess(String environmentId) {
            return environmentIds.contains(environmentId);
        }
    }

    static final class Environment {
        private final String id;
        private final String name;
        private final ResourceQuota quota;
        private final Set<String> vmIds = new HashSet<>();
        private final Set<String> networkIds = new HashSet<>();
        private final Set<String> poolIds = new HashSet<>();
        private EnvironmentState state = EnvironmentState.ACTIVE;

        Environment(String id, String name, ResourceQuota quota) {
            this.id = requireIdentifier(id, "environment id");
            this.name = Objects.requireNonNull(name);
            this.quota = Objects.requireNonNull(quota);
        }

        String id() {
            return id;
        }

        String name() {
            return name;
        }

        ResourceQuota quota() {
            return quota;
        }

        EnvironmentState state() {
            return state;
        }

        void requireActive() {
            if (state != EnvironmentState.ACTIVE) {
                throw new InvalidStateException(
                    "Environment " + id + " is not active"
                );
            }
        }
    }

    static final class Network {
        private final String id;
        private final String environmentId;
        private final String cidr;
        private final String gateway;
        private final int vlanId;
        private final Map<String, String> allocations = new HashMap<>();

        Network(
            String id,
            String environmentId,
            String cidr,
            String gateway,
            int vlanId
        ) {
            this.id = requireIdentifier(id, "network id");
            this.environmentId = environmentId;
            this.cidr = Objects.requireNonNull(cidr);
            this.gateway = Objects.requireNonNull(gateway);
            if (vlanId < 1 || vlanId > 4094) {
                throw new IllegalArgumentException("Invalid VLAN ID");
            }
            this.vlanId = vlanId;

            // This model validates basic subnet form; a production IPAM service
            // must also perform overlap checks and full CIDR arithmetic.
            if (!cidr.matches("(\\d{1,3}\\.){3}\\d{1,3}/\\d{1,2}")) {
                throw new IllegalArgumentException("Invalid IPv4 CIDR");
            }
            if (!gateway.matches("(\\d{1,3}\\.){3}\\d{1,3}")) {
                throw new IllegalArgumentException("Invalid IPv4 gateway");
            }
        }

        String id() {
            return id;
        }

        String environmentId() {
            return environmentId;
        }

        String allocateAddress(String vmId) {
            return allocations.computeIfAbsent(vmId, ignored -> {
                // The example uses a deterministic test subnet.
                // Real allocation belongs in a validated IP address manager.
                for (int host = 10; host < 255; host++) {
                    String candidate = "10.80.1." + host;
                    if (!candidate.equals(gateway) &&
                        !allocations.containsValue(candidate)) {
                        return candidate;
                    }
                }
                throw new CapacityException("No available IP addresses");
            });
        }

        void releaseAddress(String vmId) {
            allocations.remove(vmId);
        }
    }

    static final class StoragePool {
        private final String id;
        private final String environmentId;
        private final long capacityGiB;
        private final Map<String, Long> volumes = new HashMap<>();

        StoragePool(String id, String environmentId, long capacityGiB) {
            this.id = requireIdentifier(id, "storage pool id");
            this.environmentId = environmentId;
            if (capacityGiB < 1) {
                throw new IllegalArgumentException("Storage capacity must be positive");
            }
            this.capacityGiB = capacityGiB;
        }

        String id() {
            return id;
        }

        String environmentId() {
            return environmentId;
        }

        long capacityGiB() {
            return capacityGiB;
        }

        long usedGiB() {
            return volumes.values().stream().mapToLong(Long::longValue).sum();
        }

        long availableGiB() {
            return capacityGiB - usedGiB();
        }
    }

    static final class Volume {
        private final String id;
        private final String environmentId;
        private final String poolId;
        private final long sizeGiB;
        private final boolean encrypted;
        private String attachedVmId;

        Volume(
            String id,
            String environmentId,
            String poolId,
            long sizeGiB,
            boolean encrypted
        ) {
            this.id = requireIdentifier(id, "volume id");
            this.environmentId = environmentId;
            this.poolId = poolId;
            if (sizeGiB < 1) {
                throw new IllegalArgumentException("Volume size must be positive");
            }
            this.sizeGiB = sizeGiB;
            this.encrypted = encrypted;
        }

        String id() {
            return id;
        }

        long sizeGiB() {
            return sizeGiB;
        }

        String attachedVmId() {
            return attachedVmId;
        }
    }

    static final class VirtualMachine {
        private final String id;
        private final String environmentId;
        private final String name;
        private final String image;
        private final ResourceRequest resources;
        private final String networkId;
        private final Set<String> volumeIds = new HashSet<>();
        private final Instant createdAt = Instant.now();

        private String ipAddress;
        private VmState state = VmState.STOPPED;

        VirtualMachine(
            String id,
            String environmentId,
            String name,
            String image,
            ResourceRequest resources,
            String networkId,
            String ipAddress
        ) {
            this.id = requireIdentifier(id, "VM id");
            this.environmentId = environmentId;
            this.name = Objects.requireNonNull(name);
            this.image = Objects.requireNonNull(image);
            this.resources = Objects.requireNonNull(resources);
            this.networkId = networkId;
            this.ipAddress = ipAddress;

            if (image.isBlank() || image.length() > 256) {
                throw new IllegalArgumentException("Invalid image reference");
            }
        }

        String id() {
            return id;
        }

        String environmentId() {
            return environmentId;
        }

        VmState state() {
            return state;
        }

        ResourceRequest resources() {
            return resources;
        }

        String ipAddress() {
            return ipAddress;
        }

        Set<String> volumeIds() {
            return Set.copyOf(volumeIds);
        }

        void transition(String action) {
            switch (action) {
                case "start" -> {
                    if (state != VmState.STOPPED && state != VmState.SUSPENDED) {
                        throw new InvalidStateException(
                            "Cannot start VM from " + state
                        );
                    }
                    state = VmState.RUNNING;
                }
                case "stop" -> {
                    if (state != VmState.RUNNING) {
                        throw new InvalidStateException(
                            "Only a running VM can be stopped"
                        );
                    }
                    state = VmState.STOPPED;
                }
                case "suspend" -> {
                    if (state != VmState.RUNNING) {
                        throw new InvalidStateException(
                            "Only a running VM can be suspended"
                        );
                    }
                    state = VmState.SUSPENDED;
                }
                case "terminate" -> {
                    if (state == VmState.TERMINATED) {
                        throw new InvalidStateException("VM is already terminated");
                    }
                    state = VmState.TERMINATED;
                    ipAddress = null;
                }
                default -> throw new IllegalArgumentException(
                    "Unknown lifecycle action: " + action
                );
            }
        }
    }

    static final class InfrastructureService {
        private static final Pattern IDENTIFIER =
            Pattern.compile("[A-Za-z][A-Za-z0-9_-]{1,62}");

        private final AccessPolicy accessPolicy = new AccessPolicy();
        private final Map<String, User> users = new HashMap<>();
        private final Map<String, Environment> environments = new HashMap<>();
        private final Map<String, Network> networks = new HashMap<>();
        private final Map<String, StoragePool> pools = new HashMap<>();
        private final Map<String, VirtualMachine> vms = new HashMap<>();
        private final Map<String, Volume> volumes = new HashMap<>();
        private final List<AuditEvent> audit = new ArrayList<>();

        private static String requireIdentifier(String value, String field) {
            if (value == null || !IDENTIFIER.matcher(value).matches()) {
                throw new IllegalArgumentException("Invalid " + field);
            }
            return value;
        }

        private void record(
            String actor,
            String action,
            String resourceType,
            String resourceId,
            String outcome,
            String details
        ) {
            audit.add(new AuditEvent(
                Instant.now(), actor, action, resourceType,
                resourceId, outcome, details
            ));
        }

        private User requireUser(String username) {
            User user = users.get(username);
            if (user == null) {
                throw new NotFoundException("User does not exist: " + username);
            }
            return user;
        }

        private Environment requireEnvironment(String environmentId) {
            Environment environment = environments.get(environmentId);
            if (environment == null) {
                throw new NotFoundException(
                    "Environment does not exist: " + environmentId
                );
            }
            environment.requireActive();
            return environment;
        }

        private void authorize(
            String actor,
            Permission permission,
            String environmentId
        ) {
            User user = requireUser(actor);
            accessPolicy.require(user, permission);

            if (environmentId != null &&
                user.role() != Role.ADMIN &&
                !user.canAccess(environmentId)) {
                throw new AuthorizationException(
                    "Access denied to environment " + environmentId
                );
            }
        }

        void addUser(String username, Role role) {
            requireIdentifier(username, "username");
            if (users.containsKey(username)) {
                throw new InfrastructureException("User already exists");
            }
            users.put(username, new User(username, role));
        }

        void createEnvironment(
            String actor,
            String id,
            String name,
            ResourceQuota quota
        ) {
            authorize(actor, Permission.ADMINISTER, null);
            requireIdentifier(id, "environment id");
            if (environments.containsKey(id)) {
                throw new InfrastructureException("Environment already exists");
            }

            Environment environment = new Environment(id, name, quota);
            environments.put(id, environment);
            requireUser(actor).grantEnvironment(id);
            record(actor, "create_environment", "environment", id, "success", "");
        }

        void grantAccess(String actor, String username, String environmentId) {
            authorize(actor, Permission.ADMINISTER, null);
            requireEnvironment(environmentId);
            requireUser(username).grantEnvironment(environmentId);
            record(
                actor, "grant_access", "environment",
                environmentId, "success", "user=" + username
            );
        }

        void createNetwork(
            String actor,
            String environmentId,
            String id,
            String cidr,
            String gateway,
            int vlanId
        ) {
            authorize(actor, Permission.ADMINISTER, environmentId);
            Environment environment = requireEnvironment(environmentId);

            Network network = new Network(id, environmentId, cidr, gateway, vlanId);
            if (networks.containsKey(id)) {
                throw new InfrastructureException("Network already exists");
            }

            networks.put(id, network);
            environment.networkIds.add(id);
            record(actor, "create_network", "network", id, "success", cidr);
        }

        void createStoragePool(
            String actor,
            String environmentId,
            String id,
            long capacityGiB
        ) {
            authorize(actor, Permission.ADMINISTER, environmentId);
            Environment environment = requireEnvironment(environmentId);

            long allocatedCapacity = environment.poolIds.stream()
                .map(pools::get)
                .mapToLong(StoragePool::capacityGiB)
                .sum();

            if (allocatedCapacity + capacityGiB > environment.quota.maxStorageGiB()) {
                throw new CapacityException("Environment storage quota exceeded");
            }

            StoragePool pool = new StoragePool(id, environmentId, capacityGiB);
            if (pools.putIfAbsent(id, pool) != null) {
                throw new InfrastructureException("Storage pool already exists");
            }

            environment.poolIds.add(id);
            record(actor, "create_storage_pool", "storage_pool", id, "success", "");
        }

        VirtualMachine createVM(
            String actor,
            String environmentId,
            String id,
            String name,
            String image,
            ResourceRequest resources,
            String networkId
        ) {
            authorize(actor, Permission.OPERATE, environmentId);
            Environment environment = requireEnvironment(environmentId);
            Network network = networks.get(networkId);

            if (network == null || !environment.networkIds.contains(networkId)) {
                throw new InfrastructureException(
                    "Network is outside the requested environment"
                );
            }
            if (vms.containsKey(id)) {
                throw new InfrastructureException("VM already exists");
            }

            List<VirtualMachine> activeVMs = environment.vmIds.stream()
                .map(vms::get)
                .filter(vm -> vm.state() != VmState.TERMINATED)
                .toList();

            int usedVcpus = activeVMs.stream()
                .mapToInt(vm -> vm.resources().vcpus())
                .sum();
            long usedMemory = activeVMs.stream()
                .mapToLong(vm -> vm.resources().memoryMiB())
                .sum();

            if (activeVMs.size() + 1 > environment.quota.maxVMs() ||
                usedVcpus + resources.vcpus() > environment.quota.maxVcpus() ||
                usedMemory + resources.memoryMiB() >
                    environment.quota.maxMemoryMiB()) {
                throw new CapacityException("Environment compute quota exceeded");
            }

            String ip = network.allocateAddress(id);
            try {
                VirtualMachine vm = new VirtualMachine(
                    id, environmentId, name, image, resources, networkId, ip
                );
                vms.put(id, vm);
                environment.vmIds.add(id);
                record(
                    actor, "create_vm", "vm", id, "success",
                    "network=" + networkId + ",ip=" + ip
                );
                return vm;
            } catch (RuntimeException error) {
                network.releaseAddress(id);
                throw error;
            }
        }

        Volume createVolume(
            String actor,
            String environmentId,
            String id,
            String poolId,
            long sizeGiB,
            boolean encrypted
        ) {
            authorize(actor, Permission.OPERATE, environmentId);
            Environment environment = requireEnvironment(environmentId);
            StoragePool pool = pools.get(poolId);

            if (pool == null || !environment.poolIds.contains(poolId)) {
                throw new InfrastructureException(
                    "Storage pool is outside the requested environment"
                );
            }
            if (volumes.containsKey(id)) {
                throw new InfrastructureException("Volume already exists");
            }

            long allocatedStorage = environment.poolIds.stream()
                .map(pools::get)
                .mapToLong(StoragePool::usedGiB)
                .sum();

            if (sizeGiB < 1 || sizeGiB > pool.availableGiB() ||
                allocatedStorage + sizeGiB > environment.quota.maxStorageGiB()) {
                throw new CapacityException("Storage capacity exceeded");
            }

            Volume volume = new Volume(id, environmentId, poolId, sizeGiB, encrypted);
            pool.volumes.put(id, sizeGiB);
            volumes.put(id, volume);
            record(
                actor, "create_volume", "volume", id, "success",
                "sizeGiB=" + sizeGiB + ",encrypted=" + encrypted
            );
            return volume;
        }

        void attachVolume(String actor, String vmId, String volumeId) {
            VirtualMachine vm = vms.get(vmId);
            Volume volume = volumes.get(volumeId);

            if (vm == null || volume == null) {
                throw new NotFoundException("VM or volume not found");
            }
            authorize(actor, Permission.OPERATE, vm.environmentId);

            if (vm.state() == VmState.TERMINATED ||
                !vm.environmentId.equals(volume.environmentId) ||
                volume.attachedVmId != null) {
                throw new InfrastructureException(
                    "Volume attachment violates isolation or lifecycle policy"
                );
            }

            volume.attachedVmId = vmId;
            vm.volumeIds.add(volumeId);
            record(actor, "attach_volume", "volume", volumeId, "success", vmId);
        }

        void changeVMState(String actor, String vmId, String action) {
            VirtualMachine vm = vms.get(vmId);
            if (vm == null) {
                throw new NotFoundException("VM does not exist");
            }
            authorize(actor, Permission.OPERATE, vm.environmentId);

            vm.transition(action);
            if (action.equals("terminate")) {
                networks.get(vm.networkId).releaseAddress(vmId);
                for (String volumeId : vm.volumeIds) {
                    volumes.get(volumeId).attachedVmId = null;
                }
                vm.volumeIds.clear();
            }

            record(actor, action, "vm", vmId, "success", vm.state().name());
        }

        void printInventory(String actor, String environmentId) {
            authorize(actor, Permission.READ, environmentId);
            Environment environment = requireEnvironment(environmentId);

            System.out.println("\nEnvironment: " + environment.name());
            System.out.println("VM inventory:");

            environment.vmIds.stream()
                .map(vms::get)
                .filter(vm -> vm.state() != VmState.TERMINATED)
                .sorted((left, right) -> left.id().compareTo(right.id()))
                .forEach(vm -> System.out.printf(
                    "  %-12s state=%-10s ip=%-15s vCPU=%d memoryMiB=%d volumes=%s%n",
                    vm.id(), vm.state(), vm.ipAddress(),
                    vm.resources().vcpus(), vm.resources().memoryMiB(),
                    vm.volumeIds()
                ));

            long storageUsed = environment.poolIds.stream()
                .map(pools::get)
                .mapToLong(StoragePool::usedGiB)
                .sum();

            System.out.printf(
                "Storage in use: %d GiB; audit events: %d%n",
                storageUsed, audit.size()
            );
        }

        boolean validateStorageAccounting() {
            for (StoragePool pool : pools.values()) {
                long accounted = pool.volumes.values()
                    .stream()
                    .mapToLong(Long::longValue)
                    .sum();

                if (accounted != pool.usedGiB() ||
                    accounted > pool.capacityGiB()) {
                    return false;
                }
            }
            return true;
        }

        int auditCount() {
            return audit.size();
        }
    }

    public static void main(String[] args) {
        InfrastructureService service = new InfrastructureService();

        service.addUser("cloud_admin", Role.ADMIN);
        service.addUser("application_team", Role.OPERATOR);
        service.addUser("security_auditor", Role.VIEWER);

        service.createEnvironment(
            "cloud_admin",
            "engineering",
            "Engineering Sandbox",
            new ResourceQuota(8, 24, 32768, 300)
        );

        service.grantAccess("cloud_admin", "application_team", "engineering");
        service.grantAccess("cloud_admin", "security_auditor", "engineering");

        service.createNetwork(
            "cloud_admin", "engineering", "engineering_net",
            "10.80.1.0/24", "10.80.1.1", 180
        );
        service.createStoragePool(
            "cloud_admin", "engineering", "engineering_pool", 200
        );

        VirtualMachine api = service.createVM(
            "application_team",
            "engineering",
            "api_server",
            "Application API",
            "ubuntu-24.04",
            new ResourceRequest(4, 8192),
            "engineering_net"
        );

        service.createVolume(
            "application_team", "engineering", "api_data",
            "engineering_pool", 40, true
        );

        service.attachVolume("application_team", api.id(), "api_data");
        service.changeVMState("application_team", api.id(), "start");

        service.printInventory("security_auditor", "engineering");

        try {
            service.attachVolume("application_team", api.id(), "api_data");
            throw new AssertionError("A duplicate attachment should be rejected");
        } catch (InfrastructureException expected) {
            System.out.println("Duplicate attachment rejected: " + expected.getMessage());
        }

        try {
            service.createVM(
                "application_team", "engineering", "unauthorized_network_vm",
                "Invalid Network VM", "ubuntu-24.04",
                new ResourceRequest(1, 1024), "missing_network"
            );
            throw new AssertionError("An invalid network should be rejected");
        } catch (InfrastructureException expected) {
            System.out.println("Isolation policy enforced: " + expected.getMessage());
        }

        System.out.println(
            "Storage accounting: " +
            (service.validateStorageAccounting() ? "PASS" : "FAIL")
        );
        System.out.println("Recorded infrastructure events: " + service.auditCount());
    }
}
