# Cloud Virtual Machine Deployment and Lifecycle Governance

## Scope

A cloud virtual machine (VM) is a compute resource provisioned from an operating-system image and a selected machine configuration. Its operation depends on more than creating an instance: image provenance determines what software is installed, SSH key registration establishes an administrative authentication mechanism, security groups govern network reachability, and lifecycle controls determine when the resource can run, stop, restart, fail, or terminate.

This repository models those mechanisms through five executable implementations. The Python program provides a compact infrastructure simulator. JavaScript models an event-driven provisioning service. C++ implements a repository-independent deployment governance engine using explicit policy checks and lifecycle transitions. Java models an enterprise provisioning service with immutable domain records and policy objects. PostgreSQL stores deployment metadata, enforces relational integrity, and audits lifecycle changes.

All examples are simulations. They do not create cloud resources, contact a provider API, generate usable private keys, or allocate real public IP addresses.

## Deployment architecture

The deployment workflow connects resource selection, security configuration, provisioning, operational validation, and decommissioning.

    Deployment request
           |
           v
    Select region and machine type
           |
           v
    Validate image and architecture
           |
           v
    Register SSH public key
           |
           v
    Validate security-group rules
           |
           v
    Apply storage and cost policies
           |
           v
    Create instance in pending state
           |
           v
    Provision and check boot health
           |
           +---- failure ----> failed
           |
           v
         running
           |
           +---- stop --------> stopped
           |                       |
           |                       +---- start ----> running
           |
           +---- terminate -----------------------> terminated

The diagram describes the modeled workflow, not a universal provider API. Real providers may expose additional transitional states, asynchronous operations, separate storage resources, and distinct termination semantics.

## Images and machine compatibility

An image defines the initial operating-system filesystem and boot environment. The image record in these examples includes a publisher, version, architecture, availability status, trust designation, and minimum disk requirement.

An image marked `available` is not automatically trustworthy. Image selection should also account for its publisher, signature or provenance verification, supported architecture, maintenance status, and organizational approval. The examples distinguish deprecated images from untrusted images because those conditions represent different governance failures.

Machine architecture is validated independently of image availability. An x86-64 image cannot be assumed to boot on an ARM64 machine type. Disk sizing is checked against both the image minimum and the deployment policy minimum.

The Python and Java implementations make image validation an operation on the image object. The C++ governance engine checks the image and machine records before inserting an instance. The PostgreSQL function joins image and machine metadata through explicit identifiers and rejects unavailable images, incompatible architectures, and undersized root disks.

A production deployment system should identify images by immutable image identifiers rather than relying solely on a human-readable label such as `Ubuntu`. It should also define how image deprecation affects already-running instances, replacement deployments, and recovery procedures.

## SSH key registration and authentication

SSH key-based administration uses a public/private key pair. The cloud control plane generally receives the public key or a reference to a previously registered key. The administrator retains the private key and uses it during SSH authentication.

The programs validate a public-key format and retain a fingerprint or registration identifier. They do not create a real key pair or prove that a private key is available. The example public-key strings are demonstration data and must not be treated as usable credentials.

The private key should not be embedded in source code, instance metadata, audit messages, deployment logs, or database records. Production systems should apply appropriate file permissions, credential rotation, access revocation, and secret-management practices. A public-key fingerprint helps identify a registration but is not proof of ownership or authorization by itself.

The Python implementation computes a SHA-256 fingerprint from the decoded public-key payload. JavaScript demonstrates Node.js hashing and stores the resulting fingerprint instead of requiring the deployment service to retain private key material. The Java model separates key metadata into an immutable record. PostgreSQL records the public key, algorithm, owner, fingerprint, and enabled status, with a uniqueness constraint on fingerprints.

Actual cloud providers differ in how keys are registered, injected, associated with instances, and removed. Some image and access-management configurations require additional steps to enable SSH login.

## Security groups and network exposure

A security group is a network access policy associated with a cloud resource or network interface. Inbound rules commonly specify a protocol, port range, and source address range. Outbound rules control permitted destinations or traffic, depending on the provider's network model.

An SSH rule should normally restrict TCP port 22 to a known administrative network, VPN, bastion host, or other approved access path. Public web traffic may require TCP port 443 to be reachable from the internet. Those rules serve different operational purposes and should not be combined into a single broad port range.

The examples distinguish network reachability from identity authentication. Allowing a source address through a security group does not establish that the connecting user possesses an authorized private key. Conversely, possessing an SSH private key does not override a network rule that blocks the connection.

The Python security-group model evaluates a source IP against a CIDR range. The JavaScript implementation includes a small IPv4 CIDR parser and membership check for its demonstration. The Java model deliberately uses exact CIDR matching for rule evaluation and does not claim to implement general CIDR containment. The C++ case study uses explicitly registered address entries rather than a partial network parser. PostgreSQL uses its native `CIDR` and `INET` types and the `<<=` containment operator.

These differences matter: a simplified parser or exact-string comparison is not a substitute for a complete, provider-compatible network policy engine. A production implementation should support IPv4 and IPv6 as required, validate protocol-specific rules, evaluate effective ingress and egress behavior, and test default-rule behavior.

## Instance creation and provisioning failure

Instance creation begins with a configuration containing the target region, image, machine type, SSH key, security group, disk size, and organizational metadata. Each implementation verifies references before accepting the deployment.

The instance initially enters `pending`. A successful simulated boot transitions it to `running`; a simulated initialization or health-check failure moves it to `failed`. This separation matters because an accepted creation request is not equivalent to a healthy operating system or a working application.

The Python script creates a VM object, validates its dependencies, records an audit event, and handles a simulated boot failure. The JavaScript service uses asynchronous execution and `EventEmitter` notifications to separate provisioning logic from event consumers. The C++ engine uses a central validation method to reject policy violations before storing the resource. Java applies the same architectural separation through `DeploymentService`, `DeploymentPolicy`, and `VirtualMachine`.

The PostgreSQL function `deploy_virtual_machine` centralizes database-level checks and inserts the initial `pending` record. Its transaction ensures that a failed insert or constraint check does not leave a partially committed deployment row. A real infrastructure workflow would additionally need an external provider operation, retry policy, idempotency key, reconciliation process, and a mechanism to resolve cases in which the provider succeeds but the application fails to persist the result.

## Lifecycle state and termination semantics

The implementations use the following lifecycle model.

| State | Meaning in this repository |
|---|---|
| `pending` | Creation has been accepted, but provisioning is incomplete. |
| `running` | The simulated VM is operational. |
| `stopped` | Compute execution has stopped, and the modeled public address is cleared. |
| `failed` | Provisioning or operation has failed and requires investigation or decommissioning. |
| `terminated` | The instance has been decommissioned and cannot restart. |

The permitted transitions are explicit. A running instance may stop, fail, or terminate. A stopped instance may restart or terminate. A failed instance may terminate. A terminated instance cannot transition back to a running state.

These rules prevent invalid operations from silently changing a resource's status. They also distinguish stopping from termination. In real cloud environments, stopping a VM often preserves its root disk and instance configuration, while termination may delete compute resources and may or may not delete attached storage depending on provider settings. Static public addresses, reserved IP resources, snapshots, and external volumes can have independent lifecycles.

The Python and JavaScript implementations reject invalid state transitions through custom exceptions. The C++ engine checks transitions through a central function. Java uses an immutable transition map and records each state change. PostgreSQL enforces transitions with a trigger and rejects a direct regression from `running` to `pending`.

The database trigger also stamps the termination time and clears the modeled public IP. These actions are simulation rules rather than universal cloud-provider guarantees.

## Python implementation

The Python script is a standard-library-only deployment simulator. `Image`, `SSHKey`, `SecurityRule`, `SecurityGroup`, `MachineType`, and `VirtualMachine` represent distinct resource types.

`CloudSimulator` owns resource registries and coordinates provisioning. The `create_instance` method checks names, region syntax, disk bounds, image compatibility, key registration, security-group existence, and duplicate active names. A boot failure is captured as a failed lifecycle state instead of being reported as a successful deployment.

The audit model stores structured events with timestamps, state information, and event details. The optional `--export-audit` argument writes the event history to a JSON file. This makes the simulated record usable for later inspection without creating a file during an ordinary demonstration.

The cost estimate multiplies hourly compute cost by a supplied number of hours, using 730 hours as a simplified monthly period. It deliberately excludes storage, network transfer, public IP charges, discounts, taxes, and provider-specific billing rules.

The script also illustrates two important limitations. Its documentation-only IP addresses do not identify reachable machines, and the public-key parser checks structure rather than cryptographic trust or login functionality.

Run the program with Python 3.10 or later:

    python cloud_vm_deployment.py

To export the simulated audit log:

    python cloud_vm_deployment.py --export-audit

## JavaScript implementation

The JavaScript file models deployment as an event-driven service. `CloudDeploymentService` owns resource registries, validates requests, and creates virtual machines. `VirtualMachine` extends `EventEmitter` so state changes can be consumed independently of the lifecycle implementation.

This design allows audit processing and operational notifications to subscribe to state changes rather than being tightly coupled to every provisioning method. The audit log records state, revision, action, and structured details.

The `create` and `start` methods are asynchronous. They use a scheduled event-loop callback to represent a boundary between request acceptance and completion. This is a local simulation, not an actual network request or a provider's eventual-consistency guarantee.

The CIDR helper converts IPv4 addresses to unsigned 32-bit values and applies a prefix mask. It supports the IPv4 examples in the program and rejects malformed CIDR input. It is not a general replacement for a mature IP-address library, particularly where IPv6 or provider-specific rule semantics are required.

Run it with Node.js 18 or later:

    node cloud-vm-deployment.js

## C++ governance case study

The C++ program represents a platform engineering service that provisions staging workloads under centrally defined governance rules.

`GovernanceEngine` stores approved images, machine types, SSH key registrations, security groups, and instances in associative containers. Deployment validation occurs before the instance is inserted. The policy requires a trusted, non-deprecated image, compatible machine architecture, a registered key, restricted SSH access, encrypted root storage, a minimum disk size, and a machine price below the configured ceiling.

The `Instance` structure holds the resource configuration, lifecycle state, optional public address, and audit history. Lifecycle transitions are centralized so that stop, restart, failure, and termination operations cannot bypass the state machine.

The security-group representation intentionally uses exact administrator-address entries rather than attempting to implement an incomplete CIDR parser. This makes the limitation explicit while keeping the policy behavior testable.

The cost estimator performs constant-time arithmetic for a requested duration. Resource lookup in the `std::map` registries takes logarithmic time in the number of registered entries, while duplicate-name detection scans existing instances and takes linear time. A production implementation with a large resource inventory would benefit from a secondary index for active instance names.

Compile with a C++17-compatible compiler:

    g++ -std=c++17 -Wall -Wextra -pedantic cloud_vm_deployment.cpp -o cloud_vm_deployment

Run the executable:

    ./cloud_vm_deployment

On Windows, run the resulting `cloud_vm_deployment.exe` from PowerShell.

## Java enterprise model

The Java implementation separates immutable resource metadata from mutable lifecycle state. Records represent images, machine types, SSH keys, inbound rules, deployment policies, and audit events. Constructor validation rejects malformed domain objects before they reach the deployment service.

`DeploymentService` resolves resource references, evaluates enterprise policy, rejects duplicate active names, and creates the VM object. `VirtualMachine` controls its own lifecycle transitions and produces timestamped audit events. Callers cannot directly assign an arbitrary lifecycle state through a public setter.

The enterprise policy includes a minimum disk size, maximum hourly compute cost, encrypted-storage requirement, trusted-image requirement, and restricted SSH requirement. These controls complement resource validation: a machine can be technically compatible with an image but still violate the organization's cost or storage policy.

The program uses defensive copies for tags, immutable collections for rule lists, and a transition map that prevents illegal state changes. Its audit list is exposed as a copy, preventing callers from modifying the stored event history through the returned collection.

Compile and run with Java 17 or later:

    javac CloudVmDeployment.java
    java CloudVmDeployment

The sample public key and fingerprint are illustrative metadata. They do not establish that a corresponding private key exists or that authentication would succeed against a real VM.

## PostgreSQL relational model

The SQL script defines a `cloud_ops` schema with relational tables for regions, machine types, images, SSH keys, security groups, security-group rules, deployment policies, virtual machines, state events, and health checks.

The foreign keys ensure that a VM references registered infrastructure metadata. Unique constraints prevent duplicate identifiers and key fingerprints. Check constraints validate machine capacity, root-disk bounds, key metadata, tag structure, and lifecycle termination timestamps.

A partial unique index on `(region_code, instance_name)` prevents duplicate names among non-terminated instances while permitting name reuse after termination. The state-and-region index supports operational inventory queries, the JSONB GIN index supports tag-based filtering, and the event index supports recent history retrieval for a given instance.

The `deploy_virtual_machine` function centralizes image availability, trust, architecture, region, key, security group, disk, encryption, and cost checks before inserting a pending instance. The lifecycle trigger restricts legal state transitions and clears the simulated public IP when termination occurs. An audit trigger records creation and state changes.

The `security_group_allows` function evaluates whether an address falls within a configured network range using PostgreSQL's native network operators. This is more reliable for CIDR membership than comparing arbitrary IP strings.

The sample workflow provisions a staging VM, simulates successful health checks, stops and restarts the VM, queries estimated compute cost, inspects audit records, detects unsafe network configuration, and terminates the instance. An inner exception block demonstrates rejection of an illegal lifecycle transition without aborting the entire demonstration transaction.

Run the script in a PostgreSQL database using a role with permission to create a schema, types, functions, tables, and triggers. The script uses `gen_random_uuid()`, which is available in current PostgreSQL releases.

The SQL checks are a useful database enforcement layer, not a complete cloud security boundary. Real deployments also require appropriately scoped database permissions, operational controls around policy changes, concurrency-safe allocation, provider-side policy enforcement, and reconciliation between database state and actual infrastructure.

## Cost and operational accounting

The compute estimate in the implementations uses the following simplified relationship:

\[
\text{Estimated compute cost} =
\text{Hourly compute rate} \times \text{Billable hours}
\]

A stopped instance returns zero simulated compute cost. This assumption does not imply that a real stopped VM is free: persistent disks, snapshots, reserved addresses, licensed images, and other attached resources can continue to incur charges.

Production cost controls should evaluate expected runtime, machine size, storage capacity, network egress, region-specific pricing, discounts, and resource commitments. The enterprise policy examples reject machine types above a configured hourly rate before creation.

Lifecycle auditing should preserve who requested an operation, the prior and resulting states, timestamps, the operation's outcome, and a correlation identifier. Audit records should not include private keys, passwords, access tokens, or other secrets.

## Failure analysis and production boundaries

A deployment service must distinguish invalid requests from failures that occur after the request has been accepted.

Configuration failures include unavailable images, architecture mismatches, unknown key registrations, overly permissive network rules, undersized disks, and policy violations. These should be rejected before expensive provisioning begins.

Operational failures include boot errors, initialization failures, unsuccessful health checks, API timeouts, and inconsistent provider responses. They require explicit error classification and a recovery policy. A timeout does not necessarily mean that a provider operation failed; the resource may have been created even though the caller did not receive confirmation.

The examples model boot failure and illegal lifecycle transitions. A production controller should also use idempotent operation identifiers, retry only safe operations, reconcile actual provider state with stored state, and protect concurrent updates through optimistic locking or transactional coordination.

The database schema records infrastructure metadata and policy outcomes, but it does not prove that a public address is reachable, that an operating system has completed initialization, or that an SSH session can authenticate. Those facts require provider API observations, network tests, and application-level health checks.

Security-group changes, SSH key revocation, image replacement, disk resizing, backups, and deletion of attached storage also need explicit workflows. These operations have different effects and should not be hidden behind a generic instance-state update.
