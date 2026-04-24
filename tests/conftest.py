"""Pytest configuration for tests."""
import pytest

from src.config import Config


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Reset Config singleton before each test to avoid state leakage."""
    Config.reset()


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--regenerate-fixtures",
        action="store_true",
        default=False,
        help="Regenerate test fixtures even if they exist",
    )