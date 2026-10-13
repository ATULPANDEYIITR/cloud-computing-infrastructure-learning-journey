# Compute Scaling: Capacity Engineering and Workload Planning

## Scope

Compute scaling is the process of adjusting computing resources to meet application demand while controlling latency, reliability, and cost. A scaling decision must account for more than CPU usage. Memory requirements, connection limits, network throughput, application architecture, dependency capacity, and the time required to provision resources all influence the result.

This project models four connected concerns:

- **Vertical scaling:** changing the capacity of an individual compute instance.
- **Horizontal scaling:** changing the number of independent application instances.
- **Scaling limits:** identifying resource bottlenecks and the maximum capacity supported by a deployment.
- **Workload planning:** estimating future demand from observed traffic, growth assumptions, and safety margins.

The implementations use hypothetical compute specifications and prices. Their calculations illustrate capacity-planning methods rather than guaranteeing production performance.

## Core capacity model

### Workload demand

A workload is described by its request rate and resource requirements. The request rate is measured in requests per second (RPS). Other relevant inputs include CPU consumption per request, memory required by each replica, concurrent connections, and network throughput.

For a workload with request rate \(R\), CPU demand \(c\) cores per request, and a benchmark throughput of \(b\) requests per core-second, approximate CPU demand is:

\[
C_{\text{demand}} = \frac{R c}{b}
\]

The model reserves part of the available CPU capacity rather than planning around full utilization. If the target CPU utilization is \(u\) and the safety factor is \(s\), the CPU-based throughput estimate for an instance with \(v\) virtual CPUs is:

\[
R_{\text{CPU}} = \frac{vbu}{cs}
\]

This estimate is useful for preliminary planning, but the benchmark \(b\) must be measured using representative requests. Different request paths can have substantially different CPU costs.

### Resource bottlenecks

A deployment is constrained by the resource that supports the least throughput. For an individual instance, the model calculates separate estimates for CPU, memory, connections, and network bandwidth:

\[
R_{\text{instance}} =
\min(R_{\text{CPU}}, R_{\text{memory}},
R_{\text{connections}}, R_{\text{network}})
\]

If there are \(n\) equivalent replicas, the simplified deployment capacity is:

\[
R_{\text{deployment}} \approx nR_{\text{instance}}
\]

This relationship assumes that requests can be distributed effectively, instances have comparable performance, and shared dependencies can handle the resulting traffic. It is not valid without adjustment when a database, external API, shared lock, or other common dependency limits throughput.

Memory is modeled as an admission constraint based on the configured memory requirement per replica. The model also evaluates the estimated CPU, connection, and network utilization against their target limits.

A feasible plan must satisfy all relevant constraints. A deployment that has enough aggregate CPU but insufficient memory or connection capacity is not considered feasible.

## Vertical scaling

Vertical scaling assigns more resources to an existing instance. Depending on the platform, this may mean selecting a larger instance type, increasing available CPU and memory, or changing a compute allocation.

The principal advantage is that an application can often gain capacity without distributing its state or requests across additional instances. The main limitations are the maximum size of the available instance types, the cost of larger instances, and the operational effects of resizing or replacing a running machine.

The Python and Java implementations evaluate eligible instance types in ascending hourly cost while keeping the replica count fixed. The C++ case study uses the same planning principle through a dedicated capacity engine.

The selection process considers:

- Whether the instance meets the modeled throughput requirement.
- Whether memory, connection, network, and CPU targets remain within bounds.
- Whether the candidate is within the configured maximum vCPU and memory limits.
- Whether a larger instance provides sufficient capacity at an acceptable cost.

Vertical scaling cannot solve every capacity problem. A workload that requires more memory than any allowed instance provides, or that is constrained by a remote database, may remain infeasible even after the compute instance is enlarged.

## Horizontal scaling

Horizontal scaling adds or removes independent application instances. A load balancer or equivalent request distributor directs traffic among available replicas.

For approximately independent replicas, adding instances increases aggregate capacity without requiring a single instance to become larger. The benefit depends on the ability to distribute work efficiently and on whether the application can operate correctly across multiple instances.

Horizontal scaling is most useful when the application supports concurrent request processing, shared or externalized state, safe retry behavior, and sufficiently independent work units.

Important constraints include:

- **Shared dependencies:** a database connection pool or downstream service can become the bottleneck as application replicas increase.
- **State management:** in-memory session state can make requests dependent on a particular replica.
- **Uneven traffic:** poor load distribution can leave some instances overloaded while others are underused.
- **Replica startup time:** new instances may not become ready before a traffic spike reaches its peak.
- **Cost:** additional replicas consume resources even when demand falls.

The Python and Java programs search for the smallest feasible replica count within configured bounds. The C++ program uses a bounded search to show how an infrastructure planner can reject a workload when the available replica range is insufficient.

## Scaling limits and feasibility

Scaling limits are explicit capacity and policy boundaries. They prevent a planner from assuming that resources can grow indefinitely.

This project models two classes of limits.

### Resource limits

Each instance has finite CPU, memory, connection, and network capacity. These values determine the approximate throughput ceilings used by the capacity engine.

The implementation reports the resource or resources that produce the lowest throughput estimate. This is important because a capacity recommendation should explain why a particular instance size or replica count was selected.

### Policy limits

A scaling policy can specify minimum and maximum replicas, permitted vertical instance sizes, utilization thresholds, and cooldown duration.

When a workload cannot fit within those bounds, the planning functions return no feasible configuration. This is preferable to returning an oversized estimate that silently violates the configured policy.

The JavaScript autoscaler and the C++ and Java state models also enforce minimum and maximum replica counts during scale-in and scale-out operations.

A production scaling system should distinguish a rejected scaling request from a successful capacity change. The existence of a desired replica count does not prove that instances have started, passed health checks, or begun serving traffic.

## Workload forecasting

Capacity planning should consider traffic patterns instead of relying exclusively on a single average request rate.

The Python, JavaScript, C++, and Java implementations calculate a percentile from historical observations. The examples use a linearly interpolated P95 estimate to represent a high traffic level that is exceeded by approximately five percent of observations.

The planning calculation is:

\[
R_{\text{plan}} =
R_{\text{P95}}(1+g)s
\]

where:

- \(R_{\text{P95}}\) is the observed P95 request rate.
- \(g\) is the assumed fractional growth rate.
- \(s\) is the safety factor.

For example, a 25% growth assumption is represented by \(g=0.25\), not by 25. The safety factor provides additional capacity for uncertainty. It is not a substitute for a reliable forecast or a formal availability target.

The SQL example stores a current request rate, growth rate, and safety factor for each workload. Its forecast view calculates a growth-adjusted planning rate. The SQL view uses current workload inputs and an observed peak, whereas the application implementations calculate P95 directly from a sample list. These approaches serve different purposes and should not be treated as equivalent.

For production forecasting, observations should be collected at a consistent interval and grouped into meaningful windows. Daily peaks, weekly patterns, seasonal demand, planned launches, and sudden traffic surges may require separate treatment.

## Reactive autoscaling and cooldowns

Reactive autoscaling changes capacity in response to measured utilization. A simple policy can scale out when utilization exceeds an upper threshold and scale in when utilization falls below a lower threshold.

The two thresholds create a hysteresis band. Without this separation, a deployment near a single threshold can repeatedly add and remove replicas in response to small metric fluctuations.

The JavaScript implementation uses an event-driven controller. Subscribers receive an event when a replica count changes, and the subscription function returns an unsubscribe operation to avoid retaining listeners unnecessarily.

The Python, C++, and Java examples model time-based cooldowns. A cooldown prevents a new scaling action immediately after a previous action. It gives the system time to provision resources and observe the effects of the change.

A production autoscaler needs additional safeguards:

- Metrics must be timestamped, fresh, and associated with the correct deployment.
- Missing or invalid metrics should not be interpreted as proof of low demand.
- Scale-out and scale-in actions should respect deployment health.
- Maximum capacity should trigger an alert or another defined response.
- Scaling events should be logged for diagnosis and cost attribution.
- Request rate, queue depth, latency, and error rate should supplement CPU utilization where appropriate.

CPU utilization alone is an incomplete signal. A service waiting on a database can have low CPU usage while experiencing high latency and a growing queue.

## Python implementation

The Python program provides a standard-library capacity-planning model with immutable instance and workload definitions, explicit validation, and structured decision results.

`InstanceType` represents the compute options available to the planner. `Workload` captures resource demand. `CapacityProfile` defines target utilization and the benchmark throughput assumption.

`estimate_instance_capacity()` calculates throughput ceilings for CPU, memory, connections, and network. It returns both the limiting capacity and the resource names responsible for that limit.

`evaluate_deployment()` checks a complete deployment against its workload and capacity profile. `plan_vertical_scaling()` selects an eligible instance while preserving the replica count, whereas `plan_horizontal_scaling()` searches for a feasible replica count.

The `Autoscaler` class demonstrates threshold-based state changes, minimum and maximum replica limits, and cooldown enforcement. `workload_forecast()` estimates planning demand from a list of traffic observations.

The script includes self-tests for invalid inputs, zero traffic, percentile boundaries, minimum replicas, and workloads that exceed the available capacity range. These checks exercise failure conditions instead of validating only successful plans.

Run the program with `python compute_scaling.py`.

## JavaScript implementation

The JavaScript file focuses on immutable workload and instance objects, event-driven control, and asynchronous execution.

`WorkloadProfile` and `ComputeInstance` validate their configuration and freeze the resulting objects. This reduces accidental mutation of the inputs used by capacity calculations.

`forecastWorkload()` calculates traffic statistics, while `evaluate()` produces a deployment decision with estimated capacity, monthly compute cost, resource utilization, bottlenecks, and explicit violations.

`ScalingController` keeps its mutable replica count private. Its event subscription mechanism lets monitoring code respond to scaling events without coupling the controller to a specific logging or monitoring system.

`runConcurrentLoadSimulation()` uses a bounded worker pool rather than starting one promise for every request. The simulation illustrates controlled concurrency and reports a measured completion rate. Its short artificial service delays do not represent a benchmark of a real API, and the result should not be used to size production infrastructure.

Run the file with `node compute-scaling.js`.

## C++ case study

The C++ program models an order-processing service that must meet a forecast request rate within infrastructure limits.

`CapacityEngine` separates per-instance capacity calculations from deployment evaluation. It validates workload and instance specifications, identifies resource bottlenecks, and determines whether a proposed configuration meets the modeled requirements.

Vertical planning filters instance types against administrative limits and examines eligible candidates in cost order. Horizontal planning increases the replica count within a bounded range.

The `Evaluation` structure contains the proposed mode, instance, replica count, estimated capacity, hourly cost, bottlenecks, and violations. This makes the planning result usable by a caller that needs to explain why a deployment was accepted or rejected.

`ReplicaAutoscaler` represents a separate runtime mechanism. It uses utilization thresholds, cooldowns, chronological observations, and replica bounds. Keeping the planner separate from the autoscaler reflects the distinction between choosing a deployment configuration and making ongoing operational changes.

The program includes assertions for feasible small workloads, impossible configurations, and monthly compute cost calculations. It compiles using C++17 and the standard library.

## Java implementation

The Java program uses records and service classes to represent an enterprise-oriented capacity planning system.

`InstanceType`, `Workload`, `CapacityPolicy`, `Evaluation`, and `ResourceCapacity` define the principal domain data. Constructors validate configuration before the planner uses it. `Evaluation` copies its collections to prevent callers from modifying the recorded utilization, bottlenecks, or violations through an external reference.

`CapacityPlanningService` handles resource calculations and both scaling strategies. Its vertical planner filters candidates by administrative limits and evaluates them in cost order. Its horizontal planner searches a bounded replica range.

`AutoscalingPolicy` stores threshold and replica rules independently of `AutoscalingService`. This separation allows policy configuration to be validated separately from runtime state transitions.

The `Optional<Evaluation>` return type makes the absence of a feasible configuration explicit. It avoids inventing a deployment when no candidate satisfies the configured limits.

Compile and run the program with `javac ComputeScaling.java` and `java ComputeScaling`.

## PostgreSQL data model

The SQL script models capacity planning as relational data rather than as an in-memory simulation.

| Table | Purpose |
|---|---|
| `instance_types` | Defines available compute resources, connection capacity, network bandwidth, and hourly cost. |
| `workloads` | Stores traffic demand, growth assumptions, safety factors, and resource requirements. |
| `scaling_policies` | Defines scaling mode, utilization targets, replica bounds, cooldowns, and vertical size limits. |
| `deployment_plans` | Associates a workload with an instance type, policy, replica count, and planning demand. |
| `workload_metrics` | Stores timestamped traffic, utilization, latency, and error observations. |
| `scaling_events` | Records proposed scale-in or scale-out operations and whether they were accepted. |

Primary keys identify records, while foreign keys preserve relationships between workloads, instance types, policies, deployments, metrics, and events. Check constraints reject invalid resource specifications, negative costs, invalid scaling modes, and inconsistent scaling thresholds.

The `idx_metrics_workload_time` index supports queries that retrieve recent observations for a particular workload. The deployment and event indexes support operational lookups by workload status and deployment history.

`workload_forecast` calculates growth-adjusted demand from the workload's configured request rate. `scaling_plan_evaluation` compares estimated throughput and utilization with policy targets, then labels the result as feasible under the modeled constraints or identifies a violation.

The cost comparison query uses PostgreSQL's `generate_series()` to calculate the estimated cost of different replica counts. The pressure query identifies observations where utilization or latency exceeds the configured limits.

The event insertion demonstrates how a scaling decision can be recorded with a reason and accepted flag. The final reconciliation query identifies accepted events whose requested replica count differs from the current deployment configuration.

This distinction is important: recording a desired change is not the same as successfully applying it. A production controller would need to coordinate the database transaction with the infrastructure provider, monitor the deployment outcome, and reconcile failures.

Execute the script in a PostgreSQL environment. It creates and replaces the demonstration objects in the current schema, so it should be run in a dedicated learning database.

## Cost and capacity trade-offs

Hourly compute cost is calculated as:

\[
C_{\text{hour}} = nC_{\text{instance}}
\]

The illustrative monthly estimate uses 730 hours:

\[
C_{\text{month}} = 730C_{\text{hour}}
\]

These estimates include only the compute instances represented by the model. They exclude storage, load balancing, network transfer, database services, observability, licenses, reserved-capacity discounts, taxes, and operational overhead.

The cheapest feasible plan is not automatically the best production plan. A slightly more expensive configuration may provide faster recovery, greater fault tolerance, lower tail latency, or better performance during traffic spikes.

Capacity planning should therefore evaluate both resource feasibility and operational objectives. Availability targets, deployment failure behavior, startup time, dependency limits, and the cost of unused capacity can change the preferred design.

## Model limitations

The programs intentionally use a simplified capacity model. Their output is suitable for learning how resource constraints and scaling policies interact, not for treating calculated throughput as a guaranteed service limit.

Actual capacity depends on request complexity, runtime behavior, garbage collection, disk I/O, caching, network conditions, concurrent connections, dependency response times, and contention between workloads.

Memory utilization also requires careful interpretation. Memory used by a process does not necessarily grow in proportion to requests per second, and a replica's baseline memory requirement may be different from its peak requirement. The examples therefore use configured memory demand as an admission constraint rather than attempting to predict real memory consumption from request rate.

Similarly, adding replicas does not always increase capacity linearly. Shared databases, locks, rate limits, and uneven work distribution can prevent additional instances from improving throughput.

A reliable production plan should be validated against representative load tests, observed service-level indicators, realistic traffic patterns, and the failure behavior of its dependencies.
