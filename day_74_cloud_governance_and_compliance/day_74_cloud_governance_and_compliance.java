/*
 * Cloud Governance and Enterprise Compliance Management
 *
 * Java 17 implementation.
 *
 * Domain capabilities:
 * - Enterprise cloud resource inventory
 * - Governance policy interfaces
 * - Regulatory control mapping
 * - Classification-aware evaluation
 * - Data residency requirements
 * - Approval-controlled remediation
 * - Risk and compliance reporting
 * - Audit integrity
 *
 * Compile:
 * javac CloudGovernance.java
 *
 * Run:
 * java CloudGovernance
 */

import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

// ============================================================
// APPLICATION
// ============================================================

public class CloudGovernance {

    public static void main(String[] args) {

        try {

            GovernanceService service = new GovernanceService();

            service.initialize();

            System.out.println("\nCLOUD GOVERNANCE ASSESSMENT");
            System.out.println("===========================");

            for (CloudResource resource : service.resources()) {

                Assessment assessment = service.assess(
                    resource.id(),
                    "compliance-service"
                );

                System.out.println(
                    "\nResource: " + resource.name()
                );

                System.out.println(
                    "Compliance: " +
                    assessment.compliant()
                );

                assessment.policyResults().forEach(result -> {

                    System.out.println(
                        result.policyId() + " : " +
                        result.status()
                    );

                    result.violations().forEach(
                        violation ->
                            System.out.println("  - " + violation)
                    );
                });

                assessment.residencyResults().forEach(result ->
                    System.out.println(
                        result.regulationId() + " : " +
                        (result.compliant()
                            ? "COMPLIANT"
                            : "NON_COMPLIANT")
                    )
                );
            }

            System.out.println("\nAPPROVED REMEDIATION");

            service.remediate(
                "RES-001",
                new Remediation(
                    true,
                    false,
                    true,
                    true
                ),
                new Approval(
                    "security-reviewer",
                    "governance-admin",
                    true,
                    "Approved after security assessment."
                )
            );

            Assessment reassessment = service.assess(
                "RES-001",
                "compliance-service"
            );

            System.out.println(
                "RES-001 after remediation: " +
                (reassessment.compliant()
                    ? "COMPLIANT"
                    : "NON_COMPLIANT")
            );

            System.out.println("\nENTERPRISE COMPLIANCE REPORT");

            System.out.println(service.report());

            System.out.println(
                "Audit integrity: " +
                service.auditIntegrity()
            );

            try {

                service.remediate(
                    "RES-002",
                    new Remediation(
                        false,
                        true,
                        false,
                        false
                    ),
                    new Approval(
                        "untrusted-user",
                        "governance-admin",
                        true,
                        "Invalid authorization."
                    )
                );

            } catch (GovernanceException error) {

                System.out.println(
                    "Expected rejection: " + error.getMessage()
                );
            }

        } catch (GovernanceException error) {

            System.err.println(
                "Governance failure: " + error.getMessage()
            );

            System.exit(1);
        }
    }
}

// ============================================================
// ENUMERATIONS
// ============================================================

enum ResourceType {
    STORAGE,
    DATABASE,
    COMPUTE,
    NETWORK
}

enum DataClassification {
    PUBLIC,
    INTERNAL,
    CONFIDENTIAL,
    RESTRICTED
}

enum Severity {
    LOW(1),
    MEDIUM(2),
    HIGH(3),
    CRITICAL(4);

    private final int weight;

    Severity(int weight) {
        this.weight = weight;
    }

    public int weight() {
        return weight;
    }
}

enum ComplianceStatus {
    COMPLIANT,
    NON_COMPLIANT,
    NOT_APPLICABLE
}

// ============================================================
// EXCEPTIONS
// ============================================================

class GovernanceException extends RuntimeException {

    GovernanceException(String message) {
        super(message);
    }
}

class PolicyValidationException extends GovernanceException {

    PolicyValidationException(String message) {
        super(message);
    }
}

class AuthorizationException extends GovernanceException {

    AuthorizationException(String message) {
        super(message);
    }
}

class ResourceNotFoundException extends GovernanceException {

    ResourceNotFoundException(String message) {
        super(message);
    }
}

// ============================================================
// RESOURCE DOMAIN
// ============================================================

record CloudResource(
    String id,
    String name,
    String owner,
    String provider,
    String region,
    ResourceType type,
    DataClassification classification,
    boolean encrypted,
    boolean publicAccess,
    boolean backupEnabled,
    Map<String, String> tags
) {

    CloudResource {

        require(id, "Resource ID");
        require(name, "Resource name");
        require(owner, "Resource owner");
        require(provider, "Provider");
        require(region, "Region");

        Objects.requireNonNull(type);
        Objects.requireNonNull(classification);

        tags = Collections.unmodifiableMap(
            new HashMap<>(Objects.requireNonNull(tags))
        );
    }

    private static void require(
        String value,
        String field
    ) {

        if (value == null || value.isBlank()) {
            throw new PolicyValidationException(
                field + " is mandatory."
            );
        }
    }
}

// ============================================================
// GOVERNANCE POLICY INTERFACE
// ============================================================

interface GovernancePolicy {

    String id();

    String name();

    Severity severity();

    boolean appliesTo(CloudResource resource);

    List<String> validate(CloudResource resource);

    default PolicyResult evaluate(
        CloudResource resource
    ) {

        if (!appliesTo(resource)) {
            return new PolicyResult(
                resource.id(),
                id(),
                name(),
                severity(),
                ComplianceStatus.NOT_APPLICABLE,
                List.of()
            );
        }

        List<String> violations = validate(resource);

        return new PolicyResult(
            resource.id(),
            id(),
            name(),
            severity(),
            violations.isEmpty()
                ? ComplianceStatus.COMPLIANT
                : ComplianceStatus.NON_COMPLIANT,
            violations
        );
    }
}

// ============================================================
// ABSTRACT POLICY
// ============================================================

abstract class AbstractPolicy implements GovernancePolicy {

    private final String id;
    private final String name;
    private final Severity severity;
    private final Set<DataClassification> classifications;

    protected AbstractPolicy(
        String id,
        String name,
        Severity severity,
        Set<DataClassification> classifications
    ) {

        if (id == null || id.isBlank()) {
            throw new PolicyValidationException(
                "Policy ID is required."
            );
        }

        this.id = id;
        this.name = Objects.requireNonNull(name);
        this.severity = Objects.requireNonNull(severity);

        this.classifications = Set.copyOf(
            classifications
        );
    }

    @Override
    public String id() {
        return id;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public Severity severity() {
        return severity;
    }

    @Override
    public boolean appliesTo(CloudResource resource) {

        return classifications.isEmpty() ||
            classifications.contains(resource.classification());
    }
}

// ============================================================
// INDIVIDUAL POLICY IMPLEMENTATIONS
// ============================================================

final class EncryptionPolicy extends AbstractPolicy {

    EncryptionPolicy() {

        super(
            "ENC-001",
            "Sensitive Data Encryption",
            Severity.CRITICAL,
            Set.of(
                DataClassification.CONFIDENTIAL,
                DataClassification.RESTRICTED
            )
        );
    }

    @Override
    public List<String> validate(CloudResource resource) {

        return resource.encrypted()
            ? List.of()
            : List.of("Sensitive resource is not encrypted.");
    }
}

final class PublicAccessPolicy extends AbstractPolicy {

    PublicAccessPolicy() {

        super(
            "PUB-001",
            "Public Exposure Prevention",
            Severity.CRITICAL,
            Set.of(
                DataClassification.CONFIDENTIAL,
                DataClassification.RESTRICTED
            )
        );
    }

    @Override
    public List<String> validate(CloudResource resource) {

        return resource.publicAccess()
            ? List.of("Public access is prohibited.")
            : List.of();
    }
}

final class BackupPolicy extends AbstractPolicy {

    BackupPolicy() {

        super(
            "BKP-001",
            "Restricted Data Backup",
            Severity.HIGH,
            Set.of(DataClassification.RESTRICTED)
        );
    }

    @Override
    public List<String> validate(CloudResource resource) {

        return resource.backupEnabled()
            ? List.of()
            : List.of("Backup is required.");
    }
}

final class RegionPolicy extends AbstractPolicy {

    private final Set<String> permittedRegions;

    RegionPolicy(Set<String> permittedRegions) {

        super(
            "REG-001",
            "Approved Cloud Regions",
            Severity.CRITICAL,
            Set.of(DataClassification.RESTRICTED)
        );

        if (permittedRegions.isEmpty()) {
            throw new PolicyValidationException(
                "Approved region list cannot be empty."
            );
        }

        this.permittedRegions = Set.copyOf(permittedRegions);
    }

    @Override
    public List<String> validate(CloudResource resource) {

        return permittedRegions.contains(resource.region())
            ? List.of()
            : List.of(
                "Resource is deployed outside approved regions."
            );
    }
}

// ============================================================
// POLICY RESULT
// ============================================================

record PolicyResult(
    String resourceId,
    String policyId,
    String policyName,
    Severity severity,
    ComplianceStatus status,
    List<String> violations
) {

    PolicyResult {
        violations = List.copyOf(violations);
    }
}

// ============================================================
// REGULATORY CONTROL
// ============================================================

record RegulatoryControl(
    String id,
    String regulation,
    String requirement,
    Set<String> permittedRegions,
    boolean mandatoryEncryption
) {

    RegulatoryControl {

        if (id == null || id.isBlank()) {
            throw new PolicyValidationException(
                "Regulatory control ID is required."
            );
        }

        Objects.requireNonNull(regulation);
        Objects.requireNonNull(requirement);

        permittedRegions = Set.copyOf(permittedRegions);

        if (permittedRegions.isEmpty()) {
            throw new PolicyValidationException(
                "Regulatory region requirements cannot be empty."
            );
        }
    }
}

// ============================================================
// RESIDENCY RESULT
// ============================================================

record ResidencyResult(
    String resourceId,
    String regulationId,
    boolean compliant,
    String reason
) {}

// ============================================================
// RESIDENCY SERVICE
// ============================================================

class ResidencyService {

    private final Map<String, RegulatoryControl> controls =
        new ConcurrentHashMap<>();

    void register(RegulatoryControl control) {

        if (
            controls.putIfAbsent(
                control.id(),
                control
            ) != null
        ) {
            throw new PolicyValidationException(
                "Duplicate regulatory control."
            );
        }
    }

    ResidencyResult evaluate(
        CloudResource resource,
        String controlId
    ) {

        RegulatoryControl control = controls.get(controlId);

        if (control == null) {
            throw new ResourceNotFoundException(
                "Regulatory control not found: " + controlId
            );
        }

        List<String> failures = new ArrayList<>();

        if (
            !control.permittedRegions().contains(
                resource.region()
            )
        ) {
            failures.add("Data residency restriction violated.");
        }

        if (
            control.mandatoryEncryption() &&
            !resource.encrypted()
        ) {
            failures.add("Regulatory encryption requirement failed.");
        }

        return new ResidencyResult(
            resource.id(),
            controlId,
            failures.isEmpty(),
            String.join("; ", failures)
        );
    }
}

// ============================================================
// APPROVAL DOMAIN
// ============================================================

record Approval(
    String reviewer,
    String role,
    boolean approved,
    String justification
) {

    Approval {

        Objects.requireNonNull(reviewer);
        Objects.requireNonNull(role);
        Objects.requireNonNull(justification);

        if (reviewer.isBlank() || role.isBlank()) {
            throw new PolicyValidationException(
                "Reviewer and role are required."
            );
        }
    }
}

// ============================================================
// REMEDIATION DOMAIN
// ============================================================

record Remediation(
    boolean encrypt,
    boolean disablePublicAccess,
    boolean enableBackup,
    boolean requireApproval
) {}

// ============================================================
// AUDIT DOMAIN
// ============================================================

record AuditEvent(
    long sequence,
    String action,
    String actor,
    String resourceId,
    String details,
    String timestamp,
    String previousHash,
    String hash
) {}

// ============================================================
// AUDIT SERVICE
// ============================================================

class AuditService {

    private final List<AuditEvent> events =
        new ArrayList<>();

    private String previousHash = "GENESIS";

    synchronized void record(
        String action,
        String actor,
        String resourceId,
        String details
    ) {

        long sequence = events.size() + 1;

        String timestamp = Instant.now().toString();

        String payload = String.join(
            "|",
            Long.toString(sequence),
            action,
            actor,
            resourceId,
            details,
            timestamp,
            previousHash
        );

        String hash = sha256(payload);

        events.add(
            new AuditEvent(
                sequence,
                action,
                actor,
                resourceId,
                details,
                timestamp,
                previousHash,
                hash
            )
        );

        previousHash = hash;
    }

    synchronized boolean verifyIntegrity() {

        String expectedPrevious = "GENESIS";

        for (AuditEvent event : events) {

            if (!event.previousHash().equals(expectedPrevious)) {
                return false;
            }

            String payload = String.join(
                "|",
                Long.toString(event.sequence()),
                event.action(),
                event.actor(),
                event.resourceId(),
                event.details(),
                event.timestamp(),
                event.previousHash()
            );

            if (!sha256(payload).equals(event.hash())) {
                return false;
            }

            expectedPrevious = event.hash();
        }

        return true;
    }

    private static String sha256(String value) {

        try {

            java.security.MessageDigest digest =
                java.security.MessageDigest.getInstance("SHA-256");

            byte[] bytes = digest.digest(
                value.getBytes(
                    java.nio.charset.StandardCharsets.UTF_8
                )
            );

            return HexFormat.of().formatHex(bytes);

        } catch (java.security.NoSuchAlgorithmException error) {

            throw new GovernanceException(
                "SHA-256 is unavailable."
            );
        }
    }

    synchronized int count() {
        return events.size();
    }
}

// ============================================================
// ASSESSMENT
// ============================================================

record Assessment(
    String resourceId,
    List<PolicyResult> policyResults,
    List<ResidencyResult> residencyResults,
    Instant evaluatedAt
) {

    Assessment {

        policyResults = List.copyOf(policyResults);
        residencyResults = List.copyOf(residencyResults);
    }

    boolean compliant() {

        boolean policyCompliant = policyResults.stream()
            .noneMatch(result ->
                result.status() == ComplianceStatus.NON_COMPLIANT
            );

        boolean residencyCompliant = residencyResults.stream()
            .allMatch(ResidencyResult::compliant);

        return policyCompliant && residencyCompliant;
    }
}

// ============================================================
// COMPLIANCE REPORT
// ============================================================

record ComplianceReport(
    int resources,
    int assessedResources,
    long totalEvaluations,
    long compliant,
    long nonCompliant,
    long notApplicable,
    long residencyViolations,
    double compliancePercentage
) {}

// ============================================================
// GOVERNANCE SERVICE
// ============================================================

class GovernanceService {

    private final Map<String, CloudResource> resources =
        new ConcurrentHashMap<>();

    private final Map<String, Assessment> assessments =
        new ConcurrentHashMap<>();

    private final List<GovernancePolicy> policies =
        new ArrayList<>();

    private final ResidencyService residency =
        new ResidencyService();

    private final AuditService audit =
        new AuditService();

    void initialize() {

        policies.add(new EncryptionPolicy());
        policies.add(new PublicAccessPolicy());
        policies.add(new BackupPolicy());

        policies.add(
            new RegionPolicy(
                Set.of("ap-south-1", "ap-south-2")
            )
        );

        residency.register(
            new RegulatoryControl(
                "ORG-RESIDENCY",
                "Organizational Data Residency",
                "Restricted information must remain in approved regions.",
                Set.of("ap-south-1", "ap-south-2"),
                true
            )
        );

        register(new CloudResource(
            "RES-001",
            "Customer Database",
            "data-team",
            "AWS",
            "ap-south-1",
            ResourceType.DATABASE,
            DataClassification.RESTRICTED,
            false,
            true,
            false,
            Map.of("environment", "production")
        ));

        register(new CloudResource(
            "RES-002",
            "Application Server",
            "engineering-team",
            "AWS",
            "ap-south-1",
            ResourceType.COMPUTE,
            DataClassification.INTERNAL,
            true,
            false,
            true,
            Map.of("environment", "production")
        ));

        register(new CloudResource(
            "RES-003",
            "Analytics Database",
            "analytics-team",
            "Azure",
            "centralindia",
            ResourceType.DATABASE,
            DataClassification.RESTRICTED,
            true,
            false,
            true,
            Map.of("environment", "analytics")
        ));
    }

    void register(CloudResource resource) {

        if (
            resources.putIfAbsent(
                resource.id(),
                resource
            ) != null
        ) {
            throw new PolicyValidationException(
                "Duplicate cloud resource."
            );
        }

        audit.record(
            "RESOURCE_REGISTERED",
            "governance-admin",
            resource.id(),
            resource.name()
        );
    }

    List<CloudResource> resources() {

        return resources.values()
            .stream()
            .sorted(
                Comparator.comparing(CloudResource::id)
            )
            .toList();
    }

    private CloudResource findResource(String id) {

        CloudResource resource = resources.get(id);

        if (resource == null) {
            throw new ResourceNotFoundException(
                "Cloud resource does not exist: " + id
            );
        }

        return resource;
    }

    Assessment assess(
        String resourceId,
        String actor
    ) {

        CloudResource resource = findResource(resourceId);

        List<PolicyResult> policyResults =
            policies.stream()
                .map(policy -> policy.evaluate(resource))
                .toList();

        List<ResidencyResult> residencyResults =
            List.of(
                residency.evaluate(
                    resource,
                    "ORG-RESIDENCY"
                )
            );

        Assessment assessment = new Assessment(
            resourceId,
            policyResults,
            residencyResults,
            Instant.now()
        );

        assessments.put(resourceId, assessment);

        audit.record(
            "POLICY_EVALUATED",
            actor,
            resourceId,
            "Policy and residency evaluation completed."
        );

        policyResults.stream()
            .filter(result ->
                result.status() == ComplianceStatus.NON_COMPLIANT
            )
            .forEach(result ->
                audit.record(
                    "VIOLATION_DETECTED",
                    actor,
                    resourceId,
                    result.policyId()
                )
            );

        return assessment;
    }

    void remediate(
        String resourceId,
        Remediation remediation,
        Approval approval
    ) {

        if (!"governance-admin".equals(approval.role())) {
            throw new AuthorizationException(
                "Only a governance administrator can authorize remediation."
            );
        }

        if (!approval.approved()) {
            throw new AuthorizationException(
                "Remediation approval was rejected."
            );
        }

        CloudResource old = findResource(resourceId);

        CloudResource updated = new CloudResource(
            old.id(),
            old.name(),
            old.owner(),
            old.provider(),
            old.region(),
            old.type(),
            old.classification(),
            old.encrypted() || remediation.encrypt(),
            old.publicAccess() && !remediation.disablePublicAccess(),
            old.backupEnabled() || remediation.enableBackup(),
            old.tags()
        );

        // Replace the immutable resource only after validation.
        resources.put(resourceId, updated);

        assessments.remove(resourceId);

        audit.record(
            "REMEDIATION_APPLIED",
            approval.reviewer(),
            resourceId,
            approval.justification()
        );
    }

    ComplianceReport report() {

        List<Assessment> all = new ArrayList<>(
            assessments.values()
        );

        List<PolicyResult> results = all.stream()
            .flatMap(assessment ->
                assessment.policyResults().stream()
            )
            .toList();

        long compliant = results.stream()
            .filter(result ->
                result.status() == ComplianceStatus.COMPLIANT
            )
            .count();

        long nonCompliant = results.stream()
            .filter(result ->
                result.status() == ComplianceStatus.NON_COMPLIANT
            )
            .count();

        long notApplicable = results.stream()
            .filter(result ->
                result.status() == ComplianceStatus.NOT_APPLICABLE
            )
            .count();

        long residencyViolations = all.stream()
            .flatMap(assessment ->
                assessment.residencyResults().stream()
            )
            .filter(result -> !result.compliant())
            .count();

        long applicable = compliant + nonCompliant;

        double percentage = applicable == 0
            ? 100.0
            : Math.round(
                compliant * 10000.0 / applicable
            ) / 100.0;

        return new ComplianceReport(
            resources.size(),
            assessments.size(),
            results.size(),
            compliant,
            nonCompliant,
            notApplicable,
            residencyViolations,
            percentage
        );
    }

    boolean auditIntegrity() {
        return audit.verifyIntegrity();
    }
}
