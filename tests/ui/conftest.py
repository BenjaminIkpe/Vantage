"""Playwright fixtures for the Vantage UI tests.

Tests need a running stack (`docker compose up`). Each test gets a fresh browser context
(isolated cookies) so signing in as `sales` in one test can't leak to a `support` test.
"""
import os
import pytest
from playwright.sync_api import Page, BrowserContext, Browser


BASE_URL = os.environ.get("VANTAGE_URL", "http://localhost:8000")
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")

USERS = {
    "sales":   ("sales",        "sales",   "sales_user"),
    "support": ("support",      "support", "support_user"),
    "admin":   ("admin-user",   "admin",   "admin"),
}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Inject a base viewport + ignore HTTPS errors (we're on http://localhost)."""
    return {
        **browser_context_args,
        "viewport": {"width": 1400, "height": 900},
        "ignore_https_errors": True,
    }


@pytest.fixture
def base_url():
    return BASE_URL


@pytest.fixture
def signed_in_page(page: Page, request):
    """Sign in as the role specified via @pytest.mark.role("sales|support|admin")."""
    marker = request.node.get_closest_marker("role")
    role = marker.args[0] if marker else "support"
    from helpers import sign_in_as
    sign_in_as(page, role)
    return page


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "role(name): which seeded role to sign in as for `signed_in_page`"
    )
