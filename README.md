# Certbot DNS Plugin for Yandex 360

Native Certbot DNS-01 authenticator for domains managed in
[Yandex 360](https://360.yandex.ru) via the
[Directory DNS API](https://yandex.ru/dev/api360/doc/ref/DomainDNSService/).

## Installation

If Certbot lives in a virtualenv (for example `/opt/certbot`):

```bash
/opt/certbot/bin/pip install certbot-dns-yandex360
```

From a local checkout:

```bash
pip install .
```

Confirm the plugin is visible:

```bash
certbot plugins
```

You should see `dns-yandex360`.

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

The plugin lists domains in the organization and uses the most specific domain
that matches the challenge name, so subdomain zones work.

## Options

| Command line                               | Credentials file                            | Default |
|--------------------------------------------|---------------------------------------------|---------|
| `--dns-yandex360-propagation-seconds 180`  | `dns_yandex360_propagation_seconds = 180`   | `120`   |
| `--dns-yandex360-follow-cname`             | `dns_yandex360_follow_cname = true`         | off     |

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

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
