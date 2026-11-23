import pytest

from certbot_dns_yandex360.authenticator import Yandex360DNSAuthenticator


class DummyHelper:
    """Mock helper that records all add_txt_record calls."""

    def __init__(self):
        self.add_calls = []

    def find_zone(self, fqdn):
        return "example.com"

    def add_txt_record(self, *, domain: str, name: str, value: str, ttl: int):
        assert not value.startswith('"') and not value.endswith('"')
        self.add_calls.append((domain, name, value, ttl))


@pytest.fixture
def authenticator(config):
    auth = Yandex360DNSAuthenticator(config=config, name="dns-yandex360")
    dummy = DummyHelper()
    auth.yandex360_helper = dummy
    return auth, dummy


def test_perform_creates_expected_txt_record(authenticator):
    auth, dummy = authenticator

    auth._perform("example.com", "_acme-challenge.sub.example.com.", "abcdef123456")

    assert len(dummy.add_calls) == 1
    domain, name, value, ttl = dummy.add_calls[0]
    assert domain == "example.com"
    assert name == "_acme-challenge.sub"
    assert value == "abcdef123456"
    assert ttl == 120
