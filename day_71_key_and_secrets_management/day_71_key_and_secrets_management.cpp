#include <algorithm>
#include <chrono>
#include <cstdint>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

/*
 * Key and Secrets Management
 * C++17 repository-independent governance engine.
 *
 * Implements:
 * - Encryption key inventory
 * - Key lifecycle and rotation
 * - Key version relationships
 * - Access-control policies
 * - Secret metadata and versioning
 * - Certificate lifecycle monitoring
 * - Audit events
 * - Merge-independent security policy evaluation
 *
 * Cryptographic operations are deliberately delegated to a
 * dedicated cryptographic provider or HSM.
 * This program does not implement encryption primitives.
 */

using Clock = std::chrono::system_clock;
using TimePoint = Clock::time_point;

// ============================================================
// DOMAIN TYPES
// ============================================================

enum class KeyAlgorithm {
    AES_256_GCM,
    HMAC_SHA256,
    ED25519
};

enum class KeyStatus {
    ACTIVE,
    DECRYPT_ONLY,
    REVOKED,
    DESTROYED
};

enum class SecretStatus {
    ACTIVE,
    DISABLED
};

enum class CertificateStatus {
    VALID,
    EXPIRING,
    EXPIRED,
    REVOKED
};

enum class Permission {
    READ,
    WRITE,
    ROTATE,
    REVOKE,
    ADMIN
};

enum class Operation {
    ENCRYPT,
    DECRYPT,
    SIGN,
    VERIFY
};

enum class AuditOutcome {
    SUCCESS,
    DENIED,
    FAILURE
};

struct SecurityException : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct EncryptionKey {
    std::string id;
    std::string alias;
    KeyAlgorithm algorithm;
    KeyStatus status;
    int version;
    int validityDays;
    TimePoint createdAt;
    TimePoint expiresAt;
    std::string fingerprint;
    std::optional<std::string> previousKeyId;
};

struct SecretRecord {
    std::string id;
    std::string name;
    int version;
    SecretStatus status;
    std::string encryptionKeyId;
    TimePoint createdAt;
    TimePoint updatedAt;
};

struct CertificateRecord {
    std::string id;
    std::string commonName;
    std::string issuer;
    std::string serialNumber;
    std::string fingerprint;
    TimePoint notBefore;
    TimePoint notAfter;
    bool revoked;
};

struct AuditEvent {
    std::string actor;
    std::string action;
    std::string resource;
    AuditOutcome outcome;
    TimePoint timestamp;
};

// ============================================================
// UTILITIES
// ============================================================

std::string toString(KeyStatus status) {
    switch (status) {
        case KeyStatus::ACTIVE: return "ACTIVE";
        case KeyStatus::DECRYPT_ONLY: return "DECRYPT_ONLY";
        case KeyStatus::REVOKED: return "REVOKED";
        case KeyStatus::DESTROYED: return "DESTROYED";
    }
    throw SecurityException("Unknown key status");
}

std::string toString(KeyAlgorithm algorithm) {
    switch (algorithm) {
        case KeyAlgorithm::AES_256_GCM: return "AES-256-GCM";
        case KeyAlgorithm::HMAC_SHA256: return "HMAC-SHA256";
        case KeyAlgorithm::ED25519: return "ED25519";
    }
    throw SecurityException("Unknown algorithm");
}

std::string toString(CertificateStatus status) {
    switch (status) {
        case CertificateStatus::VALID: return "VALID";
        case CertificateStatus::EXPIRING: return "EXPIRING";
        case CertificateStatus::EXPIRED: return "EXPIRED";
        case CertificateStatus::REVOKED: return "REVOKED";
    }
    throw SecurityException("Unknown certificate status");
}

std::string generateId(const std::string& prefix, int number) {
    return prefix + "-" + std::to_string(number);
}

// ============================================================
// AUTHORIZATION SERVICE
// ============================================================

class AuthorizationService {
private:
    std::unordered_map<std::string, std::set<Permission>> grants;

public:
    void grant(
        const std::string& principal,
        const std::set<Permission>& permissions
    ) {
        grants[principal].insert(
            permissions.begin(),
            permissions.end()
        );
    }

    void revoke(
        const std::string& principal,
        Permission permission
    ) {
        grants[principal].erase(permission);
    }

    void authorize(
        const std::string& principal,
        Permission permission
    ) const {
        auto it = grants.find(principal);

        if (it == grants.end() ||
            (!it->second.count(permission) &&
             !it->second.count(Permission::ADMIN))) {
            throw SecurityException(
                "Access denied for principal: " + principal
            );
        }
    }
};

// ============================================================
// AUDIT SERVICE
// ============================================================

class AuditService {
private:
    std::vector<AuditEvent> events;

public:
    void record(
        const std::string& actor,
        const std::string& action,
        const std::string& resource,
        AuditOutcome outcome = AuditOutcome::SUCCESS
    ) {
        events.push_back({
            actor,
            action,
            resource,
            outcome,
            Clock::now()
        });
    }

    const std::vector<AuditEvent>& getEvents() const {
        return events;
    }

    void report() const {
        std::cout << "\nAudit events: " << events.size() << "\n";

        for (const auto& event : events) {
            std::cout
                << event.actor << " | "
                << event.action << " | "
                << event.resource << "\n";
        }
    }
};

// ============================================================
// KEY MANAGEMENT ENGINE
// ============================================================

class KeyManagementEngine {
private:
    std::unordered_map<std::string, EncryptionKey> keys;
    std::unordered_map<std::string, std::vector<std::string>> aliases;

    AuthorizationService& authorization;
    AuditService& audit;

    int sequence = 1000;

    void validateAlgorithm(KeyAlgorithm algorithm) const {
        switch (algorithm) {
            case KeyAlgorithm::AES_256_GCM:
            case KeyAlgorithm::HMAC_SHA256:
            case KeyAlgorithm::ED25519:
                return;
        }

        throw SecurityException("Unsupported key algorithm");
    }

public:
    KeyManagementEngine(
        AuthorizationService& auth,
        AuditService& auditService
    ) : authorization(auth), audit(auditService) {}

    const EncryptionKey& createKey(
        const std::string& actor,
        const std::string& alias,
        KeyAlgorithm algorithm,
        int validityDays,
        std::optional<std::string> previous = std::nullopt
    ) {
        authorization.authorize(actor, Permission::WRITE);

        if (alias.empty() || alias.size() > 100) {
            throw SecurityException("Invalid key alias");
        }

        if (validityDays <= 0 || validityDays > 3650) {
            throw SecurityException("Invalid key validity");
        }

        validateAlgorithm(algorithm);

        int version = static_cast<int>(aliases[alias].size()) + 1;

        const auto now = Clock::now();

        EncryptionKey key{
            generateId("KEY", ++sequence),
            alias,
            algorithm,
            KeyStatus::ACTIVE,
            version,
            validityDays,
            now,
            now + std::chrono::hours(24 * validityDays),
            "PROVIDER-GENERATED-FINGERPRINT-" + std::to_string(sequence),
            previous
        };

        auto id = key.id;

        keys.emplace(id, std::move(key));
        aliases[alias].push_back(id);

        audit.record(actor, "CREATE_KEY", id);

        return keys.at(id);
    }

    const EncryptionKey& getKey(
        const std::string& actor,
        const std::string& id
    ) const {
        authorization.authorize(actor, Permission::READ);

        auto it = keys.find(id);

        if (it == keys.end()) {
            throw SecurityException("Key not found");
        }

        if (it->second.status == KeyStatus::DESTROYED ||
            it->second.status == KeyStatus::REVOKED) {
            throw SecurityException("Key unavailable");
        }

        return it->second;
    }

    const EncryptionKey& rotate(
        const std::string& actor,
        const std::string& id
    ) {
        authorization.authorize(actor, Permission::ROTATE);

        auto it = keys.find(id);

        if (it == keys.end()) {
            throw SecurityException("Key not found");
        }

        if (it->second.status != KeyStatus::ACTIVE) {
            throw SecurityException("Only active keys can rotate");
        }

        const std::string alias = it->second.alias;
        const auto algorithm = it->second.algorithm;
        const int validity = it->second.validityDays;

        // Retain the old key for historical decryption.
        it->second.status = KeyStatus::DECRYPT_ONLY;

        try {
            const auto& replacement = createKey(
                actor,
                alias,
                algorithm,
                validity,
                id
            );

            audit.record(actor, "ROTATE_KEY", id);
            return replacement;
        } catch (...) {
            it->second.status = KeyStatus::ACTIVE;
            throw;
        }
    }

    void revoke(
        const std::string& actor,
        const std::string& id
    ) {
        authorization.authorize(actor, Permission::REVOKE);

        auto it = keys.find(id);

        if (it == keys.end()) {
            throw SecurityException("Key not found");
        }

        if (it->second.status == KeyStatus::DESTROYED) {
            throw SecurityException("Key already destroyed");
        }

        it->second.status = KeyStatus::REVOKED;
        audit.record(actor, "REVOKE_KEY", id);
    }

    void destroy(
        const std::string& actor,
        const std::string& id
    ) {
        authorization.authorize(actor, Permission::ADMIN);

        auto it = keys.find(id);

        if (it == keys.end()) {
            throw SecurityException("Key not found");
        }

        if (it->second.status != KeyStatus::REVOKED &&
            it->second.status != KeyStatus::DECRYPT_ONLY) {
            throw SecurityException(
                "Key must be revoked or retired first"
            );
        }

        it->second.status = KeyStatus::DESTROYED;
        it->second.fingerprint.clear();

        audit.record(actor, "DESTROY_KEY", id);
    }

    bool permits(
        const std::string& id,
        Operation operation
    ) const {
        auto it = keys.find(id);

        if (it == keys.end()) {
            return false;
        }

        const auto& key = it->second;

        if (Clock::now() >= key.expiresAt) {
            return false;
        }

        switch (operation) {
            case Operation::ENCRYPT:
            case Operation::SIGN:
                return key.status == KeyStatus::ACTIVE;

            case Operation::DECRYPT:
            case Operation::VERIFY:
                return key.status == KeyStatus::ACTIVE ||
                       key.status == KeyStatus::DECRYPT_ONLY;
        }

        return false;
    }

    std::vector<EncryptionKey> inventory() const {
        std::vector<EncryptionKey> result;

        for (const auto& item : keys) {
            result.push_back(item.second);
        }

        std::sort(
            result.begin(),
            result.end(),
            [](const auto& a, const auto& b) {
                if (a.alias != b.alias) {
                    return a.alias < b.alias;
                }
                return a.version < b.version;
            }
        );

        return result;
    }
};

// ============================================================
// SECRETS MANAGEMENT
// ============================================================

class SecretsService {
private:
    std::unordered_map<std::string, SecretRecord> secrets;
    AuthorizationService& authorization;
    AuditService& audit;
    int sequence = 0;

public:
    SecretsService(
        AuthorizationService& auth,
        AuditService& auditService
    ) : authorization(auth), audit(auditService) {}

    const SecretRecord& create(
        const std::string& actor,
        const std::string& name,
        const std::string& encryptionKeyId
    ) {
        authorization.authorize(actor, Permission::WRITE);

        if (name.empty() || name.size() > 150) {
            throw SecurityException("Invalid secret name");
        }

        if (secrets.count(name)) {
            throw SecurityException("Secret already exists");
        }

        const auto now = Clock::now();

        SecretRecord record{
            generateId("SECRET", ++sequence),
            name,
            1,
            SecretStatus::ACTIVE,
            encryptionKeyId,
            now,
            now
        };

        secrets.emplace(name, std::move(record));

        audit.record(actor, "CREATE_SECRET", name);

        return secrets.at(name);
    }

    const SecretRecord& rotate(
        const std::string& actor,
        const std::string& name,
        const std::string& newKeyId
    ) {
        authorization.authorize(actor, Permission::WRITE);

        auto it = secrets.find(name);

        if (it == secrets.end() ||
            it->second.status != SecretStatus::ACTIVE) {
            throw SecurityException("Secret unavailable");
        }

        it->second.version++;
        it->second.encryptionKeyId = newKeyId;
        it->second.updatedAt = Clock::now();

        audit.record(actor, "ROTATE_SECRET", name);

        return it->second;
    }

    void disable(
        const std::string& actor,
        const std::string& name
    ) {
        authorization.authorize(actor, Permission::ADMIN);

        auto it = secrets.find(name);

        if (it == secrets.end()) {
            throw SecurityException("Secret not found");
        }

        it->second.status = SecretStatus::DISABLED;

        audit.record(actor, "DISABLE_SECRET", name);
    }

    std::vector<SecretRecord> inventory() const {
        std::vector<SecretRecord> result;

        for (const auto& item : secrets) {
            result.push_back(item.second);
        }

        return result;
    }
};

// ============================================================
// CERTIFICATE MANAGEMENT
// ============================================================

class CertificateService {
private:
    std::unordered_map<std::string, CertificateRecord> certificates;
    int sequence = 0;
    AuditService& audit;

public:
    explicit CertificateService(AuditService& auditService)
        : audit(auditService) {}

    const CertificateRecord& registerCertificate(
        const std::string& commonName,
        const std::string& issuer,
        const std::string& serial,
        const std::string& fingerprint,
        TimePoint notBefore,
        TimePoint notAfter
    ) {
        if (commonName.empty() || issuer.empty() ||
            serial.empty() || fingerprint.size() != 64) {
            throw SecurityException("Invalid certificate metadata");
        }

        if (notBefore >= notAfter) {
            throw SecurityException("Invalid validity interval");
        }

        for (const auto& item : certificates) {
            if (item.second.fingerprint == fingerprint) {
                throw SecurityException("Duplicate certificate");
            }
        }

        std::string id = generateId("CERT", ++sequence);

        CertificateRecord cert{
            id,
            commonName,
            issuer,
            serial,
            fingerprint,
            notBefore,
            notAfter,
            false
        };

        certificates.emplace(id, std::move(cert));

        audit.record(
            "certificate-service",
            "REGISTER_CERTIFICATE",
            id
        );

        return certificates.at(id);
    }

    CertificateStatus evaluate(const std::string& id) const {
        auto it = certificates.find(id);

        if (it == certificates.end()) {
            throw SecurityException("Certificate not found");
        }

        const auto& cert = it->second;
        const auto now = Clock::now();

        if (cert.revoked) {
            return CertificateStatus::REVOKED;
        }

        if (now < cert.notBefore) {
            throw SecurityException("Certificate is not yet valid");
        }

        if (now >= cert.notAfter) {
            return CertificateStatus::EXPIRED;
        }

        if (now >= cert.notAfter - std::chrono::hours(24 * 30)) {
            return CertificateStatus::EXPIRING;
        }

        return CertificateStatus::VALID;
    }

    void revoke(const std::string& id) {
        auto it = certificates.find(id);

        if (it == certificates.end()) {
            throw SecurityException("Certificate not found");
        }

        it->second.revoked = true;

        audit.record(
            "certificate-service",
            "REVOKE_CERTIFICATE",
            id
        );
    }
};

// ============================================================
// GOVERNANCE REPORT
// ============================================================

class GovernanceReport {
public:
    static void display(
        const std::vector<EncryptionKey>& keys,
        const std::vector<SecretRecord>& secrets
    ) {
        std::cout << "\nKEY INVENTORY\n";

        for (const auto& key : keys) {
            std::cout
                << key.id << " | "
                << key.alias << " | "
                << toString(key.algorithm) << " | "
                << "v" << key.version << " | "
                << toString(key.status) << "\n";
        }

        std::cout << "\nSECRET INVENTORY\n";

        for (const auto& secret : secrets) {
            std::cout
                << secret.name << " | "
                << "v" << secret.version << " | "
                << (secret.status == SecretStatus::ACTIVE
                    ? "ACTIVE" : "DISABLED")
                << " | Key: " << secret.encryptionKeyId
                << "\n";
        }
    }
};

// ============================================================
// EXECUTABLE SCENARIO
// ============================================================

int main() {
    try {
        AuthorizationService authorization;
        AuditService audit;

        authorization.grant(
            "security-admin",
            {
                Permission::READ,
                Permission::WRITE,
                Permission::ROTATE,
                Permission::REVOKE,
                Permission::ADMIN
            }
        );

        authorization.grant(
            "application",
            {
                Permission::READ,
                Permission::WRITE
            }
        );

        authorization.grant(
            "auditor",
            {Permission::READ}
        );

        KeyManagementEngine kms(authorization, audit);

        SecretsService secretsService(authorization, audit);

        CertificateService certificateService(audit);

        std::cout << "=== KEY MANAGEMENT ===\n";

        const auto& original = kms.createKey(
            "security-admin",
            "payments/master",
            KeyAlgorithm::AES_256_GCM,
            365
        );

        const std::string originalId = original.id;

        std::cout
            << "Created: " << originalId << "\n";

        if (!kms.permits(originalId, Operation::ENCRYPT)) {
            throw SecurityException("New key cannot encrypt");
        }

        std::cout << "Encryption permission: ALLOWED\n";

        const auto& rotated = kms.rotate(
            "security-admin",
            originalId
        );

        const std::string replacementId = rotated.id;

        std::cout
            << "Replacement: " << replacementId << "\n";

        std::cout
            << "Old key: "
            << toString(kms.getKey("auditor", originalId).status)
            << "\n";

        std::cout
            << "Old key decryption permission: "
            << (kms.permits(originalId, Operation::DECRYPT)
                ? "ALLOWED" : "DENIED")
            << "\n";

        std::cout
            << "Old key encryption permission: "
            << (kms.permits(originalId, Operation::ENCRYPT)
                ? "ALLOWED" : "DENIED")
            << "\n";

        std::cout << "\n=== SECRET MANAGEMENT ===\n";

        const auto& secret = secretsService.create(
            "security-admin",
            "database/password",
            replacementId
        );

        std::cout
            << "Secret created: " << secret.id << "\n";

        const auto& updated = secretsService.rotate(
            "security-admin",
            "database/password",
            replacementId
        );

        std::cout
            << "Secret version: " << updated.version << "\n";

        std::cout << "\n=== CERTIFICATE MANAGEMENT ===\n";

        const auto now = Clock::now();

        const auto& certificate =
            certificateService.registerCertificate(
                "api.internal.example",
                "Internal Root CA",
                "SERIAL-1001",
                std::string(64, 'a'),
                now - std::chrono::hours(24),
                now + std::chrono::hours(24 * 120)
            );

        std::cout
            << "Certificate status: "
            << toString(
                certificateService.evaluate(certificate.id)
            )
            << "\n";

        std::cout << "\n=== ACCESS CONTROL ===\n";

        try {
            kms.rotate("application", replacementId);
        } catch (const SecurityException& error) {
            std::cout
                << "Expected authorization failure: "
                << error.what() << "\n";
        }

        std::cout << "\n=== GOVERNANCE REPORT ===\n";

        GovernanceReport::display(
            kms.inventory(),
            secretsService.inventory()
        );

        audit.report();

        // Verify lifecycle invariants.
        if (kms.permits(originalId, Operation::ENCRYPT)) {
            throw SecurityException("Retired key can still encrypt");
        }

        if (!kms.permits(originalId, Operation::DECRYPT)) {
            throw SecurityException("Historical decryption unavailable");
        }

        if (kms.permits(replacementId, Operation::ENCRYPT) == false) {
            throw SecurityException("Replacement key cannot encrypt");
        }

        std::cout << "\nAll governance checks passed.\n";

        return 0;

    } catch (const std::exception& error) {
        std::cerr
            << "Security workflow failure: "
            << error.what() << "\n";

        return 1;
    }
}
