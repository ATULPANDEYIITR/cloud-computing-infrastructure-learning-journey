```python
"""
====================================================================
DAY 01: INTRODUCTION TO CLOUD COMPUTING
====================================================================

Learning Journey:
Cloud Computing Infrastructure Learning Journey

Topic:
Introduction to Cloud Computing

Subtopics Covered:
1. Definition of Cloud Computing
2. Evolution of Computing Infrastructure
3. Traditional Infrastructure vs Cloud Infrastructure
4. Reasons for Cloud Adoption
5. Basic Cloud Terminology
6. Cloud Computing Characteristics
7. Cloud Service Models
8. Cloud Deployment Models
9. Cloud Infrastructure Components
10. Virtualization and Resource Abstraction
11. Multi-Tenancy and Resource Pooling
12. Scalability and Elasticity
13. Availability and Reliability
14. Regions and Availability Zones
15. Cloud Economics
16. Cloud Security Fundamentals
17. Cloud APIs and Automation
18. Cloud-Native Thinking
19. Cloud Architecture Examples
20. Advanced Concepts Introduced

Tools Referenced:
- Web Browser
- Cloud Console Concepts

This program is educational.

It does not connect to an actual cloud provider.

Instead, it uses Python simulations, examples, classes, calculations,
and architecture demonstrations to help understand how cloud
infrastructure works.
====================================================================
"""


# ================================================================
# SECTION 1: PROGRAM INTRODUCTION
# ================================================================

print("\n" + "=" * 90)
print("DAY 01 - INTRODUCTION TO CLOUD COMPUTING")
print("CLOUD COMPUTING INFRASTRUCTURE LEARNING JOURNEY")
print("=" * 90)


def print_heading(title):
    """Print a consistently formatted heading."""
    print("\n" + "-" * 90)
    print(title.upper())
    print("-" * 90)


def pause():
    """Visual separator between learning sections."""
    print("\n" + "." * 90)


print("""
Welcome to Day 01 of the Cloud Computing Infrastructure Learning Journey.

Cloud computing is one of the most important technological changes in
modern computing.

Before cloud computing became widely available, organizations often had
to purchase physical servers, build data centers, install networking
equipment, maintain storage systems, and employ teams to manage all of
that infrastructure.

Cloud computing changed this approach.

Instead of treating infrastructure as something that must always be
physically owned, organizations can consume computing resources as
services.

The purpose of this program is to understand not only WHAT cloud
computing is, but also WHY it exists and HOW the underlying ideas
changed the way modern applications are built.
""")


# ================================================================
# SECTION 2: WHAT IS CLOUD COMPUTING?
# ================================================================

print_heading("1. What Is Cloud Computing?")

cloud_definition = """
Cloud Computing is a model for delivering computing resources as
services over a network.

These computing resources can include:

- Processing power
- Virtual servers
- Storage
- Databases
- Networking
- Security services
- Containers
- Serverless computing
- Monitoring systems
- Artificial intelligence services
- Analytics platforms

Instead of purchasing all physical infrastructure themselves,
organizations can provision resources from a cloud provider.
"""

print(cloud_definition)

print("""
A simplified representation is:

USER OR ORGANIZATION
        |
        v
NETWORK / INTERNET
        |
        v
CLOUD PROVIDER PLATFORM
        |
        +--------------------------+
        | COMPUTE                  |
        | STORAGE                  |
        | NETWORKING               |
        | DATABASES                |
        | SECURITY                 |
        | ANALYTICS                |
        +--------------------------+

The organization consumes these resources according to its requirements.
""")


# ================================================================
# SECTION 3: A SIMPLE ANALOGY
# ================================================================

print_heading("2. Understanding Cloud Computing Through Electricity")

print("""
Think about electricity.

Most people do not build their own power plant.

Instead:

1. A utility company generates electricity.
2. The electricity travels through infrastructure.
3. Consumers use the electricity.
4. Consumers are billed according to usage.

Cloud computing follows a similar idea.

Instead of building:

- A personal data center
- Physical servers
- Large storage systems
- Complex networking infrastructure

An organization can consume computing capacity from a provider.

This does not mean that physical infrastructure disappears.

Cloud computing still depends on physical infrastructure.

The difference is WHO manages the infrastructure and HOW customers
consume it.

Cloud Provider:
    Owns and manages large-scale infrastructure.

Customer:
    Requests and consumes computing resources.
""")


# ================================================================
# SECTION 4: COMPUTING BEFORE THE CLOUD
# ================================================================

print_heading("3. Traditional Computing Infrastructure")

traditional_components = {
    "Physical Servers":
        "Computers installed inside organizational data centers.",

    "Storage Systems":
        "Hardware used to store application and organizational data.",

    "Networking Equipment":
        "Routers, switches, cables, firewalls, and related infrastructure.",

    "Data Center Facilities":
        "Buildings, racks, cooling systems, and physical security.",

    "Power Infrastructure":
        "UPS systems, generators, and redundant power supplies.",

    "Operations Teams":
        "Engineers responsible for maintaining and repairing infrastructure."
}

for component, description in traditional_components.items():
    print(f"\n{component}")
    print(f"  {description}")


print("""
A traditional organization may follow this process:

STEP 1:
Estimate future application demand.

STEP 2:
Purchase physical servers.

STEP 3:
Purchase storage hardware.

STEP 4:
Install networking equipment.

STEP 5:
Configure the operating systems.

STEP 6:
Deploy applications.

STEP 7:
Maintain hardware for years.

This approach introduces a major challenge:

CAPACITY PLANNING.

Organizations must estimate how much infrastructure they will require.

But predicting future demand is difficult.
""")


# ================================================================
# SECTION 5: CAPACITY PLANNING PROBLEM
# ================================================================

print_heading("4. The Capacity Planning Problem")

print("""
Imagine an online company expects approximately 10,000 users.

The company purchases enough servers for 10,000 users.

Possible situations:

SCENARIO A:
Actual users = 5,000

Result:
Some purchased infrastructure remains underutilized.


SCENARIO B:
Actual users = 10,000

Result:
Infrastructure capacity matches demand.


SCENARIO C:
Actual users = 1,000,000

Result:
Infrastructure becomes overloaded.

The organization must purchase and install additional hardware.

This may take days, weeks, or months.

Cloud computing addresses many aspects of this problem by allowing
infrastructure capacity to be provisioned more dynamically.
""")


# ================================================================
# SECTION 6: TRADITIONAL VS CLOUD
# ================================================================

print_heading("5. Traditional Infrastructure vs Cloud Infrastructure")

comparison = {
    "Infrastructure Ownership": (
        "Organization owns physical hardware",
        "Cloud provider operates underlying infrastructure"
    ),

    "Server Provisioning": (
        "Can require hardware purchasing and installation",
        "Can often be provisioned programmatically"
    ),

    "Scaling": (
        "Requires additional physical capacity",
        "Resources can be increased dynamically"
    ),

    "Maintenance": (
        "Organization manages significant physical infrastructure",
        "Provider manages portions of the infrastructure"
    ),

    "Cost Model": (
        "Often requires large upfront investment",
        "Often uses consumption-based pricing"
    ),

    "Global Expansion": (
        "May require building infrastructure in new locations",
        "Resources can often be deployed in multiple regions"
    ),

    "Automation": (
        "Historically involved more manual configuration",
        "Infrastructure can be managed through APIs and code"
    )
}

for feature, values in comparison.items():
    traditional, cloud = values

    print(f"\nFEATURE: {feature}")
    print(f"Traditional: {traditional}")
    print(f"Cloud:       {cloud}")


# ================================================================
# SECTION 7: EVOLUTION OF COMPUTING
# ================================================================

print_heading("6. Evolution of Computing Infrastructure")

evolution = [
    {
        "era": "Mainframe Computing",
        "description": (
            "Large centralized computers were used by organizations. "
            "Users accessed computing resources through terminals."
        )
    },
    {
        "era": "Personal Computing",
        "description": (
            "Computing became available on individual personal computers."
        )
    },
    {
        "era": "Client-Server Computing",
        "description": (
            "Applications were divided between client devices and centralized servers."
        )
    },
    {
        "era": "Enterprise Data Centers",
        "description": (
            "Organizations built dedicated facilities containing large amounts "
            "of computing infrastructure."
        )
    },
    {
        "era": "Virtualization",
        "description": (
            "Multiple virtual machines could run on a single physical server."
        )
    },
    {
        "era": "Cloud Computing",
        "description": (
            "Infrastructure became available as an on-demand service."
        )
    },
    {
        "era": "Containers",
        "description": (
            "Applications could be packaged with dependencies in portable units."
        )
    },
    {
        "era": "Serverless Computing",
        "description": (
            "Developers could focus more on application logic while infrastructure "
            "management became increasingly abstracted."
        )
    },
    {
        "era": "Edge Computing",
        "description": (
            "Some computation moved closer to users and devices to reduce latency."
        )
    }
]

for number, stage in enumerate(evolution, start=1):
    print(f"\n{number}. {stage['era']}")
    print(f"   {stage['description']}")


# ================================================================
# SECTION 8: VIRTUALIZATION
# ================================================================

print_heading("7. Virtualization and Its Importance")

print("""
Virtualization is one of the important technologies that enabled
modern cloud computing.

Before virtualization:

PHYSICAL SERVER
      |
OPERATING SYSTEM
      |
APPLICATION


With virtualization:

PHYSICAL SERVER
      |
HYPERVISOR
  /      |      \\
 VM1     VM2     VM3
  |       |       |
 OS      OS      OS
  |       |       |
APP     APP     APP

A single physical machine can support multiple isolated virtual
machines.

Each virtual machine may have:

- Its own operating system
- Its own CPU allocation
- Its own memory allocation
- Its own storage
- Its own network configuration
- Its own applications
""")


class VirtualMachine:
    """
    A simplified representation of a virtual machine.
    """

    def __init__(self, name, cpu_cores, memory_gb):
        self.name = name
        self.cpu_cores = cpu_cores
        self.memory_gb = memory_gb
        self.running = False

    def start(self):
        self.running = True
        print(f"{self.name} has started.")

    def stop(self):
        self.running = False
        print(f"{self.name} has stopped.")

    def show_details(self):
        status = "RUNNING" if self.running else "STOPPED"

        print("\nVirtual Machine Details")
        print(f"Name: {self.name}")
        print(f"CPU Cores: {self.cpu_cores}")
        print(f"Memory: {self.memory_gb} GB")
        print(f"Status: {status}")


print("\nVIRTUAL MACHINE SIMULATION")

vm_1 = VirtualMachine("Web-Server-01", 4, 8)
vm_2 = VirtualMachine("Database-Server-01", 8, 32)

vm_1.start()
vm_2.start()

vm_1.show_details()
vm_2.show_details()


# ================================================================
# SECTION 9: CLOUD CHARACTERISTICS
# ================================================================

print_heading("8. Core Characteristics of Cloud Computing")

characteristics = {
    "On-Demand Self-Service":
        "Users can provision computing resources when required.",

    "Broad Network Access":
        "Resources can be accessed through network-connected devices.",

    "Resource Pooling":
        "Providers maintain large pools of shared computing resources.",

    "Rapid Elasticity":
        "Resources can increase or decrease according to demand.",

    "Measured Service":
        "Resource usage can be measured for monitoring and billing."
}

for characteristic, explanation in characteristics.items():
    print(f"\n{characteristic}")
    print(f"  {explanation}")


# ================================================================
# SECTION 10: RESOURCE POOLING
# ================================================================

print_heading("9. Resource Pooling")

print("""
Cloud providers maintain extremely large pools of resources.

Examples include:

- CPU capacity
- Memory
- Storage
- Network bandwidth

Instead of dedicating an entire physical server to every customer,
resources can be allocated dynamically.

Simplified example:

PHYSICAL INFRASTRUCTURE
          |
          v
   RESOURCE POOL
     /    |    \\
    /     |     \\
Customer A Customer B Customer C

Cloud platforms use multiple technologies to ensure logical isolation
and proper allocation of resources.
""")


# ================================================================
# SECTION 11: MULTI-TENANCY
# ================================================================

print_heading("10. Multi-Tenancy")

print("""
Multi-tenancy means multiple customers can use shared underlying
infrastructure while remaining logically isolated.

Example:

Physical Infrastructure
          |
Virtualization / Isolation Layer
     /        |        \\
Tenant A    Tenant B    Tenant C

The provider must ensure:

- Security isolation
- Network isolation
- Data isolation
- Access control
- Fair resource allocation

Multi-tenancy is one of the important reasons cloud providers can
operate infrastructure efficiently at a large scale.
""")


# ================================================================
# SECTION 12: SCALABILITY
# ================================================================

print_heading("11. Scalability")

print("""
Scalability is the ability of a system to increase its capacity.

There are two primary approaches.

VERTICAL SCALING:

Increase the resources of one machine.

Example:

Before:
CPU = 4 cores
RAM = 8 GB

After:
CPU = 16 cores
RAM = 64 GB


HORIZONTAL SCALING:

Add additional machines.

Before:

Users
  |
Server


After:

Users
  |
Load Balancer
 /    |    \\
S1    S2    S3

Cloud infrastructure makes horizontal scaling easier to automate.
""")


# ================================================================
# SECTION 13: ELASTICITY
# ================================================================

print_heading("12. Elasticity")

print("""
Elasticity is related to scalability but is not exactly the same.

Scalability:
Ability to increase capacity.

Elasticity:
Ability to automatically adjust capacity according to demand.

Example:

Morning:
2 servers

Afternoon:
5 servers

Festival Sale:
100 servers

Night:
2 servers

The infrastructure adapts according to workload demand.
""")


class ElasticInfrastructure:

    def __init__(self, minimum_servers, maximum_servers):
        self.minimum_servers = minimum_servers
        self.maximum_servers = maximum_servers
        self.current_servers = minimum_servers

    def evaluate_load(self, users):

        print(f"\nCurrent User Load: {users}")

        required_servers = max(
            self.minimum_servers,
            min(
                self.maximum_servers,
                (users // 1000) + 1
            )
        )

        self.current_servers = required_servers

        print(f"Required Servers: {self.current_servers}")


print("\nELASTICITY SIMULATION")

elastic_system = ElasticInfrastructure(
    minimum_servers=2,
    maximum_servers=20
)

traffic_patterns = [
    100,
    900,
    2500,
    7000,
    15000,
    300
]

for traffic in traffic_patterns:
    elastic_system.evaluate_load(traffic)


# ================================================================
# SECTION 14: WHY ORGANIZATIONS ADOPT CLOUD
# ================================================================

print_heading("13. Reasons for Cloud Adoption")

adoption_reasons = {
    "Speed":
        "Infrastructure can be provisioned faster than traditional hardware procurement.",

    "Scalability":
        "Applications can increase capacity as usage grows.",

    "Elasticity":
        "Infrastructure can adapt to fluctuating workloads.",

    "Global Reach":
        "Applications can be deployed closer to users in different locations.",

    "Automation":
        "Infrastructure can be managed through APIs, scripts, and code.",

    "Managed Services":
        "Providers can operate certain infrastructure services for customers.",

    "Experimentation":
        "Teams can create temporary environments for testing and development.",

    "Disaster Recovery":
        "Data and infrastructure can be replicated across different locations.",

    "Modern Development":
        "Cloud platforms support containers, automation, CI/CD, and distributed systems."
}

for reason, explanation in adoption_reasons.items():
    print(f"\n{reason}")
    print(f"  {explanation}")


# ================================================================
# SECTION 15: CLOUD ECONOMICS
# ================================================================

print_heading("14. Cloud Economics")

print("""
Traditional infrastructure commonly involves CAPEX.

CAPEX means Capital Expenditure.

Example:

An organization purchases:

Servers = ₹10,00,000
Storage = ₹5,00,000
Networking = ₹3,00,000

Total upfront infrastructure investment:

₹18,00,000


Cloud infrastructure often uses a more consumption-oriented model.

Example:

Virtual Server:
₹X per hour

Storage:
₹Y per GB

Database:
₹Z per hour

The customer pays based on the pricing model of the service.

Important lesson:

Cloud does NOT automatically mean cheap.

Poorly managed cloud resources can become expensive.

Cloud cost management is an important engineering discipline.
""")


class CloudCostCalculator:

    def __init__(self):
        self.total_cost = 0

    def calculate_compute(self, hours, hourly_price):
        cost = hours * hourly_price
        self.total_cost += cost

        print(
            f"\nCompute Usage:"
            f"\nHours: {hours}"
            f"\nCost per Hour: ₹{hourly_price}"
            f"\nTotal Compute Cost: ₹{cost}"
        )

    def calculate_storage(self, storage_gb, price_per_gb):
        cost = storage_gb * price_per_gb
        self.total_cost += cost

        print(
            f"\nStorage Usage:"
            f"\nStorage: {storage_gb} GB"
            f"\nCost per GB: ₹{price_per_gb}"
            f"\nTotal Storage Cost: ₹{cost}"
        )

    def show_total(self):
        print(f"\nEstimated Total Cost: ₹{self.total_cost}")


print("\nCLOUD COST SIMULATION")

cost_calculator = CloudCostCalculator()

cost_calculator.calculate_compute(
    hours=100,
    hourly_price=10
)

cost_calculator.calculate_storage(
    storage_gb=500,
    price_per_gb=2
)

cost_calculator.show_total()


# ================================================================
# SECTION 16: BASIC CLOUD TERMINOLOGY
# ================================================================

print_heading("15. Basic Cloud Terminology")

cloud_terms = {
    "Cloud Provider":
        "An organization that provides cloud computing services.",

    "Region":
        "A geographic area containing cloud infrastructure.",

    "Availability Zone":
        "An isolated infrastructure location within a cloud region.",

    "Data Center":
        "A physical facility containing computing infrastructure.",

    "Virtual Machine":
        "A software-defined computer running on physical infrastructure.",

    "Instance":
        "A running virtual compute resource.",

    "Hypervisor":
        "Software that enables multiple virtual machines to run on physical hardware.",

    "Container":
        "A lightweight unit used to package applications and dependencies.",

    "Load Balancer":
        "A component that distributes traffic across multiple resources.",

    "Auto Scaling":
        "Automatic adjustment of infrastructure capacity.",

    "Object Storage":
        "Storage for data organized as objects.",

    "Block Storage":
        "Storage presented as blocks, commonly attached to virtual machines.",

    "Virtual Network":
        "A software-defined network created inside cloud infrastructure.",

    "API":
        "A programmatic interface used to communicate with cloud services.",

    "Infrastructure as Code":
        "Managing infrastructure using configuration files and code."
}

for term, definition in cloud_terms.items():
    print(f"\n{term}")
    print(f"  {definition}")


# ================================================================
# SECTION 17: CLOUD SERVICE MODELS
# ================================================================

print_heading("16. Cloud Service Models")

service_models = {
    "IaaS - Infrastructure as a Service":
        [
            "Virtual machines",
            "Storage",
            "Networking",
            "Customer manages more software layers"
        ],

    "PaaS - Platform as a Service":
        [
            "Managed application platforms",
            "Runtime environments",
            "Developer focuses more on application code"
        ],

    "SaaS - Software as a Service":
        [
            "Ready-to-use applications",
            "Provider manages most infrastructure and software"
        ],

    "FaaS - Function as a Service":
        [
            "Event-driven functions",
            "Infrastructure abstraction",
            "Function execution based on triggers"
        ]
}

for model, features in service_models.items():
    print(f"\n{model}")

    for feature in features:
        print(f"  - {feature}")


# ================================================================
# SECTION 18: CLOUD DEPLOYMENT MODELS
# ================================================================

print_heading("17. Cloud Deployment Models")

deployment_models = {
    "Public Cloud":
        "Infrastructure services operated by a cloud provider.",

    "Private Cloud":
        "Infrastructure dedicated to a single organization.",

    "Hybrid Cloud":
        "Combination of private infrastructure and public cloud services.",

    "Multi-Cloud":
        "Use of services from multiple cloud providers."
}

for model, explanation in deployment_models.items():
    print(f"\n{model}")
    print(f"  {explanation}")


# ================================================================
# SECTION 19: CLOUD INFRASTRUCTURE COMPONENTS
# ================================================================

print_heading("18. Core Cloud Infrastructure Components")

cloud_infrastructure = {
    "Compute": [
        "Virtual Machines",
        "Containers",
        "Serverless Functions"
    ],

    "Storage": [
        "Object Storage",
        "Block Storage",
        "File Storage"
    ],

    "Networking": [
        "Virtual Networks",
        "Subnets",
        "Route Tables",
        "Load Balancers",
        "DNS"
    ],

    "Databases": [
        "Relational Databases",
        "NoSQL Databases",
        "Caching Systems"
    ],

    "Security": [
        "Identity Management",
        "Access Control",
        "Encryption",
        "Security Monitoring"
    ],

    "Operations": [
        "Monitoring",
        "Logging",
        "Automation",
        "Backup",
        "Disaster Recovery"
    ]
}

for category, components in cloud_infrastructure.items():

    print(f"\n{category}")

    for component in components:
        print(f"  - {component}")


# ================================================================
# SECTION 20: CLOUD REGIONS AND AVAILABILITY ZONES
# ================================================================

print_heading("19. Regions and Availability Zones")

print("""
Cloud infrastructure is distributed geographically.

A simplified structure:

GLOBAL CLOUD PROVIDER
        |
        +-------------------------+
        | REGION A                |
        |   |                     |
        |   +-- AVAILABILITY ZONE |
        |   +-- AVAILABILITY ZONE |
        |   +-- AVAILABILITY ZONE |
        |                         |
        +-------------------------+
        |
        +-------------------------+
        | REGION B                |
        |   |                     |
        |   +-- AVAILABILITY ZONE |
        |   +-- AVAILABILITY ZONE |
        +-------------------------+

Organizations can use multiple infrastructure locations to improve
availability and reduce the impact of failures.
""")


# ================================================================
# SECTION 21: HIGH AVAILABILITY
# ================================================================

print_heading("20. High Availability")

print("""
A system with only one server has a potential single point of failure.

Example:

Users
  |
Server A

If Server A fails:

Application becomes unavailable.


A more resilient design:

Users
  |
Load Balancer
 /         \\
Server A   Server B

If Server A fails:

Traffic can be sent to Server B.

High availability commonly involves:

- Redundancy
- Load balancing
- Health checks
- Replication
- Failover
- Multiple availability zones
""")


# ================================================================
# SECTION 22: RELIABILITY
# ================================================================

print_heading("21. Reliability")

print("""
Reliability refers to the ability of a system to operate correctly
over time.

Cloud infrastructure engineers must consider:

- Hardware failures
- Network failures
- Software failures
- Human errors
- Configuration mistakes
- Security incidents

Modern cloud systems are often designed with the assumption that
failures WILL eventually occur.

This leads to an important infrastructure principle:

DESIGN FOR FAILURE.

Instead of asking:

"How do we ensure this server never fails?"

Modern infrastructure asks:

"What happens when this server fails?"
""")


# ================================================================
# SECTION 23: CLOUD SECURITY
# ================================================================

print_heading("22. Cloud Security Fundamentals")

security_concepts = [
    "Identity Management",
    "Authentication",
    "Authorization",
    "Least Privilege",
    "Network Security",
    "Encryption at Rest",
    "Encryption in Transit",
    "Secrets Management",
    "Logging",
    "Monitoring",
    "Incident Response"
]

for concept in security_concepts:
    print(f"- {concept}")


print("""
Cloud security depends heavily on configuration.

A cloud provider may provide secure infrastructure, but customers are
still responsible for configuring many aspects of their applications
and cloud environments correctly.
""")


# ================================================================
# SECTION 24: SHARED RESPONSIBILITY
# ================================================================

print_heading("23. Shared Responsibility Model")

print("""
Cloud security responsibilities are shared.

SIMPLIFIED EXAMPLE:

CLOUD PROVIDER:

- Physical data centers
- Physical hardware
- Core infrastructure

CUSTOMER:

- Users
- Permissions
- Application configuration
- Data security
- Application security

The exact responsibilities change depending on the cloud service model.

Generally:

IaaS:
Customer manages more.

PaaS:
Provider manages more infrastructure.

SaaS:
Provider manages most infrastructure and software.
""")


# ================================================================
# SECTION 25: CLOUD CONSOLES
# ================================================================

print_heading("24. Cloud Console Concepts")

print("""
A cloud console is usually a web-based interface that allows users
to manage cloud resources.

A cloud console may allow a user to:

- Create virtual machines
- Configure storage
- Create networks
- Manage databases
- Create users
- Configure permissions
- Monitor infrastructure
- View billing information

Conceptually:

WEB BROWSER
     |
     v
CLOUD CONSOLE
     |
     v
CLOUD MANAGEMENT PLATFORM
     |
     v
CLOUD INFRASTRUCTURE

Cloud consoles are useful for:

- Learning
- Experimentation
- Visual infrastructure management

However, large infrastructure environments are increasingly managed
through automation and APIs.
""")


# ================================================================
# SECTION 26: CLOUD APIS
# ================================================================

print_heading("25. Cloud APIs")

print("""
Cloud APIs allow software to communicate with cloud services.

Instead of manually clicking:

Create Server

A program can send a request to a cloud API.

Conceptually:

PYTHON PROGRAM
      |
      v
CLOUD API REQUEST
      |
      v
CLOUD PLATFORM
      |
      v
NEW SERVER CREATED

This enables automation.

Cloud APIs are the foundation of many infrastructure automation tools.
""")


# ================================================================
# SECTION 27: INFRASTRUCTURE AS CODE
# ================================================================

print_heading("26. Infrastructure as Code")

print("""
Infrastructure as Code means infrastructure is described and managed
using code or configuration files.

Traditional approach:

Engineer
   |
Manual Configuration
   |
Server

Infrastructure as Code:

Infrastructure Configuration
        |
Automation Tool
        |
Cloud API
        |
Cloud Infrastructure

Benefits include:

- Reproducibility
- Version control
- Automation
- Consistency
- Collaboration
- Faster deployment
""")


# ================================================================
# SECTION 28: CLOUD-NATIVE THINKING
# ================================================================

print_heading("27. Introduction to Cloud-Native Architecture")

print("""
Cloud-native applications are designed to take advantage of modern
cloud infrastructure.

Important principles include:

- Automation
- Scalability
- Elasticity
- Distributed systems
- Failure tolerance
- Containerization
- Continuous deployment
- Observability

Cloud-native applications are often designed with the assumption that:

SERVERS CAN FAIL
NETWORKS CAN FAIL
APPLICATIONS CAN FAIL

Therefore, systems should be capable of detecting and recovering from
failures.
""")


# ================================================================
# SECTION 29: CLOUD ARCHITECTURE EXAMPLE
# ================================================================

print_heading("28. Example of a Modern Cloud Architecture")

print("""
                      USERS
                        |
                        v
                     INTERNET
                        |
                        v
                       DNS
                        |
                        v
              CONTENT DELIVERY NETWORK
                        |
                        v
                  LOAD BALANCER
                  /           \\
                 /             \\
        APPLICATION SERVER    APPLICATION SERVER
                 \\             /
                  \\           /
                   APPLICATION
                        |
                        v
                      CACHE
                        |
                        v
                    DATABASE
                   /        \\
                  /          \\
            PRIMARY        REPLICA
                        |
                        v
                      BACKUP


SUPPORTING SERVICES:

- Identity Management
- Access Control
- Encryption
- Monitoring
- Logging
- Auto Scaling
- Disaster Recovery
""")


# ================================================================
# SECTION 30: ADVANCED CONCEPTS
# ================================================================

print_heading("29. Advanced Concepts You Will Explore Later")

advanced_topics = [
    "Virtualization",
    "Cloud Networking",
    "Software Defined Networking",
    "Containers",
    "Docker",
    "Kubernetes",
    "Serverless Computing",
    "Infrastructure as Code",
    "Terraform",
    "Configuration Management",
    "Ansible",
    "CI/CD",
    "DevOps",
    "Monitoring",
    "Observability",
    "Distributed Systems",
    "Microservices",
    "Event-Driven Architecture",
    "High Availability",
    "Fault Tolerance",
    "Disaster Recovery",
    "Site Reliability Engineering",
    "Hybrid Cloud",
    "Multi-Cloud",
    "Cloud Cost Optimization",
    "Cloud Security"
]

for number, topic in enumerate(advanced_topics, start=1):
    print(f"{number}. {topic}")


# ================================================================
# SECTION 31: FINAL KNOWLEDGE CHECK
# ================================================================

print_heading("30. Knowledge Check")

questions = [
    "What is cloud computing?",
    "How is cloud infrastructure different from traditional infrastructure?",
    "What problem does elasticity solve?",
    "What is the difference between scalability and elasticity?",
    "Why is virtualization important?",
    "What is multi-tenancy?",
    "What is an availability zone?",
    "What is the shared responsibility model?",
    "Why are cloud APIs important?",
    "What is Infrastructure as Code?"
]

for number, question in enumerate(questions, start=1):
    print(f"{number}. {question}")


# ================================================================
# SECTION 32: FINAL SUMMARY
# ================================================================

print_heading("31. Day 01 Summary")

summary = [
    "Cloud computing delivers computing resources as services.",
    "Cloud infrastructure still relies on physical infrastructure.",
    "Virtualization enabled efficient sharing of physical resources.",
    "Traditional infrastructure requires more physical capacity planning.",
    "Cloud resources can often be provisioned on demand.",
    "Resource pooling allows infrastructure to be shared efficiently.",
    "Multi-tenancy allows multiple customers to use shared infrastructure with isolation.",
    "Scalability increases system capacity.",
    "Elasticity adjusts capacity according to demand.",
    "Cloud infrastructure includes compute, storage, networking, databases, and security.",
    "Cloud systems can be distributed across regions and availability zones.",
    "High availability reduces the impact of infrastructure failures.",
    "Cloud security uses a shared responsibility model.",
    "Cloud consoles provide browser-based infrastructure management.",
    "Cloud APIs allow programmatic infrastructure management.",
    "Infrastructure as Code enables reproducible and automated infrastructure.",
    "Cloud-native systems are designed with automation and failure tolerance in mind."
]

for number, learning in enumerate(summary, start=1):
    print(f"{number}. {learning}")


print("\n" + "=" * 90)
print("DAY 01 COMPLETED: INTRODUCTION TO CLOUD COMPUTING")
print("=" * 90)

print("""
You have completed the foundational introduction to cloud computing.

The concepts learned here will support future topics involving:

Linux
Networking
Virtualization
Cloud Compute
Cloud Storage
Databases
Security
Docker
Kubernetes
Terraform
DevOps
Monitoring
Distributed Systems
Cloud Architecture
""")
```

