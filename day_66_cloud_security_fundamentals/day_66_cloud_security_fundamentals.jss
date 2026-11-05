import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;

/*
 * Cloud Security Fundamentals
 *
 * Enterprise-oriented cloud security governance system.
 *
 * Features:
 * - Cloud provider responsibility management
 * - Service model classification
 * - Asset inventory
 * - Attack surface discovery
 * - IAM security policies
 * - Threat assessment
 * - Security control evaluation
 * - Risk prioritization
 * - Finding lifecycle management
 * - Merge-independent security compliance decisions
 *
 * Runtime: Java 17
 */

public class CloudSecurityFundamentals {

    enum Provider {
        AWS, AZURE, GCP
    }

    enum AssetType {
        COMPUTE, STORAGE, DATABASE,
        NETWORK, IDENTITY, SERVERLESS
    }

    enum ServiceModel {
        IAAS, PAAS, SAAS
    }

    enum Responsibility {
        PROVIDER, CUSTOMER, SHARED
    }

    enum Severity {
        LOW(1, 10),
        MEDIUM(2, 20),
        HIGH(3, 30),
        CRITICAL(4, 40);

        private final int level;
        private final int defaultScore;

        Severity(int level, int defaultScore) {
            this.level = level;
            this.defaultScore = defaultScore;
        }

        public int level() {
            return level;
        }

        public int defaultScore() {
            return defaultScore;
        }
    }

    enum FindingStatus {
        OPEN, IN_PROGRESS, REMEDIATED, ACCEPTED
    }

    record SecurityControl(
        String controlId,
        String description,
        Responsibility responsibility
    ) {
        SecurityControl {
            Objects.requireNonNull(controlId);
            Objects.requireNonNull(description);
            Objects.requireNonNull(responsibility);

            if (controlId.isBlank()) {
                throw new IllegalArgumentException(
                    "Control ID cannot be empty."
                );
            }
        }
    }

    record CloudAsset(
        String id,
        String name,
        Provider provider,
        AssetType type,
        String region,
        boolean internetExposed,
        boolean encryptedAtRest,
        boolean tlsRequired,
        boolean loggingEnabled,
        boolean mfaEnabled,
        boolean leastPrivilege,
        boolean networkRestricted,
        boolean backupEnabled,
        boolean sensitiveData,
        boolean active,
        Set<String> permissions
    ) {
        CloudAsset {
            Objects.requireNonNull(id);
            Objects.requireNonNull(name);
            Objects.requireNonNull(provider);
            Objects.requireNonNull(type);
            Objects.requireNonNull(region);

            if (
                id.isBlank() ||
                name.isBlank() ||
                region.isBlank()
            ) {
                throw new IllegalArgumentException(
                    "Asset identity and region are mandatory."
                );
            }

            permissions = Set.copyOf(permissions);

            if (permissions.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException(
                    "Invalid permission entry."
                );
            }
        }
    }

    record SecurityFinding(
        String findingId,
        String assetId,
        String ruleId,
        String description,
        String remediation,
        Severity severity,
        Responsibility responsibility,
        int riskScore,
        Instant detectedAt,
        FindingStatus status
    ) {
        SecurityFinding {
            Objects.requireNonNull(findingId);
            Objects.requireNonNull(assetId);
            Objects.requireNonNull(ruleId);
            Objects.requireNonNull(severity);
            Objects.requireNonNull(responsibility);
            Objects.requireNonNull(detectedAt);
            Objects.requireNonNull(status);

            if (riskScore < 0 || riskScore > 100) {
                throw new IllegalArgumentException(
                    "Risk score must be between 0 and 100."
                );
            }
        }

        SecurityFinding updateStatus(FindingStatus newStatus) {
            if (status == FindingStatus.REMEDIATED) {
                throw new IllegalStateException(
                    "Remediated findings cannot be reopened."
                );
            }

            if (status == FindingStatus.ACCEPTED) {
                throw new IllegalStateException(
                    "Accepted findings require a new review process."
                );
            }

            return new SecurityFinding(
                findingId,
                assetId,
                ruleId,
                description,
                remediation,
                severity,
                responsibility,
                riskScore,
                detectedAt,
                newStatus
            );
        }
    }

    static class SecurityException extends RuntimeException {
        SecurityException(String message) {
            super(message);
        }
    }

    interface SecurityPolicy {
        List<SecurityFinding> evaluate(CloudAsset asset);
    }

    static class ResponsibilityRegistry {

        private final Map<String, SecurityControl> controls =
            new LinkedHashMap<>();

        ResponsibilityRegistry() {
            register("physical_datacenter",
                "Physical facilities and hardware",
                Responsibility.PROVIDER);

            register("hypervisor",
                "Virtualization infrastructure",
                Responsibility.PROVIDER);

            register("guest_os",
                "Guest operating system configuration",
                Responsibility.CUSTOMER);

            register("application",
                "Application security",
                Responsibility.CUSTOMER);

            register("data",
                "Customer data protection",
                Responsibility.CUSTOMER);

            register("identity",
                "Identity and access management",
                Responsibility.CUSTOMER);

            register("network_configuration",
                "Cloud network security configuration",
                Responsibility.CUSTOMER);

            register("managed_runtime",
                "Managed runtime security",
                Responsibility.SHARED);

            register("monitoring",
                "Security monitoring and incident response",
                Responsibility.SHARED);
        }

        private void register(
            String id,
            String description,
            Responsibility responsibility
        ) {
            SecurityControl control = new SecurityControl(
                id,
                description,
                responsibility
            );

            controls.put(id, control);
        }

        Responsibility getOwner(String controlId) {
            SecurityControl control = controls.get(controlId);

            if (control == null) {
                throw new SecurityException(
                    "Unknown security control: " + controlId
                );
            }

            return control.responsibility();
        }

        List<SecurityControl> getAllControls() {
            return List.copyOf(controls.values());
        }
    }

    static class ServiceModelPolicy {

        private final ResponsibilityRegistry registry;

        ServiceModelPolicy(ResponsibilityRegistry registry) {
            this.registry = registry;
        }

        Map<String, List<String>> evaluate(ServiceModel model) {
            Objects.requireNonNull(model);

            List<String> providerManaged;
            List<String> customerManaged;

            switch (model) {
                case IAAS -> {
                    providerManaged = List.of(
                        "physical_datacenter",
                        "hypervisor"
                    );

                    customerManaged = List.of(
                        "guest_os",
                        "application",
                        "data",
                        "identity",
                        "network_configuration"
                    );
                }

                case PAAS -> {
                    providerManaged = List.of(
                        "physical_datacenter",
                        "hypervisor",
                        "managed_runtime"
                    );

                    customerManaged = List.of(
                        "application",
                        "data",
                        "identity"
                    );
                }

                case SAAS -> {
                    providerManaged = List.of(
                        "physical_datacenter",
                        "hypervisor",
                        "managed_runtime",
                        "application"
                    );

                    customerManaged = List.of(
                        "data",
                        "identity"
                    );
                }

                default -> throw new SecurityException(
                    "Unsupported service model."
                );
            }

            // Validate every responsibility against the registry.
            providerManaged.forEach(registry::getOwner);
            customerManaged.forEach(registry::getOwner);

            return Map.of(
                "providerManaged", providerManaged,
                "customerManaged", customerManaged
            );
        }
    }

    static class CloudSecurityPolicy implements SecurityPolicy {

        private SecurityFinding finding(
            CloudAsset asset,
            String rule,
            String description,
            String remediation,
            Severity severity,
            int score
        ) {
            return new SecurityFinding(
                UUID.randomUUID().toString(),
                asset.id(),
                rule,
                description,
                remediation,
                severity,
                Responsibility.CUSTOMER,
                score,
                Instant.now(),
                FindingStatus.OPEN
            );
        }

        @Override
        public List<SecurityFinding> evaluate(CloudAsset asset) {
            Objects.requireNonNull(asset);

            if (!asset.active()) {
                return List.of();
            }

            List<SecurityFinding> findings = new ArrayList<>();

            if (
                asset.type() == AssetType.STORAGE &&
                asset.internetExposed()
            ) {
                findings.add(finding(
                    asset,
                    "PUBLIC_STORAGE",
                    "Storage is publicly accessible.",
                    "Disable public access and enforce access policies.",
                    Severity.CRITICAL,
                    40
                ));
            }

            if (
                asset.type() == AssetType.DATABASE &&
                asset.internetExposed()
            ) {
                findings.add(finding(
                    asset,
                    "PUBLIC_DATABASE",
                    "Database has public network exposure.",
                    "Use private endpoints and restrict inbound traffic.",
                    Severity.CRITICAL,
                    40
                ));
            }

            if (
                asset.sensitiveData() &&
                !asset.encryptedAtRest()
            ) {
                findings.add(finding(
                    asset,
                    "NO_ENCRYPTION",
                    "Sensitive data is not encrypted at rest.",
                    "Enable encryption using managed encryption keys.",
                    Severity.CRITICAL,
                    35
                ));
            }

            if (
                !asset.leastPrivilege() ||
                asset.permissions().contains("*")
            ) {
                findings.add(finding(
                    asset,
                    "EXCESSIVE_IAM",
                    "IAM permissions exceed operational requirements.",
                    "Remove wildcard permissions and apply least privilege.",
                    Severity.HIGH,
                    25
                ));
            }

            if (!asset.mfaEnabled()) {
                findings.add(finding(
                    asset,
                    "MFA_DISABLED",
                    "Multi-factor authentication is disabled.",
                    "Require MFA for privileged identities.",
                    Severity.HIGH,
                    25
                ));
            }

            if (!asset.loggingEnabled()) {
                findings.add(finding(
                    asset,
                    "NO_LOGGING",
                    "Audit logging is disabled.",
                    "Enable centralized protected audit logging.",
                    Severity.HIGH,
                    20
                ));
            }

            if (!asset.networkRestricted()) {
                findings.add(finding(
                    asset,
                    "OPEN_NETWORK",
                    "Network access is insufficiently restricted.",
                    "Apply segmentation and firewall controls.",
                    Severity.HIGH,
                    20
                ));
            }

            if (!asset.tlsRequired()) {
                findings.add(finding(
                    asset,
                    "NO_TLS",
                    "Secure transport is not enforced.",
                    "Require TLS for data in transit.",
                    Severity.HIGH,
                    25
                ));
            }

            if (!asset.backupEnabled()) {
                findings.add(finding(
                    asset,
                    "NO_BACKUP",
                    "Backup protection is disabled.",
                    "Configure encrypted backups and recovery tests.",
                    Severity.MEDIUM,
                    15
                ));
            }

            return findings;
        }
    }

    static class CloudInventory {

        private final Map<String, CloudAsset> assets =
            new LinkedHashMap<>();

        void register(CloudAsset asset) {
            Objects.requireNonNull(asset);

            if (assets.putIfAbsent(asset.id(), asset) != null) {
                throw new SecurityException(
                    "Duplicate cloud asset: " + asset.id()
                );
            }
        }

        List<CloudAsset> getAll() {
            return List.copyOf(assets.values());
        }

        Optional<CloudAsset> find(String id) {
            return Optional.ofNullable(assets.get(id));
        }

        List<CloudAsset> activeAssets() {
            return assets.values().stream()
                .filter(CloudAsset::active)
                .toList();
        }
    }

    static class AttackSurfaceAnalyzer {

        Map<String, List<String>> analyze(
            List<CloudAsset> assets
        ) {
            Map<String, List<String>> result = new LinkedHashMap<>();

            result.put("internetExposed", new ArrayList<>());
            result.put("identity", new ArrayList<>());
            result.put("sensitiveData", new ArrayList<>());
            result.put("network", new ArrayList<>());

            for (CloudAsset asset : assets) {
                if (!asset.active()) {
                    continue;
                }

                if (asset.internetExposed()) {
                    result.get("internetExposed").add(asset.id());
                }

                if (asset.type() == AssetType.IDENTITY) {
                    result.get("identity").add(asset.id());
                }

                if (asset.sensitiveData()) {
                    result.get("sensitiveData").add(asset.id());
                }

                if (asset.type() == AssetType.NETWORK) {
                    result.get("network").add(asset.id());
                }
            }

            return result.entrySet().stream()
                .collect(Collectors.toUnmodifiableMap(
                    Map.Entry::getKey,
                    entry -> List.copyOf(entry.getValue())
                ));
        }
    }

    static class SecurityAssessmentService {

        private final CloudInventory inventory;
        private final SecurityPolicy policy;
        private final Map<String, SecurityFinding> findings =
            new LinkedHashMap<>();

        SecurityAssessmentService(
            CloudInventory inventory,
            SecurityPolicy policy
        ) {
            this.inventory = inventory;
            this.policy = policy;
        }

        List<SecurityFinding> assess() {
            findings.clear();

            for (CloudAsset asset : inventory.activeAssets()) {
                for (SecurityFinding finding : policy.evaluate(asset)) {
                    findings.put(finding.findingId(), finding);
                }
            }

            return findings.values().stream()
                .sorted(
                    Comparator.comparingInt(
                        SecurityFinding::riskScore
                    ).reversed()
                )
                .toList();
        }

        SecurityFinding transition(
            String findingId,
            FindingStatus newStatus
        ) {
            SecurityFinding current = findings.get(findingId);

            if (current == null) {
                throw new SecurityException(
                    "Finding does not exist."
                );
            }

            SecurityFinding updated = current.updateStatus(newStatus);
            findings.put(findingId, updated);

            return updated;
        }

        Map<Severity, Long> severityDistribution() {
            return findings.values().stream()
                .collect(Collectors.groupingBy(
                    SecurityFinding::severity,
                    () -> new EnumMap<>(Severity.class),
                    Collectors.counting()
                ));
        }

        int totalRisk() {
            return findings.values().stream()
                .mapToInt(SecurityFinding::riskScore)
                .sum();
        }
    }

    private static CloudAsset sampleStorage() {
        return new CloudAsset(
            "AWS-STORAGE-001",
            "Customer Documents",
            Provider.AWS,
            AssetType.STORAGE,
            "ap-south-1",
            true,
            false,
            true,
            false,
            false,
            false,
            false,
            false,
            true,
            true,
            Set.of("*")
        );
    }

    private static CloudAsset sampleCompute() {
        return new CloudAsset(
            "AZURE-VM-001",
            "Application Server",
            Provider.AZURE,
            AssetType.COMPUTE,
            "centralindia",
            false,
            true,
            false,
            true,
            false,
            true,
            false,
            false,
            false,
            true,
            Set.of("compute:read", "compute:write")
        );
    }

    private static CloudAsset sampleDatabase() {
        return new CloudAsset(
            "GCP-DB-001",
            "Production Database",
            Provider.GCP,
            AssetType.DATABASE,
            "asia-south1",
            true,
            true,
            true,
            true,
            true,
            true,
            true,
            false,
            true,
            true,
            Set.of("database:read")
        );
    }

    private static void runTests() {
        ResponsibilityRegistry registry =
            new ResponsibilityRegistry();

        if (
            registry.getOwner("data") != Responsibility.CUSTOMER
        ) {
            throw new AssertionError("Data responsibility test failed.");
        }

        if (
            registry.getOwner("hypervisor") != Responsibility.PROVIDER
        ) {
            throw new AssertionError("Provider control test failed.");
        }

        CloudInventory inventory = new CloudInventory();
        inventory.register(sampleStorage());

        CloudSecurityPolicy policy = new CloudSecurityPolicy();

        SecurityAssessmentService service =
            new SecurityAssessmentService(inventory, policy);

        List<SecurityFinding> results = service.assess();

        if (results.size() != 5) {
            throw new AssertionError(
                "Expected five security findings."
            );
        }

        try {
            inventory.register(sampleStorage());
            throw new AssertionError("Duplicate asset accepted.");
        } catch (SecurityException expected) {
            // Expected.
        }

        SecurityFinding finding = results.get(0);

        service.transition(
            finding.findingId(),
            FindingStatus.IN_PROGRESS
        );

        System.out.println("All Java 17 tests passed.");
    }

    public static void main(String[] args) {
        ResponsibilityRegistry registry =
            new ResponsibilityRegistry();

        ServiceModelPolicy servicePolicy =
            new ServiceModelPolicy(registry);

        System.out.println("CLOUD SERVICE MODEL: IAAS");
        System.out.println(
            servicePolicy.evaluate(ServiceModel.IAAS)
        );

        CloudInventory inventory = new CloudInventory();

        inventory.register(sampleStorage());
        inventory.register(sampleCompute());
        inventory.register(sampleDatabase());

        AttackSurfaceAnalyzer analyzer =
            new AttackSurfaceAnalyzer();

        System.out.println("\nATTACK SURFACE");
        analyzer.analyze(inventory.getAll())
            .forEach((category, assets) ->
                System.out.println(category + ": " + assets)
            );

        SecurityAssessmentService assessment =
            new SecurityAssessmentService(
                inventory,
                new CloudSecurityPolicy()
            );

        List<SecurityFinding> findings = assessment.assess();

        System.out.println("\nSECURITY FINDINGS");

        for (SecurityFinding finding : findings) {
            System.out.printf(
                "%n[%s] %s%nAsset: %s%nRisk: %d%nIssue: %s%nRemediation: %s%n",
                finding.severity(),
                finding.ruleId(),
                finding.assetId(),
                finding.riskScore(),
                finding.description(),
                finding.remediation()
            );
        }

        System.out.println("\nSEVERITY DISTRIBUTION");
        System.out.println(assessment.severityDistribution());

        System.out.println(
            "Total risk score: " + assessment.totalRisk()
        );

        runTests();
    }
}
