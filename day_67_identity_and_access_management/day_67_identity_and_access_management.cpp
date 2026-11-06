#include <algorithm>
#include <chrono>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

class IAMException : public runtime_error {
public:
    explicit IAMException(const string& message)
        : runtime_error(message) {}
};

enum class Effect {
    ALLOW,
    DENY
};

enum class Decision {
    ALLOW,
    DENY
};

string toString(Decision decision) {
    return decision == Decision::ALLOW ? "ALLOW" : "DENY";
}

struct Permission {
    string resource;
    string action;

    void validate() const {
        if (resource.empty() || action.empty()) {
            throw IAMException("Permission fields cannot be empty.");
        }

        if (resource.find("..") != string::npos) {
            throw IAMException("Invalid resource path.");
        }
    }

    bool matches(
        const string& requestedResource,
        const string& requestedAction
    ) const {
        bool resourceMatch = resource == "*" ||
                             resource == requestedResource;

        if (!resourceMatch && resource.size() >= 2 &&
            resource.substr(resource.size() - 2) == "/*") {
            string prefix = resource.substr(0, resource.size() - 1);

            resourceMatch =
                requestedResource.compare(0, prefix.size(), prefix) == 0;
        }

        bool actionMatch =
            action == "*" || action == requestedAction;

        return resourceMatch && actionMatch;
    }
};

struct User {
    string id;
    string email;
    bool active = true;
    set<string> groups;
};

struct Group {
    string id;
    string name;
    set<string> roles;
};

struct Role {
    string id;
    string name;
    vector<Permission> permissions;
};

struct Policy {
    string id;
    string name;
    Effect effect;
    Permission permission;
    set<string> users;
    set<string> groups;
    bool active = true;
};

struct Assignment {
    string userId;
    string roleId;
    optional<chrono::system_clock::time_point> expiresAt;

    bool isActive(
        chrono::system_clock::time_point now
    ) const {
        return !expiresAt || now < *expiresAt;
    }
};

struct AccessRequest {
    string userId;
    string resource;
    string action;
};

struct AccessResult {
    Decision decision;
    string reason;
    vector<string> roles;
    vector<string> policies;
};

class IAMEngine {
private:
    map<string, User> users;
    map<string, Group> groups;
    map<string, Role> roles;
    map<string, Policy> policies;
    vector<Assignment> assignments;

    const User& getUser(const string& id) const {
        auto it = users.find(id);

        if (it == users.end()) {
            throw IAMException("Unknown user: " + id);
        }

        return it->second;
    }

    const Group& getGroup(const string& id) const {
        auto it = groups.find(id);

        if (it == groups.end()) {
            throw IAMException("Unknown group: " + id);
        }

        return it->second;
    }

    const Role& getRole(const string& id) const {
        auto it = roles.find(id);

        if (it == roles.end()) {
            throw IAMException("Unknown role: " + id);
        }

        return it->second;
    }

public:
    void addUser(const User& user) {
        if (user.id.empty() ||
            user.email.find('@') == string::npos) {
            throw IAMException("Invalid user.");
        }

        if (users.count(user.id)) {
            throw IAMException("Duplicate user.");
        }

        users.emplace(user.id, user);
    }

    void addGroup(const Group& group) {
        if (group.id.empty() || group.name.empty()) {
            throw IAMException("Invalid group.");
        }

        if (groups.count(group.id)) {
            throw IAMException("Duplicate group.");
        }

        groups.emplace(group.id, group);
    }

    void addRole(const Role& role) {
        if (role.id.empty() || role.permissions.empty()) {
            throw IAMException("Invalid role.");
        }

        if (roles.count(role.id)) {
            throw IAMException("Duplicate role.");
        }

        for (const auto& permission : role.permissions) {
            permission.validate();
        }

        roles.emplace(role.id, role);
    }

    void addMembership(
        const string& userId,
        const string& groupId
    ) {
        getGroup(groupId);

        auto it = users.find(userId);

        if (it == users.end()) {
            throw IAMException("Unknown user.");
        }

        if (!it->second.groups.insert(groupId).second) {
            throw IAMException("Duplicate membership.");
        }
    }

    void assignRoleToGroup(
        const string& groupId,
        const string& roleId
    ) {
        getRole(roleId);

        auto it = groups.find(groupId);

        if (it == groups.end()) {
            throw IAMException("Unknown group.");
        }

        if (!it->second.roles.insert(roleId).second) {
            throw IAMException("Duplicate role assignment.");
        }
    }

    void assignRole(
        const string& userId,
        const string& roleId,
        optional<chrono::system_clock::time_point> expiry = nullopt
    ) {
        getUser(userId);
        getRole(roleId);

        if (expiry && *expiry <= chrono::system_clock::now()) {
            throw IAMException("Expiration must be in the future.");
        }

        for (const auto& assignment : assignments) {
            if (
                assignment.userId == userId &&
                assignment.roleId == roleId &&
                assignment.expiresAt == expiry
            ) {
                throw IAMException("Duplicate assignment.");
            }
        }

        assignments.push_back({userId, roleId, expiry});
    }

    void revokeRole(
        const string& userId,
        const string& roleId
    ) {
        getUser(userId);
        getRole(roleId);

        auto oldSize = assignments.size();

        assignments.erase(
            remove_if(
                assignments.begin(),
                assignments.end(),
                [&](const Assignment& assignment) {
                    return assignment.userId == userId &&
                           assignment.roleId == roleId;
                }
            ),
            assignments.end()
        );

        if (oldSize == assignments.size()) {
            throw IAMException("Assignment not found.");
        }
    }

    void deactivateUser(const string& userId) {
        auto it = users.find(userId);

        if (it == users.end()) {
            throw IAMException("Unknown user.");
        }

        it->second.active = false;
    }

    void addPolicy(const Policy& policy) {
        if (policy.id.empty()) {
            throw IAMException("Policy ID is required.");
        }

        if (policies.count(policy.id)) {
            throw IAMException("Duplicate policy.");
        }

        if (policy.users.empty() && policy.groups.empty()) {
            throw IAMException("Policy requires a principal.");
        }

        policy.permission.validate();

        for (const auto& id : policy.users) {
            getUser(id);
        }

        for (const auto& id : policy.groups) {
            getGroup(id);
        }

        policies.emplace(policy.id, policy);
    }

    set<string> effectiveRoles(
        const string& userId,
        chrono::system_clock::time_point now
    ) const {
        const User& user = getUser(userId);

        set<string> result;

        if (!user.active) {
            return result;
        }

        for (const auto& groupId : user.groups) {
            const Group& group = getGroup(groupId);

            result.insert(
                group.roles.begin(),
                group.roles.end()
            );
        }

        for (const auto& assignment : assignments) {
            if (
                assignment.userId == userId &&
                assignment.isActive(now)
            ) {
                result.insert(assignment.roleId);
            }
        }

        return result;
    }

    AccessResult evaluate(const AccessRequest& request) const {
        if (request.resource.empty() || request.action.empty()) {
            throw IAMException("Invalid access request.");
        }

        const User& user = getUser(request.userId);

        if (!user.active) {
            return {
                Decision::DENY,
                "Inactive user.",
                {},
                {}
            };
        }

        const auto now = chrono::system_clock::now();

        auto roleIds = effectiveRoles(request.userId, now);

        vector<string> matchedRoles;
        vector<string> matchedPolicies;

        bool roleAllowed = false;
        bool policyAllowed = false;
        bool explicitDenied = false;

        for (const auto& roleId : roleIds) {
            const Role& role = getRole(roleId);

            bool matched = any_of(
                role.permissions.begin(),
                role.permissions.end(),
                [&](const Permission& permission) {
                    return permission.matches(
                        request.resource,
                        request.action
                    );
                }
            );

            if (matched) {
                roleAllowed = true;
                matchedRoles.push_back(role.name);
            }
        }

        for (const auto& [policyId, policy] : policies) {
            if (!policy.active) {
                continue;
            }

            bool principalMatch =
                policy.users.count(request.userId) > 0;

            for (const auto& groupId : user.groups) {
                if (policy.groups.count(groupId)) {
                    principalMatch = true;
                }
            }

            if (
                !principalMatch ||
                !policy.permission.matches(
                    request.resource,
                    request.action
                )
            ) {
                continue;
            }

            matchedPolicies.push_back(policyId);

            if (policy.effect == Effect::DENY) {
                explicitDenied = true;
            } else {
                policyAllowed = true;
            }
        }

        // Explicit deny always overrides role and policy grants.
        if (explicitDenied) {
            return {
                Decision::DENY,
                "Explicit deny policy.",
                matchedRoles,
                matchedPolicies
            };
        }

        if (roleAllowed || policyAllowed) {
            return {
                Decision::ALLOW,
                "Matching permission found.",
                matchedRoles,
                matchedPolicies
            };
        }

        return {
            Decision::DENY,
            "No matching permission.",
            matchedRoles,
            matchedPolicies
        };
    }

    void requireAccess(const AccessRequest& request) const {
        auto result = evaluate(request);

        if (result.decision == Decision::DENY) {
            throw IAMException(result.reason);
        }
    }

    void printEffectiveAccess(const string& userId) const {
        vector<AccessRequest> requests = {
            {userId, "applications/project-a", "read"},
            {userId, "applications/project-a", "delete"},
            {userId, "production/secrets", "read"},
            {userId, "security/logs", "read"},
            {userId, "deployment/reports", "read"}
        };

        for (const auto& request : requests) {
            auto result = evaluate(request);

            cout << request.userId << " | "
                 << request.resource << " | "
                 << request.action << " | "
                 << toString(result.decision)
                 << " | " << result.reason << '\n';
        }
    }
};

int main() {
    try {
        IAMEngine iam;

        iam.addUser({
            "USER01",
            "alice@enterprise.example",
            true,
            {}
        });

        iam.addUser({
            "USER02",
            "bob@enterprise.example",
            true,
            {}
        });

        iam.addGroup({
            "GROUP01",
            "Engineering",
            {}
        });

        iam.addGroup({
            "GROUP02",
            "Security",
            {}
        });

        iam.addRole({
            "ROLE01",
            "Developer",
            {
                {"applications/project-a", "read"},
                {"applications/project-a", "write"}
            }
        });

        iam.addRole({
            "ROLE02",
            "SecurityAuditor",
            {
                {"security/logs", "read"},
                {"security/reports", "read"}
            }
        });

        iam.addRole({
            "ROLE03",
            "TemporaryAdministrator",
            {
                {"*", "*"}
            }
        });

        iam.addMembership("USER01", "GROUP01");
        iam.addMembership("USER02", "GROUP02");

        iam.assignRoleToGroup("GROUP01", "ROLE01");
        iam.assignRoleToGroup("GROUP02", "ROLE02");

        auto expiry = chrono::system_clock::now() +
                      chrono::minutes(30);

        iam.assignRole("USER02", "ROLE03", expiry);

        iam.addPolicy({
            "POLICY01",
            "Protect production secrets",
            Effect::DENY,
            {"production/secrets", "*"},
            {},
            {"GROUP01"},
            true
        });

        iam.addPolicy({
            "POLICY02",
            "Deployment report access",
            Effect::ALLOW,
            {"deployment/reports", "read"},
            {"USER01"},
            {},
            true
        });

        cout << "IDENTITY AND ACCESS MANAGEMENT\n";
        cout << "===============================================\n";

        iam.printEffectiveAccess("USER01");

        cout << "\nTEMPORARY ADMINISTRATOR ACCESS\n";

        auto temporary = iam.evaluate({
            "USER02",
            "production/secrets",
            "read"
        });

        cout << toString(temporary.decision)
             << " | " << temporary.reason << '\n';

        cout << "\nACCESS ENFORCEMENT\n";

        try {
            iam.requireAccess({
                "USER01",
                "production/secrets",
                "read"
            });
        } catch (const IAMException& error) {
            cout << "Request rejected: "
                 << error.what() << '\n';
        }

        cout << "\nREVOCATION\n";

        iam.revokeRole("USER02", "ROLE03");

        auto afterRevocation = iam.evaluate({
            "USER02",
            "production/secrets",
            "read"
        });

        cout << "After revocation: "
             << toString(afterRevocation.decision) << '\n';

        cout << "\nVALIDATION\n";

        try {
            iam.addMembership("UNKNOWN", "GROUP01");
        } catch (const IAMException& error) {
            cout << "Expected validation failure: "
                 << error.what() << '\n';
        }

        cout << "\nIAM execution completed.\n";

    } catch (const exception& error) {
        cerr << "Fatal IAM error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
