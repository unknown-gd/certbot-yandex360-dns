import pytest
from certbot import errors

from certbot_dns_yandex360.authenticator import Yandex360DNSAuthenticator


class DummyHelper:
    """Mock helper that records delete_txt_record calls."""

    def __init__(self):
        self.delete_calls = []

    def find_zone(self, fqdn):
        return "example.com"

    def delete_txt_record(self, *, domain: str, name: str, value: str | None = None):
        self.delete_calls.append((domain, name, value))


@pytest.fixture
def authenticator(config):
    auth = Yandex360DNSAuthenticator(config=config, name="dns-yandex360")
    dummy = DummyHelper()
    auth.yandex360_helper = dummy
    return auth, dummy


def test_cleanup_removes_correct_txt_record(authenticator):
    auth, dummy = authenticator

    auth._cleanup("example.com", "_acme-challenge.sub.example.com.", "abcdef123456")

    assert len(dummy.delete_calls) == 1
    domain, name, value = dummy.delete_calls[0]
    assert domain == "example.com"
    assert name == "_acme-challenge.sub"
    assert value == "abcdef123456"


def test_perform_without_zone_raises_plugin_error(config):
    auth = Yandex360DNSAuthenticator(config=config, name="dns-yandex360")

    class NoZoneHelper:
        def find_zone(self, fqdn):
            return None

    auth.yandex360_helper = NoZoneHelper()

    with pytest.raises(errors.PluginError, match="No domain for _acme-challenge.example.com"):
        auth._perform("example.com", "_acme-challenge.example.com.", "token")
