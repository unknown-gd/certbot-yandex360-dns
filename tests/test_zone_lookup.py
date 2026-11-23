import pytest

from certbot_dns_yandex360.authenticator import relative_name
from certbot_dns_yandex360.yandex360_helper import Yandex360Helper


def helper_with_domains(*names):
    """Yandex360Helper whose org contains the given domains."""
    helper = object.__new__(Yandex360Helper)
    helper.list_domains = lambda: list(names)
    return helper


@pytest.mark.parametrize(
    "fqdn, zone, expected",
    [
        ("_acme-challenge.example.com.", "example.com", "_acme-challenge"),
        ("_acme-challenge.sub.example.com", "example.com", "_acme-challenge.sub"),
        ("_acme-challenge.fenriv.co.ua.", "fenriv.co.ua", "_acme-challenge"),
        ("_acme-challenge.example.com.", "_acme-challenge.example.com", "@"),
    ],
)
def test_relative_name(fqdn, zone, expected):
    assert relative_name(fqdn, zone) == expected


@pytest.mark.parametrize(
    "fqdn, domains, expected",
    [
        ("_acme-challenge.example.com.", ["example.com", "other.com"], "example.com"),
        ("_acme-challenge.sub.example.co.uk", ["example.co.uk"], "example.co.uk"),
        ("_acme-challenge.fenriv.co.ua.", ["fenriv.co.ua"], "fenriv.co.ua"),
        ("_acme-challenge.dev.example.com.", ["example.com", "dev.example.com"], "dev.example.com"),
        (
            "_acme-challenge.example.com.",
            ["example.com", "_acme-challenge.example.com"],
            "_acme-challenge.example.com",
        ),
        ("_acme-challenge.EXAMPLE.com.", ["example.com"], "example.com"),
    ],
)
def test_find_zone(fqdn, domains, expected):
    assert helper_with_domains(*domains).find_zone(fqdn) == expected


@pytest.mark.parametrize(
    "fqdn, domains",
    [
        ("_acme-challenge.example.com.", []),
        ("_acme-challenge.example.com.", ["other.com"]),
        ("_acme-challenge.myexample.com.", ["example.com"]),
    ],
)
def test_find_zone_none(fqdn, domains):
    assert helper_with_domains(*domains).find_zone(fqdn) is None
