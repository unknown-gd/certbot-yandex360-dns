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

Use `pvenode` so the files are written with permissions `pveproxy` can read
(`www-data`, mode `640`). A key mode of `600` makes `pveproxy` fail to start,
and the browser then reports connection refused on port 8006.

```bash
sudo pvenode cert set \
  /etc/letsencrypt/live/pve.example.com/fullchain.pem \
  /etc/letsencrypt/live/pve.example.com/privkey.pem \
  --force 1 --restart 1
```

That copies the chain to `/etc/pve/local/pveproxy-ssl.pem` and the key to
`/etc/pve/local/pveproxy-ssl.key`. Those filenames are fixed. The Certificates
page keeps showing `pve-ssl.pem` as well: that is the cluster node certificate
and must stay. The web UI uses `pveproxy-ssl.pem` when that file is present.

Open the name that is on the certificate, on port **8006**:

```bash
https://pve.example.com:8006
```

`pveproxy` always listens on 8006. To open the UI on 443, use the nginx proxy
in [Optional: serve the UI on port 443](#optional-serve-the-ui-on-port-443).

Check what is actually installed:

```bash
sudo pvenode cert info
sudo openssl x509 -in /etc/pve/local/pveproxy-ssl.pem -noout -subject -ext subjectAltName
sudo systemctl status pveproxy
```

If the UI is already unreachable, remove the custom files and start `pveproxy`
again (this brings back the local `pve-ssl` certificate), then run `pvenode cert set`:

```bash
sudo pvenode cert delete --restart 1
# or, if pvenode itself cannot be reached:
sudo rm -f /etc/pve/local/pveproxy-ssl.pem /etc/pve/local/pveproxy-ssl.key
sudo systemctl restart pveproxy
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

pvenode cert set \
  "${RENEWED_LINEAGE}/fullchain.pem" \
  "${RENEWED_LINEAGE}/privkey.pem" \
  --force 1 --restart 1
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

## Optional: serve the UI on port 443

`pveproxy` cannot change its port. `/etc/default/pveproxy` only sets the listen
address and the access list. To answer on **443**, run nginx on the node and
proxy to `https://127.0.0.1:8006`. Leave 8006 open: in a cluster the other
nodes still talk to `pveproxy` on that port.

```bash
sudo apt install nginx
sudo rm -f /etc/nginx/sites-enabled/default
```

`/etc/nginx/sites-available/pveproxy`:

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name pve.example.com;

    ssl_certificate     /etc/pve/local/pveproxy-ssl.pem;
    ssl_certificate_key /etc/pve/local/pveproxy-ssl.key;

    location / {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_pass https://127.0.0.1:8006;
        proxy_buffering off;
        client_max_body_size 0;
        proxy_connect_timeout 3600s;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        send_timeout 3600s;
    }
}
```

`Upgrade` is required for the noVNC console. Point nginx at
`pveproxy-ssl.pem` / `pveproxy-ssl.key`, the same files `pvenode cert set`
writes. `/etc/pve` is mounted by `pve-cluster`, so nginx has to start after it:

```bash
sudo ln -s /etc/nginx/sites-available/pveproxy /etc/nginx/sites-enabled/pveproxy
sudo systemctl edit nginx
```

```ini
[Unit]
Requires=pve-cluster.service
After=pve-cluster.service
```

```bash
sudo nginx -t && sudo systemctl restart nginx
```

Open `https://pve.example.com`. After a renewal, nginx keeps the old certificate
in memory until it is reloaded. Add this at the end of the deploy hook from
section 3:

```bash
systemctl reload nginx
```

## Cluster notes

- Custom `pveproxy-ssl.*` files are **per node**. Repeat issue + hook on each
  node that should present a public name, or issue a cert that covers every
  node name (`-d pve1.example.com -d pve2.example.com`) and deploy the same
  lineage on each node.
- Keep Proxmox’s built-in ACME disabled for that node if you manage the same
  name with Certbot, so the two systems do not overwrite each other.

## Optional: issue from another host

If Certbot runs off-box, copy `fullchain.pem` and `privkey.pem` onto the node
and install them with `pvenode cert set ... --force 1 --restart 1`. Your deploy
automation must do that after every renewal.
