# Data Warehousing Fundamentals

## Scope

This learning artifact models a small but complete analytical data platform around sales data. The implementations distinguish operational transaction processing from analytical processing and demonstrate the core ideas behind data warehousing, ETL, ELT, analytical databases, dimensional modeling, and column-oriented analytical access.

The five source files use different engineering perspectives:

| File | Primary perspective | Main implementation |
|---|---|---|
| Python | Data-engineering workflow | OLTP simulation, ETL/ELT pipeline, dimensional warehouse, validation, analytical scans |
| JavaScript | Event-driven processing | Pipeline events, asynchronous file handling, Maps, policy-style validation |
| C++17 | Performance-oriented domain engine | Typed warehouse model, STL containers, validation, aggregation |
| Java 17 | Enterprise architecture | Records, domain types, service layer, immutable collections, pipeline states |
| PostgreSQL | Relational analytical platform | Star schema, constraints, triggers, views, functions, procedure, CTEs, indexes |

The domain is intentionally small enough to inspect but includes the major mechanisms required in a production-oriented warehouse workflow.

## Data Warehousing Fundamentals

A data warehouse separates analytical workloads from the transactional workload that records day-to-day business events.

The central distinction is workload shape.

| Characteristic | OLTP | OLAP |
|---|---|---|
| Primary purpose | Transactions | Analysis |
| Typical operation | Insert or update one business event | Scan and aggregate many records |
| Data model | Normalized relational structures | Dimensional or analytical structures |
| Query pattern | Short, selective queries | Large scans and aggregations |
| Concurrency | High transactional concurrency | Analytical concurrency |
| Typical latency | Milliseconds | Seconds to longer analytical operations |
| Data modification | Frequent | Usually batch or incremental loading |
| Example | Creating an order | Revenue by region and month |

The Python, JavaScript, C++17, and Java implementations first represent an operational source and then move records into warehouse structures. PostgreSQL provides the relational version of the same separation.

## OLTP

OLTP means Online Transaction Processing.

An OLTP system is responsible for maintaining the current operational state. A transaction such as an order creation normally needs immediate validation and durable storage.

The source model contains:

- customers
- products
- orders
- quantities
- unit prices
- order dates
- regions

The operational order table uses primary and foreign keys and check constraints in PostgreSQL. The application implementations enforce equivalent rules through validation methods and domain objects.

Typical OLTP properties demonstrated by the artifact include:

- duplicate-key prevention
- positive identifiers
- positive quantities
- non-negative monetary values
- valid customer and product references
- mandatory regions
- transaction-oriented validation

An invalid order should be rejected before it contaminates downstream analytical data.

## OLAP

OLAP means Online Analytical Processing.

OLAP workloads answer questions across many records. Typical operations include:

- total revenue
- revenue by region
- revenue by month
- revenue by product category
- customer ranking
- aggregation across multiple dimensions

The warehouse fact table stores measurable business events. Dimension tables provide descriptive context.

A simplified relationship is:

    dim_date
        |
        |
    fact_sales ---- dim_customer
        |
        |
    dim_product

The fact table contains measurements such as quantity and revenue. Dimensions provide attributes used for filtering, grouping, and reporting.

## Dimensional Modeling

The PostgreSQL implementation uses a star-schema-like structure.

The central fact table is `fact_sales`.

Its measures include:

- `quantity`
- `revenue`

Its dimensional references include:

- date
- customer
- product

The dimensions contain descriptive attributes.

### Date dimension

`dim_date` provides:

- calendar date
- year
- month
- quarter

This avoids repeatedly deriving calendar attributes during analytical queries.

### Customer dimension

`dim_customer` provides:

- source customer identifier
- customer name
- customer segment

### Product dimension

`dim_product` provides:

- source product identifier
- product name
- product category

This structure supports analytical queries without requiring every report to reconstruct business attributes from the operational model.

## ETL

ETL means Extract, Transform, Load.

The logical sequence is:

    Operational Source
          |
       Extract
          |
       Validate
          |
       Transform
          |
        Load
          |
     Data Warehouse

The Python implementation explicitly models the stages.

1. Extract records from the operational store.
2. Validate source values.
3. Normalize region values and monetary precision.
4. Populate dimensions.
5. Populate facts.
6. Produce pipeline metrics.

Transformation occurs before warehouse loading.

ETL is useful when transformations need to occur outside the analytical database, when source data requires substantial preprocessing, or when a controlled staging and transformation layer is desirable.

## ELT

ELT means Extract, Load, Transform.

The logical sequence is:

    Operational Source
          |
       Extract
          |
        Load
          |
    Warehouse Storage
          |
      Transform
          |
      Analytical Model

ELT moves more transformation responsibility into the analytical database.

The implementations expose ETL and ELT as distinct pipeline strategies rather than treating them as interchangeable names.

The conceptual distinction is where transformation occurs.

| Process | Transformation location |
|---|---|
| ETL | Before warehouse loading |
| ELT | After loading into the analytical platform |

Modern analytical databases can make ELT attractive because they provide substantial compute, SQL processing, parallel execution, and scalable storage.

## Analytical Databases

An analytical database is optimized for queries that read substantial amounts of data and calculate results across many records.

Typical analytical operations include:

    Filter
       |
    Project
       |
    Group
       |
    Aggregate
       |
    Report

The PostgreSQL implementation demonstrates analytical behavior through:

- grouped aggregation
- `ROLLUP`
- common table expressions
- window ranking
- date filtering
- reporting views
- eligibility calculations
- execution-plan inspection

An analytical database is not simply an OLTP database with a different name. The workload, schema design, storage layout, indexing strategy, and query execution requirements can be substantially different.

## Columnar Storage

Traditional row-oriented storage organizes values approximately as:

    Row 1: order_id | date | customer | region | quantity | revenue
    Row 2: order_id | date | customer | region | quantity | revenue
    Row 3: order_id | date | customer | region | quantity | revenue

A column-oriented representation conceptually organizes them as:

    order_id:  [ ... ]
    date:      [ ... ]
    customer:  [ ... ]
    region:    [ ... ]
    quantity:  [ ... ]
    revenue:   [ ... ]

Analytical queries frequently need only a subset of columns.

For example, a regional revenue query may need:

- region
- revenue

It does not necessarily need every attribute associated with an order.

The Python and JavaScript implementations include analytical scan functions that project only requested fields after applying a predicate. This is a logical simulation of the column-oriented access principle rather than an implementation of a physical columnar storage engine.

Columnar systems can also benefit from:

- compression
- vectorized execution
- reduced I/O for narrow projections
- efficient scans of analytical measures

Columnar storage does not automatically make every workload faster. Transaction-heavy workloads with frequent row-level modifications can favor row-oriented structures.

## ETL and ELT Data Quality

Data quality should be enforced at multiple boundaries.

The implementations validate:

- identifiers
- dates
- regions
- quantities
- monetary values
- duplicate orders
- dimension references

PostgreSQL applies database-level enforcement through:

- primary keys
- foreign keys
- `CHECK` constraints
- unique constraints
- triggers

Application implementations perform equivalent validation before loading records.

This layered approach prevents invalid source records from silently becoming analytical facts.

## Pipeline State

A data pipeline needs observable state.

The source implementations model states such as:

    CREATED
       |
    EXTRACTED
       |
    VALIDATED
       |
    LOADED

A failure transitions the process into a failed state.

Pipeline metrics record:

- extracted rows
- rejected rows
- loaded rows
- error messages

This is important because a successful program termination does not necessarily mean that every source record was loaded correctly.

A production pipeline would normally persist these metrics and associate them with an execution identifier.

The PostgreSQL `pipeline_runs` and `pipeline_rejections` tables provide this operational metadata model.

## Validation and Failure Handling

Several failure classes are represented.

### Duplicate records

The operational stores reject duplicate order identifiers.

The warehouse fact table uses a unique order identifier to prevent duplicate fact insertion.

### Invalid quantity

A quantity of zero or a negative quantity is invalid because a sales fact must represent a positive number of units.

### Invalid monetary value

Negative unit prices are rejected.

### Missing dimension references

PostgreSQL foreign keys prevent orders from referencing nonexistent customers or products.

### Duplicate warehouse facts

The application implementations check whether an order has already been loaded.

### Pipeline failure

The application pipelines preserve error information and expose a failed state rather than silently continuing.

## PostgreSQL Integrity Controls

The PostgreSQL implementation demonstrates several database mechanisms.

### Primary keys

Primary keys uniquely identify records.

Examples include:

- `source_customers.customer_id`
- `source_products.product_id`
- `source_orders.order_id`
- `fact_sales.sales_fact_id`

### Foreign keys

Foreign keys maintain relationships between facts and dimensions.

For example, `fact_sales.date_key` references `dim_date.date_key`.

### Check constraints

Check constraints prevent invalid values at the database boundary.

Examples include:

- positive quantities
- non-negative monetary values
- valid month numbers
- non-empty regions

### Unique constraints

Unique constraints prevent duplicate business identifiers.

The warehouse uses a unique `order_id` in the fact table.

## Triggers

The PostgreSQL schema uses triggers for two targeted mechanisms.

The date-dimension trigger ensures that a date dimension row exists when an operational order is inserted.

The region normalization trigger standardizes whitespace and capitalization before the order is stored.

Triggers are appropriate when an invariant must be enforced automatically at the database boundary. They should not be used indiscriminately because hidden side effects can make complex systems harder to reason about.

## Views

The `sales_analytics` view combines facts and dimensions into an analytical representation.

It exposes:

- calendar information
- customer information
- product information
- region
- quantity
- revenue

A view can provide a stable analytical interface while keeping the underlying dimensional joins centralized.

## CTEs and Analytical Queries

Common table expressions are used to structure analytical processing into logical stages.

The customer-performance query first calculates revenue per customer and then ranks customers.

The conceptual workflow is:

    Fact Data
       |
    Customer Aggregation
       |
    Ranking
       |
    Performance Report

This separates aggregation from ranking and makes the query easier to reason about.

## Aggregation

The implementations demonstrate aggregation by:

- region
- month
- category
- customer
- category and region

Aggregations are central to OLAP workloads because analytical questions commonly operate on groups rather than individual transactions.

The PostgreSQL `ROLLUP` query demonstrates hierarchical aggregation by category and region.

## Performance Considerations

The analytical workload benefits from reducing unnecessary data access.

The PostgreSQL implementation includes indexes on:

- order dates
- customer identifiers
- product identifiers
- region and date
- fact dates
- fact customers
- fact products
- fact region and date

Index selection must correspond to actual workload patterns. Indexes improve some reads but consume storage and increase write-maintenance cost.

The `EXPLAIN` query demonstrates how a database execution plan can be inspected instead of assuming that an index will always be used.

For large analytical systems, additional performance mechanisms can include:

- partitioning
- parallel query execution
- compression
- materialized aggregates
- columnar storage
- distributed execution
- incremental loading

Those mechanisms are architectural extensions rather than hidden assumptions in this artifact.

## Python Design

The Python implementation emphasizes data-engineering concepts.

Important components include:

- `SalesRecord` as an immutable domain representation
- `OLTPStore` for operational transactions
- `DataWarehouse` for analytical storage
- `PipelineRun` for pipeline state and metrics
- ETL and ELT strategies
- validation exceptions
- CSV extraction
- analytical aggregation
- column-oriented projection simulation

The `dataclass` structures keep domain data explicit while the warehouse separates dimensions from facts.

The script also demonstrates temporary-file handling so that generated extracts do not require permanent filesystem state.

## JavaScript Design

The JavaScript implementation uses a different engineering model.

`Map` structures represent keyed operational and warehouse state.

`EventEmitter` exposes pipeline transitions and rejected records as events.

The asynchronous `main` function demonstrates asynchronous file handling using Node.js standard-library facilities.

The analytical projection function selects requested fields after predicate evaluation. This highlights the difference between a general object representation and a narrower analytical projection.

The implementation deliberately does not reproduce the Python control flow line for line.

## C++17 Design

The C++ implementation emphasizes explicit types, deterministic ordering, STL containers, and performance-conscious data structures.

Examples include:

- `unordered_map` for operational lookup
- `map` for ordered analytical aggregation
- `set` for dimension membership
- vectors for fact storage
- algorithms for transformation and aggregation
- typed enumerations for pipeline state

The warehouse keeps dimensions and facts separate and exposes aggregation operations through domain methods.

The implementation also avoids external libraries and uses only C++17 standard facilities.

## Java 17 Design

The Java implementation uses an enterprise-oriented domain model.

Records represent immutable domain values:

- sales records
- date dimensions
- customer dimensions
- product dimensions
- sales facts
- pipeline reports

The `Repository`, `Warehouse`, and `PipelineService` classes separate responsibilities.

The service layer owns pipeline orchestration, while domain records enforce basic invariants.

`BigDecimal` is used for monetary values instead of binary floating-point arithmetic. This avoids common rounding problems when representing financial measurements.

## Security Considerations

Data warehousing systems can contain sensitive business information even when the demonstration data is not sensitive.

Important controls include:

- least-privilege database roles
- separation between operational and analytical permissions
- parameterized SQL for application-generated queries
- validation at ingestion boundaries
- controlled access to warehouse tables
- audit logging for pipeline executions
- protection of exported extracts
- encryption in transit
- encryption at rest
- controlled retention of staging data

The PostgreSQL script focuses on structural integrity rather than implementing an entire production security model.

## Operational Reliability

A production pipeline should make partial failure visible.

Useful operational measurements include:

| Metric | Meaning |
|---|---|
| Extracted rows | Records read from the source |
| Rejected rows | Records that failed validation |
| Loaded rows | Records successfully written to the warehouse |
| Pipeline state | Current execution outcome |
| Rejection reason | Explanation for rejected data |
| Start time | Beginning of execution |
| Completion time | End of execution |

The PostgreSQL schema persists these concepts through `pipeline_runs` and `pipeline_rejections`.

A production implementation would normally also track batch identifiers, source watermarks, retry attempts, checksums, and lineage metadata.

## Edge Cases

The implementations explicitly address several edge cases:

- duplicate order identifiers
- zero quantities
- negative quantities
- negative prices
- missing regions
- invalid date formats
- missing dimension references
- duplicate fact loading
- unsupported pipeline strategies
- empty analytical input
- invalid analytical column requests

These cases matter because warehouse correctness depends on the quality of the ingestion boundary as much as the correctness of analytical queries.

## ETL Versus ELT Decision Factors

| Factor | ETL | ELT |
|---|---|---|
| Transformation location | Outside warehouse | Inside warehouse |
| Warehouse compute usage | Lower during transformation | Higher |
| Source preprocessing | Strong | Usually lighter |
| SQL-centric transformation | Optional | Central |
| Useful for complex external processing | Yes | Sometimes |
| Useful for scalable analytical platforms | Yes | Often |
| Governance requirement | Transformation layer | Warehouse transformation layer |

The correct choice depends on source-system constraints, data volume, transformation complexity, warehouse capabilities, governance requirements, and operational architecture.

## OLTP Versus OLAP Design Tradeoff

An operational database and a warehouse solve different problems.

A normalized operational schema minimizes unnecessary duplication and supports consistent transactional updates.

A dimensional analytical model intentionally organizes data around facts and dimensions to make analytical queries easier to execute and understand.

The two systems can therefore contain related information without having identical schemas.

A typical architecture is:

    Applications
         |
         v
       OLTP
         |
      Extract
         |
    ETL / ELT
         |
         v
    Data Warehouse
         |
         v
       OLAP
         |
         v
     Reporting

## Limitations

The implementations are educational models rather than distributed production data platforms.

They do not implement:

- distributed warehouse nodes
- real object-storage ingestion
- streaming ingestion
- distributed transactions
- physical columnar storage
- compression codecs
- query-vectorization engines
- change-data-capture infrastructure
- production orchestration
- enterprise identity management
- full data-lineage platforms

The columnar examples demonstrate the analytical principle of reading only required fields. They do not change the physical storage layout of Python, JavaScript, C++, Java, or PostgreSQL.

The ETL and ELT implementations demonstrate processing strategies but do not constitute a complete production scheduler.

## Practical Workflow

A realistic small warehouse workflow represented by the artifact is:

    1. Capture operational transaction
    2. Validate source constraints
    3. Extract source records
    4. Track pipeline execution
    5. Reject invalid records with reasons
    6. Normalize and transform data
    7. Populate dimensions
    8. Populate fact records
    9. Run analytical aggregations
   10. Inspect query performance
   11. Report analytical results

The most important architectural boundary is the separation between operational transaction state and analytical state.

A transaction system records what happened.

A warehouse organizes historical business events so that large-scale analytical questions can be answered efficiently.
