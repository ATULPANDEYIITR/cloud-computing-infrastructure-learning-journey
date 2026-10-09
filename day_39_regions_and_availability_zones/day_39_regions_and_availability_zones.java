import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public class RegionalResilience {
    enum ZoneStatus {
        HEALTHY, DEGRADED, DOWN
    }

    enum ReplicationPolicy {
        SINGLE_ZONE, MULTI_ZONE
    }

    record Region(String id, String name, String residencyGroup) {
        Region {
            if (id == null || id.isBlank() ||
                name == null || name.isBlank() ||
                residencyGroup == null || residencyGroup.isBlank()) {
                throw new IllegalArgumentException("Region fields are required.");
            }
        }
    }

    static final class AvailabilityZone {
        private final String id;
        private final String regionId;
        private final Set<String> failureDomains;
        private final int capacity;
        private final double latencyMs;
        private final Map<String, Integer> allocations = new HashMap<>();
        private ZoneStatus status = ZoneStatus.HEALTHY;

        AvailabilityZone(
                String id,
                String regionId,
                Set<String> failureDomains,
                int capacity,
                double latencyMs) {
            if (id == null || id.isBlank() ||
                regionId == null || regionId.isBlank()) {
                throw new IllegalArgumentException("Zone identity is required.");
            }
            if (capacity < 0 || !Double.isFinite(latencyMs) || latencyMs < 0) {
                throw new IllegalArgumentException("Invalid capacity or latency.");
            }
            if (failureDomains == null || failureDomains.isEmpty()) {
                throw new IllegalArgumentException("Failure domains are required.");
            }
            this.id = id;
            this.regionId = regionId;
            this.failureDomains = Set.copyOf(failureDomains);
            this.capacity = capacity;
            this.latencyMs = latencyMs;
        }

        String id() {
            return id;
        }

        String regionId() {
            return regionId;
        }

        Set<String> failureDomains() {
            return failureDomains;
        }

        ZoneStatus status() {
            return status;
        }

        void setStatus(ZoneStatus newStatus) {
            status = Objects.requireNonNull(newStatus);
        }

        int usedCapacity() {
            return allocations.values().stream().mapToInt(Integer::intValue).sum();
        }

        int availableCapacity() {
            if (status == ZoneStatus.DOWN) return 0;
            int free = Math.max(0, capacity - usedCapacity());
            return status == ZoneStatus.DEGRADED ? free / 2 : free;
        }

        void allocate(String workloadId, int replicas) {
            if (status != ZoneStatus.HEALTHY) {
                throw new IllegalStateException("Zone is not healthy: " + id);
            }
            if (replicas < 1 || replicas > availableCapacity()) {
                throw new IllegalStateException("Insufficient capacity in " + id);
            }
            allocations.merge(workloadId, replicas, Integer::sum);
        }
    }

    static final class Workload {
        private final String id;
        private final String regionId;
        private final int replicaCount;
        private final int minimumHealthy;
        private final ReplicationPolicy policy;
        private final Map<String, Integer> placements = new HashMap<>();

        Workload(
                String id,
                String regionId,
                int replicaCount,
                int minimumHealthy,
                ReplicationPolicy policy) {
            if (id == null || id.isBlank() ||
                regionId == null || regionId.isBlank()) {
                throw new IllegalArgumentException("Workload identity is required.");
            }
            if (replicaCount < 1 || minimumHealthy < 1 ||
                minimumHealthy > replicaCount) {
                throw new IllegalArgumentException("Invalid replica policy.");
            }
            this.id = id;
            this.regionId = regionId;
            this.replicaCount = replicaCount;
            this.minimumHealthy = minimumHealthy;
            this.policy = Objects.requireNonNull(policy);
        }

        String id() {
            return id;
        }

        String regionId() {
            return regionId;
        }

        int replicaCount() {
            return replicaCount;
        }

        ReplicationPolicy policy() {
            return policy;
        }

        Map<String, Integer> placements() {
            return Map.copyOf(placements);
        }

        int healthyReplicas(Map<String, AvailabilityZone> zones) {
            return placements.entrySet().stream()
                    .filter(entry -> zones.containsKey(entry.getKey()))
                    .filter(entry ->
                            zones.get(entry.getKey()).status() == ZoneStatus.HEALTHY)
                    .mapToInt(Map.Entry::getValue)
                    .sum();
        }

        boolean isAvailable(Map<String, AvailabilityZone> zones) {
            return healthyReplicas(zones) >= minimumHealthy;
        }
    }

    record AuditEvent(
            String eventId,
            Instant timestamp,
            String eventType,
            String subject,
            String detail) {}

    static final class InfrastructureService {
        private final Map<String, Region> regions = new HashMap<>();
        private final Map<String, AvailabilityZone> zones = new HashMap<>();
        private final Map<String, Workload> workloads = new HashMap<>();
        private final List<AuditEvent> audit = new ArrayList<>();

        void registerRegion(Region region) {
            if (regions.putIfAbsent(region.id(), region) != null) {
                throw new IllegalArgumentException("Duplicate region.");
            }
        }

        void registerZone(AvailabilityZone zone) {
            if (!regions.containsKey(zone.regionId())) {
                throw new IllegalArgumentException("Unknown parent region.");
            }
            if (zones.putIfAbsent(zone.id(), zone) != null) {
                throw new IllegalArgumentException("Duplicate zone.");
            }
        }

        void registerWorkload(Workload workload) {
            if (!regions.containsKey(workload.regionId())) {
                throw new IllegalArgumentException("Unknown workload region.");
            }
            if (workloads.putIfAbsent(workload.id(), workload) != null) {
                throw new IllegalArgumentException("Duplicate workload.");
            }
        }

        private void record(String type, String subject, String detail) {
            audit.add(new AuditEvent(
                    UUID.randomUUID().toString(),
                    Instant.now(),
                    type,
                    subject,
                    detail));
        }

        void placeWorkload(String workloadId, List<String> zoneIds) {
            Workload workload = requireWorkload(workloadId);

            if (zoneIds.size() != workload.replicaCount()) {
                throw new IllegalArgumentException("Replica count mismatch.");
            }
            if (new HashSet<>(zoneIds).size() != zoneIds.size()) {
                throw new IllegalArgumentException("Duplicate zone placement.");
            }

            List<AvailabilityZone> selected = zoneIds.stream()
                    .map(id -> {
                        AvailabilityZone zone = zones.get(id);
                        if (zone == null) throw new IllegalArgumentException(
                                "Unknown zone: " + id);
                        return zone;
                    })
                    .toList();

            Set<String> sharedDomains = new HashSet<>();
            for (AvailabilityZone zone : selected) {
                if (!zone.regionId().equals(workload.regionId())) {
                    throw new IllegalArgumentException(
                            "Regional workload crosses region boundaries.");
                }
                if (zone.status() != ZoneStatus.HEALTHY ||
                    zone.availableCapacity() < 1) {
                    throw new IllegalStateException("Zone cannot accept replicas.");
                }
                for (String domain : zone.failureDomains()) {
                    if (!sharedDomains.add(domain)) {
                        throw new IllegalArgumentException(
                                "Replicas share a modeled failure domain.");
                    }
                }
            }

            // Preflight checks prevent ordinary validation errors from leaving
            // a partially placed workload.
            selected.forEach(zone -> zone.allocate(workload.id(), 1));
            workload.placements.clear();
            zoneIds.forEach(id -> workload.placements.put(id, 1));
            record("PLACEMENT", workload.id(), zoneIds.toString());
        }

        Workload requireWorkload(String id) {
            Workload workload = workloads.get(id);
            if (workload == null) throw new IllegalArgumentException(
                    "Unknown workload: " + id);
            return workload;
        }

        void changeZoneStatus(String zoneId, ZoneStatus status) {
            AvailabilityZone zone = zones.get(zoneId);
            if (zone == null) throw new IllegalArgumentException("Unknown zone.");

            ZoneStatus previous = zone.status();
            zone.setStatus(status);
            record("ZONE_STATUS", zoneId, previous + " -> " + status);

            for (Workload workload : workloads.values()) {
                if (!workload.placements().containsKey(zoneId)) continue;
                int healthy = workload.healthyReplicas(zones);
                boolean available = workload.isAvailable(zones);
                record(
                        available ? "WORKLOAD_HEALTHY" : "WORKLOAD_IMPAIRED",
                        workload.id(),
                        "healthyReplicas=" + healthy);
                System.out.printf(
                        "%s: %d healthy replicas, service %s%n",
                        workload.id(),
                        healthy,
                        available ? "available" : "unavailable");
            }
        }

        List<AvailabilityZone> chooseIndependentZones(
                String regionId, int required) {
            if (!regions.containsKey(regionId)) {
                throw new IllegalArgumentException("Unknown region.");
            }
            if (required < 1) throw new IllegalArgumentException("Invalid count.");

            List<AvailabilityZone> candidates = zones.values().stream()
                    .filter(zone -> zone.regionId().equals(regionId))
                    .filter(zone -> zone.status() == ZoneStatus.HEALTHY)
                    .filter(zone -> zone.availableCapacity() > 0)
                    .sorted(Comparator.comparingDouble(
                            zone -> zone.latencyMs))
                    .toList();

            List<AvailabilityZone> selected = new ArrayList<>();
            Set<String> domains = new HashSet<>();

            for (AvailabilityZone zone : candidates) {
                if (zone.failureDomains().stream().anyMatch(domains::contains)) {
                    continue;
                }
                selected.add(zone);
                domains.addAll(zone.failureDomains());
                if (selected.size() == required) return List.copyOf(selected);
            }

            throw new IllegalStateException(
                    "Insufficient healthy zones with independent modeled domains.");
        }

        void printReport() {
            System.out.println("\nRegional topology");
            regions.values().stream()
                    .sorted(Comparator.comparing(Region::id))
                    .forEach(region -> {
                        System.out.printf(
                                "%s (%s), residency=%s%n",
                                region.id(), region.name(), region.residencyGroup());
                        zones.values().stream()
                                .filter(zone -> zone.regionId().equals(region.id()))
                                .sorted(Comparator.comparing(AvailabilityZone::id))
                                .forEach(zone -> System.out.printf(
                                        "  %s: %s, capacity=%d/%d%n",
                                        zone.id(),
                                        zone.status(),
                                        zone.usedCapacity(),
                                        zone.capacity));
                    });

            System.out.println("\nWorkload status");
            workloads.values().forEach(workload -> System.out.printf(
                    "%s: placements=%s, healthy=%d, available=%s%n",
                    workload.id(),
                    workload.placements(),
                    workload.healthyReplicas(zones),
                    workload.isAvailable(zones)));
        }

        List<AuditEvent> auditEvents() {
            return List.copyOf(audit);
        }
    }

    private static double parallelAvailability(double... availabilities) {
        double allFail = 1.0;
        for (double value : availabilities) {
            if (!Double.isFinite(value) || value < 0 || value > 1) {
                throw new IllegalArgumentException("Availability must be in [0,1].");
            }
            allFail *= 1.0 - value;
        }
        return 1.0 - allFail;
    }

    public static void main(String[] args) {
        InfrastructureService service = new InfrastructureService();
        service.registerRegion(new Region(
                "ap-south", "South Asia", "IN"));

        service.registerZone(new AvailabilityZone(
                "zone-a", "ap-south", Set.of("power-a", "network-a"), 20, 4));
        service.registerZone(new AvailabilityZone(
                "zone-b", "ap-south", Set.of("power-b", "network-b"), 20, 6));
        service.registerZone(new AvailabilityZone(
                "zone-c", "ap-south", Set.of("power-c", "network-c"), 20, 8));

        service.registerWorkload(new Workload(
                "payment-ledger",
                "ap-south",
                3,
                2,
                ReplicationPolicy.MULTI_ZONE));

        List<String> placement = service.chooseIndependentZones(
                        "ap-south", 3).stream()
                .map(AvailabilityZone::id)
                .toList();

        service.placeWorkload("payment-ledger", placement);
        service.printReport();

        System.out.println("\nZone failure exercise");
        service.changeZoneStatus("zone-a", ZoneStatus.DOWN);
        service.printReport();

        service.changeZoneStatus("zone-a", ZoneStatus.HEALTHY);

        System.out.printf(
                "%nAvailability of two independent 99.9%% replicas: %.5f%%%n",
                parallelAvailability(0.999, 0.999) * 100);

        System.out.println("Audit events: " + service.auditEvents().size());
    }
}
