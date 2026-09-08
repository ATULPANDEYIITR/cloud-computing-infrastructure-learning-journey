"""
Core Cloud Infrastructure Components
====================================

A self-contained Python study script covering:

- Compute
- Storage
- Networking
- Databases
- Security
- Identity and Access Management
- Monitoring and Observability
- Automation and Infrastructure as Code
- Cloud Console concepts
- Architecture design
- Scaling and availability
- Cost and performance trade-offs
- Security and production considerations

This script uses simulations rather than connecting to a real cloud provider.
The examples demonstrate concepts shared by major cloud platforms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
import hashlib
import ipaddress
import random
import statistics
import time
import uuid


# =============================================================================
# 1. FUNDAMENTAL CLOUD CONCEPTS
# =============================================================================


class CloudServiceModel(Enum):
    """Common cloud service models."""

    IAAS = "Infrastructure as a Service"
    PAAS = "Platform as a Service"
    SAAS = "Software as a Service"


class DeploymentModel(Enum):
    """Common cloud deployment models."""

    PUBLIC = "Public Cloud"
    PRIVATE = "Private Cloud"
    HYBRID = "Hybrid Cloud"
    MULTI_CLOUD = "Multi-Cloud"


@dataclass
class CloudResource:
    """
    Base representation of a cloud resource.

    Most cloud resources have:
    - A unique identifier
    - A human-readable name
    - A region or location
    - Tags or metadata
    """

    name: str
    region: str
    resource_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tags: Dict[str, str] = field(default_factory=dict)

    def add_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def describe(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.name}, region={self.region}, id={self.resource_id})"
        )


# =============================================================================
# 2. COMPUTE
# =============================================================================


class ComputeState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"


@dataclass
class VirtualMachine(CloudResource):
    """
    Simulates an Infrastructure as a Service virtual machine.

    Important compute properties:
    - vCPU: processing capacity
    - memory_gb: RAM
    - operating_system: guest operating system
    - state: lifecycle state

    A real VM may also have disks, network interfaces, firewall rules,
    images, instance profiles, placement configuration, and monitoring agents.
    """

    vcpu: int = 2
    memory_gb: int = 4
    operating_system: str = "Linux"
    state: ComputeState = ComputeState.STOPPED
    cpu_utilization: float = 0.0

    def start(self) -> None:
        if self.state == ComputeState.TERMINATED:
            raise RuntimeError("A terminated VM cannot be restarted.")

        if self.state == ComputeState.RUNNING:
            print(f"{self.name} is already running.")
            return

        self.state = ComputeState.RUNNING
        print(f"{self.name} started.")

    def stop(self) -> None:
        if self.state == ComputeState.TERMINATED:
            raise RuntimeError("A terminated VM cannot be stopped.")

        if self.state == ComputeState.STOPPED:
            print(f"{self.name} is already stopped.")
            return

        self.state = ComputeState.STOPPED
        self.cpu_utilization = 0.0
        print(f"{self.name} stopped.")

    def terminate(self) -> None:
        self.state = ComputeState.TERMINATED
        self.cpu_utilization = 0.0
        print(f"{self.name} terminated permanently.")

    def simulate_workload(self, cpu_percent: float) -> None:
        if self.state != ComputeState.RUNNING:
            raise RuntimeError("The VM must be running before processing workloads.")

        if not 0 <= cpu_percent <= 100:
            raise ValueError("CPU utilization must be between 0 and 100.")

        self.cpu_utilization = cpu_percent
        print(f"{self.name} CPU utilization: {self.cpu_utilization:.1f}%")


@dataclass
class Container:
    """
    Simplified container representation.

    Containers package an application and its dependencies while sharing
    the host operating system kernel.
    """

    name: str
    image: str
    port: int
    environment: Dict[str, str] = field(default_factory=dict)
    running: bool = False

    def start(self) -> None:
        self.running = True
        print(f"Container {self.name} started from image {self.image}.")

    def stop(self) -> None:
        self.running = False
        print(f"Container {self.name} stopped.")


@dataclass
class ServerlessFunction:
    """
    Simulates Function as a Service.

    Serverless execution is event-driven. Infrastructure provisioning is
    abstracted away from the application developer.
    """

    name: str
    memory_mb: int
    timeout_seconds: int
    invocation_count: int = 0

    def invoke(self, event: Dict[str, str]) -> Dict[str, object]:
        self.invocation_count += 1

        return {
            "function": self.name,
            "invocation": self.invocation_count,
            "event": event,
            "status": "completed",
        }


def compute_demo() -> None:
    print("\n" + "=" * 80)
    print("COMPUTE DEMONSTRATION")
    print("=" * 80)

    vm = VirtualMachine(
        name="web-server-01",
        region="ap-south",
        vcpu=4,
        memory_gb=16,
    )

    vm.start()
    vm.simulate_workload(72.5)
    vm.stop()

    container = Container(
        name="api-service",
        image="example/api:1.0",
        port=8080,
        environment={"ENV": "production"},
    )
    container.start()

    function = ServerlessFunction(
        name="process-upload",
        memory_mb=512,
        timeout_seconds=30,
    )

    result = function.invoke({"file": "document.pdf", "action": "process"})
    print(result)


# =============================================================================
# 3. AUTO SCALING
# =============================================================================


@dataclass
class AutoScalingGroup:
    """
    Simplified auto-scaling simulation.

    Auto scaling changes the number of compute instances according to demand.

    Important trade-offs:
    - Scaling too slowly can increase latency.
    - Scaling too aggressively can increase cost.
    - Scaling decisions should avoid rapid oscillation.
    """

    name: str
    minimum_instances: int
    maximum_instances: int
    target_cpu_percent: float
    desired_instances: int

    def __post_init__(self) -> None:
        if self.minimum_instances < 1:
            raise ValueError("Minimum instances must be at least 1.")

        if self.maximum_instances < self.minimum_instances:
            raise ValueError("Maximum instances must be >= minimum instances.")

        if not (
            self.minimum_instances
            <= self.desired_instances
            <= self.maximum_instances
        ):
            raise ValueError("Desired instances must be within scaling limits.")

    def evaluate(self, average_cpu_percent: float) -> int:
        """
        Scale out when utilization is significantly above target.
        Scale in when utilization is significantly below target.
        """

        if average_cpu_percent > self.target_cpu_percent + 10:
            self.desired_instances = min(
                self.desired_instances + 1,
                self.maximum_instances,
            )
        elif average_cpu_percent < self.target_cpu_percent - 20:
            self.desired_instances = max(
                self.desired_instances - 1,
                self.minimum_instances,
            )

        return self.desired_instances


def autoscaling_demo() -> None:
    print("\n" + "=" * 80)
    print("AUTO SCALING DEMONSTRATION")
    print("=" * 80)

    group = AutoScalingGroup(
        name="web-application-group",
        minimum_instances=2,
        maximum_instances=10,
        target_cpu_percent=60,
        desired_instances=3,
    )

    workloads = [25, 45, 70, 82, 95, 55, 30]

    for cpu in workloads:
        instances = group.evaluate(cpu)
        print(
            f"Average CPU: {cpu:>3}% | "
            f"Desired instances: {instances}"
        )


# =============================================================================
# 4. STORAGE
# =============================================================================


class StorageType(Enum):
    OBJECT = "Object Storage"
    BLOCK = "Block Storage"
    FILE = "File Storage"


@dataclass
class ObjectStorageObject:
    """
    Represents an object stored in object storage.

    Object storage typically stores:
    - Object data
    - Object key
    - Metadata

    Object storage is commonly used for:
    - Images
    - Videos
    - Backups
    - Logs
    - Data lakes
    - Static website content
    """

    key: str
    data: bytes
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def size_bytes(self) -> int:
        return len(self.data)

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass
class ObjectStorageBucket(CloudResource):
    objects: Dict[str, ObjectStorageObject] = field(default_factory=dict)
    versioning_enabled: bool = False
    versions: Dict[str, List[ObjectStorageObject]] = field(default_factory=dict)

    def put_object(
        self,
        key: str,
        data: bytes,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        if metadata is None:
            metadata = {}

        new_object = ObjectStorageObject(
            key=key,
            data=data,
            metadata=metadata,
        )

        if self.versioning_enabled and key in self.objects:
            self.versions.setdefault(key, []).append(self.objects[key])

        self.objects[key] = new_object

    def get_object(self, key: str) -> ObjectStorageObject:
        if key not in self.objects:
            raise KeyError(f"Object '{key}' does not exist.")

        return self.objects[key]

    def delete_object(self, key: str) -> None:
        if key not in self.objects:
            raise KeyError(f"Object '{key}' does not exist.")

        del self.objects[key]

    def list_objects(self, prefix: str = "") -> List[str]:
        return sorted(
            key for key in self.objects
            if key.startswith(prefix)
        )


@dataclass
class BlockVolume:
    """
    Simulates block storage attached to a virtual machine.

    Block storage is commonly used for:
    - Operating system disks
    - Databases
    - High-performance applications
    """

    name: str
    size_gb: int
    attached_instance: Optional[str] = None

    def attach(self, instance_name: str) -> None:
        if self.attached_instance is not None:
            raise RuntimeError(
                f"Volume is already attached to {self.attached_instance}."
            )

        self.attached_instance = instance_name

    def detach(self) -> None:
        self.attached_instance = None


@dataclass
class FileStorage:
    """
    Simplified shared file storage.

    File storage uses hierarchical paths and is useful when multiple
    compute systems need shared filesystem access.
    """

    files: Dict[str, bytes] = field(default_factory=dict)

    def write(self, path: str, content: bytes) -> None:
        if not path.startswith("/"):
            raise ValueError("File paths must be absolute.")

        self.files[path] = content

    def read(self, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)

        return self.files[path]


def storage_demo() -> None:
    print("\n" + "=" * 80)
    print("STORAGE DEMONSTRATION")
    print("=" * 80)

    bucket = ObjectStorageBucket(
        name="application-assets",
        region="ap-south",
        versioning_enabled=True,
    )

    bucket.put_object(
        "images/logo.txt",
        b"version 1",
        {"content-type": "text/plain"},
    )

    bucket.put_object(
        "images/logo.txt",
        b"version 2",
        {"content-type": "text/plain"},
    )

    current_object = bucket.get_object("images/logo.txt")

    print("Current object:", current_object.data)
    print("Checksum:", current_object.checksum)
    print("Previous versions:", len(bucket.versions["images/logo.txt"]))

    volume = BlockVolume(name="database-volume", size_gb=100)
    volume.attach("database-server-01")
    print(f"Block volume attached to: {volume.attached_instance}")

    shared_storage = FileStorage()
    shared_storage.write("/shared/report.txt", b"Cloud infrastructure")
    print(shared_storage.read("/shared/report.txt").decode())


# =============================================================================
# 5. NETWORKING
# =============================================================================


@dataclass
class Subnet:
    """
    A subnet divides a larger IP network into smaller networks.

    Public subnet:
    - May provide routes to the public internet.

    Private subnet:
    - Usually does not accept unsolicited direct internet traffic.
    """

    name: str
    cidr: str
    public: bool = False

    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.ip_network(self.cidr, strict=False)


@dataclass
class VirtualNetwork(CloudResource):
    """
    Simulates a Virtual Private Cloud or equivalent virtual network.
    """

    cidr: str = "10.0.0.0/16"
    subnets: Dict[str, Subnet] = field(default_factory=dict)

    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.ip_network(self.cidr, strict=False)

    def add_subnet(self, subnet: Subnet) -> None:
        parent_network = self.network()
        child_network = subnet.network()

        if not child_network.subnet_of(parent_network):
            raise ValueError(
                f"Subnet {subnet.cidr} is outside network {self.cidr}."
            )

        for existing_subnet in self.subnets.values():
            if child_network.overlaps(existing_subnet.network()):
                raise ValueError(
                    f"Subnet {subnet.cidr} overlaps with {existing_subnet.cidr}."
                )

        self.subnets[subnet.name] = subnet


class Protocol(Enum):
    TCP = "TCP"
    UDP = "UDP"
    ICMP = "ICMP"


@dataclass(frozen=True)
class SecurityRule:
    protocol: Protocol
    port: Optional[int]
    source: str
    allow: bool = True


@dataclass
class SecurityGroup:
    """
    A stateful virtual firewall.

    Rules control allowed network traffic.

    Security principle:
    Use least privilege. Avoid unrestricted access such as 0.0.0.0/0
    unless public access is genuinely required.
    """

    name: str
    inbound_rules: List[SecurityRule] = field(default_factory=list)

    def add_rule(self, rule: SecurityRule) -> None:
        self.inbound_rules.append(rule)

    def allows(
        self,
        source_ip: str,
        protocol: Protocol,
        port: Optional[int],
    ) -> bool:
        source_address = ipaddress.ip_address(source_ip)

        for rule in self.inbound_rules:
            if not rule.allow:
                continue

            if rule.protocol != protocol:
                continue

            if rule.port is not None and rule.port != port:
                continue

            allowed_network = ipaddress.ip_network(
                rule.source,
                strict=False,
            )

            if source_address in allowed_network:
                return True

        return False


@dataclass
class LoadBalancer:
    """
    Simplified load balancer.

    Load balancing distributes requests across healthy targets.
    """

    name: str
    targets: List[str] = field(default_factory=list)
    healthy_targets: Set[str] = field(default_factory=set)
    _current_index: int = 0

    def add_target(self, target: str) -> None:
        self.targets.append(target)
        self.healthy_targets.add(target)

    def set_health(self, target: str, healthy: bool) -> None:
        if target not in self.targets:
            raise ValueError("Unknown target.")

        if healthy:
            self.healthy_targets.add(target)
        else:
            self.healthy_targets.discard(target)

    def route_request(self) -> str:
        healthy = sorted(self.healthy_targets)

        if not healthy:
            raise RuntimeError("No healthy targets are available.")

        target = healthy[self._current_index % len(healthy)]
        self._current_index += 1
        return target


def networking_demo() -> None:
    print("\n" + "=" * 80)
    print("NETWORKING DEMONSTRATION")
    print("=" * 80)

    network = VirtualNetwork(
        name="production-network",
        region="ap-south",
        cidr="10.0.0.0/16",
    )

    network.add_subnet(
        Subnet(
            name="public-subnet",
            cidr="10.0.1.0/24",
            public=True,
        )
    )

    network.add_subnet(
        Subnet(
            name="private-subnet",
            cidr="10.0.2.0/24",
            public=False,
        )
    )

    print("Configured subnets:", list(network.subnets))

    firewall = SecurityGroup(name="web-firewall")

    firewall.add_rule(
        SecurityRule(
            protocol=Protocol.TCP,
            port=443,
            source="0.0.0.0/0",
        )
    )

    firewall.add_rule(
        SecurityRule(
            protocol=Protocol.TCP,
            port=22,
            source="10.0.0.0/16",
        )
    )

    print(
        "HTTPS from internet:",
        firewall.allows(
            source_ip="203.0.113.10",
            protocol=Protocol.TCP,
            port=443,
        ),
    )

    print(
        "SSH from internet:",
        firewall.allows(
            source_ip="203.0.113.10",
            protocol=Protocol.TCP,
            port=22,
        ),
    )

    load_balancer = LoadBalancer(name="application-load-balancer")

    for target in ["app-01", "app-02", "app-03"]:
        load_balancer.add_target(target)

    load_balancer.set_health("app-02", False)

    for request_number in range(5):
        print(
            f"Request {request_number + 1} routed to "
            f"{load_balancer.route_request()}"
        )


# =============================================================================
# 6. DATABASES
# =============================================================================


class DatabaseType(Enum):
    RELATIONAL = "Relational"
    DOCUMENT = "Document"
    KEY_VALUE = "Key-Value"
    GRAPH = "Graph"
    WAREHOUSE = "Data Warehouse"


@dataclass
class InMemoryRelationalTable:
    """
    Simplified relational table.

    Real relational databases provide:
    - SQL
    - Indexes
    - Transactions
    - Constraints
    - Query planning
    - Concurrency control
    - Durability
    """

    name: str
    primary_key: str
    rows: Dict[object, Dict[str, object]] = field(default_factory=dict)

    def insert(self, row: Dict[str, object]) -> None:
        if self.primary_key not in row:
            raise ValueError(
                f"Primary key '{self.primary_key}' is required."
            )

        key = row[self.primary_key]

        if key in self.rows:
            raise ValueError(f"Duplicate primary key: {key}")

        self.rows[key] = dict(row)

    def get(self, key: object) -> Optional[Dict[str, object]]:
        row = self.rows.get(key)
        return dict(row) if row is not None else None

    def update(
        self,
        key: object,
        updates: Dict[str, object],
    ) -> None:
        if key not in self.rows:
            raise KeyError(key)

        self.rows[key].update(updates)

    def delete(self, key: object) -> None:
        if key not in self.rows:
            raise KeyError(key)

        del self.rows[key]

    def filter_by(
        self,
        column: str,
        value: object,
    ) -> List[Dict[str, object]]:
        return [
            dict(row)
            for row in self.rows.values()
            if row.get(column) == value
        ]


@dataclass
class SimpleKeyValueStore:
    """
    Simulates a key-value database.

    Useful for workloads requiring:
    - Fast lookup by key
    - Simple data access patterns
    - Horizontal scalability
    """

    data: Dict[str, object] = field(default_factory=dict)

    def put(self, key: str, value: object) -> None:
        self.data[key] = value

    def get(self, key: str, default: object = None) -> object:
        return self.data.get(key, default)

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


def database_demo() -> None:
    print("\n" + "=" * 80)
    print("DATABASE DEMONSTRATION")
    print("=" * 80)

    users = InMemoryRelationalTable(
        name="users",
        primary_key="user_id",
    )

    users.insert(
        {
            "user_id": 1,
            "name": "Asha",
            "department": "Engineering",
        }
    )

    users.insert(
        {
            "user_id": 2,
            "name": "Ravi",
            "department": "Operations",
        }
    )

    users.update(1, {"department": "Platform Engineering"})

    print("User 1:", users.get(1))
    print(
        "Operations users:",
        users.filter_by("department", "Operations"),
    )

    cache = SimpleKeyValueStore()
    cache.put("session:user:1", {"authenticated": True})
    print("Session data:", cache.get("session:user:1"))


# =============================================================================
# 7. DATABASE REPLICATION AND AVAILABILITY
# =============================================================================


@dataclass
class DatabaseReplica:
    name: str
    healthy: bool = True


@dataclass
class ReplicatedDatabase:
    """
    Simplified primary-replica architecture.

    Typical pattern:
    - Writes go to the primary.
    - Reads may be distributed across replicas.

    Important trade-off:
    Replication can introduce replication lag, meaning a replica may not
    immediately reflect the latest write.
    """

    primary_name: str
    replicas: List[DatabaseReplica] = field(default_factory=list)
    data: Dict[str, object] = field(default_factory=dict)
    replica_data: Dict[str, Dict[str, object]] = field(default_factory=dict)

    def write(self, key: str, value: object) -> None:
        self.data[key] = value

    def replicate(self) -> None:
        for replica in self.replicas:
            if replica.healthy:
                self.replica_data[replica.name] = dict(self.data)

    def read_primary(self, key: str) -> object:
        return self.data.get(key)

    def read_replica(self, replica_name: str, key: str) -> object:
        if replica_name not in self.replica_data:
            raise KeyError(
                f"Replica '{replica_name}' has not received replicated data."
            )

        return self.replica_data[replica_name].get(key)


def replication_demo() -> None:
    print("\n" + "=" * 80)
    print("DATABASE REPLICATION DEMONSTRATION")
    print("=" * 80)

    database = ReplicatedDatabase(
        primary_name="db-primary",
        replicas=[
            DatabaseReplica("db-replica-01"),
            DatabaseReplica("db-replica-02"),
        ],
    )

    database.write("order:1001", {"status": "created"})

    print(
        "Primary before replication:",
        database.read_primary("order:1001"),
    )

    database.replicate()

    print(
        "Replica after replication:",
        database.read_replica("db-replica-01", "order:1001"),
    )


# =============================================================================
# 8. SECURITY
# =============================================================================


class EncryptionAlgorithm(Enum):
    SHA256 = "SHA256"
    SIMULATED_AES = "SIMULATED_AES"


def hash_value(value: str) -> str:
    """
    Hashing is one-way.

    Hashes are commonly used for:
    - Integrity verification
    - Password storage when combined with secure password hashing algorithms
    - Content addressing

    This example uses SHA-256 for demonstration. Password systems should use
    dedicated password hashing algorithms such as Argon2, bcrypt, or scrypt.
    """

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class SecretStore:
    """
    Simplified secret management service.

    Secrets should not normally be:
    - Hardcoded into source code
    - Stored in public repositories
    - Printed in logs
    - Exposed to unauthorized users
    """

    secrets: Dict[str, str] = field(default_factory=dict)

    def store_secret(self, name: str, secret_value: str) -> None:
        if not name:
            raise ValueError("Secret name cannot be empty.")

        self.secrets[name] = secret_value

    def retrieve_secret(self, name: str) -> str:
        if name not in self.secrets:
            raise KeyError("Secret does not exist.")

        return self.secrets[name]


@dataclass
class EncryptionKey:
    """
    Simplified representation of an encryption key.

    Real cloud key management systems provide secure key storage,
    access control, rotation, auditing, and cryptographic operations.
    """

    key_id: str
    enabled: bool = True

    def disable(self) -> None:
        self.enabled = False

    def enable(self) -> None:
        self.enabled = True


def security_demo() -> None:
    print("\n" + "=" * 80)
    print("SECURITY DEMONSTRATION")
    print("=" * 80)

    sensitive_value = "example-sensitive-value"
    digest = hash_value(sensitive_value)

    print("SHA-256 digest:", digest)

    secrets = SecretStore()
    secrets.store_secret("database-password", "example-password")

    # Demonstration only. Production applications should avoid printing secrets.
    print(
        "Secret stored successfully:",
        "database-password" in secrets.secrets,
    )

    key = EncryptionKey(key_id="key-001")
    print("Encryption key enabled:", key.enabled)
    key.disable()
    print("Encryption key enabled:", key.enabled)


# =============================================================================
# 9. IDENTITY AND ACCESS MANAGEMENT
# =============================================================================


class Permission(Enum):
    COMPUTE_READ = "compute:read"
    COMPUTE_WRITE = "compute:write"
    STORAGE_READ = "storage:read"
    STORAGE_WRITE = "storage:write"
    DATABASE_READ = "database:read"
    DATABASE_WRITE = "database:write"


@dataclass
class Policy:
    """
    A policy maps a set of permissions to a principal.
    """

    name: str
    permissions: Set[Permission]


@dataclass
class Identity:
    """
    Represents a human user, service account, role, or workload identity.
    """

    name: str
    policies: List[Policy] = field(default_factory=list)

    def attach_policy(self, policy: Policy) -> None:
        self.policies.append(policy)

    def has_permission(self, permission: Permission) -> bool:
        return any(
            permission in policy.permissions
            for policy in self.policies
        )


class AuthorizationError(PermissionError):
    """Raised when an identity lacks required permission."""


def require_permission(
    identity: Identity,
    permission: Permission,
) -> None:
    if not identity.has_permission(permission):
        raise AuthorizationError(
            f"{identity.name} does not have permission {permission.value}."
        )


def identity_demo() -> None:
    print("\n" + "=" * 80)
    print("IDENTITY AND ACCESS MANAGEMENT DEMONSTRATION")
    print("=" * 80)

    read_only_storage_policy = Policy(
        name="StorageReadOnly",
        permissions={Permission.STORAGE_READ},
    )

    application_identity = Identity(name="application-service")
    application_identity.attach_policy(read_only_storage_policy)

    require_permission(
        application_identity,
        Permission.STORAGE_READ,
    )

    print("Storage read access granted.")

    try:
        require_permission(
            application_identity,
            Permission.STORAGE_WRITE,
        )
    except AuthorizationError as error:
        print("Authorization failure:", error)


# =============================================================================
# 10. MONITORING AND OBSERVABILITY
# =============================================================================


@dataclass
class Metric:
    """
    A metric is a numerical measurement over time.

    Examples:
    - CPU utilization
    - Memory utilization
    - Request count
    - Error rate
    - Latency
    """

    name: str
    values: List[float] = field(default_factory=list)

    def record(self, value: float) -> None:
        self.values.append(value)

    def average(self) -> float:
        if not self.values:
            return 0.0

        return statistics.mean(self.values)

    def maximum(self) -> float:
        if not self.values:
            return 0.0

        return max(self.values)


@dataclass
class LogEntry:
    timestamp: float
    level: str
    message: str


@dataclass
class Logger:
    """
    Structured logging simulation.

    Production logs should avoid sensitive information such as:
    - Passwords
    - Authentication tokens
    - Private encryption keys
    - Unnecessary personal data
    """

    entries: List[LogEntry] = field(default_factory=list)

    def log(self, level: str, message: str) -> None:
        self.entries.append(
            LogEntry(
                timestamp=time.time(),
                level=level,
                message=message,
            )
        )

    def search(self, level: Optional[str] = None) -> List[LogEntry]:
        if level is None:
            return list(self.entries)

        return [
            entry
            for entry in self.entries
            if entry.level == level
        ]


@dataclass
class Alert:
    name: str
    threshold: float
    comparison: str

    def evaluate(self, value: float) -> bool:
        if self.comparison == ">":
            return value > self.threshold

        if self.comparison == "<":
            return value < self.threshold

        raise ValueError("Unsupported comparison operator.")


def monitoring_demo() -> None:
    print("\n" + "=" * 80)
    print("MONITORING DEMONSTRATION")
    print("=" * 80)

    cpu_metric = Metric(name="CPUUtilization")

    for value in [25.0, 40.0, 55.0, 88.0, 92.0]:
        cpu_metric.record(value)

    print("Average CPU:", cpu_metric.average())
    print("Maximum CPU:", cpu_metric.maximum())

    high_cpu_alert = Alert(
        name="HighCPU",
        threshold=80.0,
        comparison=">",
    )

    print(
        "Alert triggered:",
        high_cpu_alert.evaluate(cpu_metric.maximum()),
    )

    logger = Logger()
    logger.log("INFO", "Application started")
    logger.log("WARNING", "Response latency increased")
    logger.log("ERROR", "Database connection failed")

    for entry in logger.search("ERROR"):
        print(entry.level, entry.message)


# =============================================================================
# 11. SERVICE LEVEL INDICATORS AND ERROR RATES
# =============================================================================


@dataclass
class ServiceMetrics:
    """
    Tracks service reliability metrics.

    Common concepts:
    - SLI: measured reliability indicator
    - SLO: reliability target
    - SLA: contractual commitment
    """

    total_requests: int = 0
    successful_requests: int = 0
    latencies_ms: List[float] = field(default_factory=list)

    def record_request(
        self,
        successful: bool,
        latency_ms: float,
    ) -> None:
        self.total_requests += 1

        if successful:
            self.successful_requests += 1

        self.latencies_ms.append(latency_ms)

    def availability_percent(self) -> float:
        if self.total_requests == 0:
            return 100.0

        return (
            self.successful_requests
            / self.total_requests
            * 100
        )

    def error_rate_percent(self) -> float:
        return 100.0 - self.availability_percent()

    def percentile_latency(self, percentile: float) -> float:
        if not self.latencies_ms:
            return 0.0

        if not 0 <= percentile <= 100:
            raise ValueError("Percentile must be between 0 and 100.")

        sorted_values = sorted(self.latencies_ms)

        position = (
            percentile / 100
            * (len(sorted_values) - 1)
        )

        lower = int(position)
        upper = min(lower + 1, len(sorted_values) - 1)

        if lower == upper:
            return sorted_values[lower]

        fraction = position - lower

        return (
            sorted_values[lower]
            + (
                sorted_values[upper]
                - sorted_values[lower]
            )
            * fraction
        )


def reliability_demo() -> None:
    print("\n" + "=" * 80)
    print("RELIABILITY METRICS DEMONSTRATION")
    print("=" * 80)

    metrics = ServiceMetrics()

    for successful, latency in [
        (True, 100),
        (True, 120),
        (True, 150),
        (False, 800),
        (True, 110),
        (True, 130),
        (True, 200),
    ]:
        metrics.record_request(successful, latency)

    print(
        "Availability:",
        f"{metrics.availability_percent():.2f}%",
    )

    print(
        "Error rate:",
        f"{metrics.error_rate_percent():.2f}%",
    )

    print(
        "P95 latency:",
        f"{metrics.percentile_latency(95):.2f} ms",
    )


# =============================================================================
# 12. AUTOMATION AND INFRASTRUCTURE AS CODE
# =============================================================================


@dataclass(frozen=True)
class ResourceDefinition:
    """
    Declarative desired-state representation.

    Infrastructure as Code commonly describes:
    - Desired resources
    - Dependencies
    - Configuration
    - Repeatable deployment definitions
    """

    resource_type: str
    name: str
    properties: Tuple[Tuple[str, str], ...]

    @classmethod
    def from_dict(
        cls,
        resource_type: str,
        name: str,
        properties: Dict[str, object],
    ) -> "ResourceDefinition":
        normalized = tuple(
            sorted(
                (
                    str(key),
                    str(value),
                )
                for key, value in properties.items()
            )
        )

        return cls(
            resource_type=resource_type,
            name=name,
            properties=normalized,
        )


@dataclass
class InfrastructureState:
    resources: Dict[str, ResourceDefinition] = field(
        default_factory=dict
    )


class InfrastructureEngine:
    """
    Very small declarative infrastructure engine.

    It compares:
    - Desired state
    - Current state

    Then reports:
    - CREATE
    - UPDATE
    - DELETE
    - NO CHANGE

    Real Infrastructure as Code systems also manage provider APIs,
    dependencies, state persistence, locking, retries, drift, and failures.
    """

    def plan(
        self,
        desired: List[ResourceDefinition],
        current: InfrastructureState,
    ) -> List[str]:
        actions: List[str] = []

        desired_map = {
            resource.name: resource
            for resource in desired
        }

        for name, resource in desired_map.items():
            if name not in current.resources:
                actions.append(f"CREATE {resource.resource_type} {name}")
            elif current.resources[name] != resource:
                actions.append(f"UPDATE {resource.resource_type} {name}")
            else:
                actions.append(
                    f"NO CHANGE {resource.resource_type} {name}"
                )

        for name, resource in current.resources.items():
            if name not in desired_map:
                actions.append(f"DELETE {resource.resource_type} {name}")

        return actions

    def apply(
        self,
        desired: List[ResourceDefinition],
        current: InfrastructureState,
    ) -> None:
        current.resources = {
            resource.name: resource
            for resource in desired
        }


def automation_demo() -> None:
    print("\n" + "=" * 80)
    print("AUTOMATION AND INFRASTRUCTURE AS CODE")
    print("=" * 80)

    desired_resources = [
        ResourceDefinition.from_dict(
            "VirtualMachine",
            "web-server",
            {
                "vcpu": 4,
                "memory_gb": 16,
            },
        ),
        ResourceDefinition.from_dict(
            "ObjectStorageBucket",
            "application-assets",
            {
                "versioning": True,
            },
        ),
    ]

    current_state = InfrastructureState()

    engine = InfrastructureEngine()

    print("Initial plan:")

    for action in engine.plan(
        desired_resources,
        current_state,
    ):
        print(" ", action)

    engine.apply(
        desired_resources,
        current_state,
    )

    print("\nPlan after apply:")

    for action in engine.plan(
        desired_resources,
        current_state,
    ):
        print(" ", action)


# =============================================================================
# 13. CLOUD CONSOLE SIMULATION
# =============================================================================


@dataclass
class CloudConsole:
    """
    Simulates a graphical or web-based cloud management console.

    Cloud consoles commonly provide:
    - Resource dashboards
    - Resource creation
    - Monitoring
    - Access management
    - Billing information
    - Configuration interfaces

    Important production consideration:
    Manual console changes can cause configuration drift when infrastructure
    is also managed through Infrastructure as Code.
    """

    resources: Dict[str, CloudResource] = field(
        default_factory=dict
    )

    def register(self, resource: CloudResource) -> None:
        if resource.resource_id in self.resources:
            raise ValueError("Resource ID already exists.")

        self.resources[resource.resource_id] = resource

    def list_resources(self) -> List[str]:
        return [
            resource.describe()
            for resource in self.resources.values()
        ]

    def find_by_name(
        self,
        name: str,
    ) -> List[CloudResource]:
        return [
            resource
            for resource in self.resources.values()
            if resource.name == name
        ]


def console_demo() -> None:
    print("\n" + "=" * 80)
    print("CLOUD CONSOLE DEMONSTRATION")
    print("=" * 80)

    console = CloudConsole()

    vm = VirtualMachine(
        name="console-web-server",
        region="ap-south",
        vcpu=2,
        memory_gb=8,
    )

    bucket = ObjectStorageBucket(
        name="console-data-bucket",
        region="ap-south",
    )

    network = VirtualNetwork(
        name="console-network",
        region="ap-south",
    )

    for resource in [vm, bucket, network]:
        console.register(resource)

    for description in console.list_resources():
        print(description)


# =============================================================================
# 14. COST MODELING
# =============================================================================


@dataclass
class CostModel:
    """
    Simplified cloud cost model.

    Real cloud pricing may include:
    - Compute duration
    - CPU architecture
    - Storage capacity
    - Storage requests
    - Data transfer
    - Managed service usage
    - Reserved capacity
    - Spot or interruptible capacity
    """

    hourly_compute_rate: float
    storage_gb_month_rate: float
    network_gb_rate: float

    def estimate(
        self,
        compute_hours: float,
        storage_gb: float,
        network_gb: float,
    ) -> float:
        if (
            compute_hours < 0
            or storage_gb < 0
            or network_gb < 0
        ):
            raise ValueError("Usage values cannot be negative.")

        compute_cost = (
            compute_hours
            * self.hourly_compute_rate
        )

        storage_cost = (
            storage_gb
            * self.storage_gb_month_rate
        )

        network_cost = (
            network_gb
            * self.network_gb_rate
        )

        return (
            compute_cost
            + storage_cost
            + network_cost
        )


def cost_demo() -> None:
    print("\n" + "=" * 80)
    print("COST MODELING DEMONSTRATION")
    print("=" * 80)

    pricing = CostModel(
        hourly_compute_rate=0.12,
        storage_gb_month_rate=0.02,
        network_gb_rate=0.08,
    )

    estimated_cost = pricing.estimate(
        compute_hours=720,
        storage_gb=500,
        network_gb=100,
    )

    print(
        "Estimated monthly infrastructure cost:",
        f"${estimated_cost:.2f}",
    )


# =============================================================================
# 15. HIGH AVAILABILITY AND FAILURE SIMULATION
# =============================================================================


@dataclass
class AvailabilityZone:
    name: str
    healthy: bool = True


@dataclass
class HighlyAvailableService:
    """
    A service distributed across multiple failure domains.

    High availability improves resilience by avoiding dependence on a
    single server or availability zone.
    """

    name: str
    zones: List[AvailabilityZone]

    def available(self) -> bool:
        return any(zone.healthy for zone in self.zones)

    def healthy_zone_names(self) -> List[str]:
        return [
            zone.name
            for zone in self.zones
            if zone.healthy
        ]


def availability_demo() -> None:
    print("\n" + "=" * 80)
    print("HIGH AVAILABILITY DEMONSTRATION")
    print("=" * 80)

    service = HighlyAvailableService(
        name="payment-service",
        zones=[
            AvailabilityZone("zone-a"),
            AvailabilityZone("zone-b"),
            AvailabilityZone("zone-c"),
        ],
    )

    print("Service available:", service.available())
    print("Healthy zones:", service.healthy_zone_names())

    service.zones[0].healthy = False
    service.zones[1].healthy = False

    print("\nAfter two zone failures:")
    print("Service available:", service.available())
    print("Healthy zones:", service.healthy_zone_names())

    service.zones[2].healthy = False

    print("\nAfter all zone failures:")
    print("Service available:", service.available())


# =============================================================================
# 16. BACKUP AND DISASTER RECOVERY
# =============================================================================


@dataclass
class Backup:
    backup_id: str
    timestamp: float
    data: Dict[str, object]


@dataclass
class BackupService:
    """
    Simplified backup system.

    Important disaster recovery concepts:
    - RPO: Recovery Point Objective
    - RTO: Recovery Time Objective
    - Backup retention
    - Geographic redundancy
    - Restore testing
    """

    backups: List[Backup] = field(default_factory=list)

    def create_backup(
        self,
        source_data: Dict[str, object],
    ) -> Backup:
        backup = Backup(
            backup_id=str(uuid.uuid4()),
            timestamp=time.time(),
            data=dict(source_data),
        )

        self.backups.append(backup)
        return backup

    def restore_latest(self) -> Dict[str, object]:
        if not self.backups:
            raise RuntimeError("No backups are available.")

        latest = max(
            self.backups,
            key=lambda backup: backup.timestamp,
        )

        return dict(latest.data)


def backup_demo() -> None:
    print("\n" + "=" * 80)
    print("BACKUP AND DISASTER RECOVERY DEMONSTRATION")
    print("=" * 80)

    service = BackupService()

    production_data = {
        "user_count": 1000,
        "orders": 5000,
    }

    backup = service.create_backup(production_data)

    print("Backup created:", backup.backup_id)

    production_data["orders"] = 0

    restored_data = service.restore_latest()

    print("Restored data:", restored_data)


# =============================================================================
# 17. END-TO-END CLOUD ARCHITECTURE SIMULATION
# =============================================================================


@dataclass
class CloudApplicationArchitecture:
    """
    Represents a simplified production application architecture.

    Request flow:

        User
          |
          v
      Load Balancer
          |
          v
      Compute Layer
          |
          +-------------------+
          |                   |
          v                   v
      Database           Object Storage
          |
          v
       Backups

    Cross-cutting concerns:
    - IAM
    - Security groups
    - Monitoring
    - Logging
    - Automation
    """

    load_balancer: LoadBalancer
    compute_instances: List[VirtualMachine]
    database: ReplicatedDatabase
    storage: ObjectStorageBucket
    logger: Logger
    service_metrics: ServiceMetrics

    def handle_request(
        self,
        user_id: str,
        payload: Dict[str, object],
    ) -> Dict[str, object]:
        start = time.perf_counter()

        try:
            target = self.load_balancer.route_request()

            self.logger.log(
                "INFO",
                f"Request for user {user_id} routed to {target}",
            )

            object_key = (
                f"requests/{user_id}/{uuid.uuid4()}.txt"
            )

            self.storage.put_object(
                object_key,
                str(payload).encode("utf-8"),
            )

            database_key = f"request:{user_id}"

            self.database.write(
                database_key,
                {
                    "target": target,
                    "storage_key": object_key,
                },
            )

            latency_ms = (
                time.perf_counter()
                - start
            ) * 1000

            self.service_metrics.record_request(
                successful=True,
                latency_ms=latency_ms,
            )

            return {
                "status": "success",
                "target": target,
                "storage_key": object_key,
                "latency_ms": latency_ms,
            }

        except Exception as error:
            latency_ms = (
                time.perf_counter()
                - start
            ) * 1000

            self.logger.log(
                "ERROR",
                str(error),
            )

            self.service_metrics.record_request(
                successful=False,
                latency_ms=latency_ms,
            )

            return {
                "status": "error",
                "message": str(error),
            }


def end_to_end_architecture_demo() -> None:
    print("\n" + "=" * 80)
    print("END-TO-END CLOUD ARCHITECTURE DEMONSTRATION")
    print("=" * 80)

    load_balancer = LoadBalancer(
        name="production-load-balancer"
    )

    instances = [
        VirtualMachine(
            name="application-01",
            region="ap-south",
            vcpu=4,
            memory_gb=16,
        ),
        VirtualMachine(
            name="application-02",
            region="ap-south",
            vcpu=4,
            memory_gb=16,
        ),
    ]

    for instance in instances:
        instance.start()
        load_balancer.add_target(instance.name)

    database = ReplicatedDatabase(
        primary_name="primary-database",
        replicas=[
            DatabaseReplica("database-replica"),
        ],
    )

    storage = ObjectStorageBucket(
        name="application-request-data",
        region="ap-south",
    )

    logger = Logger()
    metrics = ServiceMetrics()

    architecture = CloudApplicationArchitecture(
        load_balancer=load_balancer,
        compute_instances=instances,
        database=database,
        storage=storage,
        logger=logger,
        service_metrics=metrics,
    )

    response = architecture.handle_request(
        user_id="user-123",
        payload={
            "action": "create-order",
            "amount": 2500,
        },
    )

    print("Application response:")
    print(response)

    database.replicate()

    print(
        "\nAvailability:",
        f"{metrics.availability_percent():.2f}%",
    )

    print(
        "Stored objects:",
        len(storage.objects),
    )

    print(
        "Database records:",
        len(database.data),
    )


# =============================================================================
# 18. PERFORMANCE CONSIDERATIONS
# =============================================================================


def performance_demo() -> None:
    print("\n" + "=" * 80)
    print("PERFORMANCE CONSIDERATIONS")
    print("=" * 80)

    sample_latencies = [
        random.uniform(50, 250)
        for _ in range(100)
    ]

    average_latency = statistics.mean(sample_latencies)
    maximum_latency = max(sample_latencies)

    print(
        "Average simulated latency:",
        f"{average_latency:.2f} ms",
    )

    print(
        "Maximum simulated latency:",
        f"{maximum_latency:.2f} ms",
    )

    print(
        "\nPerformance design considerations:"
    )

    considerations = [
        "Use caching for frequently accessed data.",
        "Distribute traffic with load balancers.",
        "Scale compute capacity according to demand.",
        "Place compute and data services close to reduce latency.",
        "Use indexes for appropriate database query patterns.",
        "Avoid unnecessary network transfers.",
        "Measure bottlenecks before optimizing.",
    ]

    for item in considerations:
        print("-", item)


# =============================================================================
# 19. PRODUCTION DESIGN PRINCIPLES
# =============================================================================


def production_design_demo() -> None:
    print("\n" + "=" * 80)
    print("PRODUCTION DESIGN PRINCIPLES")
    print("=" * 80)

    principles = {
        "Reliability": [
            "Remove single points of failure.",
            "Use backups and test restoration.",
            "Deploy across multiple failure domains.",
        ],
        "Security": [
            "Apply least privilege.",
            "Protect secrets.",
            "Encrypt sensitive data.",
            "Audit privileged actions.",
        ],
        "Performance": [
            "Measure latency and throughput.",
            "Use appropriate compute capacity.",
            "Optimize database access patterns.",
        ],
        "Cost": [
            "Match resource size to workload requirements.",
            "Automatically scale when appropriate.",
            "Remove unused resources.",
        ],
        "Operational Excellence": [
            "Automate repeatable infrastructure changes.",
            "Monitor systems continuously.",
            "Maintain useful logs and alerts.",
        ],
    }

    for category, items in principles.items():
        print(f"\n{category}:")
        for item in items:
            print("-", item)


# =============================================================================
# 20. COMMON MISTAKES AND EDGE CASES
# =============================================================================


def common_mistakes_demo() -> None:
    print("\n" + "=" * 80)
    print("COMMON MISTAKES AND EDGE CASES")
    print("=" * 80)

    print("\n1. Overlapping network subnets:")

    network = VirtualNetwork(
        name="test-network",
        region="test-region",
        cidr="10.1.0.0/16",
    )

    network.add_subnet(
        Subnet(
            name="first",
            cidr="10.1.1.0/24",
        )
    )

    try:
        network.add_subnet(
            Subnet(
                name="overlapping",
                cidr="10.1.1.128/25",
            )
        )
    except ValueError as error:
        print("Caught expected error:", error)

    print("\n2. Unauthorized access:")

    identity = Identity(name="limited-service")

    try:
        require_permission(
            identity,
            Permission.DATABASE_WRITE,
        )
    except AuthorizationError as error:
        print("Caught expected error:", error)

    print("\n3. Reading an object that does not exist:")

    bucket = ObjectStorageBucket(
        name="edge-case-bucket",
        region="test-region",
    )

    try:
        bucket.get_object("missing-file.txt")
    except KeyError as error:
        print("Caught expected error:", error)

    print("\n4. Routing traffic with no healthy instances:")

    balancer = LoadBalancer(name="empty-balancer")

    try:
        balancer.route_request()
    except RuntimeError as error:
        print("Caught expected error:", error)


# =============================================================================
# MAIN EXECUTION
# =============================================================================


def main() -> None:
    """
    Runs all demonstrations in a logical progression from infrastructure
    fundamentals through integrated production architecture concepts.
    """

    print("=" * 80)
    print("CORE CLOUD INFRASTRUCTURE COMPONENTS")
    print("=" * 80)

    print("\nCloud service models:")
    for model in CloudServiceModel:
        print("-", model.value)

    print("\nCloud deployment models:")
    for model in DeploymentModel:
        print("-", model.value)

    compute_demo()
    autoscaling_demo()
    storage_demo()
    networking_demo()
    database_demo()
    replication_demo()
    security_demo()
    identity_demo()
    monitoring_demo()
    reliability_demo()
    automation_demo()
    console_demo()
    cost_demo()
    availability_demo()
    backup_demo()
    end_to_end_architecture_demo()
    performance_demo()
    production_design_demo()
    common_mistakes_demo()

    print("\n" + "=" * 80)
    print("CLOUD INFRASTRUCTURE STUDY SCRIPT COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()
