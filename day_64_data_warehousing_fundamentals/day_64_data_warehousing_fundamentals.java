import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

public class DataWarehousingDemo {

    enum LoadStrategy {
        ETL,
        ELT
    }

    enum PipelineState {
        CREATED,
        EXTRACTED,
        VALIDATED,
        LOADED,
        FAILED
    }

    record SalesRecord(
            long orderId,
            LocalDate orderDate,
            long customerId,
            long productId,
            String region,
            int quantity,
            BigDecimal unitPrice) {

        SalesRecord {
            Objects.requireNonNull(orderDate, "orderDate");
            Objects.requireNonNull(region, "region");
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (orderId <= 0) {
                throw new ValidationException("orderId must be positive");
            }
            if (customerId <= 0 || productId <= 0) {
                throw new ValidationException("dimension IDs must be positive");
            }
            if (region.isBlank()) {
                throw new ValidationException("region is required");
            }
            if (quantity <= 0) {
                throw new ValidationException("quantity must be positive");
            }
            if (unitPrice.signum() < 0) {
                throw new ValidationException("unitPrice cannot be negative");
            }
        }

        BigDecimal revenue() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity))
                    .setScale(2, RoundingMode.HALF_UP);
        }
    }

    record DateDimension(
            int dateKey,
            LocalDate date,
            int year,
            int month,
            int quarter) {
    }

    record CustomerDimension(
            long customerId,
            String segment) {
    }

    record ProductDimension(
            long productId,
            String category) {
    }

    record SalesFact(
            long orderId,
            int dateKey,
            long customerId,
            long productId,
            String region,
            int quantity,
            BigDecimal revenue) {
    }

    static final class ValidationException extends RuntimeException {
        ValidationException(String message) {
            super(message);
        }
    }

    static final class PipelineException extends RuntimeException {
        PipelineException(String message) {
            super(message);
        }
    }

    static final class Repository {
        private final Map<Long, SalesRecord> orders = new LinkedHashMap<>();

        void insert(SalesRecord record) {
            if (orders.containsKey(record.orderId())) {
                throw new ValidationException(
                        "Duplicate order: " + record.orderId());
            }
            orders.put(record.orderId(), record);
        }

        List<SalesRecord> extract() {
            return orders.values().stream()
                    .sorted(Comparator.comparingLong(SalesRecord::orderId))
                    .toList();
        }
    }

    static final class Warehouse {
        private final Map<Integer, DateDimension> dates = new HashMap<>();
        private final Map<Long, CustomerDimension> customers = new HashMap<>();
        private final Map<Long, ProductDimension> products = new HashMap<>();
        private final Map<Long, SalesFact> facts = new LinkedHashMap<>();

        void loadDimensions(List<SalesRecord> records) {
            for (SalesRecord record : records) {
                int key = dateKey(record.orderDate());

                dates.putIfAbsent(
                        key,
                        new DateDimension(
                                key,
                                record.orderDate(),
                                record.orderDate().getYear(),
                                record.orderDate().getMonthValue(),
                                record.orderDate().getMonthValue() <= 3
                                        ? 1
                                        : ((record.orderDate().getMonthValue() - 1) / 3) + 1
                        )
                );

                customers.putIfAbsent(
                        record.customerId(),
                        new CustomerDimension(
                                record.customerId(), "Business"));
                products.putIfAbsent(
                        record.productId(),
                        new ProductDimension(
                                record.productId(), "General"));
            }
        }

        void loadFacts(List<SalesRecord> records) {
            for (SalesRecord record : records) {
                if (facts.containsKey(record.orderId())) {
                    throw new PipelineException(
                            "Fact already exists: " + record.orderId());
                }

                facts.put(
                        record.orderId(),
                        new SalesFact(
                                record.orderId(),
                                dateKey(record.orderDate()),
                                record.customerId(),
                                record.productId(),
                                record.region(),
                                record.quantity(),
                                record.revenue()
                        )
                );
            }
        }

        Map<String, BigDecimal> revenueByRegion() {
            Map<String, BigDecimal> totals = new TreeMap<>();

            facts.values().forEach(fact ->
                    totals.merge(
                            fact.region(),
                            fact.revenue(),
                            BigDecimal::add));

            return totals;
        }

        Map<String, BigDecimal> revenueByMonth() {
            Map<String, BigDecimal> totals = new TreeMap<>();

            facts.values().forEach(fact -> {
                DateDimension date = dates.get(fact.dateKey());
                String month = String.format(
                        "%04d-%02d",
                        date.year(),
                        date.month());

                totals.merge(
                        month,
                        fact.revenue(),
                        BigDecimal::add);
            });

            return totals;
        }

        List<SalesFact> highValueFacts(BigDecimal threshold) {
            return facts.values().stream()
                    .filter(f -> f.revenue().compareTo(threshold) >= 0)
                    .toList();
        }

        private static int dateKey(LocalDate date) {
            return date.getYear() * 10_000
                    + date.getMonthValue() * 100
                    + date.getDayOfMonth();
        }
    }

    record PipelineReport(
            PipelineState state,
            int extracted,
            int rejected,
            int loaded,
            List<String> errors) {
    }

    static final class PipelineService {
        private final Repository source;
        private final Warehouse warehouse;

        PipelineService(Repository source, Warehouse warehouse) {
            this.source = source;
            this.warehouse = warehouse;
        }

        PipelineReport execute(LoadStrategy strategy) {
            List<String> errors = new ArrayList<>();
            int rejected = 0;

            try {
                List<SalesRecord> extracted = source.extract();
                List<SalesRecord> valid = new ArrayList<>();

                for (SalesRecord record : extracted) {
                    try {
                        valid.add(normalize(record));
                    } catch (RuntimeException ex) {
                        rejected++;
                        errors.add(
                                "Order " + record.orderId()
                                        + ": " + ex.getMessage());
                    }
                }

                if (strategy == LoadStrategy.ETL) {
                    warehouse.loadDimensions(valid);
                    warehouse.loadFacts(valid);
                } else if (strategy == LoadStrategy.ELT) {
                    warehouse.loadDimensions(extracted);
                    warehouse.loadFacts(valid);
                } else {
                    throw new PipelineException(
                            "Unsupported load strategy");
                }

                return new PipelineReport(
                        PipelineState.LOADED,
                        extracted.size(),
                        rejected,
                        valid.size(),
                        List.copyOf(errors));
            } catch (RuntimeException ex) {
                errors.add(ex.getMessage());

                return new PipelineReport(
                        PipelineState.FAILED,
                        0,
                        rejected,
                        0,
                        List.copyOf(errors));
            }
        }

        private SalesRecord normalize(SalesRecord record) {
            String normalizedRegion =
                    record.region().trim().replaceAll("\\s+", " ");

            return new SalesRecord(
                    record.orderId(),
                    record.orderDate(),
                    record.customerId(),
                    record.productId(),
                    normalizedRegion,
                    record.quantity(),
                    record.unitPrice().setScale(
                            2,
                            RoundingMode.HALF_UP));
        }
    }

    static void printReport(PipelineReport report) {
        System.out.println("Pipeline state: " + report.state());
        System.out.println("Extracted: " + report.extracted());
        System.out.println("Rejected: " + report.rejected());
        System.out.println("Loaded: " + report.loaded());

        if (!report.errors().isEmpty()) {
            System.out.println("Errors:");
            report.errors().forEach(error ->
                    System.out.println("  " + error));
        }
    }

    public static void main(String[] args) {
        Repository source = new Repository();

        source.insert(new SalesRecord(
                4001,
                LocalDate.of(2026, 1, 10),
                901,
                5001,
                "North",
                5,
                new BigDecimal("120.00")));

        source.insert(new SalesRecord(
                4002,
                LocalDate.of(2026, 1, 15),
                902,
                5002,
                "South",
                3,
                new BigDecimal("250.00")));

        source.insert(new SalesRecord(
                4003,
                LocalDate.of(2026, 2, 3),
                901,
                5001,
                "North",
                7,
                new BigDecimal("120.00")));

        source.insert(new SalesRecord(
                4004,
                LocalDate.of(2026, 2, 19),
                903,
                5003,
                "West",
                2,
                new BigDecimal("450.00")));

        source.insert(new SalesRecord(
                4005,
                LocalDate.of(2026, 3, 4),
                904,
                5002,
                "East",
                4,
                new BigDecimal("250.00")));

        try {
            source.insert(new SalesRecord(
                    4006,
                    LocalDate.of(2026, 3, 7),
                    905,
                    5004,
                    "North",
                    0,
                    new BigDecimal("90.00")));
        } catch (ValidationException ex) {
            System.out.println(
                    "Invalid transaction rejected: " + ex.getMessage());
        }

        Warehouse warehouse = new Warehouse();
        PipelineService service =
                new PipelineService(source, warehouse);

        PipelineReport report = service.execute(LoadStrategy.ETL);

        System.out.println();
        printReport(report);

        System.out.println("\nRevenue by region:");
        warehouse.revenueByRegion().forEach(
                (region, revenue) ->
                        System.out.println(
                                "  " + region + ": " + revenue));

        System.out.println("\nRevenue by month:");
        warehouse.revenueByMonth().forEach(
                (month, revenue) ->
                        System.out.println(
                                "  " + month + ": " + revenue));

        System.out.println("\nHigh-value facts:");
        warehouse.highValueFacts(new BigDecimal("500.00"))
                .forEach(fact ->
                        System.out.println(
                                "  order=" + fact.orderId()
                                        + ", region=" + fact.region()
                                        + ", revenue=" + fact.revenue()));

        System.out.println(
                "\nSupported pipeline states: "
                        + EnumSet.allOf(PipelineState.class).size());
    }
}
