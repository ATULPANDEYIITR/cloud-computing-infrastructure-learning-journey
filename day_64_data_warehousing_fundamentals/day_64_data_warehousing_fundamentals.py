from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import csv
import json
import statistics
import tempfile


class LoadStrategy(Enum):
    ETL = "ETL"
    ELT = "ELT"


class StorageModel(Enum):
    ROW = "row"
    COLUMNAR = "columnar"


class PipelineState(Enum):
    CREATED = "created"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    TRANSFORMED = "transformed"
    LOADED = "loaded"
    FAILED = "failed"


class ValidationError(Exception):
    pass


class PipelineError(Exception):
    pass


@dataclass(frozen=True)
class SalesRecord:
    order_id: int
    order_date: str
    customer_id: int
    product_id: int
    region: str
    quantity: int
    unit_price: float

    @property
    def revenue(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class WarehouseFact:
    order_id: int
    date_key: int
    customer_id: int
    product_id: int
    region: str
    quantity: int
    revenue: float


@dataclass
class PipelineRun:
    strategy: LoadStrategy
    state: PipelineState = PipelineState.CREATED
    extracted: int = 0
    rejected: int = 0
    loaded: int = 0
    errors: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.errors.append(message)
        self.state = PipelineState.FAILED


class OLTPStore:
    """Small transactional source-system simulation."""

    def __init__(self) -> None:
        self.orders: dict[int, SalesRecord] = {}

    def insert_order(self, record: SalesRecord) -> None:
        if record.order_id in self.orders:
            raise ValidationError(f"Duplicate order_id: {record.order_id}")
        if record.quantity <= 0:
            raise ValidationError("Quantity must be positive")
        if record.unit_price < 0:
            raise ValidationError("Unit price cannot be negative")
        if not record.region.strip():
            raise ValidationError("Region cannot be empty")
        self.orders[record.order_id] = record

    def extract(self) -> list[SalesRecord]:
        return list(self.orders.values())


class DataWarehouse:
    """Star-schema-like analytical storage."""

    def __init__(self) -> None:
        self.dim_date: dict[int, dict[str, Any]] = {}
        self.dim_customer: dict[int, dict[str, Any]] = {}
        self.dim_product: dict[int, dict[str, Any]] = {}
        self.fact_sales: list[WarehouseFact] = []

    @staticmethod
    def date_key(date_text: str) -> int:
        return int(date_text.replace("-", ""))

    def load_dimensions(self, records: list[SalesRecord]) -> None:
        for r in records:
            key = self.date_key(r.order_date)
            date = datetime.strptime(r.order_date, "%Y-%m-%d")
            self.dim_date[key] = {
                "date": r.order_date,
                "year": date.year,
                "month": date.month,
                "quarter": (date.month - 1) // 3 + 1,
            }
            self.dim_customer.setdefault(
                r.customer_id,
                {"customer_id": r.customer_id, "segment": "Business"},
            )
            self.dim_product.setdefault(
                r.product_id,
                {"product_id": r.product_id, "category": "General"},
            )

    def load_facts(self, records: list[SalesRecord]) -> None:
        existing = {f.order_id for f in self.fact_sales}
        for r in records:
            if r.order_id in existing:
                raise PipelineError(f"Fact already loaded for order {r.order_id}")
            self.fact_sales.append(
                WarehouseFact(
                    order_id=r.order_id,
                    date_key=self.date_key(r.order_date),
                    customer_id=r.customer_id,
                    product_id=r.product_id,
                    region=r.region,
                    quantity=r.quantity,
                    revenue=round(r.revenue, 2),
                )
            )

    def revenue_by_region(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for fact in self.fact_sales:
            totals[fact.region] += fact.revenue
        return {k: round(v, 2) for k, v in sorted(totals.items())}

    def monthly_revenue(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for fact in self.fact_sales:
            date_info = self.dim_date[fact.date_key]
            month = date_info["date"][:7]
            totals[month] += fact.revenue
        return {k: round(v, 2) for k, v in sorted(totals.items())}


def validate_record(record: SalesRecord) -> None:
    datetime.strptime(record.order_date, "%Y-%m-%d")
    if record.order_id <= 0:
        raise ValidationError("Order ID must be positive")
    if record.customer_id <= 0 or record.product_id <= 0:
        raise ValidationError("Dimension identifiers must be positive")
    if record.quantity <= 0:
        raise ValidationError("Quantity must be positive")
    if record.unit_price < 0:
        raise ValidationError("Unit price cannot be negative")


def transform_record(record: SalesRecord) -> SalesRecord:
    region = " ".join(record.region.strip().title().split())
    return SalesRecord(
        order_id=record.order_id,
        order_date=record.order_date,
        customer_id=record.customer_id,
        product_id=record.product_id,
        region=region,
        quantity=record.quantity,
        unit_price=round(record.unit_price, 2),
    )


def run_pipeline(
    source: OLTPStore,
    warehouse: DataWarehouse,
    strategy: LoadStrategy,
) -> PipelineRun:
    run = PipelineRun(strategy=strategy)

    try:
        extracted = source.extract()
        run.extracted = len(extracted)
        run.state = PipelineState.EXTRACTED

        valid_records: list[SalesRecord] = []

        for record in extracted:
            try:
                validate_record(record)
                transformed = transform_record(record)
                valid_records.append(transformed)
            except (ValidationError, ValueError) as exc:
                run.rejected += 1
                run.errors.append(
                    f"Order {record.order_id} rejected: {exc}"
                )

        run.state = PipelineState.VALIDATED

        if strategy is LoadStrategy.ETL:
            warehouse.load_dimensions(valid_records)
            warehouse.load_facts(valid_records)
        else:
            # ELT conceptually loads source-shaped data first and performs
            # analytical transformation in the warehouse.
            warehouse.load_dimensions(extracted)
            transformed_records = [
                transform_record(r) for r in valid_records
            ]
            warehouse.load_facts(transformed_records)

        run.state = PipelineState.LOADED
        run.loaded = len(valid_records)

    except (PipelineError, ValidationError, ValueError) as exc:
        run.fail(str(exc))

    return run


def columnar_scan(
    rows: list[dict[str, Any]],
    requested_columns: set[str],
    predicate,
) -> list[dict[str, Any]]:
    """
    Simulates the key advantage of columnar analytical storage:
    only requested columns are reconstructed after predicate evaluation.
    """
    if not rows:
        return []

    available = set(rows[0])
    if not requested_columns.issubset(available):
        missing = requested_columns - available
        raise KeyError(f"Unknown columns: {sorted(missing)}")

    result: list[dict[str, Any]] = []
    for row in rows:
        if predicate(row):
            result.append({column: row[column] for column in requested_columns})
    return result


def write_demo_csv(path: Path, records: list[SalesRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "order_id",
                "order_date",
                "customer_id",
                "product_id",
                "region",
                "quantity",
                "unit_price",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(record.__dict__)


def main() -> None:
    source = OLTPStore()

    source_records = [
        SalesRecord(1001, "2026-01-15", 501, 9001, "north", 5, 120.00),
        SalesRecord(1002, "2026-01-18", 502, 9002, "South", 3, 250.00),
        SalesRecord(1003, "2026-02-03", 501, 9001, "north", 7, 120.00),
        SalesRecord(1004, "2026-02-19", 503, 9003, "West", 2, 450.00),
        SalesRecord(1005, "2026-03-05", 504, 9002, "east", 4, 250.00),
    ]

    for record in source_records:
        source.insert_order(record)

    # Edge case: rejected by the OLTP validation layer.
    try:
        source.insert_order(
            SalesRecord(1006, "2026-03-08", 505, 9004, "North", 0, 99.00)
        )
    except ValidationError as exc:
        print(f"OLTP validation blocked invalid transaction: {exc}")

    warehouse = DataWarehouse()
    run = run_pipeline(source, warehouse, LoadStrategy.ETL)

    print("\nPipeline:")
    print(f"  strategy:  {run.strategy.value}")
    print(f"  state:     {run.state.value}")
    print(f"  extracted: {run.extracted}")
    print(f"  loaded:    {run.loaded}")
    print(f"  rejected:  {run.rejected}")

    if run.errors:
        print("  errors:")
        for error in run.errors:
            print(f"    - {error}")

    print("\nAnalytical queries:")
    print("Revenue by region:", warehouse.revenue_by_region())
    print("Monthly revenue:", warehouse.monthly_revenue())

    total_revenue = sum(f.revenue for f in warehouse.fact_sales)
    average_order = statistics.mean(f.revenue for f in warehouse.fact_sales)
    print(f"Total revenue: {total_revenue:.2f}")
    print(f"Average order value: {average_order:.2f}")

    rows = [
        {
            "order_id": f.order_id,
            "region": f.region,
            "quantity": f.quantity,
            "revenue": f.revenue,
        }
        for f in warehouse.fact_sales
    ]

    high_value = columnar_scan(
        rows,
        {"order_id", "region", "revenue"},
        lambda row: row["revenue"] >= 500,
    )
    print("\nColumn-oriented analytical scan:")
    print(json.dumps(high_value, indent=2))

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "sales_extract.csv"
        write_demo_csv(csv_path, source_records)
        print(f"\nValidated CSV extract written to: {csv_path.name}")


if __name__ == "__main__":
    main()
