import logging

import dns.exception
import dns.resolver
from certbot import errors
from certbot.plugins import dns_common

from certbot_dns_yandex360.yandex360_helper import DEFAULT_TTL, Yandex360Helper

DEFAULT_CREDENTIALS_PATH = "/etc/letsencrypt/yandex360.ini"


def relative_name(fqdn: str, zone_name: str) -> str:
    """Return fqdn relative to zone_name, '@' for the zone apex."""
    return fqdn.rstrip(".").lower()[: -len(zone_name)].rstrip(".") or "@"


def resolve_cname(name: str) -> str:
    """Follow CNAME records of name and return the final target without a trailing dot."""
    try:
        return dns.resolver.canonical_name(name).to_text(omit_final_dot=True)
    except dns.exception.DNSException as e:
        raise errors.PluginError(f"Could not resolve CNAME of {name}: {e}") from e


def parse_bool(value: str) -> bool:
    if value.lower() in ("true", "yes", "on", "1"):
        return True
    if value.lower() in ("false", "no", "off", "0"):
        return False
    raise ValueError(value)


class Yandex360DNSAuthenticator(dns_common.DNSAuthenticator):
    description = "Obtain certificates using a DNS TXT record (Yandex 360 DNS API)."
    ttl = DEFAULT_TTL

    credentials_file_options = {"propagation-seconds": int, "follow-cname": parse_bool}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.yandex360_helper: Yandex360Helper | None = None
        self.credentials: dns_common.CredentialsConfiguration | None = None

    @classmethod
    def add_parser_arguments(cls, add, default_propagation_seconds=120):
        super().add_parser_arguments(add, default_propagation_seconds)
        add(
            "credentials",
            help="Path to Yandex 360 plugin credentials INI file.",
            default=DEFAULT_CREDENTIALS_PATH,
        )
        add(
            "follow-cname",
            action="store_true",
            default=False,
            help=(
                "Follow a CNAME on _acme-challenge.<domain> and create the TXT "
                "record in the zone it points to."
            ),
        )

    def more_info(self) -> str:
        return (
            f"{self.description}\n"
            f"You must provide oauth_token and org_id via a credentials INI file "
            f"(default: {DEFAULT_CREDENTIALS_PATH})."
        )

    def conf(self, var: str):
        parse = self.credentials_file_options.get(var)
        if parse and self.credentials and not self.config.set_by_user(self.dest(var)):
            value = self.credentials.conf(var)
            if value is not None:
                try:
                    return parse(value)
                except ValueError:
                    raise errors.PluginError(
                        f"Invalid value '{value}' for {self.dest(var)} in the credentials file."
                    ) from None
        return super().conf(var)

    def _setup_credentials(self) -> None:
        self.credentials = self._configure_credentials(
            "credentials",
            "Yandex 360 plugin credentials INI file",
            {
                "oauth_token": "Yandex OAuth token with directory:manage_dns",
                "org_id": "Yandex 360 organization ID",
            },
        )
        self.yandex360_helper = Yandex360Helper(
            oauth_token=self.credentials.conf("oauth_token"),
            org_id=self.credentials.conf("org_id"),
        )

    def _zone_and_record(self, validation_name: str) -> tuple[str, str]:
        if self.conf("follow-cname"):
            target = resolve_cname(validation_name)
            if target != validation_name.rstrip("."):
                self.logger.info("Following CNAME %s to %s", validation_name, target)
            validation_name = target

        if not self.yandex360_helper:
            raise errors.PluginError("Yandex 360 helper not initialized.")

        zone = self.yandex360_helper.find_zone(validation_name)
        if zone is None:
            raise errors.PluginError(
                f"No domain for {validation_name.rstrip('.')} in the Yandex 360 organization."
            )
        return zone, relative_name(validation_name, zone)

    def _perform(self, domain: str, validation_name: str, validation: str) -> None:
        if not self.yandex360_helper:
            raise errors.PluginError("Yandex 360 helper not initialized.")

        zone, record_name = self._zone_and_record(validation_name)
        self.logger.info("Adding TXT record %s to domain %s", record_name, zone)
        self.yandex360_helper.add_txt_record(
            domain=zone,
            name=record_name,
            value=validation,
            ttl=self.ttl,
        )

    def _cleanup(self, domain: str, validation_name: str, validation: str) -> None:
        if not self.yandex360_helper:
            return

        zone, record_name = self._zone_and_record(validation_name)
        self.logger.info("Removing TXT record %s from domain %s", record_name, zone)
        self.yandex360_helper.delete_txt_record(
            domain=zone,
            name=record_name,
            value=validation,
        )
