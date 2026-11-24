# Use Certbot certificates on Proxmox VE

By default Proxmox serves the web UI / API with a node certificate under
`/etc/pve/local/pve-ssl.pem` (cluster CA). Browsers do not trust it.

To use a Let's Encrypt certificate from Certbot (for example with
`dns-yandex360`) instead, install files as **custom pveproxy certificates**.
Do **not** overwrite `pve-ssl.pem` / `pve-ssl.key`.

| Role                         | Path                                      |
|------------------------------|-------------------------------------------|
| Custom cert (full chain)     | `/etc/pve/local/pveproxy-ssl.pem`         |
| Custom private key           | `/etc/pve/local/pveproxy-ssl.key`         |
| Certbot lineage (example)    | `/etc/letsencrypt/live/pve.example.com/`  |

`/etc/pve/local` is a symlink to `/etc/pve/nodes/<NODENAME>` on that node.

Official reference:
[Certificate Management](https://pve.proxmox.com/wiki/Certificate_Management).

## Prerequisites

- Certbot and this plugin installed on the Proxmox node (or on a host that can
  write into `/etc/pve` on that node). See the [README](../README.md).
- Credentials file for Yandex 360 (for example `/etc/letsencrypt/yandex360.ini`).
- A DNS name for the node that resolves to it (for example `pve.example.com`).

## 1. Issue the certificate

On the Proxmox node:

```bash
sudo certbot certonly --agree-tos \
  --authenticator dns-yandex360 \
  --dns-yandex360-credentials /etc/letsencrypt/yandex360.ini \
  -d pve.example.com
```

Files land under `/etc/letsencrypt/live/pve.example.com/`.

## 2. Install them for pveproxy

```bash
sudo cp /etc/letsencrypt/live/pve.example.com/fullchain.pem \
  /etc/pve/local/pveproxy-ssl.pem
sudo cp /etc/letsencrypt/live/pve.example.com/privkey.pem \
  /etc/pve/local/pveproxy-ssl.key
sudo chmod 640 /etc/pve/local/pveproxy-ssl.pem
sudo chmod 600 /etc/pve/local/pveproxy-ssl.key
sudo systemctl reload pveproxy
```

Open `https://pve.example.com:8006` — the browser should show the Let's Encrypt
certificate, not the Proxmox local one.

To drop back to the local certificate, remove the custom files and reload:

```bash
sudo rm -f /etc/pve/local/pveproxy-ssl.pem /etc/pve/local/pveproxy-ssl.key
sudo systemctl reload pveproxy
```

## 3. Deploy hook for renewals

Certbot renewals do not update Proxmox until you copy the new files again.
Add a deploy hook so every successful issue/renew installs them automatically.

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/proxmox.sh >/dev/null <<'EOF'
#!/bin/bash
set -euo pipefail

# Only act for the Proxmox hostname lineage (skip other certs on this host).
case "${RENEWED_LINEAGE}" in
  */pve.example.com) ;;
  *) exit 0 ;;
esac

install -m 640 "${RENEWED_LINEAGE}/fullchain.pem" /etc/pve/local/pveproxy-ssl.pem
install -m 600 "${RENEWED_LINEAGE}/privkey.pem" /etc/pve/local/pveproxy-ssl.key
systemctl reload pveproxy
EOF
sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/proxmox.sh
```

Replace `pve.example.com` with your certificate name (the directory under
`/etc/letsencrypt/live/`).

Test:

```bash
sudo certbot renew --dry-run
# Force one renew cycle and run hooks (use sparingly):
# sudo certbot renew --force-renewal
```

Ensure `certbot renew` is scheduled (see the [README](../README.md)).

## Cluster notes

- Custom `pveproxy-ssl.*` files are **per node**. Repeat issue + hook on each
  node that should present a public name, or issue a cert that covers every
  node name (`-d pve1.example.com -d pve2.example.com`) and deploy the same
  lineage on each node.
- Keep Proxmox’s built-in ACME disabled for that node if you manage the same
  name with Certbot, so the two systems do not overwrite each other.

## Optional: issue from another host

If Certbot runs off-box, copy `fullchain.pem` and `privkey.pem` onto the node
into `pveproxy-ssl.pem` / `pveproxy-ssl.key` (same permissions), then
`systemctl reload pveproxy`. Your deploy automation must do that after every
renewal.
