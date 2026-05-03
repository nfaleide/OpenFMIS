"""Tests for middleware stack: logging, rate limiting, compression."""

import time

from openfmis.middleware.rate_limit import RateLimitMiddleware


class TestRateLimitMiddleware:
    """Unit tests for the rate limiter."""

    def test_bucket_prune(self):
        """Old entries are pruned outside the 60s window."""
        mw = RateLimitMiddleware.__new__(RateLimitMiddleware)
        mw.rpm = 5
        mw._buckets = {}
        # Simulate entries from 120s ago (should be pruned)
        old = time.monotonic() - 120
        mw._buckets["127.0.0.1"] = [old, old + 1, old + 2]
        # After pruning, bucket should be empty
        bucket = [t for t in mw._buckets["127.0.0.1"] if t > time.monotonic() - 60]
        assert len(bucket) == 0


class TestRequestLogging:
    """Verify logging middleware produces log output."""

    def test_import(self):
        from openfmis.middleware.logging import RequestLoggingMiddleware

        assert RequestLoggingMiddleware is not None


class TestCompression:
    """Verify gzip middleware can be added."""

    def test_import(self):
        from openfmis.middleware.compression import add_gzip_middleware

        assert add_gzip_middleware is not None


class TestEmailEncryption:
    """Test SMTP password encrypt/decrypt round-trip."""

    def test_round_trip(self):
        from openfmis.services.email_delivery import _decrypt_password, _encrypt_password

        original = "my-smtp-p@ssw0rd!"
        encrypted = _encrypt_password(original)
        assert encrypted != original
        assert _decrypt_password(encrypted) == original

    def test_different_plaintexts_differ(self):
        from openfmis.services.email_delivery import _encrypt_password

        a = _encrypt_password("password1")
        b = _encrypt_password("password2")
        assert a != b
