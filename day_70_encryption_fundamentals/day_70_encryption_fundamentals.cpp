#include <algorithm>
#include <array>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Encryption Fundamentals: C++17
 *
 * Implements an encryption architecture and policy engine.
 *
 * Important distinction:
 * The C++ standard library does not provide cryptographic
 * encryption algorithms. This implementation deliberately
 * does not invent an AES, RSA, or TLS replacement.
 *
 * Cryptographic operations are represented by a strictly
 * validated provider interface. A production adapter must
 * implement the interface using a vetted cryptographic
 * library or an operating-system cryptographic service.
 *
 * This program implements:
 * - Symmetric encryption policy.
 * - Asymmetric encryption policy.
 * - Encryption-at-rest requirements.
 * - Encryption-in-transit requirements.
 * - Hybrid encryption requirements.
 * - Key lifecycle and rotation.
 * - Algorithm selection.
 * - Authenticated envelope validation.
 * - Merge-like security policy evaluation.
 *
 * Compile:
 * g++ -std=c++17 -Wall -Wextra -pedantic encryption.cpp -o encryption
 */

namespace security {

enum class EncryptionType {
    Symmetric,
    Asymmetric,
    Hybrid
};

enum class ProtectionLocation {
    AtRest,
    InTransit
};

enum class KeyStatus {
    Active,
    Retired,
    Revoked
};

enum class TLSVersion {
    TLS12,
    TLS13
};

enum class Decision {
    Allowed,
    Denied
};

std::string toString(EncryptionType type) {
    switch (type) {
        case EncryptionType::Symmetric:
            return "Symmetric";
        case EncryptionType::Asymmetric:
            return "Asymmetric";
        case EncryptionType::Hybrid:
            return "Hybrid";
    }

    throw std::invalid_argument("Unknown encryption type");
}

std::string toString(KeyStatus status) {
    switch (status) {
        case KeyStatus::Active:
            return "Active";
        case KeyStatus::Retired:
            return "Retired";
        case KeyStatus::Revoked:
            return "Revoked";
    }

    throw std::invalid_argument("Unknown key status");
}

class ValidationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class SecurityError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct EncryptionPolicy {
    std::string policyId;
    ProtectionLocation location;
    EncryptionType requiredType;

    bool requireAuthentication = true;
    bool requireUniqueNonce = true;
    bool allowLegacyAlgorithms = false;
    bool requireCertificateValidation = false;

    int minimumAesBits = 256;
    int minimumRsaBits = 3072;
    TLSVersion minimumTLS = TLSVersion::TLS12;
};

struct KeyRecord {
    std::string keyId;
    std::string algorithm;
    KeyStatus status;
    int strengthBits;
    std::uint64_t generation;
};

struct EncryptionRequest {
    std::string resource;
    ProtectionLocation location;
    EncryptionType type;

    std::string algorithm;
    std::string keyId;

    int keyStrengthBits = 0;
    bool authenticated = false;
    bool nonceUnique = false;
    bool certificateValid = false;

    TLSVersion tlsVersion = TLSVersion::TLS12;
};

struct EvaluationResult {
    Decision decision;
    std::vector<std::string> reasons;

    bool allowed() const {
        return decision == Decision::Allowed;
    }
};

/*
 * The provider interface separates cryptographic execution
 * from application policy.
 *
 * A real provider must perform actual authenticated
 * encryption and must never silently return plaintext.
 */
class CryptographicProvider {
public:
    virtual ~CryptographicProvider() = default;

    virtual std::string algorithmName() const = 0;

    virtual std::vector<std::uint8_t> encrypt(
        const std::vector<std::uint8_t>& plaintext,
        const std::string& keyId
    ) = 0;

    virtual std::vector<std::uint8_t> decrypt(
        const std::vector<std::uint8_t>& ciphertext,
        const std::string& keyId
    ) = 0;
};

class KeyRegistry {
private:
    std::map<std::string, KeyRecord> keys;
    std::optional<std::string> activeKey;

public:
    void registerKey(const KeyRecord& record) {
        if (record.keyId.empty()) {
            throw ValidationError("Key identifier cannot be empty");
        }

        if (record.strengthBits <= 0) {
            throw ValidationError("Invalid key strength");
        }

        if (keys.count(record.keyId)) {
            throw ValidationError("Duplicate key identifier");
        }

        if (record.status == KeyStatus::Active) {
            if (activeKey.has_value()) {
                keys.at(*activeKey).status = KeyStatus::Retired;
            }

            activeKey = record.keyId;
        }

        keys.emplace(record.keyId, record);
    }

    const KeyRecord& get(const std::string& id) const {
        auto it = keys.find(id);

        if (it == keys.end()) {
            throw SecurityError("Unknown key identifier");
        }

        if (it->second.status == KeyStatus::Revoked) {
            throw SecurityError("Key has been revoked");
        }

        return it->second;
    }

    const KeyRecord& getActive() const {
        if (!activeKey.has_value()) {
            throw SecurityError("No active key");
        }

        return get(*activeKey);
    }

    void rotate(const KeyRecord& newKey) {
        if (newKey.status != KeyStatus::Active) {
            throw ValidationError(
                "Rotation requires an active replacement key"
            );
        }

        registerKey(newKey);
    }

    void revoke(const std::string& id) {
        auto it = keys.find(id);

        if (it == keys.end()) {
            throw SecurityError("Unknown key");
        }

        it->second.status = KeyStatus::Revoked;

        if (activeKey.has_value() && *activeKey == id) {
            activeKey.reset();
        }
    }

    std::vector<KeyRecord> inventory() const {
        std::vector<KeyRecord> result;

        for (const auto& item : keys) {
            result.push_back(item.second);
        }

        return result;
    }
};

class SecurityPolicyEngine {
private:
    std::map<std::string, EncryptionPolicy> policies;

    static bool validAlgorithm(
        EncryptionType type,
        const std::string& algorithm
    ) {
        switch (type) {
            case EncryptionType::Symmetric:
                return algorithm == "AES-256-GCM";

            case EncryptionType::Asymmetric:
                return algorithm == "RSA-OAEP-SHA256";

            case EncryptionType::Hybrid:
                return algorithm ==
                    "AES-256-GCM+RSA-OAEP-SHA256";
        }

        return false;
    }

public:
    void addPolicy(const EncryptionPolicy& policy) {
        if (policy.policyId.empty()) {
            throw ValidationError("Policy identifier is required");
        }

        if (policy.minimumAesBits < 256 ||
            policy.minimumRsaBits < 2048) {
            throw ValidationError("Weak minimum security parameters");
        }

        if (policies.count(policy.policyId)) {
            throw ValidationError("Duplicate policy");
        }

        policies.emplace(policy.policyId, policy);
    }

    EvaluationResult evaluate(
        const EncryptionRequest& request,
        const KeyRegistry& registry
    ) const {

        EvaluationResult result{
            Decision::Allowed,
            {}
        };

        auto reject = [&](const std::string& reason) {
            result.decision = Decision::Denied;
            result.reasons.push_back(reason);
        };

        if (request.resource.empty()) {
            reject("Resource identifier is missing");
            return result;
        }

        const EncryptionPolicy* selected = nullptr;

        for (const auto& item : policies) {
            if (item.second.location == request.location) {
                selected = &item.second;
                break;
            }
        }

        if (!selected) {
            reject("No policy exists for requested location");
            return result;
        }

        if (request.type != selected->requiredType) {
            reject("Encryption type violates policy");
        }

        if (!validAlgorithm(request.type, request.algorithm)) {
            reject("Unsupported or disallowed algorithm");
        }

        if (request.keyStrengthBits < selected->minimumAesBits &&
            request.type != EncryptionType::Asymmetric) {
            reject("Symmetric key strength is insufficient");
        }

        if (request.type == EncryptionType::Asymmetric &&
            request.keyStrengthBits < selected->minimumRsaBits) {
            reject("RSA key strength is insufficient");
        }

        if (selected->requireAuthentication &&
            !request.authenticated) {
            reject("Authenticated encryption is required");
        }

        if (selected->requireUniqueNonce &&
            request.type != EncryptionType::Asymmetric &&
            !request.nonceUnique) {
            reject("Nonce uniqueness requirement not satisfied");
        }

        if (selected->requireCertificateValidation &&
            !request.certificateValid) {
            reject("Certificate validation failed");
        }

        if (request.location == ProtectionLocation::InTransit) {
            if (request.tlsVersion < selected->minimumTLS) {
                reject("TLS version is below policy minimum");
            }
        }

        try {
            const auto& key = registry.get(request.keyId);

            if (key.status != KeyStatus::Active) {
                reject("Encryption requires an active key");
            }

            if (request.type == EncryptionType::Symmetric &&
                key.strengthBits < selected->minimumAesBits) {
                reject("Registered key is too weak");
            }

            if (request.type == EncryptionType::Asymmetric &&
                key.strengthBits < selected->minimumRsaBits) {
                reject("Registered RSA key is too weak");
            }

        } catch (const SecurityError& error) {
            reject(error.what());
        }

        return result;
    }
};

struct EnvelopeMetadata {
    std::string version;
    std::string algorithm;
    std::string keyId;
    std::string nonce;
    std::string authenticationTag;
    std::string ciphertext;
};

class EnvelopeValidator {
public:
    static void validate(const EnvelopeMetadata& envelope) {
        if (envelope.version != "1") {
            throw ValidationError("Unsupported envelope version");
        }

        if (envelope.algorithm != "AES-256-GCM") {
            throw ValidationError("Unsupported envelope algorithm");
        }

        if (envelope.keyId.empty()) {
            throw ValidationError("Missing key identifier");
        }

        if (envelope.nonce.size() != 24) {
            throw ValidationError(
                "GCM nonce must contain 12 bytes encoded as hexadecimal"
            );
        }

        if (envelope.authenticationTag.size() != 32) {
            throw ValidationError(
                "GCM authentication tag must contain 16 bytes encoded as hexadecimal"
            );
        }

        if (envelope.ciphertext.empty()) {
            throw ValidationError("Ciphertext cannot be empty");
        }
    }
};

void demonstratePolicyEngine() {
    KeyRegistry registry;

    registry.registerKey({
        "storage-key-001",
        "AES-256-GCM",
        KeyStatus::Active,
        256,
        1
    });

    registry.registerKey({
        "rsa-key-001",
        "RSA-OAEP-SHA256",
        KeyStatus::Active,
        3072,
        1
    });

    SecurityPolicyEngine engine;

    engine.addPolicy({
        "REST-001",
        ProtectionLocation::AtRest,
        EncryptionType::Symmetric,
        true,
        true,
        false,
        false,
        256,
        3072,
        TLSVersion::TLS12
    });

    engine.addPolicy({
        "TRANSIT-001",
        ProtectionLocation::InTransit,
        EncryptionType::Hybrid,
        true,
        true,
        false,
        true,
        256,
        3072,
        TLSVersion::TLS12
    });

    EncryptionRequest validStorage{
        "customer-record-001",
        ProtectionLocation::AtRest,
        EncryptionType::Symmetric,
        "AES-256-GCM",
        "storage-key-001",
        256,
        true,
        true,
        false,
        TLSVersion::TLS12
    };

    EncryptionRequest invalidStorage = validStorage;
    invalidStorage.authenticated = false;

    EncryptionRequest validTransit{
        "payment-message-001",
        ProtectionLocation::InTransit,
        EncryptionType::Hybrid,
        "AES-256-GCM+RSA-OAEP-SHA256",
        "rsa-key-001",
        3072,
        true,
        true,
        true,
        TLSVersion::TLS13
    };

    EncryptionRequest invalidTransit = validTransit;
    invalidTransit.certificateValid = false;

    auto printResult = [&](const std::string& title,
                           const EvaluationResult& result) {
        std::cout << "\n" << title << "\n";
        std::cout << "Decision: "
                  << (result.allowed() ? "ALLOWED" : "DENIED")
                  << "\n";

        for (const auto& reason : result.reasons) {
            std::cout << "Reason: " << reason << "\n";
        }
    };

    printResult(
        "Valid storage request",
        engine.evaluate(validStorage, registry)
    );

    printResult(
        "Unauthenticated storage request",
        engine.evaluate(invalidStorage, registry)
    );

    printResult(
        "Valid transit request",
        engine.evaluate(validTransit, registry)
    );

    printResult(
        "Invalid certificate request",
        engine.evaluate(invalidTransit, registry)
    );
}

void demonstrateKeyRotation() {
    KeyRegistry registry;

    registry.registerKey({
        "key-generation-1",
        "AES-256-GCM",
        KeyStatus::Active,
        256,
        1
    });

    registry.rotate({
        "key-generation-2",
        "AES-256-GCM",
        KeyStatus::Active,
        256,
        2
    });

    std::cout << "\nKey lifecycle\n";

    for (const auto& key : registry.inventory()) {
        std::cout << key.keyId
                  << " | "
                  << toString(key.status)
                  << " | generation "
                  << key.generation
                  << "\n";
    }
}

void demonstrateEnvelopeValidation() {
    EnvelopeMetadata valid{
        "1",
        "AES-256-GCM",
        "storage-key-001",
        "00112233445566778899aabb",
        "00112233445566778899aabbccddeeff",
        "authenticated-ciphertext"
    };

    EnvelopeValidator::validate(valid);

    std::cout << "\nEnvelope structure: VALID\n";

    EnvelopeMetadata invalid = valid;
    invalid.nonce = "1234";

    try {
        EnvelopeValidator::validate(invalid);
    } catch (const ValidationError& error) {
        std::cout << "Invalid envelope rejected: "
                  << error.what() << "\n";
    }
}

void demonstrateSecurityFailures() {
    KeyRegistry registry;

    registry.registerKey({
        "temporary-key",
        "AES-256-GCM",
        KeyStatus::Active,
        256,
        1
    });

    registry.revoke("temporary-key");

    try {
        registry.get("temporary-key");
    } catch (const SecurityError& error) {
        std::cout << "\nRevoked key rejected: "
                  << error.what() << "\n";
    }
}

} // namespace security

int main() {
    try {
        std::cout << "ENCRYPTION FUNDAMENTALS\n";
        std::cout << "======================\n";

        security::demonstratePolicyEngine();
        security::demonstrateKeyRotation();
        security::demonstrateEnvelopeValidation();
        security::demonstrateSecurityFailures();

        std::cout << "\nExecution completed successfully.\n";

    } catch (const std::exception& error) {
        std::cerr << "Security subsystem error: "
                  << error.what() << "\n";

        return 1;
    }

    return 0;
}
