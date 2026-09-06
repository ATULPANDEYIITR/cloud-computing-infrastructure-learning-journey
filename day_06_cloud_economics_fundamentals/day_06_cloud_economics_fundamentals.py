"""
Cloud Economics Fundamentals
============================

A self-contained educational study script covering:

- Cloud economics fundamentals
- CAPEX vs OPEX
- Pay-as-you-go and consumption pricing
- Fixed, tiered, volume, and commitment pricing
- Compute, storage, database, network, and licensing cost models
- Total Cost of Ownership (TCO)
- Infrastructure budgeting
- Cost allocation, tagging, showback, and chargeback
- Unit economics and FinOps concepts
- Cloud Pricing Calculator concepts and implementation
- Scenario modeling and sensitivity analysis
- Break-even analysis
- Reserved/committed capacity economics
- Autoscaling economics
- Data-transfer economics
- Idle-resource economics
- Cost optimization trade-offs
- Forecasting, budgets, alerts, and variance analysis
- Production-oriented cost controls
- Security and governance considerations
- Testing and validation of pricing calculations

The examples use fictional prices so that the script remains provider-neutral.
Real cloud prices vary by provider, region, service configuration, currency,
contract, discounts, taxes, and date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from math import ceil
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import statistics
import unittest


# ---------------------------------------------------------------------------
# 1. BASIC NUMERIC UTILITIES
# ---------------------------------------------------------------------------

MONEY_QUANTUM = Decimal("0.01")


def money(value: Decimal | float | int | str) -> Decimal:
    """Convert a numeric value into a currency amount rounded to cents."""
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def percent(value: Decimal | float | int | str) -> Decimal:
    """Represent a percentage as a Decimal without converting it to a fraction."""
    return Decimal(str(value))


def percentage_of(amount: Decimal, percentage: Decimal) -> Decimal:
    """Calculate a percentage of an amount."""
    return amount * percentage / Decimal("100")


def annualize_monthly(monthly_cost: Decimal) -> Decimal:
    """Convert a monthly cost into a simple 12-month annual estimate."""
    return money(monthly_cost * Decimal("12"))


def monthly_from_annual(annual_cost: Decimal) -> Decimal:
    """Convert an annual cost into a monthly equivalent."""
    return money(annual_cost / Decimal("12"))


# ---------------------------------------------------------------------------
# 2. CORE ECONOMIC TERMINOLOGY
# ---------------------------------------------------------------------------

class CostType(Enum):
    CAPEX = "CAPEX"
    OPEX = "OPEX"


class PricingModel(Enum):
    PAY_AS_YOU_GO = "Pay-as-you-go"
    FIXED = "Fixed"
    TIERED = "Tiered"
    VOLUME = "Volume"
    COMMITTED = "Committed"
    RESERVED = "Reserved"
    SPOT = "Spot"
    LICENSE = "License"


class AllocationMethod(Enum):
    EQUAL = "Equal"
    USAGE = "Usage"
    REVENUE = "Revenue"
    HEADCOUNT = "Headcount"
    TAGGED = "Tagged"


def explain_basic_terms() -> None:
    """
    Print fundamental cloud-economics concepts.

    CAPEX:
        Capital expenditure, usually involving upfront investment in assets
        expected to provide value over multiple accounting periods.

    OPEX:
        Operating expenditure incurred while operating the business.

    Cloud services commonly shift infrastructure economics toward OPEX because
    organizations can consume infrastructure without buying the physical
    infrastructure themselves.

    The accounting treatment of a specific cloud contract can be more nuanced
    than the simplified CAPEX/OPEX distinction used here.
    """
    terms = {
        "CAPEX": "Upfront capital investment in long-lived assets.",
        "OPEX": "Operating expenditure incurred to run services.",
        "Pay-as-you-go": "Pay according to measured consumption.",
        "Consumption pricing": "Cost changes as resource usage changes.",
        "TCO": "Total cost of ownership over a defined period.",
        "Unit economics": "Cost and value expressed per useful business unit.",
        "FinOps": "Operational discipline for maximizing business value from cloud spend.",
        "Showback": "Reporting cloud costs to teams without necessarily charging budgets.",
        "Chargeback": "Assigning cloud costs to teams or business units for accountability.",
    }

    for term, definition in terms.items():
        print(f"{term:20} {definition}")


# ---------------------------------------------------------------------------
# 3. CAPEX VS OPEX MODEL
# ---------------------------------------------------------------------------

@dataclass
class CapitalInvestment:
    """Model a simplified on-premises infrastructure investment."""

    hardware_cost: Decimal
    installation_cost: Decimal = Decimal("0")
    initial_software_cost: Decimal = Decimal("0")
    useful_life_years: int = 3

    @property
    def initial_capex(self) -> Decimal:
        return money(
            self.hardware_cost
            + self.installation_cost
            + self.initial_software_cost
        )

    @property
    def annualized_capex(self) -> Decimal:
        if self.useful_life_years <= 0:
            raise ValueError("Useful life must be positive.")
        return money(self.initial_capex / Decimal(self.useful_life_years))


@dataclass
class OperatingInfrastructure:
    """Model recurring infrastructure operating expenses."""

    monthly_compute: Decimal
    monthly_storage: Decimal
    monthly_network: Decimal
    monthly_support: Decimal = Decimal("0")
    monthly_operations_staff: Decimal = Decimal("0")
    monthly_other: Decimal = Decimal("0")

    @property
    def monthly_opex(self) -> Decimal:
        return money(
            self.monthly_compute
            + self.monthly_storage
            + self.monthly_network
            + self.monthly_support
            + self.monthly_operations_staff
            + self.monthly_other
        )

    @property
    def annual_opex(self) -> Decimal:
        return annualize_monthly(self.monthly_opex)


def compare_capex_and_opex() -> None:
    on_prem = CapitalInvestment(
        hardware_cost=Decimal("120000"),
        installation_cost=Decimal("10000"),
        initial_software_cost=Decimal("20000"),
        useful_life_years=4,
    )

    cloud = OperatingInfrastructure(
        monthly_compute=Decimal("4500"),
        monthly_storage=Decimal("900"),
        monthly_network=Decimal("700"),
        monthly_support=Decimal("500"),
        monthly_operations_staff=Decimal("2000"),
    )

    print("\nCAPEX vs OPEX example")
    print("-" * 50)
    print(f"Initial on-prem CAPEX: {on_prem.initial_capex}")
    print(f"Annualized CAPEX:      {on_prem.annualized_capex}")
    print(f"Monthly cloud OPEX:    {cloud.monthly_opex}")
    print(f"Annual cloud OPEX:     {cloud.annual_opex}")

    print("\nEconomic distinction:")
    print("CAPEX is primarily associated with acquiring long-lived assets.")
    print("OPEX is primarily associated with recurring operating consumption.")
    print("Cloud adoption often changes the timing, flexibility, and risk profile")
    print("of infrastructure spending rather than simply making infrastructure cheaper.")


# ---------------------------------------------------------------------------
# 4. CONSUMPTION-BASED PRICING
# ---------------------------------------------------------------------------

@dataclass
class ConsumptionRate:
    """Simple unit price for a measurable resource."""

    resource: str
    unit: str
    price_per_unit: Decimal

    def calculate(self, quantity: Decimal | float | int) -> Decimal:
        if quantity < 0:
            raise ValueError("Quantity cannot be negative.")
        return money(Decimal(str(quantity)) * self.price_per_unit)


def pay_as_you_go_example() -> None:
    compute = ConsumptionRate(
        resource="Compute",
        unit="instance-hour",
        price_per_unit=Decimal("0.12"),
    )

    storage = ConsumptionRate(
        resource="Object storage",
        unit="GB-month",
        price_per_unit=Decimal("0.023"),
    )

    network = ConsumptionRate(
        resource="Data transfer",
        unit="GB",
        price_per_unit=Decimal("0.09"),
    )

    compute_cost = compute.calculate(720)
    storage_cost = storage.calculate(500)
    network_cost = network.calculate(250)

    print("\nPay-as-you-go calculation")
    print("-" * 50)
    print(f"Compute:  {compute_cost}")
    print(f"Storage:  {storage_cost}")
    print(f"Network:  {network_cost}")
    print(f"Total:    {money(compute_cost + storage_cost + network_cost)}")


# ---------------------------------------------------------------------------
# 5. PRICING MODELS
# ---------------------------------------------------------------------------

@dataclass
class FixedPrice:
    """A fixed recurring charge."""

    monthly_price: Decimal

    def cost(self, months: int) -> Decimal:
        if months < 0:
            raise ValueError("Months cannot be negative.")
        return money(self.monthly_price * Decimal(months))


@dataclass
class Tier:
    """A pricing tier.

    upper_bound is inclusive. None means unlimited.
    """

    upper_bound: Optional[Decimal]
    price_per_unit: Decimal


@dataclass
class TieredPrice:
    """
    Progressive tier pricing.

    Example:
        First 100 units: $0.10
        Next 400 units: $0.08
        Above 500:       $0.05

    This is different from volume pricing, where all units may receive the
    price corresponding to the achieved volume.
    """

    tiers: Sequence[Tier]

    def cost(self, quantity: Decimal) -> Decimal:
        if quantity < 0:
            raise ValueError("Quantity cannot be negative.")

        remaining = quantity
        previous_bound = Decimal("0")
        total = Decimal("0")

        for tier in self.tiers:
            if remaining <= 0:
                break

            if tier.upper_bound is None:
                units_in_tier = remaining
            else:
                tier_capacity = tier.upper_bound - previous_bound
                units_in_tier = min(remaining, tier_capacity)

            total += units_in_tier * tier.price_per_unit
            remaining -= units_in_tier

            if tier.upper_bound is not None:
                previous_bound = tier.upper_bound

        if remaining > 0:
            raise ValueError("Pricing tiers do not cover the supplied quantity.")

        return money(total)


@dataclass
class VolumePrice:
    """
    All-unit volume pricing.

    Once a volume threshold is reached, all units can receive the associated
    rate. Real providers may use more complicated rules.
    """

    thresholds: Sequence[Tuple[Decimal, Decimal]]

    def cost(self, quantity: Decimal) -> Decimal:
        if quantity < 0:
            raise ValueError("Quantity cannot be negative.")

        applicable_rate: Optional[Decimal] = None

        for threshold, rate in sorted(self.thresholds):
            if quantity >= threshold:
                applicable_rate = rate
            else:
                break

        if applicable_rate is None:
            raise ValueError("No pricing threshold covers this quantity.")

        return money(quantity * applicable_rate)


def pricing_model_comparison() -> None:
    quantity = Decimal("750")

    progressive = TieredPrice(
        tiers=[
            Tier(Decimal("100"), Decimal("0.10")),
            Tier(Decimal("500"), Decimal("0.08")),
            Tier(None, Decimal("0.05")),
        ]
    )

    volume = VolumePrice(
        thresholds=[
            (Decimal("1"), Decimal("0.10")),
            (Decimal("500"), Decimal("0.08")),
            (Decimal("1000"), Decimal("0.05")),
        ]
    )

    print("\nTiered vs volume pricing")
    print("-" * 50)
    print(f"Quantity: {quantity}")
    print(f"Progressive tier cost: {progressive.cost(quantity)}")
    print(f"Volume cost:            {volume.cost(quantity)}")

    print("\nImportant distinction:")
    print("Progressive pricing charges each usage segment at its own rate.")
    print("Volume pricing can apply one achieved-volume rate to all units.")


# ---------------------------------------------------------------------------
# 6. CLOUD RESOURCE COST COMPONENTS
# ---------------------------------------------------------------------------

@dataclass
class ComputeResource:
    name: str
    hourly_rate: Decimal
    hours_per_month: Decimal
    count: int = 1

    def monthly_cost(self) -> Decimal:
        if self.count < 0 or self.hours_per_month < 0:
            raise ValueError("Count and hours must be non-negative.")
        return money(
            self.hourly_rate
            * self.hours_per_month
            * Decimal(self.count)
        )


@dataclass
class StorageResource:
    name: str
    gb_months: Decimal
    price_per_gb_month: Decimal

    def monthly_cost(self) -> Decimal:
        if self.gb_months < 0:
            raise ValueError("Storage quantity cannot be negative.")
        return money(self.gb_months * self.price_per_gb_month)


@dataclass
class NetworkResource:
    name: str
    gb_transferred: Decimal
    price_per_gb: Decimal

    def monthly_cost(self) -> Decimal:
        if self.gb_transferred < 0:
            raise ValueError("Network usage cannot be negative.")
        return money(self.gb_transferred * self.price_per_gb)


@dataclass
class DatabaseResource:
    name: str
    compute_hours: Decimal
    compute_price_per_hour: Decimal
    storage_gb: Decimal
    storage_price_per_gb_month: Decimal
    backup_gb: Decimal = Decimal("0")
    backup_price_per_gb_month: Decimal = Decimal("0")

    def monthly_cost(self) -> Decimal:
        if min(
            self.compute_hours,
            self.compute_price_per_hour,
            self.storage_gb,
            self.storage_price_per_gb_month,
            self.backup_gb,
            self.backup_price_per_gb_month,
        ) < 0:
            raise ValueError("Database quantities and rates cannot be negative.")

        return money(
            self.compute_hours * self.compute_price_per_hour
            + self.storage_gb * self.storage_price_per_gb_month
            + self.backup_gb * self.backup_price_per_gb_month
        )


@dataclass
class CloudWorkload:
    name: str
    compute: List[ComputeResource] = field(default_factory=list)
    storage: List[StorageResource] = field(default_factory=list)
    network: List[NetworkResource] = field(default_factory=list)
    databases: List[DatabaseResource] = field(default_factory=list)
    other_monthly_costs: Decimal = Decimal("0")

    def monthly_cost_breakdown(self) -> Dict[str, Decimal]:
        return {
            "compute": money(sum(
                resource.monthly_cost() for resource in self.compute
            )),
            "storage": money(sum(
                resource.monthly_cost() for resource in self.storage
            )),
            "network": money(sum(
                resource.monthly_cost() for resource in self.network
            )),
            "database": money(sum(
                resource.monthly_cost() for resource in self.databases
            )),
            "other": money(self.other_monthly_costs),
        }

    def monthly_cost(self) -> Decimal:
        return money(sum(self.monthly_cost_breakdown().values()))

    def annual_cost(self) -> Decimal:
        return annualize_monthly(self.monthly_cost())


def build_example_workload() -> CloudWorkload:
    return CloudWorkload(
        name="E-commerce platform",
        compute=[
            ComputeResource(
                name="Application servers",
                hourly_rate=Decimal("0.12"),
                hours_per_month=Decimal("720"),
                count=4,
            ),
            ComputeResource(
                name="Background workers",
                hourly_rate=Decimal("0.09"),
                hours_per_month=Decimal("300"),
                count=3,
            ),
        ],
        storage=[
            StorageResource(
                name="Object storage",
                gb_months=Decimal("2000"),
                price_per_gb_month=Decimal("0.023"),
            ),
        ],
        network=[
            NetworkResource(
                name="Internet egress",
                gb_transferred=Decimal("5000"),
                price_per_gb=Decimal("0.09"),
            ),
        ],
        databases=[
            DatabaseResource(
                name="Primary database",
                compute_hours=Decimal("720"),
                compute_price_per_hour=Decimal("0.30"),
                storage_gb=Decimal("1000"),
                storage_price_per_gb_month=Decimal("0.10"),
                backup_gb=Decimal("500"),
                backup_price_per_gb_month=Decimal("0.02"),
            )
        ],
        other_monthly_costs=Decimal("300"),
    )


def demonstrate_workload_costs() -> None:
    workload = build_example_workload()

    print("\nCloud workload cost model")
    print("-" * 50)

    breakdown = workload.monthly_cost_breakdown()
    for category, cost in breakdown.items():
        print(f"{category.title():12}: {cost}")

    print(f"Monthly total: {workload.monthly_cost()}")
    print(f"Annual total:  {workload.annual_cost()}")


# ---------------------------------------------------------------------------
# 7. TOTAL COST OF OWNERSHIP
# ---------------------------------------------------------------------------

@dataclass
class TCOModel:
    """
    Compare all relevant costs over a defined period.

    TCO should not be reduced to the provider invoice. Depending on the
    decision, it can include migration, operations, support, security,
    licensing, networking, training, downtime, and exit costs.
    """

    period_months: int
    infrastructure_cost: Decimal
    operations_cost: Decimal
    support_cost: Decimal
    security_cost: Decimal
    migration_cost: Decimal = Decimal("0")
    licensing_cost: Decimal = Decimal("0")
    other_costs: Decimal = Decimal("0")
    residual_value: Decimal = Decimal("0")

    def total(self) -> Decimal:
        if self.period_months < 0:
            raise ValueError("Period cannot be negative.")

        total = (
            self.infrastructure_cost
            + self.operations_cost
            + self.support_cost
            + self.security_cost
            + self.migration_cost
            + self.licensing_cost
            + self.other_costs
            - self.residual_value
        )

        return money(total)

    def monthly_equivalent(self) -> Decimal:
        if self.period_months == 0:
            raise ValueError("Period must be greater than zero.")
        return money(self.total() / Decimal(self.period_months))


def tco_example() -> None:
    cloud_monthly_invoice = Decimal("9000")
    months = 36

    model = TCOModel(
        period_months=months,
        infrastructure_cost=cloud_monthly_invoice * months,
        operations_cost=Decimal("1500") * months,
        support_cost=Decimal("600") * months,
        security_cost=Decimal("500") * months,
        migration_cost=Decimal("25000"),
        licensing_cost=Decimal("10000"),
        other_costs=Decimal("5000"),
    )

    print("\nThree-year TCO example")
    print("-" * 50)
    print(f"TCO:              {model.total()}")
    print(f"Monthly equivalent: {model.monthly_equivalent()}")


# ---------------------------------------------------------------------------
# 8. ON-PREMISES VS CLOUD TCO
# ---------------------------------------------------------------------------

@dataclass
class InfrastructureScenario:
    name: str
    tco: TCOModel

    def total_cost(self) -> Decimal:
        return self.tco.total()


def compare_scenarios() -> None:
    months = 36

    on_prem = InfrastructureScenario(
        name="On-premises",
        tco=TCOModel(
            period_months=months,
            infrastructure_cost=Decimal("160000"),
            operations_cost=Decimal("3500") * months,
            support_cost=Decimal("1000") * months,
            security_cost=Decimal("700") * months,
            licensing_cost=Decimal("25000"),
        ),
    )

    cloud = InfrastructureScenario(
        name="Cloud",
        tco=TCOModel(
            period_months=months,
            infrastructure_cost=Decimal("8500") * months,
            operations_cost=Decimal("1600") * months,
            support_cost=Decimal("700") * months,
            security_cost=Decimal("600") * months,
            migration_cost=Decimal("25000"),
            licensing_cost=Decimal("15000"),
        ),
    )

    print("\nTCO comparison")
    print("-" * 50)
    print(f"{on_prem.name:15}: {on_prem.total_cost()}")
    print(f"{cloud.name:15}: {cloud.total_cost()}")

    difference = money(on_prem.total_cost() - cloud.total_cost())
    print(f"Difference:       {difference}")


# ---------------------------------------------------------------------------
# 9. COST PER BUSINESS UNIT
# ---------------------------------------------------------------------------

@dataclass
class UnitEconomics:
    """Calculate infrastructure cost per business unit."""

    total_cost: Decimal
    units: Decimal
    unit_name: str

    def cost_per_unit(self) -> Decimal:
        if self.units <= 0:
            raise ValueError("Business units must be greater than zero.")
        return money(self.total_cost / self.units)


def unit_economics_example() -> None:
    monthly_cloud_cost = Decimal("25000")
    monthly_orders = Decimal("500000")

    economics = UnitEconomics(
        total_cost=monthly_cloud_cost,
        units=monthly_orders,
        unit_name="order",
    )

    print("\nUnit economics")
    print("-" * 50)
    print(
        f"Cloud infrastructure cost per {economics.unit_name}: "
        f"{economics.cost_per_unit()}"
    )


# ---------------------------------------------------------------------------
# 10. UTILIZATION AND IDLE RESOURCE ECONOMICS
# ---------------------------------------------------------------------------

def utilization_cost(
    provisioned_hours: Decimal,
    used_hours: Decimal,
    hourly_rate: Decimal,
) -> Dict[str, Decimal]:
    if provisioned_hours <= 0:
        raise ValueError("Provisioned hours must be positive.")
    if used_hours < 0 or used_hours > provisioned_hours:
        raise ValueError("Used hours must be between 0 and provisioned hours.")
    if hourly_rate < 0:
        raise ValueError("Hourly rate cannot be negative.")

    total_cost = money(provisioned_hours * hourly_rate)
    productive_cost = money(used_hours * hourly_rate)
    idle_cost = money(total_cost - productive_cost)
    utilization = used_hours / provisioned_hours * Decimal("100")

    return {
        "utilization_percent": utilization,
        "total_cost": total_cost,
        "productive_cost": productive_cost,
        "idle_cost": idle_cost,
    }


def idle_resource_example() -> None:
    result = utilization_cost(
        provisioned_hours=Decimal("720"),
        used_hours=Decimal("300"),
        hourly_rate=Decimal("0.25"),
    )

    print("\nIdle resource economics")
    print("-" * 50)
    for key, value in result.items():
        print(f"{key:20}: {value}")


# ---------------------------------------------------------------------------
# 11. AUTOSCALING ECONOMICS
# ---------------------------------------------------------------------------

@dataclass
class TrafficPeriod:
    name: str
    hours: Decimal
    required_instances: int


def autoscaling_cost(
    periods: Sequence[TrafficPeriod],
    hourly_rate: Decimal,
    minimum_instances: int = 0,
) -> Decimal:
    """
    Calculate compute cost when instance count changes by traffic period.

    minimum_instances represents capacity that remains running regardless
    of demand.
    """
    if hourly_rate < 0:
        raise ValueError("Hourly rate cannot be negative.")
    if minimum_instances < 0:
        raise ValueError("Minimum instances cannot be negative.")

    total = Decimal("0")

    for period in periods:
        if period.hours < 0 or period.required_instances < 0:
            raise ValueError("Traffic period values cannot be negative.")

        instances = max(minimum_instances, period.required_instances)
        total += period.hours * Decimal(instances) * hourly_rate

    return money(total)


def autoscaling_example() -> None:
    periods = [
        TrafficPeriod("Night", Decimal("10"), 1),
        TrafficPeriod("Business", Decimal("8"), 5),
        TrafficPeriod("Evening", Decimal("6"), 3),
    ]

    fixed_cost = money(
        Decimal("24")
        * Decimal("5")
        * Decimal("0.12")
    )

    scaled_cost = autoscaling_cost(
        periods,
        hourly_rate=Decimal("0.12"),
        minimum_instances=1,
    )

    print("\nAutoscaling economics")
    print("-" * 50)
    print(f"Fixed capacity cost: {fixed_cost}")
    print(f"Scaled capacity cost: {scaled_cost}")
    print(f"Savings: {money(fixed_cost - scaled_cost)}")


# ---------------------------------------------------------------------------
# 12. COMMITTED USE / RESERVED CAPACITY
# ---------------------------------------------------------------------------

@dataclass
class CommitmentOption:
    name: str
    commitment_months: int
    effective_hourly_rate: Decimal
    upfront_cost: Decimal = Decimal("0")

    def total_cost(self, usage_hours: Decimal) -> Decimal:
        if self.commitment_months <= 0:
            raise ValueError("Commitment period must be positive.")
        if usage_hours < 0:
            raise ValueError("Usage hours cannot be negative.")

        return money(
            self.upfront_cost
            + usage_hours * self.effective_hourly_rate
        )


def commitment_break_even_hours(
    on_demand_rate: Decimal,
    committed_rate: Decimal,
    upfront_cost: Decimal,
) -> Decimal:
    """
    Solve:

        on_demand_rate * hours =
        upfront_cost + committed_rate * hours

    Therefore:

        hours = upfront_cost / (on_demand_rate - committed_rate)
    """
    savings_per_hour = on_demand_rate - committed_rate

    if savings_per_hour <= 0:
        raise ValueError(
            "The committed rate must be lower than the on-demand rate."
        )

    if upfront_cost < 0:
        raise ValueError("Upfront cost cannot be negative.")

    return upfront_cost / savings_per_hour


def commitment_example() -> None:
    on_demand = Decimal("0.20")
    committed = Decimal("0.12")
    upfront = Decimal("500")

    hours = commitment_break_even_hours(
        on_demand_rate=on_demand,
        committed_rate=committed,
        upfront_cost=upfront,
    )

    print("\nCommitment break-even")
    print("-" * 50)
    print(f"Break-even usage hours: {hours.quantize(Decimal('0.1'))}")

    usage = Decimal("7000")
    on_demand_cost = money(usage * on_demand)
    committed_cost = money(upfront + usage * committed)

    print(f"On-demand cost:         {on_demand_cost}")
    print(f"Committed cost:         {committed_cost}")
    print(f"Savings:                {money(on_demand_cost - committed_cost)}")


# ---------------------------------------------------------------------------
# 13. SPOT / INTERRUPTIBLE CAPACITY ECONOMICS
# ---------------------------------------------------------------------------

@dataclass
class SpotScenario:
    on_demand_rate: Decimal
    spot_rate: Decimal
    expected_usage_hours: Decimal
    interruption_fraction: Decimal

    def expected_cost(self) -> Decimal:
        if not 0 <= self.interruption_fraction <= 1:
            raise ValueError("Interruption fraction must be between 0 and 1.")

        effective_hours = (
            self.expected_usage_hours
            * (Decimal("1") - self.interruption_fraction)
        )

        return money(effective_hours * self.spot_rate)


def spot_example() -> None:
    scenario = SpotScenario(
        on_demand_rate=Decimal("0.30"),
        spot_rate=Decimal("0.09"),
        expected_usage_hours=Decimal("1000"),
        interruption_fraction=Decimal("0.10"),
    )

    on_demand_cost = money(
        scenario.on_demand_rate * scenario.expected_usage_hours
    )

    print("\nInterruptible capacity economics")
    print("-" * 50)
    print(f"Expected spot cost: {scenario.expected_cost()}")
    print(f"On-demand cost:     {on_demand_cost}")
    print(f"Nominal savings:    {money(on_demand_cost - scenario.expected_cost())}")
    print(
        "This simplified model does not price restart, checkpointing, "
        "failure recovery, or lost business value."
    )


# ---------------------------------------------------------------------------
# 14. DATA TRANSFER ECONOMICS
# ---------------------------------------------------------------------------

@dataclass
class NetworkCostModel:
    internet_egress_gb: Decimal
    inter_region_gb: Decimal
    inter_zone_gb: Decimal
    internet_price: Decimal
    inter_region_price: Decimal
    inter_zone_price: Decimal

    def monthly_cost(self) -> Decimal:
        values = [
            self.internet_egress_gb,
            self.inter_region_gb,
            self.inter_zone_gb,
            self.internet_price,
            self.inter_region_price,
            self.inter_zone_price,
        ]

        if any(value < 0 for value in values):
            raise ValueError("Network quantities and rates cannot be negative.")

        return money(
            self.internet_egress_gb * self.internet_price
            + self.inter_region_gb * self.inter_region_price
            + self.inter_zone_gb * self.inter_zone_price
        )


def network_example() -> None:
    model = NetworkCostModel(
        internet_egress_gb=Decimal("10000"),
        inter_region_gb=Decimal("3000"),
        inter_zone_gb=Decimal("5000"),
        internet_price=Decimal("0.09"),
        inter_region_price=Decimal("0.02"),
        inter_zone_price=Decimal("0.01"),
    )

    print("\nNetwork economics")
    print("-" * 50)
    print(f"Monthly network cost: {model.monthly_cost()}")
    print(
        "Architecture can influence network cost. Data placement, "
        "replication, caching, service topology, and cross-region traffic "
        "can materially change consumption."
    )


# ---------------------------------------------------------------------------
# 15. CLOUD PRICING CALCULATOR
# ---------------------------------------------------------------------------

@dataclass
class PricingLineItem:
    """
    A calculator line item.

    quantity:
        Number of billable units.

    unit:
        Human-readable billing unit.

    unit_price:
        Price per billing unit.

    fixed_cost:
        Optional fixed amount associated with the line item.
    """

    name: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    fixed_cost: Decimal = Decimal("0")

    def cost(self) -> Decimal:
        if self.quantity < 0:
            raise ValueError(f"Negative quantity for {self.name}.")
        if self.unit_price < 0:
            raise ValueError(f"Negative price for {self.name}.")
        if self.fixed_cost < 0:
            raise ValueError(f"Negative fixed cost for {self.name}.")

        return money(
            self.fixed_cost + self.quantity * self.unit_price
        )


class CloudPricingCalculator:
    """
    Provider-neutral pricing calculator.

    Real cloud calculators can have many dimensions:
    region, instance type, operating system, tenancy, storage class,
    requests, throughput, database engines, discounts, licenses,
    support plans, taxes, and contractual commitments.

    This implementation intentionally models the core economic mechanism
    without pretending to reproduce a specific provider's pricing catalog.
    """

    def __init__(self, currency: str = "USD") -> None:
        self.currency = currency
        self._line_items: List[PricingLineItem] = []

    def add(self, line_item: PricingLineItem) -> None:
        self._line_items.append(line_item)

    def subtotal(self) -> Decimal:
        return money(sum(item.cost() for item in self._line_items))

    def discount(self, percentage_rate: Decimal) -> Decimal:
        if not 0 <= percentage_rate <= 100:
            raise ValueError("Discount must be between 0 and 100 percent.")
        return money(percentage_of(self.subtotal(), percentage_rate))

    def total(
        self,
        discount_rate: Decimal = Decimal("0"),
        tax_rate: Decimal = Decimal("0"),
    ) -> Decimal:
        if not 0 <= discount_rate <= 100:
            raise ValueError("Discount must be between 0 and 100 percent.")
        if not 0 <= tax_rate <= 100:
            raise ValueError("Tax must be between 0 and 100 percent.")

        subtotal = self.subtotal()
        discount = percentage_of(subtotal, discount_rate)
        taxable_amount = subtotal - discount
        tax = percentage_of(taxable_amount, tax_rate)

        return money(taxable_amount + tax)

    def report(
        self,
        discount_rate: Decimal = Decimal("0"),
        tax_rate: Decimal = Decimal("0"),
    ) -> str:
        lines = [
            f"Cloud Pricing Calculator ({self.currency})",
            "-" * 60,
        ]

        for item in self._line_items:
            lines.append(
                f"{item.name:30} "
                f"{item.quantity} {item.unit} × "
                f"{item.unit_price} = {item.cost()}"
            )

        subtotal = self.subtotal()
        discount = self.discount(discount_rate)
        total = self.total(discount_rate, tax_rate)

        lines.extend([
            "-" * 60,
            f"{'Subtotal':30} {subtotal}",
            f"{'Discount':30} -{discount}",
            f"{'Tax':30} {money(percentage_of(subtotal - discount, tax_rate))}",
            f"{'Total':30} {total}",
        ])

        return "\n".join(lines)


def pricing_calculator_example() -> None:
    calculator = CloudPricingCalculator(currency="USD")

    calculator.add(
        PricingLineItem(
            name="Compute instances",
            quantity=Decimal("2880"),
            unit="instance-hours",
            unit_price=Decimal("0.12"),
        )
    )

    calculator.add(
        PricingLineItem(
            name="Object storage",
            quantity=Decimal("3000"),
            unit="GB-month",
            unit_price=Decimal("0.023"),
        )
    )

    calculator.add(
        PricingLineItem(
            name="Network egress",
            quantity=Decimal("4000"),
            unit="GB",
            unit_price=Decimal("0.09"),
        )
    )

    calculator.add(
        PricingLineItem(
            name="Support plan",
            quantity=Decimal("1"),
            unit="month",
            unit_price=Decimal("500"),
        )
    )

    print("\nCloud pricing calculator")
    print("-" * 50)
    print(calculator.report(
        discount_rate=Decimal("10"),
        tax_rate=Decimal("5"),
    ))


# ---------------------------------------------------------------------------
# 16. MONTHLY BUDGETING
# ---------------------------------------------------------------------------

@dataclass
class Budget:
    name: str
    monthly_limit: Decimal
    warning_threshold_percent: Decimal = Decimal("80")
    critical_threshold_percent: Decimal = Decimal("100")

    def utilization(self, actual_spend: Decimal) -> Decimal:
        if self.monthly_limit <= 0:
            raise ValueError("Budget must be greater than zero.")
        if actual_spend < 0:
            raise ValueError("Actual spend cannot be negative.")

        return actual_spend / self.monthly_limit * Decimal("100")

    def status(self, actual_spend: Decimal) -> str:
        utilization = self.utilization(actual_spend)

        if utilization >= self.critical_threshold_percent:
            return "CRITICAL"
        if utilization >= self.warning_threshold_percent:
            return "WARNING"
        return "NORMAL"

    def variance(self, actual_spend: Decimal) -> Decimal:
        return money(actual_spend - self.monthly_limit)


def budget_example() -> None:
    budget = Budget(
        name="Engineering",
        monthly_limit=Decimal("30000"),
        warning_threshold_percent=Decimal("80"),
        critical_threshold_percent=Decimal("100"),
    )

    actual = Decimal("26750")

    print("\nBudget management")
    print("-" * 50)
    print(f"Budget:       {budget.monthly_limit}")
    print(f"Actual:       {actual}")
    print(f"Utilization:  {budget.utilization(actual):.2f}%")
    print(f"Status:       {budget.status(actual)}")
    print(f"Variance:     {budget.variance(actual)}")


# ---------------------------------------------------------------------------
# 17. FORECASTING
# ---------------------------------------------------------------------------

def simple_run_rate_forecast(
    month_to_date_spend: Decimal,
    elapsed_days: int,
    days_in_month: int,
) -> Decimal:
    """
    Annual or monthly budget forecasting often begins with a run-rate model.

    This assumes current spending pace continues through the remainder of
    the period. It is simple and useful, but it does not understand seasonality,
    growth, planned deployments, one-time charges, or future commitments.
    """
    if month_to_date_spend < 0:
        raise ValueError("Spend cannot be negative.")
    if elapsed_days <= 0:
        raise ValueError("Elapsed days must be positive.")
    if days_in_month <= 0:
        raise ValueError("Days in month must be positive.")
    if elapsed_days > days_in_month:
        raise ValueError("Elapsed days cannot exceed days in month.")

    return money(
        month_to_date_spend
        / Decimal(elapsed_days)
        * Decimal(days_in_month)
    )


def forecasting_example() -> None:
    forecast = simple_run_rate_forecast(
        month_to_date_spend=Decimal("12000"),
        elapsed_days=10,
        days_in_month=30,
    )

    print("\nRun-rate forecast")
    print("-" * 50)
    print(f"Forecasted monthly spend: {forecast}")


# ---------------------------------------------------------------------------
# 18. VARIANCE ANALYSIS
# ---------------------------------------------------------------------------

@dataclass
class CostVariance:
    budget: Decimal
    actual: Decimal

    @property
    def absolute_variance(self) -> Decimal:
        return money(self.actual - self.budget)

    @property
    def variance_percent(self) -> Decimal:
        if self.budget == 0:
            if self.actual == 0:
                return Decimal("0")
            return Decimal("Infinity")

        return (
            (self.actual - self.budget)
            / self.budget
            * Decimal("100")
        )


def variance_example() -> None:
    variance = CostVariance(
        budget=Decimal("20000"),
        actual=Decimal("23500"),
    )

    print("\nCost variance")
    print("-" * 50)
    print(f"Absolute variance: {variance.absolute_variance}")
    print(f"Variance percent:   {variance.variance_percent:.2f}%")


# ---------------------------------------------------------------------------
# 19. COST ALLOCATION
# ---------------------------------------------------------------------------

@dataclass
class Team:
    name: str
    allocation_weight: Decimal


def allocate_cost(
    total_cost: Decimal,
    teams: Sequence[Team],
) -> Dict[str, Decimal]:
    if total_cost < 0:
        raise ValueError("Total cost cannot be negative.")

    if not teams:
        raise ValueError("At least one team is required.")

    total_weight = sum(team.allocation_weight for team in teams)

    if total_weight <= 0:
        raise ValueError("Total allocation weight must be positive.")

    if any(team.allocation_weight < 0 for team in teams):
        raise ValueError("Allocation weights cannot be negative.")

    allocation: Dict[str, Decimal] = {}

    for team in teams:
        allocation[team.name] = money(
            total_cost
            * team.allocation_weight
            / total_weight
        )

    return allocation


def allocation_example() -> None:
    teams = [
        Team("Payments", Decimal("50")),
        Team("Catalog", Decimal("30")),
        Team("Analytics", Decimal("20")),
    ]

    allocation = allocate_cost(
        total_cost=Decimal("10000"),
        teams=teams,
    )

    print("\nCost allocation")
    print("-" * 50)

    for team, cost in allocation.items():
        print(f"{team:15}: {cost}")


# ---------------------------------------------------------------------------
# 20. TAGGING AND COST CATEGORIZATION
# ---------------------------------------------------------------------------

@dataclass
class CloudResource:
    name: str
    monthly_cost: Decimal
    tags: Mapping[str, str]


def group_costs_by_tag(
    resources: Iterable[CloudResource],
    tag_name: str,
) -> Dict[str, Decimal]:
    result: Dict[str, Decimal] = {}

    for resource in resources:
        value = resource.tags.get(tag_name, "untagged")
        result[value] = result.get(value, Decimal("0")) + resource.monthly_cost

    return {
        key: money(value)
        for key, value in result.items()
    }


def tagging_example() -> None:
    resources = [
        CloudResource(
            name="payments-api",
            monthly_cost=Decimal("4000"),
            tags={"environment": "production", "team": "payments"},
        ),
        CloudResource(
            name="catalog-api",
            monthly_cost=Decimal("2500"),
            tags={"environment": "production", "team": "catalog"},
        ),
        CloudResource(
            name="test-cluster",
            monthly_cost=Decimal("1200"),
            tags={"environment": "development", "team": "catalog"},
        ),
        CloudResource(
            name="unknown-resource",
            monthly_cost=Decimal("800"),
            tags={},
        ),
    ]

    print("\nTag-based cost allocation")
    print("-" * 50)

    by_environment = group_costs_by_tag(resources, "environment")
    for environment, cost in by_environment.items():
        print(f"{environment:15}: {cost}")


# ---------------------------------------------------------------------------
# 21. COST OPTIMIZATION
# ---------------------------------------------------------------------------

@dataclass
class OptimizationOption:
    name: str
    current_monthly_cost: Decimal
    optimized_monthly_cost: Decimal
    implementation_cost: Decimal = Decimal("0")
    risk_cost: Decimal = Decimal("0")

    def monthly_savings(self) -> Decimal:
        return money(
            self.current_monthly_cost - self.optimized_monthly_cost
        )

    def net_monthly_benefit(self) -> Decimal:
        return money(
            self.monthly_savings() - self.risk_cost
        )

    def payback_months(self) -> Optional[Decimal]:
        savings = self.monthly_savings()

        if savings <= 0:
            return None

        return self.implementation_cost / savings


def optimization_example() -> None:
    option = OptimizationOption(
        name="Rightsize application cluster",
        current_monthly_cost=Decimal("12000"),
        optimized_monthly_cost=Decimal("8500"),
        implementation_cost=Decimal("5000"),
        risk_cost=Decimal("100"),
    )

    print("\nOptimization economics")
    print("-" * 50)
    print(f"Monthly savings: {option.monthly_savings()}")
    print(f"Net monthly benefit: {option.net_monthly_benefit()}")
    print(f"Payback period: {option.payback_months():.2f} months")


# ---------------------------------------------------------------------------
# 22. SENSITIVITY ANALYSIS
# ---------------------------------------------------------------------------

def sensitivity_analysis(
    base_quantity: Decimal,
    quantity_changes: Sequence[Decimal],
    unit_price: Decimal,
) -> List[Tuple[Decimal, Decimal, Decimal]]:
    """
    Produce quantity, cost, and percentage-change scenarios.

    Example:
        -20%, -10%, 0%, +10%, +20%
    """
    if base_quantity < 0 or unit_price < 0:
        raise ValueError("Base quantity and price cannot be negative.")

    base_cost = base_quantity * unit_price
    scenarios = []

    for change in quantity_changes:
        quantity = base_quantity * (
            Decimal("1") + change / Decimal("100")
        )

        if quantity < 0:
            raise ValueError("Sensitivity scenario creates negative quantity.")

        cost = money(quantity * unit_price)
        scenarios.append((change, money(quantity), cost))

    return scenarios


def sensitivity_example() -> None:
    scenarios = sensitivity_analysis(
        base_quantity=Decimal("10000"),
        quantity_changes=[
            Decimal("-20"),
            Decimal("-10"),
            Decimal("0"),
            Decimal("10"),
            Decimal("20"),
        ],
        unit_price=Decimal("0.09"),
    )

    print("\nSensitivity analysis")
    print("-" * 50)

    for change, quantity, cost in scenarios:
        print(
            f"Usage change {change:>5}% | "
            f"quantity {quantity:>8} | cost {cost}"
        )


# ---------------------------------------------------------------------------
# 23. BREAK-EVEN ANALYSIS
# ---------------------------------------------------------------------------

def break_even_units(
    fixed_cost: Decimal,
    variable_cost_per_unit: Decimal,
    revenue_per_unit: Decimal,
) -> Decimal:
    """
    Break-even units:

        fixed cost / (revenue per unit - variable cost per unit)
    """
    if fixed_cost < 0:
        raise ValueError("Fixed cost cannot be negative.")
    if variable_cost_per_unit < 0:
        raise ValueError("Variable cost cannot be negative.")
    if revenue_per_unit <= variable_cost_per_unit:
        raise ValueError(
            "Revenue per unit must exceed variable cost per unit."
        )

    return fixed_cost / (revenue_per_unit - variable_cost_per_unit)


def break_even_example() -> None:
    units = break_even_units(
        fixed_cost=Decimal("50000"),
        variable_cost_per_unit=Decimal("0.05"),
        revenue_per_unit=Decimal("0.20"),
    )

    print("\nCloud service break-even")
    print("-" * 50)
    print(f"Break-even business units: {units:.2f}")


# ---------------------------------------------------------------------------
# 24. GROWTH FORECASTING
# ---------------------------------------------------------------------------

def compound_growth(
    starting_value: Decimal,
    monthly_growth_rate_percent: Decimal,
    months: int,
) -> Decimal:
    if starting_value < 0:
        raise ValueError("Starting value cannot be negative.")
    if months < 0:
        raise ValueError("Months cannot be negative.")

    value = starting_value

    for _ in range(months):
        value *= (
            Decimal("1")
            + monthly_growth_rate_percent / Decimal("100")
        )

    return money(value)


def growth_forecast_example() -> None:
    forecast = compound_growth(
        starting_value=Decimal("10000"),
        monthly_growth_rate_percent=Decimal("5"),
        months=12,
    )

    print("\nCloud spend growth forecast")
    print("-" * 50)
    print(f"Projected monthly spend after 12 months: {forecast}")


# ---------------------------------------------------------------------------
# 25. MULTI-YEAR CLOUD BUDGET
# ---------------------------------------------------------------------------

def monthly_budget_schedule(
    starting_monthly_cost: Decimal,
    monthly_growth_rate_percent: Decimal,
    months: int,
) -> List[Decimal]:
    if starting_monthly_cost < 0:
        raise ValueError("Starting cost cannot be negative.")
    if months < 0:
        raise ValueError("Months cannot be negative.")

    schedule = []
    current = starting_monthly_cost

    for _ in range(months):
        current = money(current)
        schedule.append(current)
        current *= (
            Decimal("1")
            + monthly_growth_rate_percent / Decimal("100")
        )

    return schedule


def budget_schedule_example() -> None:
    schedule = monthly_budget_schedule(
        starting_monthly_cost=Decimal("10000"),
        monthly_growth_rate_percent=Decimal("3"),
        months=12,
    )

    print("\n12-month cloud budget schedule")
    print("-" * 50)

    for month_number, amount in enumerate(schedule, start=1):
        print(f"Month {month_number:2}: {amount}")

    print(f"Annual forecast: {money(sum(schedule))}")


# ---------------------------------------------------------------------------
# 26. COST CONVERSION AND CURRENCY
# ---------------------------------------------------------------------------

def convert_currency(
    amount: Decimal,
    exchange_rate: Decimal,
) -> Decimal:
    """
    Convert using:

        target amount = source amount × exchange rate

    Exchange rates fluctuate and should be treated as assumptions in a
    financial model.
    """
    if amount < 0:
        raise ValueError("Amount cannot be negative.")
    if exchange_rate <= 0:
        raise ValueError("Exchange rate must be positive.")

    return money(amount * exchange_rate)


def currency_example() -> None:
    usd_cost = Decimal("25000")
    usd_to_inr = Decimal("84.50")

    inr_cost = convert_currency(usd_cost, usd_to_inr)

    print("\nCurrency conversion")
    print("-" * 50)
    print(f"USD cost: {usd_cost}")
    print(f"INR equivalent: {inr_cost}")


# ---------------------------------------------------------------------------
# 27. CLOUD ECONOMICS DASHBOARD
# ---------------------------------------------------------------------------

@dataclass
class EconomicsDashboard:
    monthly_budget: Decimal
    monthly_actual: Decimal
    monthly_forecast: Decimal
    monthly_tco_equivalent: Decimal
    cost_per_unit: Decimal
    utilization_percent: Decimal

    def health_status(self) -> str:
        if self.monthly_actual > self.monthly_budget:
            return "Over budget"

        if self.monthly_forecast > self.monthly_budget:
            return "Forecasted over budget"

        if self.utilization_percent < Decimal("40"):
            return "Low utilization"

        return "Within expected range"

    def render(self) -> str:
        return "\n".join([
            "Cloud Economics Dashboard",
            "-" * 50,
            f"Monthly budget:        {self.monthly_budget}",
            f"Monthly actual:        {self.monthly_actual}",
            f"Monthly forecast:      {self.monthly_forecast}",
            f"TCO monthly equivalent: {self.monthly_tco_equivalent}",
            f"Cost per business unit: {self.cost_per_unit}",
            f"Utilization:           {self.utilization_percent:.2f}%",
            f"Health:                {self.health_status()}",
        ])


def dashboard_example() -> None:
    dashboard = EconomicsDashboard(
        monthly_budget=Decimal("30000"),
        monthly_actual=Decimal("27000"),
        monthly_forecast=Decimal("29500"),
        monthly_tco_equivalent=Decimal("28000"),
        cost_per_unit=Decimal("0.05"),
        utilization_percent=Decimal("72"),
    )

    print("\n")
    print(dashboard.render())


# ---------------------------------------------------------------------------
# 28. EDGE CASES
# ---------------------------------------------------------------------------

def demonstrate_edge_cases() -> None:
    print("\nEdge cases")
    print("-" * 50)

    cases = [
        ("Zero usage", lambda: ConsumptionRate(
            "Compute", "hour", Decimal("0.12")
        ).calculate(0)),
        ("Zero storage", lambda: StorageResource(
            "Storage", Decimal("0"), Decimal("0.023")
        ).monthly_cost()),
        ("Negative usage", lambda: ConsumptionRate(
            "Compute", "hour", Decimal("0.12")
        ).calculate(-1)),
        ("Zero units", lambda: UnitEconomics(
            Decimal("100"), Decimal("0"), "request"
        ).cost_per_unit()),
    ]

    for name, operation in cases:
        try:
            print(f"{name:20}: {operation()}")
        except (ValueError, ZeroDivisionError) as error:
            print(f"{name:20}: handled -> {error}")


# ---------------------------------------------------------------------------
# 29. COMMON PRICING MISTAKES
# ---------------------------------------------------------------------------

def demonstrate_common_mistakes() -> None:
    """
    The code intentionally illustrates economic mistakes that are easy to
    make when designing a cloud cost model.
    """
    print("\nCommon cloud economics mistakes")
    print("-" * 50)

    print("1. Multiplying a monthly price by 12 without checking billing units.")
    print("2. Ignoring data-transfer charges.")
    print("3. Treating storage capacity as the only storage cost.")
    print("4. Assuming every workload runs exactly 730 hours per month.")
    print("5. Ignoring minimum commitments.")
    print("6. Ignoring requests, operations, throughput, or I/O charges.")
    print("7. Treating discounts as permanent when contracts are temporary.")
    print("8. Comparing only invoice cost instead of full TCO.")
    print("9. Ignoring migration and exit costs.")
    print("10. Optimizing cost at the expense of reliability or security.")
    print("11. Using average utilization when peak capacity determines architecture.")
    print("12. Failing to assign shared infrastructure to responsible teams.")


# ---------------------------------------------------------------------------
# 30. TRADE-OFF ANALYSIS
# ---------------------------------------------------------------------------

@dataclass
class ArchitectureOption:
    name: str
    monthly_cost: Decimal
    availability_score: Decimal
    performance_score: Decimal
    operational_complexity: Decimal
    security_score: Decimal


def compare_architectures(
    options: Sequence[ArchitectureOption],
) -> None:
    print("\nArchitecture economics trade-off")
    print("-" * 80)
    print(
        f"{'Option':20} {'Cost':>10} {'Availability':>14} "
        f"{'Performance':>13} {'Complexity':>12} {'Security':>10}"
    )

    for option in options:
        print(
            f"{option.name:20} "
            f"{option.monthly_cost:>10} "
            f"{option.availability_score:>14.1f} "
            f"{option.performance_score:>13.1f} "
            f"{option.operational_complexity:>12.1f} "
            f"{option.security_score:>10.1f}"
        )

    print(
        "\nCloud economics is a constrained optimization problem. "
        "The lowest monetary cost is not automatically the best architecture."
    )


def architecture_example() -> None:
    compare_architectures([
        ArchitectureOption(
            "Single-region",
            Decimal("8000"),
            Decimal("85"),
            Decimal("80"),
            Decimal("30"),
            Decimal("85"),
        ),
        ArchitectureOption(
            "Multi-zone",
            Decimal("10500"),
            Decimal("95"),
            Decimal("85"),
            Decimal("50"),
            Decimal("92"),
        ),
        ArchitectureOption(
            "Multi-region",
            Decimal("17000"),
            Decimal("99"),
            Decimal("92"),
            Decimal("80"),
            Decimal("95"),
        ),
    ])


# ---------------------------------------------------------------------------
# 31. SECURITY-RELATED COST CONSIDERATIONS
# ---------------------------------------------------------------------------

def security_cost_example() -> None:
    security_components = {
        "Identity and access management": Decimal("200"),
        "Logging and monitoring": Decimal("500"),
        "Security scanning": Decimal("350"),
        "Backup and recovery": Decimal("800"),
        "Key management": Decimal("150"),
        "Security operations": Decimal("1200"),
    }

    total = money(sum(security_components.values()))

    print("\nSecurity-related cloud economics")
    print("-" * 50)

    for component, cost in security_components.items():
        print(f"{component:30}: {cost}")

    print(f"{'Security cost total':30}: {total}")

    print(
        "\nSecurity controls should not be removed solely because they increase "
        "the cloud bill. Their economic value includes avoided loss, compliance, "
        "availability, and protection of business assets."
    )


# ---------------------------------------------------------------------------
# 32. RESILIENCE COST
# ---------------------------------------------------------------------------

@dataclass
class ResilienceOption:
    name: str
    monthly_infrastructure_cost: Decimal
    expected_downtime_hours: Decimal
    business_loss_per_hour: Decimal

    def expected_downtime_loss(self) -> Decimal:
        return money(
            self.expected_downtime_hours * self.business_loss_per_hour
        )

    def expected_monthly_economic_cost(self) -> Decimal:
        return money(
            self.monthly_infrastructure_cost
            + self.expected_downtime_loss()
        )


def resilience_example() -> None:
    basic = ResilienceOption(
        name="Basic deployment",
        monthly_infrastructure_cost=Decimal("6000"),
        expected_downtime_hours=Decimal("4"),
        business_loss_per_hour=Decimal("5000"),
    )

    resilient = ResilienceOption(
        name="Highly resilient deployment",
        monthly_infrastructure_cost=Decimal("11000"),
        expected_downtime_hours=Decimal("0.5"),
        business_loss_per_hour=Decimal("5000"),
    )

    print("\nResilience economics")
    print("-" * 50)

    for option in [basic, resilient]:
        print(
            f"{option.name:30} "
            f"Infrastructure={option.monthly_infrastructure_cost} "
            f"Downtime loss={option.expected_downtime_loss()} "
            f"Economic cost={option.expected_monthly_economic_cost()}"
        )


# ---------------------------------------------------------------------------
# 33. TCO WITH ONE-TIME AND RECURRING COSTS
# ---------------------------------------------------------------------------

def lifecycle_tco_example() -> None:
    months = 24

    one_time = {
        "Migration": Decimal("30000"),
        "Data transfer during migration": Decimal("5000"),
        "Training": Decimal("7000"),
    }

    recurring_monthly = {
        "Compute": Decimal("5000"),
        "Storage": Decimal("1000"),
        "Database": Decimal("2500"),
        "Network": Decimal("1500"),
        "Support": Decimal("600"),
        "Security": Decimal("700"),
        "Operations": Decimal("1800"),
    }

    one_time_total = money(sum(one_time.values()))
    monthly_total = money(sum(recurring_monthly.values()))
    lifecycle_total = money(
        one_time_total + monthly_total * months
    )

    print("\nLifecycle TCO")
    print("-" * 50)
    print(f"One-time costs:      {one_time_total}")
    print(f"Recurring monthly:   {monthly_total}")
    print(f"Period:              {months} months")
    print(f"Lifecycle TCO:        {lifecycle_total}")


# ---------------------------------------------------------------------------
# 34. PRICING CALCULATOR INPUT VALIDATION
# ---------------------------------------------------------------------------

@dataclass
class PricingInput:
    quantity: Decimal
    unit_price: Decimal
    months: int = 1

    def validate(self) -> None:
        errors = []

        if self.quantity < 0:
            errors.append("Quantity cannot be negative.")

        if self.unit_price < 0:
            errors.append("Unit price cannot be negative.")

        if self.months <= 0:
            errors.append("Months must be greater than zero.")

        if errors:
            raise ValueError(" ".join(errors))

    def total(self) -> Decimal:
        self.validate()
        return money(
            self.quantity
            * self.unit_price
            * Decimal(self.months)
        )


def validation_example() -> None:
    print("\nPricing input validation")
    print("-" * 50)

    valid = PricingInput(
        quantity=Decimal("1000"),
        unit_price=Decimal("0.10"),
        months=3,
    )

    print(f"Valid input total: {valid.total()}")

    invalid = PricingInput(
        quantity=Decimal("-5"),
        unit_price=Decimal("0.10"),
        months=3,
    )

    try:
        invalid.total()
    except ValueError as error:
        print(f"Invalid input handled: {error}")


# ---------------------------------------------------------------------------
# 35. ROUNDING CONSIDERATIONS
# ---------------------------------------------------------------------------

def demonstrate_decimal_vs_float() -> None:
    """
    Monetary calculations should generally use Decimal or another exact
    monetary representation rather than accumulating binary floating-point
    rounding errors.
    """
    float_result = 0.1 + 0.2
    decimal_result = Decimal("0.1") + Decimal("0.2")

    print("\nDecimal vs float")
    print("-" * 50)
    print(f"Python float 0.1 + 0.2: {float_result}")
    print(f"Decimal 0.1 + 0.2:      {decimal_result}")

    print(
        "Decimal is used throughout this script for predictable monetary "
        "calculations."
    )


# ---------------------------------------------------------------------------
# 36. COST OPTIMIZATION PAYBACK
# ---------------------------------------------------------------------------

def optimization_payback(
    current_monthly_cost: Decimal,
    optimized_monthly_cost: Decimal,
    implementation_cost: Decimal,
) -> Optional[Decimal]:
    savings = current_monthly_cost - optimized_monthly_cost

    if savings <= 0:
        return None

    return implementation_cost / savings


def payback_example() -> None:
    months = optimization_payback(
        current_monthly_cost=Decimal("15000"),
        optimized_monthly_cost=Decimal("11000"),
        implementation_cost=Decimal("8000"),
    )

    print("\nOptimization payback")
    print("-" * 50)

    if months is None:
        print("No economic payback under the supplied assumptions.")
    else:
        print(f"Payback: {months:.2f} months")


# ---------------------------------------------------------------------------
# 37. COST ANOMALY DETECTION
# ---------------------------------------------------------------------------

def detect_spend_anomaly(
    historical_spend: Sequence[Decimal],
    current_spend: Decimal,
    threshold_percent: Decimal = Decimal("20"),
) -> bool:
    """
    A simple anomaly rule based on the historical mean.

    Production systems can use more advanced time-series and statistical
    methods, but the underlying concept remains comparison against expected
    spend behavior.
    """
    if not historical_spend:
        raise ValueError("Historical spend cannot be empty.")

    if any(value < 0 for value in historical_spend):
        raise ValueError("Historical spend cannot be negative.")

    if current_spend < 0:
        raise ValueError("Current spend cannot be negative.")

    average = Decimal(str(statistics.mean(
        float(value) for value in historical_spend
    )))

    if average == 0:
        return current_spend > 0

    deviation_percent = (
        (current_spend - average)
        / average
        * Decimal("100")
    )

    return deviation_percent > threshold_percent


def anomaly_example() -> None:
    historical = [
        Decimal("10000"),
        Decimal("10200"),
        Decimal("9800"),
        Decimal("10500"),
        Decimal("10100"),
    ]

    current = Decimal("13000")

    print("\nSpend anomaly detection")
    print("-" * 50)
    print(
        f"Anomaly detected: "
        f"{detect_spend_anomaly(historical, current)}"
    )


# ---------------------------------------------------------------------------
# 38. COST CENTER REPORTING
# ---------------------------------------------------------------------------

@dataclass
class CostCenter:
    name: str
    budget: Decimal
    actual: Decimal

    def variance(self) -> Decimal:
        return money(self.actual - self.budget)

    def utilization(self) -> Decimal:
        if self.budget <= 0:
            raise ValueError("Budget must be positive.")

        return self.actual / self.budget * Decimal("100")


def cost_center_report() -> None:
    centers = [
        CostCenter("Engineering", Decimal("30000"), Decimal("27500")),
        CostCenter("Data", Decimal("15000"), Decimal("17200")),
        CostCenter("Security", Decimal("12000"), Decimal("11000")),
        CostCenter("Product", Decimal("8000"), Decimal("7600")),
    ]

    print("\nCost center report")
    print("-" * 70)
    print(
        f"{'Cost center':20} {'Budget':>12} "
        f"{'Actual':>12} {'Variance':>12} {'Utilization':>12}"
    )

    for center in centers:
        print(
            f"{center.name:20} "
            f"{center.budget:>12} "
            f"{center.actual:>12} "
            f"{center.variance():>12} "
            f"{center.utilization():>11.2f}%"
        )


# ---------------------------------------------------------------------------
# 39. COST OPTIMIZATION PRIORITIZATION
# ---------------------------------------------------------------------------

@dataclass
class OptimizationCandidate:
    name: str
    annual_savings: Decimal
    engineering_effort_days: Decimal
    risk_score: Decimal

    def savings_per_engineering_day(self) -> Decimal:
        if self.engineering_effort_days <= 0:
            raise ValueError("Engineering effort must be positive.")

        return self.annual_savings / self.engineering_effort_days


def prioritize_optimization(
    candidates: Sequence[OptimizationCandidate],
) -> List[OptimizationCandidate]:
    """
    Sort by estimated annual savings per engineering day.

    This is a prioritization heuristic, not a complete decision model.
    Risk, customer impact, reliability, and strategic value also matter.
    """
    return sorted(
        candidates,
        key=lambda candidate: candidate.savings_per_engineering_day(),
        reverse=True,
    )


def optimization_prioritization_example() -> None:
    candidates = [
        OptimizationCandidate(
            "Delete idle resources",
            Decimal("18000"),
            Decimal("3"),
            Decimal("1"),
        ),
        OptimizationCandidate(
            "Rightsize databases",
            Decimal("30000"),
            Decimal("12"),
            Decimal("4"),
        ),
        OptimizationCandidate(
            "Redesign storage lifecycle",
            Decimal("12000"),
            Decimal("8"),
            Decimal("2"),
        ),
    ]

    print("\nOptimization prioritization")
    print("-" * 70)

    for rank, candidate in enumerate(
        prioritize_optimization(candidates),
        start=1,
    ):
        print(
            f"{rank}. {candidate.name}: "
            f"${candidate.annual_savings} annual savings / "
            f"{candidate.engineering_effort_days} engineering days"
        )


# ---------------------------------------------------------------------------
# 40. PRODUCTION COST GOVERNANCE
# ---------------------------------------------------------------------------

def production_governance_checklist() -> None:
    controls = [
        "Define owners for cloud accounts and subscriptions.",
        "Require environment and cost-center tags where supported.",
        "Set budgets for major organizational scopes.",
        "Create alerts for unexpected spend changes.",
        "Review idle resources periodically.",
        "Monitor utilization and rightsize resources.",
        "Review network architecture and data-transfer paths.",
        "Separate development and production spending.",
        "Track commitments and expiration dates.",
        "Model one-time migration costs.",
        "Include security and resilience costs in TCO.",
        "Use least privilege for cost-management operations.",
        "Protect billing data and financial reports.",
        "Audit pricing assumptions when provider prices change.",
        "Document cost ownership for shared services.",
    ]

    print("\nProduction cloud cost governance")
    print("-" * 50)

    for number, control in enumerate(controls, start=1):
        print(f"{number:2}. {control}")


# ---------------------------------------------------------------------------
# 41. CLOUD PRICING CALCULATOR DESIGN
# ---------------------------------------------------------------------------

def pricing_calculator_design_example() -> None:
    """
    Conceptual calculator architecture expressed through executable
    structures.

    A robust pricing calculator generally separates:

        Input layer
            ↓
        Validation
            ↓
        Pricing catalog / assumptions
            ↓
        Usage calculation
            ↓
        Discounts / commitments
            ↓
        Taxes / currency
            ↓
        TCO aggregation
            ↓
        Reporting

    Separating these concerns prevents pricing assumptions from being mixed
    with presentation logic.
    """
    inputs = {
        "region": "example-region",
        "compute_hours": Decimal("2000"),
        "instances": 4,
        "storage_gb": Decimal("2000"),
        "egress_gb": Decimal("5000"),
    }

    rates = {
        "compute_hour": Decimal("0.12"),
        "storage_gb_month": Decimal("0.023"),
        "egress_gb": Decimal("0.09"),
    }

    compute = (
        inputs["compute_hours"]
        * Decimal(inputs["instances"])
        * rates["compute_hour"]
    )

    storage = inputs["storage_gb"] * rates["storage_gb_month"]
    egress = inputs["egress_gb"] * rates["egress_gb"]

    print("\nPricing calculator architecture example")
    print("-" * 50)
    print(f"Compute: {money(compute)}")
    print(f"Storage: {money(storage)}")
    print(f"Egress:  {money(egress)}")
    print(f"Total:   {money(compute + storage + egress)}")


# ---------------------------------------------------------------------------
# 42. SHARED SERVICE ECONOMICS
# ---------------------------------------------------------------------------

def shared_service_allocation_example() -> None:
    """
    Shared services such as logging, networking, security, and monitoring
    may not map cleanly to one application.

    Allocation requires a documented policy. Possible drivers include:
    usage, request count, storage consumption, headcount, revenue, or
    proportional infrastructure consumption.
    """
    shared_cost = Decimal("12000")

    allocation = allocate_cost(
        shared_cost,
        [
            Team("Application A", Decimal("50")),
            Team("Application B", Decimal("30")),
            Team("Application C", Decimal("20")),
        ],
    )

    print("\nShared-service allocation")
    print("-" * 50)

    for team, cost in allocation.items():
        print(f"{team:20}: {cost}")


# ---------------------------------------------------------------------------
# 43. TCO COMPARISON WITH GROWTH
# ---------------------------------------------------------------------------

def projected_tco(
    initial_monthly_cost: Decimal,
    monthly_growth_rate: Decimal,
    months: int,
    one_time_cost: Decimal = Decimal("0"),
) -> Decimal:
    schedule = monthly_budget_schedule(
        initial_monthly_cost,
        monthly_growth_rate,
        months,
    )

    return money(one_time_cost + sum(schedule))


def growth_tco_example() -> None:
    cloud_tco = projected_tco(
        initial_monthly_cost=Decimal("10000"),
        monthly_growth_rate=Decimal("2"),
        months=36,
        one_time_cost=Decimal("25000"),
    )

    print("\nGrowth-aware TCO")
    print("-" * 50)
    print(f"36-month projected TCO: {cloud_tco}")


# ---------------------------------------------------------------------------
# 44. PRACTICAL CLOUD ECONOMICS WORKFLOW
# ---------------------------------------------------------------------------

def cloud_economics_workflow() -> None:
    workflow = [
        "1. Define the workload and business objective.",
        "2. Identify measurable cloud resources.",
        "3. Identify each billing dimension.",
        "4. Establish region, architecture, and usage assumptions.",
        "5. Apply unit prices.",
        "6. Model fixed and variable charges.",
        "7. Model discounts and commitments separately.",
        "8. Estimate network and ancillary charges.",
        "9. Add migration, operations, security, and support costs.",
        "10. Calculate TCO over a defined time horizon.",
        "11. Calculate cost per business unit.",
        "12. Compare alternative architectures.",
        "13. Perform sensitivity analysis.",
        "14. Establish budgets and forecasts.",
        "15. Allocate costs to accountable teams.",
        "16. Monitor actual versus expected spend.",
        "17. Investigate anomalies.",
        "18. Optimize based on value, risk, and engineering effort.",
    ]

    print("\nCloud economics workflow")
    print("-" * 50)

    for step in workflow:
        print(step)


# ---------------------------------------------------------------------------
# 45. UNIT TESTS
# ---------------------------------------------------------------------------

class TestCloudEconomics(unittest.TestCase):
    """Executable tests for the core financial calculations."""

    def test_consumption_rate(self) -> None:
        rate = ConsumptionRate(
            "Compute",
            "hour",
            Decimal("0.10"),
        )
        self.assertEqual(rate.calculate(100), Decimal("10.00"))

    def test_negative_consumption_rejected(self) -> None:
        rate = ConsumptionRate(
            "Compute",
            "hour",
            Decimal("0.10"),
        )

        with self.assertRaises(ValueError):
            rate.calculate(-1)

    def test_progressive_tiers(self) -> None:
        pricing = TieredPrice([
            Tier(Decimal("100"), Decimal("1.00")),
            Tier(Decimal("200"), Decimal("0.50")),
            Tier(None, Decimal("0.25")),
        ])

        # 100 * 1.00 + 100 * 0.50 + 100 * 0.25 = 175
        self.assertEqual(
            pricing.cost(Decimal("300")),
            Decimal("175.00"),
        )

    def test_volume_pricing(self) -> None:
        pricing = VolumePrice([
            (Decimal("1"), Decimal("1.00")),
            (Decimal("100"), Decimal("0.50")),
            (Decimal("500"), Decimal("0.25")),
        ])

        self.assertEqual(
            pricing.cost(Decimal("600")),
            Decimal("150.00"),
        )

    def test_budget_status(self) -> None:
        budget = Budget(
            name="Engineering",
            monthly_limit=Decimal("1000"),
        )

        self.assertEqual(
            budget.status(Decimal("500")),
            "NORMAL",
        )

        self.assertEqual(
            budget.status(Decimal("850")),
            "WARNING",
        )

        self.assertEqual(
            budget.status(Decimal("1000")),
            "CRITICAL",
        )

    def test_unit_economics(self) -> None:
        economics = UnitEconomics(
            total_cost=Decimal("100"),
            units=Decimal("1000"),
            unit_name="request",
        )

        self.assertEqual(
            economics.cost_per_unit(),
            Decimal("0.10"),
        )

    def test_break_even(self) -> None:
        result = break_even_units(
            fixed_cost=Decimal("1000"),
            variable_cost_per_unit=Decimal("2"),
            revenue_per_unit=Decimal("5"),
        )

        self.assertEqual(result, Decimal("333.3333333333333333333333333333"))

    def test_pricing_calculator(self) -> None:
        calculator = CloudPricingCalculator()

        calculator.add(
            PricingLineItem(
                name="Compute",
                quantity=Decimal("100"),
                unit="hours",
                unit_price=Decimal("0.10"),
            )
        )

        self.assertEqual(
            calculator.subtotal(),
            Decimal("10.00"),
        )

        self.assertEqual(
            calculator.total(
                discount_rate=Decimal("10"),
                tax_rate=Decimal("0"),
            ),
            Decimal("9.00"),
        )

    def test_currency_conversion(self) -> None:
        self.assertEqual(
            convert_currency(
                Decimal("100"),
                Decimal("80"),
            ),
            Decimal("8000.00"),
        )

    def test_commitment_break_even(self) -> None:
        self.assertEqual(
            commitment_break_even_hours(
                Decimal("0.20"),
                Decimal("0.10"),
                Decimal("100"),
            ),
            Decimal("1000"),
        )


def run_tests() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestCloudEconomics
    )

    result = unittest.TextTestRunner(
        verbosity=1
    ).run(suite)

    if not result.wasSuccessful():
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# 46. MAIN TEACHING PROGRAM
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 80)
    print("CLOUD ECONOMICS FUNDAMENTALS")
    print("=" * 80)

    print("\nSECTION 1: Fundamental terminology")
    explain_basic_terms()

    print("\nSECTION 2: CAPEX vs OPEX")
    compare_capex_and_opex()

    print("\nSECTION 3: Pay-as-you-go")
    pay_as_you_go_example()

    print("\nSECTION 4: Pricing models")
    pricing_model_comparison()

    print("\nSECTION 5: Cloud resource cost components")
    demonstrate_workload_costs()

    print("\nSECTION 6: Total Cost of Ownership")
    tco_example()

    print("\nSECTION 7: On-premises vs cloud")
    compare_scenarios()

    print("\nSECTION 8: Unit economics")
    unit_economics_example()

    print("\nSECTION 9: Utilization and idle resources")
    idle_resource_example()

    print("\nSECTION 10: Autoscaling economics")
    autoscaling_example()

    print("\nSECTION 11: Commitments and reserved capacity")
    commitment_example()

    print("\nSECTION 12: Interruptible capacity")
    spot_example()

    print("\nSECTION 13: Network economics")
    network_example()

    print("\nSECTION 14: Cloud Pricing Calculator")
    pricing_calculator_example()

    print("\nSECTION 15: Infrastructure budgeting")
    budget_example()

    print("\nSECTION 16: Forecasting")
    forecasting_example()

    print("\nSECTION 17: Variance analysis")
    variance_example()

    print("\nSECTION 18: Cost allocation")
    allocation_example()

    print("\nSECTION 19: Tagging")
    tagging_example()

    print("\nSECTION 20: Optimization economics")
    optimization_example()

    print("\nSECTION 21: Sensitivity analysis")
    sensitivity_example()

    print("\nSECTION 22: Break-even analysis")
    break_even_example()

    print("\nSECTION 23: Growth forecasting")
    growth_forecast_example()

    print("\nSECTION 24: Annual budget schedule")
    budget_schedule_example()

    print("\nSECTION 25: Currency conversion")
    currency_example()

    print("\nSECTION 26: Economics dashboard")
    dashboard_example()

    print("\nSECTION 27: Edge cases")
    demonstrate_edge_cases()

    print("\nSECTION 28: Common mistakes")
    demonstrate_common_mistakes()

    print("\nSECTION 29: Architecture trade-offs")
    architecture_example()

    print("\nSECTION 30: Security economics")
    security_cost_example()

    print("\nSECTION 31: Resilience economics")
    resilience_example()

    print("\nSECTION 32: Lifecycle TCO")
    lifecycle_tco_example()

    print("\nSECTION 33: Input validation")
    validation_example()

    print("\nSECTION 34: Monetary precision")
    demonstrate_decimal_vs_float()

    print("\nSECTION 35: Optimization payback")
    payback_example()

    print("\nSECTION 36: Spend anomaly detection")
    anomaly_example()

    print("\nSECTION 37: Cost-center reporting")
    cost_center_report()

    print("\nSECTION 38: Optimization prioritization")
    optimization_prioritization_example()

    print("\nSECTION 39: Production governance")
    production_governance_checklist()

    print("\nSECTION 40: Pricing calculator design")
    pricing_calculator_design_example()

    print("\nSECTION 41: Shared services")
    shared_service_allocation_example()

    print("\nSECTION 42: Growth-aware TCO")
    growth_tco_example()

    print("\nSECTION 43: Practical workflow")
    cloud_economics_workflow()

    print("\nSECTION 44: Automated tests")
    run_tests()

    print("\n" + "=" * 80)
    print("END OF CLOUD ECONOMICS STUDY SCRIPT")
    print("=" * 80)


if __name__ == "__main__":
    main()
