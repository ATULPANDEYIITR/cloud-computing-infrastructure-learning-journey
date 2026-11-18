#include <algorithm>
#include <chrono>
#include <cmath>
#include <ctime>
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

using namespace std;

enum class State {
    Created,
    Running,
    Paused,
    Stopped,
    Exited,
    Removing
};

enum class RestartPolicy {
    No,
    Always,
    OnFailure,
    UnlessStopped
};

string toString(State state) {
    switch (state) {
        case State::Created: return "created";
        case State::Running: return "running";
        case State::Paused: return "paused";
        case State::Stopped: return "stopped";
        case State::Exited: return "exited";
        case State::Removing: return "removing";
    }
    return "unknown";
}

string toString(RestartPolicy policy) {
    switch (policy) {
        case RestartPolicy::No: return "no";
        case RestartPolicy::Always: return "always";
        case RestartPolicy::OnFailure: return "on-failure";
        case RestartPolicy::UnlessStopped: return "unless-stopped";
    }
    return "unknown";
}

string currentTimestamp() {
    const auto now = chrono::system_clock::now();
    const time_t time = chrono::system_clock::to_time_t(now);

    tm utc{};

#ifdef _WIN32
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif

    stringstream output;
    output << put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
    return output.str();
}

struct ContainerConfig {
    string image;
    vector<string> command;
    map<string, string> environment;
    map<string, string> labels;
    int memoryMB = 512;
    double cpuLimit = 1.0;
    RestartPolicy restartPolicy = RestartPolicy::No;

    void validate() const {
        if (image.empty()) {
            throw invalid_argument("Image cannot be empty.");
        }

        if (memoryMB < 16) {
            throw invalid_argument("Memory limit must be at least 16 MB.");
        }

        if (!isfinite(cpuLimit) || cpuLimit < 0.1 || cpuLimit > 64.0) {
            throw invalid_argument("Invalid CPU limit.");
        }

        for (const auto& [key, value] : environment) {
            if (key.empty()) {
                throw invalid_argument("Environment key cannot be empty.");
            }

            for (unsigned char ch : key) {
                if (!isalnum(ch) && ch != '_') {
                    throw invalid_argument("Invalid environment key.");
                }
            }

            if (value.find('\0') != string::npos) {
                throw invalid_argument("Invalid environment value.");
            }
        }
    }
};

struct LogEntry {
    string timestamp;
    string level;
    string message;
};

struct Container {
    string id;
    string name;
    ContainerConfig config;
    State state = State::Created;

    string createdAt;
    optional<string> startedAt;
    optional<string> finishedAt;
    optional<int> exitCode;

    int restartCount = 0;
    vector<LogEntry> logs;

    void addLog(const string& message, const string& level = "INFO") {
        logs.push_back({
            currentTimestamp(),
            level,
            message
        });
    }
};

class ContainerManager {
private:
    unordered_map<string, Container> containers;
    unordered_map<string, string> nameToId;
    size_t maximumContainers;

    static string generateId() {
        static unsigned long long counter = 1000;
        return "ctr-" + to_string(++counter);
    }

    Container& resolve(const string& identifier) {
        string id = identifier;

        auto nameIterator = nameToId.find(identifier);

        if (nameIterator != nameToId.end()) {
            id = nameIterator->second;
        }

        auto iterator = containers.find(id);

        if (iterator == containers.end()) {
            throw out_of_range("Container not found: " + identifier);
        }

        return iterator->second;
    }

    static void requireState(
        const Container& container,
        const set<State>& allowed
    ) {
        if (allowed.find(container.state) == allowed.end()) {
            throw logic_error(
                "Invalid lifecycle transition from " +
                toString(container.state)
            );
        }
    }

public:
    explicit ContainerManager(size_t capacity = 1000)
        : maximumContainers(capacity) {
        if (capacity == 0) {
            throw invalid_argument("Capacity must be positive.");
        }
    }

    string create(
        const string& name,
        const ContainerConfig& config
    ) {
        config.validate();

        if (name.empty() || nameToId.count(name)) {
            throw invalid_argument("Invalid or duplicate container name.");
        }

        if (containers.size() >= maximumContainers) {
            throw runtime_error("Container capacity exceeded.");
        }

        Container container;

        container.id = generateId();
        container.name = name;
        container.config = config;
        container.state = State::Created;
        container.createdAt = currentTimestamp();

        container.addLog("Created from image " + config.image);

        const string id = container.id;

        containers.emplace(id, move(container));
        nameToId.emplace(name, id);

        return id;
    }

    void start(const string& identifier) {
        Container& container = resolve(identifier);

        requireState(
            container,
            {State::Created, State::Stopped, State::Exited}
        );

        container.state = State::Running;
        container.startedAt = currentTimestamp();
        container.finishedAt.reset();
        container.exitCode.reset();

        container.addLog("Container started.");
    }

    void pause(const string& identifier) {
        Container& container = resolve(identifier);

        requireState(container, {State::Running});

        container.state = State::Paused;
        container.addLog("Container paused.");
    }

    void unpause(const string& identifier) {
        Container& container = resolve(identifier);

        requireState(container, {State::Paused});

        container.state = State::Running;
        container.addLog("Container resumed.");
    }

    void stop(
        const string& identifier,
        int exitCode = 0
    ) {
        Container& container = resolve(identifier);

        requireState(
            container,
            {State::Running, State::Paused}
        );

        if (exitCode < 0 || exitCode > 255) {
            throw invalid_argument("Invalid exit code.");
        }

        container.state = State::Stopped;
        container.exitCode = exitCode;
        container.finishedAt = currentTimestamp();

        container.addLog(
            "Container stopped with exit code " +
            to_string(exitCode)
        );
    }

    void simulateExit(
        const string& identifier,
        int exitCode
    ) {
        Container& container = resolve(identifier);

        requireState(container, {State::Running});

        if (exitCode < 0 || exitCode > 255) {
            throw invalid_argument("Invalid exit code.");
        }

        container.state = State::Exited;
        container.exitCode = exitCode;
        container.finishedAt = currentTimestamp();

        container.addLog(
            "Main process exited with code " + to_string(exitCode),
            exitCode == 0 ? "INFO" : "ERROR"
        );
    }

    void restart(const string& identifier) {
        Container& container = resolve(identifier);

        requireState(
            container,
            {
                State::Running,
                State::Paused,
                State::Stopped,
                State::Exited
            }
        );

        container.state = State::Stopped;
        container.addLog("Restart stopping phase completed.");

        container.state = State::Running;
        container.startedAt = currentTimestamp();
        container.finishedAt.reset();
        container.exitCode.reset();
        container.restartCount++;

        container.addLog("Container restarted.");
    }

    bool applyRestartPolicy(
        const string& identifier,
        bool manuallyStopped = false
    ) {
        Container& container = resolve(identifier);

        if (container.state != State::Exited) {
            return false;
        }

        const auto policy = container.config.restartPolicy;

        bool shouldRestart = false;

        switch (policy) {
            case RestartPolicy::No:
                break;

            case RestartPolicy::Always:
                shouldRestart = true;
                break;

            case RestartPolicy::UnlessStopped:
                shouldRestart = !manuallyStopped;
                break;

            case RestartPolicy::OnFailure:
                shouldRestart =
                    container.exitCode.has_value() &&
                    container.exitCode.value() != 0;
                break;
        }

        if (shouldRestart) {
            restart(identifier);
        }

        return shouldRestart;
    }

    string execute(
        const string& identifier,
        const vector<string>& command
    ) {
        Container& container = resolve(identifier);

        if (container.state != State::Running) {
            throw logic_error("Container must be running.");
        }

        if (command.empty()) {
            throw invalid_argument("Command cannot be empty.");
        }

        static const set<string> allowed = {
            "echo",
            "printenv",
            "hostname",
            "date"
        };

        if (!allowed.count(command[0])) {
            throw runtime_error("Command rejected by security policy.");
        }

        string output;

        if (command[0] == "echo") {
            for (size_t i = 1; i < command.size(); ++i) {
                if (i > 1) output += " ";
                output += command[i];
            }
        } else if (command[0] == "hostname") {
            output = container.name;
        } else if (command[0] == "date") {
            output = currentTimestamp();
        } else {
            const auto& env = container.config.environment;

            if (command.size() == 1) {
                for (const auto& [key, value] : env) {
                    output += key + "=" + value + "\n";
                }
            } else {
                auto iterator = env.find(command[1]);

                if (iterator != env.end()) {
                    output = iterator->second;
                }
            }
        }

        container.addLog("Command executed: " + command[0]);

        return output;
    }

    void inspect(const string& identifier) {
        const Container& container = resolve(identifier);

        cout << "\nContainer inspection\n";
        cout << "ID: " << container.id << "\n";
        cout << "Name: " << container.name << "\n";
        cout << "Image: " << container.config.image << "\n";
        cout << "State: " << toString(container.state) << "\n";
        cout << "Created: " << container.createdAt << "\n";
        cout << "Memory: " << container.config.memoryMB << " MB\n";
        cout << "CPU: " << container.config.cpuLimit << "\n";
        cout << "Restart policy: "
             << toString(container.config.restartPolicy) << "\n";
        cout << "Restart count: " << container.restartCount << "\n";

        cout << "Environment:\n";

        for (const auto& [key, value] : container.config.environment) {
            cout << "  " << key << "=" << value << "\n";
        }
    }

    vector<string> list(
        optional<State> filter = nullopt
    ) const {
        vector<string> result;

        for (const auto& [id, container] : containers) {
            if (!filter || container.state == filter.value()) {
                result.push_back(
                    container.name + " [" +
                    id + "] " + toString(container.state)
                );
            }
        }

        sort(result.begin(), result.end());
        return result;
    }

    void showLogs(
        const string& identifier,
        size_t tail = 0
    ) const {
        const string id = nameToId.count(identifier)
            ? nameToId.at(identifier)
            : identifier;

        auto iterator = containers.find(id);

        if (iterator == containers.end()) {
            throw out_of_range("Container not found.");
        }

        const auto& logs = iterator->second.logs;

        const size_t start = tail == 0 || tail >= logs.size()
            ? 0
            : logs.size() - tail;

        for (size_t i = start; i < logs.size(); ++i) {
            const auto& entry = logs[i];

            cout << entry.timestamp << " "
                 << entry.level << " "
                 << entry.message << "\n";
        }
    }

    void remove(
        const string& identifier,
        bool force = false
    ) {
        Container& container = resolve(identifier);

        if (
            (container.state == State::Running ||
             container.state == State::Paused) &&
            !force
        ) {
            throw logic_error(
                "Stop the container before removal or use force."
            );
        }

        container.state = State::Removing;
        container.addLog("Container removed.");

        nameToId.erase(container.name);
        containers.erase(container.id);
    }
};

int main() {
    try {
        ContainerManager manager(100);

        ContainerConfig config;

        config.image = "nginx:1.27-alpine";
        config.command = {"nginx", "-g", "daemon off;"};

        config.environment = {
            {"APP_ENV", "production"},
            {"PORT", "8080"},
            {"LOG_LEVEL", "INFO"}
        };

        config.labels = {
            {"team", "platform"},
            {"service", "web"}
        };

        config.memoryMB = 1024;
        config.cpuLimit = 2.0;
        config.restartPolicy = RestartPolicy::OnFailure;

        cout << "1. Creating container\n";

        const string id = manager.create("web-server", config);

        cout << "Created: " << id << "\n";

        cout << "\n2. Starting container\n";
        manager.start(id);
        manager.inspect(id);

        cout << "\n3. Executing commands\n";

        cout << "APP_ENV: "
             << manager.execute(id, {"printenv", "APP_ENV"})
             << "\n";

        cout << "Hostname: "
             << manager.execute(id, {"hostname"})
             << "\n";

        cout << "Output: "
             << manager.execute(id, {"echo", "Server ready"})
             << "\n";

        cout << "\n4. Pausing and resuming\n";
        manager.pause(id);
        manager.unpause(id);

        cout << "\n5. Container logs\n";
        manager.showLogs(id, 5);

        cout << "\n6. Simulating process failure\n";
        manager.simulateExit(id, 1);

        cout << "Restart policy applied: "
             << boolalpha
             << manager.applyRestartPolicy(id)
             << "\n";

        manager.inspect(id);

        cout << "\n7. Container inventory\n";

        for (const auto& item : manager.list(State::Running)) {
            cout << item << "\n";
        }

        cout << "\n8. Security validation\n";

        try {
            manager.execute(id, {"rm", "-rf", "/"});
        } catch (const exception& error) {
            cout << "Command rejected: " << error.what() << "\n";
        }

        cout << "\n9. Stop and remove\n";
        manager.stop(id);
        manager.remove(id);

        cout << "Remaining containers: "
             << manager.list().size() << "\n";

        if (!manager.list().empty()) {
            throw runtime_error("Inventory assertion failed.");
        }

        cout << "\nAll checks completed successfully.\n";
    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << "\n";
        return 1;
    }

    return 0;
}
