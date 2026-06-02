# oaknut `econet-station` — host program design

**Status:** draft for iteration, created 2026-06-03. Agreed shape; amend in place. Builds on the service-host model in `econet-design.md` §13 and the CLI conventions in `cli-design.md`.

## Purpose

`econet-station` is the **single-station service host**: it attaches one transport, creates a `Station`, loads the configured service plug-ins (each claiming its ports), and runs `Station.serve()` until interrupted. It is *not* a bridge/router (that composes multiple transports — a different program).

The host depends only on `oaknut-econet-station` + core + the CLI layer; it depends on **no specific transport or service**. It discovers whatever plug-ins are installed via the `oaknut.econet.transport` and `oaknut.econet.service` extension axes. Provisioning a deployment is therefore "install the packages you want, then point the host at a config".

## Configuration

A station deployment *is* configuration — an address, a transport endpoint (AUN peer map / serial port / device path), and a list of services with their settings. It lives in **TOML** (parsed with stdlib `tomllib`; no dependency), in one of two interchangeable locations with the **same schema**:

- a standalone file (`econet-station.toml`, `/etc/oaknut/...`, or any `--config PATH`), with the schema at the top level; or
- a `[tool.econet-station]` table inside a **deployment project's** `pyproject.toml` (the ruff/pytest convention), with the schema nested under that table.

**Rule:** `[tool.econet-station]` belongs only in a *deployer's* project `pyproject.toml` — **never** in oaknut's own library package manifests. Runtime config (station numbers, peer IPs, file-server roots, any future secret) is not packaging metadata and must not ship inside a published package.

**Discovery order** (first match wins; no merging — we learned from the stale `ruff.toml`):

1. an explicit `--config PATH`;
2. `[tool.econet-station]` in a `pyproject.toml` found in the cwd or an ancestor;
3. a conventional `econet-station.toml` in the cwd;
4. the flag-only quick path (no file).

`validate` (and `run` at startup) reports **which source** was used, so there is never ambiguity about which file won.

### Schema

```toml
[station]
address   = "0.254"          # net.station — this host's Econet identity
transport = "aun"            # the transport plug-in to attach

[transport]                  # handed to the named transport plug-in's from_config
listen = "0.0.0.0:32768"
peers  = [
    { address = "0.1",   endpoint = "192.168.1.50:32768" },
    { address = "0.235", endpoint = "192.168.1.60:32768" },
]

[[service]]                  # services to host; each claims its own port(s)
name = "kvstore"

[[service]]
name = "fileserver"
root = "/srv/econet/disc0.ssd"
read-only = true
```

Ports are **not** in the config: a service declares its own ports (`KvServer` → `&B0`, a file server → `&99`…). The host registers them and **fails fast** on a clash, printing the resulting port map. (Under `pyproject.toml` the tables are prefixed, e.g. `[tool.econet-station.station]`, `[[tool.econet-station.service]]`.)

## Plug-in configuration: the `from_config` convention

Structured config (an AUN peer map; a Piconet serial port that must become a `SerialPicoLink`) does not reduce to plain `**kwargs`, so each plug-in interprets its own config via a classmethod:

- transports: `EconetTransport.from_config(cls, *, name, address, config) -> EconetTransport`
- services: `Service.from_config(cls, *, name, config) -> Service`

The ABC provides a sensible default for flat config:

- transport default: `cls(name=name, local_station=address, **config)`
- service default: `cls(name=name, **config)`

Plug-ins with structured config override it: `AunTransport` parses `listen`/`peers`; `PiconetTransport` turns a serial `port` into a `SerialPicoLink`; `HatTransport` turns a `device` path into an `EconetGpioDevice`. The host stays generic — it loads the plug-in *class* by name and calls `from_config`.

## CLI surface (Click, consistent with `disc`)

```
econet-station run        [--config PATH]   # the daemon; graceful shutdown on SIGINT/SIGTERM
econet-station validate   [--config PATH]   # parse + build + print the plan and config source; exit
econet-station list-transports              # discover installed transport plug-ins
econet-station list-services                # discover installed service plug-ins
econet-station describe   <name>            # a plug-in's description (Extension.describe())
```

Flag-only quick path for the trivial, config-less case (demos, the KV walking skeleton):

```
econet-station run --transport aun --station 0.254 --service kvstore
```

The CLI boundary uses `oaknut-exception`'s `handled_errors`, so a bad config / unknown plug-in / port clash is a clean `ConfigurationError` with the right exit code, not a traceback.

## Lifecycle

`run` opens the transport, starts `Station.serve()`, and waits. On SIGINT/SIGTERM it stops accepting, drains in-flight handler tasks, and closes the transport. Exit codes follow the `oaknut.exception` `ExitCode` scheme.

## Packaging

A `econet-station` console script shipped from `oaknut-econet-station`, with Click behind a `[cli]` extra so the *library* still imports without Click. The host does not depend on any transport/service distribution — those are discovered at runtime from installed entry points.

## Recommended deployment: a uv project

The neat path is to treat a deployment as a uv project — one `pyproject.toml` that is both the bill of materials and the wiring:

```toml
[project]
name = "my-econet-fileserver"
dependencies = ["oaknut-econet-station", "oaknut-econet-aun", "oaknut-econet-kvstore"]

[tool.econet-station.station]
address = "0.254"
transport = "aun"
# ... transport + service tables ...
```

Then `uv sync && econet-station run` provisions *and* runs from a single, reproducible source of truth.

## Testability

A pure `build_station(config) -> Station` (parse → load plug-ins via `from_config` → register; **construct only, do not open**) is unit-tested with no I/O. Each transport's `from_config` is tested against config dicts (construction, hermetic). The Click surface is tested with Click's runner; `Station.serve()` is already covered.

## Open questions

1. Multi-station / multi-transport in one host — deferred; the schema (single `[station]`) could grow to `[[station]]` later. The bridge is a separate program regardless.
2. Whether `from_config` should live on the `Extension` base (fully generic) rather than per-axis — kept per-axis for now since the signatures differ (transports need the station address).
