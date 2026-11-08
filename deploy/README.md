# Ubuntu server deployment

The deployment uses these paths:

- `/opt/auto-lexmount/current`: symlink to the deployed source release, with its `.venv`.
- `/opt/auto-lexmount/bin`: official Lexmount browser and webfetch CLIs.
- `/etc/auto-lexmount/env`: private model and Lexmount configuration, mode `0600`.
- `/etc/auto-lexmount/release-profile.json`: private publishing profile, mode `0600`.
- `/var/lib/auto-lexmount`: home directory for the `autolex` service account, browser credentials/cache and persistent `runs/`.
- `autolex.service`: system service; starts after Docker and restarts after failure.

Install Python 3.12 with venv support, Docker, Chromium runtime dependencies and Chinese fonts. Install the project in the release virtual environment. Install Playwright 1.48.0, matching the browser version used in the existing local validation, and Lexmount SDK 0.7.0. Install the matching Playwright Chromium as the service user. Load or pull `python:3.12-slim` for isolated generated-code execution.

Create the `autolex` account with home `/var/lib/auto-lexmount` and membership in the `docker` group. Transfer secrets over SSH separately from Git. Set the CLI paths and publishing profile path in `/etc/auto-lexmount/env`; never place secrets in the repository or a web directory.

Install the unit:

```bash
sudo install -m 644 deploy/autolex.service /etc/systemd/system/autolex.service
sudo systemctl daemon-reload
sudo systemctl enable --now autolex
sudo systemctl status autolex
sudo journalctl -u autolex -n 50 --no-pager
```

The dashboard listens on `127.0.0.1:8766`. From your own computer:

```bash
ssh -N -L 8766:127.0.0.1:8766 ubuntu@39.106.14.223
```

Then open <http://127.0.0.1:8766>. Keep the tunnel running. If that local port is occupied, stop the conflicting local service or choose the same different port on both the server CLI and tunnel; the dashboard checks its exact Host and Origin.

For public access, use the dedicated HTTPS gateway below. Public access is intentionally anonymous at the owner’s request; keep the application’s Host/Origin and mutation-token checks enabled.

Update by creating a new release directory and virtual environment, verifying it, switching `current`, and restarting `autolex`. Keep the old release for rollback. Persistent runs and credentials live outside releases. Do not restart the service during an active workflow; finish the run first or inspect its saved state before resuming.

## Low-memory hosts

On this 1.6 GiB host, existing services left roughly 120–220 MiB available. Importing images with `vm.swappiness=0` produced sustained memory pressure and temporary SSH stalls despite an existing 2 GiB swap file. Deployment set `vm.swappiness=60` in `/etc/sysctl.conf` to use that existing swap; the previous file is backed up at `/etc/auto-lexmount/sysctl.conf.before`. No existing application was stopped. The Auto Lexmount unit separately limits its memory and CPU usage.

After deployment, verify the service and real workflow rather than relying only on `doctor`:

```bash
sudo systemctl is-active autolex
sudo systemctl is-enabled autolex
sudo -u autolex /opt/auto-lexmount/current/.venv/bin/python -m autolex --env-file /etc/auto-lexmount/env doctor
```

The deployed release is recorded by the `current` symlink. Inspect run state in `/var/lib/auto-lexmount/runs/`. Successful deployment tests must not automatically publish or submit test works.

## Public IP access

### Current deployment: public port 8766

When only TCP 8766 is allowed in the cloud security group, use `https://39.106.14.223:8766`. Install `public-port.conf` as `/etc/systemd/system/autolex.service.d/public-port.conf` to move the backend to `127.0.0.1:8767`. Set `AUTOLEX_PUBLIC_ORIGIN=https://39.106.14.223:8766` in `/etc/auto-lexmount/env`, and install `nginx-public-8766.conf` as `/etc/auto-lexmount/nginx.conf`. Restart the backend before reloading the gateway to free port 8766. Neither port 8767 nor any other backend port needs public access.

Without public ACME validation ports or a domain with DNS validation, this setup uses a self-signed certificate at `/etc/auto-lexmount/tls/public-ip.crt` and a private key at `public-ip.key` (root-only, mode 0600). Include `subjectAltName=IP:39.106.14.223` when creating the certificate. Browsers display an untrusted-certificate warning; this is not a publicly trusted certificate. Record its SHA-256 fingerprint and expiry with the deployment evidence. Keep the certificate renewal timer disabled for this setup; replacing the certificate with a trusted one requires the validation setup below or a domain with DNS validation.

The gateway encrypts traffic and opens the dashboard directly without an account or password. Plain HTTP requests to port 8766 redirect to HTTPS. Anonymous page/API requests return 200 without a login challenge; workflow actions still require the normal same-origin mutation token obtained by the frontend. Verify anonymous access, a demo run, artifact downloads, and cross-origin rejection through the actual public IP. For a private SSH fallback with this layout, use `ssh -N -L 8767:127.0.0.1:8767 ubuntu@39.106.14.223` and open `http://127.0.0.1:8767`.

### Optional upgrade: standard ports and trusted certificate

The standard-port public address is `https://39.106.14.223`. For this layout remove the `public-port.conf` systemd override, return the backend to loopback port 8766, and set `AUTOLEX_PUBLIC_ORIGIN=https://39.106.14.223` in `/etc/auto-lexmount/env`. The setting explicitly permits this Host and HTTPS Origin while retaining the mutation token check. It is an origin allowlist, **not authentication**; the public dashboard intentionally has no login gate. Stop the 8766 gateway before switching the backend port, then restart it with the standard-port configuration.

Allow inbound TCP 80 and 443 in the Alibaba Cloud security group (source `0.0.0.0/0`). Port 80 serves ACME certificate validation and redirects other requests to HTTPS; do not open the backend port. If local HTTP works but an external connection times out, inspect the security group and cloud firewall before changing the application.

Use a separate nginx instance (`autolex-gateway.service`), configured by `/etc/auto-lexmount/nginx.conf`, so the existing host nginx sites are not loaded or modified. Its final configuration is `nginx-public.conf`. Before obtaining a certificate, run an HTTP-only bootstrap configuration serving `/.well-known/acme-challenge/` from `/var/lib/autolex-acme`, with other routes returning 503. Do not install the final TLS configuration until the certificate exists.

Install Certbot in `/opt/autolex-certbot`, with version 5.4 or newer. Request an IP certificate using the [official Certbot instructions](https://letsencrypt.org/2026/03/11/shorter-certs-certbot/):

```bash
sudo /opt/autolex-certbot/bin/certbot certonly --non-interactive \
  --agree-tos --register-unsafely-without-email \
  --preferred-profile shortlived --webroot -w /var/lib/autolex-acme \
  --ip-address 39.106.14.223 --cert-name autolex-ip
```

Install `nginx-public.conf`, validate with `sudo nginx -t -c /etc/auto-lexmount/nginx.conf`, and reload `autolex-gateway`.

IP certificates are short lived, so install and enable `autolex-cert-renew.timer` and its matching service. They check twice daily and reload only this gateway after renewal. Validate renewal with `sudo /opt/autolex-certbot/bin/certbot renew --cert-name autolex-ip --dry-run`.

Verify from outside the server: HTTP redirects to HTTPS, anonymous HTTPS opens the dashboard with no `WWW-Authenticate` challenge, cross-origin requests fail, and a demo reaches a downloadable package without credentials. Never call deployment complete based only on a local request. To remove public access, stop/disable `autolex-gateway` and `autolex-cert-renew.timer`; the backend and SSH tunnel continue working.
