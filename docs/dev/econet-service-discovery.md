# oaknut Econet — Service Discovery (design notes)

**Status:** forward-looking design notes, created 2026-06-02. This records a design *position*; it commits us to building nothing yet. Amend in place. Related: `econet-design.md` §11 (mDNS station advertisement), §13 (the service host), and the DSCP draft at `beebium/docs/discussion/dynamic-station-config-protocol.md`.

## The question

mDNS already gives AUN zero-config *station* advertisement — the vendor-neutral `_aun._udp` record (econet-design.md §11). Should we also advertise Econet **ports and services** this way, and can discovery extend to the true Econet wire at all?

## The hard constraint: mDNS is IP-only

mDNS is multicast DNS over UDP/IP. It runs on the AUN side (which *is* IP) and **cannot run on the Econet wire** — there is no IP and no multicast there. So any mDNS-based discovery happens on the IP network, performed by a host that has an IP interface. A real BBC on the wire can neither advertise to, nor browse, mDNS.

And natively, Econet has **no service-discovery protocol** at all. Historically services were found by:

- **convention** — station `254` is the file server because everyone agreed it is;
- **broadcasts** — a client broadcasts to locate a server;
- the **`&9C` bridge protocol** — which discovers *networks*, not services;
- **`MachinePeek`** (immediate `&88`) — which reports a machine *type*, not its services.

So "advertise Econet services" can only mean one of three quite different things.

## Three separable things

**(a) Advertise *services*, not just station presence, over IP mDNS.** Today `_aun._udp` says "station N exists at this UDP endpoint" — transport-level presence. We can additionally advertise, the idiomatic DNS-SD way, **one service type per service** — `_econet-fs._udp`, `_econet-print._udp`, `_econet-dscp._udp` — each instance carrying TXT `net=`, `station=`, the AUN endpoint, and the Econet `port` (`&99`, …). A soft client can then *browse for file servers* directly instead of assuming `254`. Purely additive, cheap, idiomatic Bonjour. **Recommended.**

**(b) Gateway translation.** A host with *both* an IP interface and a wire transport (Piconet/HAT) can advertise, over IP mDNS, the **wire-side** stations and services it can reach — speaking Bonjour *on behalf of* a real BBC file server down the wire. A modern client browses `_econet-fs._udp`, finds the gateway's AUN endpoint tagged with the wire station's `net.stn`, and the gateway bridges its requests onto the wire. This makes genuinely-legacy services discoverable to zero-config clients, and is a natural payoff of the multi-transport architecture (the same media-converter shape as the bridge). **Design for it; implement alongside the bridge.**

**(c) A native, broadcast-based Econet wire discovery protocol.** The only way to get discovery on the pure wire is to invent one: a broadcast protocol on a well-known port (a client broadcasts "who offers service X?", or servers periodically announce their service list), which legacy stations harmlessly ignore. This is a **new speculative protocol**, a sibling to DSCP, carrying the same long pole — it only helps stations that have client software for it (a real BBC would need a ROM/utility). **Keep speculative/deferred.**

## Architectural model: the service host is the source of truth

A `Station` (econet-design.md §13) already knows the `Service`s registered on it, keyed by port. So discovery should be modelled as a small set of pluggable, **transport-aware advertiser/discoverer** components that read a `Station`'s service registry and publish it over whatever medium applies:

- an **mDNS advertiser/browser** — IP side; the DNS-SD per-service types of (a) plus the existing `_aun._udp` presence record;
- a **wire broadcast announcer** — future/speculative, option (c);
- a **gateway** that runs several and *translates* between them, option (b).

This mirrors how per-transport differences are already expressed as capabilities: "what services exist" is one abstract concept with medium-specific realizations, rather than mDNS being baked into the AUN transport. A transport/station advertises through whatever discoverers its medium supports (gated, like capabilities).

## DNS-SD modelling

Two complementary layers on the IP side, not one:

- **`_aun._udp`** — *station / transport presence* (an AUN endpoint to route to). Needed for AUN routing regardless of services. Already implemented as the TXT codec in `oaknut.econet.aun`.
- **`_econet-<service>._udp`** — *application-level service discovery*, one DNS-SD service type per service. TXT carries `net=`, `station=`, the AUN `port=`, and the Econet service `econet-port=` (e.g. `&99`). Lets a client browse by service.

(An alternative to per-service types is to enrich the `_aun._udp` TXT with a list of offered services; the per-service-type form is the more idiomatic and browsable. Open question.)

## Caveats

- **Legacy hardware can't use mDNS** at all. Convention (`&99`) plus broadcasts remain the baseline; mDNS/discovery benefits modern soft-stations and gateways. Discovery never replaces the well-known-port convention; it augments it.
- **Client support is the long pole** for any wire-native protocol (c), exactly as for DSCP.
- Discovery is **application-layer and non-blocking**: the file server works via the `&99` convention with no discovery at all. None of this gates the transport layer or the first applications.

## The zero-config theme

Three facets of one "make Econet plug-and-play" story, all anchored on the service host and sharing design philosophy:

- **§11 station presence** — *who is on the network* (`_aun._udp`).
- **service discovery (this doc)** — *what services they offer*.
- **DSCP** — *automatic station-number assignment*.

## Recommendation (one line)

Do **(a)** as the natural extension of the mDNS work (keep `_aun._udp` for presence, add `_econet-<svc>._udp` for services); design **(b)** as a gateway capability to land with the bridge; keep **(c)** deferred/speculative; and anchor all of it to the service-host registry so that "a `Station` publishes its services through whatever advertisers its transports support."

## Open questions

1. **Per-service DNS-SD naming** — the exact service-type strings (`_econet-fs._udp` etc.) and TXT schema; and whether to *also* (or instead) enrich the `_aun._udp` TXT with a service list.
2. **Native wire discovery (c)** — whether to pursue it at all, and if so its broadcast shape (announce vs query/response), its well-known port, and its relationship to DSCP.
3. **Gateway translation (b)** — how a gateway represents a wire station's services in IP mDNS (contact = gateway endpoint, identity = wire `net.stn`), and the reverse direction.
4. **Trust** — on a trusted LAN, none needed; for wider deployments, whether advertisements need any authentication (shared with the DSCP security question).
