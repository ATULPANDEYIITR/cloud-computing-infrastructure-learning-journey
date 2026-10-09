#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

enum class ZoneStatus { Healthy, Degraded, Down };

std::string statusName(ZoneStatus status) {
    switch (status) {
        case ZoneStatus::Healthy: return "healthy";
        case ZoneStatus::Degraded: return "degraded";
        case ZoneStatus::Down: return "down";
    }
    throw std::logic_error("Unknown zone status");
}

struct Region {
    std::string id;
    std::string name;
    std::string residencyGroup;
};

struct Zone {
    std::string id;
    std::string regionId;
    std::set<std::string> failureDomains;
    ZoneStatus status = ZoneStatus::Healthy;
    int capacity = 100;
    int allocated = 0;
    double latencyMs = 5.0;

    int freeCapacity() const {
        if (status == ZoneStatus::Down) return 0;
        const int free = std::max(0, capacity - allocated);
        return status == ZoneStatus::Degraded ? free / 2 : free;
    }
};

struct Workload {
    std::string id;
    std::string regionId;
    int replicaCount;
    int minimumHealthy;
    std::map<std::string, int> placements;
};

class GovernanceEngine {
private:
    std::map<std::string, Region> regions_;
    std::map<std::string, Zone> zones_;
    std::map<std::string, Workload> workloads_;

public:
    void addRegion(const Region& region) {
        if (region.id.empty() || region.name.empty()) {
            throw std::invalid_argument("Region identity cannot be empty.");
        }
        if (!regions_.emplace(region.id, region).second) {
            throw std::invalid_argument("Duplicate region identifier.");
        }
    }

    void addZone(const Zone& zone) {
        if (zone.id.empty() || regions_.count(zone.regionId) == 0) {
            throw std::invalid_argument("Zone must have a valid region.");
        }
        if (zone.capacity < 0 || zone.allocated < 0 ||
            zone.allocated > zone.capacity || zone.latencyMs < 0) {
            throw std::invalid_argument("Invalid zone capacity or latency.");
        }
        if (!zones_.emplace(zone.id, zone).second) {
            throw std::invalid_argument("Duplicate zone identifier.");
        }
    }

    void addWorkload(const Workload& workload) {
        if (workload.id.empty() || regions_.count(workload.regionId) == 0) {
            throw std::invalid_argument("Workload must reference a region.");
        }
        if (workload.replicaCount < 1 ||
            workload.minimumHealthy < 1 ||
            workload.minimumHealthy > workload.replicaCount) {
            throw std::invalid_argument("Invalid workload replica policy.");
        }
        if (!workloads_.emplace(workload.id, workload).second) {
            throw std::invalid_argument("Duplicate workload identifier.");
        }
    }

    // Placement validation is performed before any capacity is consumed.
    void place(const std::string& workloadId,
               const std::vector<std::string>& zoneIds) {
        auto workloadIt = workloads_.find(workloadId);
        if (workloadIt == workloads_.end()) {
            throw std::invalid_argument("Unknown workload.");
        }

        Workload& workload = workloadIt->second;
        if (static_cast<int>(zoneIds.size()) != workload.replicaCount) {
            throw std::invalid_argument("Replica count does not match policy.");
        }

        std::set<std::string> distinct(zoneIds.begin(), zoneIds.end());
        if (distinct.size() != zoneIds.size()) {
            throw std::invalid_argument("Replicas must use distinct zones.");
        }

        std::vector<Zone*> selected;
        std::set<std::string> failureDomains;

        for (const auto& id : zoneIds) {
            auto zoneIt = zones_.find(id);
            if (zoneIt == zones_.end()) {
                throw std::invalid_argument("Unknown zone: " + id);
            }

            Zone& zone = zoneIt->second;
            if (zone.regionId != workload.regionId) {
                throw std::invalid_argument(
                    "Regional workload cannot cross region boundaries.");
            }
            if (zone.status != ZoneStatus::Healthy || zone.freeCapacity() < 1) {
                throw std::runtime_error("Zone is unhealthy or lacks capacity.");
            }

            for (const auto& domain : zone.failureDomains) {
                if (failureDomains.count(domain) != 0) {
                    throw std::invalid_argument(
                        "Selected zones share a modeled failure domain.");
                }
            }
            failureDomains.insert(
                zone.failureDomains.begin(), zone.failureDomains.end());
            selected.push_back(&zone);
        }

        for (Zone* zone : selected) {
            ++zone->allocated;
        }

        workload.placements.clear();
        for (const auto& id : zoneIds) {
            workload.placements[id] = 1;
        }
    }

    int healthyReplicas(const Workload& workload) const {
        int healthy = 0;
        for (const auto& [zoneId, count] : workload.placements) {
            auto it = zones_.find(zoneId);
            if (it != zones_.end() &&
                it->second.status == ZoneStatus::Healthy) {
                healthy += count;
            }
        }
        return healthy;
    }

    bool available(const Workload& workload) const {
        return healthyReplicas(workload) >= workload.minimumHealthy;
    }

    void setZoneStatus(const std::string& zoneId, ZoneStatus status) {
        auto it = zones_.find(zoneId);
        if (it == zones_.end()) {
            throw std::invalid_argument("Unknown zone.");
        }
        it->second.status = status;
    }

    void printReport() const {
        std::cout << "\nRegional infrastructure\n";
        for (const auto& [id, region] : regions_) {
            std::cout << "Region " << id << " (" << region.name << ")\n";
            for (const auto& [zoneId, zone] : zones_) {
                if (zone.regionId != id) continue;
                std::cout << "  " << zoneId
                          << " state=" << statusName(zone.status)
                          << " capacity=" << zone.allocated << "/"
                          << zone.capacity
                          << " latency=" << zone.latencyMs << "ms\n";
            }
        }

        std::cout << "\nWorkload health\n";
        for (const auto& [id, workload] : workloads_) {
            std::cout << "  " << id << ": healthy replicas="
                      << healthyReplicas(workload) << "/"
                      << workload.replicaCount
                      << ", required=" << workload.minimumHealthy
                      << ", available="
                      << (available(workload) ? "yes" : "no") << "\n";
        }
    }

    void simulateFailure(const std::string& zoneId) {
        std::cout << "\nSimulating outage of " << zoneId << "\n";
        setZoneStatus(zoneId, ZoneStatus::Down);

        for (const auto& [id, workload] : workloads_) {
            if (workload.placements.count(zoneId) == 0) continue;
            std::cout << "  Workload " << id
                      << " has " << healthyReplicas(workload)
                      << " healthy replicas: "
                      << (available(workload) ? "serving" : "unavailable")
                      << "\n";
        }
    }
};

double serialAvailability(const std::vector<double>& components) {
    double result = 1.0;
    for (double value : components) {
        if (!std::isfinite(value) || value < 0.0 || value > 1.0) {
            throw std::invalid_argument("Availability must be in [0, 1].");
        }
        result *= value;
    }
    return result;
}

double parallelAvailability(const std::vector<double>& replicas) {
    double allFail = 1.0;
    for (double value : replicas) {
        if (!std::isfinite(value) || value < 0.0 || value > 1.0) {
            throw std::invalid_argument("Availability must be in [0, 1].");
        }
        allFail *= 1.0 - value;
    }
    return 1.0 - allFail;
}

int main() {
    try {
        GovernanceEngine engine;
        engine.addRegion({"ap-south", "South Asia", "IN"});

        engine.addZone({
            "zone-a", "ap-south", {"power-a", "network-a"},
            ZoneStatus::Healthy, 10, 0, 4.0
        });
        engine.addZone({
            "zone-b", "ap-south", {"power-b", "network-b"},
            ZoneStatus::Healthy, 10, 0, 6.0
        });
        engine.addZone({
            "zone-c", "ap-south", {"power-c", "network-c"},
            ZoneStatus::Healthy, 10, 0, 8.0
        });

        engine.addWorkload({
            "order-processing", "ap-south", 3, 2, {}
        });

        engine.place("order-processing", {"zone-a", "zone-b", "zone-c"});
        engine.printReport();
        engine.simulateFailure("zone-a");
        engine.printReport();

        std::cout << "\nReliability estimates\n";
        std::cout << std::fixed << std::setprecision(6)
                  << "Two independent replicas at 99.9%: "
                  << parallelAvailability({0.999, 0.999}) << "\n"
                  << "Three serial dependencies at 99.9%: "
                  << serialAvailability({0.999, 0.999, 0.999}) << "\n";

        // A shared dependency violates the intended fault-domain separation.
        try {
            engine.place("order-processing", {"zone-a", "zone-b", "zone-c"});
        } catch (const std::exception& error) {
            std::cout << "\nExpected placement rejection: "
                      << error.what() << "\n";
        }

    } catch (const std::exception& error) {
        std::cerr << "Fatal infrastructure error: "
                  << error.what() << "\n";
        return 1;
    }

    return 0;
}
