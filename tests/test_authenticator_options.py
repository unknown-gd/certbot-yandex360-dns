import argparse
from unittest.mock import MagicMock

import dns.name
import dns.resolver
import pytest
from certbot import errors

import certbot_dns_yandex360.authenticator as mod
from certbot_dns_yandex360.authenticator import Yandex360DNSAuthenticator, resolve_cname
from certbot_dns_yandex360.yandex360_helper import Yandex360Helper


class DummyHelper(Yandex360Helper):
    """Helper for orgs with example.com and acme-zone.eu that records add/delete calls."""

    def __init__(self, *args, **kwargs):
        self._domains = ["example.com", "acme-zone.eu"]
        self.add_calls = []
        self.delete_calls = []

    def list_domains(self):
        return list(self._domains)

    def add_txt_record(self, *, domain, name, value, ttl):
        self.add_calls.append((domain, name))

    def delete_txt_record(self, *, domain, name, value=None):
        self.delete_calls.append((domain, name))


@pytest.fixture
def credentials_file(tmp_path):
    def write(*lines):
        path = tmp_path / "yandex360.ini"
        path.write_text(
            "\n".join(
                [
                    "dns_yandex360_oauth_token = token",
                    "dns_yandex360_org_id = 42",
                    *lines,
                ]
            )
            + "\n"
        )
        path.chmod(0o600)
        return str(path)

    return write


@pytest.fixture
def make_authenticator(make_config, credentials_file, monkeypatch):
    monkeypatch.setattr(mod, "Yandex360Helper", DummyHelper)

    def make(*lines, set_by_user=(), **values):
        config = make_config(
            set_by_user,
            dns_yandex360_credentials=credentials_file(*lines),
            **values,
        )
        auth = Yandex360DNSAuthenticator(config=config, name="dns-yandex360")
        auth._setup_credentials()
        return auth

    return make


def test_parser_defaults_and_flag():
    parser = argparse.ArgumentParser()
    Yandex360DNSAuthenticator.inject_parser_options(parser, "dns-yandex360")

    defaults = parser.parse_args([])
    assert defaults.dns_yandex360_propagation_seconds == 600
    assert defaults.dns_yandex360_follow_cname is False

    given = parser.parse_args(
        [
            "--dns-yandex360-propagation-seconds",
            "90",
            "--dns-yandex360-follow-cname",
        ]
    )
    assert given.dns_yandex360_propagation_seconds == 90
    assert given.dns_yandex360_follow_cname is True


def test_defaults_without_credentials_file_options(make_authenticator):
    auth = make_authenticator()
    assert auth.conf("propagation-seconds") == 600
    assert auth.conf("follow-cname") is False


def test_credentials_file_overrides_defaults(make_authenticator):
    auth = make_authenticator(
        "dns_yandex360_propagation_seconds = 180",
        "dns_yandex360_follow_cname = yes",
    )
    assert auth.conf("propagation-seconds") == 180
    assert auth.conf("follow-cname") is True


def test_command_line_wins_over_credentials_file(make_authenticator):
    auth = make_authenticator(
        "dns_yandex360_propagation_seconds = 180",
        set_by_user={"dns_yandex360_propagation_seconds"},
        dns_yandex360_propagation_seconds=45,
    )
    assert auth.conf("propagation-seconds") == 45


@pytest.mark.parametrize(
    "line",
    [
        "dns_yandex360_propagation_seconds = soon",
        "dns_yandex360_follow_cname = maybe",
    ],
)
def test_invalid_value_in_credentials_file(make_authenticator, line):
    auth = make_authenticator(line)
    option = line.split()[0].removeprefix("dns_yandex360_").replace("_", "-")
    with pytest.raises(errors.PluginError, match="Invalid value"):
        auth.conf(option)


def test_perform_waits_propagation_seconds_from_credentials_file(make_authenticator, monkeypatch):
    auth = make_authenticator("dns_yandex360_propagation_seconds = 180")
    sleeps = MagicMock()
    monkeypatch.setattr(mod.dns_common, "sleep", sleeps)
    monkeypatch.setattr(mod.dns_common.display_util, "notify", MagicMock())
    achall = MagicMock()
    achall.identifier.value = "example.com"
    achall.validation_domain_name.return_value = "_acme-challenge.example.com"
    achall.validation.return_value = "token"

    auth.perform([achall])

    sleeps.assert_called_once_with(180)


def test_follow_cname_writes_into_target_zone(make_authenticator, monkeypatch):
    auth = make_authenticator("dns_yandex360_follow_cname = true")
    monkeypatch.setattr(mod, "resolve_cname", lambda name: "dev-tt.acme-zone.eu")

    auth._perform("dev.example.com", "_acme-challenge.dev.example.com.", "token")
    auth._cleanup("dev.example.com", "_acme-challenge.dev.example.com.", "token")

    assert auth.yandex360_helper.add_calls == [("acme-zone.eu", "dev-tt")]
    assert auth.yandex360_helper.delete_calls == [("acme-zone.eu", "dev-tt")]


def test_cname_is_not_resolved_by_default(make_authenticator, monkeypatch):
    auth = make_authenticator()
    monkeypatch.setattr(mod, "resolve_cname", MagicMock(side_effect=AssertionError("must not resolve")))

    auth._perform("dev.example.com", "_acme-challenge.dev.example.com.", "token")

    assert auth.yandex360_helper.add_calls == [("example.com", "_acme-challenge.dev")]


def test_resolve_cname_returns_name_without_trailing_dot(monkeypatch):
    monkeypatch.setattr(
        dns.resolver,
        "canonical_name",
        lambda name: dns.name.from_text("dev-tt.acme-zone.eu."),
    )
    assert resolve_cname("_acme-challenge.dev.example.com.") == "dev-tt.acme-zone.eu"


def test_resolve_cname_failure_raises_plugin_error(monkeypatch):
    def fail(name):
        raise dns.resolver.NoNameservers()

    monkeypatch.setattr(dns.resolver, "canonical_name", fail)

    with pytest.raises(errors.PluginError, match="Could not resolve CNAME"):
        resolve_cname("_acme-challenge.dev.example.com.")
