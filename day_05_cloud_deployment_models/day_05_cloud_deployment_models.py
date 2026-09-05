"""
Cloud Deployment Models: A Comprehensive Python Study Script
==============================================================

This standalone script teaches cloud deployment models from beginner through
advanced level, with executable Python demonstrations.

Topics covered:
- Cloud computing fundamentals
- Public, private, hybrid, multi-cloud, and community cloud
- Shared responsibility
- AWS, Microsoft Azure, and Google Cloud concepts
- IaaS, PaaS, SaaS distinctions
- Deployment-model decision criteria
- Cost, scalability, control, security, compliance, and portability
- Hybrid-cloud architecture
- Multi-cloud architecture
- Cloud bursting
- Disaster recovery
- Data residency
- Vendor lock-in
- Availability and resilience
- Cloud-provider abstraction
- Workload classification
- Architecture scoring
- Validation and edge cases
- Practical cloud deployment selection
- Testing and production considerations

The examples intentionally use standard-library Python only.
They model architectural decisions rather than connecting to real cloud accounts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


# ============================================================================
# 1. CLOUD COMPUTING FUNDAMENTALS
# ============================================================================

print("=" * 78)
print("CLOUD DEPLOYMENT MODELS")
print("=" * 78)


class CloudConcept:
    """
    A compact representation of a fundamental cloud-computing concept.

    Cloud computing generally means obtaining computing capabilities such as
    compute, storage, databases, networking, and software through a service
    model rather than owning and operating every physical component directly.
    """

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    def __str__(self) -> str:
        return f"{self.name}: {self.description}"


cloud_concepts = [
    CloudConcept(
        "On-demand self-service",
        "Resources can be provisioned when needed without manual infrastructure procurement.",
    ),
    CloudConcept(
        "Resource pooling",
        "Provider infrastructure serves multiple customers through logical isolation.",
    ),
    CloudConcept(
        "Elasticity",
        "Capacity can increase or decrease in response to workload requirements.",
    ),
    CloudConcept(
        "Measured service",
        "Usage can be monitored and commonly billed according to consumption.",
    ),
    CloudConcept(
        "Broad network access",
        "Services are accessible over networks using standard interfaces and protocols.",
    ),
]

for concept in cloud_concepts:
    print(concept)


# ============================================================================
# 2. DEPLOYMENT MODEL TERMINOLOGY
# ============================================================================

class DeploymentModel(Enum):
    """
    Major cloud deployment models.

    The labels describe how infrastructure is owned, operated, isolated, and
    shared. A real architecture can combine more than one model.
    """

    PUBLIC = "Public Cloud"
    PRIVATE = "Private Cloud"
    HYBRID = "Hybrid Cloud"
    MULTI_CLOUD = "Multi-Cloud"
    COMMUNITY = "Community Cloud"


class ServiceModel(Enum):
    """
    Service models describe what layer the customer consumes.

    Deployment model answers:
        "Where and how is cloud infrastructure organized?"

    Service model answers:
        "How much infrastructure does the provider manage for me?"
    """

    IAAS = "IaaS"
    PAAS = "PaaS"
    SAAS = "SaaS"


print("\nDeployment models:")
for model in DeploymentModel:
    print(f"- {model.value}")

print("\nService models:")
for model in ServiceModel:
    print(f"- {model.value}")


# ============================================================================
# 3. DEPLOYMENT MODEL DEFINITIONS
# ============================================================================

deployment_definitions: Dict[DeploymentModel, str] = {
    DeploymentModel.PUBLIC: (
        "Cloud infrastructure operated by a provider and offered to multiple "
        "customers through logically isolated environments."
    ),
    DeploymentModel.PRIVATE: (
        "Cloud infrastructure dedicated to one organization, operated internally "
        "or by a third party."
    ),
    DeploymentModel.HYBRID: (
        "An integrated architecture combining private infrastructure with one "
        "or more public-cloud environments."
    ),
    DeploymentModel.MULTI_CLOUD: (
        "Use of cloud services from two or more independent cloud providers."
    ),
    DeploymentModel.COMMUNITY: (
        "Cloud infrastructure shared by organizations with common requirements, "
        "such as regulatory, security, or mission-specific constraints."
    ),
}

print("\nDeployment model definitions:")
for model, definition in deployment_definitions.items():
    print(f"\n{model.value}\n  {definition}")


# ============================================================================
# 4. PUBLIC CLOUD
# ============================================================================

@dataclass
class PublicCloudExample:
    provider: str
    compute: str
    storage: str
    database: str

    def describe(self) -> str:
        return (
            f"{self.provider}: compute={self.compute}, "
            f"storage={self.storage}, database={self.database}"
        )


public_cloud_examples = [
    PublicCloudExample(
        "AWS",
        "Amazon EC2",
        "Amazon S3",
        "Amazon RDS",
    ),
    PublicCloudExample(
        "Microsoft Azure",
        "Azure Virtual Machines",
        "Azure Blob Storage",
        "Azure SQL Database",
    ),
    PublicCloudExample(
        "Google Cloud",
        "Compute Engine",
        "Cloud Storage",
        "Cloud SQL",
    ),
]

print("\nRepresentative public-cloud services:")
for example in public_cloud_examples:
    print(example.describe())


# ============================================================================
# 5. PRIVATE CLOUD
# ============================================================================

@dataclass
class PrivateCloud:
    organization: str
    dedicated_hardware: bool
    virtualization: bool
    self_managed: bool

    def control_level(self) -> str:
        if self.dedicated_hardware and self.self_managed:
            return "High infrastructure control"
        if self.self_managed:
            return "High operational responsibility"
        return "Managed private-cloud environment"


private_cloud = PrivateCloud(
    organization="Example Financial Institution",
    dedicated_hardware=True,
    virtualization=True,
    self_managed=True,
)

print("\nPrivate-cloud example:")
print(private_cloud)
print(private_cloud.control_level())


# ============================================================================
# 6. HYBRID CLOUD
# ============================================================================

@dataclass
class Workload:
    name: str
    data_sensitivity: int
    compliance_requirement: int
    variable_demand: int
    latency_requirement: int
    portability_requirement: int

    def validate(self) -> None:
        """
        Validate scores before using them in architecture calculations.

        Scores are intentionally normalized to 1..10.
        """
        fields = {
            "data_sensitivity": self.data_sensitivity,
            "compliance_requirement": self.compliance_requirement,
            "variable_demand": self.variable_demand,
            "latency_requirement": self.latency_requirement,
            "portability_requirement": self.portability_requirement,
        }

        for name, value in fields.items():
            if not 1 <= value <= 10:
                raise ValueError(f"{name} must be between 1 and 10.")


hybrid_workloads = [
    Workload(
        name="Customer Analytics",
        data_sensitivity=7,
        compliance_requirement=6,
        variable_demand=9,
        latency_requirement=5,
        portability_requirement=8,
    ),
    Workload(
        name="Core Banking Database",
        data_sensitivity=10,
        compliance_requirement=10,
        variable_demand=4,
        latency_requirement=9,
        portability_requirement=3,
    ),
]

print("\nHybrid-cloud workload examples:")
for workload in hybrid_workloads:
    workload.validate()
    print(
        f"- {workload.name}: sensitivity={workload.data_sensitivity}, "
        f"compliance={workload.compliance_requirement}, "
        f"variable demand={workload.variable_demand}"
    )


# ============================================================================
# 7. HYBRID CLOUD ARCHITECTURE PATTERN
# ============================================================================

@dataclass
class HybridArchitecture:
    private_components: List[str]
    public_components: List[str]
    integration_components: List[str]

    def validate(self) -> None:
        """
        A meaningful hybrid architecture needs both sides plus a mechanism
        for controlled integration.
        """
        if not self.private_components:
            raise ValueError("Hybrid architecture needs a private side.")
        if not self.public_components:
            raise ValueError("Hybrid architecture needs a public-cloud side.")
        if not self.integration_components:
            raise ValueError(
                "Hybrid architecture needs integration or connectivity components."
            )

    def describe(self) -> None:
        self.validate()
        print("\nHybrid architecture")
        print("Private:")
        for item in self.private_components:
            print(f"  - {item}")
        print("Public:")
        for item in self.public_components:
            print(f"  - {item}")
        print("Integration:")
        for item in self.integration_components:
            print(f"  - {item}")


hybrid_architecture = HybridArchitecture(
    private_components=[
        "Sensitive customer database",
        "Legacy internal application",
    ],
    public_components=[
        "Web application",
        "Autoscaling API",
        "Object storage",
    ],
    integration_components=[
        "Private network connectivity",
        "Identity federation",
        "Encrypted data transfer",
        "API gateway",
    ],
)

hybrid_architecture.describe()


# ============================================================================
# 8. MULTI-CLOUD
# ============================================================================

@dataclass
class MultiCloudArchitecture:
    providers: Set[str]
    primary_provider: str
    secondary_provider: Optional[str] = None

    def validate(self) -> None:
        if len(self.providers) < 2:
            raise ValueError("A multi-cloud architecture needs at least two providers.")

        if self.primary_provider not in self.providers:
            raise ValueError("Primary provider must be in providers.")

        if self.secondary_provider is not None:
            if self.secondary_provider not in self.providers:
                raise ValueError("Secondary provider must be in providers.")
            if self.secondary_provider == self.primary_provider:
                raise ValueError(
                    "Primary and secondary providers must be different."
                )


multi_cloud = MultiCloudArchitecture(
    providers={"AWS", "Microsoft Azure"},
    primary_provider="AWS",
    secondary_provider="Microsoft Azure",
)

multi_cloud.validate()

print("\nMulti-cloud architecture:")
print(f"Providers: {sorted(multi_cloud.providers)}")
print(f"Primary: {multi_cloud.primary_provider}")
print(f"Secondary: {multi_cloud.secondary_provider}")


# ============================================================================
# 9. MULTI-CLOUD IS NOT THE SAME AS HYBRID CLOUD
# ============================================================================

def compare_hybrid_and_multicloud() -> None:
    """
    Important distinction:

    Hybrid:
        Usually means private/on-premises infrastructure plus public cloud,
        with some form of integration.

    Multi-cloud:
        Means multiple cloud providers.

    They can overlap. For example:
        On-premises + AWS + Azure
    can be both hybrid and multi-cloud.
    """

    comparison = {
        "Hybrid": "Private/on-premises + public cloud, integrated",
        "Multi-cloud": "Two or more cloud providers",
        "Both": "Possible when an organization uses private infrastructure plus multiple providers",
    }

    print("\nHybrid vs multi-cloud:")
    for key, value in comparison.items():
        print(f"{key}: {value}")


compare_hybrid_and_multicloud()


# ============================================================================
# 10. COMMUNITY CLOUD
# ============================================================================

@dataclass
class CommunityCloud:
    members: List[str]
    common_requirements: List[str]

    def validate(self) -> None:
        if len(self.members) < 2:
            raise ValueError("A community cloud should serve multiple organizations.")
        if not self.common_requirements:
            raise ValueError("Community cloud needs clearly shared requirements.")

    def describe(self) -> None:
        self.validate()
        print("\nCommunity-cloud example:")
        print("Member organizations:")
        for member in self.members:
            print(f"  - {member}")
        print("Shared requirements:")
        for requirement in self.common_requirements:
            print(f"  - {requirement}")


community_cloud = CommunityCloud(
    members=[
        "Regional healthcare organizations",
        "Public hospitals",
        "Healthcare research institutions",
    ],
    common_requirements=[
        "Regulatory compliance",
        "Strong access controls",
        "Auditability",
        "Data governance",
    ],
)

community_cloud.describe()


# ============================================================================
# 11. IAAS, PAAS, SAAS
# ============================================================================

@dataclass(frozen=True)
class ServiceResponsibility:
    layer: str
    customer_responsibility: str
    provider_responsibility: str


service_responsibilities = [
    ServiceResponsibility(
        "IaaS",
        "Operating systems, applications, configurations, data, and access controls",
        "Physical infrastructure, virtualization, and foundational networking/storage",
    ),
    ServiceResponsibility(
        "PaaS",
        "Application code, application configuration, and data",
        "Infrastructure, runtime, platform, and managed operational components",
    ),
    ServiceResponsibility(
        "SaaS",
        "Users, data, configuration, and access governance",
        "Application, platform, infrastructure, and most operational layers",
    ),
]

print("\nService-model responsibility comparison:")
for responsibility in service_responsibilities:
    print(f"\n{responsibility.layer}")
    print(f"  Customer: {responsibility.customer_responsibility}")
    print(f"  Provider: {responsibility.provider_responsibility}")


# ============================================================================
# 12. SHARED RESPONSIBILITY MODEL
# ============================================================================

class ResponsibilityLayer(Enum):
    PHYSICAL = "Physical facilities and hardware"
    NETWORK = "Networking infrastructure"
    HYPERVISOR = "Virtualization layer"
    OS = "Operating system"
    RUNTIME = "Application runtime"
    APPLICATION = "Application"
    DATA = "Data"
    IDENTITY = "Identity and access"


def responsibility_matrix(service_model: ServiceModel) -> Dict[str, str]:
    """
    Simplified educational responsibility matrix.

    Exact responsibilities vary by provider and service. A managed database,
    for example, shifts substantially more operational work to the provider
    than a virtual machine.
    """
    if service_model == ServiceModel.IAAS:
        provider_layers = {
            ResponsibilityLayer.PHYSICAL.value,
            ResponsibilityLayer.NETWORK.value,
            ResponsibilityLayer.HYPERVISOR.value,
        }
    elif service_model == ServiceModel.PAAS:
        provider_layers = {
            ResponsibilityLayer.PHYSICAL.value,
            ResponsibilityLayer.NETWORK.value,
            ResponsibilityLayer.HYPERVISOR.value,
            ResponsibilityLayer.OS.value,
            ResponsibilityLayer.RUNTIME.value,
        }
    else:
        provider_layers = {
            ResponsibilityLayer.PHYSICAL.value,
            ResponsibilityLayer.NETWORK.value,
            ResponsibilityLayer.HYPERVISOR.value,
            ResponsibilityLayer.OS.value,
            ResponsibilityLayer.RUNTIME.value,
            ResponsibilityLayer.APPLICATION.value,
        }

    result = {}

    for layer in ResponsibilityLayer:
        if layer.value in provider_layers:
            result[layer.value] = "Provider-managed"
        else:
            result[layer.value] = "Customer-managed"

    return result


print("\nSimplified shared-responsibility model:")
for service_model in ServiceModel:
    print(f"\n{service_model.value}")
    matrix = responsibility_matrix(service_model)
    for layer, owner in matrix.items():
        print(f"  {layer}: {owner}")


# ============================================================================
# 13. PUBLIC-CLOUD PROVIDER CONCEPTS
# ============================================================================

@dataclass(frozen=True)
class ProviderConcept:
    provider: str
    compute: str
    object_storage: str
    relational_database: str
    virtual_network: str
    identity_service: str


provider_concepts = [
    ProviderConcept(
        "AWS",
        "EC2",
        "S3",
        "RDS",
        "VPC",
        "IAM",
    ),
    ProviderConcept(
        "Microsoft Azure",
        "Virtual Machines",
        "Blob Storage",
        "Azure SQL Database",
        "Virtual Network",
        "Microsoft Entra ID",
    ),
    ProviderConcept(
        "Google Cloud",
        "Compute Engine",
        "Cloud Storage",
        "Cloud SQL",
        "VPC",
        "Cloud IAM",
    ),
]

print("\nRepresentative AWS, Azure, and Google Cloud concepts:")
for provider in provider_concepts:
    print(f"\n{provider.provider}")
    print(f"  Compute: {provider.compute}")
    print(f"  Object storage: {provider.object_storage}")
    print(f"  Relational DB: {provider.relational_database}")
    print(f"  Network: {provider.virtual_network}")
    print(f"  Identity: {provider.identity_service}")


# ============================================================================
# 14. ABSTRACT CLOUD SERVICE CATALOG
# ============================================================================

class CloudProvider:
    """
    Provider-neutral abstraction.

    The purpose is to demonstrate how architecture can reason in terms of
    capabilities instead of hard-coding provider-specific names everywhere.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.services: Dict[str, str] = {}

    def add_service(self, capability: str, service_name: str) -> None:
        self.services[capability] = service_name

    def service_for(self, capability: str) -> str:
        if capability not in self.services:
            raise KeyError(
                f"{self.name} does not have a mapped service for {capability!r}."
            )
        return self.services[capability]


aws = CloudProvider("AWS")
aws.add_service("compute", "EC2")
aws.add_service("object_storage", "S3")
aws.add_service("relational_database", "RDS")

azure = CloudProvider("Microsoft Azure")
azure.add_service("compute", "Virtual Machines")
azure.add_service("object_storage", "Blob Storage")
azure.add_service("relational_database", "Azure SQL Database")

google_cloud = CloudProvider("Google Cloud")
google_cloud.add_service("compute", "Compute Engine")
google_cloud.add_service("object_storage", "Cloud Storage")
google_cloud.add_service("relational_database", "Cloud SQL")

print("\nProvider-neutral service lookup:")
for provider in [aws, azure, google_cloud]:
    print(
        f"{provider.name}: "
        f"compute={provider.service_for('compute')}, "
        f"storage={provider.service_for('object_storage')}"
    )


# ============================================================================
# 15. CLOUD DEPLOYMENT DECISION FACTORS
# ============================================================================

@dataclass
class DecisionWeights:
    """
    Weights used for an educational architecture-scoring model.

    The model is not a replacement for a real cloud architecture review.
    It demonstrates how explicit criteria can reduce purely subjective decisions.
    """

    cost: float = 1.0
    scalability: float = 1.0
    control: float = 1.0
    security: float = 1.0
    compliance: float = 1.0
    portability: float = 1.0
    latency: float = 1.0
    operational_simplicity: float = 1.0

    def validate(self) -> None:
        values = self.__dict__.values()
        if any(weight < 0 for weight in values):
            raise ValueError("Decision weights cannot be negative.")
        if sum(values) == 0:
            raise ValueError("At least one decision weight must be positive.")


@dataclass
class ModelProfile:
    model: DeploymentModel
    scores: Dict[str, float]

    def validate(self) -> None:
        required = {
            "cost",
            "scalability",
            "control",
            "security",
            "compliance",
            "portability",
            "latency",
            "operational_simplicity",
        }

        missing = required - self.scores.keys()
        if missing:
            raise ValueError(f"Missing scores: {sorted(missing)}")

        for criterion, score in self.scores.items():
            if criterion not in required:
                raise ValueError(f"Unknown criterion: {criterion}")
            if not 1 <= score <= 10:
                raise ValueError(f"{criterion} must be between 1 and 10.")

    def weighted_score(self, weights: DecisionWeights) -> float:
        self.validate()
        weights.validate()

        weight_map = {
            "cost": weights.cost,
            "scalability": weights.scalability,
            "control": weights.control,
            "security": weights.security,
            "compliance": weights.compliance,
            "portability": weights.portability,
            "latency": weights.latency,
            "operational_simplicity": weights.operational_simplicity,
        }

        numerator = sum(
            self.scores[criterion] * weight
            for criterion, weight in weight_map.items()
        )
        denominator = sum(weight_map.values())

        return numerator / denominator


profiles = [
    ModelProfile(
        DeploymentModel.PUBLIC,
        {
            "cost": 8,
            "scalability": 10,
            "control": 6,
            "security": 8,
            "compliance": 7,
            "portability": 7,
            "latency": 8,
            "operational_simplicity": 9,
        },
    ),
    ModelProfile(
        DeploymentModel.PRIVATE,
        {
            "cost": 4,
            "scalability": 6,
            "control": 10,
            "security": 9,
            "compliance": 10,
            "portability": 5,
            "latency": 10,
            "operational_simplicity": 4,
        },
    ),
    ModelProfile(
        DeploymentModel.HYBRID,
        {
            "cost": 6,
            "scalability": 9,
            "control": 9,
            "security": 9,
            "compliance": 9,
            "portability": 7,
            "latency": 9,
            "operational_simplicity": 5,
        },
    ),
    ModelProfile(
        DeploymentModel.MULTI_CLOUD,
        {
            "cost": 5,
            "scalability": 10,
            "control": 8,
            "security": 8,
            "compliance": 8,
            "portability": 10,
            "latency": 8,
            "operational_simplicity": 3,
        },
    ),
    ModelProfile(
        DeploymentModel.COMMUNITY,
        {
            "cost": 6,
            "scalability": 7,
            "control": 8,
            "security": 9,
            "compliance": 10,
            "portability": 5,
            "latency": 8,
            "operational_simplicity": 5,
        },
    ),
]

weights = DecisionWeights(
    cost=1.0,
    scalability=1.5,
    control=1.0,
    security=1.5,
    compliance=1.5,
    portability=1.0,
    latency=1.0,
    operational_simplicity=1.0,
)

print("\nWeighted deployment-model comparison:")
ranked_models = sorted(
    profiles,
    key=lambda profile: profile.weighted_score(weights),
    reverse=True,
)

for rank, profile in enumerate(ranked_models, start=1):
    print(
        f"{rank}. {profile.model.value}: "
        f"{profile.weighted_score(weights):.2f}/10"
    )


# ============================================================================
# 16. WHY A SINGLE "BEST" DEPLOYMENT MODEL DOES NOT EXIST
# ============================================================================

def explain_tradeoffs() -> None:
    tradeoffs = {
        "Public cloud": [
            "Strong elasticity",
            "Fast provisioning",
            "Broad managed-service ecosystem",
            "Less physical infrastructure control",
            "Potential provider dependency",
        ],
        "Private cloud": [
            "High infrastructure control",
            "Useful for specialized governance requirements",
            "Higher operational burden",
            "Potentially higher capital and staffing requirements",
        ],
        "Hybrid cloud": [
            "Balances existing infrastructure with public-cloud elasticity",
            "Useful for gradual modernization",
            "Connectivity and identity become critical",
            "More complex architecture",
        ],
        "Multi-cloud": [
            "Can reduce dependence on one provider",
            "Can use provider-specific strengths",
            "Operations, networking, observability, and skills become more complex",
            "Portability does not happen automatically",
        ],
        "Community cloud": [
            "Can align shared governance requirements",
            "Useful when organizations have common constraints",
            "Requires agreement on governance, funding, security, and ownership",
        ],
    }

    print("\nMajor trade-offs:")
    for model, points in tradeoffs.items():
        print(f"\n{model}")
        for point in points:
            print(f"  - {point}")


explain_tradeoffs()


# ============================================================================
# 17. WORKLOAD PLACEMENT
# ============================================================================

def recommend_placement(workload: Workload) -> List[DeploymentModel]:
    """
    Produce a rule-based recommendation.

    This intentionally returns multiple candidates when requirements conflict.
    Real architecture decisions require business, legal, financial, and technical
    validation.
    """

    workload.validate()

    recommendations: List[DeploymentModel] = []

    if workload.compliance_requirement >= 9 and workload.data_sensitivity >= 9:
        recommendations.extend(
            [DeploymentModel.PRIVATE, DeploymentModel.HYBRID]
        )

    if workload.variable_demand >= 8:
        recommendations.append(DeploymentModel.PUBLIC)

    if workload.portability_requirement >= 9:
        recommendations.append(DeploymentModel.MULTI_CLOUD)

    if workload.compliance_requirement >= 8 and workload.data_sensitivity >= 8:
        recommendations.append(DeploymentModel.COMMUNITY)

    if not recommendations:
        recommendations.append(DeploymentModel.PUBLIC)

    # Remove duplicates while preserving order.
    return list(dict.fromkeys(recommendations))


print("\nRule-based workload placement:")
for workload in hybrid_workloads:
    choices = recommend_placement(workload)
    print(f"{workload.name}: {[choice.value for choice in choices]}")


# ============================================================================
# 18. CLOUD BURSTING
# ============================================================================

@dataclass
class CapacityPlan:
    baseline_capacity: int
    current_demand: int
    public_cloud_capacity: int

    def validate(self) -> None:
        if min(
            self.baseline_capacity,
            self.current_demand,
            self.public_cloud_capacity,
        ) < 0:
            raise ValueError("Capacity values cannot be negative.")

    def calculate_burst(self) -> int:
        self.validate()

        excess = max(0, self.current_demand - self.baseline_capacity)
        return min(excess, self.public_cloud_capacity)


burst_plan = CapacityPlan(
    baseline_capacity=1000,
    current_demand=1450,
    public_cloud_capacity=1000,
)

print("\nCloud-bursting example:")
print(f"Baseline capacity: {burst_plan.baseline_capacity}")
print(f"Demand: {burst_plan.current_demand}")
print(f"Capacity shifted to public cloud: {burst_plan.calculate_burst()}")


# ============================================================================
# 19. DISASTER RECOVERY
# ============================================================================

@dataclass
class DisasterRecoveryPlan:
    """
    Basic representation of RTO and RPO.

    RTO: Recovery Time Objective
         Maximum acceptable time to restore service.

    RPO: Recovery Point Objective
         Maximum acceptable amount of data loss measured in time.
    """

    recovery_time_objective_minutes: int
    recovery_point_objective_minutes: int
    backup_frequency_minutes: int

    def validate(self) -> None:
        values = [
            self.recovery_time_objective_minutes,
            self.recovery_point_objective_minutes,
            self.backup_frequency_minutes,
        ]

        if any(value <= 0 for value in values):
            raise ValueError("Recovery values must be positive.")

    def meets_rpo(self) -> bool:
        self.validate()
        return self.backup_frequency_minutes <= self.recovery_point_objective_minutes


dr_plan = DisasterRecoveryPlan(
    recovery_time_objective_minutes=60,
    recovery_point_objective_minutes=15,
    backup_frequency_minutes=10,
)

print("\nDisaster-recovery plan:")
print(f"RTO: {dr_plan.recovery_time_objective_minutes} minutes")
print(f"RPO: {dr_plan.recovery_point_objective_minutes} minutes")
print(f"Backup frequency: {dr_plan.backup_frequency_minutes} minutes")
print(f"RPO requirement satisfied: {dr_plan.meets_rpo()}")


# ============================================================================
# 20. AVAILABILITY AND FAILURE DOMAINS
# ============================================================================

@dataclass
class AvailabilityDesign:
    zones: int
    independent_failure_domains: int
    replicas: int

    def availability_score(self) -> float:
        """
        This is a simplified educational score, not a true availability
        probability calculation.

        Real availability depends on correlated failures, dependencies,
        recovery mechanisms, load balancers, databases, networking, DNS,
        deployment procedures, and many other components.
        """
        if min(self.zones, self.independent_failure_domains, self.replicas) < 1:
            raise ValueError("Availability values must be at least one.")

        raw_score = (
            self.zones
            + self.independent_failure_domains
            + self.replicas
        ) / 3

        return min(10.0, raw_score * 2)


availability_design = AvailabilityDesign(
    zones=3,
    independent_failure_domains=3,
    replicas=3,
)

print("\nAvailability design:")
print(f"Zones: {availability_design.zones}")
print(f"Failure domains: {availability_design.independent_failure_domains}")
print(f"Replicas: {availability_design.replicas}")
print(f"Educational resilience score: {availability_design.availability_score():.2f}/10")


# ============================================================================
# 21. DATA RESIDENCY
# ============================================================================

@dataclass
class DataPolicy:
    classification: str
    allowed_regions: Set[str]
    encryption_required: bool
    retention_days: int

    def validate(self) -> None:
        if not self.classification.strip():
            raise ValueError("Data classification cannot be empty.")
        if not self.allowed_regions:
            raise ValueError("At least one allowed region is required.")
        if self.retention_days <= 0:
            raise ValueError("Retention period must be positive.")

    def can_deploy_to(self, region: str) -> bool:
        self.validate()
        return region in self.allowed_regions


customer_data_policy = DataPolicy(
    classification="Restricted",
    allowed_regions={"India"},
    encryption_required=True,
    retention_days=3650,
)

print("\nData-residency checks:")
for region in ["India", "Germany", "United States"]:
    print(
        f"{region}: "
        f"{customer_data_policy.can_deploy_to(region)}"
    )


# ============================================================================
# 22. IDENTITY AND ACCESS MANAGEMENT
# ============================================================================

@dataclass(frozen=True)
class Permission:
    resource: str
    action: str


@dataclass
class Role:
    name: str
    permissions: Set[Permission] = field(default_factory=set)

    def allows(self, resource: str, action: str) -> bool:
        """
        Simple least-privilege authorization check.

        Production IAM systems contain substantially richer semantics such as
        conditions, identities, resource policies, inheritance, boundaries,
        service identities, and temporary credentials.
        """
        return Permission(resource, action) in self.permissions


read_only_role = Role(
    name="ReadOnlyApplication",
    permissions={
        Permission("customer-data", "read"),
        Permission("logs", "read"),
    },
)

admin_role = Role(
    name="PlatformAdministrator",
    permissions={
        Permission("customer-data", "read"),
        Permission("customer-data", "write"),
        Permission("logs", "read"),
        Permission("logs", "delete"),
    },
)

print("\nIAM authorization examples:")
for role in [read_only_role, admin_role]:
    print(
        f"{role.name}: "
        f"customer-data/write={role.allows('customer-data', 'write')}"
    )


# ============================================================================
# 23. SECURITY DESIGN PRINCIPLES
# ============================================================================

security_principles = [
    "Least privilege",
    "Strong identity verification",
    "Multi-factor authentication",
    "Encryption in transit",
    "Encryption at rest",
    "Secrets management",
    "Network segmentation",
    "Centralized logging",
    "Continuous monitoring",
    "Patch and vulnerability management",
    "Secure configuration",
    "Incident response planning",
    "Regular access review",
]

print("\nCore cloud-security principles:")
for principle in security_principles:
    print(f"- {principle}")


# ============================================================================
# 24. NETWORK ARCHITECTURE
# ============================================================================

@dataclass
class NetworkSegment:
    name: str
    publicly_reachable: bool
    purpose: str


network_segments = [
    NetworkSegment(
        "Public subnet",
        True,
        "Internet-facing load balancer",
    ),
    NetworkSegment(
        "Application subnet",
        False,
        "Application servers",
    ),
    NetworkSegment(
        "Database subnet",
        False,
        "Database systems",
    ),
]

print("\nExample network segmentation:")
for segment in network_segments:
    exposure = "public" if segment.publicly_reachable else "private"
    print(f"- {segment.name}: {exposure}; {segment.purpose}")


# ============================================================================
# 25. VENDOR LOCK-IN
# ============================================================================

@dataclass
class PortabilityAssessment:
    proprietary_services: int
    standardized_services: int
    data_exportability: int
    infrastructure_as_code: int

    def validate(self) -> None:
        values = [
            self.proprietary_services,
            self.standardized_services,
            self.data_exportability,
            self.infrastructure_as_code,
        ]

        if any(value < 0 for value in values):
            raise ValueError("Portability metrics cannot be negative.")

    def portability_score(self) -> float:
        self.validate()

        positive = (
            self.standardized_services
            + self.data_exportability
            + self.infrastructure_as_code
        )

        total = positive + self.proprietary_services

        if total == 0:
            return 0.0

        return positive / total * 10


portability = PortabilityAssessment(
    proprietary_services=3,
    standardized_services=7,
    data_exportability=8,
    infrastructure_as_code=9,
)

print("\nPortability assessment:")
print(f"Portability score: {portability.portability_score():.2f}/10")


# ============================================================================
# 26. MULTI-CLOUD COMPLEXITY
# ============================================================================

def multi_cloud_complexity(
    provider_count: int,
    networking_domains: int,
    identity_domains: int,
    monitoring_systems: int,
) -> float:
    """
    Approximate operational complexity.

    This is not a mathematical law. It demonstrates why adding providers can
    increase the number of integration points and operational concerns.
    """
    if min(
        provider_count,
        networking_domains,
        identity_domains,
        monitoring_systems,
    ) < 1:
        raise ValueError("Complexity inputs must be positive.")

    return (
        provider_count * 1.5
        + networking_domains
        + identity_domains
        + monitoring_systems
    )


print("\nMulti-cloud complexity examples:")
for providers in [1, 2, 3]:
    complexity = multi_cloud_complexity(
        provider_count=providers,
        networking_domains=providers,
        identity_domains=providers,
        monitoring_systems=providers,
    )
    print(f"{providers} provider(s): complexity index={complexity:.1f}")


# ============================================================================
# 27. COST MODEL
# ============================================================================

@dataclass
class MonthlyCloudCost:
    compute: float
    storage: float
    network: float
    database: float
    operations: float

    def total(self) -> float:
        values = [
            self.compute,
            self.storage,
            self.network,
            self.database,
            self.operations,
        ]

        if any(value < 0 for value in values):
            raise ValueError("Cloud costs cannot be negative.")

        return sum(values)

    def annual_cost(self) -> float:
        return self.total() * 12


cost = MonthlyCloudCost(
    compute=1200.00,
    storage=350.00,
    network=250.00,
    database=900.00,
    operations=300.00,
)

print("\nCloud cost model:")
print(f"Monthly cost: ${cost.total():,.2f}")
print(f"Annualized cost: ${cost.annual_cost():,.2f}")


# ============================================================================
# 28. TCO AND OPPORTUNITY COST
# ============================================================================

@dataclass
class TotalCostOfOwnership:
    infrastructure: float
    software: float
    personnel: float
    facilities: float
    networking: float
    downtime: float

    def total(self) -> float:
        values = self.__dict__.values()

        if any(value < 0 for value in values):
            raise ValueError("TCO values cannot be negative.")

        return sum(values)


private_tco = TotalCostOfOwnership(
    infrastructure=2_000_000,
    software=400_000,
    personnel=1_200_000,
    facilities=300_000,
    networking=200_000,
    downtime=150_000,
)

public_tco = TotalCostOfOwnership(
    infrastructure=400_000,
    software=500_000,
    personnel=700_000,
    facilities=50_000,
    networking=300_000,
    downtime=100_000,
)

print("\nSimplified TCO comparison:")
print(f"Private environment: ${private_tco.total():,.0f}")
print(f"Public cloud: ${public_tco.total():,.0f}")


# ============================================================================
# 29. CLOUD ELASTICITY
# ============================================================================

def required_instances(
    demand: int,
    capacity_per_instance: int,
    minimum_instances: int = 1,
    maximum_instances: int = 100,
) -> int:
    """
    Calculate instances required to satisfy demand.

    ceil() ensures that partial capacity requirements result in a complete
    instance.
    """
    if demand < 0:
        raise ValueError("Demand cannot be negative.")
    if capacity_per_instance <= 0:
        raise ValueError("Capacity per instance must be positive.")
    if minimum_instances < 1:
        raise ValueError("Minimum instances must be at least one.")
    if maximum_instances < minimum_instances:
        raise ValueError("Maximum instances must not be below minimum.")

    required = max(
        minimum_instances,
        ceil(demand / capacity_per_instance),
    )

    return min(required, maximum_instances)


print("\nElasticity examples:")
for demand in [0, 50, 100, 101, 450, 1000, 12000]:
    instances = required_instances(
        demand=demand,
        capacity_per_instance=100,
        minimum_instances=2,
        maximum_instances=100,
    )
    print(f"Demand={demand:5d} -> instances={instances}")


# ============================================================================
# 30. CLOUD-NATIVE VS CLOUD-HOSTED
# ============================================================================

def architecture_style_comparison() -> Dict[str, List[str]]:
    return {
        "Cloud-hosted": [
            "Existing application moved to cloud infrastructure",
            "May preserve traditional architecture",
            "Can provide rapid migration",
            "May not exploit all cloud-native capabilities",
        ],
        "Cloud-native": [
            "Designed around elastic and distributed cloud capabilities",
            "Often uses managed services and automation",
            "Can improve scalability and resilience",
            "Introduces distributed-system complexity",
        ],
    }


print("\nCloud-hosted vs cloud-native:")
for style, characteristics in architecture_style_comparison().items():
    print(f"\n{style}")
    for characteristic in characteristics:
        print(f"  - {characteristic}")


# ============================================================================
# 31. CONTAINERS AND KUBERNETES CONCEPTS
# ============================================================================

@dataclass
class ContainerDeployment:
    image: str
    replicas: int
    cpu_request: float
    memory_gb: float

    def validate(self) -> None:
        if not self.image.strip():
            raise ValueError("Container image cannot be empty.")
        if self.replicas < 1:
            raise ValueError("At least one replica is required.")
        if self.cpu_request <= 0:
            raise ValueError("CPU request must be positive.")
        if self.memory_gb <= 0:
            raise ValueError("Memory allocation must be positive.")

    def total_cpu(self) -> float:
        self.validate()
        return self.replicas * self.cpu_request

    def total_memory(self) -> float:
        self.validate()
        return self.replicas * self.memory_gb


container_deployment = ContainerDeployment(
    image="example-api:1.0",
    replicas=4,
    cpu_request=0.5,
    memory_gb=1.0,
)

print("\nContainer deployment:")
print(f"Replicas: {container_deployment.replicas}")
print(f"Total CPU requested: {container_deployment.total_cpu():.1f}")
print(f"Total memory requested: {container_deployment.total_memory():.1f} GB")


# ============================================================================
# 32. SERVERLESS CONCEPT
# ============================================================================

@dataclass
class ServerlessWorkload:
    requests: int
    average_duration_ms: float
    memory_gb: float

    def compute_seconds(self) -> float:
        if self.requests < 0:
            raise ValueError("Requests cannot be negative.")
        if self.average_duration_ms < 0:
            raise ValueError("Duration cannot be negative.")
        if self.memory_gb <= 0:
            raise ValueError("Memory must be positive.")

        return self.requests * self.average_duration_ms / 1000


serverless = ServerlessWorkload(
    requests=1_000_000,
    average_duration_ms=120,
    memory_gb=0.5,
)

print("\nServerless workload:")
print(f"Approximate compute seconds: {serverless.compute_seconds():,.0f}")


# ============================================================================
# 33. CLOUD MIGRATION STRATEGIES
# ============================================================================

migration_strategies = {
    "Rehost": "Move the workload with minimal architectural change.",
    "Replatform": "Make limited changes to use selected managed cloud capabilities.",
    "Refactor": "Redesign the application substantially for cloud-native operation.",
    "Repurchase": "Replace the existing solution with a different service or product.",
    "Retain": "Keep the workload where it currently runs.",
    "Retire": "Remove a workload that no longer provides sufficient value.",
}

print("\nCloud migration strategies:")
for strategy, meaning in migration_strategies.items():
    print(f"- {strategy}: {meaning}")


# ============================================================================
# 34. HYBRID MIGRATION EXAMPLE
# ============================================================================

@dataclass
class MigrationWorkload:
    name: str
    business_criticality: int
    modernization_effort: int
    data_sensitivity: int
    cloud_readiness: int

    def validate(self) -> None:
        values = {
            "business_criticality": self.business_criticality,
            "modernization_effort": self.modernization_effort,
            "data_sensitivity": self.data_sensitivity,
            "cloud_readiness": self.cloud_readiness,
        }

        for name, value in values.items():
            if not 1 <= value <= 10:
                raise ValueError(f"{name} must be between 1 and 10.")


def migration_recommendation(workload: MigrationWorkload) -> str:
    workload.validate()

    if workload.cloud_readiness >= 8 and workload.modernization_effort <= 4:
        return "Rehost"

    if workload.cloud_readiness >= 6 and workload.modernization_effort <= 7:
        return "Replatform"

    if workload.modernization_effort >= 8:
        return "Refactor"

    if workload.data_sensitivity >= 9 and workload.business_criticality >= 9:
        return "Retain temporarily and modernize through controlled phases"

    return "Assess through a migration business case"


migration_examples = [
    MigrationWorkload(
        "Internal Reporting",
        business_criticality=4,
        modernization_effort=3,
        data_sensitivity=5,
        cloud_readiness=9,
    ),
    MigrationWorkload(
        "Legacy Core Transaction System",
        business_criticality=10,
        modernization_effort=10,
        data_sensitivity=10,
        cloud_readiness=3,
    ),
]

print("\nMigration recommendations:")
for workload in migration_examples:
    print(f"{workload.name}: {migration_recommendation(workload)}")


# ============================================================================
# 35. EDGE CASES AND VALIDATION
# ============================================================================

print("\nEdge-case validation examples:")

edge_cases = [
    ("Negative cloud demand", lambda: required_instances(-1, 100)),
    ("Zero capacity", lambda: required_instances(100, 0)),
    ("Invalid retention", lambda: DataPolicy("Restricted", {"India"}, True, 0).validate()),
    ("Invalid multi-cloud", lambda: MultiCloudArchitecture({"AWS"}, "AWS").validate()),
]

for name, operation in edge_cases:
    try:
        operation()
    except (ValueError, KeyError) as error:
        print(f"- {name}: correctly rejected -> {error}")


# ============================================================================
# 36. COMMON ARCHITECTURAL MISTAKES
# ============================================================================

common_mistakes = [
    "Choosing a deployment model only because it is popular.",
    "Assuming public cloud automatically means insecure.",
    "Assuming private cloud automatically means secure.",
    "Confusing hybrid cloud with multi-cloud.",
    "Ignoring data residency and regulatory requirements.",
    "Ignoring egress and network costs.",
    "Assuming multi-cloud automatically eliminates vendor lock-in.",
    "Using provider-specific services without assessing portability requirements.",
    "Failing to design identity federation in hybrid environments.",
    "Treating backups as equivalent to disaster recovery.",
    "Ignoring observability across cloud boundaries.",
    "Using overly broad administrative permissions.",
    "Migrating workloads without understanding their dependencies.",
    "Measuring cloud cost without including operational labor.",
    "Assuming cloud elasticity means unlimited capacity at zero cost.",
]

print("\nCommon mistakes:")
for mistake in common_mistakes:
    print(f"- {mistake}")


# ============================================================================
# 37. LIMITATIONS OF ARCHITECTURE SCORING
# ============================================================================

def demonstrate_scoring_limitations() -> None:
    """
    Weighted scoring is useful for transparent decision-making but can hide
    important constraints.

    Example:
        A workload may receive a high public-cloud score while a mandatory
        legal requirement prohibits its data from leaving a particular region.

    A hard constraint should override a soft preference.
    """

    hard_constraint = DataPolicy(
        classification="Highly Restricted",
        allowed_regions={"India"},
        encryption_required=True,
        retention_days=3650,
    )

    candidate_regions = ["India", "Germany"]

    print("\nHard-constraint example:")
    for region in candidate_regions:
        allowed = hard_constraint.can_deploy_to(region)
        print(f"{region}: {'Allowed' if allowed else 'Rejected'}")


demonstrate_scoring_limitations()


# ============================================================================
# 38. HARD CONSTRAINTS VS SOFT PREFERENCES
# ============================================================================

@dataclass
class ArchitectureRequirements:
    mandatory_private: bool
    mandatory_region: Optional[str]
    minimum_security_score: float
    maximum_monthly_cost: float

    def validate(self) -> None:
        if not 0 <= self.minimum_security_score <= 10:
            raise ValueError("Security score must be between 0 and 10.")
        if self.maximum_monthly_cost < 0:
            raise ValueError("Maximum monthly cost cannot be negative.")


@dataclass
class ArchitectureCandidate:
    name: str
    private: bool
    region: str
    security_score: float
    monthly_cost: float

    def satisfies(self, requirements: ArchitectureRequirements) -> bool:
        requirements.validate()

        if requirements.mandatory_private and not self.private:
            return False

        if (
            requirements.mandatory_region is not None
            and self.region != requirements.mandatory_region
        ):
            return False

        if self.security_score < requirements.minimum_security_score:
            return False

        if self.monthly_cost > requirements.maximum_monthly_cost:
            return False

        return True


requirements = ArchitectureRequirements(
    mandatory_private=False,
    mandatory_region="India",
    minimum_security_score=8,
    maximum_monthly_cost=10_000,
)

candidates = [
    ArchitectureCandidate("AWS India", False, "India", 8.5, 8_000),
    ArchitectureCandidate("Azure Germany", False, "Germany", 9.0, 7_000),
    ArchitectureCandidate("Private India", True, "India", 9.5, 12_000),
]

print("\nCandidate filtering:")
for candidate in candidates:
    print(
        f"{candidate.name}: "
        f"{'acceptable' if candidate.satisfies(requirements) else 'rejected'}"
    )


# ============================================================================
# 39. OBSERVABILITY
# ============================================================================

@dataclass
class ObservabilitySignals:
    logs: bool
    metrics: bool
    traces: bool
    alerts: bool

    def completeness_score(self) -> float:
        signals = [
            self.logs,
            self.metrics,
            self.traces,
            self.alerts,
        ]
        return sum(signals) / len(signals) * 10


observability = ObservabilitySignals(
    logs=True,
    metrics=True,
    traces=True,
    alerts=True,
)

print("\nObservability:")
print(f"Signal coverage score: {observability.completeness_score():.1f}/10")


# ============================================================================
# 40. INFRASTRUCTURE AS CODE CONCEPT
# ============================================================================

@dataclass
class InfrastructureResource:
    resource_type: str
    name: str
    region: str


class InfrastructurePlan:
    """
    A simplified infrastructure-as-code representation.

    Real infrastructure-as-code tools maintain resource graphs, state,
    dependency relationships, plans, providers, modules, policies, and
    lifecycle operations. This class demonstrates the core idea of expressing
    infrastructure declaratively as structured data.
    """

    def __init__(self) -> None:
        self.resources: List[InfrastructureResource] = []

    def add_resource(
        self,
        resource_type: str,
        name: str,
        region: str,
    ) -> None:
        if not resource_type.strip():
            raise ValueError("Resource type cannot be empty.")
        if not name.strip():
            raise ValueError("Resource name cannot be empty.")
        if not region.strip():
            raise ValueError("Region cannot be empty.")

        self.resources.append(
            InfrastructureResource(
                resource_type=resource_type,
                name=name,
                region=region,
            )
        )

    def plan(self) -> List[str]:
        return [
            f"CREATE {resource.resource_type} "
            f"{resource.name} in {resource.region}"
            for resource in self.resources
        ]


infrastructure = InfrastructurePlan()
infrastructure.add_resource("network", "production-network", "India")
infrastructure.add_resource("application", "production-api", "India")
infrastructure.add_resource("database", "production-db", "India")

print("\nInfrastructure-as-code-style plan:")
for action in infrastructure.plan():
    print(f"- {action}")


# ============================================================================
# 41. POLICY-AS-CODE CONCEPT
# ============================================================================

@dataclass
class SecurityPolicy:
    require_encryption: bool
    prohibit_public_database: bool
    require_logging: bool

    def evaluate(
        self,
        encrypted: bool,
        public_database: bool,
        logging_enabled: bool,
    ) -> Tuple[bool, List[str]]:
        violations: List[str] = []

        if self.require_encryption and not encrypted:
            violations.append("Encryption is required.")

        if self.prohibit_public_database and public_database:
            violations.append("Public databases are prohibited.")

        if self.require_logging and not logging_enabled:
            violations.append("Centralized logging is required.")

        return len(violations) == 0, violations


security_policy = SecurityPolicy(
    require_encryption=True,
    prohibit_public_database=True,
    require_logging=True,
)

compliant, violations = security_policy.evaluate(
    encrypted=True,
    public_database=False,
    logging_enabled=True,
)

print("\nPolicy-as-code evaluation:")
print(f"Compliant: {compliant}")
print(f"Violations: {violations}")


# ============================================================================
# 42. CLOUD GOVERNANCE
# ============================================================================

governance_controls = [
    "Account/subscription/project structure",
    "Identity and access management",
    "Resource naming standards",
    "Tagging and metadata",
    "Budget controls",
    "Network standards",
    "Encryption requirements",
    "Logging requirements",
    "Data-classification rules",
    "Region restrictions",
    "Backup requirements",
    "Incident response procedures",
    "Change management",
    "Policy enforcement",
]

print("\nCloud-governance controls:")
for control in governance_controls:
    print(f"- {control}")


# ============================================================================
# 43. CLOUD LANDING ZONE CONCEPT
# ============================================================================

@dataclass
class LandingZone:
    identity: bool
    network: bool
    logging: bool
    security_baseline: bool
    governance: bool
    billing_structure: bool

    def readiness_score(self) -> float:
        controls = [
            self.identity,
            self.network,
            self.logging,
            self.security_baseline,
            self.governance,
            self.billing_structure,
        ]

        return sum(controls) / len(controls) * 100


landing_zone = LandingZone(
    identity=True,
    network=True,
    logging=True,
    security_baseline=True,
    governance=True,
    billing_structure=True,
)

print("\nLanding-zone readiness:")
print(f"{landing_zone.readiness_score():.0f}%")


# ============================================================================
# 44. REGION AND AVAILABILITY ZONE CONCEPTS
# ============================================================================

@dataclass
class CloudRegion:
    name: str
    availability_zones: int
    data_residency_country: str

    def validate(self) -> None:
        if self.availability_zones < 1:
            raise ValueError("A region must contain at least one availability zone.")
        if not self.name.strip():
            raise ValueError("Region name cannot be empty.")
        if not self.data_residency_country.strip():
            raise ValueError("Country cannot be empty.")


india_region = CloudRegion(
    name="Example India Region",
    availability_zones=3,
    data_residency_country="India",
)

india_region.validate()

print("\nRegion concept:")
print(f"Region: {india_region.name}")
print(f"Availability zones: {india_region.availability_zones}")
print(f"Data-residency country: {india_region.data_residency_country}")


# ============================================================================
# 45. DATA TRANSFER AND EGRESS
# ============================================================================

@dataclass
class DataTransfer:
    gigabytes: float
    price_per_gb: float

    def cost(self) -> float:
        if self.gigabytes < 0:
            raise ValueError("Data volume cannot be negative.")
        if self.price_per_gb < 0:
            raise ValueError("Price cannot be negative.")

        return self.gigabytes * self.price_per_gb


transfer = DataTransfer(
    gigabytes=25_000,
    price_per_gb=0.05,
)

print("\nData-transfer example:")
print(f"Estimated transfer cost: ${transfer.cost():,.2f}")


# ============================================================================
# 46. DEPENDENCY MAPPING
# ============================================================================

@dataclass
class ApplicationDependencyGraph:
    dependencies: Dict[str, Set[str]]

    def validate(self) -> None:
        nodes = set(self.dependencies)

        for service, dependencies in self.dependencies.items():
            unknown = dependencies - nodes

            if unknown:
                raise ValueError(
                    f"{service} depends on undefined services: {sorted(unknown)}"
                )

    def direct_dependencies(self, service: str) -> Set[str]:
        self.validate()

        if service not in self.dependencies:
            raise KeyError(f"Unknown service: {service}")

        return self.dependencies[service]


dependency_graph = ApplicationDependencyGraph(
    dependencies={
        "web": {"api"},
        "api": {"database", "cache"},
        "database": set(),
        "cache": set(),
    }
)

print("\nApplication dependency graph:")
for service, dependencies in dependency_graph.dependencies.items():
    print(f"{service} -> {sorted(dependencies)}")


# ============================================================================
# 47. HYBRID CONNECTIVITY FAILURE
# ============================================================================

@dataclass
class ConnectivityDesign:
    primary_links: int
    backup_links: int

    def resilience_level(self) -> str:
        if self.primary_links < 1:
            raise ValueError("At least one primary link is required.")
        if self.backup_links < 0:
            raise ValueError("Backup links cannot be negative.")

        if self.backup_links >= 2:
            return "Highly redundant"
        if self.backup_links == 1:
            return "Redundant"
        return "Single-path"


connectivity = ConnectivityDesign(
    primary_links=1,
    backup_links=1,
)

print("\nHybrid connectivity:")
print(f"Resilience: {connectivity.resilience_level()}")


# ============================================================================
# 48. SECURITY EDGE CASE: PUBLIC DATABASE
# ============================================================================

def database_exposure_risk(
    internet_accessible: bool,
    strong_authentication: bool,
    network_restrictions: bool,
    encryption: bool,
) -> str:
    """
    Demonstrates that security is multi-layered.

    Strong authentication alone should not be treated as sufficient protection
    for a sensitive database.
    """
    risk_factors = 0

    if internet_accessible:
        risk_factors += 2
    if not strong_authentication:
        risk_factors += 3
    if not network_restrictions:
        risk_factors += 2
    if not encryption:
        risk_factors += 2

    if risk_factors >= 6:
        return "High"
    if risk_factors >= 3:
        return "Medium"
    return "Lower"


print("\nDatabase exposure assessment:")
print(
    database_exposure_risk(
        internet_accessible=True,
        strong_authentication=True,
        network_restrictions=False,
        encryption=True,
    )
)


# ============================================================================
# 49. PERFORMANCE CONSIDERATIONS
# ============================================================================

def estimate_latency(
    application_processing_ms: float,
    network_hops: int,
    average_hop_latency_ms: float,
) -> float:
    """
    Simplified latency estimate.

    Real cloud latency is affected by geographic distance, routing, congestion,
    protocol behavior, TLS setup, queueing, storage latency, service-side
    processing, and network conditions.
    """
    if application_processing_ms < 0:
        raise ValueError("Processing latency cannot be negative.")
    if network_hops < 0:
        raise ValueError("Network hops cannot be negative.")
    if average_hop_latency_ms < 0:
        raise ValueError("Hop latency cannot be negative.")

    return application_processing_ms + (
        network_hops * average_hop_latency_ms
    )


print("\nLatency estimation:")
print(
    f"Estimated latency: "
    f"{estimate_latency(20, 4, 5):.1f} ms"
)


# ============================================================================
# 50. CACHING AND DISTRIBUTION
# ============================================================================

@dataclass
class CacheModel:
    total_requests: int
    cache_hits: int

    def hit_rate(self) -> float:
        if self.total_requests <= 0:
            raise ValueError("Total requests must be positive.")
        if not 0 <= self.cache_hits <= self.total_requests:
            raise ValueError("Cache hits must be within total requests.")

        return self.cache_hits / self.total_requests


cache = CacheModel(
    total_requests=1_000_000,
    cache_hits=920_000,
)

print("\nCaching:")
print(f"Cache hit rate: {cache.hit_rate() * 100:.2f}%")


# ============================================================================
# 51. TESTING CLOUD ARCHITECTURE
# ============================================================================

@dataclass
class ArchitectureTest:
    name: str
    passed: bool
    observation: str


architecture_tests = [
    ArchitectureTest(
        "Fail one application instance",
        True,
        "Traffic continues to healthy replicas.",
    ),
    ArchitectureTest(
        "Disable primary connectivity link",
        True,
        "Traffic uses backup connectivity.",
    ),
    ArchitectureTest(
        "Attempt unauthorized database write",
        True,
        "IAM policy denies the operation.",
    ),
    ArchitectureTest(
        "Deploy to prohibited region",
        True,
        "Policy validation rejects deployment.",
    ),
    ArchitectureTest(
        "Restore database from backup",
        True,
        "Recovery process meets the target RPO/RTO.",
    ),
]

print("\nArchitecture test cases:")
for test in architecture_tests:
    result = "PASS" if test.passed else "FAIL"
    print(f"[{result}] {test.name}: {test.observation}")


# ============================================================================
# 52. PRODUCTION READINESS CHECKLIST
# ============================================================================

production_checklist = {
    "Architecture": [
        "Clear workload boundaries",
        "Documented dependencies",
        "Defined failure domains",
        "Capacity strategy",
    ],
    "Security": [
        "Least privilege",
        "Strong authentication",
        "Encryption",
        "Secrets management",
        "Security monitoring",
    ],
    "Reliability": [
        "Backups",
        "Recovery testing",
        "Redundancy",
        "Defined RTO and RPO",
    ],
    "Operations": [
        "Centralized logs",
        "Metrics",
        "Tracing where appropriate",
        "Alerting",
        "Runbooks",
    ],
    "Governance": [
        "Resource ownership",
        "Cost controls",
        "Region restrictions",
        "Policy enforcement",
    ],
}

print("\nProduction-readiness checklist:")
for category, controls in production_checklist.items():
    print(f"\n{category}")
    for control in controls:
        print(f"  [ ] {control}")


# ============================================================================
# 53. DECISION ENGINE
# ============================================================================

class CloudDeploymentDecisionEngine:
    """
    Combines hard constraints and weighted preferences.

    Hard constraints are checked first. Only candidates that satisfy mandatory
    requirements participate in preference-based ranking.
    """

    def __init__(
        self,
        requirements: ArchitectureRequirements,
        weights: DecisionWeights,
    ) -> None:
        self.requirements = requirements
        self.weights = weights
        self.requirements.validate()
        self.weights.validate()

    def filter_candidates(
        self,
        candidates: Sequence[ArchitectureCandidate],
    ) -> List[ArchitectureCandidate]:
        return [
            candidate
            for candidate in candidates
            if candidate.satisfies(self.requirements)
        ]


decision_engine = CloudDeploymentDecisionEngine(
    requirements=requirements,
    weights=weights,
)

acceptable_candidates = decision_engine.filter_candidates(candidates)

print("\nDecision engine:")
for candidate in acceptable_candidates:
    print(f"- {candidate.name}")


# ============================================================================
# 54. DECISION FRAMEWORK
# ============================================================================

def deployment_model_decision_framework(
    *,
    sensitive_data: bool,
    strict_compliance: bool,
    highly_variable_demand: bool,
    existing_private_infrastructure: bool,
    multiple_provider_requirement: bool,
    shared_industry_requirement: bool,
) -> List[str]:
    """
    Generate candidate deployment models from explicit requirements.

    Multiple results are intentionally possible.
    """

    candidates: List[str] = []

    if multiple_provider_requirement:
        candidates.append(DeploymentModel.MULTI_CLOUD.value)

    if existing_private_infrastructure and (
        sensitive_data or strict_compliance
    ):
        candidates.append(DeploymentModel.HYBRID.value)

    if strict_compliance and shared_industry_requirement:
        candidates.append(DeploymentModel.COMMUNITY.value)

    if sensitive_data and strict_compliance:
        candidates.append(DeploymentModel.PRIVATE.value)

    if highly_variable_demand:
        candidates.append(DeploymentModel.PUBLIC.value)

    if not candidates:
        candidates.append(DeploymentModel.PUBLIC.value)

    return list(dict.fromkeys(candidates))


print("\nArchitecture decision framework:")
framework_result = deployment_model_decision_framework(
    sensitive_data=True,
    strict_compliance=True,
    highly_variable_demand=True,
    existing_private_infrastructure=True,
    multiple_provider_requirement=True,
    shared_industry_requirement=False,
)

for model in framework_result:
    print(f"- {model}")


# ============================================================================
# 55. ADVANCED SCENARIO: ENTERPRISE HYBRID + MULTI-CLOUD
# ============================================================================

enterprise_architecture = {
    "private_environment": [
        "Legacy transaction database",
        "Internal identity systems",
        "Highly sensitive workloads",
    ],
    "aws": [
        "Elastic customer-facing APIs",
        "Analytics workloads",
        "Object storage",
    ],
    "azure": [
        "Enterprise application integration",
        "Selected managed database services",
    ],
    "shared_controls": [
        "Federated identity",
        "Centralized logging",
        "Common security policies",
        "Infrastructure as code",
        "Centralized cost governance",
    ],
}

print("\nEnterprise hybrid + multi-cloud architecture:")
for environment, components in enterprise_architecture.items():
    print(f"\n{environment}")
    for component in components:
        print(f"  - {component}")


# ============================================================================
# 56. ADVANCED SCENARIO: ACTIVE-ACTIVE MULTI-CLOUD
# ============================================================================

@dataclass
class ActiveActiveDesign:
    provider_a_capacity_percent: float
    provider_b_capacity_percent: float
    replicated_data: bool
    synchronized_identity: bool
    global_traffic_management: bool

    def validate(self) -> None:
        if abs(
            self.provider_a_capacity_percent
            + self.provider_b_capacity_percent
            - 100
        ) > 0.01:
            raise ValueError("Provider capacity percentages must total 100.")

        if not self.replicated_data:
            raise ValueError("Active-active data architecture needs replication.")
        if not self.synchronized_identity:
            raise ValueError("Identity must work across both environments.")
        if not self.global_traffic_management:
            raise ValueError(
                "Traffic management is required to distribute workloads."
            )


active_active = ActiveActiveDesign(
    provider_a_capacity_percent=50,
    provider_b_capacity_percent=50,
    replicated_data=True,
    synchronized_identity=True,
    global_traffic_management=True,
)

active_active.validate()

print("\nActive-active multi-cloud design:")
print("Provider A capacity: 50%")
print("Provider B capacity: 50%")
print("Data replication: enabled")
print("Identity synchronization: enabled")
print("Global traffic management: enabled")


# ============================================================================
# 57. ADVANCED SCENARIO: ACTIVE-PASSIVE DISASTER RECOVERY
# ============================================================================

@dataclass
class ActivePassiveDesign:
    primary_region: str
    recovery_region: str
    recovery_capacity_percent: float
    replication_enabled: bool

    def validate(self) -> None:
        if self.primary_region == self.recovery_region:
            raise ValueError("Recovery region must differ from primary region.")

        if not 0 <= self.recovery_capacity_percent <= 100:
            raise ValueError("Recovery capacity must be between 0 and 100.")

        if not self.replication_enabled:
            raise ValueError("Replication is required for this design.")


active_passive = ActivePassiveDesign(
    primary_region="India",
    recovery_region="Singapore",
    recovery_capacity_percent=30,
    replication_enabled=True,
)

active_passive.validate()

print("\nActive-passive disaster recovery:")
print(f"Primary: {active_passive.primary_region}")
print(f"Recovery: {active_passive.recovery_region}")
print(f"Pre-provisioned recovery capacity: {active_passive.recovery_capacity_percent}%")


# ============================================================================
# 58. DATA CLASSIFICATION
# ============================================================================

class DataClassification(Enum):
    PUBLIC = "Public"
    INTERNAL = "Internal"
    CONFIDENTIAL = "Confidential"
    RESTRICTED = "Restricted"


classification_controls = {
    DataClassification.PUBLIC: [
        "Basic integrity protection",
        "Availability requirements",
    ],
    DataClassification.INTERNAL: [
        "Authenticated access",
        "Internal access controls",
    ],
    DataClassification.CONFIDENTIAL: [
        "Strong access controls",
        "Encryption",
        "Audit logging",
    ],
    DataClassification.RESTRICTED: [
        "Strict least privilege",
        "Encryption",
        "Detailed auditing",
        "Data residency controls",
        "Enhanced monitoring",
    ],
}

print("\nData classification:")
for classification, controls in classification_controls.items():
    print(f"\n{classification.value}")
    for control in controls:
        print(f"  - {control}")


# ============================================================================
# 59. CLOUD SECURITY THREAT MODEL
# ============================================================================

@dataclass
class Threat:
    name: str
    likelihood: int
    impact: int

    def risk_score(self) -> int:
        if not 1 <= self.likelihood <= 5:
            raise ValueError("Likelihood must be 1..5.")
        if not 1 <= self.impact <= 5:
            raise ValueError("Impact must be 1..5.")

        return self.likelihood * self.impact


threats = [
    Threat("Credential compromise", 4, 5),
    Threat("Misconfigured storage", 4, 4),
    Threat("Network exposure", 3, 5),
    Threat("Provider outage", 2, 5),
    Threat("Insufficient logging", 3, 3),
]

print("\nCloud threat assessment:")
for threat in sorted(threats, key=lambda item: item.risk_score(), reverse=True):
    print(f"- {threat.name}: risk={threat.risk_score()}")


# ============================================================================
# 60. CLOUD GOVERNANCE SCORE
# ============================================================================

def governance_score(
    identity: bool,
    security: bool,
    cost: bool,
    compliance: bool,
    operations: bool,
) -> float:
    controls = [identity, security, cost, compliance, operations]
    return sum(controls) / len(controls) * 100


print("\nGovernance score:")
print(
    f"{governance_score(True, True, True, True, False):.0f}%"
)


# ============================================================================
# 61. TESTING PRINCIPLES
# ============================================================================

def run_basic_assertions() -> None:
    """
    Lightweight executable checks.

    These assertions demonstrate expected behavior without requiring pytest
    or another external package.
    """

    assert required_instances(0, 100, 1, 10) == 1
    assert required_instances(100, 100, 1, 10) == 1
    assert required_instances(101, 100, 1, 10) == 2

    assert DataPolicy(
        "Internal",
        {"India"},
        True,
        30,
    ).can_deploy_to("India")

    assert not DataPolicy(
        "Internal",
        {"India"},
        True,
        30,
    ).can_deploy_to("Germany")

    assert multi_cloud_complexity(2, 2, 2, 2) > (
        multi_cloud_complexity(1, 1, 1, 1)
    )

    assert CacheModel(100, 90).hit_rate() == 0.9

    print("\nBasic assertions: PASS")


run_basic_assertions()


# ============================================================================
# 62. PERFORMANCE CONSIDERATIONS
# ============================================================================

def benchmark_complexity_explanation() -> Dict[str, str]:
    """
    Explain complexity characteristics of the educational implementations.

    The goal is to connect cloud architecture concepts with software-engineering
    concerns without pretending that cloud performance can be reduced to one
    algorithmic complexity measure.
    """

    return {
        "required_instances": "O(1)",
        "cache_hit_rate": "O(1)",
        "candidate_filtering": "O(n)",
        "model_ranking": "O(n log n)",
        "dependency_lookup": "O(1) average for dictionary access",
        "policy_evaluation": "O(k), where k is the number of policy checks",
    }


print("\nAlgorithmic complexity:")
for operation, complexity in benchmark_complexity_explanation().items():
    print(f"- {operation}: {complexity}")


# ============================================================================
# 63. PRODUCTION DESIGN PRINCIPLES
# ============================================================================

production_principles = [
    "Design for failure rather than assuming infrastructure never fails.",
    "Keep identity centralized and strongly governed.",
    "Separate public-facing components from sensitive data systems.",
    "Automate infrastructure and policy where practical.",
    "Treat observability as part of the architecture.",
    "Measure reliability with explicit objectives.",
    "Model cloud cost as an engineering concern.",
    "Use hard compliance requirements as constraints.",
    "Use standardized interfaces when portability matters.",
    "Test recovery instead of merely documenting recovery.",
    "Minimize unnecessary cross-cloud data movement.",
    "Document provider-specific dependencies.",
    "Use least privilege for humans and workloads.",
    "Validate architecture continuously as services and requirements change.",
]

print("\nProduction design principles:")
for principle in production_principles:
    print(f"- {principle}")


# ============================================================================
# 64. FINAL CONCEPT MAP
# ============================================================================

concept_map = {
    "Deployment model": [
        "Public",
        "Private",
        "Hybrid",
        "Multi-cloud",
        "Community",
    ],
    "Service model": [
        "IaaS",
        "PaaS",
        "SaaS",
    ],
    "Architecture concerns": [
        "Security",
        "Compliance",
        "Cost",
        "Scalability",
        "Availability",
        "Latency",
        "Portability",
        "Operations",
    ],
    "Cloud providers": [
        "AWS",
        "Microsoft Azure",
        "Google Cloud",
    ],
}

print("\nConcept map:")
for category, concepts in concept_map.items():
    print(f"\n{category}")
    print("  " + ", ".join(concepts))


# ============================================================================
# 65. PRACTICAL DECISION EXAMPLE
# ============================================================================

@dataclass
class BusinessScenario:
    name: str
    sensitive_customer_data: bool
    strict_regulation: bool
    unpredictable_traffic: bool
    legacy_systems: bool
    wants_provider_independence: bool

    def recommend(self) -> List[DeploymentModel]:
        """
        Convert business requirements into architectural candidates.

        This is intentionally conservative. Real-world architecture must also
        account for contracts, geography, existing skills, technical debt,
        application architecture, budgets, and organizational risk tolerance.
        """

        candidates = deployment_model_decision_framework(
            sensitive_data=self.sensitive_customer_data,
            strict_compliance=self.strict_regulation,
            highly_variable_demand=self.unpredictable_traffic,
            existing_private_infrastructure=self.legacy_systems,
            multiple_provider_requirement=self.wants_provider_independence,
            shared_industry_requirement=False,
        )

        return [DeploymentModel(candidate) for candidate in candidates]


business_scenario = BusinessScenario(
    name="Regulated Digital Banking Platform",
    sensitive_customer_data=True,
    strict_regulation=True,
    unpredictable_traffic=True,
    legacy_systems=True,
    wants_provider_independence=True,
)

print("\nPractical business scenario:")
print(business_scenario.name)
for recommendation in business_scenario.recommend():
    print(f"- Candidate: {recommendation.value}")


# ============================================================================
# 66. IMPORTANT DISTINCTIONS
# ============================================================================

distinctions = {
    "Public vs private": (
        "Public cloud uses provider infrastructure shared among customers; "
        "private cloud is dedicated to one organization."
    ),
    "Hybrid vs multi-cloud": (
        "Hybrid focuses on integrating private and public environments; "
        "multi-cloud focuses on using multiple cloud providers."
    ),
    "Deployment vs service model": (
        "Deployment model describes infrastructure organization; service model "
        "describes the level of abstraction consumed by the customer."
    ),
    "Scalability vs elasticity": (
        "Scalability is the ability to handle increasing workload; elasticity "
        "emphasizes dynamically adapting capacity to demand."
    ),
    "Availability vs disaster recovery": (
        "Availability minimizes service interruption during normal failures; "
        "disaster recovery addresses restoration after significant disruption."
    ),
    "Backup vs replication": (
        "Backups provide recoverable historical copies; replication maintains "
        "additional copies and may support faster failover."
    ),
    "Security vs compliance": (
        "Security protects systems and data; compliance demonstrates adherence "
        "to applicable requirements. A compliant system is not automatically secure."
    ),
}

print("\nImportant distinctions:")
for topic, explanation in distinctions.items():
    print(f"\n{topic}")
    print(f"  {explanation}")


# ============================================================================
# 67. SCRIPT COMPLETION
# ============================================================================

print("\n" + "=" * 78)
print("END OF CLOUD DEPLOYMENT MODELS STUDY SCRIPT")
print("=" * 78)
