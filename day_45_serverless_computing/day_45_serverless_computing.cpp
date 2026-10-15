#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Serverless repository-independent case study:
 * an order-processing platform with event-triggered functions, execution
 * environments, capacity controls, retries, cold-start costs, and a
 * deterministic merge of operational metrics.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic serverless_governance.cpp -o serverless_demo
 * Run:
 *   ./serverless_demo
 */

enum class InvocationState {
    Accepted,
    Succeeded,
    Failed,
    Throttled,
    TimedOut
};

enum class TriggerType {
    HttpRequest,
    ObjectCreated,
    Scheduled,
    QueueMessage
};

std::string toString(InvocationState state) {
    switch (state) {
        case InvocationState::Accepted: return "accepted";
        case InvocationState::Succeeded: return "succeeded";
        case InvocationState::Failed: return "failed";
        case InvocationState::Throttled: return "throttled";
        case InvocationState::TimedOut: return "timed_out";
    }
    return "unknown";
}

std::string toString(TriggerType trigger) {
    switch (trigger) {
        case TriggerType::HttpRequest: return "HTTP";
        case TriggerType::ObjectCreated: return "object-created";
        case TriggerType::Scheduled: return "scheduled";
        case TriggerType::QueueMessage: return "queue-message";
    }
    return "unknown";
}

struct Event {
    std::string id;
    TriggerType trigger;
    std::string eventType;
    std::map<std::string, std::string> attributes;
    double arrivalTimeMs;
};

struct FunctionConfiguration {
    std::string name;
    int memoryMb = 256;
    double timeoutMs = 1000.0;
    double initializationMs = 100.0;
    int maxConcurrency = 10;
    int maxRetries = 1;
    double idleTtlMs = 300000.0;

    void validate() const {
        if (name.empty()) {
            throw std::invalid_argument("Function name cannot be empty.");
        }
        if (memoryMb < 128) {
            throw std::invalid_argument("Memory must be at least 128 MB.");
        }
        if (timeoutMs <= 0.0 || initializationMs < 0.0) {
            throw std::invalid_argument("Invalid timing configuration.");
        }
        if (maxConcurrency < 1 || maxRetries < 0 || idleTtlMs < 0.0) {
            throw std::invalid_argument("Invalid concurrency or retry policy.");
        }
    }
};

struct ExecutionEnvironment {
    std::string id;
    double createdAtMs;
    double lastUsedAtMs;
    int invocations = 0;
    bool busy = false;
};

struct InvocationRecord {
    std::string eventId;
    std::string functionName;
    InvocationState state;
    bool coldStart;
    int attempts;
    double initializationMs;
    double handlerDurationMs;
    std::string message;
};

struct FunctionMetrics {
    int accepted = 0;
    int succeeded = 0;
    int failed = 0;
    int throttled = 0;
    int timedOut = 0;
    int retries = 0;
    int coldStarts = 0;
    double billedDurationMs = 0.0;
    std::vector<double> successfulDurations;

    double averageDuration() const {
        if (successfulDurations.empty()) {
            return 0.0;
        }
        double total = 0.0;
        for (double duration : successfulDurations) {
            total += duration;
        }
        return total / successfulDurations.size();
    }
};

class FunctionRuntime {
public:
    using Handler = std::string (*)(const Event&);

    FunctionRuntime(FunctionConfiguration configuration, Handler handler)
        : config_(std::move(configuration)), handler_(handler) {
        config_.validate();
        if (handler_ == nullptr) {
            throw std::invalid_argument("Function handler is required.");
        }
    }

    InvocationRecord invoke(
        const Event& event,
        double handlerDurationMs,
        bool simulateHandlerFailure = false
    ) {
        ++metrics_.accepted;

        if (handlerDurationMs < 0.0) {
            throw std::invalid_argument("Handler duration cannot be negative.");
        }

        int attempts = 0;
        bool sawColdStart = false;
        double initializationMs = 0.0;
        std::string lastError = "Unknown execution failure";

        for (int attempt = 0; attempt <= config_.maxRetries; ++attempt) {
            ++attempts;

            auto lease = acquire(event.arrivalTimeMs);
            if (!lease.has_value()) {
                ++metrics_.throttled;
                return {
                    event.id,
                    config_.name,
                    InvocationState::Throttled,
                    sawColdStart,
                    attempts,
                    initializationMs,
                    0.0,
                    "Concurrency limit reached"
                };
            }

            ExecutionEnvironment& environment = environments_[*lease];
            const bool cold = environment.invocations == 0;
            sawColdStart = sawColdStart || cold;

            if (cold) {
                ++metrics_.coldStarts;
                initializationMs += config_.initializationMs;
            }

            const double totalDuration =
                handlerDurationMs + (cold ? config_.initializationMs : 0.0);

            if (totalDuration > config_.timeoutMs) {
                ++metrics_.timedOut;
                lastError = "Configured execution timeout exceeded";
                release(*lease, event.arrivalTimeMs);

                if (attempt < config_.maxRetries) {
                    ++metrics_.retries;
                    continue;
                }

                ++metrics_.failed;
                return {
                    event.id,
                    config_.name,
                    InvocationState::TimedOut,
                    sawColdStart,
                    attempts,
                    initializationMs,
                    totalDuration,
                    lastError
                };
            }

            if (simulateHandlerFailure) {
                lastError = "Downstream dependency returned an error";
                release(*lease, event.arrivalTimeMs);

                if (attempt < config_.maxRetries) {
                    ++metrics_.retries;
                    continue;
                }

                ++metrics_.failed;
                return {
                    event.id,
                    config_.name,
                    InvocationState::Failed,
                    sawColdStart,
                    attempts,
                    initializationMs,
                    totalDuration,
                    lastError
                };
            }

            try {
                const std::string result = handler_(event);
                ++environment.invocations;
                release(*lease, event.arrivalTimeMs);
                ++metrics_.succeeded;
                metrics_.billedDurationMs += totalDuration;
                metrics_.successfulDurations.push_back(totalDuration);

                return {
                    event.id,
                    config_.name,
                    InvocationState::Succeeded,
                    sawColdStart,
                    attempts,
                    initializationMs,
                    handlerDurationMs,
                    result
                };
            } catch (const std::exception& exception) {
                lastError = exception.what();
                release(*lease, event.arrivalTimeMs);

                if (attempt < config_.maxRetries) {
                    ++metrics_.retries;
                    continue;
                }

                ++metrics_.failed;
                return {
                    event.id,
                    config_.name,
                    InvocationState::Failed,
                    sawColdStart,
                    attempts,
                    initializationMs,
                    handlerDurationMs,
                    lastError
                };
            }
        }

        ++metrics_.failed;
        return {
            event.id,
            config_.name,
            InvocationState::Failed,
            sawColdStart,
            attempts,
            initializationMs,
            0.0,
            lastError
        };
    }

    const FunctionMetrics& metrics() const {
        return metrics_;
    }

    const FunctionConfiguration& configuration() const {
        return config_;
    }

    std::size_t environmentCount() const {
        return environments_.size();
    }

private:
    FunctionConfiguration config_;
    Handler handler_;
    std::vector<ExecutionEnvironment> environments_;
    FunctionMetrics metrics_;
    unsigned long nextEnvironmentId_ = 1;

    std::optional<std::size_t> acquire(double nowMs) {
        // Remove only expired idle environments. Active environments are
        // never recycled while a handler is using them.
        environments_.erase(
            std::remove_if(
                environments_.begin(),
                environments_.end(),
                [&](const ExecutionEnvironment& environment) {
                    return !environment.busy &&
                        nowMs - environment.lastUsedAtMs > config_.idleTtlMs;
                }
            ),
            environments_.end()
        );

        for (std::size_t index = 0; index < environments_.size(); ++index) {
            if (!environments_[index].busy) {
                environments_[index].busy = true;
                return index;
            }
        }

        if (static_cast<int>(environments_.size()) >= config_.maxConcurrency) {
            return std::nullopt;
        }

        std::ostringstream id;
        id << config_.name << "-env-" << nextEnvironmentId_++;

        environments_.push_back({
            id.str(),
            nowMs,
            nowMs,
            0,
            true
        });

        return environments_.size() - 1;
    }

    void release(std::size_t index, double nowMs) {
        if (index >= environments_.size()) {
            throw std::logic_error("Invalid environment lease.");
        }
        environments_[index].busy = false;
        environments_[index].lastUsedAtMs = nowMs;
    }
};

class EventDispatcher {
public:
    void registerFunction(
        const std::string& eventType,
        FunctionRuntime& runtime,
        double handlerDurationMs
    ) {
        if (eventType.empty()) {
            throw std::invalid_argument("Event type cannot be empty.");
        }
        if (routes_.count(eventType) != 0) {
            throw std::invalid_argument("Event route already exists.");
        }
        routes_[eventType] = {&runtime, handlerDurationMs};
    }

    InvocationRecord dispatch(
        const Event& event,
        bool simulateHandlerFailure = false
    ) {
        auto route = routes_.find(event.eventType);
        if (route == routes_.end()) {
            InvocationRecord record{
                event.id,
                "unrouted",
                InvocationState::Failed,
                false,
                0,
                0.0,
                0.0,
                "No function is subscribed to this event type"
            };
            deadLetters_.push_back(record);
            return record;
        }

        InvocationRecord result = route->second.runtime->invoke(
            event,
            route->second.handlerDurationMs,
            simulateHandlerFailure
        );

        if (
            result.state == InvocationState::Failed ||
            result.state == InvocationState::TimedOut ||
            result.state == InvocationState::Throttled
        ) {
            deadLetters_.push_back(result);
        }

        return result;
    }

    const std::vector<InvocationRecord>& deadLetters() const {
        return deadLetters_;
    }

private:
    struct Route {
        FunctionRuntime* runtime;
        double handlerDurationMs;
    };

    std::map<std::string, Route> routes_;
    std::vector<InvocationRecord> deadLetters_;
};

std::string orderHandler(const Event& event) {
    auto order = event.attributes.find("order_id");
    auto amount = event.attributes.find("amount");

    if (order == event.attributes.end() || order->second.empty()) {
        throw std::invalid_argument("order_id is required.");
    }
    if (amount == event.attributes.end()) {
        throw std::invalid_argument("amount is required.");
    }

    std::size_t parsed = 0;
    const double value = std::stod(amount->second, &parsed);

    if (parsed != amount->second.size() ||
        !std::isfinite(value) ||
        value <= 0.0) {
        throw std::invalid_argument("amount must be a positive finite number.");
    }

    std::ostringstream result;
    result << "Validated order " << order->second
           << " for " << std::fixed << std::setprecision(2) << value;
    return result.str();
}

std::string thumbnailHandler(const Event& event) {
    auto object = event.attributes.find("object_key");
    if (object == event.attributes.end()) {
        throw std::invalid_argument("object_key is required.");
    }
    if (object->second.rfind("uploads/", 0) != 0) {
        throw std::invalid_argument("Only uploads/ objects may be processed.");
    }

    return "Created thumbnail for " + object->second;
}

void printRecord(const InvocationRecord& record) {
    std::cout
        << "event=" << record.eventId
        << " function=" << record.functionName
        << " state=" << toString(record.state)
        << " cold_start=" << std::boolalpha << record.coldStart
        << " attempts=" << record.attempts
        << " initialization_ms=" << record.initializationMs
        << " duration_ms=" << record.handlerDurationMs
        << " message=\"" << record.message << "\"\n";
}

void printMetrics(const FunctionRuntime& runtime) {
    const auto& metrics = runtime.metrics();
    std::cout << "\nMetrics for " << runtime.configuration().name << "\n"
              << "accepted=" << metrics.accepted
              << " succeeded=" << metrics.succeeded
              << " failed=" << metrics.failed
              << " throttled=" << metrics.throttled
              << " timed_out=" << metrics.timedOut
              << " retries=" << metrics.retries
              << " cold_starts=" << metrics.coldStarts
              << " environments=" << runtime.environmentCount()
              << " billed_duration_ms=" << metrics.billedDurationMs
              << " average_success_ms=" << metrics.averageDuration()
              << "\n";
}

int main() {
    try {
        FunctionRuntime orderFunction(
            {
                "order-validator",
                256,
                1000.0,
                120.0,
                4,
                1,
                10000.0
            },
            orderHandler
        );

        FunctionRuntime imageFunction(
            {
                "image-thumbnailer",
                512,
                800.0,
                220.0,
                3,
                0,
                10000.0
            },
            thumbnailHandler
        );

        EventDispatcher dispatcher;
        dispatcher.registerFunction(
            "order.created",
            orderFunction,
            35.0
        );
        dispatcher.registerFunction(
            "storage.object.created",
            imageFunction,
            90.0
        );

        std::vector<Event> events = {
            {
                "EVT-1001",
                TriggerType::QueueMessage,
                "order.created",
                {{"order_id", "ORD-9001"}, {"amount", "799.95"}},
                1000.0
            },
            {
                "EVT-1002",
                TriggerType::QueueMessage,
                "order.created",
                {{"order_id", "ORD-9002"}, {"amount", "0"}},
                1001.0
            },
            {
                "EVT-1003",
                TriggerType::ObjectCreated,
                "storage.object.created",
                {{"object_key", "uploads/item-42.jpg"}},
                1002.0
            },
            {
                "EVT-1004",
                TriggerType::Scheduled,
                "unknown.event",
                {},
                1003.0
            }
        };

        std::cout << "Event-driven serverless order platform\n";
        for (const Event& event : events) {
            std::cout << "\nTrigger=" << toString(event.trigger)
                      << " type=" << event.eventType << "\n";
            printRecord(dispatcher.dispatch(event));
        }

        // A cold initialization can itself cause a timeout even when the
        // handler body would fit inside the configured timeout.
        FunctionRuntime shortTimeout(
            {
                "latency-sensitive-function",
                128,
                50.0,
                80.0,
                1,
                0,
                10000.0
            },
            orderHandler
        );

        Event timeoutEvent{
            "EVT-1005",
            TriggerType::HttpRequest,
            "order.created",
            {{"order_id", "ORD-9003"}, {"amount", "20.00"}},
            2000.0
        };

        std::cout << "\nCold-start timeout case\n";
        printRecord(shortTimeout.invoke(timeoutEvent, 10.0));

        printMetrics(orderFunction);
        printMetrics(imageFunction);
        printMetrics(shortTimeout);

        std::cout << "\nDead-letter records\n";
        for (const auto& record : dispatcher.deadLetters()) {
            printRecord(record);
        }

        std::cout
            << "\nProduction interpretation\n"
            << "The dispatcher models event routing; each runtime owns its "
               "execution environments and concurrency policy.\n"
            << "Real platforms schedule invocations concurrently. This "
               "deterministic case study models sequential leases and does "
               "not claim to be a concurrent load test.\n"
            << "For durable deduplication, use a transactional idempotency "
               "store shared across instances rather than process-local state.\n";
    } catch (const std::exception& exception) {
        std::cerr << "Fatal configuration error: "
                  << exception.what() << "\n";
        return 1;
    }

    return 0;
}
