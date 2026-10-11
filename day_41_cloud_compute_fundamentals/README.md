# Cloud Compute Fundamentals

## Scope

Cloud compute provides virtualized processing capacity on demand. A cloud instance combines a selected compute configuration with a bootable machine image and associated infrastructure. Choosing an instance requires more than comparing virtual CPU counts: memory capacity, CPU performance, network limits, processor architecture, image compatibility, workload behavior, and cost all affect suitability.

This project models five connected areas:

- **Instances:** provisioned compute resources with a lifecycle that includes stopped, running, and terminated states.
- **Virtual CPUs:** the processor capacity exposed to a virtual machine by the cloud platform.
- **Memory:** RAM allocated to an instance, expressed here in GiB.
- **Instance families:** groups of configurations optimized for different workload characteristics.
- **Machine images:** reusable bootable software baselines that determine the operating system, architecture, and initial disk configuration.

The implementations use illustrative specifications and prices. They do not connect to a cloud provider, reserve capacity, or create billable resources.

## How instance sizing works

An instance type specifies a resource configuration. Its virtual CPU count, memory allocation, network capability, architecture, and pricing characteristics determine which workloads it can support.

| Resource or property | Meaning | Capacity-planning implication |
|---|---|---|
| vCPU | Virtual processor capacity exposed to the guest operating system | Relevant to parallelism and compute demand, but not a universal measure of performance |
| Memory | RAM available to the instance | Determines how much working data and how many processes can remain in memory |
| Network throughput | A provider-defined network capacity rating | Important for distributed processing, data transfer, and service-to-service communication |
| Architecture | Processor instruction-set family, such as `x86_64` or `arm64` | Must be compatible with the machine image and workload binaries |
| Instance family | A category of resource configurations | Helps narrow selection by expected CPU, memory, or general-purpose requirements |
| Machine image | Bootable software baseline | Determines the operating system, installed software, architecture, and initial root-disk requirements |
| Hourly rate | Illustrative charge per instance-hour | Supports preliminary cost estimates, not a complete invoice |

A configuration with eight vCPUs and 16 GiB of memory has 2 GiB per vCPU. A configuration with four vCPUs and 32 GiB has 8 GiB per vCPU. The latter may suit an in-memory analytics service better, while the former may be more appropriate for parallel CPU-intensive work.

Neither ratio guarantees application performance. Actual performance also depends on processor generation, sustained CPU entitlement, workload parallelism, storage latency, network behavior, and contention.

## vCPUs and memory are separate constraints

Capacity planning must evaluate processor and memory requirements independently. A workload that needs six vCPUs and 8 GiB of memory cannot fit on a two-vCPU instance merely because that instance has sufficient RAM. Similarly, a memory-intensive workload may fail even when the instance has enough vCPUs.

The examples reserve a fraction of CPU capacity and a fixed amount of memory for system overhead. The estimated placement count is the smaller of the CPU-based and memory-based limits:

- Usable CPU is calculated from the configured vCPU count after applying a reserve.
- Usable memory is calculated after subtracting the memory reserve.
- CPU capacity is divided by the workload's vCPU requirement.
- Memory capacity is divided by the workload's memory requirement.
- The smaller whole-number result determines the estimated number of placements.

This is a simplified packing estimate. It does not model NUMA placement, hypervisor overhead in detail, operating-system variability, container reservations, storage bandwidth, or interference between workloads.

## Instance families

The sample catalog uses three family categories to illustrate resource trade-offs.

| Family | Representative configuration | Suitable workload pattern |
|---|---|---|
| General purpose | Four vCPUs and 16 GiB of RAM | Web services, application servers, and balanced services |
| Compute optimized | Eight vCPUs and 16 GiB of RAM | Batch processing and CPU-intensive workers |
| Memory optimized | Four vCPUs and 32 GiB of RAM | In-memory analytics and large working sets |

These names represent conceptual categories, not a specific provider's product naming system. Actual cloud providers offer many additional family classes and different performance guarantees.

The catalog also includes an ARM-based compute configuration. Processor architecture is a compatibility property rather than a performance ranking. ARM-based workloads must use compatible operating-system images, executable binaries, and native dependencies.

### Burstable configurations

A burstable instance can provide temporary CPU performance above its sustainable baseline, subject to provider-specific rules such as CPU credits. Such configurations can be cost-effective for intermittent development services and low-utilization applications.

They are not automatically appropriate for continuously CPU-intensive jobs. The Python, JavaScript, C++, and Java planners exclude burstable configurations unless the workload explicitly permits them. A production planner would also evaluate CPU-credit balance, baseline performance, and observed utilization.

## Machine images and launch compatibility

A machine image defines the software environment from which an instance boots. Its architecture must match the selected instance architecture. The root-disk size must satisfy the environment's minimum requirements, and image provenance must meet the deployment's trust policy.

The sample models include image ownership, trust, encryption, status, architecture, and root-disk size. These are separate properties:

- **Ownership and provenance** help establish where the image originated and who maintains it.
- **Architecture compatibility** determines whether the image can boot and whether its binaries can execute on the selected processor.
- **Encryption** represents a security requirement for the image baseline in this model. Real deployments must also verify encryption and access policies for persistent volumes and snapshots.
- **Image status** distinguishes approved images from deprecated or revoked images.
- **Root-disk capacity** represents an initial disk requirement, not the total storage needed by the running workload.

A trusted image can still be unsuitable if its architecture is wrong or its operating system is no longer supported. Conversely, an architecture-compatible image should not be trusted solely because it can boot.

The code rejects untrusted or unencrypted images and prevents an instance from starting after termination. These checks illustrate policy enforcement; they are not a substitute for cloud identity and access management, image-signing verification, vulnerability scanning, patch management, or provider-side launch restrictions.

## Instance lifecycle

The model supports three states:

| State | Meaning | Allowed operation |
|---|---|---|
| Stopped | The instance is not currently running | Start, terminate |
| Running | The instance is active | Stop, terminate |
| Terminated | The instance has reached its final modeled state | No further lifecycle transition |

Stopping and terminating are distinct. A stopped instance may be restarted, subject to the model's launch checks. A terminated instance cannot be restarted. Real providers have additional differences involving billing, retained disks, public addresses, snapshots, and termination protection.

The code makes lifecycle transitions explicit so that invalid operations produce errors instead of silently changing state.

## Python implementation

The Python script provides a compact capacity-planning domain model using dataclasses, enums, validation methods, and standard-library collections.

`MachineImage`, `InstanceType`, and `Workload` represent different kinds of configuration data. Their responsibilities are intentionally separate: images validate software-baseline properties, instance types describe resource capacity, and workloads express minimum requirements.

`recommend_instances` filters catalog entries by architecture, workload class, vCPU capacity, memory, network capability, and burstability policy. It sorts the remaining candidates by hourly price and then by capacity. This is a deterministic screening rule, not a claim that the cheapest compatible configuration always performs best.

`estimate_capacity` calculates an approximate packing limit after reserving CPU and memory headroom. `estimate_monthly_cost` estimates compute charges for a chosen billing schedule and validates its inputs.

`CloudInstance` implements start, stop, restart, and termination behavior. The demonstration deliberately tests architecture mismatch, untrusted images, invalid billing input, and an attempted restart after termination.

The script runs with the Python standard library. It performs no real provisioning and should be treated as a local teaching model rather than a provider SDK.

## JavaScript implementation

The JavaScript program focuses on an event-driven provisioning model suitable for Node.js.

The instance catalog is represented by frozen objects. `recommendInstanceTypes` uses array filtering and sorting to produce compatible candidates. The validation function checks numeric requirements before recommendations are calculated, preventing malformed input from producing misleading capacity results.

`Instance` extends `EventEmitter`. When a state transition occurs, the class emits a `stateChanged` event containing the instance identifier, previous state, next state, and timestamp. This separates lifecycle observation from the code responsible for making transitions.

The provisioning demonstration uses `setImmediate` and a Promise to represent asynchronous control-plane work. The caller awaits the result and handles provisioning failures through standard Promise error propagation.

The class keeps lifecycle state private. Repeated starts on an already running instance are idempotent, while attempts to restart a terminated instance fail. Machine-image validation is performed before a stopped instance enters the running state.

The program requires Node.js 18 or later and has no external package dependencies. Its asynchronous behavior is simulated; no API request is sent to a cloud provider.

## C++ case study: compute fleet planning

The C++ program models a fleet-planning engine that must place workloads on compatible instance configurations.

`InstanceType`, `MachineImage`, and `Workload` are separate structures. `GovernanceEngine` owns the catalog and provides recommendation and packing operations. `ComputeInstance` represents the lifecycle of a selected resource.

The recommendation algorithm filters out configurations that do not satisfy the workload's architecture, workload class, CPU, memory, network, or burstability requirements. It then sorts the surviving candidates by price and capacity. For a catalog of \(n\) instance types, filtering takes \(O(n)\) time and sorting the compatible candidates takes \(O(k \log k)\), where \(k\) is the number of compatible types.

The packing calculation reserves 10% of configured CPU capacity and 0.5 GiB of memory by default. The result is the minimum of the independent CPU and memory placement limits. If either resource cannot accommodate a single workload, the estimated placement count is zero.

The lifecycle model uses exceptions to reject invalid transitions. A launch validates image trust, encryption, disk capacity, and architecture compatibility. Termination is final within this model.

The program uses C++17 standard-library features and compiles without third-party dependencies. It illustrates deterministic selection and explicit failure handling without implying that the sample catalog reflects real cloud hardware performance.

## Java implementation: enterprise capacity planning

The Java program uses records, enums, immutable collection copies, and a dedicated `CapacityPlanningService` to separate configuration from business rules.

`MachineImage`, `InstanceType`, and `Workload` records validate their data when constructed. The instance-type record stores hourly rates as `BigDecimal`, avoiding the ordinary binary floating-point representation issues that can arise when calculating currency.

The service uses streams to filter and order candidate instance types. Architecture, workload class, CPU, memory, network, and burstability remain separate conditions. This keeps the selection policy explicit and makes it easier to test individual constraints.

`CapacityEstimate` records the estimated number of workload placements along with usable CPU and memory. Returning the assumptions as data makes the estimate more auditable than returning a placement count alone.

The `Instance` class uses synchronized lifecycle methods to serialize state changes within the running process. Its immutable tags prevent callers from changing the original metadata map through a retained reference. These controls illustrate local thread-safety and state integrity, not distributed locking across cloud control planes.

The implementation requires Java 17 or later. It uses no third-party libraries and does not create actual cloud resources.

## PostgreSQL data model

The SQL script models cloud capacity as related relational entities rather than as an in-memory catalog.

| Table | Responsibility |
|---|---|
| `instance_families` | Stores family classification and intended workload characteristics |
| `instance_types` | Stores CPU, memory, architecture, network, price, and availability |
| `machine_images` | Stores image provenance, architecture, encryption, trust, and lifecycle status |
| `workloads` | Stores application resource requirements and burstability policy |
| `instances` | Stores provisioned-instance references and current lifecycle state |
| `instance_state_events` | Records state transitions for audit and troubleshooting |

Primary keys, foreign keys, unique constraints, and check constraints enforce structural integrity. For example, an instance type cannot have zero vCPUs or negative memory, and a machine image cannot declare an unsupported architecture.

The partial index on available instance configurations supports capacity searches that exclude unavailable types. The image policy index supports filtering for trusted and encrypted images. The instance-state index supports inventory queries grouped by lifecycle state.

### Candidate selection and cost analysis

`workload_instance_candidates` joins workloads, instance types, and machine images. It selects only types with sufficient resources, matching architecture, acceptable burstability, and an available image that meets the trust and encryption requirements.

A window function assigns a price rank within each workload. The resulting query returns a shortlist rather than a single universal recommendation. The lowest-priced candidate still needs performance testing before production selection.

The capacity query calculates usable CPU and memory after explicit reserves, then uses `LEAST` to derive the limiting resource. The family inventory query aggregates catalog counts, vCPU totals, memory totals, and price ranges.

The monthly cost field is a compute-only estimate based on a 30-day month. It excludes disks, snapshots, network egress, operating-system licenses where applicable, taxes, and provider-specific billing rules.

### Database-level launch enforcement

`enforce_instance_launch_policy` is a PostgreSQL trigger function. It checks the selected instance type and image when an instance enters the running state or changes its launch configuration. It rejects unavailable instance types, architecture mismatches, and images that are untrusted, unencrypted, deprecated, or revoked.

The function also prevents a terminated instance from returning to another state. `record_instance_state_event` records insertions and lifecycle transitions in the audit table.

The sample uses a savepoint to demonstrate a rejected architecture mismatch without abandoning the remaining demonstration. PostgreSQL's transactional behavior allows the test operation to be rolled back while preserving the valid catalog and instance records.

These triggers protect the modeled database state, but they cannot independently guarantee that an external cloud provider has actually launched, stopped, or terminated a resource. A production implementation would reconcile database records with provider APIs and handle concurrency, API failures, retries, idempotency, and audit permissions.

## Cost estimation and operational constraints

A basic monthly estimate is:

\[
\text{Compute cost} =
\text{hourly rate} \times \text{billable hours}
\]

For an illustrative rate of $0.12 per hour, continuous usage for 720 hours produces a compute estimate of $86.40. Running the instance for only eight hours per day over 30 days produces an estimate of $28.80 under the same assumed hourly rate.

This calculation assumes that the chosen rate applies throughout the period. Real billing can depend on the provider, region, operating system, purchase commitment, minimum billing increments, discounts, and lifecycle state.

Stopping an instance does not necessarily stop charges for associated disks, reserved addresses, snapshots, or other retained resources. A cost-control system must account for those resources separately.

## Security and production boundaries

A production capacity planner needs more than resource filtering.

- **Image provenance:** restrict launch operations to approved image owners and verify signatures, patch levels, and vulnerability status.
- **Identity and access:** ensure that only authorized principals can create, modify, or terminate instances.
- **Encryption:** apply storage encryption policies to root disks, attached volumes, and retained snapshots.
- **Architecture compatibility:** validate native dependencies and executable formats, not just the image's declared architecture.
- **Quota and availability:** confirm regional capacity, account quotas, and service limits before provisioning.
- **Observability:** compare estimated capacity with CPU utilization, memory pressure, network throughput, and application latency.
- **Cost control:** distinguish compute charges from storage, egress, licensing, and retained-resource charges.
- **Reconciliation:** track provisioning requests, actual provider state, failures, retries, and audit events.

A catalog-based recommendation is an initial screening decision. Final sizing should be based on representative workload measurements and the actual limits and guarantees of the selected cloud platform.
