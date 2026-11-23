from types import SimpleNamespace

import pytest


def _make_config(set_by_user=(), **values):
    """Minimal stand-in for Certbot's NamespaceConfig with plugin defaults."""
    defaults = {
        "dns_yandex360_propagation_seconds": 600,
        "dns_yandex360_follow_cname": False,
    }
    return SimpleNamespace(
        **{**defaults, **values},
        set_by_user=lambda var: var in set_by_user,
    )


@pytest.fixture
def make_config():
    return _make_config


@pytest.fixture
def config():
    return _make_config()
