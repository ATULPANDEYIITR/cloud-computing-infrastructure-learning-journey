#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Repository-independent infrastructure governance case study:
 * a regional payment API scaling group serving production traffic.
 *
 * This C++17 program implements a discrete-event capacity controller with
 * explicit resource states, metric windows, policy thresholds, cooldowns,
 * protected instances, health replacement, and cost accounting.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic autoscaling.cpp -o autoscaling
 *
 * Run:
 *   ./autoscaling
 *
 * All capacity and monitoring behavior is simulated.
 */

enum class InstanceState {
    Warming,
    Ready,
    Unhealthy,
    Terminating
};

enum class Decision {
    Hold,
    ScaleOut,
    ScaleIn,
    Cooldown,
    AtLimit,
    InsufficientSamples
};

std::string to_string(InstanceState state) {
    switch (state) {
        case InstanceState::Warming: return "warming";
        case InstanceState::Ready: return "ready";
        case InstanceState::Unhealthy: return "unhealthy";
        case InstanceState::Terminating: return "terminating";
    }
    throw std::logic_error("Unknown instance state.");
}

std::string to_string(Decision decision) {
    switch (decision) {
        case Decision::Hold: return "hold";
        case Decision::ScaleOut: return "scale_out";
        case Decision::ScaleIn: return "scale_in";
        case Decision::Cooldown: return "cooldown";
        case Decision::AtLimit: return "capacity_limit";
        case Decision::InsufficientSamples: return "insufficient_samples";
    }
    throw std::logic_error("Unknown scaling decision.");
}

struct Metric {
    int minute;
    double cpu_percent;
    double requests_per_second;
    double p95_latency_ms;
    double error_percent;

    Metric(
        int timestamp,
        double cpu,
        double requests,
        double latency,
        double errors
    ) : minute(timestamp),
        cpu_percent(cpu),
        requests_per_second(requests),
        p95_latency_ms(latency),
        error_percent(errors) {
        if (minute < 0) {
            throw std::invalid_argument("Timestamp cannot be negative.");
        }
        if (!std::isfinite(cpu_percent) || cpu_percent < 0 || cpu_percent > 100) {
            throw std::invalid_argument("CPU must be between 0 and 100.");
        }
        if (!std::isfinite(requests_per_second) || requests_per_second < 0) {
            throw std::invalid_argument("Request rate must be non-negative.");
        }
        if (!std::isfinite(p95_latency_ms) || p95_latency_ms < 0) {
            throw std::invalid_argument("Latency must be non-negative.");
        }
        if (!std::isfinite(error_percent) || error_percent < 0 || error_percent > 100) {
            throw std::invalid_argument("Error percentage must be between 0 and 100.");
        }
    }
};

struct Instance {
    std::string id;
    InstanceState state;
    int launched_minute;
    int ready_minute;
    bool protected_from_scale_in = false;
};

struct ScalingEvent {
    int minute;
    std::string action;
    int old_capacity;
    int new_capacity;
    std::string reason;
};

struct TargetTrackingPolicy {
    std::string name;
    double target_cpu_percent;
    double scale_out_ratio = 1.10;
    double scale_in_ratio = 0.75;
    int required_breach_periods = 2;
    int scale_out_cooldown_minutes = 2;
    int scale_in_cooldown_minutes = 3;
    int scale_in_step = 1;
    int maximum_scale_out_step = 4;
};

class ScalingGroup {
private:
    std::string name_;
    int minimum_;
    int maximum_;
    int desired_;
    int warmup_minutes_;
    int next_id_ = 1;
    int last_scale_out_minute_ = -1;
    int last_scale_in_minute_ = -1;

    std::map<std::string, Instance> instances_;
    std::vector<ScalingEvent> events_;

    void launch_instance(int minute) {
        std::string id = name_ + "-" + std::to_string(next_id_++);
        Instance instance{
            id,
            warmup_minutes_ == 0 ? InstanceState::Ready : InstanceState::Warming,
            minute,
            minute + warmup_minutes_,
            false
        };
        instances_.emplace(id, instance);
        std::cout << "  LAUNCH " << id << " (" << to_string(instance.state) << ")\n";
    }

    void terminate_one(int minute, const std::string& reason) {
        auto victim = instances_.end();

        // Deterministic victim selection makes the simulation reproducible.
        for (auto it = instances_.begin(); it != instances_.end(); ++it) {
            if (it->second.protected_from_scale_in) {
                continue;
            }
            if (
                victim == instances_.end() ||
                it->second.launched_minute < victim->second.launched_minute
            ) {
                victim = it;
            }
        }

        if (victim == instances_.end()) {
            return;
        }

        const std::string id = victim->first;
        victim->second.state = InstanceState::Terminating;
        instances_.erase(victim);
        std::cout << "  TERMINATE " << id << " (" << reason << ")\n";
        events_.push_back({
            minute, "terminate", desired_, desired_, reason + ": " + id
        });
    }

public:
    ScalingGroup(
        std::string name,
        int minimum,
        int maximum,
        int desired,
        int warmup_minutes
    ) : name_(std::move(name)),
        minimum_(minimum),
        maximum_(maximum),
        desired_(desired),
        warmup_minutes_(warmup_minutes) {
        if (name_.empty()) {
            throw std::invalid_argument("Group name cannot be empty.");
        }
        if (
            minimum_ < 0 ||
            maximum_ < minimum_ ||
            desired_ < minimum_ ||
            desired_ > maximum_ ||
            warmup_minutes_ < 0
        ) {
            throw std::invalid_argument("Invalid scaling-group configuration.");
        }
    }

    int desired() const {
        return desired_;
    }

    int actual() const {
        return static_cast<int>(instances_.size());
    }

    int ready() const {
        return static_cast<int>(std::count_if(
            instances_.begin(),
            instances_.end(),
            [](const auto& pair) {
                return pair.second.state == InstanceState::Ready;
            }
        ));
    }

    void reconcile(int minute) {
        for (auto& [id, instance] : instances_) {
            if (
                instance.state == InstanceState::Warming &&
                minute >= instance.ready_minute
            ) {
                instance.state = InstanceState::Ready;
                std::cout << "  READY " << id << "\n";
            }
        }

        while (actual() < desired_) {
            launch_instance(minute);
        }

        while (actual() > desired_) {
            const int before = actual();
            terminate_one(minute, "desired-capacity reconciliation");
            if (actual() == before) {
                // Protected instances can temporarily prevent scale-in.
                break;
            }
        }
    }

    bool change_capacity(int delta, int minute, const std::string& reason) {
        const int old_capacity = desired_;
        const int new_capacity = std::clamp(
            old_capacity + delta, minimum_, maximum_
        );

        if (new_capacity == old_capacity) {
            events_.push_back({
                minute, "at_limit", old_capacity, old_capacity, reason
            });
            return false;
        }

        desired_ = new_capacity;
        const std::string action =
            new_capacity > old_capacity ? "scale_out" : "scale_in";

        if (action == "scale_out") {
            last_scale_out_minute_ = minute;
        } else {
            last_scale_in_minute_ = minute;
        }

        events_.push_back({
            minute, action, old_capacity, new_capacity, reason
        });

        std::cout << "  " << action << ": " << old_capacity
                  << " -> " << new_capacity << " (" << reason << ")\n";

        reconcile(minute);
        return true;
    }

    bool cooldown_active(
        bool scale_out,
        int minute,
        int duration
    ) const {
        const int last = scale_out
            ? last_scale_out_minute_
            : last_scale_in_minute_;

        return last >= 0 && minute - last < duration;
    }

    void protect_instance(const std::string& id, bool protect) {
        auto it = instances_.find(id);
        if (it == instances_.end()) {
            throw std::out_of_range("Instance does not exist: " + id);
        }
        it->second.protected_from_scale_in = protect;
    }

    void mark_unhealthy(const std::string& id, int minute) {
        auto it = instances_.find(id);
        if (it == instances_.end()) {
            throw std::out_of_range("Instance does not exist: " + id);
        }

        it->second.state = InstanceState::Unhealthy;
        instances_.erase(it);
        events_.push_back({
            minute, "health_failure", desired_, desired_, id
        });

        std::cout << "  HEALTH FAILURE " << id
                  << "; replacing instance\n";
        reconcile(minute);
    }

    void print_state(int minute) const {
        std::cout << "minute=" << std::setw(3) << minute
                  << " desired=" << std::setw(2) << desired_
                  << " actual=" << std::setw(2) << actual()
                  << " ready=" << std::setw(2) << ready() << '\n';
    }

    const std::vector<ScalingEvent>& events() const {
        return events_;
    }

    std::vector<std::string> instance_ids() const {
        std::vector<std::string> ids;
        ids.reserve(instances_.size());
        for (const auto& [id, instance] : instances_) {
            ids.push_back(id);
        }
        return ids;
    }
};

class ScalingController {
private:
    ScalingGroup& group_;
    TargetTrackingPolicy policy_;
    std::vector<double> cpu_window_;
    int window_size_;
    int out_breaches_ = 0;
    int in_breaches_ = 0;
    std::optional<int> last_metric_minute_;

    double average_cpu() const {
        double total = 0.0;
        for (double cpu : cpu_window_) {
            total += cpu;
        }
        return total / static_cast<double>(cpu_window_.size());
    }

public:
    ScalingController(
        ScalingGroup& group,
        TargetTrackingPolicy policy,
        int window_size
    ) : group_(group),
        policy_(std::move(policy)),
        window_size_(window_size) {
        if (
            policy_.target_cpu_percent <= 0 ||
            policy_.target_cpu_percent > 100 ||
            policy_.required_breach_periods < 1 ||
            policy_.scale_out_ratio <= 1 ||
            policy_.scale_in_ratio <= 0 ||
            policy_.scale_in_ratio >= 1 ||
            window_size_ < 1
        ) {
            throw std::invalid_argument("Invalid target-tracking policy.");
        }
    }

    Decision evaluate(const Metric& metric) {
        if (
            last_metric_minute_.has_value() &&
            metric.minute < *last_metric_minute_
        ) {
            throw std::invalid_argument("Metrics must be chronological.");
        }
        last_metric_minute_ = metric.minute;

        group_.reconcile(metric.minute);
        cpu_window_.push_back(metric.cpu_percent);
        if (static_cast<int>(cpu_window_.size()) > window_size_) {
            cpu_window_.erase(cpu_window_.begin());
        }

        if (group_.ready() == 0) {
            return Decision::InsufficientSamples;
        }

        const double average = average_cpu();
        const double ratio = average / policy_.target_cpu_percent;

        if (ratio >= policy_.scale_out_ratio) {
            ++out_breaches_;
            in_breaches_ = 0;
        } else if (ratio <= policy_.scale_in_ratio) {
            ++in_breaches_;
            out_breaches_ = 0;
        } else {
            out_breaches_ = 0;
            in_breaches_ = 0;
            return Decision::Hold;
        }

        if (out_breaches_ >= policy_.required_breach_periods) {
            if (group_.cooldown_active(
                true, metric.minute, policy_.scale_out_cooldown_minutes
            )) {
                return Decision::Cooldown;
            }

            const int proportional_delta = static_cast<int>(
                std::ceil(group_.desired() * (ratio - 1.0))
            );
            const int delta = std::clamp(
                proportional_delta, 1, policy_.maximum_scale_out_step
            );
            out_breaches_ = 0;

            return group_.change_capacity(
                delta,
                metric.minute,
                policy_.name + ": CPU average " + std::to_string(average)
            ) ? Decision::ScaleOut : Decision::AtLimit;
        }

        if (in_breaches_ >= policy_.required_breach_periods) {
            if (group_.cooldown_active(
                false, metric.minute, policy_.scale_in_cooldown_minutes
            )) {
                return Decision::Cooldown;
            }

            in_breaches_ = 0;
            return group_.change_capacity(
                -policy_.scale_in_step,
                metric.minute,
                policy_.name + ": sustained low CPU"
            ) ? Decision::ScaleIn : Decision::AtLimit;
        }

        return Decision::InsufficientSamples;
    }
};

double calculate_cost(
    int instance_hours,
    double hourly_rate
) {
    if (instance_hours < 0 || !std::isfinite(hourly_rate) || hourly_rate < 0) {
        throw std::invalid_argument("Cost inputs must be non-negative.");
    }
    return instance_hours * hourly_rate;
}

int main() {
    try {
        std::cout << "PAYMENT API AUTO SCALING CASE STUDY\n";
        std::cout << "==================================\n";

        ScalingGroup group("payment-api", 2, 10, 3, 1);
        group.reconcile(0);

        TargetTrackingPolicy policy{
            "payment-cpu-target",
            55.0,
            1.10,
            0.75,
            2,
            2,
            3,
            1,
            4
        };

        ScalingController controller(group, policy, 2);

        const std::vector<Metric> traffic = {
            {0, 35, 120, 100, 0.1},
            {1, 60, 200, 170, 0.2},
            {2, 72, 280, 240, 0.3},
            {3, 84, 360, 390, 1.2},
            {4, 80, 370, 410, 1.4},
            {5, 45, 230, 210, 0.3},
            {6, 32, 140, 130, 0.1},
            {7, 28, 100, 110, 0.1},
            {8, 25, 90, 100, 0.1},
            {9, 24, 85, 95, 0.1}
        };

        std::cout << "\nTraffic evaluation\n";
        for (const auto& metric : traffic) {
            const Decision decision = controller.evaluate(metric);
            std::cout << "decision=" << std::setw(22)
                      << std::left << to_string(decision)
                      << std::right
                      << " CPU=" << std::setw(5) << metric.cpu_percent
                      << "% latency=" << std::setw(4)
                      << metric.p95_latency_ms << "ms ";
            group.print_state(metric.minute);
        }

        std::cout << "\nProtected capacity behavior\n";
        const auto ids = group.instance_ids();
        if (!ids.empty()) {
            group.protect_instance(ids.front(), true);
            group.change_capacity(-group.desired(), 10, "attempt scale-in");
            std::cout << "Desired capacity is bounded by the minimum; "
                      << "protected instances cannot be selected for removal.\n";
            group.protect_instance(ids.front(), false);
        }

        std::cout << "\nScheduled traffic preparation\n";
        group.change_capacity(2, 11, "scheduled business-hours capacity");
        group.print_state(11);

        std::cout << "\nHealth-check recovery\n";
        const auto after_schedule = group.instance_ids();
        if (!after_schedule.empty()) {
            group.mark_unhealthy(after_schedule.front(), 12);
        }
        group.print_state(12);

        std::cout << "\nIllustrative compute cost\n";
        const int instance_hours = group.actual() * 24 * 30;
        const double monthly_cost = calculate_cost(instance_hours, 0.048);
        std::cout << "instance_hours=" << instance_hours
                  << " monthly_cost=$" << std::fixed << std::setprecision(2)
                  << monthly_cost << '\n';

        std::cout << "\nAudit history\n";
        for (const auto& event : group.events()) {
            std::cout << "minute=" << event.minute
                      << " action=" << event.action
                      << " capacity=" << event.old_capacity
                      << "->" << event.new_capacity
                      << " reason=" << event.reason << '\n';
        }

        // A bounded group cannot grow past max_size even during a large spike.
        group.change_capacity(1000, 13, "extreme traffic spike");
        if (group.desired() > 10) {
            throw std::logic_error("Maximum capacity invariant violated.");
        }

        std::cout << "\nMaximum-capacity invariant verified.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Simulation error: " << error.what() << '\n';
        return 1;
    }
}
