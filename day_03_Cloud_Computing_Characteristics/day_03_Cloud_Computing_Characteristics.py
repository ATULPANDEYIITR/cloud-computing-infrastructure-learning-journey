"""
================================================================================
CLOUD COMPUTING CHARACTERISTICS
================================================================================

Topic:
    On-demand self-service
    Broad network access
    Resource pooling
    Rapid elasticity
    Measured service
    Multi-tenancy
    Cloud Provider Console

Purpose:
    This script is an educational, executable guide to the fundamental and
    advanced characteristics of cloud computing.

Important:
    This script does NOT connect to AWS, Microsoft Azure, Google Cloud, or
    another cloud provider. Instead, it simulates how important cloud concepts
    work internally.

Learning progression:
    1. What cloud computing is
    2. Why cloud computing exists
    3. Traditional infrastructure vs cloud
    4. Six major cloud characteristics
    5. Cloud provider console
    6. Virtualization and resource pooling
    7. Multi-tenancy
    8. Elasticity and scalability
    9. Metering and measured service
    10. Control plane and data plane
    11. Availability and fault tolerance
    12. Security considerations
    13. Cost optimization
    14. Infrastructure as Code
    15. Automation
    16. Advanced architecture concepts
    17. A complete simulated cloud environment
    18. Final knowledge summary

================================================================================
SECTION 1: WHAT IS CLOUD COMPUTING?
================================================================================

Cloud computing is a model for delivering computing resources over a network,
usually the Internet.

Instead of purchasing and operating every physical server, storage device,
network device, database server, and data-center facility yourself, you can
rent computing resources from a cloud provider.

Examples of cloud resources:

    - Virtual machines
    - Containers
    - Object storage
    - Block storage
    - Databases
    - Networking
    - Load balancers
    - Queues
    - Serverless functions
    - AI/ML services
    - Monitoring systems

The fundamental idea is:

    Traditional model:
        Buy hardware -> install hardware -> configure hardware ->
        maintain hardware -> replace hardware

    Cloud model:
        Request resource -> provider provisions resource ->
        use resource -> pay according to usage or subscription

Cloud computing therefore changes computing from a primarily
CAPITAL-EXPENDITURE model into a model that can support
OPERATIONAL-EXPENDITURE-based consumption.

CAPEX:
    Capital expenditure.
    Money spent purchasing long-lived assets.

OPEX:
    Operational expenditure.
    Money spent operating services and infrastructure.

================================================================================
SECTION 2: A SIMPLE REAL-WORLD ANALOGY
================================================================================

Imagine you need electricity.

You could:

    1. Build your own power plant.
    2. Buy generators.
    3. Maintain generators.
    4. Purchase fuel.
    5. Hire technicians.

Or you could connect to an electricity grid and consume electricity as needed.

Cloud computing follows a similar philosophy.

Instead of owning an entire data center, you consume computing infrastructure
provided by a cloud provider.

This leads to several important properties:

    - Resources can be requested when needed.
    - Resources can be accessed through networks.
    - Physical infrastructure is shared.
    - Capacity can increase or decrease.
    - Usage can be measured.
    - Multiple customers can share the underlying infrastructure securely.

These ideas are represented by the major characteristics discussed in this
script.

================================================================================
SECTION 3: THE SIX MAJOR CHARACTERISTICS
================================================================================

The major characteristics covered here are:

    1. On-demand self-service
    2. Broad network access
    3. Resource pooling
    4. Rapid elasticity
    5. Measured service
    6. Multi-tenancy

These characteristics are closely related.

For example:

    On-demand self-service
            |
            v
    User requests resources
            |
            v
    Resource pooling
            |
            v
    Provider allocates shared infrastructure
            |
            v
    Rapid elasticity
            |
            v
    Capacity changes according to demand
            |
            v
    Measured service
            |
            v
    Usage is measured
            |
            v
    Billing / cost management

Multi-tenancy exists underneath much of this architecture, allowing multiple
customers to use shared physical infrastructure while maintaining logical
isolation.

================================================================================
SECTION 4: ON-DEMAND SELF-SERVICE
================================================================================

Definition:

On-demand self-service means that a customer can provision computing
resources automatically without requiring a human operator from the cloud
provider to manually perform every provisioning operation.

For example, a user may create:

    - A virtual machine
    - A storage bucket
    - A database
    - A serverless function
    - A virtual network

through a web console, CLI, SDK, or API.

Traditional infrastructure:

    Customer
       |
       v
    Submit request
       |
       v
    IT administrator
       |
       v
    Approve request
       |
       v
    Configure server
       |
       v
    Deliver server

Cloud self-service:

    Customer
       |
       v
    Console / CLI / API
       |
       v
    Cloud control plane
       |
       v
    Resource provisioned

This drastically reduces provisioning time.

Example:

    Suppose a developer needs a virtual machine.

    Without self-service:
        Request -> approval -> procurement -> installation -> configuration

    With cloud self-service:
        API/Console -> provisioning -> usable resource

The exact provisioning time depends on the service, architecture, region,
capacity, configuration, and provider.

--------------------------------------------------------------------------------
ON-DEMAND SELF-SERVICE IN PYTHON
--------------------------------------------------------------------------------
"""

class CloudResource:
    """Represents a simplified cloud resource."""

    def __init__(self, resource_type, name, region):
        self.resource_type = resource_type
        self.name = name
        self.region = region
        self.status = "PROVISIONING"

    def provision(self):
        self.status = "RUNNING"
        print(
            f"{self.resource_type} '{self.name}' is now "
            f"{self.status} in {self.region}."
        )


vm = CloudResource(
    resource_type="Virtual Machine",
    name="web-server-01",
    region="ap-south-1"
)

vm.provision()

"""
The important concept is not the Python class itself.

The concept is:

    User -> API/Console -> Cloud control plane -> Resource

The Python object merely simulates this process.

================================================================================
SECTION 5: BROAD NETWORK ACCESS
================================================================================

Broad network access means cloud resources are accessible through standard
network mechanisms and can be consumed by many types of client devices.

Possible clients include:

    - Laptops
    - Desktop computers
    - Smartphones
    - Tablets
    - Servers
    - IoT devices
    - Applications
    - Command-line tools
    - APIs
    - SDKs

Example:

    Web browser
         |
         +------> Cloud console
         |
         +------> Application API
         |
         +------> Storage service
         |
         +------> Database service

Cloud services are fundamentally network-accessible services.

This makes networking a core component of cloud computing.

Important networking concepts include:

    - IP addresses
    - DNS
    - Routing
    - Firewalls
    - Security groups
    - Load balancers
    - VPN
    - Private networks
    - Internet gateways
    - NAT
    - TLS/HTTPS

--------------------------------------------------------------------------------
PYTHON NETWORK ACCESS SIMULATION
--------------------------------------------------------------------------------
"""

class CloudEndpoint:
    def __init__(self, name, protocol, port):
        self.name = name
        self.protocol = protocol
        self.port = port

    def describe(self):
        print(
            f"Endpoint: {self.name} | "
            f"Protocol: {self.protocol} | "
            f"Port: {self.port}"
        )


https_endpoint = CloudEndpoint(
    name="Application API",
    protocol="HTTPS",
    port=443
)

https_endpoint.describe()

"""
HTTPS commonly uses TCP port 443.

A production cloud architecture may expose a public endpoint while keeping
databases and internal services on private networks.

Example:

    Internet
       |
       v
    Load Balancer
       |
       v
    Application Servers
       |
       v
    Private Database

The database does not necessarily need to be directly reachable from the
public Internet.

================================================================================
SECTION 6: RESOURCE POOLING
================================================================================

Resource pooling means the cloud provider maintains a pool of computing
resources that can be dynamically assigned to customers.

The underlying resources can include:

    - CPU
    - Memory
    - Storage
    - Network bandwidth
    - Physical servers
    - GPUs

Imagine a physical data center containing:

    Server 1
    Server 2
    Server 3
    Server 4
    ...
    Server 1000

Customers do not usually know or care which exact physical machine hosts
their virtual machine.

Instead, the provider abstracts the physical infrastructure.

Conceptually:

                Physical Infrastructure
                         |
          +--------------+--------------+
          |              |              |
       Compute        Storage        Network
          |              |              |
          +--------------+--------------+
                         |
                    Resource Pool
                         |
          +--------------+--------------+
          |              |              |
       Customer A     Customer B     Customer C

This abstraction is one of the most powerful ideas in cloud computing.

--------------------------------------------------------------------------------
RESOURCE POOL SIMULATION
--------------------------------------------------------------------------------
"""

class ResourcePool:
    def __init__(self, total_cpu, total_memory):
        self.total_cpu = total_cpu
        self.total_memory = total_memory

        self.available_cpu = total_cpu
        self.available_memory = total_memory

        self.allocations = {}

    def allocate(self, customer, cpu, memory):
        if cpu > self.available_cpu:
            raise RuntimeError("Insufficient CPU capacity.")

        if memory > self.available_memory:
            raise RuntimeError("Insufficient memory capacity.")

        self.available_cpu -= cpu
        self.available_memory -= memory

        self.allocations[customer] = {
            "cpu": cpu,
            "memory": memory
        }

        print(
            f"Allocated to {customer}: "
            f"{cpu} CPU units, {memory} GB memory."
        )

    def release(self, customer):
        allocation = self.allocations.pop(customer, None)

        if allocation is None:
            print(f"No allocation found for {customer}.")
            return

        self.available_cpu += allocation["cpu"]
        self.available_memory += allocation["memory"]

        print(f"Released resources from {customer}.")

    def status(self):
        print("\nRESOURCE POOL STATUS")
        print("-" * 30)
        print(f"Total CPU:       {self.total_cpu}")
        print(f"Available CPU:   {self.available_cpu}")
        print(f"Total memory:    {self.total_memory} GB")
        print(f"Available memory:{self.available_memory} GB")
        print(f"Allocations:     {self.allocations}")


pool = ResourcePool(total_cpu=100, total_memory=512)

pool.allocate("Customer-A", cpu=20, memory=64)
pool.allocate("Customer-B", cpu=30, memory=128)

pool.status()

pool.release("Customer-A")

pool.status()

"""
Notice that the customers consume resources from a common logical pool.

A real cloud provider's infrastructure is much more sophisticated.

It may involve:

    - Hypervisors
    - Container runtimes
    - Distributed storage
    - Software-defined networking
    - Scheduling systems
    - Capacity management
    - Hardware abstraction
    - Automated placement
    - Fault domains
    - Availability zones

================================================================================
SECTION 7: VIRTUALIZATION
================================================================================

Virtualization is a major technology enabling resource pooling.

A physical server might contain:

    64 CPU cores
    512 GB RAM
    Several TB of storage

A hypervisor can divide the physical machine into multiple virtual machines.

Conceptually:

    Physical Server
    +------------------------------------------+
    | Hypervisor                               |
    |                                          |
    |   VM A        VM B        VM C           |
    |  4 CPU       8 CPU       2 CPU           |
    | 16 GB RAM    32 GB RAM    8 GB RAM       |
    +------------------------------------------+

Each VM behaves like an independent computer from the customer's perspective.

The customer normally does not need to manage the underlying physical server.

Types of virtualization concepts include:

    - Compute virtualization
    - Network virtualization
    - Storage virtualization

Containers provide another level of abstraction.

VM:

    Physical hardware
        -> Hypervisor
            -> Virtual machine
                -> Guest operating system
                    -> Application

Container:

    Physical hardware
        -> Operating system
            -> Container runtime
                -> Container
                    -> Application

Containers are usually more lightweight because they share the host kernel,
while virtual machines typically include their own guest operating system.

================================================================================
SECTION 8: RAPID ELASTICITY
================================================================================

Elasticity means that computing capacity can be increased or decreased
according to demand.

Suppose an e-commerce website normally receives:

    1,000 requests/minute

During a major sale it receives:

    50,000 requests/minute

A cloud architecture can automatically increase capacity.

After traffic falls:

    50,000 requests/minute
              |
              v
        scale out
              |
              v
       many instances
              |
              v
        traffic decreases
              |
              v
        scale in
              |
              v
       fewer instances

This is elasticity.

--------------------------------------------------------------------------------
SCALABILITY VS ELASTICITY
--------------------------------------------------------------------------------

These concepts are related but not identical.

SCALABILITY:

    The system's ability to handle increasing workload by increasing
    resources or improving architecture.

ELASTICITY:

    The ability to dynamically adjust resources according to changing demand.

Example:

    Scaling:
        Increase from 2 servers to 10 servers.

    Elasticity:
        Automatically increase from 2 to 10 during peak demand,
        then reduce from 10 to 2 after demand decreases.

--------------------------------------------------------------------------------
HORIZONTAL VS VERTICAL SCALING
--------------------------------------------------------------------------------

Vertical scaling:

    Increase resources of an existing machine.

    4 CPU -> 8 CPU -> 16 CPU

Horizontal scaling:

    Increase the number of machines.

    2 servers -> 5 servers -> 20 servers

Cloud-native architectures frequently use horizontal scaling because it can
support distributed workloads.

--------------------------------------------------------------------------------
AUTO-SCALING SIMULATION
--------------------------------------------------------------------------------
"""

class AutoScaler:
    def __init__(self, minimum=1, maximum=10, target_cpu=60):
        self.minimum = minimum
        self.maximum = maximum
        self.target_cpu = target_cpu
        self.instances = minimum

    def evaluate(self, cpu_usage):
        print(f"\nObserved CPU usage: {cpu_usage}%")
        print(f"Current instances: {self.instances}")

        if cpu_usage > self.target_cpu:
            if self.instances < self.maximum:
                self.instances += 1
                print("Scale OUT: added one instance.")
            else:
                print("At maximum capacity.")

        elif cpu_usage < self.target_cpu * 0.5:
            if self.instances > self.minimum:
                self.instances -= 1
                print("Scale IN: removed one instance.")
            else:
                print("At minimum capacity.")

        else:
            print("No scaling action required.")

        print(f"New instance count: {self.instances}")


autoscaler = AutoScaler(minimum=2, maximum=8, target_cpu=60)

for usage in [45, 75, 90, 85, 30, 20]:
    autoscaler.evaluate(usage)

"""
Real cloud auto-scaling may use:

    - CPU utilization
    - Memory utilization
    - Request count
    - Queue depth
    - Network traffic
    - Custom application metrics
    - Scheduled rules
    - Predictive scaling

Advanced autoscaling can use multiple metrics and cooldown periods to prevent
rapid oscillation.

================================================================================
SECTION 9: MEASURED SERVICE
================================================================================

Measured service means that cloud resource consumption can be monitored,
measured, controlled, and reported.

Examples of measurable resources:

    - CPU hours
    - Storage GB-month
    - Network traffic
    - Number of requests
    - Database capacity
    - Function invocations
    - GPU usage
    - API calls

This enables usage-based billing.

For example:

    VM usage:
        10 hours

    Storage:
        100 GB

    Data transfer:
        25 GB

The exact pricing model differs between cloud services and providers.

Measured service creates a feedback loop:

    RESOURCE USAGE
          |
          v
    METRICS
          |
          v
    BILLING DATA
          |
          v
    COST ANALYSIS
          |
          v
    OPTIMIZATION

--------------------------------------------------------------------------------
METERING SIMULATION
--------------------------------------------------------------------------------
"""

class UsageMeter:
    def __init__(self):
        self.records = []

    def record(self, resource, quantity, unit):
        self.records.append({
            "resource": resource,
            "quantity": quantity,
            "unit": unit
        })

    def report(self):
        print("\nUSAGE REPORT")
        print("-" * 50)

        for record in self.records:
            print(
                f"{record['resource']}: "
                f"{record['quantity']} {record['unit']}"
            )


meter = UsageMeter()

meter.record("Compute", 120, "CPU-hours")
meter.record("Storage", 500, "GB-month")
meter.record("Data Transfer", 75, "GB")
meter.record("API Requests", 2_000_000, "requests")

meter.report()

"""
In real cloud platforms, usage data can feed:

    - Billing dashboards
    - Cost-management systems
    - Budgets
    - Alerts
    - FinOps systems
    - Forecasting
    - Chargeback
    - Showback

================================================================================
SECTION 10: MULTI-TENANCY
================================================================================

Multi-tenancy means that multiple customers, called tenants, can use shared
underlying infrastructure while remaining logically isolated.

Example:

    Physical Infrastructure
             |
       Shared Platform
             |
      +------+------+------+
      |      |      |      |
    Tenant A Tenant B Tenant C

The physical hardware can be shared, but customers must not be able to access
each other's data or resources.

Isolation may occur at several levels:

    - Identity
    - Network
    - Compute
    - Storage
    - Database
    - Application
    - Encryption
    - Access control

Multi-tenancy is essential for large cloud platforms because dedicated
physical hardware for every customer would be extremely inefficient.

--------------------------------------------------------------------------------
TENANT SIMULATION
--------------------------------------------------------------------------------
"""

class Tenant:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id
        self.resources = []

    def add_resource(self, resource):
        self.resources.append(resource)

    def list_resources(self):
        print(f"Resources for {self.tenant_id}:")
        for resource in self.resources:
            print(f"  - {resource}")


tenant_a = Tenant("TENANT-A")
tenant_b = Tenant("TENANT-B")

tenant_a.add_resource("vm-a1")
tenant_a.add_resource("storage-a1")

tenant_b.add_resource("vm-b1")
tenant_b.add_resource("storage-b1")

tenant_a.list_resources()
tenant_b.list_resources()

"""
A real cloud platform must enforce authorization so that:

    Tenant A cannot read Tenant B's resources.

This is commonly supported through mechanisms such as:

    - IAM
    - Access policies
    - Security groups
    - Network segmentation
    - Encryption
    - Resource-level permissions
    - Tenant-aware service architecture

================================================================================
SECTION 11: CLOUD PROVIDER CONSOLE
================================================================================

A cloud provider console is a web-based graphical interface through which
users can manage cloud resources.

Examples of console functionality include:

    - Creating virtual machines
    - Creating storage
    - Configuring networks
    - Managing databases
    - Creating IAM users/roles
    - Viewing monitoring metrics
    - Checking billing
    - Configuring alerts
    - Viewing logs
    - Managing security settings

Conceptually:

    User
      |
      v
    Browser
      |
      v
    Cloud Provider Console
      |
      v
    Authentication / Authorization
      |
      v
    Control Plane APIs
      |
      +----------+-----------+
      |          |           |
    Compute   Storage     Network
      |          |           |
    VM          Bucket      VPC

The console is only one interface.

Cloud resources can usually also be managed through:

    1. Web console
    2. CLI
    3. SDK
    4. REST/API interfaces
    5. Infrastructure as Code

================================================================================
SECTION 12: CONSOLE VS CLI VS SDK VS API VS IaC
================================================================================

WEB CONSOLE:

    Graphical interface.

    Good for:
        - Learning
        - Exploration
        - Quick manual operations
        - Visual monitoring

CLI:

    Command-line interface.

    Good for:
        - Automation
        - Scripting
        - Repeatable operations
        - DevOps workflows

SDK:

    Software development kit.

    Allows programming languages to interact with cloud services.

    Example concept:

        Python application
              |
              v
             SDK
              |
              v
          Cloud API

API:

    Programmatic interface exposed by a service.

IaC:

    Infrastructure as Code.

    Infrastructure is described using declarative or programmatic
    configuration.

Example conceptual IaC:

    resource "virtual_machine" "web" {
        cpu    = 4
        memory = 16
    }

The exact syntax depends on the tool.

Examples of infrastructure-as-code technologies include:

    - Terraform
    - AWS CloudFormation
    - Azure Bicep
    - Google Cloud Deployment Manager
    - Pulumi

================================================================================
SECTION 13: CONTROL PLANE AND DATA PLANE
================================================================================

One of the most important advanced cloud concepts is the distinction between
the control plane and the data plane.

CONTROL PLANE:

    Responsible for managing resources.

Examples:

    - Create VM
    - Delete VM
    - Configure firewall
    - Create database
    - Modify network configuration

DATA PLANE:

    Responsible for actual workload traffic or resource usage.

Example:

    A web application serving users.

Conceptually:

             CONTROL PLANE
                  |
       +----------+----------+
       |          |          |
     Create    Configure   Delete
       |          |          |
       +----------+----------+
                  |
                  v
            Cloud Resources
                  |
                  v
              DATA PLANE
                  |
            User application
                  |
                  v
             End users

This distinction becomes extremely important when designing distributed
systems and troubleshooting cloud services.

================================================================================
SECTION 14: CLOUD RESOURCE LIFECYCLE
================================================================================

A cloud resource generally has a lifecycle.

Typical lifecycle:

    1. Request
    2. Validate
    3. Authorize
    4. Provision
    5. Configure
    6. Monitor
    7. Scale
    8. Update
    9. Backup
    10. Decommission
    11. Delete

Python simulation:
"""

class LifecycleResource:
    VALID_STATES = [
        "REQUESTED",
        "PROVISIONING",
        "RUNNING",
        "STOPPED",
        "TERMINATED"
    ]

    def __init__(self, name):
        self.name = name
        self.state = "REQUESTED"

    def transition(self, new_state):
        if new_state not in self.VALID_STATES:
            raise ValueError("Invalid lifecycle state.")

        self.state = new_state
        print(f"{self.name} -> {self.state}")


resource = LifecycleResource("application-server")

resource.transition("PROVISIONING")
resource.transition("RUNNING")
resource.transition("STOPPED")
resource.transition("TERMINATED")

"""
================================================================================
SECTION 15: AVAILABILITY
================================================================================

Cloud systems are designed to provide high availability.

Availability describes the proportion of time a service is operational.

A simplified formula:

    Availability =
        Uptime / Total Observed Time

For example:

    Total time = 1000 hours
    Downtime   = 1 hour

    Uptime = 999 hours

    Availability = 999 / 1000
                 = 99.9%

Common availability concepts:

    - Single server
    - Redundant servers
    - Availability zones
    - Regions
    - Multi-region architecture

A simplified hierarchy:

    Cloud Provider
        |
        +---- Region
                |
                +---- Availability Zone A
                |
                +---- Availability Zone B
                |
                +---- Availability Zone C

A resilient application may distribute workloads across multiple failure
domains.

================================================================================
SECTION 16: FAULT TOLERANCE
================================================================================

Fault tolerance means that the system can continue operating despite failures.

Potential failures:

    - Server failure
    - Disk failure
    - Network failure
    - Database failure
    - Availability zone failure
    - Software failure

Basic architecture:

    User
      |
      v
    Load Balancer
      |
      +----------+----------+
      |                     |
    Server A              Server B
      |                     |
      +----------+----------+
                 |
              Database

If Server A fails, traffic can potentially be redirected to Server B.

This requires:

    - Health checks
    - Redundancy
    - Failure detection
    - Automated recovery
    - Appropriate state management

================================================================================
SECTION 17: ELASTICITY + RESOURCE POOLING
================================================================================

Elasticity and resource pooling are closely connected.

Suppose the cloud provider has:

    10,000 available compute units.

Customer demand changes:

    Morning:
        5,000 units

    Afternoon:
        8,000 units

    Night:
        3,000 units

The provider can dynamically allocate resources according to demand.

This is fundamentally different from every customer purchasing dedicated
physical servers sized for their maximum possible demand.

The cloud model attempts to improve utilization through shared infrastructure.

================================================================================
SECTION 18: SECURITY IN MULTI-TENANT CLOUDS
================================================================================

Cloud security is based on multiple layers.

A simplified security architecture:

    Physical Security
          |
          v
    Infrastructure Security
          |
          v
    Network Security
          |
          v
    Identity & Access Management
          |
          v
    Application Security
          |
          v
    Data Security
          |
          v
    Monitoring & Detection

Important concepts:

    Authentication:
        Who are you?

    Authorization:
        What are you allowed to do?

    Encryption:
        How is information protected?

    Logging:
        What happened?

    Monitoring:
        What is happening now?

    Auditing:
        Who performed which action?

A common principle is:

    LEAST PRIVILEGE

Users and applications should receive only the permissions required for
their tasks.

Example:

    Read-only analyst:
        Can view reports.

    Application role:
        Can read application data.

    Administrator:
        Can modify infrastructure.

These roles should not automatically have identical permissions.

================================================================================
SECTION 19: SHARED RESPONSIBILITY MODEL
================================================================================

Cloud security is generally based on a shared responsibility model.

The exact responsibilities vary by service and provider.

Conceptually:

    CLOUD PROVIDER
        |
        +-- Physical data centers
        +-- Physical hardware
        +-- Core infrastructure
        +-- Underlying cloud platform

    CUSTOMER
        |
        +-- Identity configuration
        +-- Application security
        +-- Data
        +-- Access policies
        +-- Configuration
        +-- Operating system in some service models

Responsibility changes depending on whether you use:

    IaaS
    PaaS
    SaaS

IaaS:

    Customer generally manages more.

PaaS:

    Provider manages more infrastructure.

SaaS:

    Provider manages most of the underlying platform.

The customer still remains responsible for appropriate use, access,
data, and configuration according to the service.

================================================================================
SECTION 20: IaaS, PaaS AND SaaS
================================================================================

IaaS:
    Infrastructure as a Service

    Examples:
        Virtual machines
        Networks
        Storage

    Customer manages:
        More of the operating environment.

PaaS:
    Platform as a Service

    Provider manages more infrastructure and runtime components.

    Developer focuses more on:
        Application code
        Data
        Configuration

SaaS:
    Software as a Service

    Complete application delivered as a service.

Simplified spectrum:

    More customer management
              |
              v
            IaaS
              |
              v
            PaaS
              |
              v
            SaaS
              |
              v
    More provider management

================================================================================
SECTION 21: MEASURED SERVICE AND FINOPS
================================================================================

Measured service leads naturally to FinOps.

FinOps means applying financial accountability and operational discipline
to cloud usage.

Important questions:

    - Which team is spending money?
    - Which application consumes the most resources?
    - Which resources are idle?
    - Are instances oversized?
    - Is storage growing unnecessarily?
    - Can workloads use cheaper capacity?
    - Are budgets being exceeded?

Useful techniques:

    - Tags
    - Labels
    - Cost allocation
    - Budgets
    - Alerts
    - Rightsizing
    - Scheduling
    - Autoscaling
    - Storage lifecycle policies
    - Reserved/committed pricing where appropriate
    - Usage analysis

Example:

    Application A:
        $500/month

    Application B:
        $4,000/month

    Application C:
        $700/month

The organization can investigate why Application B consumes much more.

================================================================================
SECTION 22: CLOUD OBSERVABILITY
================================================================================

Cloud systems need observability.

Three fundamental pillars:

    1. Metrics
    2. Logs
    3. Traces

METRICS:

    Numeric measurements.

Examples:

    CPU = 72%
    Memory = 80%
    Requests = 10,000/minute

LOGS:

    Timestamped records of events.

TRACE:

    Tracks a request across distributed services.

Example:

    User
      |
      v
    API Gateway
      |
      v
    Service A
      |
      v
    Service B
      |
      v
    Database

Distributed tracing helps determine where latency occurs.

================================================================================
SECTION 23: CLOUD AUTOMATION
================================================================================

One of the biggest advantages of cloud computing is automation.

Manual:

    Human -> Console -> Click -> Configure -> Repeat

Automated:

    Code -> API -> Infrastructure

Automation can be implemented through:

    - CLI
    - SDK
    - APIs
    - Scripts
    - CI/CD pipelines
    - Infrastructure as Code
    - Event-driven automation

Example Python automation concept:
"""

def deploy_application(environment, replicas):
    print(f"Deploying application to: {environment}")
    print(f"Requested replicas: {replicas}")

    for number in range(1, replicas + 1):
        print(f"Provisioning application replica {number}")

    print("Deployment completed.")


deploy_application("production", 3)

"""
The real implementation could call a cloud provider's SDK/API instead of
simply printing messages.

================================================================================
SECTION 24: INFRASTRUCTURE AS CODE
================================================================================

Infrastructure as Code treats infrastructure configuration as code.

Instead of manually clicking:

    Create VM
    Configure network
    Create database
    Configure permissions

you define the desired state.

Conceptually:

    desired_state = {
        "environment": "production",
        "web_servers": 3,
        "database": True,
        "monitoring": True
    }

An IaC engine attempts to make the actual infrastructure match the desired
state.

This gives:

    - Reproducibility
    - Version control
    - Reviewability
    - Automation
    - Consistency
    - Disaster recovery benefits

================================================================================
SECTION 25: DECLARATIVE VS IMPERATIVE
================================================================================

Imperative approach:

    "Do these steps."

Example:

    1. Create VM.
    2. Install package.
    3. Configure firewall.
    4. Start service.

Declarative approach:

    "This is the desired final state."

Example:

    Desired:
        3 web servers
        HTTPS enabled
        Monitoring enabled

The system determines the necessary actions.

Modern infrastructure automation frequently favors declarative approaches.

================================================================================
SECTION 26: CLOUD API CONCEPT
================================================================================

A cloud console ultimately interacts with backend services.

Conceptually:

    Python application
           |
           v
        SDK/CLI
           |
           v
         HTTPS
           |
           v
      Cloud API
           |
           v
      Control Plane
           |
           v
        Resource

A simplified API client might look like:

"""

class FakeCloudAPI:
    def create_server(self, name, cpu, memory):
        return {
            "id": "srv-001",
            "name": name,
            "cpu": cpu,
            "memory": memory,
            "status": "RUNNING"
        }

    def delete_server(self, server_id):
        return {
            "id": server_id,
            "status": "TERMINATED"
        }


api = FakeCloudAPI()

server = api.create_server(
    name="production-web",
    cpu=4,
    memory=16
)

print("\nAPI CREATE RESPONSE:")
print(server)

delete_response = api.delete_server(server["id"])

print("\nAPI DELETE RESPONSE:")
print(delete_response)

"""
In a real implementation, an SDK would communicate with an actual provider
API using authentication, authorization, request signing, HTTPS, retries,
timeouts, pagination, and error handling.

================================================================================
SECTION 27: IDENTITY AND ACCESS MANAGEMENT
================================================================================

IAM controls access to cloud resources.

Basic IAM model:

    PRINCIPAL
        |
        v
    AUTHENTICATION
        |
        v
    AUTHORIZATION
        |
        v
    RESOURCE

Principal may be:

    - Human user
    - Service account
    - Role
    - Application identity

Authentication asks:

    "Who are you?"

Authorization asks:

    "What are you allowed to do?"

Example policy concept:
"""

class IAMPolicy:
    def __init__(self, subject, actions, resource):
        self.subject = subject
        self.actions = set(actions)
        self.resource = resource

    def allows(self, action):
        return action in self.actions


policy = IAMPolicy(
    subject="application-role",
    actions=["read", "list"],
    resource="database"
)

print("\nIAM CHECK")
print("Can read?", policy.allows("read"))
print("Can delete?", policy.allows("delete"))

"""
A real IAM system is significantly more complex and can evaluate:

    - Identity
    - Action
    - Resource
    - Conditions
    - Policies
    - Explicit denies
    - Organization-level controls
    - Resource-level permissions
    - Network context

================================================================================
SECTION 28: RESOURCE TAGGING
================================================================================

Tags or labels help organize cloud resources.

Example:

    Environment = Production
    Application = Payments
    Owner = Team-A
    CostCenter = Finance

Python simulation:
"""

resources = [
    {
        "name": "web-01",
        "environment": "production",
        "application": "website",
        "owner": "team-a"
    },
    {
        "name": "db-01",
        "environment": "production",
        "application": "database",
        "owner": "team-b"
    },
    {
        "name": "test-01",
        "environment": "development",
        "application": "website",
        "owner": "team-a"
    }
]

production_resources = [
    resource
    for resource in resources
    if resource["environment"] == "production"
]

print("\nPRODUCTION RESOURCES")

for resource in production_resources:
    print(resource)

"""
Tags support:

    - Cost allocation
    - Automation
    - Governance
    - Inventory
    - Security policies
    - Resource discovery

================================================================================
SECTION 29: CLOUD GOVERNANCE
================================================================================

As cloud environments grow, governance becomes important.

Governance answers questions such as:

    - Who can create resources?
    - Which regions are permitted?
    - What security standards must be followed?
    - What naming convention should be used?
    - What tags are mandatory?
    - What resources require approval?
    - What is the maximum permitted cost?

Governance mechanisms can include:

    - IAM policies
    - Organization policies
    - Service control policies
    - Resource policies
    - Policy-as-code
    - Budget controls
    - Compliance rules
    - Audit logs

================================================================================
SECTION 30: CLOUD RESOURCE SCHEDULING
================================================================================

Cloud elasticity allows resources to be scheduled.

Example:

    Development server:

        09:00 -> START
        18:00 -> STOP

If the server is not required overnight, scheduled shutdown can reduce cost.

This is an example of combining:

    Measured service
            +
    Automation
            +
    Cost optimization

================================================================================
SECTION 31: EVENT-DRIVEN CLOUD ARCHITECTURE
================================================================================

Cloud systems can react to events.

Example:

    File uploaded
          |
          v
       Event
          |
          v
    Serverless Function
          |
          v
    Process File
          |
          v
    Store Result

This allows systems to scale according to incoming events.

Common event sources:

    - HTTP requests
    - File uploads
    - Database changes
    - Queue messages
    - Scheduled events
    - Monitoring alerts

================================================================================
SECTION 32: SERVERLESS AND ELASTICITY
================================================================================

Serverless computing abstracts server management from the developer.

The developer typically provides:

    - Code
    - Configuration
    - Permissions

The provider handles much of:

    - Server provisioning
    - Capacity management
    - Scaling
    - Infrastructure maintenance

Serverless therefore strongly demonstrates:

    On-demand self-service
            +
    Resource pooling
            +
    Rapid elasticity
            +
    Measured service

Example conceptual function:
"""

def process_order(order):
    if not order:
        raise ValueError("Order cannot be empty.")

    return {
        "status": "processed",
        "order_id": order["id"]
    }


order = {
    "id": "ORDER-1001",
    "amount": 2500
}

print("\nSERVERLESS FUNCTION SIMULATION")
print(process_order(order))

"""
================================================================================
SECTION 33: CONTAINERS AND ORCHESTRATION
================================================================================

Containers package applications with their dependencies.

A container image may contain:

    - Application code
    - Runtime
    - Libraries
    - Configuration defaults

A container orchestrator manages many containers.

Responsibilities may include:

    - Scheduling
    - Scaling
    - Service discovery
    - Health checking
    - Rolling deployments
    - Self-healing

Conceptually:

                    Orchestrator
                         |
          +--------------+--------------+
          |              |              |
       Container      Container      Container
          |              |              |
        App A          App A          App A

If one container fails, the orchestrator may replace it.

================================================================================
SECTION 34: CLOUD-NATIVE ARCHITECTURE
================================================================================

Cloud-native systems typically embrace:

    - Automation
    - Elasticity
    - Distributed systems
    - Containers
    - Managed services
    - APIs
    - Observability
    - Infrastructure as Code
    - Continuous delivery
    - Fault tolerance

Cloud-native does NOT simply mean:

    "An application hosted on a cloud."

An application can run on a cloud VM while still behaving like a traditional
monolithic application.

Cloud-native architecture is more about how the application and infrastructure
are designed.

================================================================================
SECTION 35: COMPLETE CLOUD SIMULATION
================================================================================

The following class combines several concepts:

    - Resource pool
    - Tenants
    - Self-service
    - Elasticity
    - Metering
    - Multi-tenancy
"""

class CloudPlatform:
    def __init__(self, total_cpu, total_memory):
        self.pool = ResourcePool(total_cpu, total_memory)
        self.meter = UsageMeter()
        self.resources = {}

    def create_vm(self, tenant, name, cpu, memory):
        resource_id = f"vm-{len(self.resources) + 1}"

        self.pool.allocate(
            customer=tenant,
            cpu=cpu,
            memory=memory
        )

        self.resources[resource_id] = {
            "tenant": tenant,
            "name": name,
            "cpu": cpu,
            "memory": memory,
            "status": "RUNNING"
        }

        self.meter.record(
            resource=f"{resource_id} compute",
            quantity=cpu,
            unit="CPU units"
        )

        print(
            f"Created {resource_id} for {tenant}: "
            f"{name}"
        )

        return resource_id

    def list_resources(self, tenant=None):
        print("\nCLOUD RESOURCE INVENTORY")

        for resource_id, resource in self.resources.items():

            if tenant is not None and resource["tenant"] != tenant:
                continue

            print(
                resource_id,
                "=>",
                resource
            )


cloud = CloudPlatform(
    total_cpu=100,
    total_memory=512
)

cloud.create_vm(
    tenant="Customer-A",
    name="web-server",
    cpu=10,
    memory=32
)

cloud.create_vm(
    tenant="Customer-B",
    name="api-server",
    cpu=20,
    memory=64
)

cloud.create_vm(
    tenant="Customer-A",
    name="database-server",
    cpu=15,
    memory=64
)

cloud.list_resources()

cloud.list_resources(tenant="Customer-A")

cloud.pool.status()

cloud.meter.report()

"""
================================================================================
SECTION 36: WHAT THE CLOUD PROVIDER IS ACTUALLY DOING
================================================================================

When a customer clicks "Create" in a cloud console, many operations may occur
behind the scenes.

Simplified flow:

    1. User authenticates.
    2. User selects account/project/subscription.
    3. User selects region.
    4. User selects resource type.
    5. User specifies configuration.
    6. Request reaches the control plane.
    7. IAM authorization is evaluated.
    8. Quotas are checked.
    9. Capacity is checked.
    10. Resource is scheduled.
    11. Networking is configured.
    12. Storage is attached.
    13. Security policies are applied.
    14. Resource metadata is created.
    15. Monitoring is enabled/configured.
    16. Resource becomes available.
    17. Usage is metered.

A simple representation:

    Console
       |
       v
    Authentication
       |
       v
    Authorization
       |
       v
    API
       |
       v
    Control Plane
       |
       +---- IAM
       |
       +---- Quota
       |
       +---- Scheduler
       |
       +---- Networking
       |
       +---- Storage
       |
       +---- Monitoring
       |
       v
    Compute Resource

================================================================================
SECTION 37: QUOTAS
================================================================================

Cloud providers often enforce quotas.

A quota limits how much of a particular resource an account, project,
subscription, region, or service can consume.

Examples:

    - Maximum number of VMs
    - Maximum CPU
    - Maximum storage
    - API request rate
    - Maximum IP addresses

Why quotas exist:

    - Prevent accidental resource explosions
    - Protect platform capacity
    - Reduce abuse
    - Improve governance
    - Maintain operational stability

================================================================================
SECTION 38: API RATE LIMITING
================================================================================

Cloud APIs can also enforce rate limits.

Example:

    Application
        |
        | 1000 requests/sec
        v
    Cloud API
        |
        v
    Rate limiter

If the allowed rate is lower, requests may be delayed or rejected.

Production applications should often implement:

    - Retry logic
    - Exponential backoff
    - Jitter
    - Idempotency
    - Timeout handling

Example:
"""

import random
import time


def retry_with_backoff(operation, attempts=5):
    for attempt in range(attempts):

        try:
            return operation()

        except Exception as error:

            if attempt == attempts - 1:
                raise

            delay = (2 ** attempt) + random.random()

            print(
                f"Attempt {attempt + 1} failed: {error}. "
                f"Retrying in {delay:.2f} seconds."
            )

            time.sleep(delay)


counter = {"value": 0}


def unreliable_operation():
    counter["value"] += 1

    if counter["value"] < 3:
        raise RuntimeError("Temporary cloud API failure.")

    return "Operation succeeded."


print("\nRETRY SIMULATION")

result = retry_with_backoff(unreliable_operation)

print(result)

"""
================================================================================
SECTION 39: IDEMPOTENCY
================================================================================

Idempotency means that performing the same operation multiple times produces
the same intended result.

This is extremely important in distributed cloud systems.

Suppose a client sends:

    "Create payment"

The request times out.

The client does not know whether the server processed it.

If the client simply retries, it might accidentally create two payments.

An idempotency key can help:

    request_id = "PAYMENT-12345"

The server can recognize that the operation has already been processed.

Idempotency is important for:

    - APIs
    - Payments
    - Infrastructure automation
    - Distributed systems
    - Deployment systems

================================================================================
SECTION 40: DISASTER RECOVERY
================================================================================

Cloud architectures should consider disaster recovery.

Important concepts:

    RPO:
        Recovery Point Objective.

        How much data loss is acceptable?

    RTO:
        Recovery Time Objective.

        How quickly must the service recover?

Example:

    RPO = 15 minutes
    RTO = 1 hour

This means the organization may accept losing up to approximately 15 minutes
of data and aims to restore service within approximately one hour.

The actual implementation depends on business requirements.

================================================================================
SECTION 41: BACKUP VS HIGH AVAILABILITY
================================================================================

Backup and high availability are not the same.

Backup:

    Provides historical recovery capability.

High availability:

    Attempts to keep the service operational during failures.

Example:

    Database replicas
        -> high availability

    Daily backup
        -> recovery

A robust system may require both.

================================================================================
SECTION 42: CLOUD DEPLOYMENT STRATEGIES
================================================================================

Common deployment strategies include:

    Rolling deployment
    Blue-green deployment
    Canary deployment
    Recreate deployment

Rolling:

    Replace instances gradually.

Blue-green:

    Maintain two environments.

Canary:

    Send a small percentage of users to the new version first.

These approaches can reduce deployment risk.

================================================================================
SECTION 43: CLOUD COST AND ARCHITECTURE TRADE-OFFS
================================================================================

Cloud architecture is not simply about minimizing cost.

You balance:

    Cost
    Performance
    Availability
    Reliability
    Security
    Scalability
    Maintainability
    Compliance

For example:

    One server:
        Cheap
        Simple
        Lower redundancy

    Multiple servers:
        More expensive
        More complex
        Higher potential availability

The correct architecture depends on business requirements.

================================================================================
SECTION 44: COMMON MISUNDERSTANDINGS
================================================================================

MISUNDERSTANDING 1:

    "Cloud means someone else's computer."

Correction:

    Cloud infrastructure does involve provider-owned physical infrastructure,
    but cloud computing also includes automation, abstraction, APIs,
    elasticity, resource pooling, measured usage, distributed systems,
    managed services, and operational capabilities.

MISUNDERSTANDING 2:

    "Cloud automatically means secure."

Correction:

    Cloud providers provide substantial security capabilities, but customers
    can still create insecure configurations.

MISUNDERSTANDING 3:

    "Cloud is always cheaper."

Correction:

    Cloud can reduce infrastructure costs and improve utilization, but poorly
    managed cloud environments can become expensive.

MISUNDERSTANDING 4:

    "Scalability and elasticity are identical."

Correction:

    Scalability is the ability to handle increased workload.
    Elasticity emphasizes dynamic adjustment of capacity.

MISUNDERSTANDING 5:

    "The console is the cloud."

Correction:

    The console is only one interface to the cloud control plane.

MISUNDERSTANDING 6:

    "Multi-tenancy means customers share data."

Correction:

    Multi-tenancy means infrastructure or services can be shared while
    logical isolation prevents unauthorized access between tenants.

================================================================================
SECTION 45: INTERVIEW-LEVEL QUESTIONS
================================================================================

Q1. What is on-demand self-service?

Answer:

    It is the ability of customers to provision and manage computing
    resources automatically without requiring manual intervention from
    the provider for each request.

Q2. What is broad network access?

Answer:

    Cloud services can be accessed through standard network mechanisms by
    various client devices and applications.

Q3. What is resource pooling?

Answer:

    Provider resources are pooled and dynamically allocated among customers
    according to demand.

Q4. What is elasticity?

Answer:

    The ability to dynamically increase or decrease resources according to
    workload demand.

Q5. What is measured service?

Answer:

    Cloud resource consumption is monitored and measured, enabling visibility,
    control, reporting, and often usage-based billing.

Q6. What is multi-tenancy?

Answer:

    Multiple customers share underlying infrastructure or service components
    while maintaining logical isolation.

Q7. What is a cloud provider console?

Answer:

    A graphical web interface used to manage and monitor cloud services.

Q8. Console vs API?

Answer:

    The console is a graphical interface, while an API is a programmatic
    interface that applications and automation tools can use.

Q9. Why is virtualization important?

Answer:

    It abstracts physical hardware and allows resources to be divided,
    isolated, and efficiently allocated.

Q10. What is the difference between scaling and elasticity?

Answer:

    Scaling increases capacity; elasticity dynamically adjusts capacity
    according to changing demand.

================================================================================
SECTION 46: ADVANCED ARCHITECTURAL VIEW
================================================================================

A mature cloud architecture can be understood as several layers:

    ┌─────────────────────────────────────────────┐
    │                 Applications                │
    ├─────────────────────────────────────────────┤
    │        Containers / Serverless / VMs        │
    ├─────────────────────────────────────────────┤
    │              Managed Services              │
    ├─────────────────────────────────────────────┤
    │       Compute / Storage / Networking       │
    ├─────────────────────────────────────────────┤
    │       Virtualization / Abstraction         │
    ├─────────────────────────────────────────────┤
    │             Physical Hardware              │
    └─────────────────────────────────────────────┘

Across all layers:

    Identity
    Security
    Monitoring
    Governance
    Automation
    Billing
    Policy

The cloud provider console is an entry point into the management layer.

================================================================================
SECTION 47: COMPLETE CHARACTERISTICS MAP
================================================================================

We can summarize the relationships as:

    ON-DEMAND SELF-SERVICE
        |
        | request resources automatically
        v
    RESOURCE POOLING
        |
        | allocate shared infrastructure
        v
    MULTI-TENANCY
        |
        | isolate multiple customers
        v
    RAPID ELASTICITY
        |
        | dynamically adjust capacity
        v
    MEASURED SERVICE
        |
        | monitor and measure consumption
        v
    COST / BILLING / FINOPS

All of these operate through:

    CONSOLE
    CLI
    SDK
    API
    INFRASTRUCTURE AS CODE

================================================================================
SECTION 48: FINAL SIMULATION
================================================================================

The following demonstration brings together the main concepts.

"""

class CloudEnvironment:
    def __init__(self):
        self.tenants = {}
        self.resources = []
        self.total_capacity = 100
        self.used_capacity = 0

    def register_tenant(self, tenant):
        self.tenants[tenant] = []

    def provision(self, tenant, resource_name, capacity):
        if tenant not in self.tenants:
            raise PermissionError("Unknown tenant.")

        if self.used_capacity + capacity > self.total_capacity:
            raise RuntimeError("Cloud capacity exhausted.")

        resource = {
            "tenant": tenant,
            "name": resource_name,
            "capacity": capacity,
            "status": "RUNNING"
        }

        self.resources.append(resource)
        self.tenants[tenant].append(resource_name)

        self.used_capacity += capacity

        print(
            f"Provisioned '{resource_name}' for {tenant} "
            f"using {capacity} capacity units."
        )

    def show_console(self):
        print("\n" + "=" * 60)
        print("SIMULATED CLOUD PROVIDER CONSOLE")
        print("=" * 60)

        print(f"Total capacity: {self.total_capacity}")
        print(f"Used capacity:  {self.used_capacity}")
        print(
            f"Free capacity:  "
            f"{self.total_capacity - self.used_capacity}"
        )

        print("\nTENANTS")

        for tenant, resources in self.tenants.items():
            print(f"  {tenant}: {resources}")

        print("\nRESOURCES")

        for resource in self.resources:
            print(f"  {resource}")


environment = CloudEnvironment()

environment.register_tenant("Engineering")
environment.register_tenant("Analytics")

environment.provision(
    tenant="Engineering",
    resource_name="web-server",
    capacity=20
)

environment.provision(
    tenant="Engineering",
    resource_name="api-server",
    capacity=15
)

environment.provision(
    tenant="Analytics",
    resource_name="data-server",
    capacity=25
)

environment.show_console()

"""
================================================================================
SECTION 49: FINAL TAKEAWAY
================================================================================

The core cloud computing characteristics can be remembered using this model:

    1. ON-DEMAND SELF-SERVICE
       Resources can be requested when needed.

    2. BROAD NETWORK ACCESS
       Services are accessible through networks using standard interfaces.

    3. RESOURCE POOLING
       Provider infrastructure is pooled and dynamically allocated.

    4. RAPID ELASTICITY
       Capacity can increase or decrease according to demand.

    5. MEASURED SERVICE
       Resource usage can be monitored, measured, reported, and billed.

    6. MULTI-TENANCY
       Multiple customers can share underlying infrastructure while being
       logically isolated.

    7. CLOUD PROVIDER CONSOLE
       A graphical interface for managing cloud resources.

The deeper cloud architecture connects these characteristics with:

    Virtualization
    APIs
    IAM
    Automation
    Infrastructure as Code
    Networking
    Storage
    Monitoring
    Autoscaling
    Fault tolerance
    Disaster recovery
    FinOps
    Governance
    Security

The most important conceptual chain is:

    USER
      |
      v
    CONSOLE / CLI / SDK / API / IaC
      |
      v
    AUTHENTICATION
      |
      v
    AUTHORIZATION
      |
      v
    CLOUD CONTROL PLANE
      |
      v
    RESOURCE POOL
      |
      +----------------------+
      |                      |
      v                      v
    COMPUTE                STORAGE
      |                      |
      +----------+-----------+
                 |
                 v
              NETWORK
                 |
                 v
             APPLICATION
                 |
                 v
                USER

At the operational level:

    Demand increases
          |
          v
    Autoscaling
          |
          v
    More resources allocated
          |
          v
    Workload handled
          |
          v
    Demand decreases
          |
          v
    Resources released
          |
          v
    Lower resource consumption

At the financial level:

    Resource usage
          |
          v
    Measurement
          |
          v
    Cost
          |
          v
    Monitoring
          |
          v
    Optimization

At the security level:

    Identity
       |
       v
    Authentication
       |
       v
    Authorization
       |
       v
    Least privilege
       |
       v
    Resource isolation
       |
       v
    Monitoring / auditing

Therefore, cloud computing is not merely "renting servers."

It is an integrated computing model built around:

    SELF-SERVICE
    NETWORK ACCESS
    SHARED RESOURCE POOLS
    ELASTIC CAPACITY
    MEASUREMENT
    MULTI-TENANCY
    AUTOMATION
    ABSTRACTION
    SECURITY
    OBSERVABILITY
    GOVERNANCE

Understanding these principles provides the foundation for learning AWS,
Microsoft Azure, Google Cloud, Kubernetes, Terraform, DevOps, cloud
architecture, distributed systems, and cloud-native application development.

================================================================================
END OF SCRIPT
================================================================================
"""
