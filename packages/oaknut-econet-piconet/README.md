# oaknut-econet-piconet

The **Piconet** transport for the `oaknut-econet` family — a Raspberry Pi Pico
(RP2040) driving a real MC68B54 ADLC and presenting a USB-CDC serial-to-Econet
adapter to the host.

The Pico firmware runs the Econet four-way handshake itself and exposes a
line-based serial protocol: the host sends commands (`TX`, `BCAST`,
`SET_STATION`, …) and receives events (`RX_TRANSMIT`, `RX_BROADCAST`,
`TX_RESULT`, …) with base64-encoded payloads. This package provides:

- the serial protocol codec and the Econet frame parsing,
- the mapping between `oaknut.econet.core.EconetPacket` and the Piconet
  protocol,
- `PiconetTransport`, an `EconetTransport` driven over a `PicoLink`, and
- **`FakePiconet`** — an in-process simulation of the Pico firmware, so the
  transport is fully testable in CI with no hardware.

The real serial link (`SerialPicoLink`, via `pyserial-asyncio` behind the
`serial` extra) talks to an attached Pico. A Piconet consumes but does not
generate the Econet clock, so on-wire testing needs a clocked Econet and a peer
station (e.g. two Piconets plus a Raspberry Pi HAT / PiEconetBridge for the
clock). It registers on the `oaknut.econet.transport` axis as `piconet`. See
`docs/dev/econet-design.md` for the design.
