# Linux processes and services

## Introduction

Linux treats running programs as processes. A process is an active execution context created from a program, with its own process identifier, parent relationship, memory state, file descriptors, credentials, scheduling information and resource limits.

Services are long-running system or application capabilities. A daemon is a background process that commonly provides such a capability. Modern Linux systems frequently use systemd to manage services, establish dependencies, supervise processes, integrate services with the boot process and provide access to service logs.

This study implements the subject in three languages:

- Python provides a high-level but practical interface for process creation, signals, `/proc` inspection, command execution, monitoring and service-state analysis.
- JavaScript running on Node.js demonstrates asynchronous process management, event-driven supervision and operating-system command integration.
- C++ provides a lower-level case study using Linux/POSIX process primitives such as `fork()`, `exec()`, `waitpid()` and signals, followed by a structured service-supervision model.

The principal Linux tools represented in the implementations are `ps`, `top`, `systemctl` and `journalctl`.

## Fundamental concepts

### Program versus process

A program is a stored executable or collection of executable instructions. It does not necessarily consume CPU merely because it exists on disk.

A process is an executing instance of a program. The operating system creates and manages the process's execution state.

Multiple processes can originate from the same program. They can have different arguments, environment variables, resource usage and lifetimes.

For example, starting a command-line editor twice creates two process instances even though both instances originate from the same executable.

### Process identifier

Every normal Linux process has a process ID, commonly called a PID.

A PID identifies a process within the relevant PID namespace. It is used by administrative tools and system calls when inspecting or controlling processes.

The Python implementation obtains its PID with `os.getpid()`. Node.js exposes it as `process.pid`. C++ obtains it through `getpid()`.

### Parent process ID

Processes normally have a parent-child relationship.

The parent process ID is called the PPID. Python exposes it through `os.getppid()`, Node.js through `process.ppid`, and C++ through `getppid()` on Linux.

Parent-child relationships are important because the parent can create children, wait for them and receive notification when their state changes.

### Process groups

A process group is a collection of processes that can be managed as a group for certain signal and job-control operations.

This becomes particularly important for shells, terminal jobs, process supervisors and applications that create multiple cooperating workers.

The Python implementation displays the current process group ID and session ID.

### Sessions

A session contains one or more process groups. Terminal-oriented applications use sessions and process groups to organize job control.

The distinction between process, process group and session becomes important when controlling process trees rather than a single PID.

## Linux process states

Linux reports process states through interfaces such as `/proc` and tools such as `ps`.

Common state codes include:

| State | Meaning |
|---|---|
| `R` | Running or runnable |
| `S` | Interruptible sleep |
| `D` | Uninterruptible sleep, commonly associated with kernel-level I/O waits |
| `T` | Stopped |
| `Z` | Zombie |
| `I` | Idle kernel-thread state in applicable contexts |

A state code may be accompanied by additional flags in `ps` output.

### Running

A process in the running or runnable state is either executing on a CPU or waiting in the scheduler's runnable queue.

A process being runnable does not mean that it permanently occupies a CPU.

### Sleeping

Sleeping processes are waiting for an event. Interruptible sleep is common for programs waiting for input, timers or other events.

Sleeping is not automatically a problem. Most useful applications spend substantial periods waiting for work.

### Uninterruptible sleep

The `D` state is commonly associated with waiting inside the kernel for I/O or another operation that cannot safely be interrupted at that point.

Persistent large populations of processes in this state can indicate an underlying storage, network filesystem or kernel-level resource problem, depending on the workload.

### Stopped

A stopped process is not currently executing. Job control or signals such as `SIGSTOP` can stop a process.

`SIGCONT` can resume an appropriately stopped process.

### Zombie

A zombie has finished executing but still has a process-table entry because its parent has not collected the child's termination status.

The appropriate response to zombies is normally to investigate the parent process's child-reaping behavior rather than attempting to treat the zombie itself as an ordinary running process.

## Process creation

Linux process creation can be understood through two major concepts represented in the C++ implementation.

`fork()` creates a child process.

After `fork()`:

- the parent receives the child's PID
- the child receives a return value of zero
- both initially continue from the point at which `fork()` returned
- the child has a process relationship with its parent
- the two processes subsequently execute independently

The C++ case study uses `fork()` to create a worker process.

Python and Node.js generally use higher-level process APIs rather than directly exposing `fork()` as the normal cross-purpose mechanism for launching an arbitrary executable.

## Program replacement with exec

The `exec` family replaces the current process image with another program.

The C++ implementation uses `execl()` to demonstrate this distinction.

If `execl()` succeeds, the old program image is replaced and execution does not return to the calling code.

If it fails, the call returns with an error. The example uses `_exit(127)` in the child after the failed `exec()`.

The distinction between `fork()` and `exec()` is fundamental:

- `fork()` creates a new process.
- `exec()` replaces the program being executed inside an existing process.

A common Unix pattern is therefore:

1. parent calls `fork()`
2. child calls `exec()`
3. parent calls `waitpid()` or otherwise supervises the child

## Waiting for children

A parent can collect a child's termination status through a wait operation.

The C++ case study uses `waitpid()`.

This is important for avoiding zombies. A child that exits does not necessarily disappear from all process-management structures until its parent collects its status.

Python's `subprocess.Popen` and Node's `ChildProcess` abstraction provide higher-level mechanisms for observing child completion.

## Process inspection with ps

`ps` provides a process snapshot.

Common forms include:

`ps`

Shows processes associated with the current terminal context.

`ps aux`

Provides a widely used BSD-style process listing containing user, CPU, memory and command information.

`ps -ef`

Provides a System V-style full process listing.

A customized command such as:

`ps -eo pid,ppid,user,stat,%cpu,%mem,etime,comm`

selects explicit fields.

Important fields include:

| Field | Meaning |
|---|---|
| PID | Process ID |
| PPID | Parent process ID |
| USER | Account associated with the process |
| STAT | Process state and flags |
| `%CPU` | CPU utilization measurement |
| `%MEM` | Memory utilization measurement |
| TTY | Controlling terminal |
| TIME | Accumulated CPU time |
| COMMAND | Process command |

`ps` is useful for point-in-time inspection. It is not inherently a historical monitoring system.

## Real-time monitoring with top

`top` provides an interactive process-monitoring interface.

Important information includes:

- system load
- CPU utilization
- memory usage
- process CPU consumption
- process memory consumption
- process state
- process priority
- process identifiers
- accumulated CPU time

The Python and JavaScript implementations invoke `top` in batch mode so that a snapshot can be displayed programmatically.

Normal interactive usage is different from batch mode.

A critical operational distinction is that CPU and memory values need context. A process using significant CPU may be performing expected computation, while a process using little CPU can still be responsible for an availability failure.

## `/proc`

Linux exposes many kernel and process attributes through the proc filesystem, normally mounted at `/proc`.

A process directory commonly has the form:

`/proc/<PID>/`

Important entries include:

- `status`
- `cmdline`
- `environ`
- `fd`
- `stat`
- `limits`
- `maps`
- `io`

The implementations primarily use `/proc/<PID>/status`.

The status information can include:

- process name
- state
- PID
- PPID
- user IDs
- group IDs
- number of threads
- virtual memory size
- resident memory size

### Why `/proc` matters

Parsing a human-oriented command such as `ps` can be fragile when an application needs a specific structured value.

Reading a structured kernel interface can be more appropriate for a monitoring application.

This does not mean `/proc` should always replace standard tools. `ps` is highly useful for humans, while `/proc` is valuable for programs requiring direct system information.

## Signals

A signal is an asynchronous notification delivered to a process or process group.

Important signals include:

| Signal | Typical meaning |
|---|---|
| `SIGTERM` | Request termination |
| `SIGKILL` | Force termination |
| `SIGINT` | Interrupt |
| `SIGHUP` | Hangup; frequently used by applications for reload semantics |
| `SIGSTOP` | Stop execution |
| `SIGCONT` | Continue execution |
| `SIGCHLD` | Child process state changed |

Signal numbers are platform-dependent details and should generally be represented by symbolic names in programs.

## SIGTERM and graceful shutdown

`SIGTERM` is normally the preferred signal for requesting controlled termination.

An application can handle it and perform operations such as:

1. stop accepting new work
2. finish safe in-flight work
3. close files
4. flush buffers
5. close network connections
6. release resources
7. exit

The Python example registers a `SIGTERM` handler.

The C++ worker also installs a `SIGTERM` handler.

The Node.js implementation uses `process.on("SIGTERM", ...)`.

## SIGKILL

`SIGKILL` is fundamentally different from `SIGTERM`.

The target application cannot catch or handle `SIGKILL`. The kernel terminates the process.

Consequently, application-level cleanup cannot be performed after the process receives `SIGKILL`.

A sensible supervision sequence is therefore commonly:

1. request graceful termination with `SIGTERM`
2. wait for a bounded period
3. escalate to `SIGKILL` if the process remains alive

The Python and C++ implementations explicitly demonstrate this escalation pattern.

## Exit status

A process can terminate normally with an exit code or because it was terminated by a signal.

The C++ implementation uses:

- `WIFEXITED`
- `WEXITSTATUS`
- `WIFSIGNALED`
- `WTERMSIG`
- `WIFSTOPPED`
- `WSTOPSIG`

These macros interpret the status returned by `waitpid()`.

A non-zero exit code is application-level information. It should not automatically be interpreted as a kernel failure.

## Services

A service is a long-running capability provided by a system or application.

Examples include:

- SSH service
- web server
- database server
- DNS service
- logging service
- scheduler
- message broker
- application backend

A service can consist of one process or several cooperating processes.

## Daemons

A daemon is a background process designed to provide a service.

The historical Unix daemon model is broader than merely "a program running in the background." Daemons commonly operate independently of interactive terminal sessions and continue providing functionality over time.

Modern service managers can control daemon processes without requiring applications to implement all traditional daemonization behavior themselves.

## systemd

systemd is a system and service manager used by many Linux distributions.

Its responsibilities can include:

- system boot coordination
- service activation
- dependency management
- process supervision
- resource management
- service lifecycle control
- logging integration
- socket and timer activation
- target management

When systemd is used as PID 1, it becomes a central part of the userspace initialization and service-management architecture.

## systemctl

`systemctl` is a command-line interface for interacting with systemd.

Common inspection commands include:

`systemctl status SERVICE`

Shows detailed service status.

`systemctl is-active SERVICE`

Checks whether the service is active.

`systemctl is-enabled SERVICE`

Checks whether a unit is enabled for startup according to its unit configuration.

`systemctl show SERVICE`

Displays structured unit properties.

`systemctl list-units --type=service`

Lists loaded service units.

`systemctl list-dependencies SERVICE`

Displays dependency relationships.

Lifecycle operations include:

`systemctl start SERVICE`

`systemctl stop SERVICE`

`systemctl restart SERVICE`

`systemctl reload SERVICE`

Boot integration includes:

`systemctl enable SERVICE`

`systemctl disable SERVICE`

The Python, JavaScript and C++ implementations focus on observation and modeling rather than executing privileged service modifications.

## systemd unit files

A simplified service unit has three major sections.

### [Unit]

This section describes the unit and relationships with other units.

Examples include:

- `Description`
- `After`
- `Before`
- `Wants`
- `Requires`

Ordering and dependency are different concepts. `After=` establishes ordering, while directives such as `Requires=` and `Wants=` describe dependency relationships.

### [Service]

This section describes how the service process is executed.

Important directives include:

- `Type`
- `ExecStart`
- `ExecStop`
- `User`
- `Group`
- `WorkingDirectory`
- `Environment`
- `EnvironmentFile`
- `Restart`
- `RestartSec`
- timeout directives

The case studies use a conceptual `Type=simple` service.

### [Install]

This section describes relationships used when a unit is enabled.

A common example is:

`WantedBy=multi-user.target`

Enabling a unit establishes the appropriate relationship so that the service can participate in the corresponding boot target.

## Service states

systemd distinguishes multiple aspects of unit state.

Important concepts include:

- load state
- active state
- substate
- unit-file state
- main process PID

Examples of active-state values include:

- `active`
- `inactive`
- `failed`
- `activating`
- `deactivating`

A service being `active` does not necessarily mean that an application-level request will succeed. A process can remain alive while an internal component is broken.

This is why service monitoring should distinguish process state from application health.

## Restart policies

A service manager can restart a process after failure.

A policy can include:

- whether to restart
- which failures should trigger restart
- how long to wait
- how often failures occur
- when repeated failures should be treated as abnormal

The health models in all three implementations use a restart-count threshold as an educational example.

Restarting indefinitely without understanding the cause can create a restart loop and make diagnosis harder.

## journalctl

`journalctl` is used to query the systemd journal.

Common forms include:

`journalctl -u SERVICE`

Shows logs associated with a service.

`journalctl -u SERVICE -n 100`

Shows recent entries.

`journalctl -u SERVICE -f`

Follows new entries.

`journalctl --since "1 hour ago"`

Restricts logs by time.

`journalctl -p warning`

Filters by priority.

The implementations query recent journal entries when the environment permits access.

## Service monitoring architecture

A useful monitoring system separates several concerns.

### Collection

Collect raw observations such as:

- PID
- PPID
- process state
- RSS
- thread count
- service active state
- service substate
- restart count

### Evaluation

Apply explicit rules to observations.

The implementations use rules such as:

- service must be active
- service substate must be expected
- restart count must remain below a threshold
- memory consumption must remain below a configured limit

### Action

A production supervisor may then perform an action such as:

- record an event
- notify an operator
- request a restart
- isolate a failed workload

The educational implementations separate health evaluation from administrative control.

This separation reduces accidental coupling between observation and potentially destructive actions.

## Python implementation

The Python script uses standard-library functionality and Linux interfaces.

### Process identity

The script demonstrates:

- `os.getpid()`
- `os.getppid()`
- `os.getuid()`
- `os.getgid()`
- `os.getpgrp()`
- `os.getsid()`

These values establish the identity and hierarchy context of the current process.

### `/proc` parser

The `parse_proc_status()` function reads `/proc/<pid>/status` and converts key/value lines into a Python dictionary.

This demonstrates a common systems-programming technique:

1. access a kernel-exposed interface
2. parse structured text
3. convert it into application data
4. perform analysis on the structured representation

### Child processes

The script uses `subprocess.Popen()` to create a worker.

`communicate()` collects the child's output and waits for completion.

The implementation also demonstrates timeout handling.

### Signals

The Python implementation registers a `SIGTERM` handler and demonstrates graceful shutdown before escalation.

### Service inspection

The script invokes `systemctl show` to obtain service properties when systemd is available.

It does not assume that every Linux environment runs systemd. This distinction is particularly important in containers, minimal environments and development systems.

### Health model

`evaluate_service_health()` demonstrates deterministic rule-based evaluation without coupling the rules directly to the system-control commands.

## JavaScript implementation

The JavaScript file targets Node.js.

Node.js is useful for this topic because operating-system process management and asynchronous event handling are closely connected.

### `process`

Node exposes information about the current process through the global `process` object.

The implementation uses:

- `process.pid`
- `process.ppid`
- `process.platform`
- `process.arch`
- `process.version`
- `process.cwd()`
- `process.memoryUsage()`

### child_process

The implementation uses:

- `execFile`
- `execFileSync`
- `spawn`

`execFile` executes an executable directly and collects output.

`spawn` is appropriate for long-running programs because output can be consumed as streams.

### Event-driven lifecycle

Child processes emit events such as:

- `spawn`
- `data` on output streams
- `close`

This differs from the synchronous process-management style often used in simple command-line scripts.

The graceful worker example listens for `SIGTERM` and exits after performing its cleanup path.

### Asynchronous monitoring

The monitoring function combines:

- `/proc` reads
- asynchronous timers
- repeated sampling
- early termination when a process disappears

This represents a common event-driven monitoring pattern.

## C++ case study

The C++ implementation presents a more explicit operating-system process model.

### `fork()`

The program creates a child with `fork()`.

The child executes a worker loop.

### `exec()`

The program demonstrates failed `execl()` execution and reports the failure through the child's exit status.

### `waitpid()`

The parent uses `waitpid()` to observe and collect child termination.

The implementation uses `WNOHANG` while waiting with a deadline, allowing the parent to perform bounded polling rather than blocking indefinitely.

### Signal-based shutdown

The worker registers a `SIGTERM` handler.

The parent first sends `SIGTERM`, waits for a configured period and escalates to `SIGKILL` if necessary.

This is a basic process-supervision pattern.

### `/proc` process inventory

The program scans numeric directories under `/proc`.

Each process is converted into a `ProcessInfo` structure containing:

- PID
- PPID
- state
- RSS
- thread count
- name

The records are sorted by resident memory.

The implementation also handles a fundamental race condition: a process can disappear between the directory scan and the attempt to read its status.

This is normal in live process monitoring.

## Comparison of the three implementations

| Concern | Python | JavaScript/Node.js | C++ |
|---|---|---|---|
| Process identity | `os` module | `process` object | POSIX system calls |
| Child processes | `subprocess` | `child_process` | `fork()` |
| Program replacement | Higher-level subprocess API | `spawn`/`execFile` | `exec*()` |
| Waiting | `Popen.wait()` / `communicate()` | child events | `waitpid()` |
| Signals | `signal` module | `process.on()` / `child.kill()` | `signal()` / `kill()` |
| `/proc` | `pathlib` and file I/O | `fs` | `fstream` and filesystem |
| Asynchronous model | Threads/process APIs and blocking calls | Event loop and promises | Threads and explicit system calls |
| Memory control | High-level | Runtime-managed | Explicit low-level control |
| Systems-level visibility | High | High | Very high |
| Typical abstraction level | High | High | Lower |

The languages demonstrate different engineering trade-offs rather than different Linux fundamentals. Linux still supplies the underlying process, signal and service concepts.

## Process monitoring versus service monitoring

These concepts are related but not identical.

Process monitoring asks questions such as:

- Does PID 1234 exist?
- What state is it in?
- How much memory does it use?
- How much CPU does it consume?
- Who is its parent?

Service monitoring asks broader questions:

- Is the service unit active?
- Did systemd successfully start it?
- Is the service repeatedly restarting?
- Are dependencies satisfied?
- Is the expected application endpoint available?
- Are recent logs reporting errors?

A service can be active while an application-level health check fails.

A process can also exist without representing a healthy service.

## Edge cases

### PID reuse

PIDs are finite identifiers and can eventually be reused.

A monitoring program should not assume that a PID always refers to the same logical process over an unlimited period.

### Process disappearance

A process can terminate between two monitoring operations.

For example:

1. `/proc/1234` exists
2. the program begins reading it
3. PID 1234 exits
4. a subsequent file access fails

The Python, JavaScript and C++ examples account for this possibility.

### Permission errors

Some process information may be inaccessible to an unprivileged user.

Monitoring software must treat permission errors as normal operational possibilities.

### Containers

A Linux container may not have systemd as PID 1.

Consequently:

`systemctl`

may fail even though the container is running on a Linux host whose operating system uses systemd.

The implementations explicitly check for command availability and failure.

### Service active but unhealthy

A service can remain running while:

- a worker pool is exhausted
- a database connection is broken
- a listening socket is unavailable
- requests are failing
- internal queues are blocked

A process-level check alone is therefore insufficient for application health.

### Forced termination

`SIGKILL` prevents application cleanup.

Using it as the first response can leave external resources in undesirable states depending on the application and workload.

## Common mistakes

### Killing processes without identifying them

Using an incorrect PID can terminate an unrelated process.

Administrative tools should identify targets carefully.

### Using SIGKILL immediately

Immediate `SIGKILL` removes the application's opportunity to perform graceful shutdown.

A bounded `SIGTERM` followed by escalation is often a more controlled lifecycle pattern.

### Confusing CPU percentage with CPU time

`%CPU` is a utilization measurement over an observation interval. Accumulated CPU time is different.

### Treating high memory as proof of a memory leak

A large RSS value alone does not establish a memory leak.

Memory use must be observed over time and interpreted in relation to workload, caching, allocator behavior and application architecture.

### Ignoring parent-child relationships

Zombie accumulation frequently points toward incorrect child-reaping behavior.

### Parsing human-oriented output unnecessarily

A program that depends on exact `ps` or `systemctl` display formatting can be fragile.

Where structured interfaces exist, they can be preferable for automation.

### Assuming Linux means systemd

Linux is a kernel and ecosystem, not a guarantee that every environment uses systemd.

Minimal containers and other environments may use a different init or service-management architecture.

### Running services as root without need

Unnecessary privileges increase the impact of a compromise.

Service accounts should normally have only the permissions required for their tasks.

## Error handling

Process management is inherently failure-prone because the operating system and the managed process operate concurrently.

Important failures include:

- executable not found
- permission denied
- process exits unexpectedly
- process disappears during inspection
- signal delivery fails
- timeout expires
- service unit does not exist
- systemd is unavailable
- journal access is denied
- `/proc` information is restricted

The implementations explicitly handle several of these conditions.

Production systems should distinguish transient failures from persistent failures and should retain enough diagnostic context to investigate them.

## Performance considerations

Process monitoring has an operational cost.

Potential sources of overhead include:

- scanning `/proc` too frequently
- launching `ps` repeatedly
- launching `systemctl` repeatedly
- reading excessive process metadata
- collecting large logs
- maintaining unnecessarily short polling intervals
- repeatedly allocating temporary objects

A small diagnostic script can afford techniques that would be inappropriate for a high-frequency monitoring agent.

The appropriate sampling interval depends on the problem being observed.

A service that can fail within milliseconds may require different instrumentation from a batch workload whose state changes over several minutes.

For large systems, process-level monitoring is normally combined with system metrics, application metrics, logs and traces.

## Security considerations

Process and service management are privileged operations.

Important principles include:

### Least privilege

Run application services under dedicated accounts when possible.

### Command injection prevention

When an external value becomes part of a command, shell interpretation can introduce serious security risks.

The Python implementation uses argument arrays with `subprocess`.

The Node.js implementation uses `execFile()` rather than relying on shell parsing for service-name lookups.

The C++ case study uses direct POSIX execution APIs.

### Authorization

Input validation does not establish authorization.

A syntactically valid service name can still be a service the caller must not control.

### Secrets

Passwords, tokens and other sensitive values should not be unnecessarily exposed through command-line arguments because process-inspection mechanisms may reveal command lines to other users according to system permissions.

### Service accounts

A compromised process running as an unprivileged account generally has fewer permissions than an equivalent process running as root.

### Unit-file protection

Unauthorized modification of a service unit can provide a path to persistent or privileged execution.

Unit files and their containing directories should therefore be protected according to their security requirements.

### Logging

Logs can contain sensitive data. Access control and retention policies should be considered part of the service architecture.

## systemd and an application supervisor

The C++ program implements a small educational supervisor, but it should not be interpreted as a replacement for systemd.

A production service manager typically handles substantially more concerns, including:

- dependency transactions
- boot ordering
- targets
- restart policies
- service isolation
- socket activation
- timers
- resource controls
- credentials
- logging integration
- lifecycle state transitions
- failure propagation

An application-level supervisor can still be useful when a program needs to manage its own internal worker processes.

The architectural distinction is important:

- systemd supervises services at the operating-system level
- an application supervisor can supervise internal components
- a monitoring system observes health and reports events
- an application health check verifies application-specific behavior

These responsibilities can coexist.

## Troubleshooting methodology

A structured service investigation can follow this sequence:

### Identify the service

Use `systemctl status SERVICE` to establish the basic state.

### Inspect unit properties

Use `systemctl show SERVICE` to obtain structured properties.

### Read logs

Use `journalctl -u SERVICE` to inspect service-specific events.

### Find the process

Use `ps` or the service's `MainPID` property.

### Inspect resources

Check CPU, memory, threads and process state.

### Inspect dependencies

Use `systemctl list-dependencies SERVICE`.

### Check networking

For network services, inspect listening sockets and binding configuration.

### Check permissions

Verify service users, file ownership, directories and access rights.

### Validate configuration

A service that exits immediately may have invalid configuration.

### Change one thing at a time

Controlled changes make cause-and-effect analysis easier.

## Practical applications

The concepts demonstrated here are directly relevant to:

- web-server administration
- backend service operations
- database operations
- DevOps
- site reliability engineering
- Linux system administration
- infrastructure automation
- container runtime design
- process supervisors
- monitoring agents
- job workers
- schedulers
- batch processing
- security monitoring
- incident investigation
- resource management

## Implementation considerations

A production process or service-management application should generally consider:

- authorization
- privilege separation
- race conditions
- PID reuse
- process namespaces
- resource limits
- timeouts
- graceful shutdown
- forced termination
- structured logging
- audit trails
- configuration validation
- concurrency
- restart storms
- dependency failures
- observability
- compatibility across distributions

A particularly important design principle is to assume that the operating-system state can change between every observation.

A process may disappear. A service may restart. A PID may eventually be reused. A unit may change state while its status is being read.

Reliable monitoring therefore treats observations as time-bound snapshots rather than permanent truths.

## Complexity considerations

The `/proc` inventory scans process-directory entries and reads information for each discovered process.

For `N` visible processes, the basic scan is approximately `O(N)` with respect to the number of process entries.

Sorting the collected records by memory consumption adds approximately `O(N log N)` time.

If only the largest few processes are required, a bounded selection strategy can reduce sorting overhead.

The cost of reading `/proc` also depends on how much metadata is collected.

The service-health evaluation itself is constant time, `O(1)`, because it evaluates a fixed number of conditions.

## Relationship between ps, top and systemctl

These tools operate at related but distinct levels.

| Tool | Primary purpose |
|---|---|
| `ps` | Process snapshot |
| `top` | Interactive or sampled process/resource monitoring |
| `systemctl` | systemd unit and service management |
| `journalctl` | systemd journal inspection |

`ps` and `top` primarily expose process-level information.

`systemctl` works with systemd's service and unit model.

`journalctl` provides access to structured journal information.

Using all of them together gives a broader operational picture than relying on a single command.

## Important distinctions

### Process versus service

A process is an operating-system execution context.

A service is a functional capability that may be represented by one or more processes.

### SIGTERM versus SIGKILL

`SIGTERM` gives an application an opportunity to respond.

`SIGKILL` does not.

### Active versus healthy

A systemd service being active does not prove that its application functionality is correct.

### Program versus process

A program is stored executable logic.

A process is an active execution instance.

### Monitoring versus control

Monitoring observes system state.

Control changes system state.

These responsibilities should be separated where practical, particularly when administrative privileges are involved.

## Real-world relevance

Linux process and service concepts form a foundation for understanding how production applications run outside a development environment.

A web application may begin as a process launched manually. In production, the same application may run under a service manager with:

- a dedicated account
- controlled environment variables
- restart behavior
- resource constraints
- dependency relationships
- structured logs
- health checks
- controlled shutdown
- security boundaries

Understanding the process underneath the service makes the higher-level service-management model easier to reason about.

The three implementations demonstrate the same operating-system concepts at different abstraction levels: Python emphasizes practical automation, Node.js emphasizes asynchronous supervision, and C++ exposes the lower-level process primitives used to construct process-management systems.
```
