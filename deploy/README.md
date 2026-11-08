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

Public access requires a separate authenticated HTTPS entry point and corresponding trusted-origin support. Do not expose this private dashboard by stripping its Host/Origin checks or forwarding it anonymously.

Update by creating a new release directory and virtual environment, verifying it, switching `current`, and restarting `autolex`. Keep the old release for rollback. Persistent runs and credentials live outside releases. Do not restart the service during an active workflow; finish the run first or inspect its saved state before resuming.
