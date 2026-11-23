# Certbot DNS Plugin for Yandex 360

Native Certbot DNS-01 authenticator for domains managed in
[Yandex 360](https://360.yandex.ru) via the
[Directory DNS API](https://yandex.ru/dev/api360/doc/ref/DomainDNSService/).

## Installation

The plugin must be installed into the **same Python environment** that runs
`certbot`. Pick the matching path below.

### 1. Install Certbot

Official pip-based install (recommended for third-party DNS plugins):

```bash
sudo python3 -m venv /opt/certbot
sudo /opt/certbot/bin/pip install --upgrade pip
sudo /opt/certbot/bin/pip install certbot
sudo ln -sf /opt/certbot/bin/certbot /usr/local/bin/certbot
```

Confirm Certbot works:

```bash
certbot --version
```

If you already installed Certbot another way, find its Python and use that for
the plugin install:

```bash
# example: snap
which certbot
# or: readlink -f "$(which certbot)"
```

Snap Certbot isolates plugins; this package is not published as a snap yet, so
prefer the `/opt/certbot` venv above (or any other shared venv) for this plugin.

### 2. Install the plugin

#### From PyPI (when published)

With pip into the Certbot venv:

```bash
sudo /opt/certbot/bin/pip install certbot-dns-yandex360
```

With [uv](https://docs.astral.sh/uv/) into the same venv:

```bash
sudo uv pip install --python /opt/certbot/bin/python certbot-dns-yandex360
```

#### From a local checkout

```bash
git clone <this-repo-url> certbot-yandex360-dns
cd certbot-yandex360-dns
```

pip:

```bash
sudo /opt/certbot/bin/pip install .
# editable (dev):
sudo /opt/certbot/bin/pip install -e .
```

uv:

```bash
sudo uv pip install --python /opt/certbot/bin/python .
# editable (dev):
sudo uv pip install --python /opt/certbot/bin/python -e .
```

#### From Git (no local clone)

```bash
sudo /opt/certbot/bin/pip install "git+https://github.com/<owner>/certbot-yandex360-dns.git"
# or
sudo uv pip install --python /opt/certbot/bin/python \
  "git+https://github.com/<owner>/certbot-yandex360-dns.git"
```

### 3. Verify the plugin

```bash
certbot plugins
```

You should see `dns-yandex360` with interface `Authenticator`. Example:

```text
* dns-yandex360
Description: Obtain certificates using a DNS TXT record (Yandex 360 DNS API).
Interfaces: Authenticator, Plugin
Entry point: EntryPoint(name='dns-yandex360',
value='certbot_dns_yandex360.authenticator:Yandex360DNSAuthenticator',
group='certbot.plugins')
```

If it is missing, Certbot is almost always using a different Python than the one
you installed into. Re-run the install with that interpreter:

```bash
# discover which python certbot uses
head -1 "$(which certbot)"   # #!/opt/certbot/bin/python
sudo uv pip install --python /opt/certbot/bin/python -e .
```

## Credentials

Create `/etc/letsencrypt/yandex360.ini`:

```ini
# Yandex 360 OAuth token (directory:manage_dns and related scopes)
dns_yandex360_oauth_token = y0_...
# Yandex 360 organization ID
dns_yandex360_org_id = 1234567
```

```bash
sudo chmod 600 /etc/letsencrypt/yandex360.ini
```

Override the path with `--dns-yandex360-credentials /path/to/file.ini`.

### 1. Create an OAuth app

1. Open <https://oauth.yandex.ru/client/new>.
2. Choose **Веб-сервисы** / Web services.
3. Use the debug redirect URI `https://oauth.yandex.ru/verification_code`.
4. Under data access, add at least:
   - `directory:read_organization`
   - `directory:read_domains`
   - `directory:manage_dns`
   - `directory:write_domains`
5. Create the app and copy the **ClientID**.

### 2. Get an OAuth token

Sign in as an administrator of the Yandex 360 organization, then open:

```
https://oauth.yandex.ru/authorize?response_type=token&client_id=<ClientID>
```

Allow access and save the token (`y0_...`) as `oauth_token`.

### 3. Find the organization ID

In <https://admin.yandex.ru>, open the organization profile. The numeric **ID** is
`org_id`.

### 4. Check the credentials

```bash
curl -H "Authorization: OAuth $YANDEX360_OAUTH_TOKEN" \
  "https://api360.yandex.net/directory/v1/org/$YANDEX360_ORG_ID/domains"
```

A JSON body with `"domains": [...]` means the token and org ID work.

## Usage

Issue a certificate once:

```bash
certbot certonly --agree-tos \
  --authenticator dns-yandex360 \
  -d '*.example.com' \
  -d example.com
```

With an explicit credentials file:

```bash
certbot certonly --agree-tos \
  --authenticator dns-yandex360 \
  --dns-yandex360-credentials /path/to/yandex360.ini \
  -d '*.example.com'
```

`certonly` does **not** keep renewing by itself. Certbot writes renewal settings
under `/etc/letsencrypt/renewal/`; a scheduled job must run `certbot renew`.

### Keep certificates renewed

1. Confirm a dry run works with this plugin:

```bash
sudo certbot renew --dry-run
```

2. Schedule `certbot renew` if nothing is already running it:

```bash
systemctl list-timers 'certbot*'   # systemd
ls /etc/cron.*/*certbot* 2>/dev/null   # cron
```

**systemd** (typical for a `/opt/certbot` install):

```bash
sudo tee /etc/systemd/system/certbot-renew.service >/dev/null <<'EOF'
[Unit]
Description=Certbot renew

[Service]
Type=oneshot
ExecStart=/opt/certbot/bin/certbot renew --quiet
EOF

sudo tee /etc/systemd/system/certbot-renew.timer >/dev/null <<'EOF'
[Unit]
Description=Run Certbot renew twice daily

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now certbot-renew.timer
sudo systemctl list-timers certbot-renew.timer
```

**cron** alternative:

```bash
echo "0 0,12 * * * root /opt/certbot/bin/certbot renew --quiet" \
  | sudo tee /etc/cron.d/certbot
```

Adjust `/opt/certbot/bin/certbot` if Certbot lives elsewhere (`which certbot`).

For renewals to succeed, keep the plugin installed in Certbot’s Python env and
leave the credentials file in place (default `/etc/letsencrypt/yandex360.ini`).

The plugin lists domains in the organization and uses the most specific domain
that matches the challenge name, so subdomain zones work.

## Options

| Command line                              | Credentials file                          | Default |
| ----------------------------------------- | ----------------------------------------- | ------- |
| `--dns-yandex360-propagation-seconds 180` | `dns_yandex360_propagation_seconds = 180` | `600`   |
| `--dns-yandex360-follow-cname`            | `dns_yandex360_follow_cname = true`       | off     |

A value on the command line (or in Certbot's `cli.ini`) wins over the
credentials file. Command-line values are stored for renewal; credentials-file
values are re-read on every run.

### Propagation seconds

Seconds to wait after creating the TXT record before Let's Encrypt checks it.
Yandex 360 can be slow; raise this if validation fails with
`No TXT record found`.

### Follow CNAME

When enabled, the plugin resolves `_acme-challenge.<domain>` and creates the
TXT record in the zone the CNAME points to. That lets you keep the OAuth token
away from the main zone by delegating challenges to a dedicated ACME zone.

## Development

With pip:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

With uv:

```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest
uv run certbot plugins
```
