import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Enterprise Container Security Governance
 *
 * Java 17
 *
 * Domain-oriented implementation:
 * - Image inventory and vulnerability management
 * - Immutable security policies
 * - CVE severity thresholds
 * - Image provenance
 * - Minimal image requirements
 * - Runtime behavior evaluation
 * - Secret exposure controls
 * - Deployment admission
 * - Audit history
 */

public class ContainerSecurity {

    enum Severity {
        CRITICAL(5),
        HIGH(4),
        MEDIUM(3),
        LOW(2),
        UNKNOWN(1);

        private final int weight;

        Severity(int weight) {
            this.weight = weight;
        }

        int weight() {
            return weight;
        }
    }

    enum Decision {
        ALLOW,
        DENY,
        REVIEW
    }

    enum ImageState {
        REGISTERED,
        SCANNED,
        APPROVED,
        BLOCKED
    }

    enum RuntimeEventType {
        PROCESS_EXECUTION,
        SHELL_EXECUTION,
        PRIVILEGED_EXECUTION,
        SECRET_ACCESS,
        FILESYSTEM_WRITE,
        NETWORK_CONNECTION
    }

    static class SecurityException extends RuntimeException {
        SecurityException(String message) {
            super(message);
        }
    }

    record Vulnerability(
        String cveId,
        String packageName,
        String installedVersion,
        String fixedVersion,
        Severity severity,
        boolean exploitable
    ) {
        private static final Pattern CVE_PATTERN =
            Pattern.compile("CVE-\\d{4}-\\d{4,}");

        Vulnerability {
            Objects.requireNonNull(cveId);
            Objects.requireNonNull(packageName);
            Objects.requireNonNull(installedVersion);
            Objects.requireNonNull(severity);

            if (!CVE_PATTERN.matcher(cveId).matches()) {
                throw new IllegalArgumentException("Invalid CVE identifier");
            }

            if (packageName.isBlank() || installedVersion.isBlank()) {
                throw new IllegalArgumentException("Invalid package metadata");
            }
        }
    }

    static final class ContainerImage {
        private final String name;
        private final String tag;
        private final String digest;
        private final String baseImage;
        private final List<String> packages;
        private final List<Vulnerability> vulnerabilities;
        private final List<String> secrets;

        private final int userId;
        private final double sizeMB;

        private final boolean privileged;
        private final boolean containsShell;
        private final boolean signatureVerified;

        private ImageState state = ImageState.REGISTERED;

        ContainerImage(
            String name,
            String tag,
            String digest,
            String baseImage,
            List<String> packages,
            List<Vulnerability> vulnerabilities,
            List<String> secrets,
            int userId,
            double sizeMB,
            boolean privileged,
            boolean containsShell,
            boolean signatureVerified
        ) {
            this.name = Objects.requireNonNull(name);
            this.tag = Objects.requireNonNull(tag);
            this.digest = Objects.requireNonNull(digest);
            this.baseImage = Objects.requireNonNull(baseImage);

            this.packages = List.copyOf(packages);
            this.vulnerabilities = List.copyOf(vulnerabilities);
            this.secrets = List.copyOf(secrets);

            this.userId = userId;
            this.sizeMB = sizeMB;
            this.privileged = privileged;
            this.containsShell = containsShell;
            this.signatureVerified = signatureVerified;

            validate();
        }

        private void validate() {
            if (name.isBlank() || tag.isBlank()) {
                throw new IllegalArgumentException("Image name and tag required");
            }

            if (!digest.matches("sha256:[a-f0-9]{64}")) {
                throw new IllegalArgumentException("Invalid image digest");
            }

            if (userId < 0 || sizeMB <= 0) {
                throw new IllegalArgumentException("Invalid image configuration");
            }
        }

        String name() {
            return name;
        }

        String digest() {
            return digest;
        }

        List<Vulnerability> vulnerabilities() {
            return vulnerabilities;
        }

        List<String> secrets() {
            return secrets;
        }

        ImageState state() {
            return state;
        }

        void updateState(ImageState newState) {
            this.state = Objects.requireNonNull(newState);
        }
    }

    record SecurityPolicy(
        int maxCritical,
        int maxHigh,
        int maxMedium,
        double maxImageSizeMB,
        boolean requireNonRoot,
        boolean forbidPrivileged,
        boolean forbidShell,
        boolean requireSignature,
        boolean requireNoSecrets,
        boolean requireFixedVulnerabilities,
        boolean blockUnknownSeverity
    ) {
        SecurityPolicy {
            if (
                maxCritical < 0 ||
                maxHigh < 0 ||
                maxMedium < 0 ||
                maxImageSizeMB <= 0
            ) {
                throw new IllegalArgumentException("Invalid policy thresholds");
            }
        }

        static SecurityPolicy production() {
            return new SecurityPolicy(
                0,
                0,
                3,
                100,
                true,
                true,
                true,
                true,
                true,
                false,
                true
            );
        }
    }

    record Finding(
        String control,
        Severity severity,
        String description,
        String remediation
    ) {}

    record ScanReport(
        String imageName,
        String digest,
        Instant scannedAt,
        Map<Severity, Integer> counts,
        List<Finding> findings,
        Decision decision
    ) {
        ScanReport {
            counts = Collections.unmodifiableMap(
                new EnumMap<>(counts)
            );
            findings = List.copyOf(findings);
        }
    }

    static final class ImageScanner {
        private final SecurityPolicy policy;

        ImageScanner(SecurityPolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        ScanReport scan(ContainerImage image) {
            Map<Severity, Integer> counts =
                new EnumMap<>(Severity.class);

            for (Severity severity : Severity.values()) {
                counts.put(severity, 0);
            }

            List<Finding> findings = new ArrayList<>();

            for (Vulnerability vulnerability : image.vulnerabilities()) {
                counts.merge(vulnerability.severity(), 1, Integer::sum);

                String remediation =
                    vulnerability.fixedVersion() == null
                    ? "Investigate mitigation or replace the package"
                    : "Upgrade to " + vulnerability.fixedVersion();

                findings.add(new Finding(
                    "CVE",
                    vulnerability.severity(),
                    vulnerability.cveId() + ": " +
                        vulnerability.packageName(),
                    remediation
                ));

                if (
                    policy.requireFixedVulnerabilities() &&
                    vulnerability.fixedVersion() == null
                ) {
                    findings.add(new Finding(
                        "UNFIXED_CVE",
                        vulnerability.severity(),
                        "No known fix for " + vulnerability.cveId(),
                        "Apply compensating controls or replace the package"
                    ));
                }

                if (
                    policy.blockUnknownSeverity() &&
                    vulnerability.severity() == Severity.UNKNOWN
                ) {
                    findings.add(new Finding(
                        "UNKNOWN_SEVERITY",
                        Severity.HIGH,
                        vulnerability.cveId(),
                        "Investigate vulnerability classification"
                    ));
                }
            }

            if (policy.requireNonRoot() && image.userId == 0) {
                findings.add(new Finding(
                    "NON_ROOT",
                    Severity.HIGH,
                    "Container runs as root",
                    "Configure a dedicated non-root UID"
                ));
            }

            if (policy.forbidPrivileged() && image.privileged) {
                findings.add(new Finding(
                    "PRIVILEGED",
                    Severity.CRITICAL,
                    "Privileged execution enabled",
                    "Remove privileged mode and restrict capabilities"
                ));
            }

            if (policy.forbidShell() && image.containsShell) {
                findings.add(new Finding(
                    "MINIMAL_IMAGE",
                    Severity.MEDIUM,
                    "Shell exists in runtime image",
                    "Use a minimal shell-free runtime"
                ));
            }

            if (image.sizeMB > policy.maxImageSizeMB()) {
                findings.add(new Finding(
                    "IMAGE_SIZE",
                    Severity.MEDIUM,
                    "Image exceeds configured size",
                    "Remove unnecessary packages and build artifacts"
                ));
            }

            if (policy.requireSignature() && !image.signatureVerified) {
                findings.add(new Finding(
                    "PROVENANCE",
                    Severity.HIGH,
                    "Image signature is not verified",
                    "Verify publisher identity and provenance"
                ));
            }

            if (policy.requireNoSecrets() && !image.secrets().isEmpty()) {
                findings.add(new Finding(
                    "SECRET_EXPOSURE",
                    Severity.CRITICAL,
                    "Credentials detected in image",
                    "Rotate exposed credentials and rebuild the image"
                ));
            }

            Map<Severity, Integer> limits = Map.of(
                Severity.CRITICAL, policy.maxCritical(),
                Severity.HIGH, policy.maxHigh(),
                Severity.MEDIUM, policy.maxMedium()
            );

            limits.forEach((severity, maximum) -> {
                int actual = counts.get(severity);

                if (actual > maximum) {
                    findings.add(new Finding(
                        "CVE_THRESHOLD",
                        severity,
                        actual + " " + severity +
                            " vulnerabilities exceed " + maximum,
                        "Patch or mitigate affected packages"
                    ));
                }
            });

            Set<String> denyControls = Set.of(
                "NON_ROOT",
                "PRIVILEGED",
                "PROVENANCE",
                "SECRET_EXPOSURE",
                "UNKNOWN_SEVERITY",
                "UNFIXED_CVE"
            );

            boolean denied = findings.stream().anyMatch(finding ->
                denyControls.contains(finding.control()) ||
                (
                    finding.control().equals("CVE_THRESHOLD") &&
                    (
                        finding.severity() == Severity.CRITICAL ||
                        finding.severity() == Severity.HIGH
                    )
                )
            );

            Decision decision = denied
                ? Decision.DENY
                : findings.isEmpty()
                    ? Decision.ALLOW
                    : Decision.REVIEW;

            image.updateState(
                decision == Decision.ALLOW
                    ? ImageState.APPROVED
                    : decision == Decision.DENY
                        ? ImageState.BLOCKED
                        : ImageState.SCANNED
            );

            return new ScanReport(
                image.name(),
                image.digest(),
                Instant.now(),
                counts,
                findings,
                decision
            );
        }
    }

    record RuntimeEvent(
        String containerId,
        RuntimeEventType type,
        String process,
        int userId,
        Instant timestamp
    ) {
        RuntimeEvent {
            Objects.requireNonNull(containerId);
            Objects.requireNonNull(type);
            Objects.requireNonNull(process);
            Objects.requireNonNull(timestamp);

            if (containerId.isBlank() || process.isBlank() || userId < 0) {
                throw new IllegalArgumentException("Invalid runtime event");
            }
        }
    }

    static final class RuntimePolicy {
        private final Set<String> blockedProcesses = Set.of(
            "nc",
            "ncat",
            "socat",
            "tcpdump"
        );

        Decision evaluate(RuntimeEvent event) {
            String process = event.process()
                .substring(event.process().lastIndexOf('/') + 1)
                .toLowerCase();

            if (
                event.userId() == 0 ||
                event.type() == RuntimeEventType.SHELL_EXECUTION ||
                event.type() == RuntimeEventType.PRIVILEGED_EXECUTION ||
                blockedProcesses.contains(process)
            ) {
                return Decision.DENY;
            }

            if (
                event.type() == RuntimeEventType.SECRET_ACCESS ||
                event.type() == RuntimeEventType.FILESYSTEM_WRITE
            ) {
                return Decision.REVIEW;
            }

            return Decision.ALLOW;
        }
    }

    static final class RuntimeMonitor {
        private final RuntimePolicy policy = new RuntimePolicy();
        private final List<RuntimeEvent> history = new ArrayList<>();
        private final Map<Decision, Long> totals =
            new EnumMap<>(Decision.class);

        Decision process(RuntimeEvent event) {
            Decision decision = policy.evaluate(event);

            history.add(event);
            totals.merge(decision, 1L, Long::sum);

            return decision;
        }

        Map<Decision, Long> statistics() {
            return Map.copyOf(totals);
        }

        List<RuntimeEvent> history() {
            return List.copyOf(history);
        }
    }

    static final class SecretScanner {
        private final Map<String, Pattern> patterns = Map.of(
            "AWS_ACCESS_KEY",
            Pattern.compile("\\bAKIA[0-9A-Z]{16}\\b"),

            "PRIVATE_KEY",
            Pattern.compile(
                "-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"
            ),

            "GITHUB_TOKEN",
            Pattern.compile("\\bgh[pousr]_[A-Za-z0-9]{30,}\\b"),

            "PASSWORD",
            Pattern.compile(
                "(?:password|passwd|secret)\\s*[:=]\\s*['\"]?[^'\"\\s]{8,}",
                Pattern.CASE_INSENSITIVE
            )
        );

        List<String> scan(String content) {
            List<String> findings = new ArrayList<>();

            patterns.forEach((name, pattern) -> {
                if (pattern.matcher(content).find()) {
                    findings.add(name);
                }
            });

            return List.copyOf(findings);
        }
    }

    static final class AdmissionService {
        private final ImageScanner scanner;

        private final Map<String, ScanReport> auditLog =
            new HashMap<>();

        private final Set<String> deployedDigests =
            new HashSet<>();

        AdmissionService(ImageScanner scanner) {
            this.scanner = scanner;
        }

        synchronized ScanReport admit(ContainerImage image) {
            ScanReport report = scanner.scan(image);

            auditLog.put(
                image.digest() + ":" + Instant.now(),
                report
            );

            if (report.decision() != Decision.ALLOW) {
                throw new SecurityException(
                    "Deployment rejected: " + report.decision()
                );
            }

            deployedDigests.add(image.digest());

            return report;
        }

        Map<String, ScanReport> auditLog() {
            return Map.copyOf(auditLog);
        }

        Set<String> deployedDigests() {
            return Set.copyOf(deployedDigests);
        }
    }

    static ContainerImage createImage() {
        return new ContainerImage(
            "customer-api",
            "3.0.1",
            "sha256:" + "d".repeat(64),
            "distroless/java17",
            List.of("java-runtime", "application"),
            List.of(
                new Vulnerability(
                    "CVE-2024-12345",
                    "example-library",
                    "1.0.0",
                    "1.0.2",
                    Severity.LOW,
                    false
                )
            ),
            List.of(),
            10001,
            62,
            false,
            false,
            true
        );
    }

    public static void main(String[] args) {
        SecurityPolicy policy = SecurityPolicy.production();

        ImageScanner scanner = new ImageScanner(policy);
        AdmissionService admission = new AdmissionService(scanner);

        System.out.println("ENTERPRISE CONTAINER SECURITY");

        ContainerImage image = createImage();

        ScanReport report = scanner.scan(image);

        System.out.println("\nIMAGE SCAN");
        System.out.println("Image: " + report.imageName());
        System.out.println("Decision: " + report.decision());
        System.out.println("Findings: " + report.findings().size());

        report.counts().forEach((severity, count) ->
            System.out.println(severity + ": " + count)
        );

        System.out.println("\nADMISSION CONTROL");

        System.out.println(
            admission.admit(image).decision()
        );

        System.out.println("\nNEGATIVE TEST");

        ContainerImage compromised = new ContainerImage(
            "untrusted-api",
            "latest",
            "sha256:" + "e".repeat(64),
            "generic-linux",
            List.of("shell", "runtime"),
            List.of(
                new Vulnerability(
                    "CVE-2024-99999",
                    "unsafe-package",
                    "1.0",
                    null,
                    Severity.CRITICAL,
                    true
                )
            ),
            List.of("PRIVATE_KEY"),
            0,
            450,
            true,
            true,
            false
        );

        try {
            admission.admit(compromised);
        } catch (SecurityException exception) {
            System.out.println(exception.getMessage());
        }

        System.out.println("\nRUNTIME MONITORING");

        RuntimeMonitor monitor = new RuntimeMonitor();

        List<RuntimeEvent> events = List.of(
            new RuntimeEvent(
                "container-001",
                RuntimeEventType.PROCESS_EXECUTION,
                "java",
                10001,
                Instant.now()
            ),
            new RuntimeEvent(
                "container-001",
                RuntimeEventType.SHELL_EXECUTION,
                "/bin/sh",
                10001,
                Instant.now()
            ),
            new RuntimeEvent(
                "container-001",
                RuntimeEventType.SECRET_ACCESS,
                "application",
                10001,
                Instant.now()
            )
        );

        for (RuntimeEvent event : events) {
            System.out.println(
                event.type() + ": " + monitor.process(event)
            );
        }

        System.out.println("Statistics: " + monitor.statistics());

        System.out.println("\nSECRET DETECTION");

        SecretScanner secretScanner = new SecretScanner();

        System.out.println(
            secretScanner.scan("password=ExampleSecret123456")
        );

        System.out.println("\nVALIDATION");

        if (report.decision() != Decision.ALLOW) {
            throw new IllegalStateException("Valid image rejected");
        }

        if (scanner.scan(compromised).decision() != Decision.DENY) {
            throw new IllegalStateException("Unsafe image was accepted");
        }

        System.out.println("All security tests passed.");
    }
}
