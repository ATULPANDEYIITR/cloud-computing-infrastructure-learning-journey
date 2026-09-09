"""
Cloud Architecture Fundamentals: Infrastructure Layers, Application Layers,
Service Dependencies, Architecture Patterns, and Draw.io-Compatible Diagrams.

This standalone script is both a study guide and an executable reference
implementation. It teaches cloud architecture from foundational concepts
through dependency modeling, architecture patterns, validation, reliability,
security, scalability, observability, cost considerations, and production
design.

The script uses only the Python standard library.

When executed, it:
1. Prints a structured educational guide.
2. Demonstrates cloud architecture concepts with executable Python models.
3. Builds and validates a sample three-tier cloud architecture.
4. Demonstrates service dependencies and dependency analysis.
5. Demonstrates common architecture patterns.
6. Demonstrates availability, scaling, security, and cost concepts.
7. Runs architecture validation checks.
8. Generates Draw.io-compatible .drawio XML architecture diagrams.

Generated files:
- cloud_architecture_three_tier.drawio
- cloud_architecture_event_driven.drawio
- cloud_architecture_microservices.drawio
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
from typing import Dict, Iterable, List, Optional, Set, Tuple
import math
import random
import statistics
import textwrap
import xml.etree.ElementTree as ET
from xml.dom import minidom


# =============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# =============================================================================

def print_section(title: str) -> None:
    """Print a visually consistent educational section heading."""
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


def print_subsection(title: str) -> None:
    """Print a subsection heading."""
    print("\n" + "-" * 88)
    print(title)
    print("-" * 88)


def explain(text: str) -> None:
    """Print wrapped educational text."""
    print(textwrap.fill(text, width=88))


def demonstrate(title: str, code_description: str) -> None:
    """Introduce an executable demonstration."""
    print(f"\n[DEMONSTRATION] {title}")
    print(f"  {code_description}")


def fundamentals() -> None:
    print_section("1. CLOUD ARCHITECTURE FUNDAMENTALS")

    concepts = {
        "Cloud computing": (
            "A model for obtaining computing resources such as compute, storage, "
            "networking, databases, and managed platforms on demand."
        ),
        "Cloud architecture": (
            "The structural organization of cloud resources, applications, data, "
            "network boundaries, service dependencies, security controls, and "
            "operational mechanisms."
        ),
        "Region": (
            "A geographic area containing one or more physically separate "
            "availability zones."
        ),
        "Availability Zone": (
            "An isolated infrastructure location inside a cloud region, designed "
            "to reduce the impact of failures affecting another zone."
        ),
        "Fault domain": (
            "A group of infrastructure that can fail together. Good architectures "
            "avoid placing critical replicas inside the same fault domain."
        ),
        "Resource": (
            "A provisioned cloud object such as a VM, subnet, bucket, database, "
            "load balancer, queue, or managed service."
        ),
        "Workload": (
            "A collection of applications, services, infrastructure, data, and "
            "operational processes that collectively perform a business function."
        ),
        "Service dependency": (
            "A relationship in which one component requires another component "
            "for some operation, such as an API depending on a database."
        ),
        "Control plane": (
            "The management layer used to provision, configure, monitor, and "
            "administer cloud resources."
        ),
        "Data plane": (
            "The runtime path through which actual application traffic and data "
            "flow."
        ),
        "Blast radius": (
            "The scope of impact when a component, dependency, zone, or configuration "
            "fails."
        ),
    }

    for name, definition in concepts.items():
        print(f"\n{name}:")
        explain(definition)

    print_subsection("Shared responsibility")

    explain(
        "Cloud security is divided between the provider and the customer. The "
        "provider generally operates physical facilities, physical networking, "
        "and portions of the managed infrastructure. The customer remains "
        "responsible for configuration, identities, application security, data "
        "protection, and other responsibilities depending on the service model."
    )

    print_subsection("Service models")

    models = [
        (
            "IaaS",
            "Infrastructure as a Service",
            "The customer manages more of the operating environment, including "
            "virtual machines, operating systems, and application software."
        ),
        (
            "PaaS",
            "Platform as a Service",
            "The provider manages more of the infrastructure and runtime platform, "
            "allowing the customer to concentrate on application code."
        ),
        (
            "SaaS",
            "Software as a Service",
            "A complete application is delivered as a managed service."
        ),
        (
            "Serverless",
            "Event-driven managed execution",
            "Infrastructure provisioning is largely abstracted while billing and "
            "execution commonly follow invocation or resource-consumption models."
        ),
    ]

    for acronym, name, description in models:
        print(f"\n{acronym} - {name}")
        explain(description)


# =============================================================================
# 2. ARCHITECTURE LAYERS
# =============================================================================

class ArchitectureLayer(Enum):
    """Logical layers used to classify architecture components."""

    EDGE = "Edge / Delivery"
    NETWORK = "Network"
    SECURITY = "Security"
    COMPUTE = "Compute"
    PLATFORM = "Application Platform"
    APPLICATION = "Application"
    DATA = "Data"
    INTEGRATION = "Integration"
    OBSERVABILITY = "Observability"
    OPERATIONS = "Operations"


@dataclass
class ArchitectureComponent:
    """Represents one logical cloud architecture component."""

    name: str
    component_type: str
    layer: ArchitectureLayer
    zone: Optional[str] = None
    public: bool = False
    stateful: bool = False
    scalable: bool = True
    description: str = ""


def architecture_layers() -> None:
    print_section("2. CLOUD ARCHITECTURE LAYERS")

    layer_explanations = {
        ArchitectureLayer.EDGE: (
            "DNS, CDN, edge routing, WAF, global traffic management, and other "
            "components close to the client."
        ),
        ArchitectureLayer.NETWORK: (
            "Virtual networks, subnets, route tables, gateways, firewalls, "
            "private endpoints, and network segmentation."
        ),
        ArchitectureLayer.SECURITY: (
            "Identity, access control, encryption, secrets, certificates, "
            "security monitoring, and policy enforcement."
        ),
        ArchitectureLayer.COMPUTE: (
            "Virtual machines, containers, Kubernetes nodes, serverless functions, "
            "and other execution environments."
        ),
        ArchitectureLayer.PLATFORM: (
            "API gateways, service meshes, container platforms, runtime services, "
            "configuration systems, and managed middleware."
        ),
        ArchitectureLayer.APPLICATION: (
            "Business services, APIs, web applications, background workers, "
            "administrative applications, and domain logic."
        ),
        ArchitectureLayer.DATA: (
            "Relational databases, NoSQL databases, object storage, caches, "
            "search indexes, data warehouses, and data lakes."
        ),
        ArchitectureLayer.INTEGRATION: (
            "Queues, event buses, streams, message brokers, workflow engines, "
            "and integration adapters."
        ),
        ArchitectureLayer.OBSERVABILITY: (
            "Metrics, logs, traces, alerts, dashboards, audit records, and "
            "application performance monitoring."
        ),
        ArchitectureLayer.OPERATIONS: (
            "Infrastructure as code, CI/CD, backups, disaster recovery, "
            "configuration management, and operational automation."
        ),
    }

    for layer, explanation in layer_explanations.items():
        print(f"\n{layer.value}")
        explain(explanation)

    print_subsection("Layering principle")

    explain(
        "Layers are a reasoning mechanism rather than an absolute law. A component "
        "can participate in multiple architectural concerns. The purpose of layers "
        "is to make boundaries and responsibilities visible. A well-designed "
        "architecture minimizes unnecessary coupling between layers and keeps "
        "security, operational, and data responsibilities explicit."
    )


# =============================================================================
# 3. NETWORKING AND INFRASTRUCTURE MODEL
# =============================================================================

@dataclass
class NetworkSegment:
    """A logical network segment."""

    name: str
    cidr: str
    public: bool
    availability_zone: Optional[str] = None
    purpose: str = ""


@dataclass
class SecurityRule:
    """Represents an abstract network security rule."""

    source: str
    destination: str
    protocol: str
    port: Optional[int]
    action: str = "ALLOW"


@dataclass
class InfrastructureModel:
    """Represents core infrastructure building blocks."""

    region: str
    availability_zones: List[str]
    segments: List[NetworkSegment] = field(default_factory=list)
    security_rules: List[SecurityRule] = field(default_factory=list)

    def add_segment(self, segment: NetworkSegment) -> None:
        self.segments.append(segment)

    def add_security_rule(self, rule: SecurityRule) -> None:
        self.security_rules.append(rule)

    def public_segments(self) -> List[NetworkSegment]:
        return [segment for segment in self.segments if segment.public]

    def private_segments(self) -> List[NetworkSegment]:
        return [segment for segment in self.segments if not segment.public]


def infrastructure_demo() -> InfrastructureModel:
    print_section("3. INFRASTRUCTURE LAYER DEMONSTRATION")

    infrastructure = InfrastructureModel(
        region="example-region",
        availability_zones=["az-a", "az-b"],
    )

    infrastructure.add_segment(
        NetworkSegment(
            name="public-a",
            cidr="10.0.1.0/24",
            public=True,
            availability_zone="az-a",
            purpose="Load balancer ingress",
        )
    )
    infrastructure.add_segment(
        NetworkSegment(
            name="public-b",
            cidr="10.0.2.0/24",
            public=True,
            availability_zone="az-b",
            purpose="Load balancer ingress",
        )
    )
    infrastructure.add_segment(
        NetworkSegment(
            name="application-a",
            cidr="10.0.11.0/24",
            public=False,
            availability_zone="az-a",
            purpose="Application workloads",
        )
    )
    infrastructure.add_segment(
        NetworkSegment(
            name="application-b",
            cidr="10.0.12.0/24",
            public=False,
            availability_zone="az-b",
            purpose="Application workloads",
        )
    )
    infrastructure.add_segment(
        NetworkSegment(
            name="data-a",
            cidr="10.0.21.0/24",
            public=False,
            availability_zone="az-a",
            purpose="Database and cache",
        )
    )
    infrastructure.add_segment(
        NetworkSegment(
            name="data-b",
            cidr="10.0.22.0/24",
            public=False,
            availability_zone="az-b",
            purpose="Database and cache",
        )
    )

    infrastructure.add_security_rule(
        SecurityRule(
            source="internet",
            destination="load-balancer",
            protocol="HTTPS",
            port=443,
        )
    )
    infrastructure.add_security_rule(
        SecurityRule(
            source="load-balancer",
            destination="application-tier",
            protocol="HTTP",
            port=8080,
        )
    )
    infrastructure.add_security_rule(
        SecurityRule(
            source="application-tier",
            destination="database",
            protocol="TCP",
            port=5432,
        )
    )

    print(f"Region: {infrastructure.region}")
    print(f"Availability zones: {', '.join(infrastructure.availability_zones)}")

    print("\nNetwork segments:")
    for segment in infrastructure.segments:
        visibility = "PUBLIC" if segment.public else "PRIVATE"
        print(
            f"  {segment.name:16} {segment.cidr:15} "
            f"{visibility:7} {segment.availability_zone:5} "
            f"{segment.purpose}"
        )

    print("\nSecurity rules:")
    for rule in infrastructure.security_rules:
        port = "*" if rule.port is None else str(rule.port)
        print(
            f"  {rule.action:5} {rule.source:20} -> "
            f"{rule.destination:20} {rule.protocol:6}:{port}"
        )

    return infrastructure


# =============================================================================
# 4. APPLICATION LAYERS
# =============================================================================

@dataclass
class ApplicationService:
    """Represents an application-level service."""

    name: str
    responsibility: str
    stateless: bool = True
    replicas: int = 1
    protocol: str = "HTTPS"
    port: Optional[int] = None


def application_layers_demo() -> List[ApplicationService]:
    print_section("4. APPLICATION LAYERS")

    services = [
        ApplicationService(
            name="Web Application",
            responsibility="Serve user-facing web requests",
            stateless=True,
            replicas=2,
            protocol="HTTPS",
            port=443,
        ),
        ApplicationService(
            name="API Service",
            responsibility="Expose business APIs",
            stateless=True,
            replicas=3,
            protocol="HTTP",
            port=8080,
        ),
        ApplicationService(
            name="Background Worker",
            responsibility="Process asynchronous jobs",
            stateless=True,
            replicas=2,
            protocol="Internal",
            port=None,
        ),
        ApplicationService(
            name="Order Database",
            responsibility="Persist transactional order data",
            stateless=False,
            replicas=2,
            protocol="TCP",
            port=5432,
        ),
        ApplicationService(
            name="Cache",
            responsibility="Reduce repeated database reads",
            stateless=False,
            replicas=2,
            protocol="TCP",
            port=6379,
        ),
    ]

    print(
        "A common application architecture separates presentation, business "
        "logic, asynchronous processing, and persistence."
    )

    for service in services:
        print(
            f"\n{service.name}\n"
            f"  Responsibility: {service.responsibility}\n"
            f"  Stateless: {service.stateless}\n"
            f"  Replicas: {service.replicas}\n"
            f"  Protocol: {service.protocol}\n"
            f"  Port: {service.port if service.port is not None else 'N/A'}"
        )

    print_subsection("Stateless versus stateful services")

    explain(
        "A stateless service does not require local process memory to retain user "
        "session state across requests. This makes horizontal scaling and replacement "
        "easier. Stateful components retain important state and therefore require "
        "careful replication, consistency, backup, failover, and recovery design."
    )

    return services


# =============================================================================
# 5. SERVICE DEPENDENCY GRAPH
# =============================================================================

@dataclass
class Dependency:
    """Represents a directed service dependency."""

    source: str
    target: str
    dependency_type: str = "runtime"
    mandatory: bool = True
    description: str = ""


class DependencyGraph:
    """
    Directed graph representing service dependencies.

    An edge A -> B means A depends on B.
    """

    def __init__(self) -> None:
        self.dependencies: Dict[str, List[Dependency]] = defaultdict(list)
        self.nodes: Set[str] = set()

    def add_service(self, service: str) -> None:
        self.nodes.add(service)

    def add_dependency(
        self,
        source: str,
        target: str,
        dependency_type: str = "runtime",
        mandatory: bool = True,
        description: str = "",
    ) -> None:
        self.add_service(source)
        self.add_service(target)
        self.dependencies[source].append(
            Dependency(
                source=source,
                target=target,
                dependency_type=dependency_type,
                mandatory=mandatory,
                description=description,
            )
        )

    def direct_dependencies(self, service: str) -> List[str]:
        return [dependency.target for dependency in self.dependencies.get(service, [])]

    def reverse_dependencies(self, service: str) -> List[str]:
        return [
            source
            for source, dependencies in self.dependencies.items()
            if any(dependency.target == service for dependency in dependencies)
        ]

    def transitive_dependencies(self, service: str) -> Set[str]:
        visited: Set[str] = set()
        queue = deque([service])

        while queue:
            current = queue.popleft()

            for target in self.direct_dependencies(current):
                if target not in visited:
                    visited.add(target)
                    queue.append(target)

        visited.discard(service)
        return visited

    def dependency_depth(self, service: str) -> int:
        levels = {service: 0}
        queue = deque([service])

        while queue:
            current = queue.popleft()
            current_level = levels[current]

            for target in self.direct_dependencies(current):
                if target not in levels:
                    levels[target] = current_level + 1
                    queue.append(target)

        return max(levels.values(), default=0)

    def find_cycles(self) -> List[List[str]]:
        """
        Find directed cycles using depth-first search.

        A cycle indicates circular runtime dependency. Some cycles are intentional,
        but they usually deserve explicit architectural review.
        """
        visiting: Set[str] = set()
        visited: Set[str] = set()
        cycles: List[List[str]] = []

        def visit(node: str, path: List[str]) -> None:
            if node in visiting:
                if node in path:
                    cycle_start = path.index(node)
                    cycles.append(path[cycle_start:] + [node])
                return

            if node in visited:
                return

            visiting.add(node)

            for target in self.direct_dependencies(node):
                visit(target, path + [node])

            visiting.remove(node)
            visited.add(node)

        for node in self.nodes:
            visit(node, [])

        unique_cycles: List[List[str]] = []
        signatures: Set[Tuple[str, ...]] = set()

        for cycle in cycles:
            canonical = tuple(sorted(cycle[:-1]))
            if canonical not in signatures:
                signatures.add(canonical)
                unique_cycles.append(cycle)

        return unique_cycles

    def critical_dependencies(self) -> Dict[str, int]:
        """
        Count how many services directly or transitively depend on each service.
        A high number indicates a potentially high blast radius.
        """
        counts = {node: 0 for node in self.nodes}

        for source in self.nodes:
            for dependency in self.transitive_dependencies(source):
                counts[dependency] += 1

        return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))

    def print_graph(self) -> None:
        print("\nService dependency graph:")
        for source in sorted(self.nodes):
            dependencies = self.dependencies.get(source, [])
            if not dependencies:
                print(f"  {source} -> [none]")
                continue

            for dependency in dependencies:
                mandatory = "mandatory" if dependency.mandatory else "optional"
                print(
                    f"  {source} -> {dependency.target} "
                    f"[{dependency.dependency_type}, {mandatory}]"
                )


def dependency_demo() -> DependencyGraph:
    print_section("5. SERVICE DEPENDENCIES")

    graph = DependencyGraph()

    graph.add_dependency(
        "Internet",
        "CDN",
        dependency_type="delivery",
        description="Client traffic reaches the edge layer",
    )
    graph.add_dependency(
        "CDN",
        "Load Balancer",
        dependency_type="routing",
    )
    graph.add_dependency(
        "Load Balancer",
        "API Service",
        dependency_type="runtime",
    )
    graph.add_dependency(
        "API Service",
        "Cache",
        dependency_type="runtime",
        mandatory=False,
    )
    graph.add_dependency(
        "API Service",
        "Order Database",
        dependency_type="runtime",
    )
    graph.add_dependency(
        "API Service",
        "Message Queue",
        dependency_type="async",
    )
    graph.add_dependency(
        "Background Worker",
        "Message Queue",
        dependency_type="async",
    )
    graph.add_dependency(
        "Background Worker",
        "Order Database",
        dependency_type="runtime",
    )
    graph.add_dependency(
        "API Service",
        "Identity Provider",
        dependency_type="authentication",
    )

    graph.print_graph()

    demonstrate(
        "Transitive dependencies",
        "The API service ultimately depends on all services reachable from it.",
    )
    print(
        "API transitive dependencies:",
        sorted(graph.transitive_dependencies("API Service")),
    )

    demonstrate(
        "Dependency depth",
        "Dependency depth approximates how many dependency layers exist below a service.",
    )
    print("API dependency depth:", graph.dependency_depth("API Service"))

    demonstrate(
        "Blast-radius analysis",
        "Services depended upon by many other services deserve stronger reliability controls.",
    )
    for service, count in graph.critical_dependencies().items():
        print(f"  {service:22} depended upon by {count} service(s)")

    demonstrate(
        "Cycle detection",
        "Circular dependencies can make deployments, startup, and failure recovery harder.",
    )
    print("Cycles:", graph.find_cycles() or "none")

    return graph


# =============================================================================
# 6. ARCHITECTURE PATTERNS
# =============================================================================

class ArchitecturePattern(Enum):
    THREE_TIER = "Three-tier"
    MONOLITH = "Monolith"
    MICROSERVICES = "Microservices"
    EVENT_DRIVEN = "Event-driven"
    SERVERLESS = "Serverless"
    CQRS = "CQRS"
    SAGA = "Saga"
    STRANGLER = "Strangler Fig"
    HUB_AND_SPOKE = "Hub-and-spoke"
    ACTIVE_ACTIVE = "Active-active"
    ACTIVE_PASSIVE = "Active-passive"


@dataclass
class PatternDescription:
    pattern: ArchitecturePattern
    structure: str
    strengths: List[str]
    tradeoffs: List[str]
    appropriate_when: List[str]


def architecture_patterns() -> None:
    print_section("6. CLOUD ARCHITECTURE PATTERNS")

    patterns = [
        PatternDescription(
            ArchitecturePattern.THREE_TIER,
            "Presentation -> application/business logic -> data",
            [
                "Clear separation of concerns",
                "Easy conceptual model",
                "Independent scaling of tiers",
            ],
            [
                "Can become tightly coupled if boundaries are weak",
                "May not suit highly asynchronous workloads",
            ],
            [
                "Business web applications",
                "CRUD-oriented systems",
                "Teams needing straightforward operational boundaries",
            ],
        ),
        PatternDescription(
            ArchitecturePattern.MONOLITH,
            "One deployable application containing multiple business capabilities",
            [
                "Simple deployment model",
                "Low network overhead between modules",
                "Easy local development for small systems",
            ],
            [
                "Scaling can be coarse-grained",
                "Large codebases can become difficult to change",
                "Failure boundaries can be broad",
            ],
            [
                "Small teams",
                "Early-stage products",
                "Applications with tightly coupled domain logic",
            ],
        ),
        PatternDescription(
            ArchitecturePattern.MICROSERVICES,
            "Multiple independently deployable services organized around business capabilities",
            [
                "Independent deployment",
                "Independent scaling",
                "Service-level ownership",
            ],
            [
                "Distributed-system complexity",
                "Network failures become application concerns",
                "Observability and operations become more important",
            ],
            [
                "Large systems with clear domain boundaries",
                "Independent scaling requirements",
                "Organizations able to support distributed operations",
            ],
        ),
        PatternDescription(
            ArchitecturePattern.EVENT_DRIVEN,
            "Producers publish events consumed asynchronously by other components",
            [
                "Loose temporal coupling",
                "Scalable asynchronous processing",
                "Natural integration mechanism",
            ],
            [
                "Eventual consistency",
                "Harder debugging",
                "Duplicate delivery must be handled",
            ],
            [
                "Notifications",
                "Order processing",
                "Streaming",
                "Workflow integration",
            ],
        ),
        PatternDescription(
            ArchitecturePattern.SERVERLESS,
            "Managed functions and services execute in response to events or requests",
            [
                "Reduced infrastructure management",
                "Automatic scaling",
                "Good fit for event-driven workloads",
            ],
            [
                "Cold starts may matter",
                "Execution limits can constrain workloads",
                "Distributed debugging can be difficult",
            ],
            [
                "Variable traffic",
                "Short-lived event processing",
                "Glue logic",
            ],
        ),
        PatternDescription(
            ArchitecturePattern.CQRS,
            "Separate command/write and query/read models",
            [
                "Read and write paths can scale independently",
                "Read models can be optimized for query workloads",
            ],
            [
                "Higher architectural complexity",
                "Synchronization and eventual consistency concerns",
            ],
            [
                "Read-heavy systems",
                "Complex query models",
                "Systems requiring independent read/write scaling",
            ],
        ),
        PatternDescription(
            ArchitecturePattern.SAGA,
            "Distributed business transaction coordinated through local transactions",
            [
                "Avoids distributed database transactions",
                "Supports long-running workflows",
            ],
            [
                "Compensation logic is complex",
                "Intermediate states must be understood",
            ],
            [
                "Distributed transactions",
                "Order/payment/inventory workflows",
            ],
        ),
        PatternDescription(
            ArchitecturePattern.STRANGLER,
            "Incrementally replace parts of a legacy system with new components",
            [
                "Lower migration risk",
                "Incremental modernization",
            ],
            [
                "Temporary architectural complexity",
                "Requires routing and boundary management",
            ],
            [
                "Legacy modernization",
                "Large systems that cannot be rewritten at once",
            ],
        ),
    ]

    for description in patterns:
        print(f"\n{description.pattern.value}")
        print(f"  Structure: {description.structure}")

        print("  Strengths:")
        for item in description.strengths:
            print(f"    - {item}")

        print("  Trade-offs:")
        for item in description.tradeoffs:
            print(f"    - {item}")

        print("  Appropriate when:")
        for item in description.appropriate_when:
            print(f"    - {item}")


# =============================================================================
# 7. RELIABILITY AND AVAILABILITY
# =============================================================================

@dataclass
class AvailabilityModel:
    """Simple independent-component availability model."""

    component_availabilities: Dict[str, float]

    def serial_availability(self, components: Iterable[str]) -> float:
        """
        Availability for a serial dependency path.

        If every component must be available, probabilities multiply under
        the simplifying assumption of statistical independence.
        """
        result = 1.0
        for component in components:
            result *= self.component_availabilities[component]
        return result

    def parallel_availability(self, components: Iterable[str]) -> float:
        """
        Availability for redundant components where at least one must work.

        This uses the independence approximation:
        P(at least one available) = 1 - product(P(each unavailable)).
        """
        unavailability = 1.0
        for component in components:
            unavailability *= 1.0 - self.component_availabilities[component]
        return 1.0 - unavailability


def reliability_demo() -> None:
    print_section("7. RELIABILITY AND AVAILABILITY")

    model = AvailabilityModel(
        {
            "Load Balancer": 0.9999,
            "API Instance A": 0.999,
            "API Instance B": 0.999,
            "Database": 0.9995,
        }
    )

    serial = model.serial_availability(
        ["Load Balancer", "API Instance A", "Database"]
    )

    parallel_api = model.parallel_availability(
        ["API Instance A", "API Instance B"]
    )

    print(f"Single-path availability approximation: {serial:.6%}")
    print(f"Two-instance API tier availability approximation: {parallel_api:.6%}")

    explain(
        "Availability calculations are useful for reasoning, but real cloud "
        "systems are not perfectly independent. Shared dependencies such as "
        "DNS, credentials, control-plane operations, network paths, or a common "
        "database can invalidate simple probability assumptions."
    )

    print_subsection("SLO terminology")

    terms = {
        "SLI": "A measured indicator such as request latency or successful request rate.",
        "SLO": "A target for an SLI, such as 99.9% successful requests.",
        "SLA": "A contractual commitment that may include service credits or other remedies.",
        "Error budget": "The amount of unreliability permitted by an SLO over a period.",
        "RTO": "Recovery Time Objective: how quickly service should be restored.",
        "RPO": "Recovery Point Objective: how much data loss is acceptable.",
    }

    for term, definition in terms.items():
        print(f"{term}: {definition}")


# =============================================================================
# 8. SCALABILITY
# =============================================================================

@dataclass
class ScalingPolicy:
    """Simple horizontal scaling policy."""

    minimum_instances: int
    maximum_instances: int
    target_utilization: float

    def desired_instances(
        self,
        current_instances: int,
        current_utilization: float,
    ) -> int:
        """
        Estimate the number of instances required to reach target utilization.

        This is deliberately simplified. Production autoscaling often considers
        multiple metrics, cooldown periods, queue depth, request rate, startup
        time, and predictive signals.
        """
        if current_utilization <= 0:
            return self.minimum_instances

        estimated = math.ceil(
            current_instances * current_utilization / self.target_utilization
        )

        return max(
            self.minimum_instances,
            min(self.maximum_instances, estimated),
        )


def scalability_demo() -> None:
    print_section("8. SCALABILITY")

    policy = ScalingPolicy(
        minimum_instances=2,
        maximum_instances=20,
        target_utilization=0.60,
    )

    for utilization in [0.20, 0.50, 0.60, 0.80, 1.00, 1.50]:
        desired = policy.desired_instances(4, utilization)
        print(
            f"Current instances=4, utilization={utilization:.0%} "
            f"-> desired instances={desired}"
        )

    print_subsection("Vertical versus horizontal scaling")

    explain(
        "Vertical scaling increases the capacity of one instance, such as giving "
        "a VM more CPU or memory. Horizontal scaling adds more instances. "
        "Horizontal scaling generally improves elasticity and fault isolation, "
        "but requires applications and data layers to support distributed operation."
    )

    print_subsection("Caching")

    explain(
        "Caching can reduce latency and database load by serving frequently accessed "
        "data from a faster layer. Important cache design questions include TTL, "
        "invalidation, consistency, cache stampede prevention, eviction policy, "
        "key design, and whether stale data is acceptable."
    )


# =============================================================================
# 9. SECURITY ARCHITECTURE
# =============================================================================

@dataclass
class SecurityControl:
    """Represents a security control."""

    name: str
    category: str
    objective: str


def security_demo() -> None:
    print_section("9. CLOUD SECURITY ARCHITECTURE")

    controls = [
        SecurityControl(
            "Identity and Access Management",
            "Identity",
            "Grant only the permissions required by users and workloads.",
        ),
        SecurityControl(
            "Network segmentation",
            "Network",
            "Limit which components can communicate with each other.",
        ),
        SecurityControl(
            "Encryption in transit",
            "Data protection",
            "Protect network traffic from interception.",
        ),
        SecurityControl(
            "Encryption at rest",
            "Data protection",
            "Protect persisted information from unauthorized access.",
        ),
        SecurityControl(
            "Secrets management",
            "Credential security",
            "Avoid embedding credentials in source code or images.",
        ),
        SecurityControl(
            "Audit logging",
            "Detection",
            "Provide evidence of important administrative and application actions.",
        ),
        SecurityControl(
            "WAF",
            "Application security",
            "Filter and inspect HTTP application traffic.",
        ),
        SecurityControl(
            "Backup and recovery",
            "Resilience",
            "Recover data after accidental deletion, corruption, or destructive events.",
        ),
    ]

    for control in controls:
        print(
            f"\n{control.name}\n"
            f"  Category: {control.category}\n"
            f"  Objective: {control.objective}"
        )

    print_subsection("Zero Trust principles")

    zero_trust = [
        "Do not assume trust based solely on network location.",
        "Authenticate and authorize explicitly.",
        "Apply least privilege.",
        "Continuously evaluate access and context.",
        "Segment resources to reduce blast radius.",
        "Record and monitor important access events.",
    ]

    for principle in zero_trust:
        print(f"  - {principle}")

    print_subsection("Security mistakes to avoid")

    mistakes = [
        "Putting databases directly on the public internet.",
        "Using one administrative identity for every workload.",
        "Hard-coding passwords or API keys in source code.",
        "Granting broad permissions when narrow permissions are sufficient.",
        "Treating a private subnet as an automatic security boundary.",
        "Ignoring audit logs and security alerting.",
        "Assuming encryption eliminates authorization requirements.",
    ]

    for mistake in mistakes:
        print(f"  - {mistake}")


# =============================================================================
# 10. OBSERVABILITY
# =============================================================================

@dataclass
class ObservabilitySignal:
    """Represents one observability signal."""

    name: str
    purpose: str


def observability_demo() -> None:
    print_section("10. OBSERVABILITY")

    signals = [
        ObservabilitySignal(
            "Metrics",
            "Numerical measurements such as latency, throughput, CPU utilization, and error rate.",
        ),
        ObservabilitySignal(
            "Logs",
            "Timestamped records describing events, decisions, errors, and state changes.",
        ),
        ObservabilitySignal(
            "Traces",
            "End-to-end representation of a request as it crosses multiple services.",
        ),
        ObservabilitySignal(
            "Alerts",
            "Automated notifications triggered when important conditions are detected.",
        ),
        ObservabilitySignal(
            "Audit events",
            "Security and administrative records showing who performed important actions.",
        ),
    ]

    for signal in signals:
        print(f"\n{signal.name}: {signal.purpose}")

    explain(
        "Distributed architectures require correlation identifiers so that one "
        "user request can be followed across gateways, services, queues, and data "
        "operations. Logging should avoid secrets, authentication tokens, and "
        "unnecessary personal data."
    )


# =============================================================================
# 11. DATA ARCHITECTURE
# =============================================================================

@dataclass
class DataStore:
    """Represents a data storage technology category."""

    name: str
    category: str
    strengths: List[str]
    concerns: List[str]


def data_architecture_demo() -> None:
    print_section("11. DATA ARCHITECTURE")

    stores = [
        DataStore(
            "Relational database",
            "SQL / transactional",
            [
                "Strong relational model",
                "Transactions",
                "Constraints and joins",
            ],
            [
                "Horizontal scaling can be complex",
                "Schema changes require discipline",
            ],
        ),
        DataStore(
            "Key-value / NoSQL database",
            "NoSQL",
            [
                "High-scale access patterns",
                "Flexible data models",
                "Potentially low-latency operations",
            ],
            [
                "Access patterns influence schema design",
                "Consistency and transaction models vary",
            ],
        ),
        DataStore(
            "Object storage",
            "Object",
            [
                "Durable large-object storage",
                "Good cost characteristics",
                "Useful for static assets and data lakes",
            ],
            [
                "Not a general transactional database",
                "Object-level access semantics differ from filesystems",
            ],
        ),
        DataStore(
            "Cache",
            "In-memory",
            [
                "Very low latency",
                "Reduces load on primary data stores",
            ],
            [
                "Data can become stale",
                "Eviction and invalidation must be designed",
            ],
        ),
        DataStore(
            "Search index",
            "Search",
            [
                "Fast text and filtered search",
                "Aggregations",
            ],
            [
                "Usually not the system of record",
                "Index consistency must be managed",
            ],
        ),
    ]

    for store in stores:
        print(f"\n{store.name} [{store.category}]")
        print("  Strengths:")
        for strength in store.strengths:
            print(f"    - {strength}")
        print("  Concerns:")
        for concern in store.concerns:
            print(f"    - {concern}")

    print_subsection("System of record")

    explain(
        "The system of record is the authoritative source for a particular business "
        "fact. Caches, search indexes, read models, and analytics stores often "
        "contain derived representations. Treating a derived store as authoritative "
        "without a clear consistency strategy can create data correctness problems."
    )


# =============================================================================
# 12. ASYNCHRONOUS ARCHITECTURE
# =============================================================================

@dataclass
class Message:
    """Simple message used in the queue demonstration."""

    message_id: str
    payload: str
    attempts: int = 0


class MessageQueue:
    """
    Simplified queue with retry and dead-letter behavior.

    Production queues have many more concerns: visibility timeout, ordering,
    retention, deduplication, partitioning, throughput, delivery guarantees,
    poison-message handling, and backpressure.
    """

    def __init__(self) -> None:
        self.messages: deque[Message] = deque()
        self.dead_letter_queue: List[Message] = []

    def publish(self, message: Message) -> None:
        self.messages.append(message)

    def consume(self) -> Optional[Message]:
        if not self.messages:
            return None
        return self.messages.popleft()

    def fail(self, message: Message, max_attempts: int = 3) -> None:
        message.attempts += 1

        if message.attempts >= max_attempts:
            self.dead_letter_queue.append(message)
        else:
            self.messages.append(message)


def asynchronous_demo() -> None:
    print_section("12. ASYNCHRONOUS AND EVENT-DRIVEN ARCHITECTURE")

    queue = MessageQueue()

    for index in range(1, 5):
        queue.publish(
            Message(
                message_id=f"job-{index}",
                payload=f"process-order-{index}",
            )
        )

    print("Initial queue size:", len(queue.messages))

    while queue.messages:
        message = queue.consume()
        if message is None:
            break

        print(f"Processing {message.message_id}: {message.payload}")

        # Deliberately fail one message to demonstrate retry behavior.
        if message.message_id == "job-3" and message.attempts < 2:
            print("  Processing failed; scheduling retry.")
            queue.fail(message)
        else:
            print("  Processing succeeded.")

    print("Dead-letter queue:", [message.message_id for message in queue.dead_letter_queue])

    print_subsection("Delivery semantics")

    semantics = {
        "At-most-once": (
            "A message is delivered zero or one time. Loss is possible, "
            "but duplicate processing is minimized."
        ),
        "At-least-once": (
            "A message is delivered one or more times. Consumers should "
            "be idempotent because duplicates can occur."
        ),
        "Exactly-once": (
            "Exactly-once processing is difficult in distributed systems. "
            "Claims of exactly-once usually depend on a specific boundary, "
            "transaction mechanism, or processing model."
        ),
    }

    for name, description in semantics.items():
        print(f"\n{name}:")
        explain(description)

    print_subsection("Idempotency")

    explain(
        "An operation is idempotent when repeating it produces the same intended "
        "final result as executing it once. Idempotency keys are commonly used "
        "for payment, order creation, provisioning, and other operations where "
        "retries can otherwise create duplicates."
    )


# =============================================================================
# 13. LOAD BALANCING
# =============================================================================

@dataclass
class Backend:
    """Simple load-balancer backend."""

    name: str
    healthy: bool = True
    request_count: int = 0


class RoundRobinLoadBalancer:
    """Simple round-robin load balancer."""

    def __init__(self, backends: List[Backend]) -> None:
        self.backends = backends
        self.index = 0

    def choose_backend(self) -> Backend:
        healthy_backends = [backend for backend in self.backends if backend.healthy]

        if not healthy_backends:
            raise RuntimeError("No healthy backends available.")

        backend = healthy_backends[self.index % len(healthy_backends)]
        self.index += 1
        backend.request_count += 1
        return backend


def load_balancer_demo() -> None:
    print_section("13. LOAD BALANCING")

    backends = [
        Backend("api-a"),
        Backend("api-b"),
        Backend("api-c"),
    ]

    load_balancer = RoundRobinLoadBalancer(backends)

    for request_number in range(1, 10):
        backend = load_balancer.choose_backend()
        print(f"Request {request_number:2} -> {backend.name}")

    print("\nRequest distribution:")
    for backend in backends:
        print(f"  {backend.name}: {backend.request_count}")

    backends[1].healthy = False
    print("\napi-b becomes unhealthy.")

    for request_number in range(10, 16):
        backend = load_balancer.choose_backend()
        print(f"Request {request_number:2} -> {backend.name}")

    explain(
        "Real load balancers may use weighted routing, least connections, "
        "latency-aware routing, health checks, connection draining, sticky "
        "sessions, or locality-aware routing. Sticky sessions can simplify "
        "legacy stateful applications but may reduce elasticity and fault tolerance."
    )


# =============================================================================
# 14. COST MODELING
# =============================================================================

@dataclass
class CostItem:
    """Simple monthly cost estimate."""

    name: str
    quantity: float
    unit_cost: float

    @property
    def monthly_cost(self) -> float:
        return self.quantity * self.unit_cost


class CostModel:
    """Simple additive cost model."""

    def __init__(self, items: Optional[List[CostItem]] = None) -> None:
        self.items = items or []

    def add(self, item: CostItem) -> None:
        self.items.append(item)

    @property
    def total(self) -> float:
        return sum(item.monthly_cost for item in self.items)

    def print_report(self) -> None:
        for item in self.items:
            print(
                f"{item.name:25} "
                f"quantity={item.quantity:8.2f} "
                f"unit=${item.unit_cost:8.2f} "
                f"monthly=${item.monthly_cost:10.2f}"
            )

        print(f"\nEstimated monthly total: ${self.total:,.2f}")


def cost_demo() -> None:
    print_section("14. CLOUD COST ARCHITECTURE")

    model = CostModel(
        [
            CostItem("Compute instances", 6, 40.00),
            CostItem("Managed database", 1, 180.00),
            CostItem("Object storage", 500, 0.02),
            CostItem("Load balancer", 1, 30.00),
            CostItem("Observability", 1, 50.00),
            CostItem("Message queue", 1, 15.00),
        ]
    )

    model.print_report()

    print_subsection("Cost drivers")

    drivers = [
        "Compute hours and instance sizes",
        "Database capacity and provisioned throughput",
        "Storage volume",
        "Data transfer",
        "Requests and API calls",
        "Log ingestion and retention",
        "Managed service tiers",
        "Backup and disaster recovery capacity",
        "Idle development and test environments",
    ]

    for driver in drivers:
        print(f"  - {driver}")

    explain(
        "Cloud cost optimization is an architectural concern. Reducing cost may "
        "involve right-sizing, autoscaling, lifecycle policies, caching, storage "
        "tiering, workload scheduling, reducing unnecessary data transfer, or "
        "selecting an appropriate managed-service model. Cost reduction should "
        "not violate availability, security, compliance, or performance requirements."
    )


# =============================================================================
# 15. ARCHITECTURE DECISION RECORDS
# =============================================================================

@dataclass
class ArchitectureDecision:
    """Represents an Architecture Decision Record."""

    title: str
    context: str
    decision: str
    consequences: List[str]


def adr_demo() -> None:
    print_section("15. ARCHITECTURE DECISION RECORD")

    decision = ArchitectureDecision(
        title="Use asynchronous processing for order notifications",
        context=(
            "Order creation should remain responsive even when notification "
            "providers are slow or temporarily unavailable."
        ),
        decision=(
            "Publish an OrderCreated event to a durable message system and "
            "process notifications asynchronously."
        ),
        consequences=[
            "Order creation is less coupled to notification latency.",
            "Notification delivery becomes eventually consistent.",
            "Consumers must handle retries and duplicate events.",
            "Operational monitoring must include queue depth and processing failures.",
        ],
    )

    print(f"Title: {decision.title}")
    print(f"\nContext: {decision.context}")
    print(f"\nDecision: {decision.decision}")
    print("\nConsequences:")
    for consequence in decision.consequences:
        print(f"  - {consequence}")


# =============================================================================
# 16. ARCHITECTURE VALIDATION
# =============================================================================

class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class ValidationIssue:
    """Architecture validation result."""

    severity: Severity
    component: str
    message: str


class ArchitectureValidator:
    """
    Static architecture checks.

    These rules are intentionally generic. Real organizations normally encode
    environment-specific security, compliance, reliability, networking, and
    cost policies in automated policy-as-code systems.
    """

    def validate_components(
        self,
        components: List[ArchitectureComponent],
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        names = [component.name for component in components]
        duplicates = {
            name for name in names
            if names.count(name) > 1
        }

        for duplicate in sorted(duplicates):
            issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    duplicate,
                    "Component name is duplicated.",
                )
            )

        for component in components:
            if component.layer == ArchitectureLayer.DATA and component.public:
                issues.append(
                    ValidationIssue(
                        Severity.ERROR,
                        component.name,
                        "Data-store components should not normally be public.",
                    )
                )

            if component.stateful and component.scalable:
                issues.append(
                    ValidationIssue(
                        Severity.INFO,
                        component.name,
                        "Stateful scaling requires explicit replication and consistency design.",
                    )
                )

        return issues

    def validate_dependencies(
        self,
        graph: DependencyGraph,
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        for cycle in graph.find_cycles():
            issues.append(
                ValidationIssue(
                    Severity.WARNING,
                    "Dependency Graph",
                    f"Circular dependency detected: {' -> '.join(cycle)}",
                )
            )

        critical = graph.critical_dependencies()

        for service, count in critical.items():
            if count >= 3:
                issues.append(
                    ValidationIssue(
                        Severity.WARNING,
                        service,
                        f"High dependency fan-in: {count} services depend on this component.",
                    )
                )

        return issues

    def print_issues(self, issues: List[ValidationIssue]) -> None:
        if not issues:
            print("No validation issues detected.")
            return

        for issue in issues:
            print(
                f"[{issue.severity.value:7}] "
                f"{issue.component:25} {issue.message}"
            )


def validation_demo(graph: DependencyGraph) -> None:
    print_section("16. ARCHITECTURE VALIDATION")

    components = [
        ArchitectureComponent(
            "CDN",
            "Content Delivery Network",
            ArchitectureLayer.EDGE,
            public=True,
        ),
        ArchitectureComponent(
            "Load Balancer",
            "Application Load Balancer",
            ArchitectureLayer.EDGE,
            public=True,
        ),
        ArchitectureComponent(
            "API Service",
            "Containerized API",
            ArchitectureLayer.APPLICATION,
            public=False,
        ),
        ArchitectureComponent(
            "Order Database",
            "Relational Database",
            ArchitectureLayer.DATA,
            public=False,
            stateful=True,
            scalable=False,
        ),
        ArchitectureComponent(
            "Cache",
            "Distributed Cache",
            ArchitectureLayer.DATA,
            public=False,
            stateful=True,
            scalable=True,
        ),
    ]

    validator = ArchitectureValidator()

    component_issues = validator.validate_components(components)
    dependency_issues = validator.validate_dependencies(graph)

    print("Component validation:")
    validator.print_issues(component_issues)

    print("\nDependency validation:")
    validator.print_issues(dependency_issues)


# =============================================================================
# 17. DRAW.IO XML GENERATION
# =============================================================================

@dataclass
class DiagramNode:
    """Node used by the Draw.io diagram generator."""

    node_id: str
    label: str
    x: float
    y: float
    width: float = 180
    height: float = 60
    style: str = ""


@dataclass
class DiagramEdge:
    """Edge used by the Draw.io diagram generator."""

    edge_id: str
    source: str
    target: str
    label: str = ""
    style: str = ""


class DrawioDiagram:
    """
    Minimal Draw.io-compatible XML generator.

    The generated XML follows the mxGraphModel structure understood by Draw.io.
    It can be opened as a .drawio file and edited visually.
    """

    DEFAULT_NODE_STYLE = (
        "rounded=1;whiteSpace=wrap;html=1;"
        "strokeWidth=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"
    )

    DEFAULT_EDGE_STYLE = (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;"
        "jettySize=auto;html=1;"
        "endArrow=block;endFill=1;"
    )

    CONTAINER_STYLE = (
        "rounded=1;whiteSpace=wrap;html=1;"
        "container=1;collapsible=0;recursiveResize=0;"
        "fillColor=#f5f5f5;strokeColor=#666666;"
        "fontStyle=1;verticalAlign=top;align=left;"
        "spacingTop=8;"
    )

    def __init__(self, diagram_name: str) -> None:
        self.diagram_name = diagram_name
        self.nodes: List[DiagramNode] = []
        self.edges: List[DiagramEdge] = []
        self.containers: List[DiagramNode] = []

    def add_node(self, node: DiagramNode) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: DiagramEdge) -> None:
        self.edges.append(edge)

    def add_container(self, container: DiagramNode) -> None:
        self.containers.append(container)

    def _cell(
        self,
        parent: ET.Element,
        cell_id: str,
        value: str,
        style: str,
        vertex: Optional[bool] = None,
        edge: Optional[bool] = None,
        parent_id: str = "1",
    ) -> ET.Element:
        attributes = {
            "id": cell_id,
            "value": value,
            "style": style,
            "parent": parent_id,
        }

        if vertex is not None:
            attributes["vertex"] = "1" if vertex else "0"

        if edge is not None:
            attributes["edge"] = "1" if edge else "0"

        return ET.SubElement(parent, "mxCell", attributes)

    def build_xml(self) -> str:
        mx_graph_model = ET.Element(
            "mxGraphModel",
            {
                "dx": "1200",
                "dy": "800",
                "grid": "1",
                "gridSize": "10",
                "guides": "1",
                "tooltips": "1",
                "connect": "1",
                "arrows": "1",
                "fold": "1",
                "page": "1",
                "pageScale": "1",
                "pageWidth": "1600",
                "pageHeight": "1200",
                "math": "0",
                "shadow": "0",
            },
        )

        root = ET.SubElement(mx_graph_model, "root")

        ET.SubElement(root, "mxCell", {"id": "0"})
        ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

        for container in self.containers:
            cell = self._cell(
                root,
                container.node_id,
                container.label,
                container.style or self.CONTAINER_STYLE,
                vertex=True,
            )

            geometry = ET.SubElement(
                cell,
                "mxGeometry",
                {
                    "x": str(container.x),
                    "y": str(container.y),
                    "width": str(container.width),
                    "height": str(container.height),
                    "as": "geometry",
                },
            )
            geometry.set("relative", "0")

        for node in self.nodes:
            cell = self._cell(
                root,
                node.node_id,
                node.label,
                node.style or self.DEFAULT_NODE_STYLE,
                vertex=True,
            )

            ET.SubElement(
                cell,
                "mxGeometry",
                {
                    "x": str(node.x),
                    "y": str(node.y),
                    "width": str(node.width),
                    "height": str(node.height),
                    "as": "geometry",
                },
            )

        for edge in self.edges:
            cell = self._cell(
                root,
                edge.edge_id,
                edge.label,
                edge.style or self.DEFAULT_EDGE_STYLE,
                edge=False,
                vertex=None,
                parent_id="1",
            )

            cell.set("source", edge.source)
            cell.set("target", edge.target)

            geometry = ET.SubElement(
                cell,
                "mxGeometry",
                {
                    "relative": "1",
                    "as": "geometry",
                },
            )

        model_xml = ET.tostring(mx_graph_model, encoding="utf-8")

        document = ET.Element(
            "mxfile",
            {
                "host": "app.diagrams.net",
                "modified": "2026-09-09T00:00:00.000Z",
                "agent": "Cloud Architecture Fundamentals Study Script",
                "version": "24.7.17",
                "type": "device",
            },
        )

        diagram = ET.SubElement(
            document,
            "diagram",
            {"id": "cloud-architecture", "name": self.diagram_name},
        )

        # Draw.io expects the mxGraphModel content in the diagram element.
        diagram.append(ET.fromstring(model_xml))

        rough_xml = ET.tostring(document, encoding="utf-8")
        parsed = minidom.parseString(rough_xml)

        return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

    def save(self, filename: str) -> None:
        with open(filename, "w", encoding="utf-8") as file:
            file.write(self.build_xml())


def drawio_style_for_layer(layer: ArchitectureLayer) -> str:
    """Return a visual style associated with a logical architecture layer."""
    styles = {
        ArchitectureLayer.EDGE: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#fff2cc;strokeColor=#d6b656;"
        ),
        ArchitectureLayer.NETWORK: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#d5e8d4;strokeColor=#82b366;"
        ),
        ArchitectureLayer.SECURITY: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#f8cecc;strokeColor=#b85450;"
        ),
        ArchitectureLayer.COMPUTE: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#dae8fc;strokeColor=#6c8ebf;"
        ),
        ArchitectureLayer.APPLICATION: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#e1d5e7;strokeColor=#9673a6;"
        ),
        ArchitectureLayer.DATA: (
            "shape=cylinder;whiteSpace=wrap;html=1;"
            "boundedLbls=1;fillColor=#d5e8d4;strokeColor=#82b366;"
        ),
        ArchitectureLayer.INTEGRATION: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#ffe6cc;strokeColor=#d79b00;"
        ),
        ArchitectureLayer.OBSERVABILITY: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#f5f5f5;strokeColor=#666666;"
        ),
        ArchitectureLayer.OPERATIONS: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#f5f5f5;strokeColor=#666666;"
        ),
        ArchitectureLayer.PLATFORM: (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#dae8fc;strokeColor=#6c8ebf;"
        ),
    }

    return styles.get(
        layer,
        DrawioDiagram.DEFAULT_NODE_STYLE,
    )


def create_three_tier_drawio(filename: str) -> None:
    """
    Create a Draw.io-compatible three-tier architecture diagram.

    Architecture:
        Users -> CDN/WAF -> Load Balancer
                 -> Application instances
                 -> Cache
                 -> Database
                 -> Queue -> Worker
    """

    diagram = DrawioDiagram("Three-Tier Cloud Architecture")

    diagram.add_container(
        DiagramNode(
            "network-boundary",
            "Cloud Region",
            20,
            20,
            1100,
            650,
            style=(
                "rounded=1;whiteSpace=wrap;html=1;"
                "container=1;collapsible=0;recursiveResize=0;"
                "fillColor=#f5f5f5;strokeColor=#666666;"
                "fontStyle=1;verticalAlign=top;align=left;spacingTop=8;"
            ),
        )
    )

    nodes = [
        DiagramNode(
            "users",
            "Users",
            60,
            100,
            style=(
                "ellipse;whiteSpace=wrap;html=1;"
                "fillColor=#fff2cc;strokeColor=#d6b656;"
            ),
        ),
        DiagramNode(
            "cdn",
            "CDN + WAF",
            280,
            100,
            style=drawio_style_for_layer(ArchitectureLayer.EDGE),
        ),
        DiagramNode(
            "lb",
            "Load Balancer",
            500,
            100,
            style=drawio_style_for_layer(ArchitectureLayer.EDGE),
        ),
        DiagramNode(
            "api-a",
            "API Service A",
            390,
            250,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "api-b",
            "API Service B",
            610,
            250,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "cache",
            "Distributed Cache",
            230,
            420,
            style=drawio_style_for_layer(ArchitectureLayer.DATA),
        ),
        DiagramNode(
            "database",
            "Relational Database",
            500,
            420,
            style=drawio_style_for_layer(ArchitectureLayer.DATA),
        ),
        DiagramNode(
            "queue",
            "Message Queue",
            770,
            420,
            style=drawio_style_for_layer(ArchitectureLayer.INTEGRATION),
        ),
        DiagramNode(
            "worker",
            "Background Worker",
            770,
            550,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
    ]

    for node in nodes:
        diagram.add_node(node)

    edges = [
        DiagramEdge("e1", "users", "cdn", "HTTPS"),
        DiagramEdge("e2", "cdn", "lb", "HTTPS"),
        DiagramEdge("e3", "lb", "api-a", "HTTP"),
        DiagramEdge("e4", "lb", "api-b", "HTTP"),
        DiagramEdge("e5", "api-a", "cache", "read/write"),
        DiagramEdge("e6", "api-b", "cache", "read/write"),
        DiagramEdge("e7", "api-a", "database", "SQL"),
        DiagramEdge("e8", "api-b", "database", "SQL"),
        DiagramEdge("e9", "api-a", "queue", "publish"),
        DiagramEdge("e10", "api-b", "queue", "publish"),
        DiagramEdge("e11", "queue", "worker", "consume"),
        DiagramEdge("e12", "worker", "database", "SQL"),
    ]

    for edge in edges:
        diagram.add_edge(edge)

    diagram.save(filename)


def create_event_driven_drawio(filename: str) -> None:
    """Create an event-driven architecture diagram."""

    diagram = DrawioDiagram("Event-Driven Cloud Architecture")

    nodes = [
        DiagramNode(
            "client",
            "Client",
            40,
            220,
            style=(
                "ellipse;whiteSpace=wrap;html=1;"
                "fillColor=#fff2cc;strokeColor=#d6b656;"
            ),
        ),
        DiagramNode(
            "api",
            "API Gateway",
            230,
            220,
            style=drawio_style_for_layer(ArchitectureLayer.EDGE),
        ),
        DiagramNode(
            "order",
            "Order Service",
            450,
            140,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "eventbus",
            "Event Bus",
            680,
            220,
            style=drawio_style_for_layer(ArchitectureLayer.INTEGRATION),
        ),
        DiagramNode(
            "inventory",
            "Inventory Consumer",
            920,
            100,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "notification",
            "Notification Consumer",
            920,
            220,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "analytics",
            "Analytics Consumer",
            920,
            340,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "database",
            "Order Database",
            450,
            360,
            style=drawio_style_for_layer(ArchitectureLayer.DATA),
        ),
    ]

    for node in nodes:
        diagram.add_node(node)

    edges = [
        DiagramEdge("e1", "client", "api", "HTTPS"),
        DiagramEdge("e2", "api", "order", "request"),
        DiagramEdge("e3", "order", "database", "transaction"),
        DiagramEdge("e4", "order", "eventbus", "OrderCreated"),
        DiagramEdge("e5", "eventbus", "inventory", "event"),
        DiagramEdge("e6", "eventbus", "notification", "event"),
        DiagramEdge("e7", "eventbus", "analytics", "event"),
    ]

    for edge in edges:
        diagram.add_edge(edge)

    diagram.save(filename)


def create_microservices_drawio(filename: str) -> None:
    """Create a microservices architecture diagram."""

    diagram = DrawioDiagram("Microservices Architecture")

    nodes = [
        DiagramNode(
            "client",
            "Web / Mobile Clients",
            50,
            260,
            style=(
                "ellipse;whiteSpace=wrap;html=1;"
                "fillColor=#fff2cc;strokeColor=#d6b656;"
            ),
        ),
        DiagramNode(
            "gateway",
            "API Gateway",
            270,
            260,
            style=drawio_style_for_layer(ArchitectureLayer.EDGE),
        ),
        DiagramNode(
            "orders",
            "Order Service",
            520,
            100,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "payments",
            "Payment Service",
            520,
            220,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "catalog",
            "Catalog Service",
            520,
            340,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "users",
            "User Service",
            520,
            460,
            style=drawio_style_for_layer(ArchitectureLayer.APPLICATION),
        ),
        DiagramNode(
            "orderdb",
            "Order DB",
            800,
            70,
            style=drawio_style_for_layer(ArchitectureLayer.DATA),
        ),
        DiagramNode(
            "paymentdb",
            "Payment DB",
            800,
            190,
            style=drawio_style_for_layer(ArchitectureLayer.DATA),
        ),
        DiagramNode(
            "catalogdb",
            "Catalog DB",
            800,
            310,
            style=drawio_style_for_layer(ArchitectureLayer.DATA),
        ),
        DiagramNode(
            "userdb",
            "User DB",
            800,
            430,
            style=drawio_style_for_layer(ArchitectureLayer.DATA),
        ),
        DiagramNode(
            "bus",
            "Event Bus",
            1040,
            260,
            style=drawio_style_for_layer(ArchitectureLayer.INTEGRATION),
        ),
    ]

    for node in nodes:
        diagram.add_node(node)

    edges = [
        DiagramEdge("e1", "client", "gateway", "HTTPS"),
        DiagramEdge("e2", "gateway", "orders", "REST"),
        DiagramEdge("e3", "gateway", "payments", "REST"),
        DiagramEdge("e4", "gateway", "catalog", "REST"),
        DiagramEdge("e5", "gateway", "users", "REST"),
        DiagramEdge("e6", "orders", "orderdb", "SQL"),
        DiagramEdge("e7", "payments", "paymentdb", "SQL"),
        DiagramEdge("e8", "catalog", "catalogdb", "SQL"),
        DiagramEdge("e9", "users", "userdb", "SQL"),
        DiagramEdge("e10", "orders", "bus", "events"),
        DiagramEdge("e11", "payments", "bus", "events"),
        DiagramEdge("e12", "catalog", "bus", "events"),
        DiagramEdge("e13", "users", "bus", "events"),
    ]

    for edge in edges:
        diagram.add_edge(edge)

    diagram.save(filename)


def drawio_demo() -> None:
    print_section("17. DRAW.IO ARCHITECTURE DIAGRAM GENERATION")

    files = [
        "cloud_architecture_three_tier.drawio",
        "cloud_architecture_event_driven.drawio",
        "cloud_architecture_microservices.drawio",
    ]

    create_three_tier_drawio(files[0])
    create_event_driven_drawio(files[1])
    create_microservices_drawio(files[2])

    for filename in files:
        print(f"Created: {filename}")

    explain(
        "The generated files use Draw.io's mxGraph XML structure. They can be "
        "opened in diagrams.net / Draw.io and then edited visually. A useful "
        "architecture diagram should communicate boundaries, traffic direction, "
        "dependencies, redundancy, trust zones, and important data stores without "
        "turning every implementation detail into a visual element."
    )

    print_subsection("Draw.io diagram conventions")

    conventions = [
        "Use containers to represent regions, networks, accounts, environments, or trust boundaries.",
        "Use arrows to show traffic or dependency direction.",
        "Label important protocols such as HTTPS, SQL, events, or message delivery.",
        "Use separate visual groupings for public, private, application, and data components.",
        "Show redundancy when high availability is an explicit requirement.",
        "Avoid crossing lines when layout can be improved.",
        "Do not use decorative icons when they obscure the architectural relationship.",
        "Keep diagrams at an appropriate abstraction level.",
        "Use different diagrams for context, container, component, and deployment views when one diagram becomes overloaded.",
    ]

    for convention in conventions:
        print(f"  - {convention}")


# =============================================================================
# 18. DIAGRAM ABSTRACTION LEVELS
# =============================================================================

def diagram_levels_demo() -> None:
    print_section("18. ARCHITECTURE DIAGRAM ABSTRACTION LEVELS")

    levels = [
        (
            "Context diagram",
            "Shows users, external systems, and the system being designed.",
        ),
        (
            "Container diagram",
            "Shows major applications, services, databases, queues, and external dependencies.",
        ),
        (
            "Component diagram",
            "Shows internal components of an application or service.",
        ),
        (
            "Deployment diagram",
            "Shows runtime placement across regions, zones, hosts, containers, or nodes.",
        ),
        (
            "Data-flow diagram",
            "Emphasizes movement of data between systems and trust boundaries.",
        ),
        (
            "Network diagram",
            "Emphasizes networks, subnets, routes, gateways, and security boundaries.",
        ),
    ]

    for level, purpose in levels:
        print(f"\n{level}:")
        explain(purpose)

    explain(
        "A diagram is effective when its abstraction level matches the question. "
        "A leadership audience may need a context diagram, while an operations "
        "team may need a deployment or network diagram. Combining every level into "
        "one drawing usually decreases readability."
    )


# =============================================================================
# 19. PRODUCTION DESIGN CHECKLIST
# =============================================================================

def production_checklist() -> None:
    print_section("19. PRODUCTION ARCHITECTURE CHECKLIST")

    checklist = {
        "Requirements": [
            "Identify business-critical workflows.",
            "Define latency, throughput, availability, and recovery targets.",
            "Identify data classification and regulatory requirements.",
            "Identify expected traffic patterns and growth.",
        ],
        "Networking": [
            "Separate public and private resources where appropriate.",
            "Define ingress and egress paths.",
            "Minimize unnecessary network exposure.",
            "Document important routes and dependencies.",
        ],
        "Security": [
            "Use least-privilege identities.",
            "Protect secrets.",
            "Encrypt sensitive data.",
            "Enable audit logging.",
            "Review public exposure.",
        ],
        "Reliability": [
            "Remove unnecessary single points of failure.",
            "Distribute critical replicas across fault domains.",
            "Test backup restoration.",
            "Define and test disaster recovery procedures.",
        ],
        "Scalability": [
            "Prefer horizontal scaling for stateless workloads where appropriate.",
            "Define scaling signals.",
            "Test peak load.",
            "Design stateful services around explicit capacity and replication constraints.",
        ],
        "Operations": [
            "Automate provisioning.",
            "Use repeatable deployment processes.",
            "Monitor health and business metrics.",
            "Create actionable alerts.",
            "Maintain rollback and recovery procedures.",
        ],
        "Cost": [
            "Measure major cost drivers.",
            "Right-size resources.",
            "Remove idle resources.",
            "Control log and data retention.",
            "Evaluate managed-service economics against operational complexity.",
        ],
        "Architecture governance": [
            "Document major decisions.",
            "Review dependency changes.",
            "Keep diagrams synchronized with deployed architecture.",
            "Use architecture standards consistently without forcing inappropriate patterns.",
        ],
    }

    for category, items in checklist.items():
        print(f"\n{category}")
        for item in items:
            print(f"  [ ] {item}")


# =============================================================================
# 20. COMMON ARCHITECTURAL MISTAKES
# =============================================================================

def common_mistakes() -> None:
    print_section("20. COMMON ARCHITECTURAL MISTAKES")

    mistakes = [
        (
            "Starting with products instead of requirements",
            "Technology choices should follow business, reliability, security, "
            "performance, and operational requirements."
        ),
        (
            "Overusing microservices",
            "A distributed architecture introduces network failures, deployment "
            "coordination, observability requirements, and data consistency challenges."
        ),
        (
            "Treating a queue as a database",
            "Messaging infrastructure is designed around delivery and processing "
            "semantics rather than arbitrary long-term transactional storage."
        ),
        (
            "Putting state into horizontally scaled instances",
            "Local state can make load balancing, failover, and autoscaling unreliable "
            "unless session affinity or another state strategy is deliberately used."
        ),
        (
            "Ignoring asynchronous failure",
            "Events and messages can be delayed, duplicated, reordered, or rejected."
        ),
        (
            "Assuming private means secure",
            "Private networking reduces exposure but does not replace identity, "
            "authorization, encryption, monitoring, or secure configuration."
        ),
        (
            "Creating a single giant diagram",
            "One diagram cannot simultaneously optimize for every audience and abstraction level."
        ),
        (
            "Failing to model external dependencies",
            "Third-party APIs, identity providers, payment gateways, and DNS can be "
            "critical dependencies even when they are outside the organization's infrastructure."
        ),
        (
            "Ignoring data consistency",
            "Distributed replicas and asynchronous systems require explicit decisions "
            "about consistency, ordering, conflict resolution, and recovery."
        ),
    ]

    for mistake, explanation_text in mistakes:
        print(f"\n{mistake}")
        explain(explanation_text)


# =============================================================================
# 21. TRADE-OFF ANALYSIS
# =============================================================================

def tradeoff_demo() -> None:
    print_section("21. ARCHITECTURAL TRADE-OFFS")

    comparisons = [
        (
            "Synchronous API call",
            "Immediate response and simpler request flow",
            "Tighter temporal coupling and sensitivity to downstream latency",
        ),
        (
            "Asynchronous messaging",
            "Loose temporal coupling and better buffering",
            "Eventual consistency, retries, duplicate handling, and harder debugging",
        ),
        (
            "Single relational database",
            "Simple consistency model and transactions",
            "Potential scaling and failure-domain constraints",
        ),
        (
            "Database per service",
            "Strong service ownership and isolation",
            "Cross-service data access and distributed transaction complexity",
        ),
        (
            "Managed service",
            "Reduced operational burden",
            "Potential vendor coupling and service-specific constraints",
        ),
        (
            "Self-managed infrastructure",
            "Greater control and customization",
            "Higher operational responsibility",
        ),
        (
            "Multi-region active-active",
            "Potentially strong geographic resilience and low regional dependency",
            "High complexity involving data replication, routing, consistency, and operations",
        ),
        (
            "Multi-region active-passive",
            "Simpler failover and data consistency model",
            "Failover delay and potentially lower resource utilization",
        ),
    ]

    print(
        f"{'Approach':30} {'Primary benefit':45} Trade-off"
    )
    print("-" * 120)

    for approach, benefit, tradeoff in comparisons:
        print(f"{approach:30} {benefit:45} {tradeoff}")


# =============================================================================
# 22. CAP AND CONSISTENCY
# =============================================================================

def consistency_demo() -> None:
    print_section("22. DISTRIBUTED CONSISTENCY")

    explain(
        "Distributed systems frequently require trade-offs among consistency, "
        "availability, partition behavior, latency, and operational complexity. "
        "The CAP theorem states that when a network partition occurs, a distributed "
        "data system cannot simultaneously guarantee both strong consistency and "
        "availability in the strict CAP sense. CAP should not be interpreted as "
        "a simple rule that a system permanently chooses only two of three properties."
    )

    concepts = [
        (
            "Strong consistency",
            "A read observes the latest committed value according to the system's consistency model."
        ),
        (
            "Eventual consistency",
            "Replicas may temporarily disagree but converge if updates stop and replication succeeds."
        ),
        (
            "Read-after-write consistency",
            "A client can observe its own successful write on subsequent reads."
        ),
        (
            "Monotonic reads",
            "Once a client observes a value, later reads do not move backward to an older state."
        ),
        (
            "Conflict resolution",
            "A rule or process determines the final state when concurrent updates conflict."
        ),
    ]

    for name, definition in concepts:
        print(f"\n{name}:")
        explain(definition)


# =============================================================================
# 23. FAILURE MODE ANALYSIS
# =============================================================================

@dataclass
class FailureMode:
    """Represents a simplified failure mode."""

    component: str
    failure: str
    impact: str
    mitigation: str


def failure_mode_demo() -> None:
    print_section("23. FAILURE MODE ANALYSIS")

    failures = [
        FailureMode(
            "API instance",
            "Process crash",
            "Requests routed to that instance fail.",
            "Health checks and multiple instances.",
        ),
        FailureMode(
            "Database",
            "Primary failure",
            "Transactional operations may stop or become degraded.",
            "Replication, automated failover, backups, and tested recovery.",
        ),
        FailureMode(
            "Message consumer",
            "Consumer crash",
            "Messages remain pending or become available again.",
            "Retries, visibility timeout, consumer replicas, and monitoring.",
        ),
        FailureMode(
            "Cache",
            "Cache outage",
            "Database load and latency can increase.",
            "Cache-aside design, database capacity, and stampede controls.",
        ),
        FailureMode(
            "Third-party API",
            "Provider timeout",
            "Business workflow can become slow or fail.",
            "Timeouts, retries with backoff, circuit breakers, and graceful degradation.",
        ),
        FailureMode(
            "Availability zone",
            "Zone outage",
            "Resources in that zone become unavailable.",
            "Multi-zone deployment for critical components.",
        ),
    ]

    for failure in failures:
        print(
            f"\nComponent: {failure.component}\n"
            f"  Failure: {failure.failure}\n"
            f"  Impact: {failure.impact}\n"
            f"  Mitigation: {failure.mitigation}"
        )

    print_subsection("Resilience patterns")

    patterns = [
        "Timeouts prevent a slow dependency from consuming resources indefinitely.",
        "Retries can recover transient failures but should use bounded attempts and backoff.",
        "Circuit breakers prevent repeated calls to a failing dependency.",
        "Bulkheads isolate resource pools so one workload does not exhaust all capacity.",
        "Rate limiting controls overload.",
        "Backpressure prevents producers from overwhelming consumers.",
        "Graceful degradation allows partial service when noncritical dependencies fail.",
    ]

    for pattern in patterns:
        print(f"  - {pattern}")


# =============================================================================
# 24. TESTING ARCHITECTURE
# =============================================================================

def architecture_testing_demo() -> None:
    print_section("24. ARCHITECTURE TESTING")

    tests = [
        "Unit tests for application logic",
        "Integration tests for service and database interactions",
        "Contract tests for service interfaces",
        "End-to-end tests for critical workflows",
        "Load tests for capacity assumptions",
        "Failure injection for resilience assumptions",
        "Backup restoration tests",
        "Security tests and access-control verification",
        "Deployment rollback tests",
        "Disaster recovery exercises",
    ]

    for test in tests:
        print(f"  - {test}")

    explain(
        "Architecture claims should be testable. Saying that a system is highly "
        "available is incomplete unless failover behavior, recovery time, and "
        "failure isolation have been exercised. Saying that backups exist is also "
        "incomplete unless restoration has been verified."
    )


# =============================================================================
# 25. SAMPLE ARCHITECTURE AS DATA
# =============================================================================

def build_reference_architecture() -> Tuple[List[ArchitectureComponent], DependencyGraph]:
    """Build a reusable reference architecture model."""

    components = [
        ArchitectureComponent(
            "Users",
            "Human clients",
            ArchitectureLayer.EDGE,
            public=True,
            scalable=False,
        ),
        ArchitectureComponent(
            "CDN",
            "Content delivery and edge caching",
            ArchitectureLayer.EDGE,
            public=True,
        ),
        ArchitectureComponent(
            "WAF",
            "Web application firewall",
            ArchitectureLayer.SECURITY,
            public=True,
        ),
        ArchitectureComponent(
            "Load Balancer",
            "Traffic distribution",
            ArchitectureLayer.EDGE,
            public=True,
        ),
        ArchitectureComponent(
            "API Service",
            "Business API",
            ArchitectureLayer.APPLICATION,
            replicas=1 if False else None,  # Type-safe replacement below.
        ),
    ]

    # Replace the intentionally explicit construction above with a valid
    # ArchitectureComponent because this class does not have a replicas field.
    components[-1] = ArchitectureComponent(
        "API Service",
        "Business API",
        ArchitectureLayer.APPLICATION,
        public=False,
        stateless=True if False else False,
    )

    components.extend(
        [
            ArchitectureComponent(
                "Background Worker",
                "Asynchronous processing",
                ArchitectureLayer.APPLICATION,
                public=False,
                stateless=True,
            ),
            ArchitectureComponent(
                "Cache",
                "Low-latency derived data",
                ArchitectureLayer.DATA,
                public=False,
                stateful=True,
                scalable=True,
            ),
            ArchitectureComponent(
                "Order Database",
                "Transactional system of record",
                ArchitectureLayer.DATA,
                public=False,
                stateful=True,
                scalable=False,
            ),
            ArchitectureComponent(
                "Message Queue",
                "Asynchronous transport",
                ArchitectureLayer.INTEGRATION,
                public=False,
                stateful=True,
                scalable=True,
            ),
            ArchitectureComponent(
                "Monitoring",
                "Metrics, logs, traces, alerts",
                ArchitectureLayer.OBSERVABILITY,
                public=False,
            ),
        ]
    )

    graph = DependencyGraph()

    dependencies = [
        ("Users", "CDN"),
        ("CDN", "WAF"),
        ("WAF", "Load Balancer"),
        ("Load Balancer", "API Service"),
        ("API Service", "Cache"),
        ("API Service", "Order Database"),
        ("API Service", "Message Queue"),
        ("Message Queue", "Background Worker"),
        ("Background Worker", "Order Database"),
        ("API Service", "Monitoring"),
        ("Background Worker", "Monitoring"),
    ]

    for source, target in dependencies:
        graph.add_dependency(source, target)

    return components, graph


# =============================================================================
# 26. ARCHITECTURE DOCUMENTATION PRINCIPLES
# =============================================================================

def documentation_demo() -> None:
    print_section("26. ARCHITECTURE DOCUMENTATION")

    documentation_elements = [
        (
            "System context",
            "Who uses the system and which external systems interact with it."
        ),
        (
            "Logical architecture",
            "Major application responsibilities and relationships."
        ),
        (
            "Deployment architecture",
            "Where components run and how they are distributed."
        ),
        (
            "Network architecture",
            "Subnets, routes, gateways, ingress, egress, and segmentation."
        ),
        (
            "Data architecture",
            "Systems of record, data flows, replication, retention, and backup."
        ),
        (
            "Security architecture",
            "Identity, trust boundaries, access control, encryption, and monitoring."
        ),
        (
            "Operational architecture",
            "Observability, deployments, scaling, failover, and incident response."
        ),
        (
            "Architecture decisions",
            "Important choices, context, alternatives, and consequences."
        ),
    ]

    for name, explanation_text in documentation_elements:
        print(f"\n{name}:")
        explain(explanation_text)

    explain(
        "Architecture documentation is most valuable when it explains why a system "
        "has a particular structure, not merely what products were provisioned. "
        "Diagrams should remain consistent with infrastructure and application "
        "changes through the normal engineering lifecycle."
    )


# =============================================================================
# 27. MINI ARCHITECTURE EXERCISE
# =============================================================================

def mini_architecture_exercise() -> None:
    print_section("27. MINI ARCHITECTURE DESIGN EXERCISE")

    requirements = [
        "A public web application must serve users globally.",
        "Application traffic should be encrypted.",
        "The application should tolerate loss of one availability zone.",
        "Orders require transactional persistence.",
        "Email notifications should not block order creation.",
        "Traffic may vary substantially during the day.",
        "Administrators need auditability.",
    ]

    print("Requirements:")
    for index, requirement in enumerate(requirements, 1):
        print(f"  {index}. {requirement}")

    print("\nReasoned architecture:")
    architecture = [
        "Use CDN and WAF at the edge.",
        "Use a load balancer to distribute traffic across application replicas.",
        "Deploy stateless application instances across multiple availability zones.",
        "Use a private transactional database with replication/failover appropriate to requirements.",
        "Use a queue for asynchronous notification processing.",
        "Use autoscaling for stateless compute based on relevant workload metrics.",
        "Use centralized metrics, logs, traces, and audit records.",
        "Use least-privilege identities and private networking for internal components.",
    ]

    for item in architecture:
        print(f"  - {item}")

    print("\nImportant design questions:")
    questions = [
        "What are the required availability and recovery targets?",
        "How much eventual consistency is acceptable?",
        "What is the expected peak request rate?",
        "How much data can be lost during disaster recovery?",
        "Which external dependencies exist?",
        "Which data requires encryption and special retention controls?",
        "What is the acceptable monthly cost range?",
    ]

    for question in questions:
        print(f"  - {question}")


# =============================================================================
# 28. PROGRAMMATIC TESTS
# =============================================================================

def run_tests() -> None:
    """Run deterministic assertions for the educational implementations."""

    print_section("28. SELF-TESTS")

    graph = DependencyGraph()
    graph.add_dependency("A", "B")
    graph.add_dependency("B", "C")

    assert graph.direct_dependencies("A") == ["B"]
    assert graph.transitive_dependencies("A") == {"B", "C"}
    assert graph.dependency_depth("A") == 2
    assert not graph.find_cycles()

    cyclic = DependencyGraph()
    cyclic.add_dependency("A", "B")
    cyclic.add_dependency("B", "A")
    assert cyclic.find_cycles()

    availability = AvailabilityModel(
        {
            "A": 0.99,
            "B": 0.99,
        }
    )

    assert math.isclose(
        availability.serial_availability(["A", "B"]),
        0.9801,
    )

    assert math.isclose(
        availability.parallel_availability(["A", "B"]),
        0.9999,
    )

    policy = ScalingPolicy(
        minimum_instances=2,
        maximum_instances=10,
        target_utilization=0.50,
    )

    assert policy.desired_instances(4, 0.50) == 4
    assert policy.desired_instances(4, 1.00) == 8
    assert policy.desired_instances(4, 2.00) == 10

    queue = MessageQueue()
    message = Message("m1", "test")

    queue.publish(message)
    assert queue.consume() is message

    for _ in range(3):
        queue.fail(message)

    assert message in queue.dead_letter_queue

    print("All self-tests passed.")


# =============================================================================
# 29. FINAL STUDY MAP
# =============================================================================

def study_map() -> None:
    print_section("29. CONCEPTUAL STUDY MAP")

    study = [
        ("Foundations", "Cloud, regions, availability zones, workloads, shared responsibility"),
        ("Infrastructure", "Networking, subnets, routing, gateways, compute, security boundaries"),
        ("Application", "Presentation, APIs, business services, workers, statelessness"),
        ("Data", "Transactions, databases, caches, object storage, search, consistency"),
        ("Dependencies", "Direct dependencies, transitive dependencies, cycles, blast radius"),
        ("Patterns", "Three-tier, monolith, microservices, event-driven, serverless, CQRS, Saga"),
        ("Reliability", "Redundancy, health checks, failover, SLOs, RTO, RPO, error budgets"),
        ("Scalability", "Vertical scaling, horizontal scaling, autoscaling, caching"),
        ("Security", "IAM, least privilege, segmentation, encryption, secrets, auditability"),
        ("Operations", "Metrics, logs, traces, alerts, deployment, recovery"),
        ("Cost", "Capacity, utilization, data transfer, managed services, retention"),
        ("Diagrams", "Context, container, component, deployment, network, data-flow"),
        ("Governance", "Architecture decisions, standards, validation, documentation"),
    ]

    for category, concepts in study:
        print(f"{category:20} -> {concepts}")


# =============================================================================
# 30. MAIN PROGRAM
# =============================================================================

def main() -> None:
    """Run the complete cloud architecture learning and demonstration program."""

    print("=" * 88)
    print("CLOUD ARCHITECTURE FUNDAMENTALS")
    print("Infrastructure Layers | Application Layers | Service Dependencies")
    print("Architecture Patterns | Reliability | Security | Draw.io Diagrams")
    print("=" * 88)

    fundamentals()
    architecture_layers()

    infrastructure = infrastructure_demo()
    application_layers_demo()
    graph = dependency_demo()
    architecture_patterns()
    reliability_demo()
    scalability_demo()
    security_demo()
    observability_demo()
    data_architecture_demo()
    asynchronous_demo()
    load_balancer_demo()
    cost_demo()
    adr_demo()
    validation_demo(graph)
    drawio_demo()
    diagram_levels_demo()
    production_checklist()
    common_mistakes()
    tradeoff_demo()
    consistency_demo()
    failure_mode_demo()
    architecture_testing_demo()
    documentation_demo()
    mini_architecture_exercise()
    run_tests()
    study_map()

    print_section("30. GENERATED ARTIFACTS")

    print(
        "Three Draw.io-compatible architecture files were generated in the "
        "current working directory:"
    )
    print("  - cloud_architecture_three_tier.drawio")
    print("  - cloud_architecture_event_driven.drawio")
    print("  - cloud_architecture_microservices.drawio")

    print("\nInfrastructure model statistics:")
    print(f"  Region: {infrastructure.region}")
    print(f"  Availability zones: {len(infrastructure.availability_zones)}")
    print(f"  Network segments: {len(infrastructure.segments)}")
    print(f"  Public segments: {len(infrastructure.public_segments())}")
    print(f"  Private segments: {len(infrastructure.private_segments())}")

    print("\nThe script completed successfully.")


if __name__ == "__main__":
    main()
