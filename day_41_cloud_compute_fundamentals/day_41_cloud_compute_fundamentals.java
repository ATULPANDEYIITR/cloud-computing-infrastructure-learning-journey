import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public class CloudComputeGovernance {

    enum Architecture {
        X86_64, ARM64
    }

    enum WorkloadClass {
        GENERAL, WEB, COMPUTE, MEMORY
    }

    enum InstanceState {
        STOPPED, RUNNING, TERMINATED
    }

    record MachineImage(
        String id,
        String name,
        Architecture architecture,
        int rootDiskGiB,
        String owner,
        boolean trusted,
        boolean encrypted
    ) {
        MachineImage {
            Objects.requireNonNull(id, "Image ID is required.");
            Objects.requireNonNull(name, "Image name is required.");
            Objects.requireNonNull(architecture, "Architecture is required.");
            Objects.requireNonNull(owner, "Image owner is required.");

            if (id.isBlank() || name.isBlank() || owner.isBlank()) {
                throw new IllegalArgumentException(
                    "Image ID, name, and owner cannot be blank."
                );
            }
            if (rootDiskGiB < 8) {
                throw new IllegalArgumentException(
                    "Image root disk must be at least 8 GiB."
                );
            }
        }

        void validateForProduction() {
            if (!trusted || !encrypted) {
                throw new SecurityException(
                    "Production images must be trusted and encrypted."
                );
            }
        }
    }

    record InstanceType(
        String name,
        String family,
        int vcpus,
        double memoryGiB,
        Architecture architecture,
        double networkGbps,
        BigDecimal hourlyRate,
        Set<WorkloadClass> supportedWorkloads,
        boolean burstable
    ) {
        InstanceType {
            Objects.requireNonNull(name);
            Objects.requireNonNull(family);
            Objects.requireNonNull(architecture);
            Objects.requireNonNull(hourlyRate);
            supportedWorkloads = Set.copyOf(supportedWorkloads);

            if (name.isBlank() || family.isBlank()
                || vcpus < 1 || memoryGiB <= 0
                || networkGbps <= 0 || hourlyRate.signum() < 0) {
                throw new IllegalArgumentException(
                    "Invalid instance type specification."
                );
            }
        }

        double memoryPerVcpu() {
            return memoryGiB / vcpus;
        }
    }

    record Workload(
        String name,
        WorkloadClass workloadClass,
        int requiredVcpus,
        double requiredMemoryGiB,
        double minimumNetworkGbps,
        Architecture architecture,
        boolean allowBurstable
    ) {
        Workload {
            Objects.requireNonNull(name);
            Objects.requireNonNull(workloadClass);
            Objects.requireNonNull(architecture);

            if (name.isBlank() || requiredVcpus < 1
                || requiredMemoryGiB <= 0 || minimumNetworkGbps < 0) {
                throw new IllegalArgumentException(
                    "Invalid workload capacity requirements."
                );
            }
        }
    }

    record CapacityEstimate(
        int workloadPlacements,
        double usableVcpus,
        double usableMemoryGiB
    ) {}

    static final class Instance {
        private final String id;
        private final InstanceType type;
        private final MachineImage image;
        private final Map<String, String> tags;
        private InstanceState state = InstanceState.STOPPED;

        Instance(
            InstanceType type,
            MachineImage image,
            Map<String, String> tags
        ) {
            this.id = "i-" + UUID.randomUUID();
            this.type = Objects.requireNonNull(type);
            this.image = Objects.requireNonNull(image);
            this.tags = Map.copyOf(tags);
        }

        synchronized void start() {
            if (state == InstanceState.TERMINATED) {
                throw new IllegalStateException(
                    "Terminated instances cannot be started."
                );
            }
            if (state == InstanceState.RUNNING) {
                return;
            }

            image.validateForProduction();
            if (type.architecture() != image.architecture()) {
                throw new IllegalArgumentException(
                    "Image architecture does not match instance architecture."
                );
            }

            state = InstanceState.RUNNING;
        }

        synchronized void stop() {
            if (state != InstanceState.RUNNING) {
                throw new IllegalStateException(
                    "Only running instances can be stopped."
                );
            }
            state = InstanceState.STOPPED;
        }

        synchronized void terminate() {
            if (state == InstanceState.TERMINATED) {
                throw new IllegalStateException(
                    "Instance is already terminated."
                );
            }
            state = InstanceState.TERMINATED;
        }

        synchronized InstanceState state() {
            return state;
        }

        String id() {
            return id;
        }

        InstanceType type() {
            return type;
        }

        Map<String, String> tags() {
            return tags;
        }
    }

    static final class CapacityPlanningService {
        private final List<InstanceType> catalog;

        CapacityPlanningService(List<InstanceType> catalog) {
            this.catalog = List.copyOf(catalog);
        }

        List<InstanceType> recommend(Workload workload) {
            return catalog.stream()
                .filter(type ->
                    type.architecture() == workload.architecture())
                .filter(type ->
                    type.supportedWorkloads().contains(workload.workloadClass()))
                .filter(type -> type.vcpus() >= workload.requiredVcpus())
                .filter(type -> type.memoryGiB() >= workload.requiredMemoryGiB())
                .filter(type ->
                    type.networkGbps() >= workload.minimumNetworkGbps())
                .filter(type ->
                    !type.burstable() || workload.allowBurstable())
                .sorted(
                    Comparator.comparing(InstanceType::hourlyRate)
                        .thenComparingDouble(InstanceType::memoryGiB)
                        .thenComparingInt(InstanceType::vcpus)
                )
                .toList();
        }

        CapacityEstimate estimateCapacity(
            InstanceType type,
            int workloadVcpus,
            double workloadMemoryGiB,
            double cpuReserveFraction,
            double memoryReserveGiB
        ) {
            if (workloadVcpus < 1 || workloadMemoryGiB <= 0
                || cpuReserveFraction < 0 || cpuReserveFraction >= 1
                || memoryReserveGiB < 0) {
                throw new IllegalArgumentException(
                    "Invalid capacity estimation parameters."
                );
            }

            double usableCpu = type.vcpus() * (1 - cpuReserveFraction);
            double usableMemory = type.memoryGiB() - memoryReserveGiB;

            if (usableCpu < workloadVcpus
                || usableMemory < workloadMemoryGiB) {
                return new CapacityEstimate(0, usableCpu, usableMemory);
            }

            int cpuPlacements = (int) Math.floor(usableCpu / workloadVcpus);
            int memoryPlacements =
                (int) Math.floor(usableMemory / workloadMemoryGiB);

            return new CapacityEstimate(
                Math.min(cpuPlacements, memoryPlacements),
                usableCpu,
                usableMemory
            );
        }
    }

    static BigDecimal monthlyCost(
        BigDecimal hourlyRate,
        int hoursPerDay,
        int days
    ) {
        if (hourlyRate.signum() < 0 || hoursPerDay < 0
            || hoursPerDay > 24 || days < 1 || days > 366) {
            throw new IllegalArgumentException("Invalid billing parameters.");
        }

        return hourlyRate
            .multiply(BigDecimal.valueOf(hoursPerDay))
            .multiply(BigDecimal.valueOf(days))
            .setScale(2, RoundingMode.HALF_UP);
    }

    private static InstanceType type(
        String name,
        String family,
        int vcpus,
        double memoryGiB,
        Architecture architecture,
        double networkGbps,
        String hourlyRate,
        boolean burstable,
        WorkloadClass... workloadClasses
    ) {
        return new InstanceType(
            name,
            family,
            vcpus,
            memoryGiB,
            architecture,
            networkGbps,
            new BigDecimal(hourlyRate),
            EnumSet.copyOf(List.of(workloadClasses)),
            burstable
        );
    }

    public static void main(String[] args) {
        List<InstanceType> catalog = new ArrayList<>(List.of(
            type("general.small", "general", 2, 4, Architecture.X86_64,
                1, "0.025", false, WorkloadClass.GENERAL, WorkloadClass.WEB),
            type("general.medium", "general", 4, 16, Architecture.X86_64,
                5, "0.080", false, WorkloadClass.GENERAL, WorkloadClass.WEB),
            type("compute.large", "compute", 8, 16, Architecture.X86_64,
                10, "0.120", false, WorkloadClass.COMPUTE, WorkloadClass.GENERAL),
            type("memory.large", "memory", 4, 32, Architecture.X86_64,
                10, "0.150", false, WorkloadClass.MEMORY, WorkloadClass.GENERAL),
            type("arm.compute", "compute", 8, 16, Architecture.ARM64,
                10, "0.095", false, WorkloadClass.COMPUTE, WorkloadClass.GENERAL),
            type("general.burst", "general", 2, 4, Architecture.X86_64,
                1, "0.012", true, WorkloadClass.WEB, WorkloadClass.GENERAL)
        ));

        CapacityPlanningService service =
            new CapacityPlanningService(catalog);

        List<Workload> workloads = List.of(
            new Workload(
                "API batch workers", WorkloadClass.COMPUTE, 6, 8, 5,
                Architecture.X86_64, false
            ),
            new Workload(
                "in-memory analytics", WorkloadClass.MEMORY, 4, 24, 5,
                Architecture.X86_64, false
            ),
            new Workload(
                "ARM build agents", WorkloadClass.COMPUTE, 4, 8, 2,
                Architecture.ARM64, false
            )
        );

        System.out.println("Enterprise cloud compute planning");
        System.out.println("=================================");

        for (Workload workload : workloads) {
            System.out.println("\nWorkload: " + workload.name());
            List<InstanceType> choices = service.recommend(workload);

            if (choices.isEmpty()) {
                System.out.println("No instance type satisfies all requirements.");
                continue;
            }

            for (InstanceType choice : choices) {
                System.out.printf(
                    "  %s | %d vCPU | %.1f GiB | %s | $%s/hour%n",
                    choice.name(),
                    choice.vcpus(),
                    choice.memoryGiB(),
                    choice.architecture(),
                    choice.hourlyRate().toPlainString()
                );
            }
        }

        InstanceType compute = catalog.stream()
            .filter(type -> type.name().equals("compute.large"))
            .findFirst()
            .orElseThrow();

        CapacityEstimate capacity = service.estimateCapacity(
            compute, 2, 3, 0.10, 0.5
        );

        System.out.printf(
            "%nCapacity estimate: %d workloads; usable CPU %.1f vCPU; "
                + "usable memory %.1f GiB%n",
            capacity.workloadPlacements(),
            capacity.usableVcpus(),
            capacity.usableMemoryGiB()
        );

        System.out.println(
            "Monthly compute estimate: $"
                + monthlyCost(compute.hourlyRate(), 24, 30)
        );

        MachineImage linuxImage = new MachineImage(
            "img-linux-hardened",
            "Hardened Linux",
            Architecture.X86_64,
            30,
            "platform-engineering",
            true,
            true
        );

        Instance instance = new Instance(
            compute,
            linuxImage,
            Map.of("environment", "test", "service", "analytics")
        );

        instance.start();
        System.out.println(
            "\nInstance " + instance.id() + " state: " + instance.state()
        );
        instance.stop();
        instance.start();
        instance.terminate();
        System.out.println("Final state: " + instance.state());

        try {
            instance.start();
        } catch (IllegalStateException exception) {
            System.out.println("Lifecycle policy: " + exception.getMessage());
        }

        MachineImage incompatibleImage = new MachineImage(
            "img-arm",
            "ARM Linux",
            Architecture.ARM64,
            20,
            "platform-engineering",
            true,
            true
        );

        try {
            new Instance(compute, incompatibleImage, Map.of()).start();
        } catch (IllegalArgumentException exception) {
            System.out.println("Architecture policy: " + exception.getMessage());
        }

        try {
            monthlyCost(compute.hourlyRate(), 25, 30);
        } catch (IllegalArgumentException exception) {
            System.out.println("Billing policy: " + exception.getMessage());
        }

        System.out.println("\nEnterprise controls:");
        System.out.println("- Immutable records protect catalog and image definitions.");
        System.out.println("- Copying collections prevents external mutation of policies.");
        System.out.println("- Synchronized lifecycle methods serialize instance transitions.");
        System.out.println("- Real deployments also require IAM, quotas, and audit logging.");
    }
}
