# oaknut-econet-station

The Econet **service host** for the `oaknut-econet` family.

A `Station` is one network identity — an address plus an `EconetTransport` —
that hosts one or more `Service`s. It owns the inbound loop and dispatches each
received packet, **by port**, to the service registered for it, running each as
an independent `asyncio` task. A service replies by initiating a fresh transmit
to the reply port the client nominated.

This is the application-layer foundation: a file server, a print server, a DSCP
server, or a key-value store are each just a `Service` registered on a
`Station`. Several services run on one station concurrently — the thing
single-tasking 6502 hardware never could.

```python
station = Station(transport, address=Address(0, 254))
station.register(FileServer(...))      # claims port &99
station.register(PrintServer(...))     # claims the print ports
await station.serve()                  # dispatch inbound packets by port
```

See `docs/dev/econet-design.md` §13 for the design, including process
granularity and the station-broker pattern for multi-process services.
