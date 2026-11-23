from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

DEFAULT_BASE_URL = "https://api360.yandex.net/"
DEFAULT_TTL = 120


class Yandex360Helper:
    """Helper to manage Yandex 360 DNS records for ACME challenges."""

    def __init__(
        self,
        oauth_token: str,
        org_id: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
    ) -> None:
        if not oauth_token:
            raise ValueError("oauth_token is required")
        if not org_id or not str(org_id).isdigit() or int(org_id) <= 0:
            raise ValueError(f"invalid org_id {org_id!r}")

        self.oauth_token = oauth_token
        self.org_id = str(org_id)
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"OAuth {self.oauth_token}",
        }

    def _url(self, *parts: str) -> str:
        path = "/".join(["directory", "v1", "org", self.org_id, *parts])
        return urljoin(self.base_url, path)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        headers = self._headers()
        if json_body is not None:
            headers = {**headers, "Content-Type": "application/json"}
        response = self.session.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=30,
        )
        if not response.ok:
            try:
                payload = response.json()
                message = payload.get("message") or response.text
            except ValueError:
                message = response.text
            raise requests.HTTPError(
                f"{response.status_code} Client Error: {message} for url: {response.url}",
                response=response,
            )
        if not response.content.strip():
            return None
        return response.json()

    def list_domains(self) -> list[str]:
        names: list[str] = []
        page = 1
        while True:
            data = self._request(
                "GET",
                self._url("domains"),
                params={"page": page, "perPage": 10},
            )
            names.extend(domain["name"] for domain in data.get("domains", []))
            pages = int(data.get("pages") or 1)
            if page >= pages or not data.get("domains"):
                return names
            page += 1

    def find_zone(self, fqdn: str) -> str | None:
        """Return the most specific org domain that fqdn belongs to."""
        fqdn = fqdn.rstrip(".").lower()
        matches = [
            name
            for name in self.list_domains()
            if fqdn == name.lower() or fqdn.endswith("." + name.lower())
        ]
        return max(matches, key=len, default=None)

    def list_records(self, domain: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._request(
                "GET",
                self._url("domains", domain, "dns"),
                params={"page": page, "perPage": 100},
            )
            batch = data.get("records") or []
            records.extend(batch)
            pages = int(data.get("pages") or 1)
            if page >= pages or not batch:
                return records
            page += 1

    def add_txt_record(
        self,
        *,
        domain: str,
        name: str,
        value: str,
        ttl: int = DEFAULT_TTL,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            self._url("domains", domain, "dns"),
            json_body={"type": "TXT", "name": name, "text": value, "ttl": ttl},
        )

    def delete_txt_record(
        self,
        *,
        domain: str,
        name: str,
        value: str | None = None,
    ) -> None:
        for record in self.list_records(domain):
            if str(record.get("type", "")).upper() != "TXT":
                continue
            if record.get("name") != name:
                continue
            if value is not None and record.get("text") != value:
                continue
            record_id = record.get("recordId")
            if record_id is None:
                continue
            self._request("DELETE", self._url("domains", domain, "dns", str(record_id)))
