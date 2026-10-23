# oaknut-econet-core

The core abstractions for Econet networking in the `oaknut` package family.

Econet was Acorn's networking technology for the BBC Micro, Master, and
Archimedes, built around the Motorola MC68B54 ADLC. This package provides the
foundation on which transports and applications are built:

- **`EconetPacket`** and **`PacketKind`** — the logical-packet currency shared by
  every transport (modelled on the AUN packet).
- **`Address`** — `(network, station)` addressing, with the well-known values
  (broadcast station, local network, immediate port).
- **`TransmitResult`** / **`TransmitOutcome`** — the fine-grained delivery outcome
  of a transmission (acknowledged, not-listening, no-clock, line-jammed, …).
- **`EconetTransport`** — the abstract, `asyncio`-native interface a transport
  implements, plus **`TransportCapability`** flags describing what a given
  transport supports.
- **`TestTransport`** — an in-process loopback transport for testing Econet
  applications without hardware or a network.

Concrete transports live in sibling packages (`oaknut-econet-aun`,
`oaknut-econet-piconet`, `oaknut-econet-hat`) and plug in through the
`oaknut.econet.transport` extension axis. Higher-level applications — a file
server, a bridge — build on this interface.

This package sits at the **logical-packet** level: the Econet four-way handshake
is resolved below the transport boundary, so applications work in whole packets,
not ADLC frames. See `docs/dev/econet-design.md` in the repository root for the
full design.
