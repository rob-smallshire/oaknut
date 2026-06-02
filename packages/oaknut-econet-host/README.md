# oaknut-econet-host

The **`econet-host`** program — the CLI that turns installed Econet transport
and service plug-ins into a running station.

It depends on the `oaknut-econet-station` library and on Click (a hard
dependency — this *is* a CLI), and discovers whatever transports
(`oaknut.econet.transport`) and services (`oaknut.econet.service`) are installed.

```
econet-host run        [--config PATH]   # run the station until SIGINT/SIGTERM
econet-host validate   [--config PATH]   # build the config, print the plan, exit
econet-host list-transports              # installed transport plug-ins
econet-host list-services                # installed service plug-ins
econet-host describe   <name>            # a plug-in's description
econet-host run --transport aun --station 0.254 --service kvstore   # flag-only quick path
```

Configuration is TOML, discovered (first match wins) from `--config`, then
`[tool.econet-host]` in a `pyproject.toml`, then `econet-host.toml`, else the
flags above. See `docs/dev/econet-host.md` for the design and the recommended
uv-project deployment pattern.
