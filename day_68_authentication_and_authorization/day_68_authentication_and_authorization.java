import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

/*
 * Authentication and Authorization
 * Java 17
 *
 * Enterprise-oriented identity management model.
 *
 * Implements password hashing, TOTP, HMAC-signed tokens,
 * sessions, OAuth PKCE, RBAC and ABAC.
 */

public class AuthenticationAuthorization {

    // ========================================================
    // Exceptions
    // ========================================================

    static class AuthenticationException extends RuntimeException {
        AuthenticationException(String message) {
            super(message);
        }
    }

    static class AuthorizationException extends RuntimeException {
        AuthorizationException(String message) {
            super(message);
        }
    }

    static class ValidationException extends RuntimeException {
        ValidationException(String message) {
            super(message);
        }
    }

    // ========================================================
    // Domain enums
    // ========================================================

    enum AccountStatus {
        ACTIVE, LOCKED, DISABLED
    }

    enum SessionStatus {
        ACTIVE, REVOKED, EXPIRED
    }

    enum Permission {
        PROFILE_READ("profile:read"),
        PROFILE_UPDATE("profile:update"),
        REPORTS_READ("reports:read"),
        USERS_MANAGE("users:manage"),
        SECURITY_MANAGE("security:manage");

        private final String value;

        Permission(String value) {
            this.value = value;
        }

        String value() {
            return value;
        }
    }

    // ========================================================
    // Immutable records
    // ========================================================

    record PasswordRecord(
        String algorithm,
        int iterations,
        byte[] salt,
        byte[] hash
    ) {
        PasswordRecord {
            salt = salt.clone();
            hash = hash.clone();
        }

        @Override
        public byte[] salt() {
            return salt.clone();
        }

        @Override
        public byte[] hash() {
            return hash.clone();
        }
    }

    record Resource(
        String id,
        String department,
        String ownerId,
        int classification
    ) {}

    record Environment(
        boolean mfaVerified,
        int riskScore,
        String networkZone
    ) {}

    record TokenClaims(
        String subject,
        Set<String> roles,
        String issuer,
        String audience,
        long issuedAt,
        long expiresAt,
        String tokenId
    ) {
        TokenClaims {
            roles = Set.copyOf(roles);
        }
    }

    // ========================================================
    // User aggregate
    // ========================================================

    static final class User {
        private final String id;
        private final String username;
        private final PasswordRecord password;
        private final Set<String> roles;
        private final String department;
        private final int clearance;

        private final AtomicInteger failedAttempts =
            new AtomicInteger(0);

        private volatile AccountStatus status =
            AccountStatus.ACTIVE;

        private volatile byte[] mfaSecret;

        User(
            String id,
            String username,
            PasswordRecord password,
            Set<String> roles,
            String department,
            int clearance
        ) {
            this.id = id;
            this.username = username;
            this.password = password;
            this.roles = Set.copyOf(roles);
            this.department = department;
            this.clearance = clearance;
        }

        String id() {
            return id;
        }

        String username() {
            return username;
        }

        PasswordRecord password() {
            return password;
        }

        Set<String> roles() {
            return roles;
        }

        String department() {
            return department;
        }

        int clearance() {
            return clearance;
        }

        AccountStatus status() {
            return status;
        }

        void lock() {
            status = AccountStatus.LOCKED;
        }

        void disable() {
            status = AccountStatus.DISABLED;
        }

        int incrementFailures() {
            return failedAttempts.incrementAndGet();
        }

        void resetFailures() {
            failedAttempts.set(0);
        }

        void enrollMfa(byte[] secret) {
            if (status != AccountStatus.ACTIVE) {
                throw new ValidationException("Account unavailable.");
            }

            mfaSecret = secret.clone();
        }

        boolean isMfaEnrolled() {
            return mfaSecret != null;
        }

        byte[] mfaSecret() {
            return mfaSecret == null ? null : mfaSecret.clone();
        }
    }

    // ========================================================
    // Password hashing
    // ========================================================

    static final class PasswordService {
        private static final int ITERATIONS = 600_000;
        private static final int KEY_LENGTH = 256;

        private static final SecureRandom RANDOM =
            new SecureRandom();

        static PasswordRecord hash(char[] password) {
            validate(password);

            byte[] salt = new byte[16];
            RANDOM.nextBytes(salt);

            return new PasswordRecord(
                "PBKDF2WithHmacSHA256",
                ITERATIONS,
                salt,
                derive(password, salt, ITERATIONS)
            );
        }

        static void validate(char[] password) {
            if (password == null || password.length < 12) {
                throw new ValidationException("Password too short.");
            }

            boolean upper = false;
            boolean lower = false;
            boolean digit = false;
            boolean special = false;

            for (char character : password) {
                upper |= Character.isUpperCase(character);
                lower |= Character.isLowerCase(character);
                digit |= Character.isDigit(character);
                special |= !Character.isLetterOrDigit(character);
            }

            if (!upper || !lower || !digit || !special) {
                throw new ValidationException("Password policy violation.");
            }
        }

        private static byte[] derive(
            char[] password,
            byte[] salt,
            int iterations
        ) {
            PBEKeySpec specification = new PBEKeySpec(
                password,
                salt,
                iterations,
                KEY_LENGTH
            );

            try {
                SecretKeyFactory factory =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");

                return factory.generateSecret(specification).getEncoded();

            } catch (GeneralSecurityException exception) {
                throw new IllegalStateException(
                    "Password hashing unavailable.",
                    exception
                );

            } finally {
                specification.clearPassword();
            }
        }

        static boolean verify(
            char[] password,
            PasswordRecord record
        ) {
            if (record == null ||
                !record.algorithm().equals("PBKDF2WithHmacSHA256") ||
                record.iterations() < 100_000 ||
                record.iterations() > 2_000_000) {
                return false;
            }

            byte[] actual = derive(
                password,
                record.salt(),
                record.iterations()
            );

            return MessageDigest.isEqual(
                actual,
                record.hash()
            );
        }
    }

    // ========================================================
    // TOTP multi-factor authentication
    // ========================================================

    static final class TOTPService {
        private static final int PERIOD = 30;

        private static final SecureRandom RANDOM =
            new SecureRandom();

        static byte[] generateSecret() {
            byte[] secret = new byte[20];
            RANDOM.nextBytes(secret);
            return secret;
        }

        static String generate(byte[] secret, long epochSeconds) {
            long counter = epochSeconds / PERIOD;

            byte[] message = new byte[8];

            for (int i = 7; i >= 0; i--) {
                message[i] = (byte) counter;
                counter >>>= 8;
            }

            try {
                Mac mac = Mac.getInstance("HmacSHA1");

                mac.init(new SecretKeySpec(secret, "HmacSHA1"));

                byte[] digest = mac.doFinal(message);

                int offset = digest[digest.length - 1] & 0x0f;

                int binary =
                    ((digest[offset] & 0x7f) << 24) |
                    ((digest[offset + 1] & 0xff) << 16) |
                    ((digest[offset + 2] & 0xff) << 8) |
                    (digest[offset + 3] & 0xff);

                return String.format(
                    "%06d",
                    binary % 1_000_000
                );

            } catch (GeneralSecurityException exception) {
                throw new IllegalStateException(exception);
            }
        }

        static boolean verify(
            byte[] secret,
            String suppliedCode,
            long epochSeconds
        ) {
            if (suppliedCode == null ||
                !suppliedCode.matches("\\d{6}")) {
                return false;
            }

            for (int offset = -1; offset <= 1; offset++) {
                String expected = generate(
                    secret,
                    epochSeconds + offset * PERIOD
                );

                if (MessageDigest.isEqual(
                    expected.getBytes(StandardCharsets.US_ASCII),
                    suppliedCode.getBytes(StandardCharsets.US_ASCII)
                )) {
                    return true;
                }
            }

            return false;
        }
    }

    // ========================================================
    // RBAC policy
    // ========================================================

    static final class RBACPolicy {
        private final Map<String, Set<Permission>> permissions =
            new HashMap<>();

        RBACPolicy() {
            permissions.put(
                "employee",
                EnumSet.of(
                    Permission.PROFILE_READ,
                    Permission.PROFILE_UPDATE
                )
            );

            permissions.put(
                "analyst",
                EnumSet.of(
                    Permission.PROFILE_READ,
                    Permission.REPORTS_READ
                )
            );

            permissions.put(
                "admin",
                EnumSet.allOf(Permission.class)
            );
        }

        boolean allows(
            Set<String> roles,
            Permission permission
        ) {
            return roles.stream().anyMatch(role ->
                permissions.getOrDefault(role, Set.of())
                    .contains(permission)
            );
        }
    }

    // ========================================================
    // ABAC policy
    // ========================================================

    static final class ABACPolicy {

        boolean evaluate(
            User subject,
            Resource resource,
            String action,
            Environment environment
        ) {
            if (subject.status() != AccountStatus.ACTIVE ||
                !environment.mfaVerified() ||
                environment.riskScore() > 70) {
                return false;
            }

            if ("read".equals(action)) {
                return subject.department().equals(
                    resource.department()
                ) || subject.roles().contains("admin");
            }

            if ("approve".equals(action)) {
                return subject.department().equals(
                    resource.department()
                ) &&
                    subject.clearance() >= resource.classification() &&
                    !subject.id().equals(resource.ownerId());
            }

            return false;
        }
    }

    // ========================================================
    // Access-token service
    // ========================================================

    static final class TokenService {
        private final byte[] signingKey;

        TokenService(byte[] signingKey) {
            if (signingKey == null || signingKey.length < 32) {
                throw new ValidationException("Signing key too short.");
            }

            this.signingKey = signingKey.clone();
        }

        private byte[] sign(String content) {
            try {
                Mac mac = Mac.getInstance("HmacSHA256");

                mac.init(new SecretKeySpec(
                    signingKey,
                    "HmacSHA256"
                ));

                return mac.doFinal(
                    content.getBytes(StandardCharsets.UTF_8)
                );

            } catch (GeneralSecurityException exception) {
                throw new IllegalStateException(exception);
            }
        }

        String issue(User user, long lifetimeSeconds) {
            if (lifetimeSeconds < 1 || lifetimeSeconds > 3600) {
                throw new ValidationException("Invalid token lifetime.");
            }

            long now = Instant.now().getEpochSecond();

            String roles = String.join(",", user.roles());

            String payload =
                user.id() + "|" +
                roles + "|" +
                now + "|" +
                (now + lifetimeSeconds) + "|" +
                UUID.randomUUID() + "|" +
                "identity.example|api.example";

            String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(
                    payload.getBytes(StandardCharsets.UTF_8)
                );

            String signature = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(sign(encoded));

            return encoded + "." + signature;
        }

        TokenClaims verify(String token) {
            String[] parts = token.split("\\.", -1);

            if (parts.length != 2) {
                throw new AuthenticationException("Malformed token.");
            }

            byte[] expected = sign(parts[0]);

            byte[] supplied;

            try {
                supplied = Base64.getUrlDecoder().decode(parts[1]);
            } catch (IllegalArgumentException exception) {
                throw new AuthenticationException("Invalid signature.");
            }

            if (!MessageDigest.isEqual(expected, supplied)) {
                throw new AuthenticationException("Invalid signature.");
            }

            try {
                String payload = new String(
                    Base64.getUrlDecoder().decode(parts[0]),
                    StandardCharsets.UTF_8
                );

                String[] values = payload.split("\\|", -1);

                if (values.length != 7) {
                    throw new AuthenticationException("Invalid claims.");
                }

                long issuedAt = Long.parseLong(values[2]);
                long expiresAt = Long.parseLong(values[3]);

                if (!values[5].equals("identity.example") ||
                    !values[6].equals("api.example") ||
                    expiresAt <= Instant.now().getEpochSecond()) {
                    throw new AuthenticationException("Invalid token claims.");
                }

                Set<String> roles = new HashSet<>();

                if (!values[1].isEmpty()) {
                    roles.addAll(List.of(values[1].split(",")));
                }

                return new TokenClaims(
                    values[0],
                    roles,
                    values[5],
                    values[6],
                    issuedAt,
                    expiresAt,
                    values[4]
                );

            } catch (NumberFormatException exception) {
                throw new AuthenticationException("Invalid token claims.");
            }
        }
    }

    // ========================================================
    // Session management
    // ========================================================

    static final class Session {
        private final String id;
        private final String userId;
        private final long createdAt;
        private final long expiresAt;

        private volatile SessionStatus status =
            SessionStatus.ACTIVE;

        Session(String userId, long lifetimeSeconds) {
            this.id = UUID.randomUUID().toString();
            this.userId = userId;
            this.createdAt = Instant.now().getEpochSecond();
            this.expiresAt = createdAt + lifetimeSeconds;
        }

        String id() {
            return id;
        }

        String userId() {
            return userId;
        }

        SessionStatus status() {
            return status;
        }
    }

    static final class SessionService {
        private final Map<String, Session> sessions =
            new ConcurrentHashMap<>();

        Session create(User user) {
            if (user.status() != AccountStatus.ACTIVE) {
                throw new AuthenticationException("Account unavailable.");
            }

            Session session = new Session(user.id(), 1800);

            sessions.put(session.id(), session);

            return session;
        }

        Session validate(String id) {
            Session session = sessions.get(id);

            if (session == null ||
                session.status != SessionStatus.ACTIVE) {
                throw new AuthenticationException("Invalid session.");
            }

            if (Instant.now().getEpochSecond() >= session.expiresAt) {
                session.status = SessionStatus.EXPIRED;

                throw new AuthenticationException("Session expired.");
            }

            return session;
        }

        void revoke(String id) {
            Session session = sessions.get(id);

            if (session != null) {
                session.status = SessionStatus.REVOKED;
            }
        }

        int revokeAll(String userId) {
            int count = 0;

            for (Session session : sessions.values()) {
                if (session.userId().equals(userId) &&
                    session.status == SessionStatus.ACTIVE) {
                    session.status = SessionStatus.REVOKED;
                    count++;
                }
            }

            return count;
        }
    }

    // ========================================================
    // OAuth 2.0 PKCE
    // ========================================================

    static final class OAuthService {
        private final Map<String, Set<String>> clients =
            new ConcurrentHashMap<>();

        private final Map<String, AuthorizationCode> codes =
            new ConcurrentHashMap<>();

        record AuthorizationCode(
            String clientId,
            String redirectUri,
            String state,
            String challenge,
            long expiresAt,
            boolean used
        ) {}

        void registerClient(
            String clientId,
            Set<String> redirectUris
        ) {
            if (clientId == null || clientId.isBlank() ||
                redirectUris.isEmpty()) {
                throw new ValidationException("Invalid OAuth client.");
            }

            clients.put(clientId, Set.copyOf(redirectUris));
        }

        String challenge(String verifier) {
            if (verifier == null ||
                verifier.length() < 43 ||
                verifier.length() > 128) {
                throw new ValidationException("Invalid PKCE verifier.");
            }

            try {
                byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(verifier.getBytes(StandardCharsets.US_ASCII));

                return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(digest);

            } catch (GeneralSecurityException exception) {
                throw new IllegalStateException(exception);
            }
        }

        String authorize(
            String clientId,
            String redirectUri,
            String state,
            String challenge
        ) {
            Set<String> registered = clients.get(clientId);

            if (registered == null ||
                !registered.contains(redirectUri)) {
                throw new AuthorizationException("Invalid redirect URI.");
            }

            if (state == null || state.length() < 16 ||
                challenge == null || challenge.length() != 43) {
                throw new ValidationException("Invalid OAuth parameters.");
            }

            String code = UUID.randomUUID().toString();

            codes.put(
                code,
                new AuthorizationCode(
                    clientId,
                    redirectUri,
                    state,
                    challenge,
                    Instant.now().getEpochSecond() + 300,
                    false
                )
            );

            return code;
        }

        String exchange(
            String code,
            String clientId,
            String redirectUri,
            String verifier
        ) {
            AuthorizationCode record = codes.get(code);

            if (record == null || record.used() ||
                record.expiresAt() <= Instant.now().getEpochSecond()) {
                throw new AuthenticationException("Invalid authorization code.");
            }

            if (!record.clientId().equals(clientId) ||
                !record.redirectUri().equals(redirectUri)) {
                throw new AuthenticationException("Client mismatch.");
            }

            if (!MessageDigest.isEqual(
                record.challenge().getBytes(StandardCharsets.US_ASCII),
                challenge(verifier).getBytes(StandardCharsets.US_ASCII)
            )) {
                throw new AuthenticationException("PKCE verification failed.");
            }

            AuthorizationCode consumed = new AuthorizationCode(
                record.clientId(),
                record.redirectUri(),
                record.state(),
                record.challenge(),
                record.expiresAt(),
                true
            );

            if (!codes.replace(code, record, consumed)) {
                throw new AuthenticationException("Authorization code reused.");
            }

            return UUID.randomUUID().toString();
        }
    }

    // ========================================================
    // Authentication service
    // ========================================================

    static final class IdentityService {
        private final Map<String, User> users =
            new ConcurrentHashMap<>();

        private final Map<String, String> usernames =
            new ConcurrentHashMap<>();

        private final SessionService sessions =
            new SessionService();

        private final RBACPolicy rbac = new RBACPolicy();

        User register(
            String username,
            char[] password,
            Set<String> roles,
            String department,
            int clearance
        ) {
            String normalized = username.toLowerCase();

            if (!normalized.matches("[a-z0-9_.-]{3,40}")) {
                throw new ValidationException("Invalid username.");
            }

            if (usernames.containsKey(normalized)) {
                throw new ValidationException("Duplicate username.");
            }

            Set<String> validRoles = Set.of(
                "employee",
                "analyst",
                "admin"
            );

            if (roles.isEmpty() || !validRoles.containsAll(roles)) {
                throw new ValidationException("Invalid roles.");
            }

            PasswordRecord passwordRecord =
                PasswordService.hash(password);

            User user = new User(
                UUID.randomUUID().toString(),
                normalized,
                passwordRecord,
                roles,
                department,
                clearance
            );

            User previous = users.putIfAbsent(user.id(), user);

            if (previous != null ||
                usernames.putIfAbsent(normalized, user.id()) != null) {
                throw new ValidationException("Concurrent registration conflict.");
            }

            return user;
        }

        Session authenticate(
            String username,
            char[] password,
            String mfaCode
        ) {
            String userId = usernames.get(username.toLowerCase());

            User user = userId == null ? null : users.get(userId);

            if (user == null ||
                user.status() != AccountStatus.ACTIVE) {
                throw new AuthenticationException("Invalid credentials.");
            }

            if (!PasswordService.verify(password, user.password())) {
                if (user.incrementFailures() >= 5) {
                    user.lock();
                }

                throw new AuthenticationException("Invalid credentials.");
            }

            if (user.isMfaEnrolled()) {
                if (!TOTPService.verify(
                    user.mfaSecret(),
                    mfaCode,
                    Instant.now().getEpochSecond()
                )) {
                    throw new AuthenticationException("MFA failed.");
                }
            }

            user.resetFailures();

            return sessions.create(user);
        }

        void authorize(
            User user,
            Permission permission
        ) {
            if (user.status() != AccountStatus.ACTIVE ||
                !rbac.allows(user.roles(), permission)) {
                throw new AuthorizationException("Access denied.");
            }
        }

        SessionService sessions() {
            return sessions;
        }
    }

    // ========================================================
    // Integrated demonstration
    // ========================================================

    public static void main(String[] args) {

        System.out.println("AUTHENTICATION AND AUTHORIZATION");
        System.out.println("================================");

        IdentityService identity = new IdentityService();

        User alice = identity.register(
            "alice",
            "StrongPassword#2026".toCharArray(),
            Set.of("employee"),
            "engineering",
            2
        );

        User bob = identity.register(
            "bob",
            "Administrator#2026".toCharArray(),
            Set.of("admin"),
            "security",
            5
        );

        System.out.println("\n1. Password authentication");

        Session session = identity.authenticate(
            "alice",
            "StrongPassword#2026".toCharArray(),
            null
        );

        System.out.println("Session created: " + session.id());

        System.out.println("\n2. RBAC");

        identity.authorize(alice, Permission.PROFILE_READ);

        System.out.println("Profile access granted.");

        try {
            identity.authorize(alice, Permission.USERS_MANAGE);
        } catch (AuthorizationException exception) {
            System.out.println("Administrative access denied.");
        }

        identity.authorize(bob, Permission.USERS_MANAGE);

        System.out.println("Administrator access granted.");

        System.out.println("\n3. MFA");

        byte[] secret = TOTPService.generateSecret();

        long now = Instant.now().getEpochSecond();

        String code = TOTPService.generate(secret, now);

        System.out.println(
            "TOTP valid: " +
            TOTPService.verify(secret, code, now)
        );

        System.out.println("\n4. ABAC");

        ABACPolicy abac = new ABACPolicy();

        Resource report = new Resource(
            "R001",
            "engineering",
            "U003",
            1
        );

        Environment environment = new Environment(
            true,
            20,
            "corporate"
        );

        System.out.println(
            "Department access: " +
            abac.evaluate(alice, report, "read", environment)
        );

        System.out.println("\n5. Signed access token");

        byte[] signingKey = new byte[32];
        new SecureRandom().nextBytes(signingKey);

        TokenService tokenService = new TokenService(signingKey);

        String token = tokenService.issue(alice, 900);

        TokenClaims claims = tokenService.verify(token);

        System.out.println("Token subject: " + claims.subject());

        System.out.println("\n6. OAuth authorization code and PKCE");

        OAuthService oauth = new OAuthService();

        oauth.registerClient(
            "web-client",
            Set.of("https://client.example/callback")
        );

        String verifier = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(new byte[32]);

        String challenge = oauth.challenge(verifier);

        String authorizationCode = oauth.authorize(
            "web-client",
            "https://client.example/callback",
            UUID.randomUUID().toString(),
            challenge
        );

        String oauthToken = oauth.exchange(
            authorizationCode,
            "web-client",
            "https://client.example/callback",
            verifier
        );

        System.out.println("OAuth exchange successful: " +
            !oauthToken.isEmpty());

        System.out.println("\n7. Session revocation");

        identity.sessions().validate(session.id());

        identity.sessions().revoke(session.id());

        try {
            identity.sessions().validate(session.id());
        } catch (AuthenticationException exception) {
            System.out.println("Revoked session rejected.");
        }

        System.out.println("\n8. Validation tests");

        if (PasswordService.verify(
            "IncorrectPassword#2026".toCharArray(),
            alice.password()
        )) {
            throw new AssertionError("Incorrect password accepted.");
        }

        try {
            tokenService.verify(token + "tampered");
            throw new AssertionError("Tampered token accepted.");
        } catch (AuthenticationException expected) {
            System.out.println("Tampered token rejected.");
        }

        System.out.println("\nAll demonstrations completed.");
    }
}
