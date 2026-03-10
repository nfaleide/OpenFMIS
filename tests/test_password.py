"""Password hashing tests — Argon2id, MD5 detection, legacy migration."""

import hashlib

from openfmis.security.password import (
    hash_password,
    is_legacy_md5,
    needs_rehash,
    verify_password,
)


def test_argon2_hash_and_verify():
    hashed = hash_password("mysecretpassword")
    assert hashed.startswith("$argon2id$")
    assert verify_password("mysecretpassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_md5_detection():
    md5_hash = hashlib.md5(b"test").hexdigest()
    assert is_legacy_md5(md5_hash)
    assert not is_legacy_md5("$argon2id$v=19$m=65536,t=3,p=4$...")
    assert not is_legacy_md5("short")
    assert not is_legacy_md5("")


def test_md5_verify():
    md5_hash = hashlib.md5(b"legacypassword").hexdigest()
    assert verify_password("legacypassword", md5_hash)
    assert not verify_password("wrongpassword", md5_hash)


def test_needs_rehash_md5():
    md5_hash = hashlib.md5(b"test").hexdigest()
    assert needs_rehash(md5_hash)


def test_needs_rehash_argon2():
    fresh_hash = hash_password("test")
    assert not needs_rehash(fresh_hash)


def test_argon2_different_passwords_different_hashes():
    h1 = hash_password("password1")
    h2 = hash_password("password2")
    assert h1 != h2
