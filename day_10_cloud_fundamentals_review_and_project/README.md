# Cloud fundamentals review and project

## Introduction

Cloud architecture is the structured design of computing resources, networks, storage systems, security controls, identities, applications, and operational services that work together to deliver a system.

A basic cloud architecture can be understood as a set of cooperating layers:

- Users and identities
- DNS and application entry points
- Networking
- Compute
- Databases and storage
- Security
- Monitoring and logging
- Backup and recovery
- Scaling and cost management

The Python script models these concepts without connecting to a real cloud provider. The implementation is intentionally provider-neutral so that the underlying architectural principles can be understood before mapping them to services from AWS, Microsoft Azure, Google Cloud, or another provider.

## Cloud computing fundamentals

Cloud computing provides computing resources through a network rather than requiring an organization to purchase and operate every physical server, storage device, and networking component itself.

Common cloud resources include:

- Virtual machines
- Containers
- Serverless compute
- Databases
- Object storage
- Block storage
- File storage
- Virtual networks
- Load balancers
- DNS
- Identity and access management
- Monitoring
- Logging
- Security services

### Elasticity

Elasticity is the ability to increase or decrease resources in response to changing demand.

For example, an application may run with two compute instances during normal traffic and temporarily increase to four instances during a period of high demand.

### Scalability

Scalability is the ability of a system to handle increased workload.

Two common forms are:

**Horizontal scaling**

More instances are added.

For example:

`2 servers -> 4 servers -> 8 servers`

**Vertical scaling**

An existing instance receives more resources.

For example:

`2 CPU / 4 GB RAM -> 4 CPU / 8 GB RAM`

Horizontal scaling is often useful for distributed applications because traffic can be spread across multiple instances.

### Availability

Availability describes whether a service can be accessed when required.

A system with multiple application instances in separate failure domains can remain available even if one instance or zone fails.

### Durability

Durability describes the likelihood that stored data remains intact over time.

Availability and durability are different properties. A storage service can be highly durable while still being temporarily inaccessible during an outage.

### Fault tolerance

Fault tolerance is the ability of a system to continue operating despite the failure of one or more components.

Fault tolerance requires deliberate architectural design. It does not automatically appear merely because a system is hosted in the cloud.

## Cloud service models

The script introduces three common service models.

### Infrastructure as a Service

Infrastructure as a Service, or IaaS, provides infrastructure such as virtual machines, storage, and networking.

The customer generally manages more of the operating system and application environment.

Typical responsibilities include:

- Operating system configuration
- Application installation
- Application security
- Network configuration
- Identity configuration
- Data management

The provider manages the physical infrastructure and underlying hardware.

### Platform as a Service

Platform as a Service, or PaaS, provides a managed application platform.

The provider manages more of the infrastructure and runtime environment, allowing developers to focus more heavily on application code and configuration.

### Software as a Service

Software as a Service, or SaaS, provides a complete application to users.

The provider manages the application and the underlying infrastructure.

The three models represent different responsibility boundaries. Moving from IaaS toward SaaS generally shifts more operational responsibility to the provider.

## Cloud deployment models

### Public cloud

Public cloud infrastructure is operated by a cloud provider and used by multiple customers through logical isolation.

### Private cloud

Private cloud infrastructure is dedicated to one organization.

### Hybrid cloud

Hybrid cloud combines public-cloud resources with private infrastructure.

### Multi-cloud

Multi-cloud uses services from multiple cloud providers.

Multi-cloud can provide flexibility but can also increase operational complexity because teams must understand multiple platforms, security models, networking models, APIs, and billing systems.

## Regions and availability zones

A cloud region represents a geographic area containing cloud infrastructure.

Availability zones represent separate infrastructure failure domains within a region.

The exact implementation differs by provider, but the architectural principle is important:

> Separating critical resources across failure domains can reduce the effect of localized infrastructure failure.

The script creates a region containing three availability zones and then simulates the failure of one zone.

A production architecture should not automatically assume that multiple zones solve every availability problem. Dependencies, databases, networking, deployment mechanisms, configuration, and external services can still create single points of failure.

## Users and identities

Users are the starting point of many application architectures.

A user might be:

- A human customer
- An administrator
- A developer
- A service account
- An application workload

Identity management determines who or what is interacting with the system.

The script represents users using a `User` class and associates them with roles.

## Authentication and authorization

Authentication and authorization are related but distinct.

### Authentication

Authentication answers:

> Who are you?

Examples include:

- Password authentication
- Multi-factor authentication
- Certificates
- Federated identity
- Single sign-on
- Workload identity

### Authorization

Authorization answers:

> What are you allowed to do?

For example, an ordinary application user might be allowed to read and update application data but not modify cloud infrastructure.

The script demonstrates this distinction through roles and permissions.

## Role-based access control

Role-based access control, or RBAC, assigns permissions to roles and assigns roles to users.

Instead of individually defining every permission for every user, an organization can define roles such as:

- Application user
- Developer
- Operations administrator
- Auditor

The script demonstrates two roles:

- `application-user`
- `operations-admin`

The application user has application permissions but cannot manage infrastructure.

The operations administrator has a broader set of permissions.

## Least privilege

Least privilege means providing only the access necessary to perform a task.

For example, an application that only needs to read objects from storage should not automatically receive permission to delete every object or modify the entire cloud account.

Least privilege reduces the potential impact of:

- Stolen credentials
- Compromised applications
- Human mistakes
- Malicious insiders
- Incorrect configurations

Permissions should be reviewed periodically because requirements change over time.

## Compute

Compute provides the processing capacity required to execute applications.

The script models compute instances using:

- CPU capacity
- Memory
- Availability zone
- Public or private network placement
- Health state

A basic application architecture uses multiple compute instances rather than relying on a single server.

This provides a foundation for:

- Load balancing
- Horizontal scaling
- Failure recovery
- Rolling deployments

## Public and private resources

One of the most important architectural decisions is determining which resources need direct public exposure.

A typical application design can use:

- Public load balancer
- Private application servers
- Private database
- Controlled storage access

The load balancer becomes the public entry point while internal components remain protected by network boundaries.

This is generally preferable to giving every application server a public IP address.

## Networking

Cloud networking provides logical communication boundaries.

Important networking concepts include:

- Virtual networks
- CIDR ranges
- Subnets
- Routing
- Internet gateways
- NAT
- Firewalls
- Security groups
- Network access controls
- Private connectivity
- DNS

The script models a virtual network using the address space:

`10.0.0.0/16`

It contains public and private subnet ranges.

## Subnets

A subnet divides a larger network into smaller logical sections.

The example architecture uses:

- Public subnets for internet-facing components
- Private subnets for internal application and database resources

Network segmentation provides a mechanism for controlling which components can communicate.

A private subnet does not automatically mean that a resource is secure. Security still depends on routing, firewall rules, identity controls, application security, encryption, configuration, and monitoring.

## Security groups and firewall rules

A security group or equivalent network control restricts permitted connections.

The example application security group allows HTTPS traffic from the internet.

Administrative SSH access is restricted to an administrative network rather than being opened universally.

The database security group permits database communication from the application layer rather than from the entire internet.

This demonstrates an important principle:

> Network access should be explicitly controlled according to legitimate communication requirements.

## DNS

The Domain Name System, or DNS, maps human-readable hostnames to destinations.

For example:

`app.example.com`

can resolve toward a public application entry point.

DNS separates the user-facing name from the underlying infrastructure.

This is useful because compute resources can change without requiring users to know their individual network addresses.

## Load balancing

A load balancer distributes requests across healthy application instances.

The script models two application servers:

- `web-app-1`
- `web-app-2`

The load balancer selects a healthy backend.

Load balancing can support:

- Horizontal scaling
- High availability
- Health checking
- Traffic distribution
- Rolling deployments
- Controlled application entry points

A load balancer does not automatically make an application highly available. The application instances and their dependencies must also be designed appropriately.

## Object storage

Object storage stores objects rather than exposing a traditional disk interface.

Typical use cases include:

- Images
- Videos
- Documents
- Static assets
- Backups
- Data exports
- Logs
- Large files

The script creates an object-storage bucket containing example objects.

It also demonstrates:

- Encryption
- Versioning
- Object deletion
- Total stored size

Object storage is particularly useful when applications need durable storage for files that do not belong naturally inside a relational database.

## Block storage

Block storage behaves more like a disk attached to a compute resource.

Common uses include:

- Operating system disks
- Application disks
- Database storage
- High-performance workloads

The script represents block volumes using a size and encryption property.

Block storage and object storage should not be treated as interchangeable technologies. Their access models and typical workloads are different.

## File storage

File storage provides a shared file-system-style interface.

It can be appropriate when multiple systems need access to shared directories or files.

The choice between object, block, and file storage depends on:

- Access pattern
- Latency
- Sharing requirements
- Performance
- Capacity
- Durability
- Cost
- Application compatibility

## Database layer

The script models a private relational database.

The database is configured with:

- Private network placement
- Encryption
- Health status
- Structured records

The application can write records when the database is healthy.

The database is deliberately not exposed directly to the internet.

A real database architecture may also require:

- Replication
- Automated backups
- Point-in-time recovery
- Connection pooling
- Indexing
- Query optimization
- Monitoring
- Failover
- Maintenance windows
- Capacity management

## Encryption

Encryption protects information by transforming readable data into a form that requires an appropriate key to recover.

Two important categories are:

### Encryption at rest

Protects stored data.

Examples include:

- Database storage
- Object storage
- Block volumes
- Backups

### Encryption in transit

Protects data while it moves between systems.

HTTPS and TLS are common examples.

Using encryption at rest does not eliminate the need for encryption in transit, and encryption in transit does not replace appropriate access control.

## Secret management

Secrets include:

- Passwords
- API keys
- Access tokens
- Private keys
- Database credentials

The script uses a `SecretReference` object to demonstrate safe representation of a secret.

Production systems should not hard-code secrets in source code.

A dedicated secret-management mechanism should be used where appropriate, combined with:

- Access control
- Rotation
- Auditing
- Limited exposure
- Secure application retrieval

Logs should also be checked to ensure secrets are not accidentally printed.

## Security architecture

Cloud security should be layered.

Important security controls include:

- Identity and access management
- Authentication
- Authorization
- Multi-factor authentication
- Least privilege
- Network segmentation
- Security groups
- HTTPS
- Encryption
- Secret management
- Logging
- Monitoring
- Backups
- Vulnerability management
- Configuration validation

No single security control should be considered sufficient by itself.

## Threat modeling

Threat modeling identifies potential threats, affected components, possible impact, and mitigations.

The script demonstrates several threats.

### Unauthorized access

Potential impact:

- Data exposure
- Unauthorized changes
- Resource misuse

Controls include authentication, MFA, RBAC, and least privilege.

### Open administrative ports

An administrative service exposed to the entire internet creates unnecessary attack surface.

A safer design restricts management access to appropriate networks or controlled administrative mechanisms.

### Data interception

Unencrypted traffic can expose sensitive information.

TLS helps protect information while it moves between systems.

### Accidental deletion

Versioning, backups, retention policies, and recovery mechanisms reduce the impact of accidental deletion.

### Credential leakage

Credentials embedded in source code can be exposed through:

- Public repositories
- Logs
- Build artifacts
- Screenshots
- Error messages

Secrets should be managed separately from ordinary application source code.

## Monitoring and logging

Monitoring provides measurable information about system behavior.

The script models metrics such as:

- CPU utilization
- Request latency

It also models log events such as:

- Application startup
- Database connection errors

### Metrics

Metrics are numerical measurements.

Examples:

`CPU utilization = 48%`

`Request latency = 120 ms`

### Logs

Logs contain event information.

Examples:

- Application started
- User authentication failed
- Database connection timed out
- Configuration changed

### Alerting

Monitoring becomes operationally useful when thresholds or other detection mechanisms generate alerts.

The script demonstrates a high-CPU alert.

Real systems may monitor:

- Error rate
- Latency
- CPU
- Memory
- Disk utilization
- Network throughput
- Database connections
- Queue depth
- Availability
- Authentication failures

## Backups and disaster recovery

Backups provide a mechanism for recovering data after certain failures.

A backup strategy should consider:

- Frequency
- Retention
- Storage location
- Encryption
- Access controls
- Restoration procedures
- Cross-zone copies
- Cross-region copies

The script models a daily backup policy with 30-day retention and cross-zone and cross-region copies.

The correct configuration depends on application requirements and recovery objectives.

## RPO and RTO

### Recovery Point Objective

RPO defines how much data loss is acceptable.

For example, an RPO of one hour means the organization may accept losing up to approximately one hour of recent data in a particular disaster scenario.

### Recovery Time Objective

RTO defines how quickly a service should be restored after a failure.

RPO concerns data loss.

RTO concerns recovery time.

These objectives influence architecture, replication, backup frequency, automation, and cost.

## High availability

High availability attempts to reduce service interruption.

The example architecture uses multiple application instances in different availability zones.

If one instance fails, the load balancer can continue sending traffic to another healthy instance.

The script explicitly simulates this failure.

This demonstrates why redundancy matters.

## Single points of failure

A single point of failure is a component whose failure can cause the entire service to become unavailable.

Examples include:

- One application server
- One database instance without appropriate failover
- One network component
- One critical dependency
- One authentication dependency
- One manually maintained server

Removing one single point of failure does not guarantee complete resilience because dependencies can introduce additional failure points.

## Scalability

The script demonstrates a simplified auto-scaling model.

The scaling policy uses:

- Minimum instances
- Maximum instances
- Current instance count
- Target CPU utilization

When observed CPU increases significantly, the example adds an instance.

When utilization falls significantly, it removes one while respecting the configured minimum.

Real auto-scaling systems are more sophisticated and may use:

- CPU
- Memory
- Request count
- Queue depth
- Latency
- Custom application metrics
- Scheduled scaling
- Predictive signals

## Capacity planning

Capacity planning estimates how much infrastructure is required for expected workload.

The script includes a simplified calculation based on:

- Requests per second
- Capacity per instance
- Safety factor

For example, if traffic is expected to reach 450 requests per second and one instance is estimated to handle 100 requests per second, a safety factor can be applied before calculating the number of instances.

This is only an educational model.

Production capacity planning should be based on:

- Load testing
- Real performance measurements
- CPU behavior
- Memory behavior
- Database capacity
- Network capacity
- Dependency limits
- Failure scenarios
- Peak traffic

## Performance considerations

Cloud performance depends on many components.

Important factors include:

- Network latency
- Geographic distance
- Compute capacity
- Database queries
- Storage access
- Application code
- Concurrency
- Connection management
- Caching

The script models component latency and calculates an average.

Averages are useful but insufficient for serious performance analysis. Production systems often examine percentile measurements such as p50, p95, and p99 because a small number of very slow requests can be hidden by an average.

## Caching

Caching stores frequently accessed information closer to the point of use.

Potential benefits include:

- Lower latency
- Reduced database load
- Lower repeated computation
- Improved throughput

Caching introduces additional design questions:

- When should data expire?
- How is stale data handled?
- How is cache invalidation performed?
- What happens when the cache fails?
- How much memory is required?

The script demonstrates a simple in-memory cache.

## Stateful and stateless applications

A stateless application does not depend on a particular application server retaining important user state locally.

This makes it easier to distribute requests across multiple instances.

A stateful application maintains important state within an individual instance.

This can make:

- Load balancing
- Scaling
- Failover
- Instance replacement

more complicated.

A common cloud architecture pattern is to move shared state into appropriate external services such as databases, caches, or object storage.

This does not mean every application should be forced to be completely stateless. The correct design depends on requirements.

## Managed services versus self-managed infrastructure

Managed services transfer many operational responsibilities to the cloud provider.

Benefits can include:

- Reduced infrastructure administration
- Automated maintenance
- Simplified scaling
- Integrated monitoring
- Managed backups

Trade-offs can include:

- Less low-level control
- Provider-specific behavior
- Service limitations
- Different pricing models
- Potential migration complexity

Self-managed infrastructure provides greater control but requires the organization to manage more of:

- Patching
- Scaling
- Security
- Availability
- Monitoring
- Backups
- Capacity
- Operational procedures

## Cost considerations

Cloud architecture is not only a technical problem. It is also a financial design problem.

The script models five simplified cost categories:

- Compute
- Storage
- Network
- Database
- Monitoring

The actual price of a cloud environment depends on many factors, including:

- Provider
- Region
- Resource size
- Resource count
- Usage duration
- Storage capacity
- Data transfer
- API requests
- Database capacity
- Monitoring volume
- Reserved or committed pricing
- Discounts

Cost optimization should not simply mean choosing the cheapest resource. A cheaper resource that causes poor availability or performance can increase the total cost of operating the system.

## Cost control

Useful cost controls include:

- Resource tagging
- Budgets
- Billing alerts
- Usage monitoring
- Automatic shutdown of unnecessary development resources
- Right-sizing
- Storage lifecycle policies
- Removal of unused resources
- Capacity limits
- Review of network transfer
- Review of managed-service usage

## Infrastructure as Code

Infrastructure as Code, or IaC, represents infrastructure configuration in machine-readable definitions.

The script models resources using `ResourceDefinition`.

Example conceptual resources include:

- Network
- Load balancer
- Compute
- Database
- Object storage

IaC can improve:

- Repeatability
- Version control
- Auditability
- Reviewability
- Environment consistency
- Automation
- Disaster recovery

Infrastructure should be treated as a reproducible system rather than a collection of undocumented manual changes.

## Configuration drift

Configuration drift occurs when actual infrastructure differs from the intended configuration.

The script compares desired and actual configuration.

For example:

Desired:

`database_encrypted = True`

Actual:

`database_encrypted = False`

This is an important finding because encryption requirements are part of the architecture's security posture.

Configuration drift can occur through:

- Manual changes
- Emergency fixes
- Incomplete automation
- Different deployment processes
- Changes made outside infrastructure management tools

Regular validation can help detect drift.

## Architecture validation

The script contains an `Architecture` class with a validation method.

It checks properties such as:

- Users exist
- Multiple compute instances exist
- Public subnets exist
- Private subnets exist
- Database is private
- Database is encrypted
- Object storage is encrypted
- Object storage versioning is enabled
- Security groups exist
- Monitoring exists
- At least one backend is healthy

This represents an important engineering practice: architecture requirements should be converted into testable conditions where practical.

## Architecture testing

The script also creates lightweight architecture tests.

Tests verify requirements such as:

- Multiple application instances
- Private database
- Encryption
- Storage versioning
- Network segmentation
- Load-balancer health
- Monitoring configuration

Real cloud environments can extend this concept through automated policy checks, infrastructure validation, integration testing, security testing, and deployment pipelines.

## Failure simulation

The script simulates several failures.

### Application server failure

One compute instance is marked unhealthy.

The load balancer continues using the remaining healthy instance.

This demonstrates the value of redundancy.

### Complete application failure

All application instances are marked unhealthy.

The architecture can no longer serve requests.

This demonstrates that two servers do not provide infinite resilience.

### Database failure

The database is marked unhealthy.

A database write raises an error instead of silently succeeding.

This illustrates that application availability depends on dependencies as well as application servers.

## Basic cloud architecture

The project architecture can be represented conceptually as:

Users

↓

DNS

↓

Public load balancer

↓

Private application servers

↓

Private database

↓

Encrypted object storage

Supporting all layers are:

- Identity and access management
- Role-based authorization
- Least privilege
- Network security
- Encryption
- Secret management
- Monitoring
- Logging
- Backups
- Scaling
- Configuration validation

## End-to-end request flow

A typical request follows this logical sequence:

1. A user sends an HTTPS request.
2. DNS resolves the application hostname.
3. DNS directs the request toward the public load balancer.
4. The load balancer selects a healthy application server.
5. The application authenticates and authorizes the user.
6. The application communicates with the private database when required.
7. The application accesses object storage when files are required.
8. Monitoring systems collect operational information.
9. The response is returned to the user.

The important architectural idea is that users do not need direct access to every internal component.

## Public versus private placement

A common baseline design is:

| Component | Typical placement | Reason |
|---|---|---|
| DNS | Public service | Users need to locate the application |
| Load balancer | Public | Receives controlled external traffic |
| Application servers | Private | Reduces direct internet exposure |
| Database | Private | Prevents unnecessary public database access |
| Object storage | Access controlled | Public access should exist only when required |
| Management systems | Restricted | Limits administrative attack surface |

The exact placement depends on application requirements.

## Common mistakes

### Public database

A database directly accessible from the internet creates unnecessary attack surface.

### Single application server

One failed server can make the application unavailable.

### Hard-coded credentials

Credentials in source code can be leaked through repositories, logs, or build artifacts.

### Excessive permissions

Broad permissions increase the potential impact of compromised identities.

### Open network ports

Allowing unnecessary ports increases attack surface.

### No backups

Data loss becomes significantly harder to recover from.

### No monitoring

Operational problems may remain undetected.

### No cost controls

Unexpected scaling, storage growth, or data transfer can increase costs.

### No failure testing

An architecture that looks resilient on paper may fail differently in practice.

## Important distinctions

### Scalability versus elasticity

Scalability describes the ability to handle growth.

Elasticity describes the ability to dynamically adjust resources as demand changes.

### Availability versus durability

Availability concerns access.

Durability concerns preservation of data.

### Authentication versus authorization

Authentication identifies the user or workload.

Authorization determines permitted actions.

### Horizontal versus vertical scaling

Horizontal scaling adds instances.

Vertical scaling increases the capacity of existing instances.

### Object versus block storage

Object storage manages independent objects.

Block storage behaves more like a disk.

### Backup versus high availability

High availability attempts to keep services operating during failures.

Backups provide recovery from data loss and other recovery scenarios.

They solve different problems and are often required together.

## Security considerations

A production-oriented cloud architecture should consider at least:

- Strong identity controls
- Multi-factor authentication
- Least privilege
- Private network placement
- Secure network rules
- HTTPS/TLS
- Encryption at rest
- Encryption in transit
- Secret management
- Credential rotation
- Logging
- Monitoring
- Auditability
- Backup protection
- Vulnerability management
- Secure configuration
- Incident response
- Dependency security

Security should be treated as an architectural property rather than as a final configuration step.

## Implementation considerations

The Python implementation is intentionally simplified.

It uses classes to represent cloud concepts such as:

- `CloudRegion`
- `ComputeInstance`
- `ObjectStorageBucket`
- `BlockStorageVolume`
- `VirtualNetwork`
- `SecurityGroup`
- `LoadBalancer`
- `Database`
- `User`
- `Role`
- `IdentityManager`
- `MonitoringSystem`
- `Architecture`

These classes are not cloud-provider SDKs. They are educational abstractions.

For example, a real load balancer has substantially more functionality than the `LoadBalancer` class in the script. A real cloud network includes routing tables, gateways, network interfaces, address allocation, DNS behavior, security controls, and provider-specific implementation details.

The abstractions are useful because they focus attention on the architectural relationship between components.

## Edge cases and validation

The script deliberately handles invalid conditions.

Examples include:

- Negative object size
- Zero-sized block storage
- Invalid capacity calculations
- Empty performance observations
- No healthy application backend
- Database failure
- Missing network segments
- Missing encryption
- Missing monitoring

Explicit validation is especially important for infrastructure because configuration mistakes can affect:

- Security
- Availability
- Data integrity
- Performance
- Cost

## Performance considerations

Cloud architecture performance should be evaluated using measurements rather than assumptions.

Important measurements include:

- Request latency
- Error rate
- Throughput
- CPU utilization
- Memory utilization
- Database latency
- Storage latency
- Network latency
- Queue depth
- Concurrent requests

Capacity planning should also consider peak traffic rather than only average traffic.

## Production considerations

A production architecture generally requires more than the basic model demonstrated in the script.

Important areas include:

- Multiple failure domains
- Automated deployment
- Infrastructure as Code
- Secure identity management
- Secret rotation
- Backup verification
- Disaster recovery
- Monitoring and alerting
- Log retention
- Audit trails
- Vulnerability management
- Patch management
- Incident response
- Cost controls
- Capacity planning
- Performance testing
- Failure testing
- Configuration compliance
- Change management

The exact implementation depends on application requirements, risk tolerance, regulatory requirements, expected workload, recovery objectives, and budget.

## Practical applications

The architecture principles demonstrated by the project can apply to many systems, including:

- Web applications
- E-commerce platforms
- Internal business applications
- Learning platforms
- Mobile application backends
- SaaS products
- Document management systems
- Data processing applications
- APIs
- Customer portals
- Business dashboards

A typical web application can use the same general structure:

User → DNS → Load Balancer → Application → Database/Object Storage

The actual services and topology will vary according to the workload.

## Architecture design process

A systematic cloud architecture design process can follow these stages:

1. Identify users and requirements.
2. Identify application workloads.
3. Identify application dependencies.
4. Select an appropriate service model.
5. Select the deployment model.
6. Select the region and failure domains.
7. Design the network.
8. Define public and private boundaries.
9. Select compute resources.
10. Select storage and database technologies.
11. Design identity and authorization.
12. Apply least privilege.
13. Protect data with encryption.
14. Design monitoring and logging.
15. Define backup and recovery objectives.
16. Design scaling behavior.
17. Estimate costs.
18. Identify security threats.
19. Identify failure scenarios.
20. Validate the architecture.
21. Automate repeatable infrastructure.
22. Test normal and failure conditions.

## Architecture trade-offs

Cloud architecture involves trade-offs rather than universally correct choices.

| Objective | Common approach | Trade-off |
|---|---|---|
| Higher availability | Multiple instances and zones | Higher cost and complexity |
| Lower latency | Caching and geographic placement | More components and consistency concerns |
| Lower operational effort | Managed services | Less low-level control |
| Greater infrastructure control | Self-managed systems | More operational responsibility |
| Stronger recovery | Replication and additional backups | Higher cost |
| Broader network access | More permissive rules | Larger attack surface |
| Greater performance | Larger or additional resources | Higher infrastructure cost |

Good architecture decisions are based on requirements and measured constraints.

## Project architecture review

The final project combines:

- Users
- Identity
- DNS
- Load balancing
- Compute
- Networking
- Database
- Object storage
- Security groups
- Encryption
- Monitoring
- Logging
- Backups
- Scaling
- Failure simulation
- Architecture validation
- Infrastructure as Code concepts
- Configuration drift detection
- Cost modeling

The resulting architecture establishes a practical foundation for understanding how major cloud components cooperate in a real application environment.
