import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from certbot_dns_yandex360.yandex360_helper import Yandex360Helper


class FakeYandex360API(BaseHTTPRequestHandler):
    """In-memory Yandex 360 Directory DNS + Domains API."""

    def log_message(self, format, *args):
        pass

    @property
    def store(self):
        return self.server.store

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return None
        return json.loads(self.rfile.read(length))

    def _write_json(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _unauthorized(self):
        self._write_json(401, {"code": 16, "message": "unauthenticated"})

    def do_GET(self):
        if self.headers.get("Authorization") != "OAuth token":
            return self._unauthorized()

        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        query = parse_qs(parsed.query)

        # GET /directory/v1/org/42/domains
        if parts == ["directory", "v1", "org", "42", "domains"]:
            page = int(query.get("page", ["1"])[0])
            per_page = int(query.get("perPage", ["10"])[0])
            all_domains = [{"name": n, "delegated": True} for n in self.store["domains"]]
            pages = max(1, (len(all_domains) + per_page - 1) // per_page)
            start = (page - 1) * per_page
            end = start + per_page
            return self._write_json(
                200,
                {
                    "domains": all_domains[start:end],
                    "page": page,
                    "pages": pages,
                    "perPage": per_page,
                    "total": len(all_domains),
                },
            )

        # GET /directory/v1/org/42/domains/{domain}/dns
        if (
            len(parts) == 7
            and parts[:5] == ["directory", "v1", "org", "42", "domains"]
            and parts[6] == "dns"
        ):
            domain = parts[5]
            page = int(query.get("page", ["1"])[0])
            per_page = int(query.get("perPage", ["100"])[0])
            all_records = self.store["records"].get(domain, [])
            pages = max(1, (len(all_records) + per_page - 1) // per_page) if all_records else 1
            start = (page - 1) * per_page
            end = start + per_page
            return self._write_json(
                200,
                {
                    "records": all_records[start:end],
                    "page": page,
                    "pages": pages,
                    "perPage": per_page,
                    "total": len(all_records),
                },
            )

        self._write_json(404, {"code": 5, "message": "not found"})

    def do_POST(self):
        if self.headers.get("Authorization") != "OAuth token":
            return self._unauthorized()

        parts = [p for p in urlparse(self.path).path.split("/") if p]
        if (
            len(parts) == 7
            and parts[:5] == ["directory", "v1", "org", "42", "domains"]
            and parts[6] == "dns"
        ):
            domain = parts[5]
            body = self._read_json()
            record = dict(body)
            record["recordId"] = self.store["next_id"]
            self.store["next_id"] += 1
            self.store["records"].setdefault(domain, []).append(record)
            return self._write_json(200, record)

        self._write_json(404, {"code": 5, "message": "not found"})

    def do_DELETE(self):
        if self.headers.get("Authorization") != "OAuth token":
            return self._unauthorized()

        parts = [p for p in urlparse(self.path).path.split("/") if p]
        if (
            len(parts) == 8
            and parts[:5] == ["directory", "v1", "org", "42", "domains"]
            and parts[6] == "dns"
        ):
            domain = parts[5]
            record_id = int(parts[7])
            records = self.store["records"].get(domain, [])
            for i, rec in enumerate(records):
                if rec["recordId"] == record_id:
                    del records[i]
                    return self._write_json(200, {})
            return self._write_json(404, {"code": 5, "message": "not found"})

        self._write_json(404, {"code": 5, "message": "not found"})


@pytest.fixture
def fake_api():
    store = {"domains": ["example.com", "other.com"], "records": {}, "next_id": 1}
    server = HTTPServer(("127.0.0.1", 0), FakeYandex360API)
    server.store = store
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}/"
    yield store, base_url
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture
def helper(fake_api):
    store, base_url = fake_api
    h = Yandex360Helper(oauth_token="token", org_id="42", base_url=base_url)
    return store, h


def test_list_domains_returns_all_pages(helper):
    store, h = helper
    store["domains"] = [f"d{i}.com" for i in range(25)]
    assert h.list_domains() == store["domains"]


def test_add_txt_record_creates_record(helper):
    store, h = helper
    created = h.add_txt_record(domain="example.com", name="_acme-challenge", value="abc123", ttl=120)
    assert created["recordId"] == 1
    assert store["records"]["example.com"] == [
        {"type": "TXT", "name": "_acme-challenge", "text": "abc123", "ttl": 120, "recordId": 1}
    ]


def test_delete_txt_record_removes_matching_value(helper):
    store, h = helper
    store["records"]["example.com"] = [
        {"type": "TXT", "name": "_acme-challenge", "text": "keep", "ttl": 120, "recordId": 10},
        {"type": "TXT", "name": "_acme-challenge", "text": "drop", "ttl": 120, "recordId": 11},
        {"type": "A", "name": "@", "address": "192.0.2.1", "ttl": 3600, "recordId": 12},
    ]
    h.delete_txt_record(domain="example.com", name="_acme-challenge", value="drop")
    remaining = store["records"]["example.com"]
    assert [r["recordId"] for r in remaining] == [10, 12]


def test_delete_txt_record_without_value_removes_all_txt_with_name(helper):
    store, h = helper
    store["records"]["example.com"] = [
        {"type": "TXT", "name": "_acme-challenge", "text": "a", "ttl": 120, "recordId": 1},
        {"type": "TXT", "name": "_acme-challenge", "text": "b", "ttl": 120, "recordId": 2},
        {"type": "TXT", "name": "other", "text": "c", "ttl": 120, "recordId": 3},
    ]
    h.delete_txt_record(domain="example.com", name="_acme-challenge", value=None)
    assert [r["recordId"] for r in store["records"]["example.com"]] == [3]


def test_unauthorized_raises(fake_api):
    _, base_url = fake_api
    h = Yandex360Helper(oauth_token="wrong", org_id="42", base_url=base_url)
    with pytest.raises(requests.HTTPError):
        h.list_domains()
