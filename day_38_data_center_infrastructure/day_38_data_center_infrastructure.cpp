#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

enum class PowerPath {
    A,
    B,
    SingleA,
    SingleB
};

enum class ServerState {
    Running,
    Failed,
    Maintenance
};

struct Server {
    std::string name;
    std::string rack;
    double powerKW;
    PowerPath powerPath;
    bool dualNetwork;
    ServerState state{ServerState::Running};

    double thermalLoadKW() const {
        // IT electrical energy ultimately becomes heat in the data hall.
        return powerKW;
    }
};

class Rack {
private:
    std::string id_;
    int capacityU_;
    double powerCapacityKW_;
    std::vector<const Server*> servers_;

public:
    Rack(std::string id, int capacityU, double powerCapacityKW)
        : id_(std::move(id)),
          capacityU_(capacityU),
          powerCapacityKW_(powerCapacityKW) {
        if (capacityU_ <= 0 || powerCapacityKW_ <= 0) {
            throw std::invalid_argument("Rack capacity must be positive");
        }
    }

    bool canInstall(const Server& server) const {
        return static_cast<int>(servers_.size()) < capacityU_ &&
               usedPowerKW() + server.powerKW <= powerCapacityKW_;
    }

    void install(const Server& server) {
        if (!canInstall(server)) {
            throw std::runtime_error(
                "Rack " + id_ + " cannot accept " + server.name
            );
        }
        servers_.push_back(&server);
    }

    double usedPowerKW() const {
        double result = 0.0;
        for (const Server* server : servers_) {
            result += server->powerKW;
        }
        return result;
    }

    int usedU() const {
        return static_cast<int>(servers_.size());
    }

    double availablePowerKW() const {
        return powerCapacityKW_ - usedPowerKW();
    }

    const std::string& id() const {
        return id_;
    }

    void report() const {
        std::cout << "Rack " << id_
                  << ": " << usedU() << "/" << capacityU_
                  << " U, "
                  << std::fixed << std::setprecision(2)
                  << usedPowerKW() << "/" << powerCapacityKW_
                  << " kW\n";
    }
};

class PowerFeed {
private:
    std::string name_;
    double capacityKW_;
    double loadKW_{0.0};

public:
    PowerFeed(std::string name, double capacityKW)
        : name_(std::move(name)), capacityKW_(capacityKW) {
        if (capacityKW_ <= 0) {
            throw std::invalid_argument("Power capacity must be positive");
        }
    }

    void reserve(double powerKW) {
        if (loadKW_ + powerKW > capacityKW_ + 1e-9) {
            throw std::runtime_error(
                "Power feed " + name_ + " would exceed capacity"
            );
        }
        loadKW_ += powerKW;
    }

    double loadKW() const {
        return loadKW_;
    }

    double capacityKW() const {
        return capacityKW_;
    }

    const std::string& name() const {
        return name_;
    }
};

class CoolingSystem {
private:
    std::string name_;
    double capacityKW_;
    double loadKW_{0.0};

public:
    CoolingSystem(std::string name, double capacityKW)
        : name_(std::move(name)), capacityKW_(capacityKW) {}

    void reserve(double thermalLoadKW) {
        if (loadKW_ + thermalLoadKW > capacityKW_ + 1e-9) {
            throw std::runtime_error(
                "Cooling system " + name_ + " would exceed capacity"
            );
        }
        loadKW_ += thermalLoadKW;
    }

    double capacityKW() const {
        return capacityKW_;
    }

    double loadKW() const {
        return loadKW_;
    }

    const std::string& name() const {
        return name_;
    }
};

class NetworkFabric {
private:
    int switchAPorts_;
    int switchBPorts_;
    int usedA_{0};
    int usedB_{0};

public:
    explicit NetworkFabric(int portsPerSwitch)
        : switchAPorts_(portsPerSwitch),
          switchBPorts_(portsPerSwitch) {}

    void connect(const Server& server) {
        if (usedA_ >= switchAPorts_) {
            throw std::runtime_error("TOR-A has no available ports");
        }

        ++usedA_;

        if (server.dualNetwork) {
            if (usedB_ >= switchBPorts_) {
                throw std::runtime_error("TOR-B has no available ports");
            }
            ++usedB_;
        }
    }

    bool survivesSwitchFailure(const std::vector<Server>& servers) const {
        // A dual-network server has an alternate top-of-rack path.
        return std::all_of(
            servers.begin(),
            servers.end(),
            [](const Server& server) {
                return server.state != ServerState::Running ||
                       server.dualNetwork;
            }
        );
    }

    void report() const {
        std::cout << "TOR-A ports: " << usedA_
                  << "/" << switchAPorts_ << "\n";
        std::cout << "TOR-B ports: " << usedB_
                  << "/" << switchBPorts_ << "\n";
    }
};

class MergeStyleCapacityPlanner {
public:
    static int minimumRacks(
        int serverCount,
        double serverPowerKW,
        double rackPowerCapacityKW,
        int rackU = 42
    ) {
        if (serverCount <= 0 ||
            serverPowerKW <= 0 ||
            rackPowerCapacityKW <= 0 ||
            rackU <= 0) {
            throw std::invalid_argument(
                "Capacity-planning inputs must be positive"
            );
        }

        const int byPower = static_cast<int>(
            rackPowerCapacityKW / serverPowerKW
        );

        const int serversPerRack = std::max(
            1,
            std::min(rackU, byPower)
        );

        return (serverCount + serversPerRack - 1) / serversPerRack;
    }
};

class DataCenter {
private:
    std::map<std::string, Rack> racks_;
    PowerFeed powerA_;
    PowerFeed powerB_;
    CoolingSystem coolingA_;
    CoolingSystem coolingB_;
    NetworkFabric network_;
    std::vector<Server> servers_;

public:
    DataCenter()
        : racks_{
              {"R01", Rack("R01", 42, 8.0)},
              {"R02", Rack("R02", 42, 8.0)}
          },
          powerA_("A", 10.0),
          powerB_("B", 10.0),
          coolingA_("CRAC-A", 12.0),
          coolingB_("CRAC-B", 12.0),
          network_(48) {}

    void addServer(const Server& server) {
        auto rackIt = racks_.find(server.rack);

        if (rackIt == racks_.end()) {
            throw std::invalid_argument(
                "Unknown rack: " + server.rack
            );
        }

        Rack& rack = rackIt->second;

        if (!rack.canInstall(server)) {
            throw std::runtime_error(
                "Rack capacity violation for " + server.name
            );
        }

        // Dual-corded equipment is modeled as sharing its load between
        // independent electrical paths. A real design would also validate
        // upstream transformers, PDUs, UPS modules, and generators.
        switch (server.powerPath) {
            case PowerPath::A:
                powerA_.reserve(server.powerKW);
                break;
            case PowerPath::B:
                powerB_.reserve(server.powerKW);
                break;
            case PowerPath::SingleA:
                powerA_.reserve(server.powerKW);
                break;
            case PowerPath::SingleB:
                powerB_.reserve(server.powerKW);
                break;
        }

        // The cooling model treats IT power as equivalent thermal load.
        coolingA_.reserve(server.thermalLoadKW());

        network_.connect(server);

        servers_.push_back(server);
        rack.install(servers_.back());
    }

    double totalITLoadKW() const {
        double total = 0.0;

        for (const Server& server : servers_) {
            if (server.state == ServerState::Running) {
                total += server.powerKW;
            }
        }

        return total;
    }

    bool survivesPowerFeedFailure(PowerPath failedPath) const {
        for (const Server& server : servers_) {
            if (server.state != ServerState::Running) {
                continue;
            }

            if (failedPath == PowerPath::A &&
                server.powerPath == PowerPath::SingleA) {
                return false;
            }

            if (failedPath == PowerPath::B &&
                server.powerPath == PowerPath::SingleB) {
                return false;
            }
        }

        return true;
    }

    bool survivesCoolingFailure() const {
        double remainingCapacity = coolingB_.capacityKW();
        return remainingCapacity >= totalITLoadKW();
    }

    void report() const {
        std::cout << "\n=== REPOSITORY-STYLE INFRASTRUCTURE CASE STUDY ===\n";
        std::cout << "Physical IT load: "
                  << totalITLoadKW() << " kW\n";

        for (const auto& [id, rack] : racks_) {
            rack.report();
        }

        std::cout << "Power A: "
                  << powerA_.loadKW() << "/"
                  << powerA_.capacityKW() << " kW\n";

        std::cout << "Power B: "
                  << powerB_.loadKW() << "/"
                  << powerB_.capacityKW() << " kW\n";

        std::cout << "Cooling A: "
                  << coolingA_.loadKW() << "/"
                  << coolingA_.capacityKW() << " kW\n";

        network_.report();
    }
};

int main() {
    try {
        std::cout << "Minimum racks for 80 servers at 0.6 kW/server: "
                  << MergeStyleCapacityPlanner::minimumRacks(
                         80, 0.6, 8.0
                     )
                  << "\n";

        DataCenter dataCenter;

        // The workload deliberately contains a database, applications, and
        // backup infrastructure. Each production server has dual network
        // connectivity, while electrical diversity is modeled per server.
        dataCenter.addServer({
            "DB-PRIMARY",
            "R01",
            2.4,
            PowerPath::A,
            true
        });

        dataCenter.addServer({
            "APP-01",
            "R01",
            1.4,
            PowerPath::B,
            true
        });

        dataCenter.addServer({
            "APP-02",
            "R02",
            1.4,
            PowerPath::A,
            true
        });

        dataCenter.addServer({
            "BACKUP-01",
            "R02",
            1.8,
            PowerPath::B,
            true
        });

        dataCenter.report();

        const double facilityOverheadKW = 4.0;
        const double itLoad = dataCenter.totalITLoadKW();
        const double pue = (itLoad + facilityOverheadKW) / itLoad;

        std::cout << std::fixed << std::setprecision(3);
        std::cout << "Estimated PUE: " << pue << "\n";

        std::cout << "\n=== FAILURE-DOMAIN ANALYSIS ===\n";

        std::cout << "Power-A failure: "
                  << (dataCenter.survivesPowerFeedFailure(PowerPath::A)
                          ? "survivable"
                          : "not survivable")
                  << "\n";

        std::cout << "Power-B failure: "
                  << (dataCenter.survivesPowerFeedFailure(PowerPath::B)
                          ? "survivable"
                          : "not survivable")
                  << "\n";

        std::cout << "Cooling-A failure: "
                  << (dataCenter.survivesCoolingFailure()
                          ? "survivable under modeled capacity"
                          : "cooling capacity insufficient")
                  << "\n";

        std::cout << "Network switch failure: "
                  << (dataCenter.survivesCoolingFailure()
                          ? "network model assumes dual paths"
                          : "requires investigation")
                  << "\n";

        std::cout << "\nThe model distinguishes rack capacity, "
                     "electrical capacity, thermal capacity, and network "
                     "failure domains instead of treating availability as "
                     "a single property.\n";
    }
    catch (const std::exception& ex) {
        std::cerr << "Infrastructure validation failed: "
                  << ex.what() << "\n";
        return 1;
    }

    return 0;
}
