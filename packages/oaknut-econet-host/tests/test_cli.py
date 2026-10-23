"""Tests for the econet-host host CLI and the serve lifecycle."""

import asyncio

from click.testing import CliRunner
from oaknut.econet.core import Address, TestTransport
from oaknut.econet.host.cli import cli, serve_until
from oaknut.econet.station import Station


def test_list_transports_lists_installed_plugins():
    result = CliRunner().invoke(cli, ["list-transports"])
    assert result.exit_code == 0, result.output
    assert "aun" in result.output
    assert "piconet" in result.output
    assert "hat" in result.output


def test_list_services_lists_kvstore():
    result = CliRunner().invoke(cli, ["list-services"])
    assert result.exit_code == 0, result.output
    assert "kvstore" in result.output


def test_describe_a_transport():
    result = CliRunner().invoke(cli, ["describe", "aun"])
    assert result.exit_code == 0, result.output
    assert result.output.strip()


def test_describe_unknown_name_errors():
    result = CliRunner().invoke(cli, ["describe", "no-such-plugin"])
    assert result.exit_code != 0


def test_validate_flag_path():
    result = CliRunner().invoke(
        cli, ["validate", "--transport", "aun", "--station", "0.254", "--service", "kvstore"]
    )
    assert result.exit_code == 0, result.output
    assert "0.254" in result.output
    assert "aun" in result.output
    assert "kvstore" in result.output
    assert "command-line flags" in result.output


def test_validate_unknown_transport_errors():
    result = CliRunner().invoke(cli, ["validate", "--transport", "nope", "--station", "0.254"])
    assert result.exit_code != 0


def test_validate_flag_path_needs_both_transport_and_station():
    result = CliRunner().invoke(cli, ["validate", "--transport", "aun"])
    assert result.exit_code != 0


async def test_serve_until_opens_then_closes_on_stop():
    transport = TestTransport(local_station=Address(0, 254))
    station = Station(transport)
    stop = asyncio.Event()
    task = asyncio.create_task(serve_until(station, stop))
    await asyncio.sleep(0)
    assert transport.is_open
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert transport.is_closed
