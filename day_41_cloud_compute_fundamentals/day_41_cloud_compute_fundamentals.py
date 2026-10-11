#!/usr/bin/env python3
"""Cloud compute fundamentals: instances, vCPUs, memory, instance families, and images.

Uses only the Python standard library. The examples model a small cloud capacity
planner without making real cloud API calls or creating billable resources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Iterable


class WorkloadType(str, Enum):
    WEB = "web"
    COMPUTE = "compute"
    MEMORY = "memory"
    GENERAL = "general"


class InstanceState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    TERMINATED = "terminated"


@dataclass(frozen=True)
class MachineImage:
    image_id: str
    name: str
    operating_system: str
    architecture: str
    root_disk_gib: int
    owner: str
    trusted: bool = True
    encrypted: bool = True

    def validate(self) -> None:
        if not self.image_id.strip() or not self.name.strip():
            raise ValueError("Image ID and name are required.")
        if self.architecture not in {"x86_64", "arm64"}:
            raise ValueError(f"Unsupported architecture: {self.architecture}")
        if self.root_disk_gib < 8:
            raise ValueError("Root disk must be at least 8 GiB.")
        if not self.owner.strip():
            raise ValueError("Image owner is required.")


@dataclass(frozen=True)
class InstanceType:
    name: str
    family: str
    vcpus: int
    memory_gib: float
    architecture: str
    network_gbps: float
    hourly_rate_usd: float
    workload_types: frozenset[WorkloadType]
    burstable: bool = False

    def validate(self) -> None:
        if self.vcpus <= 0 or self.memory_gib <= 0:
            raise ValueError("vCPUs and memory must be positive.")
        if self.network_gbps <= 0 or self.hourly_rate_usd < 0:
            raise ValueError("Network capacity must be positive and price nonnegative.")
        if self.architecture not in {"x86_64", "arm64"}:
            raise ValueError("Unsupported instance architecture.")
        if not self.name or not self.family:
            raise ValueError("Instance name and family are required.")

    @property
    def memory_per_vcpu(self) -> float:
        return self.memory_gib / self.vcpus


@dataclass
class CloudInstance:
    instance_id: str
    instance_type: InstanceType
    image: MachineImage
    state: InstanceState = InstanceState.STOPPED
    tags: dict[str, str] = field(default_factory=dict)

    def launch(self) -> None:
        if self.state == InstanceState.TERMINATED:
            raise RuntimeError("A terminated instance cannot be restarted.")
        self.image.validate()
        self.instance_type.validate()
        if self.image.architecture != self.instance_type.architecture:
            raise ValueError("Image architecture does not match instance architecture.")
        if not self.image.trusted:
            raise PermissionError("Untrusted machine images cannot be launched.")
        if not self.image.encrypted:
            raise PermissionError("This environment requires encrypted images.")
        self.state = InstanceState.RUNNING

    def stop(self) -> None:
        if self.state != InstanceState.RUNNING:
            raise RuntimeError("Only running instances can be stopped.")
        self.state = InstanceState.STOPPED

    def terminate(self) -> None:
        if self.state == InstanceState.TERMINATED:
            raise RuntimeError("Instance is already terminated.")
        self.state = InstanceState.TERMINATED


@dataclass(frozen=True)
class Workload:
    name: str
    workload_type: WorkloadType
    required_vcpus: int
    required_memory_gib: float
    minimum_network_gbps: float = 0.5
    architecture: str = "x86_64"
    allow_burstable: bool = False

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Workload name is required.")
        if self.required_vcpus < 1 or self.required_memory_gib <= 0:
            raise ValueError("Workload CPU and memory requirements must be positive.")
        if self.minimum_network_gbps < 0:
            raise ValueError("Network requirement cannot be negative.")
        if self.architecture not in {"x86_64", "arm64"}:
            raise ValueError("Unsupported workload architecture.")


def sample_catalog() -> list[InstanceType]:
    """Illustrative prices and capacities, not live cloud-provider quotes."""
    return [
        InstanceType(
            "general.small", "general", 2, 4, "x86_64", 1.0, 0.025,
            frozenset({WorkloadType.GENERAL, WorkloadType.WEB}),
        ),
        InstanceType(
            "general.medium", "general", 4, 16, "x86_64", 5.0, 0.080,
            frozenset({WorkloadType.GENERAL, WorkloadType.WEB}),
        ),
        InstanceType(
            "compute.large", "compute", 8, 16, "x86_64", 10.0, 0.120,
            frozenset({WorkloadType.COMPUTE, WorkloadType.GENERAL}),
        ),
        InstanceType(
            "memory.large", "memory", 4, 32, "x86_64", 10.0, 0.150,
            frozenset({WorkloadType.MEMORY, WorkloadType.GENERAL}),
        ),
        InstanceType(
            "arm.compute", "compute", 8, 16, "arm64", 10.0, 0.095,
            frozenset({WorkloadType.COMPUTE, WorkloadType.GENERAL}),
        ),
        InstanceType(
            "general.burst", "general", 2, 4, "x86_64", 1.0, 0.012,
            frozenset({WorkloadType.WEB, WorkloadType.GENERAL}),
            burstable=True,
        ),
    ]


def estimate_monthly_cost(
    hourly_rate_usd: float,
    hours_per_day: float = 24,
    days_per_month: int = 30,
    utilization: float = 1.0,
) -> float:
    """Estimate compute charges before disks, network egress, and taxes."""
    if hourly_rate_usd < 0:
        raise ValueError("Hourly rate cannot be negative.")
    if not 0 <= utilization <= 1:
        raise ValueError("Utilization must be between zero and one.")
    if not 0 <= hours_per_day <= 24 or days_per_month < 1:
        raise ValueError("Invalid billing period.")
    return hourly_rate_usd * hours_per_day * days_per_month * utilization


def recommend_instances(
    workload: Workload,
    catalog: Iterable[InstanceType],
    maximum_hourly_rate: float | None = None,
) -> list[InstanceType]:
    """Return compatible types ordered by illustrative hourly price."""
    workload.validate()
    candidates = []

    for instance_type in catalog:
        if instance_type.architecture != workload.architecture:
            continue
        if workload.workload_type not in instance_type.workload_types:
            continue
        if instance_type.vcpus < workload.required_vcpus:
            continue
        if instance_type.memory_gib < workload.required_memory_gib:
            continue
        if instance_type.network_gbps < workload.minimum_network_gbps:
            continue
        if instance_type.burstable and not workload.allow_burstable:
            continue
        if (
            maximum_hourly_rate is not None
            and instance_type.hourly_rate_usd > maximum_hourly_rate
        ):
            continue
        candidates.append(instance_type)

    return sorted(
        candidates,
        key=lambda item: (
            item.hourly_rate_usd,
            item.memory_gib,
            item.vcpus,
        ),
    )


def estimate_capacity(
    instance_type: InstanceType,
    workload_vcpus: int,
    workload_memory_gib: float,
    reserved_cpu_fraction: float = 0.10,
    reserved_memory_gib: float = 0.5,
) -> int:
    """Estimate whole workload placements using conservative usable capacity."""
    if workload_vcpus < 1 or workload_memory_gib <= 0:
        raise ValueError("Each workload must require positive CPU and memory.")
    if not 0 <= reserved_cpu_fraction < 1 or reserved_memory_gib < 0:
        raise ValueError("Invalid capacity reserve.")

    usable_vcpus = instance_type.vcpus * (1 - reserved_cpu_fraction)
    usable_memory = instance_type.memory_gib - reserved_memory_gib

    if usable_vcpus < workload_vcpus or usable_memory < workload_memory_gib:
        return 0

    return min(
        int(usable_vcpus // workload_vcpus),
        int(usable_memory // workload_memory_gib),
    )


def explain_instance(instance_type: InstanceType) -> None:
    print(f"\nInstance type: {instance_type.name}")
    print(f"  Family: {instance_type.family}")
    print(f"  Virtual CPUs: {instance_type.vcpus}")
    print(f"  Memory: {instance_type.memory_gib:g} GiB")
    print(f"  Memory per vCPU: {instance_type.memory_per_vcpu:.2f} GiB")
    print(f"  Architecture: {instance_type.architecture}")
    print(f"  Network rating: {instance_type.network_gbps:g} Gbps")
    print(f"  Burstable: {instance_type.burstable}")
    print(f"  Illustrative monthly compute cost: "
          f"${estimate_monthly_cost(instance_type.hourly_rate_usd):.2f}")


def demonstrate_lifecycle(image: MachineImage, instance_type: InstanceType) -> None:
    instance = CloudInstance("i-demo-001", instance_type, image, tags={"env": "lab"})
    print(f"\nLifecycle demonstration: {instance.instance_id}")
    print(f"Initial state: {instance.state.value}")
    instance.launch()
    print(f"After launch: {instance.state.value}")
    instance.stop()
    print(f"After stop: {instance.state.value}")
    instance.launch()
    print(f"After restart: {instance.state.value}")
    instance.terminate()
    print(f"After termination: {instance.state.value}")

    try:
        instance.launch()
    except RuntimeError as error:
        print(f"Expected lifecycle rejection: {error}")


def demonstrate_validation(image: MachineImage, instance_type: InstanceType) -> None:
    print("\nValidation demonstrations:")

    mismatched_image = MachineImage(
        "img-arm-lab", "ARM Linux", "Linux", "arm64", 20, "internal",
    )
    mismatched = CloudInstance("i-bad-arch", instance_type, mismatched_image)
    try:
        mismatched.launch()
    except ValueError as error:
        print(f"Architecture mismatch rejected: {error}")

    untrusted_image = MachineImage(
        "img-unknown", "Unknown image", "Linux", "x86_64", 20,
        "external", trusted=False,
    )
    untrusted = CloudInstance("i-untrusted", instance_type, untrusted_image)
    try:
        untrusted.launch()
    except PermissionError as error:
        print(f"Image trust policy rejected launch: {error}")

    try:
        estimate_monthly_cost(0.05, utilization=1.5)
    except ValueError as error:
        print(f"Invalid cost input rejected: {error}")


def main() -> None:
    catalog = sample_catalog()
    for instance_type in catalog:
        instance_type.validate()

    linux_image = MachineImage(
        image_id="img-linux-2026-10",
        name="Hardened Linux Base",
        operating_system="Linux",
        architecture="x86_64",
        root_disk_gib=30,
        owner="organization-image-team",
    )
    linux_image.validate()

    print("Cloud compute fundamentals")
    print("==========================")
    print("A vCPU is a provider-presented unit of virtual processor capacity.")
    print("It does not guarantee identical physical CPU performance across families.")
    print("GiB measures memory capacity; Gbps describes network throughput.")

    for instance_type in catalog:
        explain_instance(instance_type)

    workloads = [
        Workload("HTTP service", WorkloadType.WEB, 2, 3, 0.5),
        Workload("Batch renderer", WorkloadType.COMPUTE, 6, 8, 5.0),
        Workload("In-memory analytics", WorkloadType.MEMORY, 4, 24, 5.0),
        Workload(
            "ARM-compatible compiler",
            WorkloadType.COMPUTE,
            4,
            8,
            2.0,
            architecture="arm64",
        ),
    ]

    print("\nWorkload recommendations")
    for workload in workloads:
        matches = recommend_instances(workload, catalog)
        print(f"\n{workload.name}:")
        if not matches:
            print("  No compatible instance type in this catalog.")
            continue
        for match in matches:
            print(
                f"  {match.name}: {match.vcpus} vCPU, "
                f"{match.memory_gib:g} GiB, "
                f"${match.hourly_rate_usd:.3f}/hour"
            )

    compute = next(item for item in catalog if item.name == "compute.large")
    print("\nCapacity planning")
    print(f"On {compute.name}, approximate placements for a workload "
          f"requiring 2 vCPU and 3 GiB: "
          f"{estimate_capacity(compute, 2, 3)}")

    print("\nBilling examples")
    rate = compute.hourly_rate_usd
    print(f"Continuous 30-day usage: ${estimate_monthly_cost(rate):.2f}")
    print(f"Eight hours per day: "
          f"${estimate_monthly_cost(rate, hours_per_day=8):.2f}")
    print(f"Twenty-four hours per day at 50% billed runtime: "
          f"${estimate_monthly_cost(rate, utilization=0.5):.2f}")

    # A machine image describes the bootable software baseline, not CPU or RAM.
    demonstrate_lifecycle(linux_image, compute)
    demonstrate_validation(linux_image, compute)

    # Small instances can fit CPU and memory requirements but still be unsuitable
    # if they lack sustained CPU performance or adequate network bandwidth.
    print("\nPlanning caveats")
    print("- Burstable instances may depend on accumulated CPU credits.")
    print("- Actual capacity also depends on disk I/O, quotas, and regional availability.")
    print("- Production estimates must include storage, egress, licensing, and taxes.")
    print("- Image provenance, patching, encryption, and architecture require verification.")
    print("- Real cloud APIs must confirm current instance specifications and pricing.")


if __name__ == "__main__":
    main()
