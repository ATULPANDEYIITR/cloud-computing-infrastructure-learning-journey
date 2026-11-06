import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Enterprise Identity and Access Management.
 *
 * Implements identity lifecycle, group-based role inheritance,
 * explicit policy evaluation, temporary assignments, access auditing,
 * and authorization enforcement.
 */
public class IAMEnterprise {

    enum Effect {
        ALLOW,
        DENY
    }

    enum Decision {
        ALLOW,
        DENY
    }

    enum UserStatus {
        ACTIVE,
        SUSPENDED,
        DISABLED
    }

    static class IAMException extends RuntimeException {
        IAMException(String message) {
            super(message);
        }
    }

    static class ValidationException extends IAMException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class NotFoundException extends IAMException {
        NotFoundException(String message) {
            super(message);
        }
    }

    static class AccessDeniedException extends IAMException {
        AccessDeniedException(String message) {
            super(message);
        }
    }

    record Permission(String resource, String action) {

        Permission {
            Objects.requireNonNull(resource);
            Objects.requireNonNull(action);

            if (resource.isBlank() || action.isBlank()) {
                throw new ValidationException(
                    "Permission fields cannot be empty."
                );
            }

            if (resource.contains("..")) {
                throw new ValidationException(
                    "Invalid resource path."
                );
            }
        }

        boolean matches(String requestedResource, String requestedAction) {
            boolean resourceMatches =
                resource.equals("*") ||
                resource.equals(requestedResource) ||
                (
                    resource.endsWith("/*") &&
                    requestedResource.startsWith(
                        resource.substring(0, resource.length() - 1)
                    )
                );

            boolean actionMatches =
                action.equals("*") ||
                action.equals(requestedAction);

            return resourceMatches && actionMatches;
        }
    }

    static final class User {
        private final String id;
        private final String email;
        private UserStatus status;
        private final Set<String> groupIds = new HashSet<>();

        User(String id, String email) {
            if (id == null || id.isBlank()) {
                throw new ValidationException("User ID is required.");
            }

            if (
                email == null ||
                !email.matches("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")
            ) {
                throw new ValidationException("Invalid email.");
            }

            this.id = id;
            this.email = email;
            this.status = UserStatus.ACTIVE;
        }

        String id() {
            return id;
        }

        boolean isActive() {
            return status == UserStatus.ACTIVE;
        }

        void changeStatus(UserStatus status) {
            this.status = Objects.requireNonNull(status);
        }
    }

    static final class Group {
        private final String id;
        private final String name;
        private final Set<String> roleIds = new HashSet<>();

        Group(String id, String name) {
            if (id == null || id.isBlank() ||
                name == null || name.isBlank()) {
                throw new ValidationException("Invalid group.");
            }

            this.id = id;
            this.name = name;
        }
    }

    static final class Role {
        private final String id;
        private final String name;
        private final Set<Permission> permissions;

        Role(
            String id,
            String name,
            Set<Permission> permissions
        ) {
            if (id == null || id.isBlank() ||
                name == null || name.isBlank() ||
                permissions == null || permissions.isEmpty()) {
                throw new ValidationException("Invalid role.");
            }

            this.id = id;
            this.name = name;
            this.permissions = Set.copyOf(permissions);
        }
    }

    record RoleAssignment(
        String id,
        String userId,
        String roleId,
        Instant expiresAt
    ) {
        RoleAssignment {
            Objects.requireNonNull(id);
            Objects.requireNonNull(userId);
            Objects.requireNonNull(roleId);

            if (
                expiresAt != null &&
                !expiresAt.isAfter(Instant.now())
            ) {
                throw new ValidationException(
                    "Assignment expiration must be in the future."
                );
            }
        }

        boolean activeAt(Instant now) {
            return expiresAt == null || now.isBefore(expiresAt);
        }
    }

    static final class Policy {
        private final String id;
        private final String name;
        private final Effect effect;
        private final Permission permission;
        private final Set<String> userIds;
        private final Set<String> groupIds;
        private final Map<String, String> conditions;
        private final Instant expiresAt;
        private boolean active = true;

        Policy(
            String id,
            String name,
            Effect effect,
            Permission permission,
            Set<String> userIds,
            Set<String> groupIds,
            Map<String, String> conditions,
            Instant expiresAt
        ) {
            if (
                id == null || id.isBlank() ||
                name == null || name.isBlank()
            ) {
                throw new ValidationException("Invalid policy identity.");
            }

            if (userIds.isEmpty() && groupIds.isEmpty()) {
                throw new ValidationException(
                    "Policy requires at least one principal."
                );
            }

            this.id = id;
            this.name = name;
            this.effect = Objects.requireNonNull(effect);
            this.permission = Objects.requireNonNull(permission);
            this.userIds = Set.copyOf(userIds);
            this.groupIds = Set.copyOf(groupIds);
            this.conditions = Map.copyOf(conditions);
            this.expiresAt = expiresAt;
        }

        boolean activeAt(Instant now) {
            return active &&
                (expiresAt == null || now.isBefore(expiresAt));
        }

        void deactivate() {
            active = false;
        }
    }

    record AccessRequest(
        String userId,
        String resource,
        String action,
        Map<String, String> context
    ) {
        AccessRequest {
            Objects.requireNonNull(userId);
            Objects.requireNonNull(resource);
            Objects.requireNonNull(action);
            context = Map.copyOf(context);

            if (resource.isBlank() || action.isBlank()) {
                throw new ValidationException(
                    "Invalid access request."
                );
            }
        }
    }

    record AccessDecision(
        String requestId,
        Decision decision,
        String reason,
        Set<String> matchedRoles,
        Set<String> matchedPolicies
    ) {
        AccessDecision {
            matchedRoles = Set.copyOf(matchedRoles);
            matchedPolicies = Set.copyOf(matchedPolicies);
        }
    }

    interface AuthorizationService {
        AccessDecision evaluate(AccessRequest request);

        void requireAccess(AccessRequest request);
    }

    static final class AuditService {
        private final List<AccessDecision> events = new ArrayList<>();

        void record(AccessDecision decision) {
            events.add(decision);
        }

        List<AccessDecision> events() {
            return List.copyOf(events);
        }

        long count(Decision decision) {
            return events.stream()
                .filter(event -> event.decision() == decision)
                .count();
        }

        void printReport() {
            System.out.println("Total decisions: " + events.size());
            System.out.println("Allowed: " + count(Decision.ALLOW));
            System.out.println("Denied: " + count(Decision.DENY));
        }
    }

    static final class IAMService implements AuthorizationService {
        private final Map<String, User> users = new HashMap<>();
        private final Map<String, Group> groups = new HashMap<>();
        private final Map<String, Role> roles = new HashMap<>();
        private final Map<String, Policy> policies = new HashMap<>();
        private final Map<String, RoleAssignment> assignments =
            new HashMap<>();

        private final AuditService auditService = new AuditService();

        void registerUser(User user) {
            if (users.putIfAbsent(user.id, user) != null) {
                throw new ValidationException("Duplicate user.");
            }
        }

        void registerGroup(Group group) {
            if (groups.putIfAbsent(group.id, group) != null) {
                throw new ValidationException("Duplicate group.");
            }
        }

        void registerRole(Role role) {
            if (roles.putIfAbsent(role.id, role) != null) {
                throw new ValidationException("Duplicate role.");
            }
        }

        void registerPolicy(Policy policy) {
            if (policies.containsKey(policy.id)) {
                throw new ValidationException("Duplicate policy.");
            }

            policy.userIds.forEach(this::getUser);
            policy.groupIds.forEach(this::getGroup);

            policies.put(policy.id, policy);
        }

        User getUser(String id) {
            User user = users.get(id);

            if (user == null) {
                throw new NotFoundException("Unknown user: " + id);
            }

            return user;
        }

        Group getGroup(String id) {
            Group group = groups.get(id);

            if (group == null) {
                throw new NotFoundException("Unknown group: " + id);
            }

            return group;
        }

        Role getRole(String id) {
            Role role = roles.get(id);

            if (role == null) {
                throw new NotFoundException("Unknown role: " + id);
            }

            return role;
        }

        void addUserToGroup(String userId, String groupId) {
            User user = getUser(userId);
            getGroup(groupId);

            if (!user.groupIds.add(groupId)) {
                throw new ValidationException(
                    "User is already a group member."
                );
            }
        }

        void assignRoleToGroup(String groupId, String roleId) {
            Group group = getGroup(groupId);
            getRole(roleId);

            if (!group.roleIds.add(roleId)) {
                throw new ValidationException(
                    "Role already assigned to group."
                );
            }
        }

        String assignTemporaryRole(
            String userId,
            String roleId,
            Instant expiresAt
        ) {
            getUser(userId);
            getRole(roleId);

            String id = UUID.randomUUID().toString();

            RoleAssignment assignment = new RoleAssignment(
                id,
                userId,
                roleId,
                expiresAt
            );

            assignments.put(id, assignment);
            return id;
        }

        void revokeAssignment(String assignmentId) {
            if (assignments.remove(assignmentId) == null) {
                throw new NotFoundException(
                    "Role assignment not found."
                );
            }
        }

        void suspendUser(String userId) {
            getUser(userId).changeStatus(UserStatus.SUSPENDED);
        }

        void disableUser(String userId) {
            getUser(userId).changeStatus(UserStatus.DISABLED);
        }

        Set<String> effectiveRoles(String userId, Instant now) {
            User user = getUser(userId);

            Set<String> effective = new HashSet<>();

            if (!user.isActive()) {
                return effective;
            }

            for (String groupId : user.groupIds) {
                effective.addAll(getGroup(groupId).roleIds);
            }

            assignments.values().stream()
                .filter(a -> a.userId().equals(userId))
                .filter(a -> a.activeAt(now))
                .map(RoleAssignment::roleId)
                .forEach(effective::add);

            return effective;
        }

        private boolean policyPrincipalMatches(
            Policy policy,
            User user
        ) {
            if (policy.userIds.contains(user.id)) {
                return true;
            }

            return policy.groupIds.stream()
                .anyMatch(user.groupIds::contains);
        }

        private boolean conditionsMatch(
            Policy policy,
            AccessRequest request
        ) {
            return policy.conditions.entrySet().stream()
                .allMatch(entry ->
                    Objects.equals(
                        request.context().get(entry.getKey()),
                        entry.getValue()
                    )
                );
        }

        @Override
        public AccessDecision evaluate(AccessRequest request) {
            User user = getUser(request.userId());
            Instant now = Instant.now();

            Set<String> matchedRoles = new HashSet<>();
            Set<String> matchedPolicies = new HashSet<>();

            if (!user.isActive()) {
                return record(new AccessDecision(
                    UUID.randomUUID().toString(),
                    Decision.DENY,
                    "Identity is not active.",
                    matchedRoles,
                    matchedPolicies
                ));
            }

            boolean roleGrant = false;
            boolean policyGrant = false;
            boolean explicitDeny = false;

            for (String roleId : effectiveRoles(user.id, now)) {
                Role role = getRole(roleId);

                boolean match = role.permissions.stream()
                    .anyMatch(p -> p.matches(
                        request.resource(),
                        request.action()
                    ));

                if (match) {
                    roleGrant = true;
                    matchedRoles.add(role.name);
                }
            }

            for (Policy policy : policies.values()) {
                if (
                    !policy.activeAt(now) ||
                    !policyPrincipalMatches(policy, user) ||
                    !conditionsMatch(policy, request) ||
                    !policy.permission.matches(
                        request.resource(),
                        request.action()
                    )
                ) {
                    continue;
                }

                matchedPolicies.add(policy.id);

                if (policy.effect == Effect.DENY) {
                    explicitDeny = true;
                } else {
                    policyGrant = true;
                }
            }

            AccessDecision result;

            if (explicitDeny) {
                result = new AccessDecision(
                    UUID.randomUUID().toString(),
                    Decision.DENY,
                    "Explicit deny overrides grants.",
                    matchedRoles,
                    matchedPolicies
                );
            } else if (roleGrant || policyGrant) {
                result = new AccessDecision(
                    UUID.randomUUID().toString(),
                    Decision.ALLOW,
                    "Matching authorization grant.",
                    matchedRoles,
                    matchedPolicies
                );
            } else {
                result = new AccessDecision(
                    UUID.randomUUID().toString(),
                    Decision.DENY,
                    "No matching permission.",
                    matchedRoles,
                    matchedPolicies
                );
            }

            return record(result);
        }

        private AccessDecision record(AccessDecision decision) {
            auditService.record(decision);
            return decision;
        }

        @Override
        public void requireAccess(AccessRequest request) {
            AccessDecision result = evaluate(request);

            if (result.decision() == Decision.DENY) {
                throw new AccessDeniedException(result.reason());
            }
        }

        AuditService audit() {
            return auditService;
        }
    }

    private static Set<Permission> permissions(
        Permission... permissions
    ) {
        return Set.of(permissions);
    }

    public static void main(String[] args) {
        IAMService iam = new IAMService();

        User alice = new User(
            "USER01",
            "alice@enterprise.example"
        );

        User bob = new User(
            "USER02",
            "bob@enterprise.example"
        );

        iam.registerUser(alice);
        iam.registerUser(bob);

        iam.registerGroup(new Group("GROUP01", "Engineering"));
        iam.registerGroup(new Group("GROUP02", "Security"));

        iam.registerRole(new Role(
            "ROLE01",
            "Developer",
            permissions(
                new Permission("applications/project-a", "read"),
                new Permission("applications/project-a", "write")
            )
        ));

        iam.registerRole(new Role(
            "ROLE02",
            "SecurityAuditor",
            permissions(
                new Permission("security/logs", "read"),
                new Permission("security/reports", "read")
            )
        ));

        iam.registerRole(new Role(
            "ROLE03",
            "IncidentAdministrator",
            permissions(
                new Permission("*", "*")
            )
        ));

        iam.addUserToGroup("USER01", "GROUP01");
        iam.addUserToGroup("USER02", "GROUP02");

        iam.assignRoleToGroup("GROUP01", "ROLE01");
        iam.assignRoleToGroup("GROUP02", "ROLE02");

        String temporaryAssignment = iam.assignTemporaryRole(
            "USER02",
            "ROLE03",
            Instant.now().plus(30, ChronoUnit.MINUTES)
        );

        iam.registerPolicy(new Policy(
            "POLICY01",
            "Protect production secrets",
            Effect.DENY,
            new Permission("production/secrets", "*"),
            Set.of(),
            Set.of("GROUP01"),
            Map.of(),
            null
        ));

        iam.registerPolicy(new Policy(
            "POLICY02",
            "Deployment report access",
            Effect.ALLOW,
            new Permission("deployment/reports", "read"),
            Set.of("USER01"),
            Set.of(),
            Map.of("department", "engineering"),
            null
        ));

        List<AccessRequest> requests = List.of(
            new AccessRequest(
                "USER01",
                "applications/project-a",
                "read",
                Map.of()
            ),
            new AccessRequest(
                "USER01",
                "production/secrets",
                "read",
                Map.of()
            ),
            new AccessRequest(
                "USER01",
                "deployment/reports",
                "read",
                Map.of("department", "engineering")
            ),
            new AccessRequest(
                "USER01",
                "deployment/reports",
                "read",
                Map.of("department", "finance")
            ),
            new AccessRequest(
                "USER02",
                "security/logs",
                "read",
                Map.of()
            )
        );

        System.out.println("ENTERPRISE IAM AUTHORIZATION");
        System.out.println("========================================");

        for (AccessRequest request : requests) {
            AccessDecision result = iam.evaluate(request);

            System.out.printf(
                "%s | %s | %s | %s | %s%n",
                request.userId(),
                request.resource(),
                request.action(),
                result.decision(),
                result.reason()
            );
        }

        System.out.println("\nENFORCED ACCESS");

        try {
            iam.requireAccess(new AccessRequest(
                "USER01",
                "production/secrets",
                "read",
                Map.of()
            ));
        } catch (AccessDeniedException exception) {
            System.out.println(
                "Rejected: " + exception.getMessage()
            );
        }

        System.out.println("\nROLE REVOCATION");

        iam.revokeAssignment(temporaryAssignment);

        AccessDecision afterRevocation = iam.evaluate(
            new AccessRequest(
                "USER02",
                "production/secrets",
                "read",
                Map.of()
            )
        );

        System.out.println(
            "After revocation: " + afterRevocation.decision()
        );

        System.out.println("\nIDENTITY SUSPENSION");

        iam.suspendUser("USER01");

        AccessDecision suspended = iam.evaluate(
            new AccessRequest(
                "USER01",
                "applications/project-a",
                "read",
                Map.of()
            )
        );

        System.out.println(
            "Suspended identity: " + suspended.decision()
        );

        System.out.println("\nAUDIT REPORT");
        iam.audit().printReport();

        System.out.println("\nVALIDATION");

        try {
            iam.addUserToGroup("UNKNOWN", "GROUP01");
        } catch (IAMException exception) {
            System.out.println(
                "Expected failure: " + exception.getMessage()
            );
        }

        System.out.println("\nEnterprise IAM execution completed.");
    }
}
