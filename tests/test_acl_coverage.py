"""ACL coverage introspection — verify every endpoint requires authentication.

Walks all routes registered on the app and asserts each one either:
(a) has get_current_user or get_superuser in its dependencies, or
(b) is listed in the explicit WHITELIST with a reason.

This is a structural test — it does not hit the database.
"""

import pytest

from openfmis.dependencies import get_current_user, get_superuser
from openfmis.main import create_app

# Endpoints that intentionally do not require auth.
# Format: {("METHOD", "/full/path"): "reason"}
WHITELIST: dict[tuple[str, str], str] = {
    # Auth
    ("POST", "/api/v1/login"): "login endpoint — provides the token",
    ("POST", "/api/v1/refresh"): "token refresh — uses refresh token, not session",
    # Health
    ("GET", "/api/v1/health"): "health check — used by load balancers",
    ("GET", "/api/v1/health/ready"): "readiness probe — no auth needed",
    # Static / root
    ("GET", "/"): "root redirect or static page — no auth",
    # Public boundary data (PLSS/CLU reference data, read-only)
    ("GET", "/api/v1/boundaries/clus/bbox"): "public CLU reference data",
    ("GET", "/api/v1/boundaries/plss/states"): "public PLSS state list",
    ("GET", "/api/v1/boundaries/plss/counties"): "public PLSS county list",
    ("GET", "/api/v1/boundaries/plss/townships/bbox"): "public PLSS township bbox query",
    ("GET", "/api/v1/boundaries/plss/townships/search"): "public PLSS township search",
    ("GET", "/api/v1/boundaries/plss/townships/{township_id}"): "public PLSS township detail",
    ("GET", "/api/v1/boundaries/plss/townships/{township_id}/sections"): "public PLSS sections",
    ("GET", "/api/v1/boundaries/plss/sections/bbox"): "public PLSS section bbox query",
    ("GET", "/api/v1/boundaries/plss/sections/{section_id}"): "public PLSS section detail",
    # Export links — shareable download via hash, no auth
    ("GET", "/api/v1/export/links/{link_hash}"): "shareable export link — auth via hash",
}


def _has_auth_dependency(route) -> bool:
    """Check if a route has get_current_user or get_superuser in its deps."""
    for dep in route.dependant.dependencies:
        call = dep.call
        if call is get_current_user or call is get_superuser:
            return True
        # Check nested — some routes use Annotated[User, Depends(get_current_user)]
        # which shows up as the call itself
        if hasattr(call, "__wrapped__"):
            if call.__wrapped__ is get_current_user or call.__wrapped__ is get_superuser:
                return True
    return False


@pytest.mark.asyncio
async def test_all_endpoints_require_auth():
    """Every endpoint must require authentication or be whitelisted."""
    app = create_app()

    unguarded = []
    for route in app.routes:
        if not hasattr(route, "methods") or not hasattr(route, "dependant"):
            continue  # Skip non-API routes (mounts, etc.)

        for method in route.methods:
            key = (method, route.path)
            if key in WHITELIST:
                continue
            if method == "HEAD":
                continue  # HEAD mirrors GET, skip

            if not _has_auth_dependency(route):
                unguarded.append(f"{method} {route.path}")

    assert unguarded == [], (
        "The following endpoints lack auth dependencies "
        "(add get_current_user/get_superuser or whitelist them):\n"
        + "\n".join(f"  - {e}" for e in sorted(unguarded))
    )


@pytest.mark.asyncio
async def test_whitelist_entries_still_exist():
    """Verify whitelisted endpoints actually exist in the app."""
    app = create_app()

    registered = set()
    for route in app.routes:
        if not hasattr(route, "methods"):
            continue
        for method in route.methods:
            registered.add((method, route.path))

    for key, reason in WHITELIST.items():
        assert key in registered, (
            f"Whitelisted endpoint {key[0]} {key[1]} no longer exists — "
            f"remove from WHITELIST (was: {reason})"
        )
