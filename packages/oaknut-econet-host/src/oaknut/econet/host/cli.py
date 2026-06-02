"""The ``econet-station`` host CLI: configure transports + services and run."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from pathlib import Path

import click
from oaknut.cli import use_plain_help
from oaknut.econet.host import __version__
from oaknut.econet.station import Station, build_station, config_from_flags, load_config
from oaknut.exception import ConfigurationError, handled_errors
from oaknut.extension import describe_extension, list_extensions, namespace_for

_TRANSPORT_NS = namespace_for("econet.transport")
_SERVICE_NS = namespace_for("econet.service")


def _print_error(line: str, is_continuation: bool = False) -> None:
    click.secho(line, err=True, fg="yellow" if is_continuation else "red")


class _BoundaryGroup(click.Group):
    """Wraps every command in the oaknut handled_errors boundary, honouring --debug."""

    def invoke(self, ctx: click.Context):
        debug = bool(ctx.params.get("debug", False))
        with handled_errors(_print_error, debug=debug):
            return super().invoke(ctx)


def _resolve_config(config_path, transport, station, services):
    if config_path is not None:
        return load_config(config_path)
    if transport is not None or station is not None or services:
        if transport is None or station is None:
            raise ConfigurationError("the flag path needs both --transport and --station")
        config = config_from_flags(transport=transport, station=station, services=tuple(services))
        return config, "command-line flags"
    return load_config(None)


@click.group(cls=_BoundaryGroup)
@click.option("--debug", is_flag=True, help="Show full tracebacks for internal errors.")
@click.version_option(__version__, prog_name="econet-station")
def cli(debug: bool) -> None:
    """Host Econet services on a single station."""


_CONFIG = click.option(
    "--config", "config_path", default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a station config TOML file.",
)
_TRANSPORT = click.option("--transport", default=None, help="Transport plug-in (flag-only path).")
_STATION = click.option("--station", default=None, help="Station address, e.g. 0.254 (flag path).")
_SERVICE = click.option(
    "--service", "services", multiple=True, help="A service plug-in to host (repeatable)."
)


@cli.command()
@_CONFIG
@_TRANSPORT
@_STATION
@_SERVICE
def run(config_path, transport, station, services) -> None:
    """Run the station host until interrupted (SIGINT/SIGTERM)."""
    config, source = _resolve_config(config_path, transport, station, services)
    host = build_station(config)
    click.echo(f"econet-station {host.address} on '{config.transport}' (config: {source})")
    _echo_port_map(host)
    _run_blocking(host)


@cli.command()
@_CONFIG
@_TRANSPORT
@_STATION
@_SERVICE
def validate(config_path, transport, station, services) -> None:
    """Parse and build the configuration, print the plan, then exit."""
    config, source = _resolve_config(config_path, transport, station, services)
    host = build_station(config)
    click.echo(f"config source: {source}")
    click.echo(f"station:       {host.address}")
    click.echo(f"transport:     {config.transport}")
    _echo_port_map(host)
    click.echo("ok")


@cli.command("list-transports")
def list_transports() -> None:
    """List the installed transport plug-ins."""
    for name in sorted(list_extensions(_TRANSPORT_NS)):
        click.echo(name)


@cli.command("list-services")
def list_services() -> None:
    """List the installed service plug-ins."""
    for name in sorted(list_extensions(_SERVICE_NS)):
        click.echo(name)


@cli.command()
@click.argument("name")
def describe(name: str) -> None:
    """Describe a transport or service plug-in by name."""
    for kind, namespace in (("econet.transport", _TRANSPORT_NS), ("econet.service", _SERVICE_NS)):
        if name in list_extensions(namespace):
            click.echo(describe_extension(kind, namespace, name))
            return
    raise ConfigurationError(f"no transport or service named {name!r}")


def _echo_port_map(host: Station) -> None:
    port_map = host.port_map
    if not port_map:
        click.echo("  (no services)")
        return
    for port in sorted(port_map):
        click.echo(f"  &{port:02X}  {port_map[port]}")


async def serve_until(host: Station, stop: asyncio.Event) -> None:
    """Open the transport, serve, and shut down gracefully when *stop* is set."""
    await host.transport.open()
    serve_task = asyncio.create_task(host.serve())
    try:
        await stop.wait()
    finally:
        await host.transport.close()
        await serve_task


def _run_blocking(host: Station) -> None:
    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)
        await serve_until(host, stop)

    asyncio.run(_main())


use_plain_help(cli)
