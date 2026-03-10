"""Password hashing — Argon2id with MD5 legacy migration bridge.

Legacy system stored passwords as bare MD5 hex digests (32 chars).
On login, if the stored hash looks like MD5, we verify via MD5 and
then transparently re-hash to Argon2id.
"""

import hashlib
import re

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_MD5_PATTERN = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash (Argon2id or legacy MD5)."""
    if is_legacy_md5(stored_hash):
        return _verify_md5(password, stored_hash)
    try:
        return _hasher.verify(stored_hash, password)
    except VerifyMismatchError:
        return False


def is_legacy_md5(stored_hash: str) -> bool:
    """Detect whether the stored hash is a legacy MD5 hex digest."""
    return bool(_MD5_PATTERN.match(stored_hash))


def needs_rehash(stored_hash: str) -> bool:
    """True if the hash should be upgraded (MD5 or outdated Argon2 params)."""
    if is_legacy_md5(stored_hash):
        return True
    return _hasher.check_needs_rehash(stored_hash)


def _verify_md5(password: str, md5_hex: str) -> bool:
    """Verify a plaintext password against a legacy MD5 hex digest."""
    return hashlib.md5(password.encode()).hexdigest().lower() == md5_hex.lower()
