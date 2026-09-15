#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Linux Users and Permissions
 * ===========================
 *
 * C++17 industry-style case study:
 *
 * A multi-user engineering document service uses Linux-style ownership,
 * groups, permissions, ACL entries, privilege checks, and auditing.
 *
 * The program is an executable simulation rather than a program that modifies
 * the host operating system. This keeps the case study safe and portable
 * while demonstrating the architecture and algorithms involved.
 *
 * Compile:
 *
 *   g++ -std=c++17 -Wall -Wextra -pedantic linux_users_permissions.cpp -o permissions
 *
 * Run:
 *
 *   ./permissions
 *
 * Real Linux systems additionally involve ACLs, capabilities, namespaces,
 * SELinux/AppArmor, mount options, and other kernel security mechanisms.
 */

enum class Permission : std::uint8_t {
    Read = 4,
    Write = 2,
    Execute = 1
};

struct PermissionSet {
    bool read{false};
    bool write{false};
    bool execute{false};

    static PermissionSet fromDigit(int digit) {
        if (digit < 0 || digit > 7) {
            throw std::invalid_argument("Permission digit must be 0-7.");
        }

        return {
            (digit & 4) != 0,
            (digit & 2) != 0,
            (digit & 1) != 0
        };
    }

    int numeric() const {
        return (read ? 4 : 0)
             + (write ? 2 : 0)
             + (execute ? 1 : 0);
    }

    std::string symbolic() const {
        std::string result;
        result += read ? 'r' : '-';
        result += write ? 'w' : '-';
        result += execute ? 'x' : '-';
        return result;
    }
};

bool allows(const PermissionSet& permissions, Permission requested) {
    switch (requested) {
        case Permission::Read:
            return permissions.read;
        case Permission::Write:
            return permissions.write;
        case Permission::Execute:
            return permissions.execute;
    }

    return false;
}

struct User {
    std::string username;
    int uid{};
    int primaryGid{};
    std::set<int> supplementaryGids;

    bool belongsToGroup(int gid) const {
        return primaryGid == gid || supplementaryGids.count(gid) > 0;
    }
};

struct Group {
    std::string name;
    int gid{};
    std::set<int> memberUids;

    void addMember(const User& user) {
        memberUids.insert(user.uid);
    }
};

enum class ResourceType {
    File,
    Directory
};

struct AclEntry {
    enum class Type {
        User,
        Group
    };

    Type type;
    int id{};
    PermissionSet permissions;
};

struct FileResource {
    std::string path;
    int ownerUid{};
    int groupGid{};
    int mode{}; // Lower nine bits represent owner/group/other rwx.
    ResourceType type{ResourceType::File};
    std::vector<AclEntry> aclEntries;

    PermissionSet ownerPermissions() const {
        return PermissionSet::fromDigit((mode >> 6) & 7);
    }

    PermissionSet groupPermissions() const {
        return PermissionSet::fromDigit((mode >> 3) & 7);
    }

    PermissionSet otherPermissions() const {
        return PermissionSet::fromDigit(mode & 7);
    }
};

std::string octalMode(int mode) {
    std::ostringstream output;
    output << std::oct << std::setw(3) << std::setfill('0') << (mode & 0777);
    return output.str();
}

std::string symbolicMode(const FileResource& resource) {
    std::string result;

    result += resource.type == ResourceType::Directory ? 'd' : '-';
    result += resource.ownerPermissions().symbolic();
    result += resource.groupPermissions().symbolic();
    result += resource.otherPermissions().symbolic();

    /*
     * Special bits are represented separately so that the example remains
     * explicit about their semantics.
     */
    if ((resource.mode & 04000) != 0) {
        result += " [setuid]";
    }

    if ((resource.mode & 02000) != 0) {
        result += " [setgid]";
    }

    if ((resource.mode & 01000) != 0) {
        result += " [sticky]";
    }

    return result;
}

enum class PermissionClass {
    Owner,
    Group,
    Other,
    NamedAcl
};

struct AccessDecision {
    bool allowed{false};
    PermissionClass source{PermissionClass::Other};
    std::string explanation;
};

std::string permissionClassName(PermissionClass value) {
    switch (value) {
        case PermissionClass::Owner:
            return "owner";
        case PermissionClass::Group:
            return "group";
        case PermissionClass::Other:
            return "other";
        case PermissionClass::NamedAcl:
            return "named ACL";
    }

    return "unknown";
}

/*
 * Simplified POSIX permission selection:
 *
 * 1. Root is handled as a privileged case.
 * 2. Owner permissions are selected when UID matches.
 * 3. Otherwise a matching ACL entry may grant access.
 * 4. Otherwise group permissions are selected if the user belongs to the
 *    owning group.
 * 5. Otherwise other permissions are selected.
 *
 * Real POSIX ACL evaluation contains additional rules, including the ACL
 * mask. Linux also applies other security mechanisms outside this model.
 */
AccessDecision evaluateAccess(
    const User& user,
    const FileResource& resource,
    Permission requested
) {
    if (user.uid == 0) {
        return {
            true,
            PermissionClass::Owner,
            "root privilege model"
        };
    }

    if (user.uid == resource.ownerUid) {
        const bool allowed = allows(
            resource.ownerPermissions(),
            requested
        );

        return {
            allowed,
            PermissionClass::Owner,
            "owner permission class selected"
        };
    }

    for (const auto& entry : resource.aclEntries) {
        bool matches = false;

        if (entry.type == AclEntry::Type::User) {
            matches = entry.id == user.uid;
        } else if (entry.type == AclEntry::Type::Group) {
            matches = user.belongsToGroup(entry.id);
        }

        if (matches) {
            const bool allowed = allows(entry.permissions, requested);

            return {
                allowed,
                PermissionClass::NamedAcl,
                "matching named ACL entry selected"
            };
        }
    }

    if (user.belongsToGroup(resource.groupGid)) {
        const bool allowed = allows(
            resource.groupPermissions(),
            requested
        );

        return {
            allowed,
            PermissionClass::Group,
            "owning group permission class selected"
        };
    }

    const bool allowed = allows(
        resource.otherPermissions(),
        requested
    );

    return {
        allowed,
        PermissionClass::Other,
        "other permission class selected"
    };
}

class AuditLogger {
private:
    struct Event {
        std::string timestamp;
        std::string actor;
        std::string action;
        std::string resource;
        bool allowed;
    };

    std::vector<Event> events;

public:
    void record(
        const User& actor,
        const std::string& action,
        const std::string& resource,
        bool allowed
    ) {
        const auto now = std::chrono::system_clock::now();
        const auto timeValue =
            std::chrono::system_clock::to_time_t(now);

        std::ostringstream timestamp;
        timestamp << std::put_time(
            std::localtime(&timeValue),
            "%Y-%m-%d %H:%M:%S"
        );

        events.push_back({
            timestamp.str(),
            actor.username,
            action,
            resource,
            allowed
        });
    }

    void print() const {
        std::cout << "\nAUDIT EVENTS\n";
        std::cout << "------------\n";

        for (const auto& event : events) {
            std::cout
                << event.timestamp << " | "
                << event.actor << " | "
                << event.action << " | "
                << event.resource << " | "
                << (event.allowed ? "ALLOWED" : "DENIED")
                << '\n';
        }
    }
};

class DocumentRepository {
private:
    std::map<std::string, FileResource> resources;

public:
    void add(FileResource resource) {
        if (resource.path.empty()) {
            throw std::invalid_argument("Resource path cannot be empty.");
        }

        if (resource.mode < 0 || resource.mode > 07777) {
            throw std::invalid_argument("Invalid file mode.");
        }

        if (resources.count(resource.path) != 0) {
            throw std::runtime_error("Resource already exists.");
        }

        resources.emplace(resource.path, std::move(resource));
    }

    const FileResource* find(const std::string& path) const {
        const auto iterator = resources.find(path);

        if (iterator == resources.end()) {
            return nullptr;
        }

        return &iterator->second;
    }
};

class DocumentService {
private:
    const DocumentRepository& repository;
    AuditLogger& audit;

public:
    DocumentService(
        const DocumentRepository& repository,
        AuditLogger& audit
    )
        : repository(repository), audit(audit) {}

    bool authorize(
        const User& user,
        const std::string& path,
        Permission requested
    ) {
        const FileResource* resource = repository.find(path);

        if (resource == nullptr) {
            audit.record(user, "ACCESS_UNKNOWN_RESOURCE", path, false);
            return false;
        }

        const AccessDecision decision =
            evaluateAccess(user, *resource, requested);

        audit.record(
            user,
            "ACCESS_" + std::string(
                requested == Permission::Read ? "READ" :
                requested == Permission::Write ? "WRITE" :
                "EXECUTE"
            ),
            path,
            decision.allowed
        );

        std::cout
            << user.username
            << " requesting "
            << (requested == Permission::Read ? "read" :
                requested == Permission::Write ? "write" :
                "execute")
            << " on "
            << path
            << " -> "
            << (decision.allowed ? "ALLOWED" : "DENIED")
            << " ["
            << permissionClassName(decision.source)
            << "] "
            << decision.explanation
            << '\n';

        return decision.allowed;
    }
};

class PrivilegedAdministrationService {
private:
    AuditLogger& audit;

public:
    explicit PrivilegedAdministrationService(AuditLogger& audit)
        : audit(audit) {}

    bool changeOwnership(
        const User& actor,
        FileResource& resource,
        int newOwnerUid
    ) {
        /*
         * A real chown operation is governed by kernel rules and capabilities.
         * This case study uses UID 0 as the simplified administrative identity.
         */
        if (actor.uid != 0) {
            audit.record(
                actor,
                "CHANGE_OWNERSHIP",
                resource.path,
                false
            );

            return false;
        }

        resource.ownerUid = newOwnerUid;

        audit.record(
            actor,
            "CHANGE_OWNERSHIP",
            resource.path,
            true
        );

        return true;
    }
};

int applyUmask(int requestedMode, int umask) {
    if (requestedMode < 0 || requestedMode > 0777 ||
        umask < 0 || umask > 0777) {
        throw std::invalid_argument("Invalid mode or umask.");
    }

    return requestedMode & (~umask);
}

void demonstrateUmask() {
    std::cout << "\nUMASK CALCULATION\n";
    std::cout << "-----------------\n";

    for (int mask : {0022, 0027, 0077}) {
        const int fileMode = applyUmask(0666, mask);
        const int directoryMode = applyUmask(0777, mask);

        std::cout
            << "umask "
            << octalMode(mask)
            << " -> file "
            << octalMode(fileMode)
            << ", directory "
            << octalMode(directoryMode)
            << '\n';
    }
}

void demonstrateDirectorySemantics() {
    std::cout << "\nDIRECTORY PERMISSION SEMANTICS\n";
    std::cout << "-----------------------------\n";

    std::cout
        << "r = list directory entries\n"
        << "w = create/remove/rename entries, subject to other rules\n"
        << "x = search/traverse the directory\n";
}

void runUnitTests() {
    std::cout << "\nUNIT TESTS\n";
    std::cout << "----------\n";

    User owner{
        "alice",
        1000,
        100,
        {}
    };

    User groupMember{
        "bob",
        1001,
        200,
        {100}
    };

    User outsider{
        "charlie",
        1002,
        300,
        {}
    };

    FileResource resource{
        "/srv/engineering/design.txt",
        1000,
        100,
        0640,
        ResourceType::File,
        {}
    };

    struct Test {
        const User& user;
        Permission permission;
        bool expected;
    };

    const std::vector<Test> tests{
        {owner, Permission::Read, true},
        {owner, Permission::Write, true},
        {owner, Permission::Execute, false},
        {groupMember, Permission::Read, true},
        {groupMember, Permission::Write, false},
        {outsider, Permission::Read, false},
        {outsider, Permission::Write, false}
    };

    int passed = 0;

    for (const auto& test : tests) {
        const auto decision =
            evaluateAccess(test.user, resource, test.permission);

        const bool successful =
            decision.allowed == test.expected;

        if (successful) {
            ++passed;
        }

        std::cout
            << (successful ? "PASS" : "FAIL")
            << " "
            << test.user.username
            << " expected="
            << (test.expected ? "allow" : "deny")
            << " actual="
            << (decision.allowed ? "allow" : "deny")
            << '\n';
    }

    std::cout
        << passed
        << "/"
        << tests.size()
        << " tests passed\n";
}

void demonstrateSpecialBits() {
    std::cout << "\nSPECIAL PERMISSIONS\n";
    std::cout << "-------------------\n";

    FileResource setuidProgram{
        "/usr/local/bin/report-helper",
        0,
        0,
        04755,
        ResourceType::File,
        {}
    };

    FileResource collaborativeDirectory{
        "/srv/team",
        1000,
        100,
        02770,
        ResourceType::Directory,
        {}
    };

    FileResource sharedDirectory{
        "/srv/drop",
        1000,
        100,
        01777,
        ResourceType::Directory,
        {}
    };

    std::cout << setuidProgram.path
              << " -> "
              << symbolicMode(setuidProgram)
              << '\n';

    std::cout << collaborativeDirectory.path
              << " -> "
              << symbolicMode(collaborativeDirectory)
              << '\n';

    std::cout << sharedDirectory.path
              << " -> "
              << symbolicMode(sharedDirectory)
              << '\n';

    std::cout
        << "\nsetuid: executable can use file owner's effective identity.\n"
        << "setgid: directory can establish inherited group ownership.\n"
        << "sticky: shared directory deletion/rename is restricted.\n";
}

void demonstrateAcl() {
    std::cout << "\nACL CASE\n";
    std::cout << "--------\n";

    User owner{
        "owner",
        1000,
        100,
        {}
    };

    User auditor{
        "auditor",
        2000,
        200,
        {}
    };

    FileResource financeFile{
        "/srv/finance/audit.csv",
        owner.uid,
        100,
        0600,
        ResourceType::File,
        {
            {
                AclEntry::Type::User,
                auditor.uid,
                {true, false, false}
            }
        }
    };

    auto readDecision =
        evaluateAccess(auditor, financeFile, Permission::Read);

    auto writeDecision =
        evaluateAccess(auditor, financeFile, Permission::Write);

    std::cout
        << "Auditor read -> "
        << (readDecision.allowed ? "ALLOWED" : "DENIED")
        << " via "
        << permissionClassName(readDecision.source)
        << '\n';

    std::cout
        << "Auditor write -> "
        << (writeDecision.allowed ? "ALLOWED" : "DENIED")
        << " via "
        << permissionClassName(writeDecision.source)
        << '\n';

    /*
     * The traditional mode is 600, yet a named ACL can provide a more
     * specific grant. Real POSIX ACL evaluation also includes a mask entry.
     */
}

void demonstrateSecurityTradeoffs() {
    std::cout << R"(
SECURITY TRADE-OFFS
-------------------

644:
  Owner can read/write.
  Everyone else can read.
  Appropriate for some public-readable data.

640:
  Owner can read/write.
  Owning group can read.
  Others have no access.
  Useful for controlled team data.

600:
  Only owner can read/write.
  Appropriate for many private configuration files.

750:
  Owner can read/write/execute.
  Group can read/execute.
  Others have no access.
  Common for private application directories.

777:
  Everyone can read/write/execute.
  Usually an unnecessarily broad permission.

Production security requires more than choosing a mode:
  - correct ownership
  - secure parent directories
  - appropriate group membership
  - ACL review
  - sudo policy
  - capabilities
  - LSM policy
  - secure application authorization
  - auditing
  - protection against symlink and race-condition attacks
)" << '\n';
}

int main() {
    try {
        std::cout << "LINUX USERS AND PERMISSIONS\n";
        std::cout << "===========================\n";

        User alice{
            "alice",
            1000,
            100,
            {}
        };

        User bob{
            "bob",
            1001,
            200,
            {100}
        };

        User charlie{
            "charlie",
            1002,
            300,
            {}
        };

        User root{
            "root",
            0,
            0,
            {}
        };

        Group developers{
            "developers",
            100
        };

        developers.addMember(alice);
        developers.addMember(bob);

        FileResource source{
            "/srv/engineering/main.cpp",
            alice.uid,
            developers.gid,
            0750,
            ResourceType::File,
            {}
        };

        std::cout
            << "\nRESOURCE\n"
            << "--------\n"
            << "Path: "
            << source.path
            << '\n'
            << "Owner UID: "
            << source.ownerUid
            << '\n'
            << "Group GID: "
            << source.groupGid
            << '\n'
            << "Mode: "
            << octalMode(source.mode)
            << '\n'
            << "Permissions: "
            << symbolicMode(source)
            << '\n';

        DocumentRepository repository;
        repository.add(source);

        AuditLogger audit;
        DocumentService service(repository, audit);

        std::cout << "\nACCESS REQUESTS\n";
        std::cout << "---------------\n";

        service.authorize(alice, source.path, Permission::Read);
        service.authorize(alice, source.path, Permission::Write);
        service.authorize(alice, source.path, Permission::Execute);

        service.authorize(bob, source.path, Permission::Read);
        service.authorize(bob, source.path, Permission::Write);
        service.authorize(bob, source.path, Permission::Execute);

        service.authorize(charlie, source.path, Permission::Read);
        service.authorize(charlie, source.path, Permission::Execute);

        service.authorize(root, source.path, Permission::Write);

        demonstrateUmask();
        demonstrateDirectorySemantics();
        demonstrateSpecialBits();
        demonstrateAcl();

        /*
         * The repository owns its resource copy. For the administrative
         * ownership demonstration, we create a separate mutable resource.
         */
        FileResource administrativeResource{
            "/srv/engineering/architecture.pdf",
            alice.uid,
            developers.gid,
            0640,
            ResourceType::File,
            {}
        };

        PrivilegedAdministrationService administration(audit);

        std::cout << "\nOWNERSHIP CHANGE\n";
        std::cout << "----------------\n";

        const bool aliceChangedOwnership =
            administration.changeOwnership(
                alice,
                administrativeResource,
                charlie.uid
            );

        std::cout
            << "Alice changing ownership: "
            << (aliceChangedOwnership ? "ALLOWED" : "DENIED")
            << '\n';

        const bool rootChangedOwnership =
            administration.changeOwnership(
                root,
                administrativeResource,
                charlie.uid
            );

        std::cout
            << "Root changing ownership: "
            << (rootChangedOwnership ? "ALLOWED" : "DENIED")
            << '\n';

        std::cout
            << "New owner UID: "
            << administrativeResource.ownerUid
            << '\n';

        demonstrateSecurityTradeoffs();

        audit.print();

        runUnitTests();

        std::cout << R"(
ARCHITECTURAL NOTES
-------------------

The case study separates several concerns:

User:
  Identity and group membership.

FileResource:
  Ownership, mode bits, resource type, and ACL entries.

Access evaluation:
  Converts identity + resource metadata + requested operation into an
  authorization decision.

DocumentService:
  Represents an application-level service using the authorization layer.

PrivilegedAdministrationService:
  Represents operations requiring elevated authority.

AuditLogger:
  Records security-sensitive decisions.

This separation resembles real production design because identity, policy,
resource metadata, business logic, and auditing should not be mixed into one
large function.

Complexity:
  Traditional owner/group/other selection is O(1).
  The simplified ACL lookup above is O(A), where A is the number of ACL
  entries. Production implementations may use more efficient internal
  structures.

The model deliberately does not claim to replace Linux's kernel permission
implementation.
)" << '\n';

        return 0;
    } catch (const std::exception& exception) {
        std::cerr
            << "Fatal error: "
            << exception.what()
            << '\n';

        return 1;
    }
}
