#!/usr/bin/env python3
"""
Encryption Fundamentals
Demonstrates:
- Symmetric encryption using AES-256-GCM
- Asymmetric encryption using RSA-OAEP
- Encryption at rest using authenticated file encryption
- Encryption in transit using TLS configuration and certificate validation
- Hybrid encryption using AES-GCM and RSA-OAEP
- Key management, rotation, validation, and integrity verification

Dependency:
    python -m pip install cryptography

Run:
    python encryption_fundamentals.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import tempfile
import unittest

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hmac as crypto_hmac


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(asctime)s %(message)s",
)

LOGGER = logging.getLogger("encryption_fundamentals")


class EncryptionError(Exception):
    """Base exception for encryption operations."""


class AuthenticationError(EncryptionError):
    """Raised when authentication or integrity verification fails."""


class KeyManagementError(EncryptionError):
    """Raised when a key operation is invalid."""


class EncryptionMode(Enum):
    AT_REST = "at_rest"
    IN_TRANSIT = "in_transit"
    HYBRID = "hybrid"


class KeyStatus(Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    REVOKED = "revoked"


@dataclass(frozen=True)
class EncryptionMetadata:
    algorithm: str
    key_id: str
    nonce: str
    created_at: str
    mode: str


@dataclass
class ManagedKey:
    key_id: str
    material: bytes
    status: KeyStatus
    created_at: datetime


class KeyManager:
    """
    In-memory demonstration of key lifecycle management.

    Production deployments should use a KMS or HSM.
    """

    def __init__(self):
        self._keys: dict[str, ManagedKey] = {}
        self._active_key_id: Optional[str] = None

    def create_key(self) -> str:
        key_id = secrets.token_hex(12)

        key = ManagedKey(
            key_id=key_id,
            material=AESGCM.generate_key(bit_length=256),
            status=KeyStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )

        if self._active_key_id:
            self._keys[self._active_key_id].status = KeyStatus.RETIRED

        self._keys[key_id] = key
        self._active_key_id = key_id

        LOGGER.info("Created encryption key: %s", key_id)
        return key_id

    def get_active_key(self) -> ManagedKey:
        if not self._active_key_id:
            raise KeyManagementError("No active encryption key")

        key = self._keys[self._active_key_id]

        if key.status != KeyStatus.ACTIVE:
            raise KeyManagementError("Active key is not usable")

        return key

    def get_key(self, key_id: str) -> ManagedKey:
        key = self._keys.get(key_id)

        if key is None:
            raise KeyManagementError("Unknown key identifier")

        if key.status == KeyStatus.REVOKED:
            raise KeyManagementError("Key has been revoked")

        return key

    def revoke_key(self, key_id: str) -> None:
        key = self.get_key(key_id)
        key.status = KeyStatus.REVOKED

        if self._active_key_id == key_id:
            self._active_key_id = None

    def rotate_key(self) -> str:
        return self.create_key()

    def inventory(self) -> list[dict]:
        return [
            {
                "key_id": key.key_id,
                "status": key.status.value,
                "created_at": key.created_at.isoformat(),
            }
            for key in self._keys.values()
        ]


class SymmetricEncryption:
    """AES-256-GCM authenticated encryption."""

    NONCE_SIZE = 12
    KEY_SIZE = 32

    @classmethod
    def encrypt(
        cls,
        plaintext: bytes,
        key: bytes,
        associated_data: bytes = b"",
    ) -> tuple[bytes, bytes]:

        if not isinstance(plaintext, bytes):
            raise TypeError("Plaintext must be bytes")

        if len(key) != cls.KEY_SIZE:
            raise ValueError("AES-256 requires a 32-byte key")

        nonce = os.urandom(cls.NONCE_SIZE)

        ciphertext = AESGCM(key).encrypt(
            nonce,
            plaintext,
            associated_data,
        )

        return nonce, ciphertext

    @classmethod
    def decrypt(
        cls,
        nonce: bytes,
        ciphertext: bytes,
        key: bytes,
        associated_data: bytes = b"",
    ) -> bytes:

        if len(key) != cls.KEY_SIZE:
            raise ValueError("Invalid AES-256 key length")

        if len(nonce) != cls.NONCE_SIZE:
            raise ValueError("Invalid GCM nonce length")

        try:
            return AESGCM(key).decrypt(
                nonce,
                ciphertext,
                associated_data,
            )
        except InvalidTag as exc:
            raise AuthenticationError(
                "Ciphertext authentication failed"
            ) from exc


class AsymmetricEncryption:
    """RSA-OAEP encryption and digital signatures."""

    def __init__(self, key_size: int = 3072):
        if key_size < 2048:
            raise ValueError("RSA key size must be at least 2048 bits")

        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )

        self.public_key = self.private_key.public_key()

    def encrypt(self, plaintext: bytes) -> bytes:
        return self.public_key.encrypt(
            plaintext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

    def decrypt(self, ciphertext: bytes) -> bytes:
        try:
            return self.private_key.decrypt(
                ciphertext,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
        except Exception as exc:
            raise AuthenticationError(
                "RSA decryption failed"
            ) from exc

    def sign(self, message: bytes) -> bytes:
        return self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

    def verify(self, message: bytes, signature: bytes) -> bool:
        from cryptography.exceptions import InvalidSignature

        try:
            self.public_key.verify(
                signature,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except InvalidSignature:
            return False


class HybridEncryption:
    """
    Encrypts data using AES-GCM and protects the AES key
    using RSA-OAEP.

    This avoids RSA's plaintext size limitation.
    """

    @staticmethod
    def encrypt(
        plaintext: bytes,
        recipient_public_key,
    ) -> dict:

        data_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)

        ciphertext = AESGCM(data_key).encrypt(
            nonce,
            plaintext,
            b"hybrid-envelope-v1",
        )

        wrapped_key = recipient_public_key.encrypt(
            data_key,
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        return {
            "version": 1,
            "algorithm": "AES-256-GCM+RSA-OAEP-SHA256",
            "nonce": base64.b64encode(nonce).decode(),
            "wrapped_key": base64.b64encode(wrapped_key).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }

    @staticmethod
    def decrypt(
        envelope: dict,
        recipient_private_key,
    ) -> bytes:

        required = {
            "version",
            "algorithm",
            "nonce",
            "wrapped_key",
            "ciphertext",
        }

        if set(envelope) != required:
            raise EncryptionError("Invalid envelope structure")

        if envelope["version"] != 1:
            raise EncryptionError("Unsupported envelope version")

        if envelope["algorithm"] != "AES-256-GCM+RSA-OAEP-SHA256":
            raise EncryptionError("Unsupported encryption algorithm")

        try:
            nonce = base64.b64decode(
                envelope["nonce"],
                validate=True,
            )

            wrapped_key = base64.b64decode(
                envelope["wrapped_key"],
                validate=True,
            )

            ciphertext = base64.b64decode(
                envelope["ciphertext"],
                validate=True,
            )

            if len(nonce) != 12:
                raise EncryptionError("Invalid nonce")

            data_key = recipient_private_key.decrypt(
                wrapped_key,
                padding.OAEP(
                    mgf=padding.MGF1(hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            if len(data_key) != 32:
                raise EncryptionError("Invalid data key")

            return AESGCM(data_key).decrypt(
                nonce,
                ciphertext,
                b"hybrid-envelope-v1",
            )

        except (InvalidTag, ValueError, TypeError) as exc:
            raise AuthenticationError(
                "Hybrid envelope verification failed"
            ) from exc


class SecureFileStorage:
    """
    Authenticated encryption for files at rest.

    File format:
        4 bytes: magic
        12 bytes: nonce
        remaining bytes: ciphertext and authentication tag
    """

    MAGIC = b"ENC1"
    ASSOCIATED_DATA = b"secure-file-storage-v1"

    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager

    def encrypt_file(
        self,
        source: Path,
        destination: Path,
    ) -> None:

        if not source.is_file():
            raise FileNotFoundError(source)

        if source.resolve() == destination.resolve():
            raise ValueError("Source and destination must differ")

        key = self.key_manager.get_active_key()
        plaintext = source.read_bytes()

        nonce, ciphertext = SymmetricEncryption.encrypt(
            plaintext,
            key.material,
            self.ASSOCIATED_DATA,
        )

        metadata = {
            "key_id": key.key_id,
            "algorithm": "AES-256-GCM",
        }

        header = json.dumps(
            metadata,
            separators=(",", ":"),
        ).encode()

        if len(header) > 65535:
            raise EncryptionError("Metadata is too large")

        payload = (
            self.MAGIC
            + len(header).to_bytes(2, "big")
            + header
            + nonce
            + ciphertext
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_path = destination.with_name(
            destination.name + ".tmp"
        )

        try:
            with open(temp_path, "xb") as file:
                os.chmod(temp_path, 0o600)
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_path, destination)

        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def decrypt_file(
        self,
        source: Path,
        destination: Path,
    ) -> None:

        payload = source.read_bytes()

        if len(payload) < 34 or payload[:4] != self.MAGIC:
            raise EncryptionError("Invalid encrypted file format")

        header_length = int.from_bytes(payload[4:6], "big")

        if len(payload) < 6 + header_length + 12 + 16:
            raise EncryptionError("Truncated encrypted file")

        try:
            metadata = json.loads(
                payload[6:6 + header_length]
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EncryptionError("Invalid file metadata") from exc

        if metadata.get("algorithm") != "AES-256-GCM":
            raise EncryptionError("Unsupported file algorithm")

        key = self.key_manager.get_key(metadata["key_id"])

        offset = 6 + header_length
        nonce = payload[offset:offset + 12]
        ciphertext = payload[offset + 12:]

        plaintext = SymmetricEncryption.decrypt(
            nonce,
            ciphertext,
            key.material,
            self.ASSOCIATED_DATA,
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_path = destination.with_name(
            destination.name + ".tmp"
        )

        try:
            with open(temp_path, "xb") as file:
                os.chmod(temp_path, 0o600)
                file.write(plaintext)
                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_path, destination)

        except Exception:
            temp_path.unlink(missing_ok=True)
            raise


class TransportSecurity:
    """
    Creates a secure TLS client context.

    Certificate and hostname verification remain enabled.
    """

    @staticmethod
    def create_client_context():
        import ssl

        context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH
        )

        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        return context


class Fingerprint:
    """SHA-256 content fingerprint for identification."""

    @staticmethod
    def calculate(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


def demonstrate_encryption():
    print("\n=== ENCRYPTION FUNDAMENTALS ===")

    original = (
        b"Confidential repository credentials "
        b"and enterprise records."
    )

    # 1. Symmetric encryption
    key = AESGCM.generate_key(bit_length=256)

    nonce, ciphertext = SymmetricEncryption.encrypt(
        original,
        key,
    )

    recovered = SymmetricEncryption.decrypt(
        nonce,
        ciphertext,
        key,
    )

    assert recovered == original

    print("\n1. Symmetric Encryption")
    print("Algorithm: AES-256-GCM")
    print("Ciphertext bytes:", len(ciphertext))
    print("Decryption verified:", recovered == original)

    # 2. Asymmetric encryption
    rsa_manager = AsymmetricEncryption()

    short_message = b"Secure key exchange demonstration"

    encrypted = rsa_manager.encrypt(short_message)
    decrypted = rsa_manager.decrypt(encrypted)

    assert decrypted == short_message

    print("\n2. Asymmetric Encryption")
    print("Algorithm: RSA-OAEP-SHA256")
    print("Decryption verified:", decrypted == short_message)

    # 3. Digital signatures
    signature = rsa_manager.sign(original)

    assert rsa_manager.verify(original, signature)
    assert not rsa_manager.verify(b"Modified content", signature)

    print("\n3. Digital Signatures")
    print("Valid signature:", rsa_manager.verify(original, signature))
    print(
        "Modified message accepted:",
        rsa_manager.verify(b"Modified content", signature),
    )

    # 4. Hybrid encryption
    envelope = HybridEncryption.encrypt(
        original,
        rsa_manager.public_key,
    )

    recovered = HybridEncryption.decrypt(
        envelope,
        rsa_manager.private_key,
    )

    assert recovered == original

    print("\n4. Hybrid Encryption")
    print("Algorithm:", envelope["algorithm"])
    print("Envelope decryption verified:", recovered == original)

    # 5. Encryption at rest
    manager = KeyManager()
    manager.create_key()

    storage = SecureFileStorage(manager)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        source = root / "confidential.txt"
        encrypted_file = root / "confidential.enc"
        decrypted_file = root / "restored.txt"

        source.write_bytes(original)

        storage.encrypt_file(source, encrypted_file)
        storage.decrypt_file(encrypted_file, decrypted_file)

        assert decrypted_file.read_bytes() == original

        print("\n5. Encryption at Rest")
        print("Encrypted file size:", encrypted_file.stat().st_size)
        print("File recovery verified:", True)

    # 6. Key rotation
    old_key_id = manager.get_active_key().key_id
    new_key_id = manager.rotate_key()

    assert manager.get_key(old_key_id).status == KeyStatus.RETIRED

    print("\n6. Key Management")
    print("Previous key:", old_key_id)
    print("New active key:", new_key_id)

    # 7. TLS configuration
    context = TransportSecurity.create_client_context()

    print("\n7. Encryption in Transit")
    print("Minimum TLS:", context.minimum_version.name)
    print("Certificate verification:", context.verify_mode.name)
    print("Hostname verification:", context.check_hostname)

    # 8. Integrity failure
    damaged = bytearray(ciphertext)
    damaged[0] ^= 1

    try:
        SymmetricEncryption.decrypt(
            nonce,
            bytes(damaged),
            key,
        )
    except AuthenticationError:
        print("\n8. Integrity Protection")
        print("Tampered ciphertext correctly rejected")


class EncryptionTests(unittest.TestCase):

    def setUp(self):
        self.key = AESGCM.generate_key(bit_length=256)

    def test_symmetric_round_trip(self):
        message = b"Sensitive information"

        nonce, encrypted = SymmetricEncryption.encrypt(
            message,
            self.key,
        )

        self.assertEqual(
            SymmetricEncryption.decrypt(
                nonce,
                encrypted,
                self.key,
            ),
            message,
        )

    def test_tampering_detection(self):
        nonce, encrypted = SymmetricEncryption.encrypt(
            b"Important data",
            self.key,
        )

        modified = bytearray(encrypted)
        modified[0] ^= 1

        with self.assertRaises(AuthenticationError):
            SymmetricEncryption.decrypt(
                nonce,
                bytes(modified),
                self.key,
            )

    def test_invalid_key(self):
        with self.assertRaises(ValueError):
            SymmetricEncryption.encrypt(
                b"data",
                b"short",
            )

    def test_asymmetric_round_trip(self):
        manager = AsymmetricEncryption()

        message = b"RSA encryption"

        self.assertEqual(
            manager.decrypt(manager.encrypt(message)),
            message,
        )

    def test_signature_verification(self):
        manager = AsymmetricEncryption()

        message = b"Signed transaction"
        signature = manager.sign(message)

        self.assertTrue(manager.verify(message, signature))
        self.assertFalse(
            manager.verify(b"Different transaction", signature)
        )

    def test_hybrid_round_trip(self):
        manager = AsymmetricEncryption()
        message = b"Large confidential business record"

        envelope = HybridEncryption.encrypt(
            message,
            manager.public_key,
        )

        self.assertEqual(
            HybridEncryption.decrypt(
                envelope,
                manager.private_key,
            ),
            message,
        )

    def test_key_rotation(self):
        manager = KeyManager()

        first = manager.create_key()
        second = manager.rotate_key()

        self.assertNotEqual(first, second)
        self.assertEqual(
            manager.get_key(first).status,
            KeyStatus.RETIRED,
        )
        self.assertEqual(
            manager.get_active_key().key_id,
            second,
        )


if __name__ == "__main__":
    demonstrate_encryption()

    print("\n=== AUTOMATED VALIDATION ===")
    unittest.main(argv=["encryption_fundamentals.py"], exit=False)
