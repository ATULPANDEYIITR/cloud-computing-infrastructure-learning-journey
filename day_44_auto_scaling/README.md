# Auto Scaling: Metrics, Policies, Thresholds, and Capacity Management

## Technical scope

Auto scaling adjusts the compute capacity assigned to a service as its workload changes. A scaling controller observes monitoring data, evaluates configured policies, calculates a desired capacity, and requests a change to the capacity managed by a scaling group.

The central engineering problem is not simply deciding when CPU utilization is high. A reliable controller must distinguish current capacity from available capacity, account for instance startup time, reject invalid telemetry, limit rapid reversals, recover from unhealthy instances, and preserve explicit minimum and maximum capacity boundaries.

This project models an order-processing or payment API that experiences changing request rates throughout the day. The same principles apply to web applications, background workers, containerized services, and other workloads whose resource requirements vary over time.

All implementations are local simulations. They do not connect to a cloud provider, provision machines, or retrieve live monitoring data.

## Core terminology

| Term | Technical meaning |
|---|---|
| Scaling group | A managed collection of compute instances with shared capacity limits and scaling behavior. |
| Minimum capacity | The lowest permitted desired capacity. It can preserve baseline availability even when traffic is low. |
| Maximum capacity | The upper capacity boundary that limits resource consumption and uncontrolled expansion. |
| Desired capacity | The number of instances the controller requests the group to maintain. |
| Actual capacity | The instances currently represented by the group, including instances that might not yet be ready to serve traffic. |
| Healthy capacity | The instances that have completed initialization and passed the relevant health checks. |
| Warm-up period | The time required for a newly launched instance to initialize and become useful to the application. |
| Scaling metric | A measurement used to assess workload or service performance, such as CPU utilization or request latency. |
| Threshold | A boundary that determines whether a metric requires a scaling decision. |
| Evaluation period | An observation interval used to determine whether a condition persists rather than appearing in a single sample. |
| Cooldown | A time restriction intended to reduce repeated scaling actions in rapid succession. |
| Stabilization | A broader control strategy that reduces unnecessary capacity changes caused by noisy or rapidly changing metrics. |
| Target tracking | A policy that adjusts capacity to keep a selected metric near a configured target. |
| Step scaling | A policy that selects a capacity adjustment based on the severity of a metric deviation. |
| Scheduled scaling | A policy that sets capacity at a known time to prepare for an expected workload. |
| Scale-in protection | An instance-level restriction that prevents an otherwise eligible instance from being removed during scale-in. |

These mechanisms serve different purposes. Metrics describe observed conditions. Policies interpret those conditions. Scaling groups enforce capacity boundaries and manage instance lifecycle operations.

## Control-system architecture

The implementations use the following logical sequence:

    Workload
       |
       v
    Monitoring metrics
       |
       v
    Validation and metric window
       |
       v
    Scaling policy evaluation
       |
       v
    Thresholds, evaluation periods, cooldowns
       |
       v
    Desired-capacity calculation
       |
       v
    Scaling-group capacity limits
       |
       v
    Instance launch, warm-up, termination, or replacement
       |
       v
    Updated capacity and audit events

The control loop is a feedback system. A scaling action changes capacity, and the resulting capacity affects future metric observations. Decisions therefore depend on both the current measurements and the recent history of the system.

The implementations keep the policy decision separate from the group operation. This makes it possible to change the scaling algorithm without discarding instance lifecycle management, capacity constraints, or event recording.

## Metrics and thresholds

### CPU utilization

CPU utilization is the percentage of available processor capacity being consumed. It is a useful signal for CPU-bound workloads, but it is not a universal measure of demand.

A service can experience high request latency while CPU utilization remains low because requests are waiting for database connections, network responses, locks, or another constrained resource. A CPU-only policy can miss those conditions.

The examples use a target CPU utilization of 55%. The controller compares the observed or averaged utilization with this target.

For observed metric \(m\) and configured target \(t\), the utilization ratio is:

\[
r=\frac{m}{t}
\]

A ratio of \(1.4\) means that the observed value is 140% of the target. It does not mean CPU utilization itself is 140%; a valid CPU metric remains bounded between 0% and 100%.

### Request rate

Requests per second measures incoming or processed workload volume. It can be useful when the service has reasonably predictable work per request.

A request-rate policy is less reliable when request complexity varies significantly. Ten expensive requests may require more resources than hundreds of lightweight requests. Production systems can combine request rate with latency, queue depth, concurrency, or workload-specific measurements.

### Tail latency

The 95th-percentile latency, or p95, estimates the response time below which 95% of observations fall within the measurement population. It helps identify poor experiences that an average can conceal.

Latency-driven scaling requires care. If latency increases because a downstream database is saturated, adding application instances may increase connection pressure without improving response times. The metric should be interpreted alongside the architecture and the actual bottleneck.

### Error rate

Error rate is the percentage of requests that fail. A sudden increase can indicate overload, dependency failure, or a software defect.

Scaling can help when failures result from insufficient service capacity. It cannot repair every cause of errors. A production controller should avoid treating every error-rate increase as an instruction to launch more instances.

### Threshold bands

The implementations use separate scale-out and scale-in boundaries. In the Python, JavaScript, C++, and Java examples, the illustrative ratios are 1.10 for scale-out and 0.75 for scale-in.

For a target of 55% CPU, these ratios correspond to:

- Scale-out candidate: averaged CPU reaches at least 60.5%.
- Scale-in candidate: averaged CPU falls to 41.25% or less.
- Neutral region: the average remains between these boundaries.

The neutral region reduces the likelihood that minor metric changes cause the controller to reverse its decision on every evaluation.

These values are educational settings, not universal production recommendations. Actual thresholds depend on workload behavior, service-level objectives, startup time, and available headroom.

## Target tracking, step scaling, and scheduled scaling

### Target tracking

Target tracking attempts to keep a selected metric near a target value. When the metric stays above the target, the controller requests more capacity. When it stays sufficiently below the target, the controller may request less capacity.

The proportional estimate used in these simulations is:

\[
\Delta C \approx
\left\lceil C_d(r-1)\right\rceil
\]

where \(C_d\) is the current desired capacity and \(r\) is the ratio of observed utilization to the target.

The calculation estimates a change rather than predicting the exact capacity required by a real application. Each implementation bounds the resulting adjustment to prevent an extreme metric value from causing an unbounded change in one evaluation.

Real cloud target-tracking systems can use provider-specific algorithms, metric aggregation, predictive mechanisms, and additional restrictions. Their exact behavior should not be assumed to match this illustrative formula.

### Step scaling

Step scaling maps metric severity to a configured adjustment. For example, a moderate threshold breach could request two additional instances, while a more severe breach could request a larger adjustment.

Its defining feature is the explicit mapping from metric deviation to a capacity change. It does not simply attempt to maintain a single target through a proportional estimate.

The Python implementation contains an explicit step-policy evaluator. The PostgreSQL model stores separate step-policy configuration, including a latency-based policy, to demonstrate that different metrics can drive different adjustments.

### Scheduled scaling

Scheduled scaling changes desired capacity at a known time.

A business-hours preparation action might raise desired capacity shortly before a predictable increase in traffic. Scheduled capacity can reduce the delay associated with waiting for reactive metrics to cross a threshold.

A schedule must be evaluated against the group's minimum and maximum values. A scheduled target outside these boundaries is invalid rather than an instruction to bypass them.

Scheduling and target tracking can coexist, but their interactions need a defined precedence strategy. For example, a scheduled increase can establish a higher baseline while reactive policies continue to respond to actual demand.

## Evaluation periods, rolling averages, and cooldowns

A single metric sample can be misleading. A short-lived CPU spike may disappear before a new instance becomes ready.

The Python, JavaScript, C++, and Java controllers retain recent samples and evaluate their average. They also require repeated threshold breaches before requesting a change.

A moving average reduces sensitivity to isolated observations, but it introduces delay. A large window can hide a rapid traffic increase. A small window reacts quickly but can produce unstable decisions when metrics are noisy.

Evaluation periods and cooldowns address different concerns:

- Evaluation periods determine whether the threshold condition has persisted for enough observations.
- Cooldowns limit repeated scaling actions after a change.
- Instance warm-up tracking identifies when new capacity becomes ready.
- Stabilization can use additional history to avoid reversing a recent decision too quickly.

Cooldowns alone do not guarantee stability. They may delay a necessary scale-out action during a sharp increase in demand. A controller must balance responsiveness with the cost of unnecessary changes.

## Python implementation

The Python script uses dataclasses and enums to represent metrics, instances, policies, and scaling events. Its `ScalingGroup` class owns the minimum, maximum, and desired capacity settings and reconciles the simulated instance collection against the desired target.

The `MetricWindow` class retains a bounded sequence of observations. It validates chronological ordering and computes averages for supported metric fields. This prevents a delayed metric from silently changing the intended time order of the controller's history.

The `AutoScaler` evaluates target-tracking conditions and uses separate counters for sustained high and low utilization. It records capacity changes and applies directional cooldowns. The step-policy method represents a separate policy mechanism rather than treating every policy as target tracking.

Instance lifecycle behavior is represented through pending or warming, in-service, unhealthy, and terminating states. The simulation distinguishes desired capacity from in-service capacity because a newly launched instance may require time to initialize.

The health replacement example removes a failed instance and reconciles the group against the unchanged desired capacity. The unit tests check capacity bounds, metric validation, warm-up transitions, scale-in protection, metric ordering, and cost calculations.

The cost calculation is deliberately illustrative. It estimates compute cost from instance count, hourly price, and elapsed hours. It does not include storage, networking, monitoring, discounts, taxes, or provider-specific billing rules.

Run the script with Python 3.10 or later:

    python autoscaling_lab.py

The script uses only the Python standard library. Its synthetic observations make the policy behavior reproducible without credentials or a monitoring service.

## JavaScript implementation

The JavaScript implementation emphasizes event-driven behavior. `MetricCollector` extends Node.js `EventEmitter` and emits validated metric objects as observations arrive. The scaling group emits capacity and instance lifecycle events so that monitoring and audit consumers can react independently of the scaling policy.

The collector accepts an asynchronous provider function. This models the separation between retrieving metrics and processing them without requiring a real monitoring API.

`ScalingGroup` uses a private `Map` to manage instance records and private fields to protect its desired-capacity state. The `snapshot()` method returns a read-only representation instead of exposing the internal collection directly.

`TargetTrackingPolicy` maintains a rolling metric window and separate breach counters. The scheduled policy sorts its actions by execution time and tracks which actions have already been applied. This prevents repeated evaluation of the same scheduled action from repeatedly applying the same capacity target.

The audit trail records ordered events with timestamps and event details. Such an audit record is useful for explaining why capacity changed, although a production audit system would need durable storage, access controls, and stronger guarantees against modification.

The simulation uses Node.js 18 or later:

    node autoscaling_lab.js

The JavaScript design is particularly useful for event-oriented controllers and services that process telemetry asynchronously. The code does not claim to reproduce the exact semantics of any cloud provider's scaling service.

## C++ case study

The C++ program models a payment API that must remain responsive during traffic increases while limiting unnecessary compute allocation.

Its `ScalingGroup` owns the capacity bounds, instance map, readiness transitions, protected-instance selection, and audit history. `ScalingController` owns metric-window evaluation and policy decisions. This separation prevents the policy algorithm from directly manipulating the internal instance collection.

The implementation uses a `std::map` keyed by instance ID for deterministic instance iteration, a `std::vector` for metric history and events, and `std::optional` to represent whether a previous metric timestamp exists.

The controller calculates average CPU over a bounded window. It uses explicit threshold bands, repeated breach counters, cooldown checks, and a bounded proportional adjustment. The group then clamps the desired capacity to the configured limits.

Health failure removes an unhealthy instance and restores the requested capacity through reconciliation. Scale-in protection prevents the protected instance from being selected for removal, although protection can leave actual capacity above the desired target when no eligible instance remains.

The program uses C++17 standard-library facilities only. Its data structures and algorithms are intentionally small enough to inspect while still modeling a complete control loop.

Compile and run:

    g++ -std=c++17 -Wall -Wextra -pedantic autoscaling.cpp -o autoscaling
    ./autoscaling

The program's cost estimate uses instance-hours and an illustrative hourly rate. It does not attempt to model real provider billing or distributed coordination.

## Java implementation

The Java program uses explicit domain types for metric names, policy kinds, scaling directions, instance states, and scaling events. These types make invalid combinations easier to detect and reduce dependence on ambiguous strings.

`MetricSample` validates its values at construction. `ScalingPolicy` validates target values, threshold ratios, step sizes, cooldown durations, and evaluation settings. The `ScalingGroup` encapsulates instance management and exposes synchronized operations for capacity changes and reconciliation.

Synchronization protects the in-memory simulation from conflicting operations within a single JVM. It does not coordinate multiple application processes, cloud controllers, or database transactions. A production implementation needs a distributed concurrency strategy.

`ScalingService` evaluates a policy independently of the group implementation. It uses a bounded metric window, counts consecutive threshold breaches, applies cooldowns, and submits a bounded capacity adjustment. The group remains responsible for enforcing capacity boundaries.

The scheduled-action record represents a distinct policy input. It requests a desired capacity at an explicit instant instead of waiting for a metric threshold. The health replacement operation preserves the group's requested capacity and records the failure event.

Compile and execute with Java 17 or later:

    javac AutoScalingEnterprise.java
    java AutoScalingEnterprise

The Java program illustrates an enterprise-oriented domain model. A real service would normally use stable provider instance identifiers, durable event storage, an external metrics adapter, and cloud API error handling.

## PostgreSQL data model

The SQL script represents the control plane relationally rather than storing the entire simulation as a single document.

### Relational entities

| Table | Purpose |
|---|---|
| `scaling_groups` | Stores group-level minimum, maximum, desired capacity, warm-up, and health-check timing. |
| `scaling_instances` | Records individual instances, readiness, health, launch time, and scale-in protection. |
| `scaling_policies` | Stores target-tracking, step-scaling, and scheduled-policy configuration. |
| `metric_samples` | Preserves timestamped CPU, request-rate, latency, and error-rate observations. |
| `scaling_evaluations` | Records the metric value, target, ratio, decision, and capacity values considered during evaluation. |
| `scheduled_scaling_actions` | Represents scheduled capacity targets and their execution state. |
| `scaling_events` | Stores capacity changes, health replacements, and reasons for decisions. |

Foreign keys connect policies, metrics, instances, and events to their owning scaling groups. Unique constraints prevent duplicate group names, policy names within a group, provider instance identifiers, and metric timestamps within a group.

Check constraints enforce local data rules, including valid capacity boundaries, non-negative resource measurements, valid threshold ratios, and consistent termination timestamps.

Indexes support common controller queries. The recent-metrics index supports time-ordered telemetry retrieval. The partial index on scale-in candidates excludes protected instances and states that should not be selected for ordinary termination.

### Rolling metrics and policy evaluation

The moving-average query uses a PostgreSQL window function over the most recent rows. This demonstrates how historical metric trends can be calculated directly from stored telemetry.

The target-tracking query compares the latest group-level CPU average with an enabled policy target. It returns a candidate decision rather than executing an infrastructure change automatically.

Keeping observation and action separate is important. A query that identifies a scale-out candidate does not itself prove that a capacity change is safe. A controller must still check cooldowns, evaluation history, current capacity, policy precedence, and available operational limits.

### Transactional capacity changes

The `request_capacity_change` function locks the relevant group row using `FOR UPDATE`. It then validates the requested change, clamps the result to the group's capacity bounds, updates desired capacity, and records an event within the calling transaction.

The row lock serializes conflicting updates to the same group when callers follow the same locking protocol. The transaction ensures that the desired-capacity update and its audit event commit or roll back together.

The function does not launch or terminate cloud instances. An external reconciliation worker would need to observe the updated desired capacity, call the relevant provider API, handle retries, and update instance state.

### Scheduled actions

The due-action query uses `FOR UPDATE SKIP LOCKED` to allow competing workers to claim separate scheduled-action rows. The example illustrates one part of a concurrent scheduler; production processing would also need transactional capacity changes, retry handling, and protection against a crash between execution and acknowledgment.

The schema stores an execution status and timestamp so operators can distinguish pending actions from completed actions. Additional operational metadata would be useful for recording rejection reasons and failed provider operations.

Run the script in a PostgreSQL development database. It drops and recreates the dedicated `autoscaling_lab` schema, so it should not be executed against an existing schema containing data that must be preserved.

## Desired capacity is not serving capacity

A critical operational distinction is that the requested capacity can differ from the number of healthy instances.

Suppose a group has a desired capacity of six. Two instances may be warming while four are already healthy. The controller has requested six instances, but only four may be able to serve production requests.

A system that evaluates utilization without accounting for warm-up can make repeated scale-out decisions before earlier instances become useful. That can produce unnecessary capacity growth.

The examples track warming and ready instances separately. Real infrastructure platforms may also report pending launches, draining instances, failed launches, or instances that are healthy at the compute layer but unable to serve application traffic.

Capacity reconciliation should account for those states explicitly.

## Health recovery and scale-in protection

Health recovery and metric-driven scaling are related but distinct operations.

A health replacement restores capacity lost through an instance failure. It does not necessarily indicate that workload demand increased. In the simulations, the failed instance is removed and a replacement is launched to restore the existing desired capacity.

Scale-in protection addresses a different risk: removing an instance that must remain available during a scale-in operation. Examples include instances processing work that cannot safely be interrupted or instances reserved for a controlled operational purpose.

Protection can prevent reconciliation from immediately reaching desired capacity. This is an intentional safety constraint, not a successful reduction in serving capacity. A production controller should surface this condition through metrics and events rather than repeatedly attempting an impossible scale-in without explanation.

## Failure conditions and production considerations

### Missing or invalid metrics

A controller should not interpret missing telemetry as zero utilization. Doing so can trigger unsafe scale-in actions during a monitoring outage.

Metric ingestion should validate value ranges, timestamps, duplicate observations, and data freshness. The examples reject malformed values and out-of-order samples. A production controller also needs an explicit stale-data policy and a safe response to missing measurements.

### Oscillation and excessive changes

Rapid alternation between scale-out and scale-in can increase costs, disrupt workloads, and make capacity unpredictable.

Separate threshold bands, moving averages, evaluation periods, cooldowns, and conservative scale-in steps reduce some sources of oscillation. They do not remove the need to evaluate the system's response time and actual workload characteristics.

### Startup time and sudden demand

Reactive scaling cannot eliminate the delay between detecting a workload increase and bringing additional instances into service.

Minimum capacity, scheduled preparation, workload queues, and predictive capacity planning can reduce the risk of running out of serving capacity before new instances are ready. The appropriate approach depends on whether the workload is interactive, queued, batch-oriented, or otherwise tolerant of delay.

### Capacity exhaustion

A group at maximum capacity cannot satisfy a request for further scale-out. The controller must make that condition visible.

Maximum capacity is also a cost and safety boundary. It should be chosen with workload limits, provider quotas, downstream capacity, and the consequences of overload in mind.

### Health checks and replacement storms

An incorrect health check can cause healthy instances to be marked unhealthy, creating repeated replacements and further service instability.

Health checks should reflect the intended failure domain. A failed downstream dependency should not automatically cause every application instance to be replaced unless the health policy explicitly requires that behavior.

### Security and operational control

A production scaling controller requires narrowly scoped permissions. It should be authorized to manage only the intended groups and operations, with audit events retained for review.

Monitoring endpoints and policy configuration should not be publicly writable. Untrusted metric input should be validated before it affects capacity decisions. Capacity limits should remain enforced even when an input is malformed or a policy behaves unexpectedly.

### Cost and performance

Scaling trades additional compute cost against throughput, latency, availability, and failure risk.

The sample cost calculations multiply instance-hours by an illustrative hourly rate. Actual cost analysis must include the relevant provider's billing granularity, instance types, discounts, storage, networking, observability, idle capacity, and any additional managed services.

A low average CPU value does not prove that scale-in is safe. Traffic bursts, uneven request distribution, background tasks, redundancy requirements, and downstream constraints can justify retaining more capacity than a CPU target alone suggests.

## Implementation distinctions

| Concern | Policy or mechanism responsible |
|---|---|
| Determining whether workload is above a target | Target-tracking policy |
| Mapping deviation severity to a fixed adjustment | Step-scaling policy |
| Preparing capacity at a known time | Scheduled scaling |
| Restricting capacity growth or reduction | Scaling-group bounds |
| Preventing reactions to a single short-lived observation | Metric windows and evaluation periods |
| Reducing repeated directional changes | Cooldowns and stabilization |
| Tracking whether newly launched capacity can serve traffic | Instance lifecycle and warm-up handling |
| Recovering from failed instances | Health detection and reconciliation |
| Preventing selected instances from being removed | Scale-in protection |
| Explaining why the controller acted | Scaling events and audit history |
| Preserving consistent capacity updates | Transactional state changes and concurrency controls |

These responsibilities should remain distinct even when a production platform implements several of them within a single managed service. A sound scaling system makes its observed inputs, policy decisions, capacity constraints, lifecycle state, and operational events independently understandable.
