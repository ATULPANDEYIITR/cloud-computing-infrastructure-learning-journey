/*
 * Security Monitoring and Auditing
 *
 * Java 17
 *
 * Enterprise security monitoring architecture:
 * - Domain records and immutable events
 * - Role-based access control
 * - Audit hash chains
 * - Event validation
 * - Sliding-window anomaly detection
 * - Security alert management
 * - Analyst assignment
 * - Statistical anomaly detection
 * - Merge-independent security policy enforcement
 *
 * Save as SecurityMonitoring.java
 * Compile: javac SecurityMonitoring.java
 * Run: java SecurityMonitoring
 */

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

import java.time.Duration;
import java.time.Instant;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

// ============================================================
// MAIN ENTERPRISE APPLICATION
// ============================================================

public class SecurityMonitoring {

    // ========================================================
    // ENUMS
    // ========================================================

    enum EventType {
        LOGIN_SUCCESS,
        LOGIN_FAILURE,
        LOGOUT,
        ACCESS_GRANTED,
        ACCESS_DENIED,
        PRIVILEGE_CHANGE,
        DATA_EXPORT,
        CONFIGURATION_CHANGE,
        PASSWORD_CHANGE,
        FIREWALL_CHANGE
    }

    enum Severity {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    enum AlertStatus {
        OPEN,
        INVESTIGATING,
        RESOLVED,
        FALSE_POSITIVE
    }

    // ========================================================
    // CUSTOM EXCEPTIONS
    // ========================================================

    static class SecurityException extends RuntimeException {

        SecurityException(String message) {
            super(message);
        }
    }

    static class AuthorizationException extends SecurityException {

        AuthorizationException(String message) {
            super(message);
        }
    }

    static class AuditException extends SecurityException {

        AuditException(String message) {
            super(message);
        }
    }

    // ========================================================
    // DOMAIN RECORDS
    // ========================================================

    record SecurityEvent(
        String id,
        Instant timestamp,
        EventType type,
        String userId,
        String sourceIP,
        String resource,
        boolean success,
        Map<String, String> details
    ) {

        SecurityEvent {

            Objects.requireNonNull(id);
            Objects.requireNonNull(timestamp);
            Objects.requireNonNull(type);
            Objects.requireNonNull(details);

            if (id.isBlank() || id.length() > 128) {
                throw new IllegalArgumentException("Invalid event ID");
            }

            if (userId == null || userId.isBlank() || userId.length() > 128) {
                throw new IllegalArgumentException("Invalid user ID");
            }

            if (sourceIP == null || sourceIP.isBlank() || sourceIP.length() > 45) {
                throw new IllegalArgumentException("Invalid source IP");
            }

            if (resource == null || resource.isBlank() || resource.length() > 512) {
                throw new IllegalArgumentException("Invalid resource");
            }

            if (details.size() > 30) {
                throw new IllegalArgumentException("Too many event attributes");
            }

            details.forEach((key, value) -> {
                if (
                    key == null ||
                    value == null ||
                    key.length() > 128 ||
                    value.length() > 2048
                ) {
                    throw new IllegalArgumentException(
                        "Invalid event attribute"
                    );
                }
            });

            details = Map.copyOf(details);
        }

        static SecurityEvent create(
            EventType type,
            String userId,
            String sourceIP,
            String resource,
            boolean success,
            Map<String, String> details,
            Instant timestamp
        ) {

            return new SecurityEvent(
                UUID.randomUUID().toString(),
                timestamp,
                type,
                userId,
                sourceIP,
                resource,
                success,
                details
            );
        }
    }

    record DetectionResult(
        String eventId,
        double score,
        Severity severity,
        List<String> anomalies
    ) {

        DetectionResult {
            anomalies = List.copyOf(anomalies);
        }
    }

    record AuditRecord(
        SecurityEvent event,
        String previousHash,
        String currentHash
    ) {}

    record SecurityAlert(
        String id,
        Instant timestamp,
        String userId,
        Severity severity,
        double score,
        List<String> categories,
        List<String> evidence,
        AlertStatus status,
        String assignedTo
    ) {

        SecurityAlert {
            categories = List.copyOf(categories);
            evidence = List.copyOf(evidence);
        }

        SecurityAlert withStatus(
            AlertStatus newStatus,
            String analyst
        ) {

            return new SecurityAlert(
                id,
                timestamp,
                userId,
                severity,
                score,
                categories,
                evidence,
                newStatus,
                analyst == null ? assignedTo : analyst
            );
        }
    }

    // ========================================================
    // HASH UTILITY
    // ========================================================

    static class HashUtility {

        static String sha256(String input) {

            try {

                MessageDigest digest = MessageDigest.getInstance(
                    "SHA-256"
                );

                byte[] result = digest.digest(
                    input.getBytes(StandardCharsets.UTF_8)
                );

                StringBuilder output = new StringBuilder();

                for (byte value : result) {
                    output.append(
                        String.format("%02x", value & 0xff)
                    );
                }

                return output.toString();

            } catch (NoSuchAlgorithmException exception) {

                throw new AuditException(
                    "SHA-256 is unavailable"
                );
            }
        }
    }

    // ========================================================
    // CANONICAL EVENT SERIALIZATION
    // ========================================================

    static String serialize(SecurityEvent event) {

        StringBuilder result = new StringBuilder();

        result.append(event.id()).append('|');
        result.append(event.timestamp()).append('|');
        result.append(event.type()).append('|');
        result.append(event.userId()).append('|');
        result.append(event.sourceIP()).append('|');
        result.append(event.resource()).append('|');
        result.append(event.success());

        event.details()
            .entrySet()
            .stream()
            .sorted(Map.Entry.comparingByKey())
            .forEach(entry -> result
                .append('|')
                .append(entry.getKey())
                .append('=')
                .append(entry.getValue())
            );

        return result.toString();
    }

    // ========================================================
    // AUDIT SERVICE
    // ========================================================

    static class AuditService {

        private final List<AuditRecord> records = new ArrayList<>();

        private final Set<String> eventIds = new HashSet<>();

        private String previousHash = "0".repeat(64);

        public synchronized AuditRecord append(
            SecurityEvent event
        ) {

            if (eventIds.contains(event.id())) {
                throw new AuditException("Duplicate audit event");
            }

            String canonical = serialize(event);

            String currentHash = HashUtility.sha256(
                previousHash + canonical
            );

            AuditRecord record = new AuditRecord(
                event,
                previousHash,
                currentHash
            );

            records.add(record);

            eventIds.add(event.id());

            previousHash = currentHash;

            return record;
        }

        public synchronized boolean verify() {

            String expectedPrevious = "0".repeat(64);

            Set<String> identifiers = new HashSet<>();

            for (AuditRecord record : records) {

                if (!record.previousHash().equals(expectedPrevious)) {
                    return false;
                }

                if (!identifiers.add(record.event().id())) {
                    return false;
                }

                String expected = HashUtility.sha256(
                    expectedPrevious + serialize(record.event())
                );

                if (!expected.equals(record.currentHash())) {
                    return false;
                }

                expectedPrevious = record.currentHash();
            }

            return expectedPrevious.equals(previousHash);
        }

        public synchronized List<AuditRecord> getRecords() {

            return Collections.unmodifiableList(
                new ArrayList<>(records)
            );
        }

        public synchronized int size() {
            return records.size();
        }
    }

    // ========================================================
    // ROLE-BASED ACCESS CONTROL
    // ========================================================

    interface AccessPolicy {

        boolean authorize(String userId, String resource);
    }

    static class RoleBasedAccessPolicy implements AccessPolicy {

        private final Map<String, Set<String>> userRoles =
            new HashMap<>();

        private final Map<String, Set<String>> permissions =
            new HashMap<>();

        RoleBasedAccessPolicy() {

            userRoles.put(
                "alice",
                Set.of("developer")
            );

            userRoles.put(
                "bob",
                Set.of("administrator")
            );

            userRoles.put(
                "carol",
                Set.of("auditor")
            );

            userRoles.put(
                "david",
                Set.of("analyst")
            );

            permissions.put(
                "/admin",
                Set.of("administrator")
            );

            permissions.put(
                "/database",
                Set.of("administrator", "developer")
            );

            permissions.put(
                "/credentials",
                Set.of("administrator")
            );

            permissions.put(
                "/financial-records",
                Set.of("administrator", "auditor")
            );

            permissions.put(
                "/reports",
                Set.of("administrator", "auditor", "analyst")
            );

            permissions.put(
                "/application",
                Set.of("administrator", "developer", "analyst")
            );
        }

        @Override
        public boolean authorize(
            String userId,
            String resource
        ) {

            Set<String> roles = userRoles.get(userId);
            Set<String> required = permissions.get(resource);

            if (roles == null || required == null) {
                return false;
            }

            return roles.stream().anyMatch(required::contains);
        }

        public void changeRole(
            String userId,
            String newRole
        ) {

            if (!userRoles.containsKey(userId)) {
                throw new SecurityException("Unknown user");
            }

            if (!Set.of(
                "administrator",
                "developer",
                "auditor",
                "analyst"
            ).contains(newRole)) {
                throw new SecurityException("Invalid role");
            }

            userRoles.put(userId, Set.of(newRole));
        }
    }

    // ========================================================
    // ANOMALY DETECTION SERVICE
    // ========================================================

    static class AnomalyDetectionService {

        private final Deque<SecurityEvent> events =
            new ArrayDeque<>();

        private final Duration window = Duration.ofMinutes(10);

        private final int failureThreshold = 5;

        private final int exportThreshold = 1000;

        private final int frequencyThreshold = 30;

        public synchronized DetectionResult analyze(
            SecurityEvent event
        ) {

            Instant cutoff = event.timestamp().minus(window);

            while (
                !events.isEmpty() &&
                events.peekFirst().timestamp().isBefore(cutoff)
            ) {
                events.removeFirst();
            }

            events.addLast(event);

            List<SecurityEvent> relevant = events.stream()
                .filter(item ->
                    item.userId().equals(event.userId())
                )
                .toList();

            List<String> anomalies = new ArrayList<>();

            double score = 0;

            long failedLogins = relevant.stream()
                .filter(item ->
                    item.type() == EventType.LOGIN_FAILURE
                )
                .count();

            if (failedLogins >= failureThreshold) {

                anomalies.add(
                    "REPEATED_FAILED_AUTHENTICATION"
                );

                score += 0.40;
            }

            long uniqueIPs = relevant.stream()
                .filter(item ->
                    item.type() == EventType.LOGIN_SUCCESS ||
                    item.type() == EventType.LOGIN_FAILURE
                )
                .map(SecurityEvent::sourceIP)
                .distinct()
                .count();

            if (uniqueIPs >= 3) {

                anomalies.add(
                    "MULTIPLE_SOURCE_IP_ADDRESSES"
                );

                score += 0.25;
            }

            if (
                event.type() == EventType.ACCESS_DENIED &&
                Set.of(
                    "/admin",
                    "/database",
                    "/credentials",
                    "/financial-records",
                    "/security-configuration"
                ).contains(event.resource())
            ) {

                anomalies.add(
                    "SENSITIVE_RESOURCE_ACCESS_DENIED"
                );

                score += 0.30;
            }

            if (event.type() == EventType.PRIVILEGE_CHANGE) {

                anomalies.add("PRIVILEGE_CHANGE");

                score += 0.50;
            }

            if (event.type() == EventType.DATA_EXPORT) {

                String rawCount = event.details().get("recordCount");

                try {

                    int count = Integer.parseInt(rawCount);

                    if (count < 0) {
                        throw new NumberFormatException();
                    }

                    if (count > exportThreshold) {

                        anomalies.add("UNUSUAL_DATA_EXPORT");

                        score += 0.45;
                    }

                } catch (RuntimeException exception) {

                    throw new IllegalArgumentException(
                        "Invalid data export count"
                    );
                }
            }

            if (relevant.size() > frequencyThreshold) {

                anomalies.add("HIGH_EVENT_FREQUENCY");

                score += 0.30;
            }

            score = Math.min(score, 1.0);

            Severity severity =
                score >= 0.75 ? Severity.CRITICAL :
                score >= 0.50 ? Severity.HIGH :
                score >= 0.25 ? Severity.MEDIUM :
                Severity.LOW;

            return new DetectionResult(
                event.id(),
                score,
                severity,
                anomalies
            );
        }
    }

    // ========================================================
    // ALERT MANAGEMENT SERVICE
    // ========================================================

    static class AlertManagementService {

        private final Map<String, SecurityAlert> alerts =
            new LinkedHashMap<>();

        public synchronized Optional<SecurityAlert> create(
            DetectionResult detection,
            SecurityEvent event
        ) {

            if (detection.anomalies().isEmpty()) {
                return Optional.empty();
            }

            SecurityAlert alert = new SecurityAlert(
                UUID.randomUUID().toString(),
                Instant.now(),
                event.userId(),
                detection.severity(),
                detection.score(),
                detection.anomalies(),
                List.of(event.id()),
                AlertStatus.OPEN,
                null
            );

            alerts.put(alert.id(), alert);

            return Optional.of(alert);
        }

        public synchronized SecurityAlert update(
            String alertId,
            AlertStatus newStatus,
            String analyst
        ) {

            SecurityAlert alert = alerts.get(alertId);

            if (alert == null) {
                throw new SecurityException("Alert not found");
            }

            if (
                alert.status() == AlertStatus.RESOLVED ||
                alert.status() == AlertStatus.FALSE_POSITIVE
            ) {
                throw new SecurityException(
                    "Closed alerts cannot be changed"
                );
            }

            if (
                newStatus == AlertStatus.INVESTIGATING &&
                (analyst == null || analyst.isBlank())
            ) {
                throw new SecurityException(
                    "Investigation requires an analyst"
                );
            }

            SecurityAlert updated = alert.withStatus(
                newStatus,
                analyst
            );

            alerts.put(alertId, updated);

            return updated;
        }

        public synchronized List<SecurityAlert> getAlerts() {

            return alerts.values()
                .stream()
                .sorted(
                    Comparator.comparing(
                        SecurityAlert::timestamp
                    )
                )
                .toList();
        }

        public synchronized Map<Severity, Long> severityReport() {

            return alerts.values()
                .stream()
                .collect(
                    Collectors.groupingBy(
                        SecurityAlert::severity,
                        () -> new EnumMap<>(Severity.class),
                        Collectors.counting()
                    )
                );
        }
    }

    // ========================================================
    // MONITORING APPLICATION SERVICE
    // ========================================================

    static class SecurityMonitoringService {

        private final AuditService auditService =
            new AuditService();

        private final AccessPolicy accessPolicy =
            new RoleBasedAccessPolicy();

        private final AnomalyDetectionService detector =
            new AnomalyDetectionService();

        private final AlertManagementService alertService =
            new AlertManagementService();

        private final Map<EventType, Long> eventCounts =
            new EnumMap<>(EventType.class);

        private final Set<String> processedEvents =
            new HashSet<>();

        public synchronized Optional<SecurityAlert> process(
            SecurityEvent event
        ) {

            if (processedEvents.contains(event.id())) {
                throw new SecurityException("Duplicate event");
            }

            if (
                event.type() == EventType.ACCESS_GRANTED &&
                !accessPolicy.authorize(
                    event.userId(),
                    event.resource()
                )
            ) {
                throw new AuthorizationException(
                    "Unauthorized access recorded as granted"
                );
            }

            // Audit persistence is performed before detection.
            auditService.append(event);

            processedEvents.add(event.id());

            eventCounts.merge(
                event.type(),
                1L,
                Long::sum
            );

            DetectionResult detection = detector.analyze(event);

            return alertService.create(
                detection,
                event
            );
        }

        public void printReport() {

            System.out.println("\nSECURITY MONITORING REPORT");

            System.out.println(
                "Audit records: " + auditService.size()
            );

            System.out.println(
                "Audit integrity: " + auditService.verify()
            );

            System.out.println(
                "Total alerts: " + alertService.getAlerts().size()
            );

            System.out.println("\nSEVERITY DISTRIBUTION");

            alertService.severityReport().forEach(
                (severity, count) ->
                    System.out.println(
                        severity + ": " + count
                    )
            );

            System.out.println("\nEVENT DISTRIBUTION");

            eventCounts.forEach(
                (type, count) ->
                    System.out.println(
                        type + ": " + count
                    )
            );
        }

        AuditService audit() {
            return auditService;
        }

        AlertManagementService alerts() {
            return alertService;
        }

        AccessPolicy access() {
            return accessPolicy;
        }
    }

    // ========================================================
    // STATISTICAL ANOMALY DETECTION
    // ========================================================

    static List<Integer> detectStatisticalAnomalies(
        List<Double> values,
        double threshold
    ) {

        if (
            values.size() < 2 ||
            threshold <= 0 ||
            values.stream().anyMatch(
                value -> value == null || !Double.isFinite(value)
            )
        ) {
            throw new IllegalArgumentException(
                "Invalid statistical observations"
            );
        }

        double mean = values.stream()
            .mapToDouble(Double::doubleValue)
            .average()
            .orElseThrow();

        double variance = values.stream()
            .mapToDouble(value ->
                Math.pow(value - mean, 2)
            )
            .average()
            .orElse(0);

        double deviation = Math.sqrt(variance);

        if (deviation == 0) {
            return List.of();
        }

        List<Integer> anomalies = new ArrayList<>();

        for (int index = 0; index < values.size(); index++) {

            double zScore =
                (values.get(index) - mean) / deviation;

            if (Math.abs(zScore) > threshold) {
                anomalies.add(index);
            }
        }

        return List.copyOf(anomalies);
    }

    // ========================================================
    // SAMPLE EVENTS
    // ========================================================

    static List<SecurityEvent> sampleEvents() {

        Instant base = Instant.now();

        List<SecurityEvent> events = new ArrayList<>();

        events.add(
            SecurityEvent.create(
                EventType.LOGIN_SUCCESS,
                "alice",
                "192.168.1.10",
                "/authentication",
                true,
                Map.of(),
                base
            )
        );

        events.add(
            SecurityEvent.create(
                EventType.ACCESS_GRANTED,
                "alice",
                "192.168.1.10",
                "/application",
                true,
                Map.of(),
                base.plusSeconds(5)
            )
        );

        for (int i = 0; i < 6; i++) {

            events.add(
                SecurityEvent.create(
                    EventType.LOGIN_FAILURE,
                    "david",
                    "203.0.113.50",
                    "/authentication",
                    false,
                    Map.of("attempt", String.valueOf(i + 1)),
                    base.plusSeconds(60 + i)
                )
            );
        }

        events.add(
            SecurityEvent.create(
                EventType.ACCESS_DENIED,
                "alice",
                "192.168.1.10",
                "/credentials",
                false,
                Map.of(),
                base.plusSeconds(120)
            )
        );

        events.add(
            SecurityEvent.create(
                EventType.PRIVILEGE_CHANGE,
                "bob",
                "192.168.1.20",
                "/admin",
                true,
                Map.of(
                    "targetUser", "alice",
                    "newRole", "administrator"
                ),
                base.plusSeconds(180)
            )
        );

        events.add(
            SecurityEvent.create(
                EventType.DATA_EXPORT,
                "david",
                "203.0.113.50",
                "/financial-records",
                true,
                Map.of("recordCount", "5000"),
                base.plusSeconds(240)
            )
        );

        return List.copyOf(events);
    }

    // ========================================================
    // TESTS
    // ========================================================

    static void runTests() {

        SecurityMonitoringService service =
            new SecurityMonitoringService();

        List<SecurityEvent> events = sampleEvents();

        for (SecurityEvent event : events) {
            service.process(event);
        }

        if (service.audit().size() != events.size()) {
            throw new AssertionError("Audit count test failed");
        }

        if (!service.audit().verify()) {
            throw new AssertionError("Audit integrity test failed");
        }

        if (service.alerts().getAlerts().size() < 3) {
            throw new AssertionError("Alert generation test failed");
        }

        if (!service.access().authorize("alice", "/application")) {
            throw new AssertionError("Access authorization failed");
        }

        if (service.access().authorize("alice", "/credentials")) {
            throw new AssertionError("Access denial failed");
        }

        boolean duplicateRejected = false;

        try {
            service.process(events.get(0));
        } catch (SecurityException exception) {
            duplicateRejected = true;
        }

        if (!duplicateRejected) {
            throw new AssertionError("Duplicate event accepted");
        }

        List<Integer> anomalies = detectStatisticalAnomalies(
            List.of(10.0, 11.0, 10.0, 12.0, 100.0),
            1.5
        );

        if (!anomalies.equals(List.of(4))) {
            throw new AssertionError("Statistical test failed");
        }

        SecurityAlert alert = service.alerts()
            .getAlerts()
            .get(0);

        service.alerts().update(
            alert.id(),
            AlertStatus.INVESTIGATING,
            "security-analyst-01"
        );

        System.out.println("All Java 17 tests passed.");
    }

    // ========================================================
    // MAIN
    // ========================================================

    public static void main(String[] args) {

        try {

            SecurityMonitoringService service =
                new SecurityMonitoringService();

            for (SecurityEvent event : sampleEvents()) {

                Optional<SecurityAlert> alert =
                    service.process(event);

                alert.ifPresent(item -> {

                    System.out.println(
                        "[" + item.severity() + "] " +
                        String.join(", ", item.categories()) +
                        " | User: " + item.userId()
                    );
                });
            }

            service.printReport();

            System.out.println("\nSTATISTICAL ANOMALIES");

            System.out.println(
                detectStatisticalAnomalies(
                    List.of(
                        12.0, 13.0, 11.0, 12.0,
                        14.0, 13.0, 90.0
                    ),
                    2.0
                )
            );

            runTests();

        } catch (RuntimeException exception) {

            System.err.println(
                "Security monitoring failure: " +
                exception.getMessage()
            );

            System.exit(1);
        }
    }
}
