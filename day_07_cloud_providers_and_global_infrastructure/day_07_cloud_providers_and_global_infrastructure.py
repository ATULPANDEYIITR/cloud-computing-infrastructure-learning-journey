"""
Cloud Providers and Global Infrastructure
==========================================

A standalone study script covering:

1. Cloud computing providers and service models
2. Global infrastructure terminology
3. Regions and availability zones
4. Edge locations and points of presence
5. Data centers, clusters, and fault domains
6. Latency, geography, and network distance
7. High availability and fault tolerance
8. Disaster recovery and multi-region architecture
9. Traffic routing and latency-aware selection
10. Capacity, scalability, and load distribution
11. Data residency and compliance considerations
12. Provider comparisons
13. Multi-cloud and hybrid-cloud designs
14. Cost and performance trade-offs
15. Security and infrastructure design
16. Monitoring and operational considerations
17. Practical simulations
18. Validation, testing, and advanced design patterns

The examples are simulations. They do not create real cloud resources and do
not require cloud-provider credentials or external packages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from statistics import mean
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# ============================================================================

def print_section(title: str) -> None:
    """Print a readable section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


print_section("1. CLOUD PROVIDERS AND GLOBAL INFRASTRUCTURE")

print(
    """
A cloud provider operates physical and logical infrastructure that customers
can consume through APIs, consoles, automation systems, or managed services.

Examples of major public-cloud providers include:

- Amazon Web Services (AWS)
- Microsoft Azure
- Google Cloud
- Oracle Cloud Infrastructure (OCI)
- IBM Cloud
- Alibaba Cloud

A provider's global infrastructure is the geographic and physical foundation
used to deliver cloud services.

Important terms:

Provider
    The organization operating cloud infrastructure and managed services.

Region
    A geographically distinct cloud deployment area containing one or more
    physically separate availability zones or equivalent fault domains.

Availability Zone (AZ)
    An isolated infrastructure location within a region. A cloud provider
    normally designs zones so that failures in one zone are less likely to
    affect another zone.

Data center
    A physical facility containing compute, storage, networking, power,
    cooling, security, and other infrastructure.

Edge location
    A location positioned closer to end users and commonly used for services
    such as content delivery, caching, DNS, and request acceleration.

Point of Presence (PoP)
    A network presence point where traffic can enter, leave, or traverse a
    provider's network. A PoP may contain networking and edge infrastructure.

Fault domain
    A group of resources sharing a possible failure boundary.

Failure domain
    A physical or logical boundary within which a failure may occur.

Global infrastructure
    The combined geographic, physical, networking, and service-delivery
    infrastructure operated by a cloud provider.
"""
)


# ============================================================================
# 2. CLOUD SERVICE MODELS
# ============================================================================

class ServiceModel(Enum):
    """Common cloud service-consumption models."""

    IAAS = "Infrastructure as a Service"
    PAAS = "Platform as a Service"
    SAAS = "Software as a Service"
    FAAS = "Function as a Service"


@dataclass(frozen=True)
class CloudService:
    """Represents a simplified cloud service."""

    name: str
    model: ServiceModel
    provider: str
    description: str


SERVICES = [
    CloudService(
        "Virtual machine",
        ServiceModel.IAAS,
        "Generic provider",
        "Customer manages the operating system and applications.",
    ),
    CloudService(
        "Managed database",
        ServiceModel.PAAS,
        "Generic provider",
        "Provider manages much of the database infrastructure.",
    ),
    CloudService(
        "Hosted application",
        ServiceModel.SAAS,
        "Generic provider",
        "Customer primarily consumes a complete application.",
    ),
    CloudService(
        "Serverless function",
        ServiceModel.FAAS,
        "Generic provider",
        "Code executes in provider-managed infrastructure.",
    ),
]

print_section("2. CLOUD SERVICE MODELS")

for service in SERVICES:
    print(f"{service.name:22} | {service.model.value:30} | {service.description}")


# ============================================================================
# 3. PROVIDER AND INFRASTRUCTURE REPRESENTATION
# ============================================================================

@dataclass
class AvailabilityZone:
    """A simplified availability zone."""

    name: str
    city: str
    capacity_units: int
    active: bool = True

    def available_capacity(self) -> int:
        """Return capacity only when the zone is operational."""
        return self.capacity_units if self.active else 0


@dataclass
class Region:
    """A cloud region containing multiple availability zones."""

    name: str
    country: str
    latitude: float
    longitude: float
    zones: List[AvailabilityZone] = field(default_factory=list)

    def active_zones(self) -> List[AvailabilityZone]:
        """Return operational zones."""
        return [zone for zone in self.zones if zone.active]

    def total_capacity(self) -> int:
        """Calculate active capacity across all zones."""
        return sum(zone.available_capacity() for zone in self.zones)


@dataclass
class EdgeLocation:
    """A simplified edge or PoP location."""

    name: str
    city: str
    country: str
    latitude: float
    longitude: float
    services: Tuple[str, ...]


@dataclass
class CloudProvider:
    """Simplified representation of a cloud provider's global footprint."""

    name: str
    regions: List[Region]
    edge_locations: List[EdgeLocation]

    def region(self, name: str) -> Optional[Region]:
        """Find a region by name."""
        for region in self.regions:
            if region.name == name:
                return region
        return None

    def active_region_count(self) -> int:
        """Count regions containing at least one active zone."""
        return sum(bool(region.active_zones()) for region in self.regions)


# ============================================================================
# 4. BUILD A SIMULATED MULTI-REGION PROVIDER
# ============================================================================

provider = CloudProvider(
    name="ExampleCloud",
    regions=[
        Region(
            name="us-east",
            country="United States",
            latitude=37.0,
            longitude=-77.0,
            zones=[
                AvailabilityZone("us-east-a", "Virginia", 100),
                AvailabilityZone("us-east-b", "Virginia", 100),
                AvailabilityZone("us-east-c", "Virginia", 100),
            ],
        ),
        Region(
            name="eu-west",
            country="Ireland",
            latitude=53.3,
            longitude=-6.3,
            zones=[
                AvailabilityZone("eu-west-a", "Dublin", 90),
                AvailabilityZone("eu-west-b", "Dublin", 90),
                AvailabilityZone("eu-west-c", "Dublin", 90),
            ],
        ),
        Region(
            name="ap-south",
            country="India",
            latitude=19.1,
            longitude=72.9,
            zones=[
                AvailabilityZone("ap-south-a", "Mumbai", 80),
                AvailabilityZone("ap-south-b", "Mumbai", 80),
                AvailabilityZone("ap-south-c", "Mumbai", 80),
            ],
        ),
    ],
    edge_locations=[
        EdgeLocation(
            "edge-mumbai",
            "Mumbai",
            "India",
            19.1,
            72.9,
            ("CDN", "DNS", "TLS termination"),
        ),
        EdgeLocation(
            "edge-london",
            "London",
            "United Kingdom",
            51.5,
            -0.1,
            ("CDN", "DNS", "TLS termination"),
        ),
        EdgeLocation(
            "edge-new-york",
            "New York",
            "United States",
            40.7,
            -74.0,
            ("CDN", "DNS", "TLS termination"),
        ),
    ],
)


def describe_provider(cloud_provider: CloudProvider) -> None:
    """Print the simulated provider's infrastructure."""
    print_section(f"3. {cloud_provider.name.upper()} GLOBAL INFRASTRUCTURE")

    print(f"Provider: {cloud_provider.name}")
    print(f"Active regions: {cloud_provider.active_region_count()}")

    for region in cloud_provider.regions:
        print(
            f"\nRegion: {region.name} ({region.country})"
            f"\n  Active zones: {len(region.active_zones())}"
            f"\n  Active capacity: {region.total_capacity()} units"
        )

        for zone in region.zones:
            print(
                f"    {zone.name:14} "
                f"location={zone.city:10} "
                f"capacity={zone.capacity_units:3} "
                f"active={zone.active}"
            )

    print("\nEdge locations:")
    for edge in cloud_provider.edge_locations:
        print(
            f"  {edge.name:18} {edge.city:12} "
            f"services={', '.join(edge.services)}"
        )


describe_provider(provider)


# ============================================================================
# 5. REGION VS AVAILABILITY ZONE
# ============================================================================

print_section("4. REGION VS AVAILABILITY ZONE")

print(
    """
A region is primarily a geographic and administrative deployment boundary.

An availability zone is an isolated failure domain inside a region.

Example:

    Region: ap-south
        |
        +-- Availability Zone A
        |
        +-- Availability Zone B
        |
        +-- Availability Zone C

A single-zone architecture can fail when that zone becomes unavailable.

A multi-zone architecture distributes workloads:

    Load Balancer
          |
      +---+---+
      |   |   |
     AZ-A AZ-B AZ-C
      |   |   |
     App App App
      +---+---+
          |
       Database

The important principle is not merely "use multiple servers."

The stronger principle is:

    Avoid placing all critical components inside the same failure domain.
"""
)


# ============================================================================
# 6. EDGE LOCATIONS AND POINTS OF PRESENCE
# ============================================================================

@dataclass
class User:
    """Represents a client location."""

    name: str
    city: str
    latitude: float
    longitude: float


users = [
    User("User India", "Delhi", 28.6, 77.2),
    User("User Europe", "Paris", 48.9, 2.4),
    User("User USA", "New York", 40.7, -74.0),
]


print_section("5. EDGE LOCATIONS AND POINTS OF PRESENCE")

print(
    """
The origin application may be located in a cloud region, while users can
connect to nearby edge infrastructure.

A simplified request path can look like:

    User
      |
      v
    Nearby PoP / Edge
      |
      v
    Provider Backbone
      |
      v
    Regional Origin
      |
      v
    Application

Edge infrastructure can reduce the distance that frequently requested content
travels to users.

Typical edge workloads include:

- Content caching
- DNS resolution
- TLS termination
- Traffic acceleration
- DDoS absorption
- HTTP request routing
- Static asset delivery

Edge infrastructure does not automatically mean that the application's
database or complete application stack is physically located there.
"""
)


# ============================================================================
# 7. GEOGRAPHIC DISTANCE AND LATENCY
# ============================================================================

def approximate_distance_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """
    Estimate geographic distance using the equirectangular approximation.

    This is sufficient for educational ranking and is not a replacement for
    actual network measurements.
    """
    from math import cos, radians, sqrt

    x = radians(longitude_2 - longitude_1) * cos(
        radians((latitude_1 + latitude_2) / 2)
    )
    y = radians(latitude_2 - latitude_1)

    earth_radius_km = 6371.0
    return earth_radius_km * sqrt(x * x + y * y)


def estimated_latency_ms(distance_km: float) -> float:
    """
    Estimate a simplified network round-trip latency.

    Real latency depends on fiber paths, routing, congestion, peering,
    processing, queues, and many other factors.
    """
    # Deliberately simplified educational model.
    propagation_component = distance_km / 100.0
    processing_and_routing = 8.0
    return propagation_component + processing_and_routing


def rank_regions_by_distance(
    user: User,
    regions: Sequence[Region],
) -> List[Tuple[str, float, float]]:
    """Rank active regions by estimated distance and latency."""
    candidates = []

    for region in regions:
        if not region.active_zones():
            continue

        distance = approximate_distance_km(
            user.latitude,
            user.longitude,
            region.latitude,
            region.longitude,
        )
        latency = estimated_latency_ms(distance)
        candidates.append((region.name, distance, latency))

    return sorted(candidates, key=lambda item: item[2])


print_section("6. LATENCY-AWARE REGION SELECTION")

for user in users:
    print(f"\nClient: {user.city}")

    for region_name, distance, latency in rank_regions_by_distance(
        user, provider.regions
    ):
        print(
            f"  {region_name:12} "
            f"distance≈{distance:7.0f} km "
            f"estimated_latency≈{latency:5.1f} ms"
        )

print(
    """
Important distinction:

Geographic proximity is a useful heuristic, not a guarantee of low latency.

Two locations at similar geographic distances can have different network
latencies because Internet traffic does not necessarily follow the shortest
geographic path.
"""
)


# ============================================================================
# 8. EDGE ROUTING
# ============================================================================

def nearest_edge(
    user: User,
    edges: Sequence[EdgeLocation],
) -> Optional[Tuple[EdgeLocation, float]]:
    """Return the geographically closest edge location."""
    if not edges:
        return None

    ranked = []

    for edge in edges:
        distance = approximate_distance_km(
            user.latitude,
            user.longitude,
            edge.latitude,
            edge.longitude,
        )
        ranked.append((edge, distance))

    return min(ranked, key=lambda item: item[1])


print_section("7. USERS AND EDGE LOCATIONS")

for user in users:
    result = nearest_edge(user, provider.edge_locations)

    if result:
        edge, distance = result
        print(
            f"{user.city:10} -> {edge.city:12} "
            f"distance≈{distance:7.0f} km"
        )


# ============================================================================
# 9. HIGH AVAILABILITY
# ============================================================================

@dataclass
class ApplicationInstance:
    """A simplified application instance."""

    name: str
    zone: str
    healthy: bool = True


def available_instances(
    instances: Iterable[ApplicationInstance],
) -> List[ApplicationInstance]:
    """Return healthy instances."""
    return [instance for instance in instances if instance.healthy]


print_section("8. HIGH AVAILABILITY")

instances = [
    ApplicationInstance("app-1", "us-east-a"),
    ApplicationInstance("app-2", "us-east-b"),
    ApplicationInstance("app-3", "us-east-c"),
]

print(f"Healthy instances: {len(available_instances(instances))}")

# Simulate a complete AZ failure.
for instance in instances:
    if instance.zone == "us-east-b":
        instance.healthy = False

print("After us-east-b failure:")
for instance in instances:
    print(
        f"  {instance.name} zone={instance.zone} "
        f"healthy={instance.healthy}"
    )

print(f"Remaining healthy instances: {len(available_instances(instances))}")

print(
    """
High availability is about continuing service despite failures.

A multi-AZ architecture reduces the probability that a single zone-level
failure will take down the entire application.

High availability is not the same as disaster recovery:

    High Availability
        -> handles failures during normal operation

    Disaster Recovery
        -> restores or continues service after larger failures
"""
)


# ============================================================================
# 10. AVAILABILITY AND REDUNDANCY MATH
# ============================================================================

def series_availability(component_availability: Sequence[float]) -> float:
    """
    Calculate availability for components that all need to work.

    Example:
        Application AND database

    The system availability is approximately the product of the component
    availabilities when failures are independent.
    """
    result = 1.0

    for availability in component_availability:
        result *= availability

    return result


def parallel_availability(component_availability: Sequence[float]) -> float:
    """
    Calculate availability for redundant components where at least one must
    remain available.

    Example:
        Two independent application instances behind a load balancer.
    """
    probability_all_fail = 1.0

    for availability in component_availability:
        probability_all_fail *= 1.0 - availability

    return 1.0 - probability_all_fail


print_section("9. AVAILABILITY CALCULATIONS")

single_service = series_availability([0.9999, 0.9999])
redundant_service = parallel_availability([0.9999, 0.9999])

print(f"Two required components in series: {single_service:.6f}")
print(f"Two redundant components in parallel: {redundant_service:.6f}")

print(
    """
Redundancy can improve availability, but the mathematical benefit depends
on assumptions such as independence.

Real systems often have correlated failures.

For example, two application servers can both fail if they depend on:

- the same availability zone
- the same database
- the same network path
- the same software release
- the same identity service
- the same power infrastructure
- the same human deployment action

This is why simply adding replicas does not automatically produce resilience.
"""
)


# ============================================================================
# 11. FAILURE-DOMAIN ANALYSIS
# ============================================================================

@dataclass
class Resource:
    """A resource assigned to a fault domain."""

    name: str
    region: str
    zone: str


def failure_domain_report(resources: Sequence[Resource]) -> Dict[str, List[str]]:
    """Group resources by availability zone."""
    result: Dict[str, List[str]] = {}

    for resource in resources:
        result.setdefault(resource.zone, []).append(resource.name)

    return result


resources = [
    Resource("web-1", "us-east", "us-east-a"),
    Resource("web-2", "us-east", "us-east-b"),
    Resource("web-3", "us-east", "us-east-c"),
    Resource("db-primary", "us-east", "us-east-a"),
    Resource("cache-1", "us-east", "us-east-b"),
]

print_section("10. FAILURE-DOMAIN ANALYSIS")

for zone, resource_names in failure_domain_report(resources).items():
    print(f"{zone}: {', '.join(resource_names)}")

print(
    """
A design review should ask:

1. Where is each component deployed?
2. What infrastructure can fail together?
3. What happens if one zone disappears?
4. What happens if the whole region disappears?
5. Which dependencies remain available?
6. Can traffic move automatically?
7. Can state be recovered?
"""
)


# ============================================================================
# 12. MULTI-REGION ARCHITECTURE
# ============================================================================

@dataclass
class RegionalService:
    """Represents an application deployment in one region."""

    region_name: str
    healthy: bool = True
    capacity_units: int = 0


regional_services = [
    RegionalService("us-east", True, 300),
    RegionalService("eu-west", True, 270),
    RegionalService("ap-south", True, 240),
]


def choose_healthy_region(
    user: User,
    services: Sequence[RegionalService],
    regions: Sequence[Region],
) -> Optional[RegionalService]:
    """
    Choose a healthy regional deployment using estimated latency.

    Capacity is checked after latency ranking.
    """
    region_lookup = {region.name: region for region in regions}

    candidates = []

    for service in services:
        if not service.healthy or service.capacity_units <= 0:
            continue

        region = region_lookup.get(service.region_name)

        if region is None or not region.active_zones():
            continue

        distance = approximate_distance_km(
            user.latitude,
            user.longitude,
            region.latitude,
            region.longitude,
        )
        latency = estimated_latency_ms(distance)

        candidates.append((latency, service))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


print_section("11. MULTI-REGION TRAFFIC SELECTION")

for user in users:
    selected = choose_healthy_region(
        user,
        regional_services,
        provider.regions,
    )

    print(
        f"{user.city:10} -> "
        f"{selected.region_name if selected else 'NO AVAILABLE REGION'}"
    )


# ============================================================================
# 13. FAILOVER
# ============================================================================

print_section("12. MULTI-REGION FAILOVER")

print("Initial regional health:")
for service in regional_services:
    print(f"  {service.region_name}: healthy={service.healthy}")

# Simulate an entire region becoming unavailable.
regional_services[0].healthy = False

print("\nAfter us-east regional failure:")

for service in regional_services:
    print(f"  {service.region_name}: healthy={service.healthy}")

for user in users:
    selected = choose_healthy_region(
        user,
        regional_services,
        provider.regions,
    )

    print(
        f"{user.city:10} -> "
        f"{selected.region_name if selected else 'NO AVAILABLE REGION'}"
    )

print(
    """
A real failover architecture requires more than selecting another region.

The system may need:

- Global DNS or traffic management
- Health checks
- Application replication
- Database replication
- Object-storage replication
- Secret and configuration replication
- Identity dependencies
- Infrastructure-as-code
- Data recovery procedures
- Automated or manual promotion
- Testing of the recovery process

A region-level failover can also introduce data-consistency problems.
"""
)


# ============================================================================
# 14. ACTIVE-ACTIVE VS ACTIVE-PASSIVE
# ============================================================================

class DisasterRecoveryMode(Enum):
    ACTIVE_ACTIVE = "Active-Active"
    ACTIVE_PASSIVE = "Active-Passive"


@dataclass
class DRDesign:
    mode: DisasterRecoveryMode
    primary_region: str
    secondary_regions: List[str]
    expected_rto_minutes: int
    expected_rpo_minutes: int


designs = [
    DRDesign(
        DisasterRecoveryMode.ACTIVE_ACTIVE,
        "us-east",
        ["eu-west", "ap-south"],
        1,
        0,
    ),
    DRDesign(
        DisasterRecoveryMode.ACTIVE_PASSIVE,
        "us-east",
        ["eu-west"],
        30,
        15,
    ),
]

print_section("13. DISASTER RECOVERY MODES")

for design in designs:
    print(
        f"{design.mode.value:16} "
        f"RTO={design.expected_rto_minutes:3} min "
        f"RPO={design.expected_rpo_minutes:3} min"
    )

print(
    """
RTO = Recovery Time Objective
    How long the organization can tolerate service unavailability.

RPO = Recovery Point Objective
    How much data loss, measured in time, can be tolerated.

Active-active:
    Multiple regions actively serve traffic.

Advantages:
    - Lower failover time
    - Better global latency
    - Capacity can be used continuously

Challenges:
    - More complex data consistency
    - Higher operational cost
    - More complicated deployments

Active-passive:
    One region serves production traffic while another is prepared for
    recovery.

Advantages:
    - Simpler architecture
    - Often lower steady-state cost

Challenges:
    - Failover can take longer
    - Standby capacity may be underutilized
    - Recovery procedures require rigorous testing
"""
)


# ============================================================================
# 15. DATA RESIDENCY AND GEOGRAPHIC CONSTRAINTS
# ============================================================================

@dataclass
class DataPolicy:
    """Simplified data-placement policy."""

    allowed_countries: Tuple[str, ...]
    must_remain_in_region: bool


@dataclass
class DataStore:
    """Represents a regional data store."""

    name: str
    region: str
    country: str


def is_data_location_compliant(
    data_store: DataStore,
    policy: DataPolicy,
) -> bool:
    """Check a simplified geographic data policy."""
    return data_store.country in policy.allowed_countries


print_section("14. DATA RESIDENCY AND DATA LOCATION")

india_policy = DataPolicy(
    allowed_countries=("India",),
    must_remain_in_region=True,
)

india_store = DataStore(
    name="customer-db",
    region="ap-south",
    country="India",
)

europe_store = DataStore(
    name="backup-db",
    region="eu-west",
    country="Ireland",
)

print(
    f"{india_store.name}: "
    f"compliant={is_data_location_compliant(india_store, india_policy)}"
)

print(
    f"{europe_store.name}: "
    f"compliant={is_data_location_compliant(europe_store, india_policy)}"
)

print(
    """
Geographic placement can be constrained by:

- Data residency requirements
- Privacy regulations
- Contractual obligations
- Industry requirements
- Internal security policies
- Customer requirements
- Export controls
- Disaster-recovery policies

A design cannot assume that copying data to another region is always legal
or operationally acceptable.

Actual compliance depends on the applicable laws, contracts, service
configuration, and organization's legal interpretation.
"""
)


# ============================================================================
# 16. GLOBAL INFRASTRUCTURE COMPARISON
# ============================================================================

@dataclass(frozen=True)
class ProviderProfile:
    """High-level conceptual provider profile."""

    name: str
    typical_strengths: Tuple[str, ...]
    architectural_characteristics: Tuple[str, ...]


profiles = [
    ProviderProfile(
        "AWS",
        (
            "Very broad service catalog",
            "Mature global cloud ecosystem",
            "Large enterprise and startup adoption",
        ),
        (
            "Regions and Availability Zones",
            "Extensive edge and networking services",
        ),
    ),
    ProviderProfile(
        "Microsoft Azure",
        (
            "Strong enterprise integration",
            "Broad hybrid-cloud capabilities",
            "Large global footprint",
        ),
        (
            "Regions and availability-zone architecture",
            "Strong enterprise identity integration",
        ),
    ),
    ProviderProfile(
        "Google Cloud",
        (
            "Strong global networking",
            "Data and analytics capabilities",
            "Container and Kubernetes ecosystem",
        ),
        (
            "Regions and zones",
            "Large private backbone",
        ),
    ),
    ProviderProfile(
        "Oracle Cloud Infrastructure",
        (
            "Database-centric enterprise workloads",
            "Enterprise infrastructure services",
        ),
        (
            "Regions and availability domains",
            "Dedicated cloud infrastructure options",
        ),
    ),
    ProviderProfile(
        "IBM Cloud",
        (
            "Enterprise and regulated workloads",
            "Hybrid-cloud orientation",
        ),
        (
            "Regional infrastructure",
            "Bare-metal and enterprise options",
        ),
    ),
    ProviderProfile(
        "Alibaba Cloud",
        (
            "Large presence in Asia",
            "Strong China and Asia-Pacific ecosystem",
        ),
        (
            "Regions and zones",
            "Broad cloud and edge services",
        ),
    ),
]

print_section("15. MAJOR CLOUD PROVIDERS")

for profile in profiles:
    print(f"\n{profile.name}")
    print("  Strengths:")
    for strength in profile.typical_strengths:
        print(f"    - {strength}")

    print("  Infrastructure characteristics:")
    for characteristic in profile.architectural_characteristics:
        print(f"    - {characteristic}")

print(
    """
Provider terminology is not perfectly standardized.

For example, one provider may call an isolated infrastructure grouping a
"zone", while another uses different terminology such as "availability
domain" or another fault-domain concept.

The architectural idea is more important than memorizing names:

    geographic isolation
        +
    independent failure domains
        +
    network connectivity
        +
    service-specific deployment boundaries
"""
)


# ============================================================================
# 17. REGION SELECTION DECISION MODEL
# ============================================================================

@dataclass
class RegionDecision:
    """Factors used in a region-selection decision."""

    name: str
    latency_score: float
    compliance_score: float
    cost_score: float
    service_score: float
    resilience_score: float


def weighted_region_score(
    decision: RegionDecision,
    weights: Dict[str, float],
) -> float:
    """Calculate a weighted region-selection score."""
    return (
        decision.latency_score * weights["latency"]
        + decision.compliance_score * weights["compliance"]
        + decision.cost_score * weights["cost"]
        + decision.service_score * weights["services"]
        + decision.resilience_score * weights["resilience"]
    )


decisions = [
    RegionDecision("us-east", 70, 80, 90, 100, 95),
    RegionDecision("eu-west", 80, 95, 75, 95, 90),
    RegionDecision("ap-south", 100, 100, 80, 85, 85),
]

weights = {
    "latency": 0.30,
    "compliance": 0.25,
    "cost": 0.15,
    "services": 0.15,
    "resilience": 0.15,
}

print_section("16. REGION SELECTION AS A MULTI-CRITERIA PROBLEM")

ranked_decisions = sorted(
    decisions,
    key=lambda item: weighted_region_score(item, weights),
    reverse=True,
)

for decision in ranked_decisions:
    score = weighted_region_score(decision, weights)
    print(f"{decision.name:12} score={score:6.2f}")

print(
    """
Region selection should not be based solely on price or geographic distance.

Typical factors include:

1. User latency
2. Data residency
3. Regulatory requirements
4. Required cloud services
5. Availability characteristics
6. Capacity availability
7. Service quotas
8. Network connectivity
9. Pricing
10. Existing operational expertise
11. Disaster-recovery requirements
12. Inter-region data-transfer costs
13. Vendor-specific dependencies

The best region is therefore a business and engineering decision rather than
a purely geographic decision.
"""
)


# ============================================================================
# 18. CAPACITY PLANNING
# ============================================================================

def required_capacity(
    peak_requests_per_second: int,
    requests_per_unit_per_second: int,
    headroom_ratio: float = 0.30,
) -> int:
    """
    Estimate required capacity units with headroom.

    Example:
        1000 requests/sec
        100 requests/sec per unit
        30% headroom

        Base = 10 units
        Required = ceil(10 * 1.30) = 13 units
    """
    if peak_requests_per_second < 0:
        raise ValueError("Peak request rate cannot be negative.")

    if requests_per_unit_per_second <= 0:
        raise ValueError("Per-unit capacity must be positive.")

    if headroom_ratio < 0:
        raise ValueError("Headroom ratio cannot be negative.")

    base_units = ceil(
        peak_requests_per_second / requests_per_unit_per_second
    )

    return ceil(base_units * (1.0 + headroom_ratio))


print_section("17. CAPACITY PLANNING")

for region_name, request_rate in [
    ("us-east", 1500),
    ("eu-west", 1000),
    ("ap-south", 700),
]:
    capacity = required_capacity(request_rate, 100, 0.30)
    print(
        f"{region_name:12} "
        f"peak={request_rate:4} req/s "
        f"capacity={capacity:3} units"
    )

print(
    """
Capacity planning must account for:

- Average traffic
- Peak traffic
- Traffic growth
- Failure scenarios
- Maintenance
- Deployment capacity
- Autoscaling delay
- Quotas
- Regional capacity
- Dependency capacity

A multi-region architecture must also consider what happens when one region
fails and another region must absorb its traffic.
"""
)


# ============================================================================
# 19. REGION FAILURE CAPACITY SIMULATION
# ============================================================================

def can_survive_region_failure(
    services: Sequence[RegionalService],
    traffic_units: int,
) -> bool:
    """
    Determine whether remaining healthy regions can absorb the traffic.
    """
    healthy_capacity = sum(
        service.capacity_units
        for service in services
        if service.healthy
    )

    return healthy_capacity >= traffic_units


print_section("18. REGION FAILURE CAPACITY TEST")

regional_services = [
    RegionalService("us-east", True, 300),
    RegionalService("eu-west", True, 250),
    RegionalService("ap-south", True, 200),
]

normal_traffic = 400
failure_traffic = 400

print(
    f"Normal traffic={normal_traffic}, "
    f"survivable={can_survive_region_failure(regional_services, normal_traffic)}"
)

regional_services[0].healthy = False

print(
    f"After us-east failure, traffic={failure_traffic}, "
    f"survivable="
    f"{can_survive_region_failure(regional_services, failure_traffic)}"
)

print(
    """
A resilient architecture should be evaluated under failure conditions, not
only under normal conditions.

A useful question is:

    "If the largest region disappears, can the remaining infrastructure
     handle the required workload?"

This is a capacity-resilience question.
"""
)


# ============================================================================
# 20. LOAD DISTRIBUTION
# ============================================================================

def distribute_requests(
    request_count: int,
    regional_capacity: Dict[str, int],
) -> Dict[str, int]:
    """
    Distribute requests approximately proportionally to capacity.

    This models weighted routing rather than implementing a real load balancer.
    """
    if request_count < 0:
        raise ValueError("Request count cannot be negative.")

    if any(capacity < 0 for capacity in regional_capacity.values()):
        raise ValueError("Capacity cannot be negative.")

    total_capacity = sum(regional_capacity.values())

    if total_capacity == 0:
        raise ValueError("At least one region must have capacity.")

    result = {}

    for region_name, capacity in regional_capacity.items():
        result[region_name] = int(
            request_count * capacity / total_capacity
        )

    # Correct rounding loss by assigning remaining requests to the largest
    # capacity region.
    allocated = sum(result.values())
    remainder = request_count - allocated

    if remainder:
        largest_region = max(
            regional_capacity,
            key=regional_capacity.get,
        )
        result[largest_region] += remainder

    return result


print_section("19. CAPACITY-WEIGHTED TRAFFIC DISTRIBUTION")

distribution = distribute_requests(
    1000,
    {
        "us-east": 500,
        "eu-west": 300,
        "ap-south": 200,
    },
)

for region_name, requests in distribution.items():
    print(f"{region_name:12}: {requests} requests")


# ============================================================================
# 21. EDGE CACHING SIMULATION
# ============================================================================

@dataclass
class Cache:
    """Simple key-value cache used to demonstrate edge caching."""

    entries: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> Optional[str]:
        """Return cached content or None."""
        return self.entries.get(key)

    def put(self, key: str, value: str) -> None:
        """Store content in the cache."""
        self.entries[key] = value


def fetch_content(
    cache: Cache,
    content_key: str,
    origin: Dict[str, str],
) -> Tuple[str, str]:
    """
    Simulate a cache lookup.

    Returns:
        (content, "CACHE_HIT") or (content, "ORIGIN")
    """
    cached = cache.get(content_key)

    if cached is not None:
        return cached, "CACHE_HIT"

    if content_key not in origin:
        raise KeyError(f"Origin content not found: {content_key}")

    value = origin[content_key]
    cache.put(content_key, value)
    return value, "ORIGIN"


print_section("20. EDGE CACHING")

origin_content = {
    "/logo.png": "IMAGE-DATA",
    "/style.css": "CSS-DATA",
    "/index.html": "HTML-DATA",
}

edge_cache = Cache()

for path in ["/logo.png", "/logo.png", "/style.css", "/logo.png"]:
    content, source = fetch_content(edge_cache, path, origin_content)
    print(f"{path:15} source={source:10} content={content}")


# ============================================================================
# 22. CACHE CONSISTENCY
# ============================================================================

print(
    """
Edge caching introduces an important trade-off:

    Lower latency
        vs.
    Freshness and consistency

If an object is cached for too long, users may receive stale content.

Common cache-control concepts include:

- TTL (Time To Live)
- Cache invalidation
- Versioned assets
- Purge operations
- Revalidation
- Conditional requests

A useful production strategy is often to version immutable static assets,
such as:

    app.abc123.css

instead of repeatedly replacing:

    app.css

This reduces ambiguity about which version clients should receive.
"""
)


# ============================================================================
# 23. GLOBAL NETWORKING CONCEPTS
# ============================================================================

print_section("21. GLOBAL NETWORKING CONCEPTS")

print(
    """
Cloud global infrastructure depends heavily on networking.

Important concepts:

Internet
    Public global network connecting independent networks.

ISP
    Internet Service Provider that provides Internet connectivity.

Autonomous System (AS)
    A network or collection of networks under a common routing policy.

BGP
    Border Gateway Protocol, widely used to exchange routing information
    between autonomous systems.

Peering
    Direct exchange of traffic between networks.

Transit
    A network paying or being paid to carry traffic toward other networks.

Provider backbone
    A large private network connecting provider infrastructure.

Anycast
    Multiple geographically distributed locations advertise the same network
    address. Routing generally sends clients toward a suitable network
    location according to routing policy.

Unicast
    Traffic is directed toward one specific network destination.

DNS
    A distributed naming system mapping domain names to network endpoints.

CDN
    Content Delivery Network that distributes content closer to users.
"""
)


# ============================================================================
# 24. ANYCAST CONCEPT SIMULATION
# ============================================================================

@dataclass(frozen=True)
class AnycastNode:
    """A node advertising the same logical service address."""

    name: str
    city: str
    latitude: float
    longitude: float


anycast_nodes = [
    AnycastNode("node-us", "New York", 40.7, -74.0),
    AnycastNode("node-eu", "London", 51.5, -0.1),
    AnycastNode("node-in", "Mumbai", 19.1, 72.9),
]


def select_anycast_node(
    user: User,
    nodes: Sequence[AnycastNode],
) -> AnycastNode:
    """
    Simplified anycast selection based on geographic distance.

    Real Internet routing uses routing information and policies rather than
    simply choosing the geographically closest node.
    """
    return min(
        nodes,
        key=lambda node: approximate_distance_km(
            user.latitude,
            user.longitude,
            node.latitude,
            node.longitude,
        ),
    )


print_section("22. ANYCAST SIMULATION")

for user in users:
    node = select_anycast_node(user, anycast_nodes)
    print(f"{user.city:10} -> {node.city}")


# ============================================================================
# 25. DNS-BASED GLOBAL ROUTING
# ============================================================================

class RoutingPolicy(Enum):
    LATENCY = "Latency-based"
    GEOLOCATION = "Geolocation-based"
    WEIGHTED = "Weighted"
    FAILOVER = "Failover"
    HEALTH_BASED = "Health-based"


@dataclass
class Endpoint:
    """Represents a service endpoint."""

    name: str
    region: str
    healthy: bool
    weight: int = 1


def weighted_endpoint_selection(
    endpoints: Sequence[Endpoint],
) -> Optional[Endpoint]:
    """
    Deterministically select the highest-weight healthy endpoint.

    Real traffic routing uses dynamic algorithms and many more factors.
    """
    healthy = [
        endpoint
        for endpoint in endpoints
        if endpoint.healthy and endpoint.weight > 0
    ]

    if not healthy:
        return None

    return max(healthy, key=lambda endpoint: endpoint.weight)


print_section("23. GLOBAL TRAFFIC-ROUTING POLICIES")

for policy in RoutingPolicy:
    print(f"- {policy.value}")

endpoints = [
    Endpoint("endpoint-us", "us-east", True, 50),
    Endpoint("endpoint-eu", "eu-west", True, 30),
    Endpoint("endpoint-in", "ap-south", True, 20),
]

selected_endpoint = weighted_endpoint_selection(endpoints)

print(
    f"\nHighest-weight healthy endpoint: "
    f"{selected_endpoint.name if selected_endpoint else 'NONE'}"
)


# ============================================================================
# 26. DATABASE PLACEMENT AND CONSISTENCY
# ============================================================================

class ConsistencyModel(Enum):
    STRONG = "Strong consistency"
    EVENTUAL = "Eventual consistency"


@dataclass
class DatabaseArchitecture:
    """Conceptual database architecture."""

    primary_region: str
    replicas: List[str]
    consistency: ConsistencyModel


database_architectures = [
    DatabaseArchitecture(
        "ap-south",
        ["ap-south-secondary"],
        ConsistencyModel.STRONG,
    ),
    DatabaseArchitecture(
        "ap-south",
        ["eu-west", "us-east"],
        ConsistencyModel.EVENTUAL,
    ),
]

print_section("24. DATABASE GEOGRAPHY AND CONSISTENCY")

for architecture in database_architectures:
    print(
        f"Primary={architecture.primary_region:10} "
        f"replicas={architecture.replicas} "
        f"consistency={architecture.consistency.value}"
    )

print(
    """
Global applications frequently face a trade-off between:

    Low latency
    Strong consistency
    Availability
    Cross-region durability
    Operational simplicity

Cross-region writes can be affected by network latency.

Strong consistency may require coordination between locations.

Eventual consistency can permit geographically distributed writes or
replication but means that different clients may temporarily observe different
states.

The appropriate model depends on the application.
"""
)


# ============================================================================
# 27. STORAGE REPLICATION
# ============================================================================

@dataclass
class StorageReplica:
    """Represents a storage replica."""

    region: str
    synchronized: bool


def replicated_storage_is_healthy(
    replicas: Sequence[StorageReplica],
    required_replicas: int,
) -> bool:
    """Check whether enough synchronized replicas exist."""
    synchronized_count = sum(
        replica.synchronized for replica in replicas
    )
    return synchronized_count >= required_replicas


print_section("25. CROSS-REGION STORAGE REPLICATION")

storage_replicas = [
    StorageReplica("ap-south", True),
    StorageReplica("eu-west", True),
    StorageReplica("us-east", False),
]

print(
    "Enough synchronized replicas:",
    replicated_storage_is_healthy(storage_replicas, 2),
)


# ============================================================================
# 28. HYBRID CLOUD
# ============================================================================

@dataclass
class Environment:
    """Represents an infrastructure environment."""

    name: str
    location: str
    workloads: List[str]


hybrid_environments = [
    Environment(
        "on-premises",
        "Corporate data center",
        ["legacy ERP", "sensitive database"],
    ),
    Environment(
        "public-cloud",
        "Cloud region",
        ["web application", "analytics"],
    ),
    Environment(
        "edge",
        "Retail locations",
        ["local processing", "device gateway"],
    ),
]

print_section("26. HYBRID CLOUD AND EDGE")

for environment in hybrid_environments:
    print(
        f"{environment.name:15} "
        f"location={environment.location:25} "
        f"workloads={', '.join(environment.workloads)}"
    )

print(
    """
Hybrid architecture combines environments such as:

    On-premises
        |
        +---- Public cloud
        |
        +---- Edge infrastructure

Common reasons include:

- Existing systems
- Regulatory constraints
- Latency requirements
- Data sovereignty
- Hardware dependencies
- Migration strategies

Hybrid infrastructure introduces integration complexity and requires careful
networking, identity, monitoring, security, and operational ownership.
"""
)


# ============================================================================
# 29. MULTI-CLOUD
# ============================================================================

@dataclass
class MultiCloudWorkload:
    """Represents a workload distributed across providers."""

    workload_name: str
    providers: Tuple[str, ...]
    reason: str


multi_cloud_workloads = [
    MultiCloudWorkload(
        "Global web service",
        ("AWS", "Google Cloud"),
        "Resilience and provider diversification",
    ),
    MultiCloudWorkload(
        "Enterprise analytics",
        ("Azure", "AWS"),
        "Existing enterprise integrations and analytics requirements",
    ),
]

print_section("27. MULTI-CLOUD ARCHITECTURE")

for workload in multi_cloud_workloads:
    print(
        f"{workload.workload_name}: "
        f"{', '.join(workload.providers)}"
    )
    print(f"  Reason: {workload.reason}")

print(
    """
Multi-cloud can reduce dependence on a single provider, but it is not free
resilience.

Potential costs include:

- Multiple skill sets
- Different APIs
- Different identity systems
- Different networking models
- Different observability tools
- Data-transfer costs
- Different security controls
- Different service semantics

A multi-cloud architecture should have a specific business or technical
reason rather than being adopted merely as a slogan.
"""
)


# ============================================================================
# 30. VENDOR LOCK-IN
# ============================================================================

@dataclass
class LockInFactor:
    """Represents one potential source of provider dependency."""

    category: str
    dependency: str
    portability: str


lock_in_factors = [
    LockInFactor(
        "Compute",
        "Virtual machine images and provider-specific orchestration",
        "Medium",
    ),
    LockInFactor(
        "Database",
        "Provider-specific managed database features",
        "Low to Medium",
    ),
    LockInFactor(
        "Serverless",
        "Provider-specific function APIs and event systems",
        "Low",
    ),
    LockInFactor(
        "Storage",
        "Provider-specific object storage APIs",
        "Medium",
    ),
    LockInFactor(
        "Networking",
        "Provider-specific load balancing and private networking",
        "Low to Medium",
    ),
]

print_section("28. VENDOR LOCK-IN")

for factor in lock_in_factors:
    print(
        f"{factor.category:12} "
        f"portability={factor.portability:12} "
        f"{factor.dependency}"
    )

print(
    """
Vendor lock-in is not automatically bad.

Using a highly specialized managed service may produce:

- Better productivity
- Better reliability
- Lower operational burden
- Better integration

Portability has a cost.

A system should optimize for the organization's actual priorities rather than
attempting to eliminate every provider-specific feature.
"""
)


# ============================================================================
# 31. COST MODEL
# ============================================================================

@dataclass
class RegionalCost:
    """Simplified regional infrastructure cost."""

    region: str
    compute_cost: float
    storage_cost: float
    data_transfer_cost: float
    support_cost: float

    def total(self) -> float:
        """Return total modeled monthly cost."""
        return (
            self.compute_cost
            + self.storage_cost
            + self.data_transfer_cost
            + self.support_cost
        )


costs = [
    RegionalCost("us-east", 5000, 1200, 800, 500),
    RegionalCost("eu-west", 5300, 1250, 950, 500),
    RegionalCost("ap-south", 4700, 1100, 900, 500),
]

print_section("29. REGIONAL COST MODEL")

for cost in costs:
    print(
        f"{cost.region:12} "
        f"total=${cost.total():,.2f}/month"
    )

print(
    """
Cloud cost is not just the price of virtual machines.

Important cost categories can include:

- Compute
- Block storage
- Object storage
- Database
- Network egress
- Inter-region transfer
- Load balancing
- CDN
- Logging
- Monitoring
- Backups
- Managed services
- Support
- Reserved or committed capacity

A geographically distributed architecture can improve availability and
latency while increasing replication and networking costs.
"""
)


# ============================================================================
# 32. SECURITY BOUNDARIES
# ============================================================================

@dataclass
class SecurityBoundary:
    """Represents a conceptual security boundary."""

    name: str
    controls: Tuple[str, ...]


security_boundaries = [
    SecurityBoundary(
        "Edge",
        (
            "DDoS protection",
            "TLS",
            "WAF",
            "Rate limiting",
        ),
    ),
    SecurityBoundary(
        "Network",
        (
            "Private subnets",
            "Security groups",
            "Network ACLs",
            "Routing controls",
        ),
    ),
    SecurityBoundary(
        "Application",
        (
            "Authentication",
            "Authorization",
            "Input validation",
            "Secrets management",
        ),
    ),
    SecurityBoundary(
        "Data",
        (
            "Encryption at rest",
            "Encryption in transit",
            "Access control",
            "Backup protection",
        ),
    ),
]

print_section("30. GLOBAL INFRASTRUCTURE SECURITY")

for boundary in security_boundaries:
    print(f"\n{boundary.name}")
    for control in boundary.controls:
        print(f"  - {control}")

print(
    """
Security must be considered across the entire path:

    User
      |
    Edge
      |
    Network
      |
    Load Balancer
      |
    Application
      |
    Database
      |
    Backup / Replication

Geographic distribution does not eliminate security responsibility.

A multi-region system can actually increase the number of security
configurations that must be managed.
"""
)


# ============================================================================
# 33. ZERO TRUST PRINCIPLES
# ============================================================================

print_section("31. ZERO-TRUST PRINCIPLES")

print(
    """
A zero-trust approach does not treat a network location as sufficient proof
of trust.

Core principles include:

- Authenticate requests
- Authorize explicitly
- Apply least privilege
- Continuously evaluate relevant signals
- Segment workloads
- Protect service-to-service communication
- Log security-sensitive activity

Example:

    Service A -> Service B

should not be trusted merely because both services are inside the same cloud
network.

Identity, authorization, encryption, and policy should still be considered.
"""
)


# ============================================================================
# 34. OBSERVABILITY
# ============================================================================

@dataclass
class MetricSample:
    """A simple monitoring metric."""

    region: str
    latency_ms: float
    error_rate: float
    cpu_percent: float


samples = [
    MetricSample("us-east", 45, 0.01, 60),
    MetricSample("eu-west", 70, 0.02, 55),
    MetricSample("ap-south", 40, 0.01, 65),
    MetricSample("us-east", 50, 0.03, 75),
    MetricSample("eu-west", 75, 0.01, 58),
    MetricSample("ap-south", 42, 0.02, 70),
]


def average_metric(
    samples: Sequence[MetricSample],
    region: str,
    metric: str,
) -> float:
    """Calculate an average metric for one region."""
    regional_samples = [
        sample
        for sample in samples
        if sample.region == region
    ]

    if not regional_samples:
        raise ValueError(f"No samples for region: {region}")

    values = [getattr(sample, metric) for sample in regional_samples]
    return mean(values)


print_section("32. GLOBAL OBSERVABILITY")

for region_name in ["us-east", "eu-west", "ap-south"]:
    print(
        f"{region_name:12} "
        f"latency={average_metric(samples, region_name, 'latency_ms'):.1f} ms "
        f"error_rate={average_metric(samples, region_name, 'error_rate'):.3f} "
        f"cpu={average_metric(samples, region_name, 'cpu_percent'):.1f}%"
    )

print(
    """
Global systems require regional visibility.

Useful signals include:

Metrics
    Numerical measurements such as latency and CPU.

Logs
    Detailed event records.

Traces
    Request paths across distributed services.

Health checks
    Tests used to determine whether an endpoint can receive traffic.

SLO
    Service Level Objective defining a target level of service.

Error budget
    The amount of unreliability allowed by an SLO.

A global architecture should monitor both individual components and the
complete user-facing request path.
"""
)


# ============================================================================
# 35. LATENCY PERCENTILES
# ============================================================================

def percentile(values: Sequence[float], percentage: float) -> float:
    """
    Calculate a simple nearest-rank percentile.

    This educational implementation is intentionally simple.
    """
    if not values:
        raise ValueError("At least one value is required.")

    if not 0 <= percentage <= 100:
        raise ValueError("Percentage must be between 0 and 100.")

    ordered = sorted(values)
    index = ceil((percentage / 100.0) * len(ordered)) - 1
    index = max(0, min(index, len(ordered) - 1))
    return ordered[index]


print_section("33. LATENCY PERCENTILES")

latencies = [25, 27, 28, 30, 31, 35, 40, 42, 60, 120]

for percentage in [50, 90, 95, 99]:
    print(
        f"p{percentage}: "
        f"{percentile(latencies, percentage):.0f} ms"
    )

print(
    """
Average latency can hide poor user experiences.

For example, a small number of very slow requests may barely change the mean
but can significantly affect p95 or p99 latency.

Distributed systems commonly examine:

- Mean
- Median / p50
- p90
- p95
- p99
- Error rate
- Availability
"""
)


# ============================================================================
# 36. HEALTH CHECKS AND ROUTING
# ============================================================================

@dataclass
class HealthCheck:
    """Represents a health-check result."""

    endpoint: str
    latency_ms: float
    status_code: int

    @property
    def healthy(self) -> bool:
        """Return whether the endpoint passes the simplified health check."""
        return self.status_code == 200 and self.latency_ms < 500


health_checks = [
    HealthCheck("us-east", 80, 200),
    HealthCheck("eu-west", 120, 200),
    HealthCheck("ap-south", 700, 200),
]

print_section("34. HEALTH CHECKS")

for check in health_checks:
    print(
        f"{check.endpoint:12} "
        f"latency={check.latency_ms:4} ms "
        f"status={check.status_code} "
        f"healthy={check.healthy}"
    )


# ============================================================================
# 37. COMMON ARCHITECTURAL MISTAKES
# ============================================================================

print_section("35. COMMON ARCHITECTURAL MISTAKES")

mistakes = [
    (
        "Running every critical component in one AZ",
        "A zone-level failure can remove the entire workload.",
    ),
    (
        "Choosing a region only by price",
        "Latency, compliance, capacity, and service availability may matter more.",
    ),
    (
        "Assuming another region automatically provides DR",
        "Applications, data, identity, networking, and operations must also fail over.",
    ),
    (
        "Ignoring cross-region data-transfer cost",
        "Replication and traffic can create substantial network charges.",
    ),
    (
        "Assuming geographic distance equals network latency",
        "Internet routing and provider network paths affect latency.",
    ),
    (
        "Using active-active without considering data consistency",
        "Distributed writes can create conflict and consistency challenges.",
    ),
    (
        "Failing to test disaster recovery",
        "A theoretical recovery plan may fail when actually needed.",
    ),
    (
        "Treating edge locations as complete application regions",
        "Edge infrastructure usually serves specialized edge functions.",
    ),
    (
        "Duplicating infrastructure without duplicating security",
        "Every deployment location must have appropriate controls.",
    ),
    (
        "Assuming cloud provider capacity is infinite",
        "Quotas, service limits, regional capacity, and resource constraints exist.",
    ),
]

for mistake, consequence in mistakes:
    print(f"\nMistake: {mistake}")
    print(f"Consequence: {consequence}")


# ============================================================================
# 38. EDGE CASES
# ============================================================================

print_section("36. EDGE CASES AND EXCEPTIONS")

print(
    """
Important edge cases include:

1. A region may have multiple zones, but a particular managed service may not
   support every zone equally.

2. A service can be global in its control plane while still having
   region-specific data planes.

3. A provider may use different infrastructure terminology for different
   services.

4. A workload can be geographically close to a region but still experience
   high latency because of routing or congestion.

5. A healthy region may not have enough spare capacity to absorb another
   region's workload.

6. A database replica may exist in another region without being immediately
   usable as a writable primary.

7. Edge caching can reduce origin traffic but may return stale content.

8. Multi-region replication can improve durability but increase cost and
   consistency complexity.

9. A multi-cloud architecture can improve diversification while increasing
   operational complexity.

10. Disaster recovery objectives may conflict with cost constraints.

11. Compliance may restrict where replicas, backups, logs, or encryption keys
    can be stored.

12. Provider service availability differs by region and changes over time.

13. A cloud region outage is only one failure mode. Software bugs, credential
    compromise, bad deployments, DNS errors, and application-level failures
    can affect multiple regions simultaneously.
"""
)


# ============================================================================
# 39. BLAST RADIUS
# ============================================================================

@dataclass
class DeploymentUnit:
    """Represents a deployment boundary."""

    name: str
    region: str
    zone: str
    application_version: str


deployments = [
    DeploymentUnit("app-a", "ap-south", "ap-south-a", "v10"),
    DeploymentUnit("app-b", "ap-south", "ap-south-b", "v10"),
    DeploymentUnit("app-c", "ap-south", "ap-south-c", "v9"),
    DeploymentUnit("app-d", "eu-west", "eu-west-a", "v9"),
]


def deployment_blast_radius(
    deployments: Sequence[DeploymentUnit],
    version: str,
) -> List[str]:
    """Find deployment units exposed to a specified version."""
    return [
        deployment.name
        for deployment in deployments
        if deployment.application_version == version
    ]


print_section("37. BLAST RADIUS")

print(
    "Units running v10:",
    deployment_blast_radius(deployments, "v10"),
)

print(
    """
A global architecture should control blast radius.

Techniques include:

- Multiple availability zones
- Multiple regions
- Staged deployments
- Canary releases
- Blue-green deployments
- Automated rollback
- Independent configuration
- Segmented access
- Separate failure domains

Geographic redundancy is only one form of blast-radius reduction.
"""
)


# ============================================================================
# 40. CANARY DEPLOYMENT SIMULATION
# ============================================================================

@dataclass
class DeploymentTraffic:
    """Traffic allocation for a deployment version."""

    version: str
    percentage: float


def validate_traffic_split(
    allocations: Sequence[DeploymentTraffic],
) -> bool:
    """Verify that traffic percentages add up to approximately 100%."""
    total = sum(item.percentage for item in allocations)

    return abs(total - 100.0) < 1e-9 and all(
        0 <= item.percentage <= 100
        for item in allocations
    )


canary = [
    DeploymentTraffic("v9", 95),
    DeploymentTraffic("v10", 5),
]

print_section("38. CANARY DEPLOYMENT")

print("Valid traffic split:", validate_traffic_split(canary))

for allocation in canary:
    print(
        f"{allocation.version}: "
        f"{allocation.percentage:.1f}%"
    )


# ============================================================================
# 41. RESILIENCE SCORECARD
# ============================================================================

@dataclass
class ResilienceScore:
    """A simple resilience checklist."""

    multi_az: bool
    multi_region: bool
    tested_failover: bool
    replicated_data: bool
    monitoring: bool
    automated_recovery: bool

    def score(self) -> int:
        """Return the number of satisfied resilience controls."""
        return sum(
            [
                self.multi_az,
                self.multi_region,
                self.tested_failover,
                self.replicated_data,
                self.monitoring,
                self.automated_recovery,
            ]
        )


scorecard = ResilienceScore(
    multi_az=True,
    multi_region=True,
    tested_failover=True,
    replicated_data=True,
    monitoring=True,
    automated_recovery=False,
)

print_section("39. RESILIENCE SCORECARD")

print(f"Resilience controls satisfied: {scorecard.score()}/6")

print(
    """
A checklist like this is not a formal reliability calculation. It is a
design-review aid.

Production architecture should evaluate actual failure modes and dependencies
rather than assigning a simplistic score.
"""
)


# ============================================================================
# 42. TESTING FAILURE SCENARIOS
# ============================================================================

@dataclass
class FailureScenario:
    """A failure scenario for resilience testing."""

    name: str
    expected_behavior: str


failure_scenarios = [
    FailureScenario(
        "Single application instance failure",
        "Traffic moves to healthy instances.",
    ),
    FailureScenario(
        "Availability zone failure",
        "Traffic continues through other zones.",
    ),
    FailureScenario(
        "Database primary failure",
        "A healthy replica or recovery mechanism becomes available.",
    ),
    FailureScenario(
        "Regional outage",
        "Traffic moves to another region if architecture supports it.",
    ),
    FailureScenario(
        "Network partition",
        "System follows its designed consistency and availability behavior.",
    ),
    FailureScenario(
        "Bad deployment",
        "Automated rollback or controlled recovery limits blast radius.",
    ),
    FailureScenario(
        "Credential compromise",
        "Access can be revoked and suspicious activity detected.",
    ),
]

print_section("40. FAILURE-TESTING SCENARIOS")

for scenario in failure_scenarios:
    print(f"\nScenario: {scenario.name}")
    print(f"Expected: {scenario.expected_behavior}")


# ============================================================================
# 43. INFRASTRUCTURE AS CODE
# ============================================================================

print_section("41. INFRASTRUCTURE AS CODE")

print(
    """
Infrastructure as Code (IaC) represents infrastructure configuration as
version-controlled definitions.

Conceptually:

    Source control
          |
          v
    Infrastructure definition
          |
          v
    Validation
          |
          v
    Deployment
          |
          v
    Cloud resources

Benefits include:

- Repeatability
- Version history
- Reviewability
- Automated deployment
- Consistent environments
- Easier regional replication

Important production practices include:

- Review infrastructure changes
- Protect secrets
- Validate plans
- Separate environments
- Use least privilege
- Control state
- Test destructive changes
- Make deployments observable
"""
)


# ============================================================================
# 44. IMMUTABLE INFRASTRUCTURE
# ============================================================================

print_section("42. IMMUTABLE INFRASTRUCTURE")

print(
    """
Immutable infrastructure treats deployed infrastructure as replaceable
artifacts rather than repeatedly modifying live machines.

Conceptual workflow:

    Build image
       |
       v
    Test image
       |
       v
    Deploy new instances
       |
       v
    Shift traffic
       |
       v
    Remove old instances

Advantages:

- Predictable deployments
- Easier rollback
- Reduced configuration drift

Trade-off:

- More automation is required
- State must be externalized appropriately
"""
)


# ============================================================================
# 45. CONFIGURATION DRIFT
# ============================================================================

@dataclass
class Configuration:
    """Simplified infrastructure configuration."""

    desired_version: str
    actual_version: str

    @property
    def drifted(self) -> bool:
        """Return True when actual state differs from desired state."""
        return self.desired_version != self.actual_version


print_section("43. CONFIGURATION DRIFT")

configuration = Configuration(
    desired_version="v12",
    actual_version="v11",
)

print("Configuration drift detected:", configuration.drifted)


# ============================================================================
# 46. SERVICE DEPENDENCY GRAPH
# ============================================================================

@dataclass
class DependencyGraph:
    """Simple directed dependency graph."""

    edges: Dict[str, List[str]]

    def dependencies_of(self, service: str) -> List[str]:
        """Return direct dependencies."""
        return self.edges.get(service, [])


dependency_graph = DependencyGraph(
    edges={
        "frontend": ["api"],
        "api": ["database", "cache", "identity"],
        "worker": ["queue", "database"],
        "analytics": ["object-storage"],
    }
)

print_section("44. GLOBAL SERVICE DEPENDENCIES")

for service, dependencies in dependency_graph.edges.items():
    print(f"{service:15} -> {', '.join(dependencies)}")

print(
    """
A common resilience mistake is replicating the application but leaving a
critical dependency single-region.

For example:

    Region A application
    Region B application

but:

    Region A + Region B
            |
            v
    One regional database

The application is multi-region, but the dependency remains a single point
of failure.

Resilience analysis should follow the dependency graph.
"""
)


# ============================================================================
# 47. SINGLE POINT OF FAILURE DETECTION
# ============================================================================

def find_single_region_dependencies(
    dependency_locations: Dict[str, Sequence[str]],
) -> List[str]:
    """
    Identify dependencies present in only one region.

    This is a simplified architecture-review heuristic.
    """
    return [
        dependency
        for dependency, regions in dependency_locations.items()
        if len(set(regions)) == 1
    ]


dependency_locations = {
    "database": ["ap-south"],
    "cache": ["ap-south", "eu-west"],
    "identity": ["ap-south", "eu-west"],
    "queue": ["ap-south"],
    "object-storage": ["ap-south", "eu-west"],
}

print_section("45. SINGLE-REGION DEPENDENCY CHECK")

single_region_dependencies = find_single_region_dependencies(
    dependency_locations
)

for dependency in single_region_dependencies:
    print(f"Potential single-region dependency: {dependency}")


# ============================================================================
# 48. PRODUCTION DESIGN CHECKLIST
# ============================================================================

print_section("46. PRODUCTION GLOBAL-INFRASTRUCTURE CHECKLIST")

checklist = [
    "Define user geography and latency requirements.",
    "Select regions based on latency, compliance, services, cost, and resilience.",
    "Distribute critical workloads across appropriate failure domains.",
    "Identify regional and zone-level single points of failure.",
    "Design database replication and consistency behavior explicitly.",
    "Define RTO and RPO.",
    "Define traffic-routing and failover behavior.",
    "Plan spare capacity for failure scenarios.",
    "Account for inter-region and Internet data-transfer costs.",
    "Protect every regional deployment with appropriate security controls.",
    "Centralize or federate observability appropriately.",
    "Test regional and zone-level failure scenarios.",
    "Automate repeatable infrastructure deployment.",
    "Control configuration drift.",
    "Document ownership and recovery procedures.",
    "Review provider-specific service and regional limitations.",
]

for index, item in enumerate(checklist, start=1):
    print(f"{index:2}. {item}")


# ============================================================================
# 49. VALIDATION AND ERROR-HANDLING EXAMPLES
# ============================================================================

print_section("47. VALIDATION AND EDGE-CASE TESTS")

test_cases = [
    ("negative request rate", -1, 100, 0.30),
    ("zero per-unit capacity", 1000, 0, 0.30),
    ("negative headroom", 1000, 100, -0.10),
    ("normal input", 1000, 100, 0.30),
]

for name, requests, per_unit, headroom in test_cases:
    try:
        result = required_capacity(requests, per_unit, headroom)
        print(f"{name:25} -> {result} capacity units")
    except ValueError as error:
        print(f"{name:25} -> rejected: {error}")


# ============================================================================
# 50. UNIT TESTS
# ============================================================================

def run_assertion_tests() -> None:
    """Run small executable tests for important functions."""

    assert approximate_distance_km(
        0,
        0,
        0,
        0,
    ) == 0.0

    assert estimated_latency_ms(0) == 8.0

    assert required_capacity(1000, 100, 0.30) == 13

    assert parallel_availability([0.99, 0.99]) > 0.99

    assert series_availability([0.99, 0.99]) < 0.99

    cache = Cache()
    origin = {"a": "value"}

    value, source = fetch_content(cache, "a", origin)
    assert value == "value"
    assert source == "ORIGIN"

    value, source = fetch_content(cache, "a", origin)
    assert value == "value"
    assert source == "CACHE_HIT"

    assert validate_traffic_split(
        [
            DeploymentTraffic("old", 90),
            DeploymentTraffic("new", 10),
        ]
    )

    assert not validate_traffic_split(
        [
            DeploymentTraffic("old", 80),
            DeploymentTraffic("new", 10),
        ]
    )


print_section("48. EXECUTABLE VALIDATION")

run_assertion_tests()
print("All assertion tests passed.")


# ============================================================================
# 51. COMPLETE ARCHITECTURE SIMULATION
# ============================================================================

@dataclass
class GlobalApplication:
    """A simplified end-to-end global application."""

    name: str
    regions: List[RegionalService]
    edges: List[EdgeLocation]

    def route_user(self, user: User) -> str:
        """
        Route a user through the nearest edge and then to a healthy region.

        This models the conceptual architecture:

            User -> Edge -> Healthy Region
        """
        edge_result = nearest_edge(user, self.edges)

        healthy_services = [
            service
            for service in self.regions
            if service.healthy
        ]

        selected = choose_healthy_region(
            user,
            healthy_services,
            provider.regions,
        )

        if edge_result is None:
            edge_name = "no-edge"
        else:
            edge_name = edge_result[0].city

        region_name = selected.region_name if selected else "NO-REGION"

        return f"{user.city} -> edge:{edge_name} -> region:{region_name}"


global_application = GlobalApplication(
    name="GlobalStore",
    regions=[
        RegionalService("us-east", True, 300),
        RegionalService("eu-west", True, 250),
        RegionalService("ap-south", True, 200),
    ],
    edges=provider.edge_locations,
)

print_section("49. END-TO-END GLOBAL APPLICATION SIMULATION")

for user in users:
    print(global_application.route_user(user))


# ============================================================================
# 52. FAILURE SIMULATION OF COMPLETE ARCHITECTURE
# ============================================================================

print_section("50. END-TO-END REGION FAILURE")

global_application.regions[0].healthy = False

for user in users:
    print(global_application.route_user(user))

print(
    """
The simulation demonstrates the layered nature of global cloud
infrastructure:

    Geographic user
          |
          v
    Edge / PoP
          |
          v
    Global routing
          |
          v
    Cloud region
          |
          v
    Availability zone
          |
          v
    Application
          |
          v
    Data services

Each layer has different responsibilities and different failure modes.
"""
)


# ============================================================================
# 53. ARCHITECTURAL COMPARISON
# ============================================================================

@dataclass(frozen=True)
class Architecture:
    """Represents a conceptual architecture pattern."""

    name: str
    availability: str
    latency: str
    complexity: str
    cost: str
    consistency: str


architectures = [
    Architecture(
        "Single-region single-AZ",
        "Low",
        "Good for nearby users",
        "Low",
        "Low",
        "Simple",
    ),
    Architecture(
        "Single-region multi-AZ",
        "High against AZ failure",
        "Good",
        "Medium",
        "Medium",
        "Simple to moderate",
    ),
    Architecture(
        "Multi-region active-passive",
        "High against regional failure",
        "Good",
        "High",
        "Medium to high",
        "Moderate",
    ),
    Architecture(
        "Multi-region active-active",
        "Very high when correctly designed",
        "Excellent",
        "Very high",
        "High",
        "Complex",
    ),
    Architecture(
        "Multi-cloud",
        "Potentially high",
        "Depends on topology",
        "Very high",
        "High",
        "Complex",
    ),
]

print_section("51. ARCHITECTURAL COMPARISON")

for architecture in architectures:
    print(
        f"\n{architecture.name}"
        f"\n  Availability: {architecture.availability}"
        f"\n  Latency:      {architecture.latency}"
        f"\n  Complexity:   {architecture.complexity}"
        f"\n  Cost:         {architecture.cost}"
        f"\n  Consistency:  {architecture.consistency}"
    )


# ============================================================================
# 54. DESIGN TRADE-OFF FUNCTION
# ============================================================================

def compare_architecture(
    availability: float,
    latency: float,
    simplicity: float,
    cost_efficiency: float,
    consistency: float,
    weights: Dict[str, float],
) -> float:
    """
    Produce a weighted architecture score.

    Scores are expected to be normalized between 0 and 100.
    """
    values = {
        "availability": availability,
        "latency": latency,
        "simplicity": simplicity,
        "cost": cost_efficiency,
        "consistency": consistency,
    }

    if any(not 0 <= value <= 100 for value in values.values()):
        raise ValueError("Architecture scores must be between 0 and 100.")

    return sum(
        values[name] * weight
        for name, weight in weights.items()
    )


print_section("52. ARCHITECTURE TRADE-OFF MODEL")

tradeoff_weights = {
    "availability": 0.30,
    "latency": 0.20,
    "simplicity": 0.15,
    "cost": 0.15,
    "consistency": 0.20,
}

active_active_score = compare_architecture(
    availability=95,
    latency=95,
    simplicity=45,
    cost_efficiency=40,
    consistency=65,
    weights=tradeoff_weights,
)

single_region_score = compare_architecture(
    availability=75,
    latency=80,
    simplicity=90,
    cost_efficiency=90,
    consistency=95,
    weights=tradeoff_weights,
)

print(f"Active-active score:  {active_active_score:.2f}")
print(f"Single-region score: {single_region_score:.2f}")

print(
    """
A weighted score is useful for making assumptions explicit, but it does not
replace engineering judgment.

Different organizations can legitimately choose different architectures
because their priorities differ.
"""
)


# ============================================================================
# 55. FINAL CONCEPT MAP
# ============================================================================

print_section("53. CONCEPT MAP")

print(
    """
CLOUD PROVIDERS
|
+-- Global Infrastructure
|   |
|   +-- Regions
|   |   |
|   |   +-- Availability Zones
|   |       |
|   |       +-- Data centers / fault domains
|   |
|   +-- Edge Locations
|   |
|   +-- Points of Presence
|   |
|   +-- Provider Backbone
|
+-- Networking
|   |
|   +-- DNS
|   +-- BGP
|   +-- Anycast
|   +-- Peering
|   +-- Transit
|   +-- CDN
|
+-- Resilience
|   |
|   +-- Redundancy
|   +-- High Availability
|   +-- Multi-AZ
|   +-- Multi-Region
|   +-- Disaster Recovery
|   +-- RTO / RPO
|
+-- Data
|   |
|   +-- Replication
|   +-- Consistency
|   +-- Residency
|   +-- Durability
|
+-- Operations
|   |
|   +-- Capacity
|   +-- Monitoring
|   +-- Logging
|   +-- Tracing
|   +-- Infrastructure as Code
|   +-- Failure Testing
|
+-- Business Constraints
    |
    +-- Cost
    +-- Compliance
    +-- Latency
    +-- Availability
    +-- Security
    +-- Vendor Dependence
"""
)


# ============================================================================
# 56. FINAL STUDY QUESTIONS AS EXECUTABLE DATA
# ============================================================================

study_questions = [
    "Why is a region different from an availability zone?",
    "Why does multi-AZ deployment improve availability?",
    "Why does multi-region deployment introduce data-consistency challenges?",
    "What role does an edge location play?",
    "Why is geographic distance not identical to network latency?",
    "What is a point of presence?",
    "How do RTO and RPO differ?",
    "What happens when a region fails?",
    "How much spare capacity is required after regional failure?",
    "Why can multi-cloud increase operational complexity?",
    "How can data residency affect region selection?",
    "Why do CDN caches improve latency?",
    "What are the risks of stale cached data?",
    "Why should disaster recovery be tested?",
    "What dependencies can remain single points of failure?",
]

print_section("54. STUDY QUESTIONS")

for number, question in enumerate(study_questions, start=1):
    print(f"{number:2}. {question}")


# ============================================================================
# 57. SCRIPT COMPLETION
# ============================================================================

print_section("55. SCRIPT COMPLETED")

print(
    """
This executable study file has demonstrated the core architecture of global
cloud infrastructure through data models, calculations, simulations,
validation, routing examples, failure scenarios, and architectural
comparisons.

The central relationship to remember is:

    Provider
       |
       +-- Region
       |     |
       |     +-- Availability Zones
       |             |
       |             +-- Compute / Storage / Network resources
       |
       +-- Edge Locations / PoPs
       |
       +-- Global Network

A production architecture must connect these physical and logical concepts
with application requirements for latency, availability, resilience,
security, compliance, cost, data consistency, and operational control.
"""
)
