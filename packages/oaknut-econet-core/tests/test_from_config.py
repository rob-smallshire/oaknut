"""Contract for the EconetTransport.from_config default."""

from collections.abc import AsyncIterator

from oaknut.econet.core import (
    Address,
    EconetPacket,
    EconetTransport,
    TestTransport,
    TransmitOutcome,
    TransmitResult,
    TransportCapability,
)


class _ConfigTransport(EconetTransport):
    """A minimal transport whose constructor takes a flat keyword argument."""

    def __init__(self, name="cfg", *, local_station=None, retry_count=3):
        super().__init__(name=name)
        self._local_station = local_station
        self.retry_count = retry_count

    @property
    def capabilities(self) -> frozenset[TransportCapability]:
        return frozenset()

    @property
    def local_station(self):
        return self._local_station

    async def open(self) -> None: ...
    async def close(self) -> None: ...

    async def transmit(self, packet: EconetPacket) -> TransmitResult:
        return TransmitResult(TransmitOutcome.ACKNOWLEDGED)

    async def broadcast(self, payload: bytes, *, port: int, control: int) -> None: ...

    async def immediate(self, packet: EconetPacket) -> TransmitResult:
        return TransmitResult(TransmitOutcome.ACKNOWLEDGED)

    def __aiter__(self) -> AsyncIterator[EconetPacket]:
        return self

    async def __anext__(self) -> EconetPacket:
        raise StopAsyncIteration


def test_from_config_supplies_the_address_as_local_station():
    transport = TestTransport.from_config(name="t", address=Address(0, 5), config={})
    assert isinstance(transport, TestTransport)
    assert transport.name == "t"
    assert transport.local_station == Address(0, 5)


def test_from_config_passes_flat_kwargs_and_normalises_hyphens():
    transport = _ConfigTransport.from_config(
        name="c", address=Address(0, 1), config={"retry-count": 5}
    )
    assert transport.retry_count == 5
    assert transport.local_station == Address(0, 1)
