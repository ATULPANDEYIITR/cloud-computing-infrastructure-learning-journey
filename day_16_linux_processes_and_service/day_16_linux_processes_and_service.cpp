```cpp
#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#ifdef __linux__
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

/*
    Linux Processes and Services
    =============================

    Industry-style C++ case study: a lightweight service supervisor.

    The program demonstrates:

      - Process identity
      - fork()
      - exec()
      - waitpid()
      - exit status interpretation
      - SIGTERM and SIGKILL
      - /proc inspection
      - service health modeling
      - restart policy
      - timeout supervision
      - configuration validation
      - structured monitoring records
      - resource observations
      - separation of monitoring from process control

    Compile:

      g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
          linux_processes_services.cpp -o linux_processes_services

    Run:

      ./linux_processes_services

    The program is intentionally self-contained and does not modify systemd
    services. Real system service administration should normally be delegated
    to systemd rather than implemented as an ad-hoc supervisor.
*/

namespace fs = std::filesystem;

struct ProcessInfo {
    int pid{};
    int parent_pid{};
    char state{'?'};
    long memory_kb{};
    int threads{};
    std::string name;
};

struct ServiceHealth {
    bool healthy{false};
    std::vector<std::string> reasons;
};

struct ServicePolicy {
    int max_restarts{5};
    long memory_limit_kb{512000};
    std::chrono::seconds shutdown_timeout{3};
};

static std::atomic<bool> worker_running{true};

void print_heading(const std::string& title) {
    std::cout << "\n" << std::string(78, '=') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '=') << "\n";
}

void print_subheading(const std::string& title) {
    std::cout << "\n" << std::string(78, '-') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '-') << "\n";
}

bool is_linux() {
#ifdef __linux__
    return true;
#else
    return false;
#endif
}

std::optional<std::string> read_text_file(const fs::path& path) {
    std::ifstream input(path);

    if (!input) {
        return std::nullopt;
    }

    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

std::map<std::string, std::string> parse_proc_status(int pid) {
    std::map<std::string, std::string> values;

#ifdef __linux__
    const auto path = fs::path("/proc") / std::to_string(pid) / "status";
    auto content = read_text_file(path);

    if (!content) {
        return values;
    }

    std::istringstream stream(*content);
    std::string line;

    while (std::getline(stream, line)) {
        const auto separator = line.find(':');

        if (separator == std::string::npos) {
            continue;
        }

        std::string key = line.substr(0, separator);
        std::string value = line.substr(separator + 1);

        while (!value.empty() && std::isspace(
            static_cast<unsigned char>(value.front()))) {
            value.erase(value.begin());
        }

        values[key] = value;
    }
#else
    (void)pid;
#endif

    return values;
}

long parse_first_number(const std::string& value) {
    std::istringstream stream(value);
    long number = 0;
    stream >> number;
    return number;
}

ProcessInfo read_process_info(int pid) {
    ProcessInfo result;
    result.pid = pid;

    const auto values = parse_proc_status(pid);

    if (values.empty()) {
        return result;
    }

    result.parent_pid = parse_first_number(values.count("PPid")
        ? values.at("PPid") : "0");

    result.memory_kb = parse_first_number(values.count("VmRSS")
        ? values.at("VmRSS") : "0");

    result.threads = static_cast<int>(parse_first_number(
        values.count("Threads") ? values.at("Threads") : "0"
    ));

    if (values.count("Name")) {
        result.name = values.at("Name");
    }

    if (values.count("State") && !values.at("State").empty()) {
        result.state = values.at("State").front();
    }

    return result;
}

void process_identity() {
    print_heading("1. Process identity");

#ifdef __linux__
    std::cout << "PID  : " << getpid() << "\n";
    std::cout << "PPID : " << getppid() << "\n";
    std::cout << "PGID : " << getpgrp() << "\n";
    std::cout << "UID  : " << getuid() << "\n";
    std::cout << "GID  : " << getgid() << "\n";
#else
    std::cout << "This case study requires Linux-specific APIs.\n";
#endif
}

void process_state_explanation() {
    print_heading("2. Linux process states");

    std::cout
        << "R = running or runnable\n"
        << "S = interruptible sleep\n"
        << "D = uninterruptible sleep, often I/O related\n"
        << "T = stopped\n"
        << "Z = zombie\n"
        << "I = idle kernel-thread state in applicable contexts\n";

    std::cout
        << "\nA zombie has completed execution but still has a process-table "
        << "entry because its parent has not collected its exit status.\n";
}

void proc_case_study() {
    print_heading("3. Inspecting the current process through /proc");

#ifdef __linux__
    const int pid = static_cast<int>(getpid());
    const auto values = parse_proc_status(pid);

    for (const std::string& key : {
        "Name", "State", "Pid", "PPid",
        "Uid", "Gid", "Threads", "VmSize", "VmRSS"
    }) {
        auto iterator = values.find(key);

        if (iterator != values.end()) {
            std::cout << std::left << std::setw(12)
                      << key << ": " << iterator->second << "\n";
        }
    }
#else
    std::cout << "/proc is a Linux-specific interface.\n";
#endif
}

#ifdef __linux__

void child_signal_handler(int signal_number) {
    if (signal_number == SIGTERM) {
        worker_running = false;
    }
}

void run_child_worker() {
    /*
        The child installs a SIGTERM handler.

        This models graceful shutdown:
          1. Stop accepting new work.
          2. Leave the main loop.
          3. Release resources.
          4. Exit normally.

        SIGKILL cannot provide this application-level behavior.
    */
    std::signal(SIGTERM, child_signal_handler);

    std::cout << "Child worker started. PID=" << getpid() << std::endl;

    while (worker_running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    std::cout << "Child worker performed cleanup." << std::endl;
    _exit(0);
}

pid_t start_worker() {
    const pid_t child = fork();

    if (child < 0) {
        throw std::runtime_error(
            std::string("fork failed: ") + std::strerror(errno)
        );
    }

    if (child == 0) {
        run_child_worker();
    }

    return child;
}

bool wait_for_exit(pid_t pid, int timeout_seconds, int& status) {
    const auto deadline =
        std::chrono::steady_clock::now() +
        std::chrono::seconds(timeout_seconds);

    while (std::chrono::steady_clock::now() < deadline) {
        const pid_t result = waitpid(pid, &status, WNOHANG);

        if (result == pid) {
            return true;
        }

        if (result == -1) {
            return false;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    return false;
}

void explain_wait_status(int status) {
    if (WIFEXITED(status)) {
        std::cout
            << "Child exited normally with code "
            << WEXITSTATUS(status) << "\n";
    } else if (WIFSIGNALED(status)) {
        std::cout
            << "Child was terminated by signal "
            << WTERMSIG(status) << "\n";
    } else if (WIFSTOPPED(status)) {
        std::cout
            << "Child was stopped by signal "
            << WSTOPSIG(status) << "\n";
    }
}

bool terminate_worker(pid_t pid, const ServicePolicy& policy) {
    std::cout << "Sending SIGTERM to PID " << pid << "\n";

    if (kill(pid, SIGTERM) == -1) {
        if (errno == ESRCH) {
            return true;
        }

        std::cerr
            << "SIGTERM failed: "
            << std::strerror(errno) << "\n";
        return false;
    }

    int status = 0;

    if (wait_for_exit(
        pid,
        static_cast<int>(policy.shutdown_timeout.count()),
        status
    )) {
        explain_wait_status(status);
        return true;
    }

    /*
        A graceful shutdown exceeded its deadline. SIGKILL is used only as a
        final escalation because the target cannot handle SIGKILL itself.
    */
    std::cout << "Graceful shutdown timed out. Sending SIGKILL.\n";

    if (kill(pid, SIGKILL) == -1 && errno != ESRCH) {
        std::cerr
            << "SIGKILL failed: "
            << std::strerror(errno) << "\n";
        return false;
    }

    waitpid(pid, &status, 0);
    explain_wait_status(status);

    return true;
}

void process_creation_case_study() {
    print_heading("4. Process creation and graceful shutdown");

    const pid_t worker = start_worker();

    std::cout << "Parent created worker PID=" << worker << "\n";

    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    const auto information = read_process_info(worker);

    std::cout
        << "Observed child PPID="
        << information.parent_pid
        << " state="
        << information.state
        << " RSS="
        << information.memory_kb
        << " KiB\n";

    ServicePolicy policy;
    terminate_worker(worker, policy);
}

void demonstrate_failed_exec() {
    print_heading("5. Handling an execution failure");

    const pid_t child = fork();

    if (child < 0) {
        std::cerr << "fork failed\n";
        return;
    }

    if (child == 0) {
        /*
            execl replaces the child process image.

            If it succeeds, execution never returns to this C++ code.
            If it fails, _exit() prevents accidental execution of parent-side
            cleanup logic inherited through fork().
        */
        execl(
            "/definitely/not/a/real/program",
            "missing-program",
            static_cast<char*>(nullptr)
        );

        std::cerr
            << "exec failed: "
            << std::strerror(errno)
            << "\n";

        _exit(127);
    }

    int status = 0;
    waitpid(child, &status, 0);

    explain_wait_status(status);
}

std::vector<ProcessInfo> collect_processes() {
    std::vector<ProcessInfo> processes;

#ifdef __linux__
    for (const auto& entry : fs::directory_iterator("/proc")) {
        const std::string filename = entry.path().filename().string();

        if (!std::all_of(
            filename.begin(),
            filename.end(),
            [](unsigned char character) {
                return std::isdigit(character);
            }
        )) {
            continue;
        }

        try {
            const int pid = std::stoi(filename);
            const ProcessInfo information = read_process_info(pid);

            if (!information.name.empty()) {
                processes.push_back(information);
            }
        } catch (...) {
            /*
                Processes can disappear while /proc is being scanned.
                This is a normal race condition rather than necessarily
                an application failure.
            */
        }
    }
#endif

    std::sort(
        processes.begin(),
        processes.end(),
        [](const ProcessInfo& left, const ProcessInfo& right) {
            return left.memory_kb > right.memory_kb;
        }
    );

    return processes;
}

void process_inventory_case_study() {
    print_heading("6. Process inventory");

    const auto processes = collect_processes();

    std::cout
        << std::right
        << std::setw(8) << "PID"
        << std::setw(8) << "PPID"
        << std::setw(8) << "STATE"
        << std::setw(12) << "RSS KiB"
        << std::setw(10) << "THREADS"
        << "  NAME\n";

    std::cout << std::string(70, '-') << "\n";

    const std::size_t limit =
        std::min<std::size_t>(processes.size(), 20);

    for (std::size_t index = 0; index < limit; ++index) {
        const auto& process = processes[index];

        std::cout
            << std::setw(8) << process.pid
            << std::setw(8) << process.parent_pid
            << std::setw(8) << process.state
            << std::setw(12) << process.memory_kb
            << std::setw(10) << process.threads
            << "  " << process.name
            << "\n";
    }
}

#else

void process_creation_case_study() {
    print_heading("4. Process creation and graceful shutdown");
    std::cout << "fork(), waitpid() and signals require Linux/POSIX APIs.\n";
}

void demonstrate_failed_exec() {
    print_heading("5. Handling an execution failure");
    std::cout << "exec() demonstration requires Linux/POSIX APIs.\n";
}

void process_inventory_case_study() {
    print_heading("6. Process inventory");
    std::cout << "/proc is unavailable on this operating system.\n";
}

#endif

ServiceHealth evaluate_health(
    const std::string& active_state,
    const std::string& sub_state,
    int restart_count,
    long memory_kb,
    const ServicePolicy& policy
) {
    ServiceHealth health;
    health.healthy = true;

    if (active_state != "active") {
        health.healthy = false;
        health.reasons.push_back(
            "service is not active: " + active_state
        );
    }

    if (
        sub_state != "running" &&
        sub_state != "listening" &&
        sub_state != "exited"
    ) {
        health.healthy = false;
        health.reasons.push_back(
            "unexpected service substate: " + sub_state
        );
    }

    if (restart_count > policy.max_restarts) {
        health.healthy = false;
        health.reasons.push_back(
            "restart count exceeds configured threshold"
        );
    }

    if (memory_kb > policy.memory_limit_kb) {
        health.healthy = false;
        health.reasons.push_back(
            "memory usage exceeds configured limit"
        );
    }

    return health;
}

void health_model_case_study() {
    print_heading("7. Service health model");

    ServicePolicy policy;

    struct TestCase {
        std::string active;
        std::string sub;
        int restarts;
        long memory;
    };

    const std::vector<TestCase> cases = {
        {"active", "running", 0, 100000},
        {"failed", "failed", 8, 100000},
        {"active", "running", 1, 700000},
    };

    for (std::size_t index = 0; index < cases.size(); ++index) {
        const auto& test = cases[index];

        const ServiceHealth result = evaluate_health(
            test.active,
            test.sub,
            test.restarts,
            test.memory,
            policy
        );

        std::cout
            << "Case "
            << index + 1
            << ": healthy="
            << std::boolalpha
            << result.healthy
            << "\n";

        for (const auto& reason : result.reasons) {
            std::cout << "  - " << reason << "\n";
        }
    }
}

bool validate_service_name(const std::string& name) {
    if (name.empty() || name.size() > 255) {
        return false;
    }

    if (
        name.find('/') != std::string::npos ||
        name.find('\\') != std::string::npos ||
        name.find("..") != std::string::npos ||
        name.find(' ') != std::string::npos
    ) {
        return false;
    }

    for (const unsigned char character : name) {
        const bool valid =
            std::isalnum(character) ||
            character == '.' ||
            character == '_' ||
            character == '@' ||
            character == '-';

        if (!valid) {
            return false;
        }
    }

    return true;
}

void validation_case_study() {
    print_heading("8. Administrative input validation");

    const std::vector<std::string> samples = {
        "ssh.service",
        "cron.service",
        "worker@1.service",
        "",
        "../../etc/passwd",
        "service name",
    };

    for (const auto& sample : samples) {
        std::cout
            << std::setw(28)
            << std::left
            << (sample.empty() ? "<empty>" : sample)
            << " valid="
            << std::boolalpha
            << validate_service_name(sample)
            << "\n";
    }

    std::cout
        << "\nValidation and authorization are different controls. "
        << "A valid unit name does not mean the caller has permission "
        << "to control that unit.\n";
}

void show_systemd_commands() {
    print_heading("9. systemd and systemctl operational model");

    std::cout
        << "Common observation commands:\n"
        << "  systemctl status SERVICE\n"
        << "  systemctl is-active SERVICE\n"
        << "  systemctl is-enabled SERVICE\n"
        << "  systemctl show SERVICE\n"
        << "  systemctl list-units --type=service\n"
        << "  systemctl list-dependencies SERVICE\n"
        << "\nLifecycle commands:\n"
        << "  systemctl start SERVICE\n"
        << "  systemctl stop SERVICE\n"
        << "  systemctl restart SERVICE\n"
        << "  systemctl reload SERVICE\n"
        << "\nBoot integration:\n"
        << "  systemctl enable SERVICE\n"
        << "  systemctl disable SERVICE\n"
        << "\nLogs:\n"
        << "  journalctl -u SERVICE\n"
        << "  journalctl -u SERVICE -n 100\n"
        << "  journalctl -u SERVICE -f\n";

    std::cout
        << "\nThis case study deliberately does not execute privileged "
        << "systemctl modification commands.\n";
}

void show_unit_file() {
    print_heading("10. Example systemd service unit");

    const std::string unit =
        "[Unit]\n"
        "Description=Example Application Service\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        "User=example\n"
        "Group=example\n"
        "ExecStart=/opt/example/bin/server\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n";

    std::cout << unit;

    std::cout
        << "\nThe unit expresses desired service behavior rather than merely "
        << "launching a process manually.\n";
}

void security_case_study() {
    print_heading("11. Security design");

    const std::vector<std::string> controls = {
        "Run services under dedicated accounts where practical.",
        "Use least privilege for files and devices.",
        "Avoid shell interpretation for untrusted arguments.",
        "Protect unit files from unauthorized modification.",
        "Do not expose administrative control to untrusted users.",
        "Use systemd sandboxing controls where compatible.",
        "Keep secrets out of command-line arguments.",
        "Audit process creation and privilege changes.",
        "Limit network exposure to required interfaces and ports.",
        "Treat logs as potentially sensitive information.",
    };

    for (std::size_t index = 0; index < controls.size(); ++index) {
        std::cout
            << std::setw(2)
            << index + 1
            << ". "
            << controls[index]
            << "\n";
    }
}

void performance_case_study() {
    print_heading("12. Performance considerations");

    std::cout
        << "A monitoring program has overhead of its own.\n\n"
        << "Repeatedly scanning /proc can consume CPU and filesystem work.\n"
        << "Starting external commands for every sample can be more expensive "
        << "than reading structured kernel interfaces directly.\n"
        << "Very short sampling intervals increase overhead.\n"
        << "Large process inventories should avoid unnecessary allocations "
        << "and repeated parsing.\n\n"
        << "For a small local diagnostic tool, simplicity may matter more "
        << "than micro-optimization. For high-frequency monitoring, the "
        << "collection strategy becomes a significant architectural decision.\n";
}

void testing_case_study() {
    print_heading("13. Assertions and deterministic tests");

    if (!validate_service_name("example.service")) {
        throw std::runtime_error(
            "Valid service name was rejected."
        );
    }

    if (validate_service_name("../bad.service")) {
        throw std::runtime_error(
            "Unsafe service name was accepted."
        );
    }

    ServicePolicy policy;

    const auto healthy = evaluate_health(
        "active",
        "running",
        0,
        100,
        policy
    );

    if (!healthy.healthy) {
        throw std::runtime_error(
            "Healthy test case was rejected."
        );
    }

    const auto unhealthy = evaluate_health(
        "failed",
        "failed",
        0,
        100,
        policy
    );

    if (unhealthy.healthy) {
        throw std::runtime_error(
            "Failed service was reported healthy."
        );
    }

    std::cout << "All deterministic tests passed.\n";
}

void troubleshooting_case_study() {
    print_heading("14. Operational troubleshooting workflow");

    std::cout
        << "1. Identify the service and its current state.\n"
        << "2. Inspect the unit properties with systemctl show.\n"
        << "3. Read recent journal entries.\n"
        << "4. Identify the main process PID.\n"
        << "5. Inspect CPU, memory and process state.\n"
        << "6. Check dependencies and startup ordering.\n"
        << "7. Validate configuration and filesystem permissions.\n"
        << "8. Check listening sockets when networking is involved.\n"
        << "9. Make one controlled change.\n"
        << "10. Observe whether the change altered the failure mode.\n";

    std::cout
        << "\nTypical distinctions:\n"
        << "  failed service -> startup or runtime failure\n"
        << "  active service -> systemd considers the unit active\n"
        << "  listening problem -> inspect sockets and bind addresses\n"
        << "  restart loop -> inspect application exit behavior and policy\n"
        << "  zombie -> investigate parent child-reaping behavior\n";
}

int main() {
    try {
        std::cout
            << "Linux Processes and Services - C++ Case Study\n"
            << "================================================\n";

        process_identity();
        process_state_explanation();
        proc_case_study();
        process_creation_case_study();
        demonstrate_failed_exec();
        process_inventory_case_study();
        health_model_case_study();
        validation_case_study();
        show_systemd_commands();
        show_unit_file();
        security_case_study();
        performance_case_study();
        testing_case_study();
        troubleshooting_case_study();

        print_heading("15. Case study completed");

        std::cout
            << "The program demonstrated the relationship between Linux "
            << "process primitives and higher-level service supervision.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << "\n";

        return 1;
    }
}
```
