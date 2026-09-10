"""
Cloud Fundamentals Review and Project
Design a Basic Cloud Architecture Combining Compute, Storage,
Networking, Security, and Users

This standalone script is an educational study file. It teaches cloud
fundamentals from beginner concepts through a practical architecture
design exercise.

The script intentionally uses only Python's standard library. It does not
connect to a real cloud provider or create real cloud resources. Instead,
it models the major cloud components and demonstrates how they interact.

Topics covered:
- Cloud computing fundamentals
- Cloud service models
- Cloud deployment models
- Regions and availability zones
- Users, identities, authentication, and authorization
- Compute
- Storage
- Networking
- DNS
- Load balancing
- Firewalls and security groups
- Subnets
- Public and private resources
- Object, block, and file storage
- Encryption
- Secrets
- Monitoring and logging
- Backups
- High availability
- Scalability
- Reliability
- Availability versus durability
- Infrastructure architecture
- Network flow
- Security flow
- Least privilege
- Threat modeling
- Cost considerations
- Performance considerations
- Architecture trade-offs
- Infrastructure as Code concepts
- Configuration validation
- Architecture testing
- Failure simulation
- Production considerations

The examples are deliberately provider-neutral. Terminology may differ
slightly between AWS, Microsoft Azure, Google Cloud, and other providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Dict, List, Optional, Set, Tuple


# ============================================================================
# SECTION 1: BASIC CLOUD TERMINOLOGY
# ============================================================================

print("=" * 78)
print("CLOUD FUNDAMENTALS REVIEW AND PROJECT")
print("=" * 78)


def explain_cloud_computing() -> None:
    """
    Explain the fundamental idea of cloud computing.

    Cloud computing means obtaining computing resources such as servers,
    storage, databases, networking, and software through a provider rather
    than owning and operating all physical infrastructure directly.

    Important characteristics commonly associated with cloud computing:
    - On-demand resources
    - Elastic scaling
    - Measured usage
    - Resource pooling
    - Broad network access
    """
    print("\n1. CLOUD COMPUTING FUNDAMENTALS")
    print("-" * 78)

    concepts = {
        "Cloud computing": (
            "Using computing resources delivered through a network, usually "
            "from provider-operated data centers."
        ),
        "Elasticity": (
            "The ability to increase or decrease resources as workload "
            "changes."
        ),
        "Scalability": (
            "The ability of a system to handle increasing workload by "
            "adding resources or improving existing resources."
        ),
        "Availability": (
            "The ability of a service to remain accessible when users need it."
        ),
        "Durability": (
            "The ability of stored data to remain intact and not be lost."
        ),
        "Fault tolerance": (
            "The ability to continue operating despite component failures."
        ),
        "Measured service": (
            "Resource consumption can be measured and charged according to "
            "usage or pricing models."
        ),
    }

    for name, definition in concepts.items():
        print(f"{name}: {definition}")


explain_cloud_computing()


# ============================================================================
# SECTION 2: SERVICE MODELS
# ============================================================================

class ServiceModel(Enum):
    """Common cloud service delivery models."""

    IAAS = "Infrastructure as a Service"
    PAAS = "Platform as a Service"
    SAAS = "Software as a Service"


def explain_service_models() -> None:
    print("\n2. CLOUD SERVICE MODELS")
    print("-" * 78)

    models = {
        ServiceModel.IAAS: (
            "You manage operating systems, applications, and configurations "
            "while the provider manages physical infrastructure."
        ),
        ServiceModel.PAAS: (
            "The provider manages much of the underlying platform so teams "
            "can focus primarily on application code and configuration."
        ),
        ServiceModel.SAAS: (
            "A complete application is delivered to users. The provider "
            "manages the application and underlying infrastructure."
        ),
    }

    for model, description in models.items():
        print(f"{model.name}: {description}")

    print("\nResponsibility generally moves toward the provider as we move:")
    print("IaaS -> PaaS -> SaaS")

    print("\nImportant distinction:")
    print(
        "Cloud provider responsibility and customer responsibility are "
        "shared differently depending on the service."
    )


explain_service_models()


# ============================================================================
# SECTION 3: DEPLOYMENT MODELS
# ============================================================================

class DeploymentModel(Enum):
    """Common cloud deployment approaches."""

    PUBLIC = "Public Cloud"
    PRIVATE = "Private Cloud"
    HYBRID = "Hybrid Cloud"
    MULTI_CLOUD = "Multi-Cloud"


def explain_deployment_models() -> None:
    print("\n3. CLOUD DEPLOYMENT MODELS")
    print("-" * 78)

    descriptions = {
        DeploymentModel.PUBLIC: (
            "Infrastructure operated by a cloud provider and shared among "
            "multiple customers through logical isolation."
        ),
        DeploymentModel.PRIVATE: (
            "Cloud infrastructure dedicated to one organization."
        ),
        DeploymentModel.HYBRID: (
            "An architecture combining private infrastructure with public "
            "cloud resources."
        ),
        DeploymentModel.MULTI_CLOUD: (
            "Use of services from more than one cloud provider."
        ),
    }

    for model, description in descriptions.items():
        print(f"{model.value}: {description}")


explain_deployment_models()


# ============================================================================
# SECTION 4: REGIONS AND AVAILABILITY ZONES
# ============================================================================

@dataclass
class AvailabilityZone:
    """Represents an isolated cloud availability zone."""

    name: str
    healthy: bool = True


@dataclass
class CloudRegion:
    """
    Represents a geographic cloud region containing multiple zones.

    Real providers use different terminology and physical designs, but the
    conceptual purpose is similar: separating infrastructure into failure
    domains improves resilience.
    """

    name: str
    zones: List[AvailabilityZone]

    @property
    def healthy_zones(self) -> int:
        return sum(zone.healthy for zone in self.zones)

    @property
    def is_available(self) -> bool:
        return self.healthy_zones > 0


def demonstrate_region_design() -> None:
    print("\n4. REGIONS AND AVAILABILITY ZONES")
    print("-" * 78)

    region = CloudRegion(
        name="Example Region",
        zones=[
            AvailabilityZone("zone-a"),
            AvailabilityZone("zone-b"),
            AvailabilityZone("zone-c"),
        ],
    )

    print(f"Region: {region.name}")
    print(f"Availability zones: {len(region.zones)}")
    print(f"Healthy zones: {region.healthy_zones}")
    print(f"Region available: {region.is_available}")

    # Simulate a zone failure.
    region.zones[0].healthy = False

    print("\nAfter zone-a failure:")
    print(f"Healthy zones: {region.healthy_zones}")
    print(f"Region available: {region.is_available}")

    print(
        "\nDesign principle: placing important application instances in "
        "multiple failure domains reduces the impact of one zone failure."
    )


demonstrate_region_design()


# ============================================================================
# SECTION 5: CLOUD ARCHITECTURE COMPONENTS
# ============================================================================

@dataclass
class User:
    """Represents a human or application identity."""

    username: str
    role: str
    authenticated: bool = False


@dataclass
class ComputeInstance:
    """Represents a virtual compute resource."""

    name: str
    cpu: int
    memory_gb: int
    zone: str
    public_ip: bool = False
    healthy: bool = True


@dataclass
class ObjectStorageBucket:
    """
    Represents object storage.

    Object storage is suitable for files such as images, documents,
    backups, media, logs, and static assets.
    """

    name: str
    encrypted: bool = True
    versioning: bool = True
    objects: Dict[str, int] = field(default_factory=dict)

    def upload(self, object_name: str, size_mb: int) -> None:
        if size_mb < 0:
            raise ValueError("Object size cannot be negative.")
        self.objects[object_name] = size_mb

    def delete(self, object_name: str) -> None:
        self.objects.pop(object_name, None)

    def total_size_mb(self) -> int:
        return sum(self.objects.values())


@dataclass
class BlockStorageVolume:
    """
    Represents block storage attached to compute resources.

    Block storage behaves more like a disk than an object repository.
    """

    name: str
    size_gb: int
    encrypted: bool = True

    def __post_init__(self) -> None:
        if self.size_gb <= 0:
            raise ValueError("Block storage size must be positive.")


@dataclass
class VirtualNetwork:
    """Represents the logical network surrounding cloud resources."""

    name: str
    cidr: str
    public_subnets: List[str]
    private_subnets: List[str]


def create_basic_components() -> Tuple[
    List[ComputeInstance],
    ObjectStorageBucket,
    List[BlockStorageVolume],
    VirtualNetwork,
]:
    print("\n5. BASIC CLOUD COMPONENTS")
    print("-" * 78)

    compute = [
        ComputeInstance(
            name="app-server-1",
            cpu=2,
            memory_gb=4,
            zone="zone-a",
            public_ip=False,
        ),
        ComputeInstance(
            name="app-server-2",
            cpu=2,
            memory_gb=4,
            zone="zone-b",
            public_ip=False,
        ),
    ]

    object_storage = ObjectStorageBucket(
        name="application-assets",
        encrypted=True,
        versioning=True,
    )

    object_storage.upload("images/logo.png", 2)
    object_storage.upload("documents/report.pdf", 8)
    object_storage.upload("backups/database-backup.sql", 150)

    block_volumes = [
        BlockStorageVolume("app-disk-1", 50),
        BlockStorageVolume("app-disk-2", 50),
    ]

    network = VirtualNetwork(
        name="production-network",
        cidr="10.0.0.0/16",
        public_subnets=["10.0.1.0/24", "10.0.2.0/24"],
        private_subnets=["10.0.11.0/24", "10.0.12.0/24"],
    )

    print("Compute instances:")
    for instance in compute:
        print(
            f"  {instance.name}: {instance.cpu} CPU, "
            f"{instance.memory_gb} GB RAM, {instance.zone}"
        )

    print(f"\nObject storage: {object_storage.name}")
    print(f"Stored size: {object_storage.total_size_mb()} MB")
    print(f"Encryption enabled: {object_storage.encrypted}")
    print(f"Versioning enabled: {object_storage.versioning}")

    print("\nBlock storage:")
    for volume in block_volumes:
        print(f"  {volume.name}: {volume.size_gb} GB")

    print(f"\nVirtual network: {network.name} ({network.cidr})")
    print(f"Public subnets: {network.public_subnets}")
    print(f"Private subnets: {network.private_subnets}")

    return compute, object_storage, block_volumes, network


compute_instances, storage_bucket, block_volumes, virtual_network = (
    create_basic_components()
)


# ============================================================================
# SECTION 6: STORAGE TYPES
# ============================================================================

def compare_storage_types() -> None:
    print("\n6. STORAGE TYPES")
    print("-" * 78)

    storage_types = {
        "Object storage": (
            "Stores independent objects with metadata. Good for images, "
            "documents, backups, media, and static files."
        ),
        "Block storage": (
            "Provides disk-like storage to compute resources. Good for "
            "operating systems, application disks, and databases."
        ),
        "File storage": (
            "Provides a shared file-system-like interface. Useful when "
            "multiple systems need shared files."
        ),
    }

    for storage_type, use_case in storage_types.items():
        print(f"{storage_type}: {use_case}")

    print("\nKey distinction:")
    print(
        "Choosing storage depends on access pattern, latency, sharing, "
        "capacity, durability, performance, and cost."
    )


compare_storage_types()


# ============================================================================
# SECTION 7: NETWORKING FUNDAMENTALS
# ============================================================================

@dataclass
class Subnet:
    """Represents a logical network segment."""

    name: str
    cidr: str
    public: bool


@dataclass
class FirewallRule:
    """Represents a simplified network access rule."""

    protocol: str
    port: int
    source: str
    action: str = "ALLOW"


class SecurityGroup:
    """
    Simplified stateful firewall model.

    In real cloud providers, security group behavior differs by provider,
    but the educational purpose here is to demonstrate explicit network
    access control.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.rules: List[FirewallRule] = []

    def allow(self, protocol: str, port: int, source: str) -> None:
        self.rules.append(
            FirewallRule(
                protocol=protocol,
                port=port,
                source=source,
                action="ALLOW",
            )
        )

    def is_allowed(self, protocol: str, port: int, source: str) -> bool:
        return any(
            rule.action == "ALLOW"
            and rule.protocol == protocol
            and rule.port == port
            and rule.source == source
            for rule in self.rules
        )


def demonstrate_networking() -> None:
    print("\n7. NETWORKING FUNDAMENTALS")
    print("-" * 78)

    public_subnet = Subnet("public-subnet", "10.0.1.0/24", public=True)
    private_subnet = Subnet("private-subnet", "10.0.11.0/24", public=False)

    print(
        f"Public subnet: {public_subnet.cidr}, "
        f"public={public_subnet.public}"
    )
    print(
        f"Private subnet: {private_subnet.cidr}, "
        f"public={private_subnet.public}"
    )

    application_sg = SecurityGroup("application-security-group")

    # HTTPS from users is permitted.
    application_sg.allow("TCP", 443, "INTERNET")

    # HTTP is allowed here only to demonstrate explicit rules. Production
    # architectures commonly redirect HTTP to HTTPS or block it entirely.
    application_sg.allow("TCP", 80, "INTERNET")

    # SSH is deliberately not opened to the entire internet.
    application_sg.allow("TCP", 22, "ADMIN_NETWORK")

    print("\nSecurity group rules:")
    for rule in application_sg.rules:
        print(
            f"  {rule.action} {rule.protocol}/{rule.port} "
            f"from {rule.source}"
        )

    print("\nAccess tests:")
    print(
        "HTTPS from internet:",
        application_sg.is_allowed("TCP", 443, "INTERNET"),
    )
    print(
        "SSH from internet:",
        application_sg.is_allowed("TCP", 22, "INTERNET"),
    )
    print(
        "SSH from admin network:",
        application_sg.is_allowed("TCP", 22, "ADMIN_NETWORK"),
    )


demonstrate_networking()


# ============================================================================
# SECTION 8: INTERNET ACCESS, ROUTING, DNS, AND LOAD BALANCING
# ============================================================================

@dataclass
class DNSRecord:
    """Simplified DNS record."""

    hostname: str
    destination: str


@dataclass
class LoadBalancer:
    """
    Simplified load balancer.

    A load balancer distributes requests among healthy backend instances.
    """

    name: str
    backends: List[ComputeInstance]

    def healthy_backends(self) -> List[ComputeInstance]:
        return [backend for backend in self.backends if backend.healthy]

    def choose_backend(self) -> Optional[ComputeInstance]:
        healthy = self.healthy_backends()
        if not healthy:
            return None

        # A simple deterministic selection is sufficient for demonstration.
        return healthy[0]


def demonstrate_request_flow() -> None:
    print("\n8. REQUEST FLOW")
    print("-" * 78)

    dns = DNSRecord(
        hostname="www.example.com",
        destination="public-load-balancer",
    )

    load_balancer = LoadBalancer(
        name="application-load-balancer",
        backends=compute_instances,
    )

    print(f"DNS: {dns.hostname} -> {dns.destination}")

    selected = load_balancer.choose_backend()

    if selected:
        print(
            f"Load balancer sends request to "
            f"{selected.name} in {selected.zone}."
        )
    else:
        print("No healthy application backend is available.")

    print(
        "\nConceptual request path:\n"
        "User -> DNS -> Load Balancer -> Application Server -> "
        "Storage/Database"
    )


demonstrate_request_flow()


# ============================================================================
# SECTION 9: DATABASE CONCEPT
# ============================================================================

@dataclass
class Database:
    """
    Simplified managed database representation.

    A real database has many additional properties including replication,
    transactions, indexes, backups, connections, and consistency behavior.
    """

    name: str
    engine: str
    private: bool = True
    encrypted: bool = True
    healthy: bool = True
    records: List[Dict[str, object]] = field(default_factory=list)

    def insert(self, record: Dict[str, object]) -> None:
        if not self.healthy:
            raise RuntimeError("Database is unavailable.")
        self.records.append(record)

    def count(self) -> int:
        return len(self.records)


def demonstrate_database_layer() -> Database:
    print("\n9. DATABASE LAYER")
    print("-" * 78)

    database = Database(
        name="application-database",
        engine="relational",
        private=True,
        encrypted=True,
    )

    database.insert({"id": 1, "name": "Alice"})
    database.insert({"id": 2, "name": "Bob"})

    print(f"Database: {database.name}")
    print(f"Engine: {database.engine}")
    print(f"Private network placement: {database.private}")
    print(f"Encryption enabled: {database.encrypted}")
    print(f"Records: {database.count()}")

    return database


database = demonstrate_database_layer()


# ============================================================================
# SECTION 10: USERS, AUTHENTICATION, AND AUTHORIZATION
# ============================================================================

class Permission(Enum):
    """Example permissions for role-based access control."""

    READ_APPLICATION = "read_application"
    WRITE_APPLICATION = "write_application"
    READ_STORAGE = "read_storage"
    WRITE_STORAGE = "write_storage"
    MANAGE_INFRASTRUCTURE = "manage_infrastructure"
    VIEW_LOGS = "view_logs"


@dataclass
class Role:
    """A role groups permissions."""

    name: str
    permissions: Set[Permission]


class IdentityManager:
    """Simplified authentication and authorization service."""

    def __init__(self) -> None:
        self.roles: Dict[str, Role] = {}
        self.users: Dict[str, User] = {}

    def add_role(self, role: Role) -> None:
        self.roles[role.name] = role

    def add_user(self, user: User) -> None:
        if user.role not in self.roles:
            raise ValueError(f"Unknown role: {user.role}")
        self.users[user.username] = user

    def authenticate(self, username: str) -> bool:
        user = self.users.get(username)
        if user is None:
            return False

        user.authenticated = True
        return True

    def authorize(self, username: str, permission: Permission) -> bool:
        user = self.users.get(username)

        if user is None or not user.authenticated:
            return False

        role = self.roles.get(user.role)

        if role is None:
            return False

        return permission in role.permissions


def demonstrate_identity_and_access() -> IdentityManager:
    print("\n10. IDENTITY, AUTHENTICATION, AND AUTHORIZATION")
    print("-" * 78)

    identity_manager = IdentityManager()

    identity_manager.add_role(
        Role(
            name="application-user",
            permissions={
                Permission.READ_APPLICATION,
                Permission.WRITE_APPLICATION,
            },
        )
    )

    identity_manager.add_role(
        Role(
            name="operations-admin",
            permissions={
                Permission.READ_APPLICATION,
                Permission.WRITE_APPLICATION,
                Permission.READ_STORAGE,
                Permission.WRITE_STORAGE,
                Permission.MANAGE_INFRASTRUCTURE,
                Permission.VIEW_LOGS,
            },
        )
    )

    identity_manager.add_user(
        User(username="alice", role="application-user")
    )
    identity_manager.add_user(
        User(username="admin", role="operations-admin")
    )

    identity_manager.authenticate("alice")
    identity_manager.authenticate("admin")

    print(
        "Alice can read application:",
        identity_manager.authorize(
            "alice", Permission.READ_APPLICATION
        ),
    )

    print(
        "Alice can manage infrastructure:",
        identity_manager.authorize(
            "alice", Permission.MANAGE_INFRASTRUCTURE
        ),
    )

    print(
        "Admin can manage infrastructure:",
        identity_manager.authorize(
            "admin", Permission.MANAGE_INFRASTRUCTURE
        ),
    )

    print(
        "\nSecurity principle: authentication answers "
        "'Who are you?' while authorization answers "
        "'What are you allowed to do?'"
    )

    return identity_manager


identity_manager = demonstrate_identity_and_access()


# ============================================================================
# SECTION 11: LEAST PRIVILEGE
# ============================================================================

def demonstrate_least_privilege() -> None:
    print("\n11. LEAST PRIVILEGE")
    print("-" * 78)

    application_permissions = {
        Permission.READ_APPLICATION,
        Permission.WRITE_APPLICATION,
    }

    excessive_permissions = set(Permission)

    print("Application permissions:")
    for permission in sorted(
        application_permissions, key=lambda item: item.value
    ):
        print(f"  {permission.value}")

    print("\nExcessive administrative permissions:")
    for permission in sorted(
        excessive_permissions, key=lambda item: item.value
    ):
        print(f"  {permission.value}")

    print(
        "\nLeast privilege means granting only the permissions required "
        "for a task rather than broad administrative access."
    )


demonstrate_least_privilege()


# ============================================================================
# SECTION 12: ENCRYPTION AND SECRETS
# ============================================================================

@dataclass
class SecretReference:
    """
    Represents a reference to a secret.

    A production system should retrieve secrets from a dedicated secret
    management service rather than hard-coding passwords in source code.
    """

    name: str
    value: str = field(repr=False)

    def masked(self) -> str:
        if not self.value:
            return ""
        return "*" * min(len(self.value), 8)


def demonstrate_security_basics() -> None:
    print("\n12. ENCRYPTION AND SECRET MANAGEMENT")
    print("-" * 78)

    secret = SecretReference(
        name="database-password",
        value="example-not-a-real-password",
    )

    print(f"Secret name: {secret.name}")
    print(f"Secret value displayed safely: {secret.masked()}")

    print("\nEncryption concepts:")
    print("At rest: protects stored data.")
    print("In transit: protects data moving across networks.")
    print("Key management: controls creation, storage, rotation, and use of keys.")

    print(
        "\nDo not place passwords, API keys, private keys, or tokens "
        "directly in source code or public repositories."
    )


demonstrate_security_basics()


# ============================================================================
# SECTION 13: MONITORING AND LOGGING
# ============================================================================

@dataclass
class Metric:
    """Represents a numerical operational metric."""

    name: str
    value: float
    unit: str


@dataclass
class LogEvent:
    """Represents an application or infrastructure log event."""

    timestamp: str
    level: str
    message: str


class MonitoringSystem:
    """Simple monitoring and alerting model."""

    def __init__(self) -> None:
        self.metrics: List[Metric] = []
        self.logs: List[LogEvent] = []

    def record_metric(self, metric: Metric) -> None:
        self.metrics.append(metric)

    def record_log(self, event: LogEvent) -> None:
        self.logs.append(event)

    def alert_if_high_cpu(self, threshold: float = 80.0) -> List[str]:
        alerts = []

        for metric in self.metrics:
            if metric.name == "cpu_utilization" and metric.value > threshold:
                alerts.append(
                    f"High CPU detected: {metric.value}{metric.unit}"
                )

        return alerts


def demonstrate_monitoring() -> None:
    print("\n13. MONITORING, LOGGING, AND ALERTING")
    print("-" * 78)

    monitoring = MonitoringSystem()

    monitoring.record_metric(
        Metric("cpu_utilization", 42.5, "%")
    )
    monitoring.record_metric(
        Metric("cpu_utilization", 91.0, "%")
    )
    monitoring.record_metric(
        Metric("request_latency", 180.0, "ms")
    )

    monitoring.record_log(
        LogEvent(
            timestamp="2026-09-10T10:00:00",
            level="INFO",
            message="Application started.",
        )
    )

    monitoring.record_log(
        LogEvent(
            timestamp="2026-09-10T10:01:00",
            level="ERROR",
            message="Database connection timeout.",
        )
    )

    print("Metrics:")
    for metric in monitoring.metrics:
        print(f"  {metric.name}: {metric.value}{metric.unit}")

    print("\nAlerts:")
    for alert in monitoring.alert_if_high_cpu():
        print(f"  {alert}")

    print("\nLogs:")
    for event in monitoring.logs:
        print(
            f"  [{event.timestamp}] {event.level}: {event.message}"
        )


demonstrate_monitoring()


# ============================================================================
# SECTION 14: BACKUPS AND RECOVERY
# ============================================================================

@dataclass
class BackupPolicy:
    """Represents a simple backup policy."""

    frequency_hours: int
    retention_days: int
    cross_zone: bool
    cross_region: bool

    def validate(self) -> None:
        if self.frequency_hours <= 0:
            raise ValueError("Backup frequency must be positive.")

        if self.retention_days <= 0:
            raise ValueError("Retention must be positive.")


def demonstrate_backup_strategy() -> None:
    print("\n14. BACKUPS AND DISASTER RECOVERY")
    print("-" * 78)

    policy = BackupPolicy(
        frequency_hours=24,
        retention_days=30,
        cross_zone=True,
        cross_region=True,
    )

    policy.validate()

    print(f"Backup frequency: every {policy.frequency_hours} hours")
    print(f"Retention: {policy.retention_days} days")
    print(f"Cross-zone copy: {policy.cross_zone}")
    print(f"Cross-region copy: {policy.cross_region}")

    print("\nImportant recovery concepts:")
    print("RPO = Recovery Point Objective: acceptable amount of data loss.")
    print("RTO = Recovery Time Objective: acceptable time to restore service.")

    print(
        "\nBackups should be tested. A backup that has never been restored "
        "should not automatically be assumed to be usable."
    )


demonstrate_backup_strategy()


# ============================================================================
# SECTION 15: HIGH AVAILABILITY AND FAILURE SIMULATION
# ============================================================================

def simulate_zone_failure() -> None:
    print("\n15. HIGH AVAILABILITY AND FAILURE SIMULATION")
    print("-" * 78)

    load_balancer = LoadBalancer(
        name="production-lb",
        backends=compute_instances,
    )

    print("Initial healthy backends:")
    for backend in load_balancer.healthy_backends():
        print(f"  {backend.name} in {backend.zone}")

    # Simulate failure of the first application server.
    compute_instances[0].healthy = False

    print("\nAfter app-server-1 failure:")
    for backend in load_balancer.healthy_backends():
        print(f"  {backend.name} in {backend.zone}")

    selected = load_balancer.choose_backend()

    if selected:
        print(f"\nTraffic continues through {selected.name}.")
    else:
        print("\nTraffic cannot reach an application server.")

    # Restore the instance for later demonstrations.
    compute_instances[0].healthy = True


simulate_zone_failure()


# ============================================================================
# SECTION 16: SCALABILITY
# ============================================================================

@dataclass
class AutoScalingGroup:
    """
    Simplified horizontal auto-scaling model.

    Horizontal scaling adds more instances. Vertical scaling increases the
    capacity of an existing instance.
    """

    minimum_instances: int
    maximum_instances: int
    current_instances: int
    target_cpu_percent: float

    def scale_for_cpu(self, observed_cpu: float) -> int:
        if observed_cpu > self.target_cpu_percent + 10:
            self.current_instances += 1
        elif observed_cpu < self.target_cpu_percent - 20:
            self.current_instances -= 1

        self.current_instances = max(
            self.minimum_instances,
            min(self.current_instances, self.maximum_instances),
        )

        return self.current_instances


def demonstrate_scalability() -> None:
    print("\n16. SCALABILITY")
    print("-" * 78)

    scaling = AutoScalingGroup(
        minimum_instances=2,
        maximum_instances=6,
        current_instances=2,
        target_cpu_percent=60,
    )

    observations = [45, 65, 85, 92, 40, 25]

    print("CPU -> desired instance count:")

    for cpu in observations:
        instances = scaling.scale_for_cpu(cpu)
        print(f"  {cpu}% -> {instances} instances")

    print("\nHorizontal scaling: add or remove instances.")
    print("Vertical scaling: increase or decrease instance capacity.")

    print(
        "\nHorizontal scaling often improves resilience because workload "
        "is distributed across multiple instances."
    )


demonstrate_scalability()


# ============================================================================
# SECTION 17: CAPACITY PLANNING
# ============================================================================

def estimate_instances(
    requests_per_second: float,
    requests_per_instance: float,
    safety_factor: float = 1.3,
) -> int:
    """
    Estimate instance count from workload.

    This is a simplified planning formula and should not be treated as
    production capacity planning. Real systems require load testing and
    measurement of CPU, memory, I/O, latency, and dependency limits.
    """
    if requests_per_second < 0:
        raise ValueError("Request rate cannot be negative.")

    if requests_per_instance <= 0:
        raise ValueError("Instance capacity must be positive.")

    if safety_factor < 1:
        raise ValueError("Safety factor should be at least 1.")

    required_capacity = requests_per_second * safety_factor

    return max(1, ceil(required_capacity / requests_per_instance))


def demonstrate_capacity_planning() -> None:
    print("\n17. BASIC CAPACITY PLANNING")
    print("-" * 78)

    expected_rps = 450
    instance_capacity = 100

    count = estimate_instances(
        requests_per_second=expected_rps,
        requests_per_instance=instance_capacity,
        safety_factor=1.3,
    )

    print(f"Expected traffic: {expected_rps} requests/second")
    print(f"Estimated instance capacity: {instance_capacity} requests/second")
    print(f"Safety-adjusted instances: {count}")

    print(
        "\nThe calculation is intentionally conservative. Production "
        "capacity decisions should be validated through measurement."
    )


demonstrate_capacity_planning()


# ============================================================================
# SECTION 18: BASIC COST MODEL
# ============================================================================

@dataclass
class MonthlyCostEstimate:
    """Simplified monthly cost model."""

    compute_cost: float
    storage_cost: float
    network_cost: float
    database_cost: float
    monitoring_cost: float

    @property
    def total(self) -> float:
        return (
            self.compute_cost
            + self.storage_cost
            + self.network_cost
            + self.database_cost
            + self.monitoring_cost
        )


def demonstrate_cost_model() -> None:
    print("\n18. BASIC CLOUD COST MODEL")
    print("-" * 78)

    estimate = MonthlyCostEstimate(
        compute_cost=120.0,
        storage_cost=25.0,
        network_cost=30.0,
        database_cost=100.0,
        monitoring_cost=20.0,
    )

    print(f"Compute: ${estimate.compute_cost:.2f}")
    print(f"Storage: ${estimate.storage_cost:.2f}")
    print(f"Network: ${estimate.network_cost:.2f}")
    print(f"Database: ${estimate.database_cost:.2f}")
    print(f"Monitoring: ${estimate.monitoring_cost:.2f}")
    print(f"Estimated total: ${estimate.total:.2f}")

    print(
        "\nActual cloud bills depend on provider, region, resource size, "
        "usage, data transfer, discounts, commitments, and service-specific "
        "pricing."
    )


demonstrate_cost_model()


# ============================================================================
# SECTION 19: BASIC SECURITY ARCHITECTURE
# ============================================================================

@dataclass
class SecurityControl:
    """Represents a security control."""

    name: str
    purpose: str
    layer: str


def demonstrate_security_layers() -> None:
    print("\n19. SECURITY ARCHITECTURE")
    print("-" * 78)

    controls = [
        SecurityControl(
            "Identity and access management",
            "Controls who can access resources and what they can do.",
            "Identity",
        ),
        SecurityControl(
            "HTTPS",
            "Encrypts application traffic between clients and services.",
            "Network/Application",
        ),
        SecurityControl(
            "Network segmentation",
            "Separates public-facing and internal resources.",
            "Network",
        ),
        SecurityControl(
            "Security groups",
            "Restricts allowed network connections.",
            "Network",
        ),
        SecurityControl(
            "Encryption at rest",
            "Protects stored data.",
            "Data",
        ),
        SecurityControl(
            "Secrets management",
            "Protects passwords, tokens, and keys.",
            "Application",
        ),
        SecurityControl(
            "Logging",
            "Provides evidence for monitoring and investigation.",
            "Operations",
        ),
        SecurityControl(
            "Backups",
            "Provides recovery from data loss and certain incidents.",
            "Recovery",
        ),
    ]

    for control in controls:
        print(
            f"{control.layer}: {control.name} -> {control.purpose}"
        )

    print(
        "\nSecurity should be layered. A single control should not be "
        "treated as sufficient protection."
    )


demonstrate_security_layers()


# ============================================================================
# SECTION 20: THREAT MODELING
# ============================================================================

@dataclass
class Threat:
    """Represents a simplified security threat."""

    name: str
    affected_component: str
    impact: str
    mitigation: str


def demonstrate_threat_model() -> None:
    print("\n20. BASIC THREAT MODELING")
    print("-" * 78)

    threats = [
        Threat(
            name="Unauthorized access",
            affected_component="Application",
            impact="Data exposure or unauthorized actions",
            mitigation="Strong authentication, MFA, RBAC, least privilege",
        ),
        Threat(
            name="Open administrative port",
            affected_component="Compute",
            impact="Remote attack surface",
            mitigation="Restrict management access to trusted networks",
        ),
        Threat(
            name="Data interception",
            affected_component="Network",
            impact="Credential or data exposure",
            mitigation="TLS/HTTPS and secure protocols",
        ),
        Threat(
            name="Accidental deletion",
            affected_component="Storage",
            impact="Data loss",
            mitigation="Versioning, backups, retention controls",
        ),
        Threat(
            name="Credential leakage",
            affected_component="Source code",
            impact="Unauthorized resource access",
            mitigation="Secret manager, rotation, scanning, access control",
        ),
    ]

    for threat in threats:
        print(f"\nThreat: {threat.name}")
        print(f"Component: {threat.affected_component}")
        print(f"Impact: {threat.impact}")
        print(f"Mitigation: {threat.mitigation}")


demonstrate_threat_model()


# ============================================================================
# SECTION 21: ARCHITECTURE VALIDATION
# ============================================================================

@dataclass
class Architecture:
    """
    Represents the complete basic architecture.

    The architecture contains:
    - users
    - DNS
    - load balancer
    - compute
    - private database
    - object storage
    - network
    - security controls
    - monitoring
    """

    name: str
    users: List[User]
    dns: DNSRecord
    load_balancer: LoadBalancer
    compute: List[ComputeInstance]
    database: Database
    storage: ObjectStorageBucket
    network: VirtualNetwork
    monitoring: MonitoringSystem
    security_groups: List[SecurityGroup]

    def validate(self) -> List[str]:
        """Return architecture validation errors."""

        errors: List[str] = []

        if not self.users:
            errors.append("Architecture has no users.")

        if not self.compute:
            errors.append("Architecture has no compute instances.")

        if len(self.compute) < 2:
            errors.append(
                "Production-oriented architecture should have multiple "
                "application instances."
            )

        if not self.network.public_subnets:
            errors.append("No public subnet exists.")

        if not self.network.private_subnets:
            errors.append("No private subnet exists.")

        if not self.database.private:
            errors.append("Database should normally be private.")

        if not self.database.encrypted:
            errors.append("Database encryption should be enabled.")

        if not self.storage.encrypted:
            errors.append("Object storage encryption should be enabled.")

        if not self.storage.versioning:
            errors.append("Object storage versioning is recommended for recovery.")

        if not self.security_groups:
            errors.append("No network security groups are configured.")

        if not self.monitoring.metrics and not self.monitoring.logs:
            errors.append("No monitoring or logging data is configured.")

        if not self.load_balancer.healthy_backends():
            errors.append("No healthy compute backend exists.")

        return errors


# ============================================================================
# SECTION 22: BUILD THE COMPLETE BASIC CLOUD ARCHITECTURE
# ============================================================================

def build_basic_cloud_architecture() -> Architecture:
    print("\n21. BASIC CLOUD ARCHITECTURE PROJECT")
    print("-" * 78)

    users = [
        User("customer-1", "application-user", authenticated=True),
        User("operations-admin", "operations-admin", authenticated=True),
    ]

    application_instances = [
        ComputeInstance(
            "web-app-1",
            cpu=2,
            memory_gb=4,
            zone="zone-a",
            public_ip=False,
        ),
        ComputeInstance(
            "web-app-2",
            cpu=2,
            memory_gb=4,
            zone="zone-b",
            public_ip=False,
        ),
    ]

    project_storage = ObjectStorageBucket(
        name="project-object-storage",
        encrypted=True,
        versioning=True,
    )

    project_storage.upload("static/index.html", 1)
    project_storage.upload("uploads/example.pdf", 5)

    project_database = Database(
        name="project-database",
        engine="relational",
        private=True,
        encrypted=True,
    )

    project_database.insert(
        {
            "id": 1,
            "username": "customer-1",
            "status": "active",
        }
    )

    project_network = VirtualNetwork(
        name="project-vpc",
        cidr="10.0.0.0/16",
        public_subnets=[
            "10.0.1.0/24",
            "10.0.2.0/24",
        ],
        private_subnets=[
            "10.0.11.0/24",
            "10.0.12.0/24",
        ],
    )

    application_security_group = SecurityGroup("application-sg")
    application_security_group.allow(
        protocol="TCP",
        port=443,
        source="INTERNET",
    )

    database_security_group = SecurityGroup("database-sg")
    database_security_group.allow(
        protocol="TCP",
        port=5432,
        source="APPLICATION_SECURITY_GROUP",
    )

    load_balancer = LoadBalancer(
        name="project-load-balancer",
        backends=application_instances,
    )

    dns = DNSRecord(
        hostname="app.example.com",
        destination="project-load-balancer",
    )

    monitoring = MonitoringSystem()
    monitoring.record_metric(
        Metric("cpu_utilization", 48.0, "%")
    )
    monitoring.record_metric(
        Metric("request_latency", 120.0, "ms")
    )
    monitoring.record_log(
        LogEvent(
            "2026-09-10T10:15:00",
            "INFO",
            "Application health check passed.",
        )
    )

    architecture = Architecture(
        name="basic-production-cloud",
        users=users,
        dns=dns,
        load_balancer=load_balancer,
        compute=application_instances,
        database=project_database,
        storage=project_storage,
        network=project_network,
        monitoring=monitoring,
        security_groups=[
            application_security_group,
            database_security_group,
        ],
    )

    print(f"Architecture: {architecture.name}")
    print(f"Users: {len(architecture.users)}")
    print(f"Compute instances: {len(architecture.compute)}")
    print(f"Object storage objects: {len(architecture.storage.objects)}")
    print(f"Database records: {architecture.database.count()}")
    print(f"Network CIDR: {architecture.network.cidr}")

    return architecture


architecture = build_basic_cloud_architecture()


# ============================================================================
# SECTION 23: ARCHITECTURE DIAGRAM AS TEXT
# ============================================================================

def print_architecture_diagram(architecture: Architecture) -> None:
    print("\n22. ARCHITECTURE DIAGRAM")
    print("-" * 78)

    print(
        """
                         INTERNET USERS
                               |
                               v
                         +-----------+
                         |    DNS    |
                         +-----------+
                               |
                               v
                    +---------------------+
                    |   LOAD BALANCER     |
                    |       HTTPS         |
                    +---------------------+
                         /           \\
                        /             \\
                       v               v
               +-------------+   +-------------+
               | Compute #1  |   | Compute #2  |
               | Private     |   | Private     |
               | Zone A      |   | Zone B      |
               +-------------+   +-------------+
                       \\               /
                        \\             /
                         v           v
                    +----------------+
                    | Private        |
                    | Database       |
                    +----------------+
                           |
                           |
                    +----------------+
                    | Object Storage |
                    | Encrypted      |
                    | Versioned      |
                    +----------------+

             MANAGEMENT / SECURITY / MONITORING
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
        IAM        Security Groups   Monitoring
        /RBAC       /Network ACLs    /Logging
"""
    )

    print(
        "Architecture principle: public access should terminate at the "
        "controlled entry point rather than exposing every internal resource."
    )


print_architecture_diagram(architecture)


# ============================================================================
# SECTION 24: END-TO-END REQUEST SIMULATION
# ============================================================================

def simulate_user_request(architecture: Architecture) -> None:
    print("\n23. END-TO-END REQUEST SIMULATION")
    print("-" * 78)

    user = architecture.users[0]

    print(f"1. User '{user.username}' sends an HTTPS request.")
    print(f"2. DNS resolves {architecture.dns.hostname}.")
    print(
        f"3. DNS points to {architecture.dns.destination}."
    )

    backend = architecture.load_balancer.choose_backend()

    if backend is None:
        print("4. Request fails because no backend is healthy.")
        return

    print(
        f"4. Load balancer forwards the request to "
        f"{backend.name} in {backend.zone}."
    )

    print("5. Application authenticates and authorizes the user.")
    print("6. Application reads or writes required database data.")
    print("7. Application accesses object storage when files are required.")
    print("8. Metrics and logs are recorded.")
    print("9. Response travels back through the load balancer to the user.")

    print(
        "\nThe application servers do not need public IP addresses in this "
        "architecture because the load balancer provides the controlled "
        "public entry point."
    )


simulate_user_request(architecture)


# ============================================================================
# SECTION 25: PRIVATE VERSUS PUBLIC RESOURCE DESIGN
# ============================================================================

def compare_public_private_design() -> None:
    print("\n24. PUBLIC VERSUS PRIVATE RESOURCE DESIGN")
    print("-" * 78)

    comparison = [
        (
            "Load balancer",
            "Usually public",
            "Receives legitimate internet traffic."
        ),
        (
            "Application server",
            "Usually private",
            "Reduces direct internet attack surface."
        ),
        (
            "Database",
            "Usually private",
            "Should not normally accept direct internet traffic."
        ),
        (
            "Object storage",
            "Access-controlled",
            "May support public assets, but private-by-default is safer."
        ),
        (
            "Management interface",
            "Restricted",
            "Should be accessible only to authorized administrators."
        ),
    ]

    for component, exposure, reason in comparison:
        print(f"{component}: {exposure} -> {reason}")


compare_public_private_design()


# ============================================================================
# SECTION 26: NETWORK SECURITY VALIDATION
# ============================================================================

def validate_network_security(
    application_sg: SecurityGroup,
    database_sg: SecurityGroup,
) -> List[str]:
    """
    Validate a few high-level network security requirements.

    This is not a substitute for a cloud provider's actual network
    configuration validation.
    """
    findings: List[str] = []

    if application_sg.is_allowed("TCP", 22, "INTERNET"):
        findings.append(
            "HIGH: SSH is directly exposed to the internet."
        )
    else:
        findings.append(
            "PASS: SSH is not directly exposed to the internet."
        )

    if database_sg.is_allowed(
        "TCP",
        5432,
        "INTERNET",
    ):
        findings.append(
            "HIGH: Database port is directly exposed to the internet."
        )
    else:
        findings.append(
            "PASS: Database port is not directly exposed to the internet."
        )

    if application_sg.is_allowed(
        "TCP",
        443,
        "INTERNET",
    ):
        findings.append(
            "PASS: HTTPS access is explicitly allowed."
        )
    else:
        findings.append(
            "WARNING: HTTPS is not allowed."
        )

    return findings


def demonstrate_network_security_validation() -> None:
    print("\n25. NETWORK SECURITY VALIDATION")
    print("-" * 78)

    application_sg = architecture.security_groups[0]
    database_sg = architecture.security_groups[1]

    findings = validate_network_security(
        application_sg,
        database_sg,
    )

    for finding in findings:
        print(f"  {finding}")


demonstrate_network_security_validation()


# ============================================================================
# SECTION 27: ARCHITECTURE VALIDATION
# ============================================================================

def demonstrate_architecture_validation(
    architecture: Architecture,
) -> None:
    print("\n26. ARCHITECTURE VALIDATION")
    print("-" * 78)

    errors = architecture.validate()

    if not errors:
        print("Architecture validation passed.")
    else:
        print("Architecture validation findings:")
        for error in errors:
            print(f"  - {error}")


demonstrate_architecture_validation(architecture)


# ============================================================================
# SECTION 28: FAILURE SCENARIOS
# ============================================================================

def simulate_failure_scenarios(architecture: Architecture) -> None:
    print("\n27. FAILURE SCENARIOS")
    print("-" * 78)

    # Scenario 1: one compute instance fails.
    architecture.compute[0].healthy = False

    healthy_instances = architecture.load_balancer.healthy_backends()

    print("Scenario 1: One application server fails.")
    print(
        f"Healthy application servers remaining: "
        f"{len(healthy_instances)}"
    )

    # Scenario 2: all compute instances fail.
    for instance in architecture.compute:
        instance.healthy = False

    healthy_instances = architecture.load_balancer.healthy_backends()

    print("\nScenario 2: All application servers fail.")
    print(
        f"Healthy application servers remaining: "
        f"{len(healthy_instances)}"
    )

    # Restore application servers.
    for instance in architecture.compute:
        instance.healthy = True

    # Scenario 3: database fails.
    architecture.database.healthy = False

    try:
        architecture.database.insert(
            {"id": 999, "status": "test"}
        )
    except RuntimeError as error:
        print("\nScenario 3: Database failure.")
        print(f"Application operation failed safely: {error}")

    architecture.database.healthy = True


simulate_failure_scenarios(architecture)


# ============================================================================
# SECTION 29: AVAILABILITY VERSUS DURABILITY
# ============================================================================

def explain_availability_and_durability() -> None:
    print("\n28. AVAILABILITY VERSUS DURABILITY")
    print("-" * 78)

    print(
        "Availability asks: Can I access the service or data now?"
    )
    print(
        "Durability asks: Will my stored data remain intact over time?"
    )

    print(
        "\nExample: A storage system may be highly durable but temporarily "
        "unavailable during an outage."
    )

    print(
        "\nA backup can improve recoverability and durability without "
        "necessarily making an application immediately available."
    )


explain_availability_and_durability()


# ============================================================================
# SECTION 30: LATENCY AND PERFORMANCE
# ============================================================================

@dataclass
class PerformanceObservation:
    """Represents one performance measurement."""

    component: str
    latency_ms: float


def calculate_average_latency(
    observations: List[PerformanceObservation],
) -> float:
    if not observations:
        raise ValueError("At least one observation is required.")

    return sum(
        observation.latency_ms for observation in observations
    ) / len(observations)


def demonstrate_performance() -> None:
    print("\n29. PERFORMANCE CONSIDERATIONS")
    print("-" * 78)

    observations = [
        PerformanceObservation("DNS", 20),
        PerformanceObservation("Load Balancer", 10),
        PerformanceObservation("Application", 40),
        PerformanceObservation("Database", 30),
    ]

    average = calculate_average_latency(observations)

    for observation in observations:
        print(
            f"{observation.component}: "
            f"{observation.latency_ms:.1f} ms"
        )

    print(f"Average component latency: {average:.2f} ms")

    print("\nCommon performance factors:")
    print("- Network distance")
    print("- Compute capacity")
    print("- Database query performance")
    print("- Storage access pattern")
    print("- Application code")
    print("- Caching")
    print("- Concurrency")
    print("- Connection management")

    print(
        "\nPerformance should be measured rather than optimized based "
        "only on assumptions."
    )


demonstrate_performance()


# ============================================================================
# SECTION 31: CACHING CONCEPT
# ============================================================================

@dataclass
class SimpleCache:
    """Very small in-memory cache demonstration."""

    data: Dict[str, object] = field(default_factory=dict)

    def get(self, key: str) -> Optional[object]:
        return self.data.get(key)

    def set(self, key: str, value: object) -> None:
        self.data[key] = value


def demonstrate_caching() -> None:
    print("\n30. CACHING")
    print("-" * 78)

    cache = SimpleCache()

    print("Initial cache lookup:", cache.get("homepage"))

    cache.set("homepage", "cached-page-content")

    print("After caching:", cache.get("homepage"))

    print(
        "\nCaching can reduce repeated work and improve response time, "
        "but stale data, invalidation, memory usage, and consistency "
        "must be considered."
    )


demonstrate_caching()


# ============================================================================
# SECTION 32: STATEFUL VERSUS STATELESS APPLICATIONS
# ============================================================================

def compare_stateful_stateless() -> None:
    print("\n31. STATEFUL VERSUS STATELESS APPLICATIONS")
    print("-" * 78)

    print(
        "Stateless application: each request can generally be handled by "
        "any healthy application instance because session state is stored "
        "outside the instance."
    )

    print(
        "\nStateful application: an instance maintains important state "
        "locally, which can make load balancing and replacement more complex."
    )

    print(
        "\nCloud-friendly pattern: store shared state in a database, cache, "
        "object store, or other dedicated service when appropriate."
    )


compare_stateful_stateless()


# ============================================================================
# SECTION 33: MANAGED SERVICES VERSUS SELF-MANAGED INFRASTRUCTURE
# ============================================================================

def compare_managed_and_self_managed() -> None:
    print("\n32. MANAGED VERSUS SELF-MANAGED SERVICES")
    print("-" * 78)

    comparison = {
        "Managed service": [
            "Less infrastructure administration",
            "Provider handles many operational tasks",
            "Can reduce operational burden",
            "May provide less low-level control",
        ],
        "Self-managed service": [
            "More configuration control",
            "Greater responsibility for patching and operations",
            "Potentially more customization",
            "Higher operational complexity",
        ],
    }

    for category, points in comparison.items():
        print(f"\n{category}:")
        for point in points:
            print(f"  - {point}")


compare_managed_and_self_managed()


# ============================================================================
# SECTION 34: INFRASTRUCTURE AS CODE
# ============================================================================

@dataclass
class ResourceDefinition:
    """
    Provider-neutral infrastructure definition.

    Infrastructure as Code represents infrastructure configuration in
    machine-readable files so environments can be reviewed, versioned,
    tested, and reproduced.
    """

    resource_type: str
    name: str
    properties: Dict[str, object]


def demonstrate_infrastructure_as_code() -> None:
    print("\n33. INFRASTRUCTURE AS CODE")
    print("-" * 78)

    resources = [
        ResourceDefinition(
            resource_type="network",
            name="production-network",
            properties={
                "cidr": "10.0.0.0/16",
                "public_subnets": 2,
                "private_subnets": 2,
            },
        ),
        ResourceDefinition(
            resource_type="load_balancer",
            name="application-lb",
            properties={
                "protocol": "HTTPS",
                "public": True,
            },
        ),
        ResourceDefinition(
            resource_type="compute",
            name="application",
            properties={
                "instances": 2,
                "private": True,
            },
        ),
        ResourceDefinition(
            resource_type="database",
            name="application-db",
            properties={
                "private": True,
                "encrypted": True,
            },
        ),
        ResourceDefinition(
            resource_type="object_storage",
            name="application-assets",
            properties={
                "encrypted": True,
                "versioning": True,
            },
        ),
    ]

    for resource in resources:
        print(f"\nResource: {resource.resource_type}/{resource.name}")

        for key, value in resource.properties.items():
            print(f"  {key}: {value}")

    print(
        "\nThe benefit is not merely automation. Versioned infrastructure "
        "can make changes auditable and repeatable."
    )


demonstrate_infrastructure_as_code()


# ============================================================================
# SECTION 35: CONFIGURATION DRIFT
# ============================================================================

def detect_configuration_drift(
    desired: Dict[str, object],
    actual: Dict[str, object],
) -> Dict[str, Tuple[object, object]]:
    """
    Compare desired and actual configuration.

    Returns:
        A mapping of property -> (desired_value, actual_value).
    """
    differences: Dict[str, Tuple[object, object]] = {}

    all_keys = set(desired) | set(actual)

    for key in all_keys:
        desired_value = desired.get(key)
        actual_value = actual.get(key)

        if desired_value != actual_value:
            differences[key] = (desired_value, actual_value)

    return differences


def demonstrate_configuration_drift() -> None:
    print("\n34. CONFIGURATION DRIFT")
    print("-" * 78)

    desired_configuration = {
        "database_private": True,
        "database_encrypted": True,
        "https_enabled": True,
        "min_instances": 2,
    }

    actual_configuration = {
        "database_private": True,
        "database_encrypted": False,
        "https_enabled": True,
        "min_instances": 1,
    }

    differences = detect_configuration_drift(
        desired_configuration,
        actual_configuration,
    )

    if differences:
        print("Configuration drift detected:")

        for key, values in differences.items():
            desired_value, actual_value = values

            print(
                f"  {key}: desired={desired_value}, "
                f"actual={actual_value}"
            )
    else:
        print("No configuration drift detected.")


demonstrate_configuration_drift()


# ============================================================================
# SECTION 36: TESTING CLOUD ARCHITECTURE
# ============================================================================

def run_architecture_tests(architecture: Architecture) -> Dict[str, bool]:
    """
    Perform lightweight architectural tests.

    These tests demonstrate the idea of validating design requirements
    before deployment.
    """
    return {
        "multiple_compute_instances":
            len(architecture.compute) >= 2,
        "private_database":
            architecture.database.private,
        "encrypted_database":
            architecture.database.encrypted,
        "encrypted_object_storage":
            architecture.storage.encrypted,
        "versioned_object_storage":
            architecture.storage.versioning,
        "private_subnets_exist":
            len(architecture.network.private_subnets) > 0,
        "public_subnets_exist":
            len(architecture.network.public_subnets) > 0,
        "healthy_backend_exists":
            bool(architecture.load_balancer.healthy_backends()),
        "monitoring_configured":
            bool(
                architecture.monitoring.metrics
                or architecture.monitoring.logs
            ),
    }


def demonstrate_architecture_tests() -> None:
    print("\n35. ARCHITECTURE TESTING")
    print("-" * 78)

    results = run_architecture_tests(architecture)

    passed = 0

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"

        if result:
            passed += 1

        print(f"{status}: {test_name}")

    print(
        f"\nTests passed: {passed}/{len(results)}"
    )


demonstrate_architecture_tests()


# ============================================================================
# SECTION 37: COMMON ARCHITECTURE MISTAKES
# ============================================================================

def demonstrate_common_mistakes() -> None:
    print("\n36. COMMON CLOUD ARCHITECTURE MISTAKES")
    print("-" * 78)

    mistakes = {
        "Public database": (
            "Creates unnecessary direct attack surface."
        ),
        "All compute in one failure domain": (
            "A zone failure can remove the entire application."
        ),
        "Hard-coded credentials": (
            "Secrets can leak through source control and logs."
        ),
        "No backups": (
            "Accidental deletion or corruption becomes much harder to recover."
        ),
        "No monitoring": (
            "Failures can remain invisible until users report them."
        ),
        "Overly broad permissions": (
            "A compromised identity can cause excessive damage."
        ),
        "Opening every port": (
            "Increases the network attack surface."
        ),
        "No capacity limits": (
            "Unexpected traffic can cause availability problems or excessive cost."
        ),
        "No cost monitoring": (
            "Misconfigured resources can generate unexpectedly high bills."
        ),
        "No failure testing": (
            "Theoretical resilience may not match actual behavior."
        ),
    }

    for mistake, consequence in mistakes.items():
        print(f"{mistake}: {consequence}")


demonstrate_common_mistakes()


# ============================================================================
# SECTION 38: TRADE-OFFS
# ============================================================================

def demonstrate_architecture_tradeoffs() -> None:
    print("\n37. ARCHITECTURE TRADE-OFFS")
    print("-" * 78)

    tradeoffs = [
        (
            "Higher availability",
            "More instances and failure domains",
            "Higher infrastructure cost and operational complexity",
        ),
        (
            "Lower latency",
            "Caching and geographic placement",
            "More components and consistency considerations",
        ),
        (
            "Lower operational burden",
            "Managed services",
            "Potentially less low-level control",
        ),
        (
            "Maximum control",
            "Self-managed infrastructure",
            "More maintenance and security responsibility",
        ),
        (
            "Stronger recovery",
            "More backups and replication",
            "Higher storage and transfer cost",
        ),
        (
            "Broader access",
            "More permissive network rules",
            "Larger security attack surface",
        ),
    ]

    for objective, approach, tradeoff in tradeoffs:
        print(f"\nObjective: {objective}")
        print(f"Approach: {approach}")
        print(f"Trade-off: {tradeoff}")


demonstrate_architecture_tradeoffs()


# ============================================================================
# SECTION 39: PRODUCTION READINESS CHECKLIST
# ============================================================================

def production_readiness_checklist(
    architecture: Architecture,
) -> Dict[str, bool]:
    """Return a high-level production readiness checklist."""

    return {
        "authentication_configured":
            bool(architecture.users),
        "multiple_application_instances":
            len(architecture.compute) >= 2,
        "private_database":
            architecture.database.private,
        "database_encryption":
            architecture.database.encrypted,
        "storage_encryption":
            architecture.storage.encrypted,
        "storage_versioning":
            architecture.storage.versioning,
        "public_and_private_network_segments":
            bool(
                architecture.network.public_subnets
                and architecture.network.private_subnets
            ),
        "load_balancing":
            bool(architecture.load_balancer),
        "monitoring":
            bool(
                architecture.monitoring.metrics
                or architecture.monitoring.logs
            ),
        "network_security":
            bool(architecture.security_groups),
    }


def demonstrate_production_readiness() -> None:
    print("\n38. PRODUCTION-ORIENTED READINESS CHECK")
    print("-" * 78)

    checks = production_readiness_checklist(architecture)

    for check, passed in checks.items():
        print(
            f"{'PASS' if passed else 'FAIL'}: {check}"
        )


demonstrate_production_readiness()


# ============================================================================
# SECTION 40: CLOUD ARCHITECTURE DESIGN METHOD
# ============================================================================

def architecture_design_method() -> None:
    print("\n39. CLOUD ARCHITECTURE DESIGN METHOD")
    print("-" * 78)

    steps = [
        "1. Identify users and business/application requirements.",
        "2. Identify application workloads and dependencies.",
        "3. Choose an appropriate service model.",
        "4. Select a deployment model.",
        "5. Select region and failure domains.",
        "6. Design the network and subnet structure.",
        "7. Define public and private resource boundaries.",
        "8. Choose compute resources.",
        "9. Choose appropriate storage and database services.",
        "10. Design authentication and authorization.",
        "11. Apply least privilege.",
        "12. Encrypt data in transit and at rest.",
        "13. Design logging, metrics, monitoring, and alerting.",
        "14. Define backup and recovery objectives.",
        "15. Consider scalability and performance.",
        "16. Estimate cost and establish cost controls.",
        "17. Model likely failure and security scenarios.",
        "18. Validate architecture requirements.",
        "19. Automate repeatable infrastructure where appropriate.",
        "20. Test the architecture under normal and failure conditions.",
    ]

    for step in steps:
        print(step)


architecture_design_method()


# ============================================================================
# SECTION 41: COMPLETE ARCHITECTURE REVIEW
# ============================================================================

def complete_architecture_review(
    architecture: Architecture,
) -> None:
    print("\n40. COMPLETE ARCHITECTURE REVIEW")
    print("-" * 78)

    review = {
        "Users":
            f"{len(architecture.users)} configured",
        "DNS":
            architecture.dns.hostname,
        "Load balancer":
            architecture.load_balancer.name,
        "Compute":
            f"{len(architecture.compute)} instances",
        "Database":
            (
                f"{architecture.database.engine}, "
                f"private={architecture.database.private}, "
                f"encrypted={architecture.database.encrypted}"
            ),
        "Object storage":
            (
                f"encrypted={architecture.storage.encrypted}, "
                f"versioning={architecture.storage.versioning}"
            ),
        "Network":
            architecture.network.cidr,
        "Public subnets":
            str(len(architecture.network.public_subnets)),
        "Private subnets":
            str(len(architecture.network.private_subnets)),
        "Security groups":
            str(len(architecture.security_groups)),
        "Monitoring metrics":
            str(len(architecture.monitoring.metrics)),
        "Log events":
            str(len(architecture.monitoring.logs)),
    }

    for category, value in review.items():
        print(f"{category}: {value}")


complete_architecture_review(architecture)


# ============================================================================
# SECTION 42: EDGE CASES AND VALIDATION EXAMPLES
# ============================================================================

def demonstrate_edge_cases() -> None:
    print("\n41. EDGE CASES AND VALIDATION")
    print("-" * 78)

    print("Negative object size:")

    try:
        storage_bucket.upload("invalid.txt", -1)
    except ValueError as error:
        print(f"  Correctly rejected: {error}")

    print("\nInvalid block storage size:")

    try:
        BlockStorageVolume("invalid", 0)
    except ValueError as error:
        print(f"  Correctly rejected: {error}")

    print("\nInvalid capacity planning:")

    try:
        estimate_instances(100, 0)
    except ValueError as error:
        print(f"  Correctly rejected: {error}")

    print("\nEmpty latency observations:")

    try:
        calculate_average_latency([])
    except ValueError as error:
        print(f"  Correctly rejected: {error}")

    print(
        "\nValidation is important because cloud infrastructure can be "
        "expensive or security-sensitive when incorrectly configured."
    )


demonstrate_edge_cases()


# ============================================================================
# SECTION 43: KEY RELATIONSHIPS BETWEEN CLOUD COMPONENTS
# ============================================================================

def demonstrate_component_relationships() -> None:
    print("\n42. COMPONENT RELATIONSHIPS")
    print("-" * 78)

    relationships = [
        (
            "Users -> DNS",
            "Users need a way to locate an application endpoint."
        ),
        (
            "DNS -> Load balancer",
            "DNS can direct users toward the application entry point."
        ),
        (
            "Load balancer -> Compute",
            "The load balancer distributes requests to application instances."
        ),
        (
            "Compute -> Database",
            "Application servers retrieve and update structured application data."
        ),
        (
            "Compute -> Object storage",
            "Applications can store and retrieve files and large objects."
        ),
        (
            "Users -> IAM",
            "Identity systems authenticate users and control permissions."
        ),
        (
            "All components -> Monitoring",
            "Operational signals help detect and investigate failures."
        ),
        (
            "Data -> Backup",
            "Backups provide a recovery mechanism for certain data-loss scenarios."
        ),
        (
            "Network -> Security controls",
            "Network boundaries restrict which components can communicate."
        ),
    ]

    for relationship, explanation in relationships:
        print(f"{relationship}: {explanation}")


demonstrate_component_relationships()


# ============================================================================
# SECTION 44: CLOUD ARCHITECTURE PRINCIPLES
# ============================================================================

def print_architecture_principles() -> None:
    print("\n43. CORE ARCHITECTURE PRINCIPLES")
    print("-" * 78)

    principles = [
        "Design around requirements rather than choosing services first.",
        "Keep sensitive resources private unless public exposure is required.",
        "Use least privilege for identities and services.",
        "Encrypt sensitive data in transit and at rest.",
        "Separate workloads into logical network boundaries.",
        "Avoid single points of failure for important services.",
        "Monitor infrastructure and applications continuously.",
        "Maintain tested backups and recovery procedures.",
        "Design for expected growth and controlled scaling.",
        "Measure performance instead of relying only on assumptions.",
        "Treat cost as an architectural constraint.",
        "Automate repeatable infrastructure configuration.",
        "Validate security and architecture rules before deployment.",
        "Assume components can fail and design appropriate recovery paths.",
        "Document important architectural decisions and dependencies.",
    ]

    for principle in principles:
        print(f"- {principle}")


print_architecture_principles()


# ============================================================================
# SECTION 45: FINAL PROJECT OUTPUT
# ============================================================================

def print_project_output(architecture: Architecture) -> None:
    print("\n44. PROJECT OUTPUT")
    print("-" * 78)

    print(
        """
Basic cloud architecture:

Users
  |
  v
DNS
  |
  v
Public Load Balancer
  |
  +--------------------+
  |                    |
  v                    v
Private Compute A   Private Compute B
  |                    |
  +----------+---------+
             |
             v
       Private Database
             |
             v
       Encrypted Object Storage

Supporting controls:
- Identity and access management
- Role-based access control
- Least privilege
- Network segmentation
- Security groups
- HTTPS/TLS
- Encryption
- Secret management
- Monitoring
- Logging
- Backups
- Auto-scaling
- Configuration validation
- Failure testing
- Cost monitoring
"""
    )

    validation_errors = architecture.validate()

    if validation_errors:
        print("Architecture status: REVIEW REQUIRED")
        for error in validation_errors:
            print(f"- {error}")
    else:
        print("Architecture status: BASELINE DESIGN VALIDATED")

    print(
        "\nThis model is provider-neutral. A real implementation would "
        "map these conceptual components to specific cloud-provider "
        "services and then apply provider-specific networking, IAM, "
        "security, deployment, monitoring, and pricing configurations."
    )


print_project_output(architecture)


# ============================================================================
# SECTION 46: STUDY QUESTIONS
# ============================================================================

def print_review_questions() -> None:
    print("\n45. REVIEW QUESTIONS")
    print("-" * 78)

    questions = [
        "Why should a production database normally be placed in a private network?",
        "What is the difference between authentication and authorization?",
        "Why is least privilege important?",
        "What is the difference between object and block storage?",
        "Why can multiple availability zones improve availability?",
        "What is the difference between horizontal and vertical scaling?",
        "Why is encryption at rest different from encryption in transit?",
        "What problem does a load balancer solve?",
        "Why are backups not the same as high availability?",
        "What are RPO and RTO?",
        "Why should secrets not be hard-coded?",
        "What is configuration drift?",
        "Why are monitoring and logging important in production?",
        "What trade-offs can arise from using managed services?",
        "Why should architecture be tested against failure scenarios?",
        "How can network segmentation reduce attack surface?",
        "Why should cloud cost be treated as an architectural concern?",
        "What is the difference between scalability and elasticity?",
        "Why is a public subnet not automatically equivalent to a secure subnet?",
        "How does Infrastructure as Code improve repeatability?",
    ]

    for number, question in enumerate(questions, start=1):
        print(f"{number}. {question}")


print_review_questions()


# ============================================================================
# SECTION 47: SCRIPT COMPLETION
# ============================================================================

print("\n" + "=" * 78)
print("CLOUD FUNDAMENTALS REVIEW AND PROJECT COMPLETE")
print("=" * 78)
print(
    "The script demonstrated a complete basic cloud architecture using "
    "compute, storage, networking, security, identity, users, monitoring, "
    "scaling, backups, validation, and failure simulation."
)
