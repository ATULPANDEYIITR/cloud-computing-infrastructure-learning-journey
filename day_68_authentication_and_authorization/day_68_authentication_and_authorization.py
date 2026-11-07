#!/usr/bin/env python3
"""
Authentication and Authorization
MFA, passwords, tokens, sessions, OAuth concepts, RBAC and ABAC.

Python 3.10+
Standard-library implementation.

Educational security model. Production systems should use a vetted
identity provider, secure secret management and established protocols.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ============================================================
# Exceptions and domain types
# ============================================================

class AuthenticationError(Exception):
    pass


class AuthorizationError(Exception):
    pass


class ValidationError(Exception):
    pass


class AccountStatus(Enum):
    ACTIVE = "active"
    LOCKED = "locked"
    DISABLED = "disabled"


class SessionStatus(Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class Permission(Enum):
    READ_PROFILE = "profile:read"
    UPDATE_PROFILE = "profile:update"
    READ_REPORTS = "reports:read"
    MANAGE_USERS = "users:manage"
    MANAGE_SECURITY = "security:manage"


@dataclass
class User:
    user_id: str
    username: str
    password_hash: str
    roles: set[str] = field(default_factory=set)
    status: AccountStatus = AccountStatus.ACTIVE
    failed_attempts: int = 0
    mfa_secret: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    session_id: str
    user_id: str
    created_at: float
    expires_at: float
    status: SessionStatus = SessionStatus.ACTIVE


@dataclass
class OAuthAuthorization:
    client_id: str
    redirect_uri: str
    state: str
    code_challenge: str
    code: str
    expires_at: float
    used: bool = False


# ============================================================
# Password management
# ============================================================

class PasswordManager:
    ITERATIONS = 600_000
    SALT_BYTES = 16

    @staticmethod
    def validate(password: str) -> None:
        if len(password) < 12:
            raise ValidationError("Password must contain at least 12 characters.")

        if not any(c.isupper() for c in password):
            raise ValidationError("Password needs an uppercase character.")

        if not any(c.islower() for c in password):
            raise ValidationError("Password needs a lowercase character.")

        if not any(c.isdigit() for c in password):
            raise ValidationError("Password needs a digit.")

        if not any(not c.isalnum() for c in password):
            raise ValidationError("Password needs a special character.")

    @classmethod
    def hash_password(cls, password: str) -> str:
        cls.validate(password)

        salt = secrets.token_bytes(cls.SALT_BYTES)

        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            cls.ITERATIONS
        )

        return (
            f"pbkdf2_sha256${cls.ITERATIONS}$"
            f"{base64.b64encode(salt).decode()}$"
            f"{base64.b64encode(derived).decode()}"
        )

    @staticmethod
    def verify(password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations, salt, expected = stored_hash.split("$")

            if algorithm != "pbkdf2_sha256":
                return False

            iterations = int(iterations)

            if not 100_000 <= iterations <= 2_000_000:
                return False

            salt_bytes = base64.b64decode(salt, validate=True)
            expected_bytes = base64.b64decode(expected, validate=True)

            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt_bytes,
                iterations
            )

            return hmac.compare_digest(actual, expected_bytes)

        except (ValueError, TypeError):
            return False


# ============================================================
# Multi-factor authentication: TOTP
# ============================================================

class TOTP:
    PERIOD = 30
    DIGITS = 6

    @staticmethod
    def generate_secret() -> bytes:
        return secrets.token_bytes(20)

    @classmethod
    def generate(cls, secret: bytes, timestamp: int | None = None) -> str:
        timestamp = int(time.time()) if timestamp is None else timestamp
        counter = timestamp // cls.PERIOD

        message = counter.to_bytes(8, "big")
        digest = hmac.new(secret, message, hashlib.sha1).digest()

        offset = digest[-1] & 0x0F

        binary = (
            ((digest[offset] & 0x7F) << 24)
            | ((digest[offset + 1] & 0xFF) << 16)
            | ((digest[offset + 2] & 0xFF) << 8)
            | (digest[offset + 3] & 0xFF)
        )

        return str(binary % (10 ** cls.DIGITS)).zfill(cls.DIGITS)

    @classmethod
    def verify(
        cls,
        secret: bytes,
        supplied_code: str,
        timestamp: int | None = None
    ) -> bool:

        if not re.fullmatch(r"\d{6}", supplied_code):
            return False

        timestamp = int(time.time()) if timestamp is None else timestamp

        # Allow one 30-second interval of clock drift.
        return any(
            hmac.compare_digest(
                cls.generate(secret, timestamp + offset * cls.PERIOD),
                supplied_code
            )
            for offset in (-1, 0, 1)
        )


# ============================================================
# Signed access tokens
# ============================================================

class TokenManager:
    """
    Compact HMAC-signed token model.

    Production deployments should use a vetted JWT/OIDC library
    with explicit algorithm, issuer, audience and key validation.
    """

    def __init__(self, secret: bytes):
        if len(secret) < 32:
            raise ValidationError("Signing secret must contain at least 32 bytes.")

        self.secret = secret

    @staticmethod
    def encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    @staticmethod
    def decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(
            value + "=" * (-len(value) % 4)
        )

    def issue(
        self,
        user_id: str,
        roles: set[str],
        lifetime: int = 900
    ) -> str:

        if lifetime <= 0 or lifetime > 3600:
            raise ValidationError("Invalid access-token lifetime.")

        header = {"alg": "HS256", "typ": "JWT"}

        payload = {
            "sub": user_id,
            "roles": sorted(roles),
            "iat": int(time.time()),
            "exp": int(time.time()) + lifetime,
            "jti": secrets.token_urlsafe(16),
            "iss": "example-identity-service",
            "aud": "example-api"
        }

        first = self.encode(
            json.dumps(header, separators=(",", ":")).encode()
        )

        second = self.encode(
            json.dumps(payload, separators=(",", ":")).encode()
        )

        message = f"{first}.{second}".encode()

        signature = hmac.new(
            self.secret,
            message,
            hashlib.sha256
        ).digest()

        return f"{first}.{second}.{self.encode(signature)}"

    def verify(self, token: str) -> dict[str, Any]:
        try:
            parts = token.split(".")

            if len(parts) != 3:
                raise AuthenticationError("Malformed token.")

            header = json.loads(self.decode(parts[0]))
            payload = json.loads(self.decode(parts[1]))
            supplied_signature = self.decode(parts[2])

            if header != {"alg": "HS256", "typ": "JWT"}:
                raise AuthenticationError("Unsupported token algorithm.")

            expected_signature = hmac.new(
                self.secret,
                f"{parts[0]}.{parts[1]}".encode(),
                hashlib.sha256
            ).digest()

            if not hmac.compare_digest(
                supplied_signature,
                expected_signature
            ):
                raise AuthenticationError("Invalid signature.")

            if payload.get("iss") != "example-identity-service":
                raise AuthenticationError("Invalid issuer.")

            if payload.get("aud") != "example-api":
                raise AuthenticationError("Invalid audience.")

            if not isinstance(payload.get("exp"), int):
                raise AuthenticationError("Invalid expiration.")

            if payload["exp"] <= int(time.time()):
                raise AuthenticationError("Token expired.")

            if not isinstance(payload.get("roles"), list):
                raise AuthenticationError("Invalid roles.")

            if not isinstance(payload.get("sub"), str):
                raise AuthenticationError("Invalid subject.")

            return payload

        except AuthenticationError:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise AuthenticationError("Token validation failed.") from None


# ============================================================
# RBAC: role-based access control
# ============================================================

class RBAC:
    ROLE_PERMISSIONS = {
        "employee": {
            Permission.READ_PROFILE,
            Permission.UPDATE_PROFILE
        },
        "analyst": {
            Permission.READ_PROFILE,
            Permission.READ_REPORTS
        },
        "admin": set(Permission)
    }

    @classmethod
    def is_allowed(
        cls,
        roles: set[str],
        permission: Permission
    ) -> bool:

        effective = set()

        for role in roles:
            effective.update(cls.ROLE_PERMISSIONS.get(role, set()))

        return permission in effective


# ============================================================
# ABAC: attribute-based access control
# ============================================================

class ABAC:
    @staticmethod
    def evaluate(
        subject: dict[str, Any],
        resource: dict[str, Any],
        action: str,
        environment: dict[str, Any]
    ) -> bool:

        # Explicit policy conditions.
        if subject.get("status") != "active":
            return False

        if environment.get("mfa_verified") is not True:
            return False

        if environment.get("risk_score", 100) > 70:
            return False

        if action == "read":
            return (
                subject.get("department") == resource.get("department")
                or "admin" in subject.get("roles", [])
            )

        if action == "approve":
            return (
                subject.get("department") == resource.get("department")
                and subject.get("clearance", 0)
                >= resource.get("classification", 0)
                and subject.get("user_id") != resource.get("owner_id")
            )

        return False


# ============================================================
# OAuth 2.0 authorization-code and PKCE model
# ============================================================

class OAuthService:
    def __init__(self):
        self.authorizations: dict[str, OAuthAuthorization] = {}

    @staticmethod
    def s256(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode()).digest()

        return base64.urlsafe_b64encode(
            digest
        ).rstrip(b"=").decode()

    def authorize(
        self,
        client_id: str,
        redirect_uri: str,
        registered_redirect_uris: set[str],
        state: str,
        code_challenge: str
    ) -> str:

        if redirect_uri not in registered_redirect_uris:
            raise ValidationError("Unregistered redirect URI.")

        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", code_challenge):
            raise ValidationError("Invalid PKCE challenge.")

        if not state or len(state) < 16:
            raise ValidationError("State must be unpredictable.")

        code = secrets.token_urlsafe(32)

        self.authorizations[code] = OAuthAuthorization(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code=code,
            expires_at=time.time() + 300
        )

        return code

    def exchange(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        verifier: str
    ) -> str:

        authorization = self.authorizations.get(code)

        if authorization is None:
            raise AuthenticationError("Unknown authorization code.")

        if authorization.used or authorization.expires_at <= time.time():
            raise AuthenticationError("Authorization code expired or used.")

        if authorization.client_id != client_id:
            raise AuthenticationError("Client mismatch.")

        if authorization.redirect_uri != redirect_uri:
            raise AuthenticationError("Redirect URI mismatch.")

        if not 43 <= len(verifier) <= 128:
            raise AuthenticationError("Invalid PKCE verifier.")

        if not hmac.compare_digest(
            self.s256(verifier),
            authorization.code_challenge
        ):
            raise AuthenticationError("PKCE verification failed.")

        # Authorization codes are single-use.
        authorization.used = True

        return secrets.token_urlsafe(32)


# ============================================================
# Identity and session service
# ============================================================

class IdentityService:
    MAX_FAILED_ATTEMPTS = 5
    SESSION_LIFETIME = 1800

    def __init__(self):
        self.users: dict[str, User] = {}
        self.sessions: dict[str, Session] = {}
        self.username_index: dict[str, str] = {}

    def register(
        self,
        username: str,
        password: str,
        roles: set[str],
        department: str
    ) -> User:

        username = username.strip().lower()

        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
            raise ValidationError("Invalid username.")

        if username in self.username_index:
            raise ValidationError("Username already exists.")

        if not roles or not roles.issubset(RBAC.ROLE_PERMISSIONS):
            raise ValidationError("Unknown or missing role.")

        user = User(
            user_id=str(uuid.uuid4()),
            username=username,
            password_hash=PasswordManager.hash_password(password),
            roles=set(roles),
            attributes={
                "department": department,
                "status": "active",
                "clearance": 1
            }
        )

        self.users[user.user_id] = user
        self.username_index[username] = user.user_id

        return user

    def enroll_mfa(self, user_id: str) -> str:
        user = self.users.get(user_id)

        if user is None or user.status != AccountStatus.ACTIVE:
            raise AuthenticationError("Account unavailable.")

        secret = TOTP.generate_secret()
        user.mfa_secret = base64.b32encode(secret).decode().rstrip("=")

        return user.mfa_secret

    @staticmethod
    def decode_mfa_secret(encoded: str) -> bytes:
        padded = encoded + "=" * (-len(encoded) % 8)
        return base64.b32decode(padded)

    def authenticate(
        self,
        username: str,
        password: str,
        mfa_code: str | None = None
    ) -> Session:

        user_id = self.username_index.get(username.strip().lower())
        user = self.users.get(user_id) if user_id else None

        if user is None:
            raise AuthenticationError("Invalid credentials.")

        if user.status != AccountStatus.ACTIVE:
            raise AuthenticationError("Account unavailable.")

        if user.failed_attempts >= self.MAX_FAILED_ATTEMPTS:
            user.status = AccountStatus.LOCKED
            raise AuthenticationError("Account locked.")

        if not PasswordManager.verify(password, user.password_hash):
            user.failed_attempts += 1

            if user.failed_attempts >= self.MAX_FAILED_ATTEMPTS:
                user.status = AccountStatus.LOCKED

            raise AuthenticationError("Invalid credentials.")

        if user.mfa_secret is not None:
            if mfa_code is None:
                raise AuthenticationError("MFA verification required.")

            if not TOTP.verify(
                self.decode_mfa_secret(user.mfa_secret),
                mfa_code
            ):
                raise AuthenticationError("Invalid MFA code.")

        user.failed_attempts = 0

        session = Session(
            session_id=secrets.token_urlsafe(32),
            user_id=user.user_id,
            created_at=time.time(),
            expires_at=time.time() + self.SESSION_LIFETIME
        )

        self.sessions[session.session_id] = session

        return session

    def validate_session(self, session_id: str) -> User:
        session = self.sessions.get(session_id)

        if session is None or session.status != SessionStatus.ACTIVE:
            raise AuthenticationError("Invalid session.")

        if session.expires_at <= time.time():
            session.status = SessionStatus.EXPIRED
            raise AuthenticationError("Session expired.")

        user = self.users.get(session.user_id)

        if user is None or user.status != AccountStatus.ACTIVE:
            session.status = SessionStatus.REVOKED
            raise AuthenticationError("Account unavailable.")

        return user

    def logout(self, session_id: str) -> None:
        session = self.sessions.get(session_id)

        if session:
            session.status = SessionStatus.REVOKED

    def revoke_user_sessions(self, user_id: str) -> int:
        count = 0

        for session in self.sessions.values():
            if (
                session.user_id == user_id
                and session.status == SessionStatus.ACTIVE
            ):
                session.status = SessionStatus.REVOKED
                count += 1

        return count


# ============================================================
# Integrated authentication and authorization workflow
# ============================================================

def main() -> None:
    print("AUTHENTICATION AND AUTHORIZATION DEMONSTRATION")
    print("=" * 55)

    identity = IdentityService()

    employee = identity.register(
        "alice",
        "StrongPassword#2026",
        {"employee"},
        "engineering"
    )

    administrator = identity.register(
        "bob",
        "AdminPassword#2026",
        {"admin"},
        "security"
    )

    # Password verification and session establishment.
    session = identity.authenticate(
        "alice",
        "StrongPassword#2026"
    )

    print("\n1. Authentication")
    print("Authenticated:", employee.username)
    print("Session established:", bool(session.session_id))

    # RBAC decision.
    print("\n2. Role-Based Access Control")

    print(
        "Read profile:",
        RBAC.is_allowed(
            employee.roles,
            Permission.READ_PROFILE
        )
    )

    print(
        "Manage users:",
        RBAC.is_allowed(
            employee.roles,
            Permission.MANAGE_USERS
        )
    )

    # ABAC decision.
    print("\n3. Attribute-Based Access Control")

    subject = {
        "user_id": employee.user_id,
        "status": "active",
        "department": "engineering",
        "roles": ["employee"],
        "clearance": 2
    }

    resource = {
        "department": "engineering",
        "classification": 1,
        "owner_id": "another-user"
    }

    environment = {
        "mfa_verified": True,
        "risk_score": 20
    }

    print(
        "Resource access:",
        ABAC.evaluate(subject, resource, "read", environment)
    )

    # MFA verification.
    print("\n4. Multi-Factor Authentication")

    secret = TOTP.generate_secret()
    current_code = TOTP.generate(secret)

    print(
        "TOTP verification:",
        TOTP.verify(secret, current_code)
    )

    # Signed token.
    print("\n5. Access Tokens")

    token_manager = TokenManager(secrets.token_bytes(32))

    token = token_manager.issue(
        employee.user_id,
        employee.roles
    )

    claims = token_manager.verify(token)

    print("Token subject:", claims["sub"])
    print("Token roles:", claims["roles"])

    # OAuth authorization-code flow with PKCE.
    print("\n6. OAuth 2.0 and PKCE")

    oauth = OAuthService()

    verifier = secrets.token_urlsafe(48)
    challenge = oauth.s256(verifier)

    code = oauth.authorize(
        client_id="web-client",
        redirect_uri="https://client.example/callback",
        registered_redirect_uris={
            "https://client.example/callback"
        },
        state=secrets.token_urlsafe(24),
        code_challenge=challenge
    )

    access_token = oauth.exchange(
        code,
        "web-client",
        "https://client.example/callback",
        verifier
    )

    print("OAuth token issued:", bool(access_token))

    # Session validation and revocation.
    print("\n7. Session Lifecycle")

    authenticated_user = identity.validate_session(
        session.session_id
    )

    print("Session user:", authenticated_user.username)

    identity.logout(session.session_id)

    try:
        identity.validate_session(session.session_id)
    except AuthenticationError as error:
        print("Revoked session rejected:", error)

    # Administrator permissions.
    print("\n8. Administrator Authorization")

    print(
        "Can manage users:",
        RBAC.is_allowed(
            administrator.roles,
            Permission.MANAGE_USERS
        )
    )

    # Negative tests.
    print("\n9. Security Validation")

    assert not PasswordManager.verify(
        "IncorrectPassword",
        employee.password_hash
    )

    assert not TOTP.verify(
        secret,
        "123456",
        timestamp=0
    )

    try:
        token_manager.verify(token + "invalid")
    except AuthenticationError:
        print("Tampered token rejected.")

    print("\nAll demonstrations completed.")


if __name__ == "__main__":
    main()
