# oaknut-econet-aun

The **AUN** (Acorn Universal Networking) transport for the `oaknut-econet`
family — logical Econet carried over UDP/IP.

AUN was Acorn's bridge from Econet to Ethernet. It collapses the Econet
four-way handshake into a two-packet UDP exchange (a typed datagram plus an
`Ack`/`Nack`), with a 4-byte handle for correlation. Station addresses
`(network, station)` are resolved to and from IP `(host, port)` by a peer map;
the AUN header itself carries no station numbers.

This package provides:

- the AUN wire codec (`AunPacket` / `AunType`),
- the mapping between `oaknut.econet.core.EconetPacket` and AUN packets,
- `AunTransport`, an `EconetTransport` over an `asyncio` UDP endpoint, and
- optional mDNS station advertisement/discovery (the vendor-neutral
  `_aun._udp` convention), available with the `mdns` extra.

It registers on the `oaknut.econet.transport` extension axis as `aun`, so an
application can load it by name. It is the easiest transport to run with no
hardware — pure UDP — and is the reference against which the `EconetTransport`
abstraction is validated. See `docs/dev/econet-design.md` for the design.
