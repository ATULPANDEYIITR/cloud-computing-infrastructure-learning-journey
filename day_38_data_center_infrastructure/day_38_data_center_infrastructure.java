import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class DataCenterInfrastructure {

    enum PowerPath {
        A,
        B,
        DUAL
    }

    enum ServerState {
        RUNNING,
        FAILED,
        MAINTENANCE
    }

    enum EquipmentRole {
        APPLICATION,
        DATABASE,
        BACKUP,
        NETWORK
    }

    record ServerSpec(
        String name,
        String rackId,
        double powerKW,
        EquipmentRole role,
        EnumSet<PowerPath> powerPaths,
        boolean dualNetwork
    ) {
        ServerSpec {
            Objects.requireNonNull(name);
            Objects.requireNonNull(rackId);
            Objects.requireNonNull(role);
            Objects.requireNonNull(powerPaths);

            if (powerKW <= 0) {
                throw new IllegalArgumentException(
                    "Server power must be positive"
                );
            }

            if (powerPaths.isEmpty()) {
                throw new IllegalArgumentException(
                    "A server must have at least one power path"
                );
            }
        }
    }

    static final class Server {
        private final ServerSpec specification;
        private ServerState state = ServerState.RUNNING;

        Server(ServerSpec specification) {
            this.specification = specification;
        }

        String name() {
            return specification.name();
        }

        String rackId() {
            return specification.rackId();
        }

        double powerKW() {
            return specification.powerKW();
        }

        EquipmentRole role() {
            return specification.role();
        }

        EnumSet<PowerPath> powerPaths() {
            return specification.powerPaths();
        }

        boolean dualNetwork() {
            return specification.dualNetwork();
        }

        ServerState state() {
            return state;
        }

        void transitionTo(ServerState newState) {
            Objects.requireNonNull(newState);

            if (state == ServerState.FAILED &&
                newState == ServerState.RUNNING) {
                throw new IllegalStateException(
                    "A failed server requires recovery before it can run"
                );
            }

            state = newState;
        }
    }

    static final class Rack {
        private final String id;
        private final int capacityU;
        private final double powerCapacityKW;
        private final List<Server> servers = new ArrayList<>();

        Rack(String id, int capacityU, double powerCapacityKW) {
            this.id = id;
            this.capacityU = capacityU;
            this.powerCapacityKW = powerCapacityKW;
        }

        boolean canAccept(Server server) {
            return servers.size() < capacityU &&
                   usedPowerKW() + server.powerKW() <= powerCapacityKW;
        }

        void install(Server server) {
            if (!canAccept(server)) {
                throw new IllegalStateException(
                    "Rack " + id + " cannot accept " + server.name()
                );
            }
            servers.add(server);
        }

        double usedPowerKW() {
            return servers.stream()
                .mapToDouble(Server::powerKW)
                .sum();
        }

        int usedU() {
            return servers.size();
        }

        String id() {
            return id;
        }
    }

    static final class PowerSystem {
        private final Map<PowerPath, Double> capacityKW = new HashMap<>();
        private final Map<PowerPath, Double> loadKW = new HashMap<>();

        PowerSystem(double capacityPerPath) {
            capacityKW.put(PowerPath.A, capacityPerPath);
            capacityKW.put(PowerPath.B, capacityPerPath);
            loadKW.put(PowerPath.A, 0.0);
            loadKW.put(PowerPath.B, 0.0);
        }

        void reserve(PowerPath path, double amountKW) {
            double current = loadKW.get(path);
            double capacity = capacityKW.get(path);

            if (current + amountKW > capacity) {
                throw new IllegalStateException(
                    "Power path " + path + " exceeds capacity"
                );
            }

            loadKW.put(path, current + amountKW);
        }

        void connect(Server server) {
            EnumSet<PowerPath> paths = server.powerPaths();

            if (paths.contains(PowerPath.DUAL)) {
                reserve(PowerPath.A, server.powerKW() / 2);
                reserve(PowerPath.B, server.powerKW() / 2);
                return;
            }

            if (paths.contains(PowerPath.A)) {
                reserve(PowerPath.A, server.powerKW());
                return;
            }

            reserve(PowerPath.B, server.powerKW());
        }

        boolean survivesFailure(PowerPath failedPath, List<Server> servers) {
            return servers.stream()
                .filter(server -> server.state() == ServerState.RUNNING)
                .allMatch(server -> {
                    EnumSet<PowerPath> paths = server.powerPaths();

                    if (paths.contains(PowerPath.DUAL)) {
                        return true;
                    }

                    return !paths.contains(failedPath);
                });
        }

        void report() {
            for (PowerPath path : List.of(PowerPath.A, PowerPath.B)) {
                System.out.printf(
                    "Power %s: %.2f/%.2f kW%n",
                    path,
                    loadKW.get(path),
                    capacityKW.get(path)
                );
            }
        }
    }

    static final class CoolingPlant {
        private final Map<String, Double> capacities = new HashMap<>();
        private final Map<String, Double> loads = new HashMap<>();

        CoolingPlant() {
            capacities.put("CRAC-A", 12.0);
            capacities.put("CRAC-B", 12.0);
            loads.put("CRAC-A", 0.0);
            loads.put("CRAC-B", 0.0);
        }

        void reserve(String unit, double heatKW) {
            double projected = loads.get(unit) + heatKW;

            if (projected > capacities.get(unit)) {
                throw new IllegalStateException(
                    unit + " cannot support projected thermal load"
                );
            }

            loads.put(unit, projected);
        }

        boolean survivesSingleFailure(
            String failedUnit,
            double requiredHeatKW
        ) {
            return capacities.entrySet().stream()
                .filter(entry -> !entry.getKey().equals(failedUnit))
                .mapToDouble(Map.Entry::getValue)
                .sum() >= requiredHeatKW;
        }
    }

    static final class NetworkFabric {
        private final int portCapacity;
        private int switchAUsed;
        private int switchBUsed;

        NetworkFabric(int portCapacity) {
            this.portCapacity = portCapacity;
        }

        void connect(Server server) {
            if (switchAUsed >= portCapacity) {
                throw new IllegalStateException("TOR-A has no ports");
            }

            switchAUsed++;

            if (server.dualNetwork()) {
                if (switchBUsed >= portCapacity) {
                    throw new IllegalStateException("TOR-B has no ports");
                }
                switchBUsed++;
            }
        }

        boolean survivesSwitchFailure(List<Server> servers) {
            return servers.stream()
                .filter(server -> server.state() == ServerState.RUNNING)
                .allMatch(Server::dualNetwork);
        }

        void report() {
            System.out.printf(
                "TOR-A: %d/%d ports%n",
                switchAUsed,
                portCapacity
            );
            System.out.printf(
                "TOR-B: %d/%d ports%n",
                switchBUsed,
                portCapacity
            );
        }
    }

    static final class Repository {
        private final Map<String, Rack> racks = new HashMap<>();
        private final PowerSystem powerSystem = new PowerSystem(10.0);
        private final CoolingPlant coolingPlant = new CoolingPlant();
        private final NetworkFabric networkFabric = new NetworkFabric(48);
        private final List<Server> servers = new ArrayList<>();

        Repository() {
            racks.put("R01", new Rack("R01", 42, 8.0));
            racks.put("R02", new Rack("R02", 42, 8.0));
        }

        void provision(ServerSpec specification) {
            Rack rack = racks.get(specification.rackId());

            if (rack == null) {
                throw new IllegalArgumentException(
                    "Unknown rack " + specification.rackId()
                );
            }

            Server server = new Server(specification);

            if (!rack.canAccept(server)) {
                throw new IllegalStateException(
                    "Rack lacks physical or electrical capacity"
                );
            }

            powerSystem.connect(server);

            // Server electrical consumption is treated as thermal output.
            coolingPlant.reserve("CRAC-A", server.powerKW());
            networkFabric.connect(server);

            rack.install(server);
            servers.add(server);
        }

        double itLoadKW() {
            return servers.stream()
                .filter(server -> server.state() == ServerState.RUNNING)
                .mapToDouble(Server::powerKW)
                .sum();
        }

        void report() {
            System.out.println("\n=== ENTERPRISE DATA CENTER ===");

            for (Rack rack : racks.values()) {
                System.out.printf(
                    "%s: %d U used, %.2f kW used%n",
                    rack.id(),
                    rack.usedU(),
                    rack.usedPowerKW()
                );
            }

            System.out.printf(
                "IT load: %.2f kW%n",
                itLoadKW()
            );

            powerSystem.report();
            networkFabric.report();

            System.out.printf(
                "PUE with 4.0 kW facility overhead: %.3f%n",
                (itLoadKW() + 4.0) / itLoadKW()
            );
        }

        void failureAnalysis() {
            System.out.println("\n=== FAILURE ANALYSIS ===");

            System.out.println(
                "Power A survivability: " +
                powerSystem.survivesFailure(PowerPath.A, servers)
            );

            System.out.println(
                "Power B survivability: " +
                powerSystem.survivesFailure(PowerPath.B, servers)
            );

            System.out.println(
                "CRAC-A survivability: " +
                coolingPlant.survivesSingleFailure(
                    "CRAC-A",
                    itLoadKW()
                )
            );

            System.out.println(
                "TOR-A survivability: " +
                networkFabric.survivesSwitchFailure(servers)
            );
        }
    }

    public static void main(String[] args) {
        Repository dataCenter = new Repository();

        dataCenter.provision(new ServerSpec(
            "DB-PRIMARY",
            "R01",
            2.4,
            EquipmentRole.DATABASE,
            EnumSet.of(PowerPath.A),
            true
        ));

        dataCenter.provision(new ServerSpec(
            "APP-01",
            "R01",
            1.4,
            EquipmentRole.APPLICATION,
            EnumSet.of(PowerPath.B),
            true
        ));

        dataCenter.provision(new ServerSpec(
            "APP-02",
            "R02",
            1.4,
            EquipmentRole.APPLICATION,
            EnumSet.of(PowerPath.A),
            true
        ));

        dataCenter.provision(new ServerSpec(
            "BACKUP-01",
            "R02",
            1.8,
            EquipmentRole.BACKUP,
            EnumSet.of(PowerPath.B),
            true
        ));

        dataCenter.report();
        dataCenter.failureAnalysis();

        System.out.println(
            "\nEnterprise design rule: physical capacity, "
            + "power capacity, cooling capacity, and network redundancy "
            + "must be evaluated as separate failure domains."
        );
    }
}
