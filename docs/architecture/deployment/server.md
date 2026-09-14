# Server deployment

Target: the user's dedicated Ubuntu Server 26.04.1 LTS host, one Uvicorn worker on loopback and Tailscale Serve for private HTTPS. [Server design](../../../.specs/features/persistent-task-creation-editing/design.md) defines the contracts; [README](../../../README.md) owns local development commands.

## Authorization and prerequisites

This procedure has not been run on the target. Deployment, account/service configuration and real database initialization require explicit authorization. Initialization is a separate step; preserve any existing state first.

Confirm the actual Python interpreter (3.13+), installation/state paths, tailnet hostname and authorized desktop device. uv.lock resolves dependencies across supported environments, but does not prove installation or execution on this host. Run the quality checks on the actual target interpreter before claiming compatibility.

## Installation

Proposed paths: `/opt/task-analyzer` for the read-only installed application and `/var/lib/task-analyzer/task-analyzer.sqlite3` for local state. Adjust the service asset to confirmed values. Use a dedicated unprivileged `task-analyzer` account.

Build the wheel with `uv build`. For deployment, export the locked runtime dependencies and install into the service environment:

```sh
uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file /tmp/task-analyzer-runtime.txt
sudo uv venv --python /path/to/confirmed/python /opt/task-analyzer/venv
sudo uv pip install --python /opt/task-analyzer/venv/bin/python --require-hashes -r /tmp/task-analyzer-runtime.txt
sudo uv pip install --python /opt/task-analyzer/venv/bin/python --no-deps dist/task_analyzer_server-0.1.0-py3-none-any.whl
uv pip check --python /opt/task-analyzer/venv/bin/python
```

`/tmp/task-analyzer-runtime.txt` is generated for this installation, not a second dependency source. Confirm uv availability and grant only the service account's needed read access to installed files.

## One-time initialization and service

After separate database authorization, create the state directory owned by `task-analyzer` (mode 0750), then initialize a new path:

```sh
sudo -u task-analyzer /opt/task-analyzer/venv/bin/python -c "from pathlib import Path; from task_analyzer_server.schema import initialize_database; initialize_database(Path('/var/lib/task-analyzer/task-analyzer.sqlite3'))"
```

The initializer refuses existing paths. Normal startup only opens an existing database and never initializes or migrates one. An unset product zone is configured through the API once the server is running.

Install [task-analyzer-server.service](task-analyzer-server.service) under `/etc/systemd/system/`, then run `systemctl daemon-reload` and `systemctl enable --now task-analyzer-server`. The unit runs one worker, uses a writable state directory and protects the installed application. Inspect JSON-line logs with `journalctl -u task-analyzer-server -f`.

## Private access and acceptance

Configure Tailscale Serve after authorization:

```sh
sudo tailscale serve --bg --https 443 http://127.0.0.1:8000
tailscale serve status
```

Restrict the tailnet policy to the authorized desktop. No product sign-in or forwarded-header account is added. The API port stays on loopback; do not publish it directly.

Record actual evidence for: interpreter/locked dependency compatibility; installed startup, restart and reboot; retained zone/tasks after restart; access from the authorized desktop; and rejection of unauthorized access. Local tests and these instructions alone do not satisfy PCE-47 or the target-interpreter checkpoint. Physical power-loss durability is not established by process-restart tests.

## Open questions

Actual interpreter, paths, hostname/device policy and timing of the authorized host session remain unknown. No deployment or real database change was performed during simplification.
