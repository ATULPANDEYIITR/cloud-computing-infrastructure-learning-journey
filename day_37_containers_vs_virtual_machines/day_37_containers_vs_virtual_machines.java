import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/*
 * Containers vs Virtual Machines
 *
 * Enterprise-oriented infrastructure governance model.
 *
 * Compile:
 *   javac ContainersVsVirtualMachines.java
 *
 * Run:
 *   java ContainersVsVirtualMachines
 */

public class ContainersVsVirtualMachines {

    enum WorkloadType {
        WEB_API,
        DATABASE,
        LEGACY_APPLICATION,
        BATCH,
        MULTI_SERVICE
    }

    enum RuntimeType {
        CONTAINER,
        VIRTUAL_MACHINE
    }

    record Workload(
        String name,
        WorkloadType type,
        double cpuRequest,
        double memoryGb,
        double storageGb,
        boolean requiresCustomKernel,
        boolean untrusted,
        String architecture
    ) {
        Workload {
            Objects.requireNonNull(name, "name");
            Objects.requireNonNull(type, "type");
            Objects.requireNonNull(architecture, "architecture");

            if (name.isBlank()) {
                throw new IllegalArgumentException(
                    "Workload name cannot be blank"
                );
            }

            if (cpuRequest <= 0) {
                throw new IllegalArgumentException(
                    "CPU request must be positive"
                );
            }

            if (memoryGb <= 0) {
                throw new IllegalArgumentException(
                    "Memory request must be positive"
                );
            }

            if (storageGb < 0) {
                throw new IllegalArgumentException(
                    "Storage cannot be negative"
                );
            }
        }
    }

    interface RuntimeEnvironment {
        String name();

        RuntimeType type();

        Workload workload();

        double cpuLimit();

        double memoryLimitGb();

        double startupSeconds();

        double isolationScore();

        double portabilityScore();

        double memoryOverheadGb();

        String isolationBoundary();

        boolean supportsArchitecture(String architecture);

        default double effectiveMemoryGb() {
            return memoryLimitGb() - memoryOverheadGb();
        }
    }

    abstract static class BaseRuntime implements RuntimeEnvironment {
        private final String name;
        private final Workload workload;
        private final double cpuLimit;
        private final double memoryLimitGb;
        private final double startupSeconds;
        private final double isolationScore;
        private final double portabilityScore;
        private final double memoryOverheadGb;

        protected BaseRuntime(
            String name,
            Workload workload,
            double cpuLimit,
            double memoryLimitGb,
            double startupSeconds,
            double isolationScore,
            double portabilityScore,
            double memoryOverheadGb
        ) {
            this.name = Objects.requireNonNull(name);
            this.workload = Objects.requireNonNull(workload);

            if (cpuLimit < workload.cpuRequest()) {
                throw new IllegalArgumentException(
                    "CPU limit is below workload request"
                );
            }

            if (memoryLimitGb < workload.memoryGb()) {
                throw new IllegalArgumentException(
                    "Memory limit is below workload request"
                );
            }

            this.cpuLimit = cpuLimit;
            this.memoryLimitGb = memoryLimitGb;
            this.startupSeconds = startupSeconds;
            this.isolationScore = isolationScore;
            this.portabilityScore = portabilityScore;
            this.memoryOverheadGb = memoryOverheadGb;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public Workload workload() {
            return workload;
        }

        @Override
        public double cpuLimit() {
            return cpuLimit;
        }

        @Override
        public double memoryLimitGb() {
            return memoryLimitGb;
        }

        @Override
        public double startupSeconds() {
            return startupSeconds;
        }

        @Override
        public double isolationScore() {
            return isolationScore;
        }

        @Override
        public double portabilityScore() {
            return portabilityScore;
        }

        @Override
        public double memoryOverheadGb() {
            return memoryOverheadGb;
        }

        @Override
        public boolean supportsArchitecture(String architecture) {
            return workload.architecture().equals(architecture);
        }
    }

    static final class Container extends BaseRuntime {
        Container(
            String name,
            Workload workload,
            double cpuLimit,
            double memoryLimitGb
        ) {
            super(
                name,
                workload,
                cpuLimit,
                memoryLimitGb,
                0.8,
                0.72,
                0.95,
                0.08
            );
        }

        @Override
        public RuntimeType type() {
            return RuntimeType.CONTAINER;
        }

        @Override
        public String isolationBoundary() {
            return "Process, namespace and cgroup isolation with a shared host kernel";
        }
    }

    static final class VirtualMachine extends BaseRuntime {
        private final String guestOperatingSystem;

        VirtualMachine(
            String name,
            Workload workload,
            double cpuLimit,
            double memoryLimitGb,
            String guestOperatingSystem
        ) {
            super(
                name,
                workload,
                cpuLimit,
                memoryLimitGb,
                22.0,
                0.96,
                0.82,
                0.65
            );

            this.guestOperatingSystem =
                Objects.requireNonNull(guestOperatingSystem);
        }

        @Override
        public RuntimeType type() {
            return RuntimeType.VIRTUAL_MACHINE;
        }

        @Override
        public String isolationBoundary() {
            return "Virtual hardware boundary with an independent guest kernel";
        }

        String guestOperatingSystem() {
            return guestOperatingSystem;
        }
    }

    record PlacementDecision(
        RuntimeType runtime,
        String reason
    ) {}

    static final class PlacementService {

        PlacementDecision decide(Workload workload) {
            if (workload.requiresCustomKernel()) {
                return new PlacementDecision(
                    RuntimeType.VIRTUAL_MACHINE,
                    "Kernel independence is a direct requirement."
                );
            }

            if (workload.type() == WorkloadType.LEGACY_APPLICATION) {
                return new PlacementDecision(
                    RuntimeType.VIRTUAL_MACHINE,
                    "The application may depend on a complete guest OS."
                );
            }

            if (
                workload.type() == WorkloadType.WEB_API
                    || workload.type() == WorkloadType.BATCH
                    || workload.type() == WorkloadType.MULTI_SERVICE
            ) {
                return new PlacementDecision(
                    RuntimeType.CONTAINER,
                    "Fast startup, application packaging and density are valuable."
                );
            }

            return new PlacementDecision(
                RuntimeType.CONTAINER,
                "Container is a starting point; storage and isolation must be evaluated."
            );
        }
    }

    static final class ResourcePolicy {
        private final double maximumCpuUtilization;
        private final double maximumMemoryUtilization;

        ResourcePolicy(
            double maximumCpuUtilization,
            double maximumMemoryUtilization
        ) {
            if (
                maximumCpuUtilization <= 0
                    || maximumCpuUtilization > 1
                    || maximumMemoryUtilization <= 0
                    || maximumMemoryUtilization > 1
            ) {
                throw new IllegalArgumentException(
                    "Utilization thresholds must be between zero and one"
                );
            }

            this.maximumCpuUtilization = maximumCpuUtilization;
            this.maximumMemoryUtilization = maximumMemoryUtilization;
        }

        boolean allows(
            double currentCpu,
            double totalCpu,
            double currentMemory,
            double totalMemory,
            RuntimeEnvironment runtime
        ) {
            double cpu =
                (currentCpu + runtime.cpuLimit()) / totalCpu;

            double memory =
                (currentMemory + runtime.memoryLimitGb())
                    / totalMemory;

            return cpu <= maximumCpuUtilization
                && memory <= maximumMemoryUtilization;
        }
    }

    static final class ComputeHost {
        private final String name;
        private final String architecture;
        private final double cpu;
        private final double memoryGb;
        private final double storageGb;
        private final ResourcePolicy resourcePolicy;
        private final List<RuntimeEnvironment> deployments =
            new ArrayList<>();

        ComputeHost(
            String name,
            String architecture,
            double cpu,
            double memoryGb,
            double storageGb,
            ResourcePolicy resourcePolicy
        ) {
            this.name = Objects.requireNonNull(name);
            this.architecture = Objects.requireNonNull(architecture);
            this.resourcePolicy = Objects.requireNonNull(resourcePolicy);

            if (cpu <= 0 || memoryGb <= 0 || storageGb <= 0) {
                throw new IllegalArgumentException(
                    "Host resources must be positive"
                );
            }

            this.cpu = cpu;
            this.memoryGb = memoryGb;
            this.storageGb = storageGb;
        }

        double allocatedCpu() {
            return deployments.stream()
                .mapToDouble(RuntimeEnvironment::cpuLimit)
                .sum();
        }

        double allocatedMemory() {
            return deployments.stream()
                .mapToDouble(RuntimeEnvironment::memoryLimitGb)
                .sum();
        }

        double allocatedStorage() {
            return deployments.stream()
                .mapToDouble(
                    runtime -> runtime.workload().storageGb()
                )
                .sum();
        }

        void deploy(RuntimeEnvironment runtime) {
            if (!runtime.supportsArchitecture(architecture)) {
                throw new IllegalStateException(
                    "Architecture mismatch for " + runtime.name()
                );
            }

            if (
                allocatedStorage()
                    + runtime.workload().storageGb()
                    > storageGb
            ) {
                throw new IllegalStateException(
                    "Storage capacity exceeded"
                );
            }

            if (
                !resourcePolicy.allows(
                    allocatedCpu(),
                    cpu,
                    allocatedMemory(),
                    memoryGb,
                    runtime
                )
            ) {
                throw new IllegalStateException(
                    "Resource policy rejected deployment"
                );
            }

            deployments.add(runtime);
        }

        double cpuUtilization() {
            return allocatedCpu() / cpu;
        }

        double memoryUtilization() {
            return allocatedMemory() / memoryGb;
        }

        List<RuntimeEnvironment> deployments() {
            return Collections.unmodifiableList(deployments);
        }

        String name() {
            return name;
        }
    }

    static void printRuntime(RuntimeEnvironment runtime) {
        System.out.printf(
            "%-24s %-18s startup=%6.1fs isolation=%.2f portability=%.2f%n",
            runtime.name(),
            runtime.type(),
            runtime.startupSeconds(),
            runtime.isolationScore(),
            runtime.portabilityScore()
        );

        System.out.println(
            "  Boundary: " + runtime.isolationBoundary()
        );

        System.out.printf(
            "  Effective memory: %.2f GB%n",
            runtime.effectiveMemoryGb()
        );
    }

    static List<Workload> createWorkloads() {
        return List.of(
            new Workload(
                "customer-api",
                WorkloadType.WEB_API,
                1.0,
                1.0,
                5.0,
                false,
                false,
                "x86_64"
            ),
            new Workload(
                "analytics-batch",
                WorkloadType.BATCH,
                4.0,
                8.0,
                25.0,
                false,
                false,
                "x86_64"
            ),
            new Workload(
                "legacy-payment",
                WorkloadType.LEGACY_APPLICATION,
                2.0,
                4.0,
                40.0,
                true,
                false,
                "x86_64"
            ),
            new Workload(
                "orders-database",
                WorkloadType.DATABASE,
                4.0,
                12.0,
                200.0,
                false,
                false,
                "x86_64"
            )
        );
    }

    static void demonstratePlacement(List<Workload> workloads) {
        System.out.println("\n=== Enterprise placement decisions ===");

        PlacementService service = new PlacementService();

        for (Workload workload : workloads) {
            PlacementDecision decision = service.decide(workload);

            System.out.printf(
                "%-22s -> %-18s %s%n",
                workload.name(),
                decision.runtime(),
                decision.reason()
            );
        }
    }

    static void demonstrateRuntimeDifferences(Workload workload) {
        System.out.println("\n=== Runtime characteristics ===");

        RuntimeEnvironment container =
            new Container(
                "customer-api-container",
                workload,
                1.0,
                1.0
            );

        RuntimeEnvironment vm =
            new VirtualMachine(
                "customer-api-vm",
                workload,
                1.0,
                1.0,
                "Linux"
            );

        printRuntime(container);
        printRuntime(vm);

        System.out.println(
            "\nThe container shares the host kernel, while the VM boots " +
            "a separate guest operating system."
        );
    }

    static void demonstrateResourceDensity() {
        System.out.println("\n=== Resource density ===");

        ResourcePolicy policy =
            new ResourcePolicy(0.95, 0.95);

        ComputeHost containerHost =
            new ComputeHost(
                "container-host",
                "x86_64",
                16,
                32,
                500,
                policy
            );

        for (int index = 1; index <= 12; index++) {
            Workload workload =
                new Workload(
                    "web-" + index,
                    WorkloadType.WEB_API,
                    1,
                    1,
                    4,
                    false,
                    false,
                    "x86_64"
                );

            containerHost.deploy(
                new Container(
                    "container-" + index,
                    workload,
                    1,
                    1
                )
            );
        }

        System.out.printf(
            "Containers deployed: %d%n",
            containerHost.deployments().size()
        );

        System.out.printf(
            "CPU utilization: %.1f%%%n",
            containerHost.cpuUtilization() * 100
        );

        System.out.printf(
            "Memory utilization: %.1f%%%n",
            containerHost.memoryUtilization() * 100
        );
    }

    static void demonstrateSecurity() {
        System.out.println("\n=== Security boundary ===");

        System.out.println(
            "Container: processes are isolated while sharing the host kernel."
        );

        System.out.println(
            "VM: applications run inside an independent guest kernel."
        );

        System.out.println(
            "Container hardening can use namespaces, cgroups, dropped " +
            "capabilities, seccomp, read-only filesystems and image provenance."
        );

        System.out.println(
            "VM security still depends on the hypervisor, host OS, device " +
            "exposure, management plane and guest OS configuration."
        );
    }

    public static void main(String[] args) {
        System.out.println("CONTAINERS VS VIRTUAL MACHINES");
        System.out.println("==============================");

        try {
            List<Workload> workloads = createWorkloads();

            demonstratePlacement(workloads);
            demonstrateRuntimeDifferences(workloads.get(0));
            demonstrateResourceDensity();
            demonstrateSecurity();

            System.out.println("\n=== Architectural model ===");
            System.out.println(
                "Containers optimize application-level packaging, density " +
                "and startup time."
            );
            System.out.println(
                "VMs optimize kernel independence and stronger guest-level " +
                "isolation."
            );
            System.out.println(
                "Both can coexist when VMs provide infrastructure isolation " +
                "and containers provide application packaging."
            );
        } catch (RuntimeException error) {
            System.err.println(
                "Infrastructure model failed: " + error.getMessage()
            );
            System.exit(1);
        }
    }
}
