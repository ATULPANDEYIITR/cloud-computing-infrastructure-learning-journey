#include <algorithm>
#include <chrono>
#include <cstdint>
#include <exception>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

/*
 * Authentication and Authorization
 * C++17
 *
 * Repository-independent enterprise identity and access-control engine.
 *
 * Cryptographic operations are represented by injected credential
 * verification and token-signature interfaces. The demonstration
 * does not implement production password hashing or JWT signing.
 */

using namespace std;

// ============================================================
// Domain types
// ============================================================

enum class AccountStatus {
    ACTIVE,
    LOCKED,
    DISABLED
};

enum class SessionStatus {
    ACTIVE,
    REVOKED,
    EXPIRED
};

enum class Permission {
    PROFILE_READ,
    PROFILE_UPDATE,
    REPORTS_READ,
    USERS_MANAGE,
    SECURITY_MANAGE
};

enum class ReviewDecision {
    ALLOW,
    DENY
};

string permissionName(Permission permission) {
    switch (permission) {
        case Permission::PROFILE_READ: return "profile:read";
        case Permission::PROFILE_UPDATE: return "profile:update";
        case Permission::REPORTS_READ: return "reports:read";
        case Permission::USERS_MANAGE: return "users:manage";
        case Permission::SECURITY_MANAGE: return "security:manage";
    }

    throw invalid_argument("Unknown permission");
}

class AuthenticationError : public runtime_error {
public:
    using runtime_error::runtime_error;
};

class AuthorizationError : public runtime_error {
public:
    using runtime_error::runtime_error;
};

class ValidationError : public runtime_error {
public:
    using runtime_error::runtime_error;
};

// ============================================================
// User and resource models
// ============================================================

struct User {
    string id;
    string username;
    string credentialRecord;
    set<string> roles;
    string department;
    int clearance = 0;
    int failedAttempts = 0;
    AccountStatus status = AccountStatus::ACTIVE;
    bool mfaEnrolled = false;
};

struct Resource {
    string id;
    string department;
    string ownerId;
    int classification = 0;
};

struct Environment {
    bool mfaVerified = false;
    int riskScore = 100;
    string networkZone;
};

struct Session {
    string id;
    string userId;
    chrono::system_clock::time_point createdAt;
    chrono::system_clock::time_point expiresAt;
    SessionStatus status = SessionStatus::ACTIVE;
};

// ============================================================
// Credential verification interface
// ============================================================

class CredentialVerifier {
public:
    virtual ~CredentialVerifier() = default;

    virtual bool verify(
        const string& suppliedCredential,
        const string& storedRecord
    ) const = 0;
};

/*
 * Test-only verifier.
 *
 * Production implementations must use a dedicated password-hashing
 * library with Argon2id or an appropriately configured PBKDF2.
 */
class DemonstrationVerifier : public CredentialVerifier {
public:
    bool verify(
        const string& supplied,
        const string& stored
    ) const override {
        return supplied == stored;
    }
};

// ============================================================
// Random session identifier generation
// ============================================================

class IdentifierGenerator {
private:
    mt19937_64 engine;

public:
    IdentifierGenerator() : engine(random_device{}()) {}

    string generate() {
        uniform_int_distribution<uint64_t> distribution;

        ostringstream output;
        output << hex
               << distribution(engine)
               << distribution(engine);

        return output.str();
    }
};

// ============================================================
// Identity repository
// ============================================================

class IdentityRepository {
private:
    unordered_map<string, User> users;
    unordered_map<string, string> usernameIndex;

public:
    void addUser(const User& user) {
        if (user.id.empty() || user.username.empty()) {
            throw ValidationError("Invalid user identity");
        }

        if (users.count(user.id) ||
            usernameIndex.count(user.username)) {
            throw ValidationError("Duplicate identity");
        }

        if (user.roles.empty()) {
            throw ValidationError("User must have a role");
        }

        users.emplace(user.id, user);
        usernameIndex.emplace(user.username, user.id);
    }

    User* findByUsername(const string& username) {
        auto index = usernameIndex.find(username);

        if (index == usernameIndex.end()) {
            return nullptr;
        }

        return &users.at(index->second);
    }

    User* findById(const string& id) {
        auto iterator = users.find(id);

        return iterator == users.end()
            ? nullptr
            : &iterator->second;
    }

    const unordered_map<string, User>& all() const {
        return users;
    }
};

// ============================================================
// Password authentication and account lockout
// ============================================================

class AuthenticationService {
private:
    IdentityRepository& repository;
    const CredentialVerifier& verifier;

    static constexpr int MAX_ATTEMPTS = 5;

public:
    AuthenticationService(
        IdentityRepository& repository,
        const CredentialVerifier& verifier
    )
        : repository(repository), verifier(verifier) {}

    User& authenticate(
        const string& username,
        const string& password,
        bool mfaVerified
    ) {
        User* user = repository.findByUsername(username);

        if (!user || user->status != AccountStatus::ACTIVE) {
            throw AuthenticationError("Account unavailable");
        }

        if (user->failedAttempts >= MAX_ATTEMPTS) {
            user->status = AccountStatus::LOCKED;
            throw AuthenticationError("Account locked");
        }

        if (!verifier.verify(password, user->credentialRecord)) {
            user->failedAttempts++;

            if (user->failedAttempts >= MAX_ATTEMPTS) {
                user->status = AccountStatus::LOCKED;
            }

            throw AuthenticationError("Invalid credentials");
        }

        if (user->mfaEnrolled && !mfaVerified) {
            throw AuthenticationError("MFA required");
        }

        user->failedAttempts = 0;

        return *user;
    }
};

// ============================================================
// Session lifecycle
// ============================================================

class SessionService {
private:
    unordered_map<string, Session> sessions;
    IdentifierGenerator generator;

    chrono::seconds lifetime{1800};

public:
    Session create(const User& user) {
        if (user.status != AccountStatus::ACTIVE) {
            throw AuthenticationError("Account unavailable");
        }

        auto now = chrono::system_clock::now();

        Session session{
            generator.generate(),
            user.id,
            now,
            now + lifetime,
            SessionStatus::ACTIVE
        };

        sessions.emplace(session.id, session);

        return session;
    }

    const Session& validate(const string& id) {
        auto iterator = sessions.find(id);

        if (iterator == sessions.end()) {
            throw AuthenticationError("Unknown session");
        }

        Session& session = iterator->second;

        if (session.status != SessionStatus::ACTIVE) {
            throw AuthenticationError("Session unavailable");
        }

        if (chrono::system_clock::now() >= session.expiresAt) {
            session.status = SessionStatus::EXPIRED;
            throw AuthenticationError("Session expired");
        }

        return session;
    }

    bool revoke(const string& id) {
        auto iterator = sessions.find(id);

        if (iterator == sessions.end() ||
            iterator->second.status != SessionStatus::ACTIVE) {
            return false;
        }

        iterator->second.status = SessionStatus::REVOKED;
        return true;
    }

    size_t revokeAll(const string& userId) {
        size_t count = 0;

        for (auto& entry : sessions) {
            Session& session = entry.second;

            if (session.userId == userId &&
                session.status == SessionStatus::ACTIVE) {
                session.status = SessionStatus::REVOKED;
                ++count;
            }
        }

        return count;
    }

    size_t activeCount() const {
        return count_if(
            sessions.begin(),
            sessions.end(),
            [](const auto& entry) {
                return entry.second.status == SessionStatus::ACTIVE;
            }
        );
    }
};

// ============================================================
// RBAC engine
// ============================================================

class RBACPolicy {
private:
    map<string, set<Permission>> rolePermissions;

public:
    RBACPolicy() {
        rolePermissions["employee"] = {
            Permission::PROFILE_READ,
            Permission::PROFILE_UPDATE
        };

        rolePermissions["analyst"] = {
            Permission::PROFILE_READ,
            Permission::REPORTS_READ
        };

        rolePermissions["admin"] = {
            Permission::PROFILE_READ,
            Permission::PROFILE_UPDATE,
            Permission::REPORTS_READ,
            Permission::USERS_MANAGE,
            Permission::SECURITY_MANAGE
        };
    }

    bool allows(
        const set<string>& roles,
        Permission permission
    ) const {
        for (const string& role : roles) {
            auto iterator = rolePermissions.find(role);

            if (iterator != rolePermissions.end() &&
                iterator->second.count(permission)) {
                return true;
            }
        }

        return false;
    }
};

// ============================================================
// ABAC engine
// ============================================================

class ABACPolicy {
public:
    ReviewDecision evaluate(
        const User& subject,
        const Resource& resource,
        const string& action,
        const Environment& environment
    ) const {

        if (subject.status != AccountStatus::ACTIVE ||
            !environment.mfaVerified ||
            environment.riskScore > 70) {
            return ReviewDecision::DENY;
        }

        if (action == "read") {
            bool sameDepartment =
                subject.department == resource.department;

            bool administrator =
                subject.roles.count("admin") > 0;

            return sameDepartment || administrator
                ? ReviewDecision::ALLOW
                : ReviewDecision::DENY;
        }

        if (action == "approve") {
            bool authorized =
                subject.department == resource.department &&
                subject.clearance >= resource.classification &&
                subject.id != resource.ownerId;

            return authorized
                ? ReviewDecision::ALLOW
                : ReviewDecision::DENY;
        }

        return ReviewDecision::DENY;
    }
};

// ============================================================
// Token validation interface
// ============================================================

struct TokenClaims {
    string subject;
    string issuer;
    string audience;
    chrono::system_clock::time_point expiresAt;
    set<string> roles;
};

class TokenSignatureVerifier {
public:
    virtual ~TokenSignatureVerifier() = default;

    virtual bool verifySignature(
        const string& token
    ) const = 0;

    virtual TokenClaims decodeClaims(
        const string& token
    ) const = 0;
};

class TokenValidationService {
private:
    const TokenSignatureVerifier& verifier;

public:
    explicit TokenValidationService(
        const TokenSignatureVerifier& verifier
    ) : verifier(verifier) {}

    TokenClaims validate(const string& token) const {
        if (!verifier.verifySignature(token)) {
            throw AuthenticationError("Invalid token signature");
        }

        TokenClaims claims = verifier.decodeClaims(token);

        if (claims.subject.empty() ||
            claims.issuer != "identity.example" ||
            claims.audience != "api.example") {
            throw AuthenticationError("Invalid token claims");
        }

        if (claims.expiresAt <= chrono::system_clock::now()) {
            throw AuthenticationError("Expired token");
        }

        return claims;
    }
};

// ============================================================
// OAuth PKCE verification
// ============================================================

class OAuthClient {
public:
    static bool validateRedirect(
        const string& requested,
        const set<string>& registered
    ) {
        return registered.count(requested) > 0;
    }

    /*
     * PKCE S256 requires SHA-256 and Base64URL encoding.
     * A production implementation should use a cryptographic
     * library to calculate and compare the actual challenge.
     *
     * This interface accepts the result from that trusted layer.
     */
    static bool validatePKCE(
        const string& expectedChallenge,
        const string& calculatedChallenge
    ) {
        if (expectedChallenge.size() != 43 ||
            calculatedChallenge.size() != 43) {
            return false;
        }

        unsigned char difference = 0;

        for (size_t i = 0; i < 43; ++i) {
            difference |=
                static_cast<unsigned char>(
                    expectedChallenge[i] ^ calculatedChallenge[i]
                );
        }

        return difference == 0;
    }
};

// ============================================================
// Central authorization service
// ============================================================

class AuthorizationService {
private:
    const RBACPolicy& rbac;
    const ABACPolicy& abac;

public:
    AuthorizationService(
        const RBACPolicy& rbac,
        const ABACPolicy& abac
    ) : rbac(rbac), abac(abac) {}

    void requirePermission(
        const User& user,
        Permission permission
    ) const {
        if (user.status != AccountStatus::ACTIVE ||
            !rbac.allows(user.roles, permission)) {
            throw AuthorizationError("Permission denied");
        }
    }

    void requireResourceAccess(
        const User& user,
        const Resource& resource,
        const string& action,
        const Environment& environment
    ) const {
        if (abac.evaluate(
            user,
            resource,
            action,
            environment
        ) != ReviewDecision::ALLOW) {
            throw AuthorizationError("ABAC policy denied access");
        }
    }
};

// ============================================================
// Demonstration
// ============================================================

int main() {
    try {
        cout << "AUTHENTICATION AND AUTHORIZATION ENGINE\n";
        cout << "========================================\n";

        IdentityRepository repository;

        repository.addUser({
            "U001",
            "alice",
            "DemoPassword#2026",
            {"employee"},
            "engineering",
            2,
            0,
            AccountStatus::ACTIVE,
            true
        });

        repository.addUser({
            "U002",
            "bob",
            "AdminPassword#2026",
            {"admin"},
            "security",
            5,
            0,
            AccountStatus::ACTIVE,
            false
        });

        DemonstrationVerifier verifier;

        AuthenticationService authentication(
            repository,
            verifier
        );

        SessionService sessionService;

        RBACPolicy rbac;
        ABACPolicy abac;

        AuthorizationService authorization(
            rbac,
            abac
        );

        // Password plus MFA.
        cout << "\n1. Authentication\n";

        User& alice = authentication.authenticate(
            "alice",
            "DemoPassword#2026",
            true
        );

        cout << "Authenticated: " << alice.username << '\n';

        // Session creation.
        cout << "\n2. Session management\n";

        Session session = sessionService.create(alice);

        sessionService.validate(session.id);

        cout << "Session active: "
             << (sessionService.activeCount() == 1)
             << '\n';

        // Role authorization.
        cout << "\n3. RBAC evaluation\n";

        authorization.requirePermission(
            alice,
            Permission::PROFILE_READ
        );

        cout << "Profile read permitted\n";

        try {
            authorization.requirePermission(
                alice,
                Permission::USERS_MANAGE
            );
        } catch (const AuthorizationError& error) {
            cout << "Administrative access rejected: "
                 << error.what() << '\n';
        }

        // Attribute authorization.
        cout << "\n4. ABAC evaluation\n";

        Resource report{
            "R001",
            "engineering",
            "U003",
            1
        };

        Environment environment{
            true,
            15,
            "corporate"
        };

        authorization.requireResourceAccess(
            alice,
            report,
            "read",
            environment
        );

        cout << "Department resource access permitted\n";

        // Risk-based denial.
        cout << "\n5. Risk evaluation\n";

        environment.riskScore = 95;

        try {
            authorization.requireResourceAccess(
                alice,
                report,
                "read",
                environment
            );
        } catch (const AuthorizationError& error) {
            cout << "High-risk request rejected: "
                 << error.what() << '\n';
        }

        // OAuth redirect validation.
        cout << "\n6. OAuth client validation\n";

        set<string> registeredRedirects = {
            "https://client.example/callback"
        };

        bool redirectValid = OAuthClient::validateRedirect(
            "https://client.example/callback",
            registeredRedirects
        );

        cout << "Registered redirect: "
             << boolalpha << redirectValid << '\n';

        // PKCE comparison.
        cout << "\n7. PKCE challenge validation\n";

        string challenge(43, 'A');

        cout << "Matching challenge: "
             << OAuthClient::validatePKCE(challenge, challenge)
             << '\n';

        // Session revocation.
        cout << "\n8. Logout and revocation\n";

        sessionService.revoke(session.id);

        try {
            sessionService.validate(session.id);
        } catch (const AuthenticationError& error) {
            cout << "Revoked session rejected: "
                 << error.what() << '\n';
        }

        // Administrator permissions.
        User* bob = repository.findById("U002");

        authorization.requirePermission(
            *bob,
            Permission::USERS_MANAGE
        );

        cout << "\nAdministrator permission verified\n";

        cout << "\nExecution completed successfully.\n";

    } catch (const exception& error) {
        cerr << "Security engine error: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}
