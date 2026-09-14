# Task Analyzer Server deployment and private access

This guide describes how the Task Analyzer Server is installed on the
dedicated Ubuntu host, how its database is initialized once, and how the
desktop reaches it privately through Tailscale. It follows the approved
[1A Design](../../../.specs/features/persistent-task-creation-editing/design.md)
and the runtime constraints in [AGENTS.md](../../../AGENTS.md).

## Authorization

**Nothing in this document has been executed.** No host was contacted, no
interpreter inspected, no account created, no database initialized, and no
tailnet rule configured. The guide is a written procedure, not a record of
work performed.

The target is the user's own Ubuntu server, not a disposable validation
host. That has three consequences:

- Every install, service, and Tailscale step below requires explicit
  authorization **at the time it is run**. Approval of the feature, this
  document, or the task plan does not authorize any of them.
- The first `initialize_database` call is authorized **separately** from
  the deployment itself.
- Existing state is backed up **before** that first initialization.

Writing or reviewing this guide satisfies no acceptance criterion that
requires evidence from the host.

## Values to confirm before deployment

These are unknown in the environment that produced this repository. Each
must be supplied and confirmed in an authorized session before the step
that needs it runs.

| Value | Used by | Status |
| --- | --- | --- |
| Installed interpreter and version set on the target | Dependency locks, service `ExecStart` | Not confirmed |
| Installation path (assumed `/opt/task-analyzer`) | Service unit, install steps | Not confirmed |
| State directory and database path (assumed `/var/lib/task-analyzer/task-analyzer.sqlite3`) | Service environment, initialization | Not confirmed |
| Tailnet device name for this server | Tailscale Serve, desktop configuration | Not confirmed |
| Authorized desktop device identifiers | Tailnet access policy | Not confirmed |

## Target interpreter checkpoint

[`requirements/README.md`](../../../requirements/README.md) records that the
hash-pinned locks were generated on Windows 11 / AMD64 / CPython 3.13.2.
They claim no cross-platform validation.

Before the service is considered deployable:

1. Confirm the interpreter actually installed on Ubuntu Server 26.04.1 LTS
   satisfies the approved `>=3.13` baseline.
2. Re-check the locked dependency set against that interpreter, producing a
   target-specific lock from the same `.in` inputs.
3. Run the same quality gates on that environment.

A local lock is not evidence of target compatibility. If a dependency
cannot satisfy the Python 3.13 baseline on the target, that returns to
Design as a revision proposal; the baseline is not lowered or raised to
accommodate a package.

## Installation

Run as an administrator on the target host, after authorization.

Create the dedicated unprivileged account and the installation directory:

```
sudo adduser --system --group --no-create-home --home /opt/task-analyzer task-analyzer
sudo install -d -o root -g root -m 0755 /opt/task-analyzer
```

Install the application and its locked dependencies into a virtual
environment that the service account can read but not write:

```
sudo python3.13 -m venv /opt/task-analyzer/venv
sudo /opt/task-analyzer/venv/bin/python -m pip install --require-hashes -r requirements/server-py313.txt
sudo /opt/task-analyzer/venv/bin/python -m pip install --no-deps dist/task_analyzer_server-<version>-py3-none-any.whl
sudo /opt/task-analyzer/venv/bin/python -m pip check
```

Use the target-specific lock produced by the checkpoint above, not the
Windows lock committed here. The wheel is built with
`python -m build --no-isolation` using the locked build backend.

## One-time database initialization

**This step is authorized separately from the deployment.** Back up any
existing state first.

The application never creates, migrates, or repairs a database. It opens
the configured file in existing-file mode and fails visibly if the file is
absent or incompatible. Initialization is therefore explicit and happens
exactly once:

```
sudo -u task-analyzer /opt/task-analyzer/venv/bin/python -c \
  "from pathlib import Path; from task_analyzer_server.schema import initialize_database; initialize_database(Path('/var/lib/task-analyzer/task-analyzer.sqlite3'))"
```

The state directory is created and owned by systemd through
`StateDirectory=task-analyzer` when the service first starts; create it
beforehand if initialization runs first.

A newly initialized database legitimately has no product time zone yet.
The configuration endpoints remain usable, and the desktop completes that
one-time setup before task operations are enabled.

## Service installation

Install [`task-analyzer-server.service`](task-analyzer-server.service) to
`/etc/systemd/system/`, then:

```
sudo systemctl daemon-reload
sudo systemctl enable --now task-analyzer-server.service
systemctl status task-analyzer-server.service
```

The unit runs one Uvicorn worker bound to `127.0.0.1:8000`, with no
development reload, under the `task-analyzer` account, with the installed
application read-only and only the state directory writable. Adjust the
paths in the unit to the confirmed values before installing it.

Logs are JSON lines on the journal:

```
journalctl -u task-analyzer-server.service -f
```

Task titles, observations, request bodies, and canonical requests are
never logged.

## Private access through Tailscale

The listener stays on loopback. Tailscale Serve is the tailnet-only HTTPS
front end; the port is never published to the local network or the
internet.

```
sudo tailscale serve --bg --https 443 http://127.0.0.1:8000
tailscale serve status
```

Serve's persistent background mode resumes after reboot. Restrict access
to the authorized desktop device through the tailnet access policy, using
the dedicated device name for this server.

The application has no product sign-in and no product accounts. It does
not treat forwarded identity headers as product identity. Privacy comes
from the tailnet boundary, which is why the private-access check is part
of acceptance rather than an optional hardening step.

## Verification checklist

Run on the target, in an authorized session. Record the actual output.

| Check | Evidence |
| --- | --- |
| Interpreter satisfies `>=3.13` | `python --version` on the target |
| Locked dependencies install and agree | `pip install --require-hashes`, then `pip check` |
| Quality gates pass on the target | `ruff format --check`, `ruff check`, `mypy --strict`, `pytest tests/server` |
| Database initialized exactly once | Initialization output; service starts against the existing file |
| Service starts, restarts, and survives reboot | `systemctl status`, a forced restart, and a reboot |
| Configured product zone survives a restart | `GET /v1/configuration` before and after |
| Persisted tasks survive a restart | `GET /v1/tasks` before and after |
| Private access from the authorized desktop | HTTPS request over the tailnet, with no product sign-in |
| Service is unreachable outside the tailnet | Connection attempt from an unauthorized network |

## Completion status

PCE-44 and PCE-45 (runtime and self-hosting) and PCE-46 and PCE-47
(personal collection without product accounts, private Tailscale access)
cannot be closed by local work alone. The absence of product sign-in is
verified locally through the composed application; the private tailnet
path is not.

Local implementation tasks may finish while this checkpoint is open. The
feature does not receive an overall PASS or `Verified` traceability status
until the target-interpreter gates and the required private-access
evidence pass in a later, explicitly authorized verification session.

## Open questions

- Which interpreter and version set does the Ubuntu Server 26.04.1 LTS
  target actually provide, and does the locked dependency set resolve
  against it? Handed over from the dependency task and still open.
- Which tailnet device name and authorized desktop device identifiers
  will this service use?
- Which installation and state paths will the host use, if not the
  assumed `/opt/task-analyzer` and `/var/lib/task-analyzer`?
- When will the authorized deployment session run, and who confirms the
  backup of existing state before the first database initialization?
