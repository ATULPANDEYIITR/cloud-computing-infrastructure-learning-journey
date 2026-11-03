"use strict";

const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const EventEmitter = require("node:events");

const LoadStrategy = Object.freeze({
  ETL: "ETL",
  ELT: "ELT",
});

const PipelineState = Object.freeze({
  CREATED: "created",
  EXTRACTED: "extracted",
  VALIDATED: "validated",
  LOADED: "loaded",
  FAILED: "failed",
});

class ValidationError extends Error {}
class PipelineError extends Error {}

class SalesRecord {
  constructor({
    orderId,
    orderDate,
    customerId,
    productId,
    region,
    quantity,
    unitPrice,
  }) {
    this.orderId = orderId;
    this.orderDate = orderDate;
    this.customerId = customerId;
    this.productId = productId;
    this.region = region;
    this.quantity = quantity;
    this.unitPrice = unitPrice;
  }

  get revenue() {
    return this.quantity * this.unitPrice;
  }
}

class OLTPStore {
  constructor() {
    this.orders = new Map();
  }

  insert(record) {
    validateRecord(record);

    if (this.orders.has(record.orderId)) {
      throw new ValidationError(`Duplicate order: ${record.orderId}`);
    }

    this.orders.set(record.orderId, record);
  }

  extract() {
    return [...this.orders.values()];
  }
}

class Warehouse {
  constructor() {
    this.dimDate = new Map();
    this.dimCustomer = new Map();
    this.dimProduct = new Map();
    this.factSales = new Map();
  }

  static dateKey(dateText) {
    return Number(dateText.replaceAll("-", ""));
  }

  loadDimensions(records) {
    for (const record of records) {
      const date = new Date(`${record.orderDate}T00:00:00Z`);
      const key = Warehouse.dateKey(record.orderDate);

      this.dimDate.set(key, {
        date: record.orderDate,
        year: date.getUTCFullYear(),
        month: date.getUTCMonth() + 1,
        quarter: Math.floor(date.getUTCMonth() / 3) + 1,
      });

      if (!this.dimCustomer.has(record.customerId)) {
        this.dimCustomer.set(record.customerId, {
          customerId: record.customerId,
          segment: "Business",
        });
      }

      if (!this.dimProduct.has(record.productId)) {
        this.dimProduct.set(record.productId, {
          productId: record.productId,
          category: "General",
        });
      }
    }
  }

  loadFacts(records) {
    for (const record of records) {
      if (this.factSales.has(record.orderId)) {
        throw new PipelineError(
          `Fact already exists for order ${record.orderId}`
        );
      }

      this.factSales.set(record.orderId, {
        orderId: record.orderId,
        dateKey: Warehouse.dateKey(record.orderDate),
        customerId: record.customerId,
        productId: record.productId,
        region: record.region,
        quantity: record.quantity,
        revenue: Number(record.revenue.toFixed(2)),
      });
    }
  }

  aggregateByRegion() {
    const totals = new Map();

    for (const fact of this.factSales.values()) {
      totals.set(
        fact.region,
        (totals.get(fact.region) ?? 0) + fact.revenue
      );
    }

    return new Map(
      [...totals.entries()].sort(([a], [b]) => a.localeCompare(b))
    );
  }

  aggregateByMonth() {
    const totals = new Map();

    for (const fact of this.factSales.values()) {
      const month = this.dimDate.get(fact.dateKey).date.slice(0, 7);
      totals.set(month, (totals.get(month) ?? 0) + fact.revenue);
    }

    return new Map(
      [...totals.entries()].sort(([a], [b]) => a.localeCompare(b))
    );
  }
}

function validateRecord(record) {
  if (!Number.isInteger(record.orderId) || record.orderId <= 0) {
    throw new ValidationError("orderId must be a positive integer");
  }

  if (!/^\d{4}-\d{2}-\d{2}$/.test(record.orderDate)) {
    throw new ValidationError("orderDate must use YYYY-MM-DD");
  }

  const parsedDate = new Date(`${record.orderDate}T00:00:00Z`);
  if (Number.isNaN(parsedDate.getTime())) {
    throw new ValidationError("Invalid order date");
  }

  if (!Number.isInteger(record.customerId) || record.customerId <= 0) {
    throw new ValidationError("customerId must be positive");
  }

  if (!Number.isInteger(record.productId) || record.productId <= 0) {
    throw new ValidationError("productId must be positive");
  }

  if (typeof record.region !== "string" || !record.region.trim()) {
    throw new ValidationError("region is required");
  }

  if (!Number.isInteger(record.quantity) || record.quantity <= 0) {
    throw new ValidationError("quantity must be positive");
  }

  if (!Number.isFinite(record.unitPrice) || record.unitPrice < 0) {
    throw new ValidationError("unitPrice must be non-negative");
  }
}

function normalize(record) {
  return new SalesRecord({
    orderId: record.orderId,
    orderDate: record.orderDate,
    customerId: record.customerId,
    productId: record.productId,
    region: record.region.trim().replace(/\s+/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
    quantity: record.quantity,
    unitPrice: Number(record.unitPrice.toFixed(2)),
  });
}

class Pipeline extends EventEmitter {
  constructor(source, warehouse, strategy) {
    super();
    this.source = source;
    this.warehouse = warehouse;
    this.strategy = strategy;
    this.state = PipelineState.CREATED;
    this.metrics = {
      extracted: 0,
      rejected: 0,
      loaded: 0,
      errors: [],
    };
  }

  async execute() {
    try {
      const extracted = this.source.extract();
      this.metrics.extracted = extracted.length;
      this.state = PipelineState.EXTRACTED;
      this.emit("state", this.state);

      const valid = [];

      for (const record of extracted) {
        try {
          validateRecord(record);
          valid.push(normalize(record));
        } catch (error) {
          this.metrics.rejected++;
          this.metrics.errors.push(
            `Order ${record.orderId}: ${error.message}`
          );
          this.emit("rejected", record, error);
        }
      }

      this.state = PipelineState.VALIDATED;
      this.emit("state", this.state);

      if (this.strategy === LoadStrategy.ETL) {
        this.warehouse.loadDimensions(valid);
        this.warehouse.loadFacts(valid);
      } else if (this.strategy === LoadStrategy.ELT) {
        this.warehouse.loadDimensions(extracted);
        this.warehouse.loadFacts(valid);
      } else {
        throw new PipelineError(`Unsupported strategy: ${this.strategy}`);
      }

      this.metrics.loaded = valid.length;
      this.state = PipelineState.LOADED;
      this.emit("state", this.state);

      return this.metrics;
    } catch (error) {
      this.state = PipelineState.FAILED;
      this.metrics.errors.push(error.message);
      this.emit("state", this.state);
      throw error;
    }
  }
}

function analyticalColumnScan(rows, columns, predicate) {
  if (!Array.isArray(rows)) {
    throw new TypeError("rows must be an array");
  }

  return rows
    .filter(predicate)
    .map(row => {
      const output = {};
      for (const column of columns) {
        if (!(column in row)) {
          throw new Error(`Unknown analytical column: ${column}`);
        }
        output[column] = row[column];
      }
      return output;
    });
}

async function writeExtract(fileName, records) {
  const header =
    "order_id,order_date,customer_id,product_id,region,quantity,unit_price\n";

  const lines = records.map(record =>
    [
      record.orderId,
      record.orderDate,
      record.customerId,
      record.productId,
      record.region,
      record.quantity,
      record.unitPrice.toFixed(2),
    ].join(",")
  );

  await fs.writeFile(fileName, header + lines.join("\n"), "utf8");
}

async function main() {
  const source = new OLTPStore();

  const records = [
    new SalesRecord({
      orderId: 2001,
      orderDate: "2026-01-10",
      customerId: 701,
      productId: 3001,
      region: "north",
      quantity: 5,
      unitPrice: 120,
    }),
    new SalesRecord({
      orderId: 2002,
      orderDate: "2026-01-12",
      customerId: 702,
      productId: 3002,
      region: "South",
      quantity: 3,
      unitPrice: 250,
    }),
    new SalesRecord({
      orderId: 2003,
      orderDate: "2026-02-08",
      customerId: 701,
      productId: 3001,
      region: "north",
      quantity: 7,
      unitPrice: 120,
    }),
    new SalesRecord({
      orderId: 2004,
      orderDate: "2026-02-15",
      customerId: 703,
      productId: 3003,
      region: "West",
      quantity: 2,
      unitPrice: 450,
    }),
  ];

  for (const record of records) {
    source.insert(record);
  }

  const warehouse = new Warehouse();
  const pipeline = new Pipeline(
    source,
    warehouse,
    LoadStrategy.ETL
  );

  pipeline.on("state", state => {
    console.log(`Pipeline state: ${state}`);
  });

  pipeline.on("rejected", (record, error) => {
    console.log(`Rejected ${record.orderId}: ${error.message}`);
  });

  const metrics = await pipeline.execute();

  console.log("\nPipeline metrics:");
  console.log(metrics);

  console.log("\nRevenue by region:");
  console.log(Object.fromEntries(warehouse.aggregateByRegion()));

  console.log("\nRevenue by month:");
  console.log(Object.fromEntries(warehouse.aggregateByMonth()));

  const analyticalRows = [...warehouse.factSales.values()];

  const highValue = analyticalColumnScan(
    analyticalRows,
    ["orderId", "region", "revenue"],
    row => row.revenue >= 500
  );

  console.log("\nColumnar-style projection:");
  console.log(highValue);

  const tempFile = path.join(
    os.tmpdir(),
    `warehouse_extract_${Date.now()}.csv`
  );

  await writeExtract(tempFile, records);
  console.log(`\nExtract written to ${tempFile}`);

  await fs.unlink(tempFile);
}

main().catch(error => {
  console.error(`Fatal pipeline error: ${error.message}`);
  process.exitCode = 1;
});
