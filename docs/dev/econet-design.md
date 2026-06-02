# oaknut Econet — Requirements & Design Document

**Status:** draft for iteration, created 2026-06-01. Nothing here is decided beyond what the prose marks as *decided*; flag anything you want to change. Amend this file in place; commit history is the discussion log. A separate `econet-implementation-plan.md` will carry the phased build once this shape is agreed.

---

## 1. Context

Econet was Acorn's proprietary LAN for the BBC Micro, Master, and Archimedes, built around the Motorola **MC68B54 ADLC** (Advanced Data Link Controller). Stations exchange HDLC-framed packets on a shared, clocked, two-pair bus using a **four-way handshake** for reliable unicast.

This project adds a new family of `oaknut` packages providing **low-level Python tools for writing Econet clients and servers** ("Econet applications") on contemporary hardware, plus — later — higher-level applications built on them, the first being a **file server**. It targets three contemporary Econet transports:

- **AUN** (Acorn Universal Networking) — logical Econet carried over UDP/IP. Acorn's own bridge from Econet to Ethernet; widely used by emulators (BeebEm, Beebium) and real RISC OS machines.
- **Piconet** — a Raspberry Pi Pico (RP2040) driving a real ADLC, presenting a USB-CDC **serial-to-Econet** adapter to the host. Source: `/Users/rjs/Code/piconet`.
- **PiEconetHAT** — a Raspberry Pi HAT carrying a real ADLC, driven by a Linux **kernel module** exposing a character device to user space. Source: `/Users/rjs/Code/PiEconetBridge`.

An explicit goal is to **technically supersede PiEconetBridge** — the dominant modern Econet stack — which suffers from no automated tests, blocking/busy-wait I/O, coarse global locking, and tight kernel/user-space coupling. We aim for a clean, fully tested, `asyncio`-based stack with a sharp separation between dumb transports and the routing/server logic above them. A specific target is a **true Econet bridge** — one that participates in the native bridge protocol (`&9C`) and forwards transactions faithfully between segments, which we believe PiEconetBridge does not genuinely do (it routes/NATs AUN packets rather than bridging Econet). A canonical deployment is a single host with **two Piconet adapters** bridging two Econet segments, running `oaknut-econet`-based software (see §12, FR10).

### Relationship to the rest of oaknut

- The eventual file server speaks the Acorn **file-server protocol** (port `&99`), the same protocol the existing `oaknut-afs` Level 3 file-server on-disc work serves data *from*. The two meet: `oaknut-afs` owns the on-disc `AFS0` format; the Econet file server owns the wire protocol. See `project_afs_implementation` memory and `docs/dev/afs-*.md`.
- The **NFS/ANFS disassemblies** at `/Users/rjs/Code/acornaeology/acorn-nfs` are the ground-truth specification for the client side of the `&99` file-server, `&9F` print-server, and `&9C` bridge protocols, and for immediate-operation semantics. They are the spec the future server is judged against; they do **not** affect the transport design below.

### Primary sources (reference codebases)

All local; **each carries its own `CLAUDE.md`**, so each can be consulted as its own project agent (read-only) via `claude -p "…" --permission-mode plan` run with its directory as the cwd.

| Codebase | Path | What it gives us |
|---|---|---|
| Beebium | `/Users/rjs/Code/beebium` | Best architectural guide: `Mc6854` ADLC, `FourWayHandshake` decorator, `NetworkBackend` ABC with AUN + Piconet backends, and the `_aun._udp` mDNS station-advertisement standard. C++. |
| Piconet | `/Users/rjs/Code/piconet` | Host↔Pico serial protocol; firmware that runs the four-way handshake on the wire. C firmware + TypeScript host driver. |
| PiEconetBridge | `/Users/rjs/Code/PiEconetBridge` | Kernel char-device interface (`/dev/econet-gpio`, ioctl magic `0xa9`), AUN/trunk bridging, the design we mean to supersede. C. |
| acorn-nfs | `/Users/rjs/Code/acornaeology/acorn-nfs` | Disassemblies of NFS/ANFS — `&99` file-server / `&9F` print protocols, immediate ops. The server's spec. |
| acorn-econet-bridge | `/Users/rjs/Code/acornaeology/acorn-econet-bridge` | Disassembly + analysis of the Acorn Econet Bridge appliance — the native bridge protocol (`&9C`) and true-bridge forwarding semantics. The bridge's spec. |

---

## 2. Econet primer (terms used throughout)

- **Station address** — an 8-bit **station number** (1–254; `255` = broadcast; `0` reserved) qualified by an 8-bit **network number** (`0` = "this network" / local segment; 1–127 conventional for remote nets). Throughout this doc and the code, an **`Address`** is the pair `(network, station)`.
- **Port** — an 8-bit demultiplexing key chosen by the receiver. Well-known ports, from the NFS/ANFS disassembly: `&00` immediate operations, `&90` FS reply, `&91` FS save/ack, `&92` FS load-data, `&93` remote, `&99` file-server command, `&D1` print server; plus `&9C` for the bridge protocol (from the Acorn bridge disassembly — NFS/ANFS itself does not use `&9C`). Port `&00` is special: it carries immediate operations, not normal data. These are the `Port` constants in `oaknut.econet.core`.
- **Control byte** — an 8-bit per-packet code; the high bit (`&80`) is conventionally set on the wire and is **cleared in the AUN representation**. The lower bits select the operation within a protocol.
- **Four-way handshake** — reliable unicast: sender emits a **scout** (dest+src addresses, control, port), receiver returns a **scout-ack**, sender sends the **data** frame(s), receiver returns a **final-ack**. CRC, flag-fill, and timing are ADLC concerns.
- **Immediate operations** — control-port (`&00`) operations executed by the receiver's NMI handler without application involvement: `Peek`, `Poke`, `JSR`, user/OS procedure calls, `Halt`, `Continue`, **`MachinePeek`** (returns machine type/version) — control bytes `&81`–`&88`, the `ImmediateOp` codes in `oaknut.econet.core`. These are a **two-way** exchange (request → reply), not four-way.
- **Broadcast** — a single unacknowledged frame to `255.255`.
- **AUN** — collapses the wire handshake into a two-packet UDP exchange (a typed datagram + an `Ack`/`Nack`), with a 4-byte handle/sequence for correlation and retransmission.

---

## 3. The central design insight

The natural fear when unifying these transports is an *abstraction-level mismatch*: a real ADLC operates at the **frame** level (scout / scout-ack / data / final-ack), while AUN operates at the **logical packet** level (one request, one ack). In fact **all three transports already resolve the four-way handshake below the host boundary**:

| Transport | Exposes to the host | Who runs the four-way handshake |
|---|---|---|
| AUN | typed UDP datagrams `(type, port, ctrl, seq, payload)` | nobody — AUN is two-packet by design |
| Piconet | `TX …` → `TX_RESULT`; inbound `RX_TRANSMIT scout data` | the Pico **firmware**, on the wire |
| PiEconetHAT | `read()`/`write()` of `struct __econet_packet_aun` | the **kernel module**, in the ADLC IRQ |

The clincher: PiEconetBridge's *own internal IPC currency* is `struct __econet_packet_aun` — an AUN-shaped logical packet. Beebium needs its frame-level `Mc6854` + `FourWayHandshake` only because it emulates an ADLC for a real 6502 to poke registers on. **We never present an ADLC to anyone** — we write Python clients and servers — so we sit one layer up, at the **logical AUN packet**, and the abstraction stays clean across all three transports.

**Decided:** the `EconetTransport` abstraction is at the logical-packet level. There is no ADLC model, no frame codec, no scout/ack state machine in this project. (One exception surfaces later: a *true* Econet bridge is a frame relay and needs a frame-level facet — see §12.2. That is an additive, optional capability used only by the bridge application; it does not change the logical-packet core that clients, servers, and transaction-level routers use.)

A direct consequence, **validated against the Piconet firmware via its project agent** (firmware completes the full four-way including the final data ack at `econet.c:586` *before* emitting `RX_TRANSMIT`): **an inbound packet delivered to the application is a completed transaction — already acknowledged on the wire.** An application *replies* by initiating a fresh outbound transaction. The sole two-way exception is immediate operations.

---

## 4. Requirements

### Functional

- **FR1** — An `asyncio`-native Python API to send and receive Econet packets over a pluggable transport.
- **FR2** — Three concrete transports: AUN (UDP), Piconet (serial), PiEconetHAT (kernel char device), plus an in-process `TestTransport`.
- **FR3** — Support unicast (reliable four-way, abstracted), broadcast (fire-and-forget), and immediate operations (two-way).
- **FR4** — Address by `(network, station)`; treat network `0` as "this network".
- **FR5** — Transports are pluggable via the existing `oaknut-extension` (stevedore) system and are configured at application startup. An application may instantiate **multiple transports of different kinds simultaneously** (the prerequisite for bridges, switches, routers, and media converters).
- **FR6** — Advertise and discover AUN stations over mDNS using Beebium's `_aun._udp` convention, for zero-config interop.
- **FR7** — Each transport advertises a set of **capability flags**; applications branch on capabilities, not on transport identity.
- **FR8** — Surface fine-grained delivery outcomes (acknowledged / not-listening / no-clock / line-jammed / timeout / handshake-failed …) rather than a bare success/failure.
- **FR9 (future)** — Higher-level applications layered on the transport: a file server (`&99`), a print server (`&9F`), and bridge/router/switch services composing multiple transports.
- **FR10 (future)** — A *true* Econet bridge: participates in the native bridge protocol (`&9C` — `WhatNet`/`IsNet`/`Reset`/`Update`), manages per-segment network numbers, and forwards four-way transactions, immediate operations, and broadcasts faithfully across segments — as distinct from AUN-level packet routing/NAT. Canonical topology: one host, two Piconet adapters, two Econet segments. The Acorn Econet Bridge disassembly is the spec. **Parked 2026-06-01:** model A (verbatim relay) is parked pending a dual-ADLC controller (host-mediated relay can't meet per-frame timing); model B (proxy store-and-forward) is feasible but deferred behind phases 1–3. See §12.3.
- **FR11 (long-term)** — A Dynamic Station Configuration Protocol (DSCP): a DHCP-equivalent for automatic station-number (and peer-table) configuration, server and client, to make plug-and-play Econet feasible. A detailed speculative spec already exists at `beebium/docs/discussion/dynamic-station-config-protocol.md`; oaknut-econet is well placed to provide the dependency-light reference implementation and — uniquely — a *wire-side* DSCP station on real Econet via a Piconet/HAT transport. See §12.4.

### Non-functional

- **NFR1** — Raw `asyncio`; Python ≥ 3.12 (**decided**: the *whole* workspace bumps from ≥ 3.11 to ≥ 3.12).
- **NFR2** — Fully testable **without hardware or a network**; test-first (see `feedback_test_first`). The `TestTransport` and protocol-level unit tests carry the bulk of coverage; hardware-in-the-loop tests are opt-in.
- **NFR3** — No blocking calls on the event loop; **no busy-wait** (the specific PiEconetBridge anti-pattern of spinning on a status ioctl). Blocking syscalls (e.g. HAT ioctls) run in a thread executor.
- **NFR4** — Transports stay **dumb**: no routing, no address translation, no peer/NAT tables, no firewalling. Those are application-layer concerns, kept separate so transports remain composable.
- **NFR5** — Conform to oaknut conventions: PEP 420 namespace packages, the `oaknut-exception` hierarchy, the capability idiom already used by filesystems, the `_filename`/`_filepath`/`_dirpath` naming suffixes, and small, frequent, semantically-meaningful commits.
- **NFR6** — Interoperate on the wire with existing AUN implementations (BeebEm, PiEconetBridge, real Acorn AUN) and with Beebium's mDNS advertisement.

---

## 5. Guiding principles

1. **Logical packets, not frames.** The lingua franca is one `EconetPacket` type modelled on the AUN packet. No ADLC, no HDLC framing in this project.
2. **Pull, not push, at the public API.** Applications consume inbound traffic with `async for packet in transport:` and send with `await transport.transmit(packet)`. Internally we bridge `asyncio`'s push callbacks to this pull model with a bounded queue (see §8). Server and bridge logic reads as a loop, not a callback graph.
3. **Dumb transports, smart applications.** A transport moves packets between this host and one Econet-or-AUN segment, nothing more. Routing, NAT, pools, and firewalling live above. This is the structural fix that lets us supersede PiEconetBridge cleanly.
4. **Capabilities over type-checks.** Transports differ in real ways (monitor mode, host-generated immediate replies, multi-net awareness, discovery). Express the differences as flags; never write `if isinstance(t, AunTransport)`.
5. **Inbound is already acknowledged.** A received packet is a completed transaction. Replies are fresh transmits. Immediate operations are the lone two-way exception.
6. **Fail informatively.** Delivery returns a rich outcome; errors derive from the `oaknut-exception` hierarchy and render through the existing CLI boundary.
7. **Test without hardware.** Every protocol decode/encode and the full transport contract are exercised against in-process doubles. Hardware tests are an opt-in extra.

---

## 6. Core abstractions (`oaknut.econet.core`)

Sketches below establish *shape and intent*; exact signatures are settled in code, test-first.

### Addressing

```python
@dataclass(frozen=True, slots=True)
class Address:
    network: int   # 0 == "this network"
    station: int   # 1..254 ; 255 == broadcast

    @property
    def is_broadcast(self) -> bool: ...
    @property
    def is_local_net(self) -> bool: ...   # network == 0
```

Well-known constants live here: `BROADCAST_STATION = 255`, `LOCAL_NET = 0`, `IMMEDIATE_PORT = 0x00`, and a `Port` enum / constants for `&99`, `&9F`, `&9C`, etc. (named once the NFS/ANFS disassembly confirms them).

### Packets

```python
class PacketKind(Enum):
    BROADCAST = auto()
    UNICAST = auto()          # reliable four-way (abstracted)
    IMMEDIATE = auto()        # two-way request
    IMMEDIATE_REPLY = auto()  # two-way reply

@dataclass(frozen=True, slots=True)
class EconetPacket:
    kind: PacketKind
    dst: Address
    src: Address
    control: int              # 0..255 (AUN representation: high bit clear)
    port: int                 # 0..255
    payload: bytes
    seq: int | None = None    # transport owns AUN handle/sequence; usually None at the app layer
```

`ACK`/`NACK` are *not* packet kinds the application sees — they are wire-level outcomes folded into `TransmitOutcome` (below), because inbound packets are already acknowledged (principle 5).

### Delivery outcome

```python
class TransmitOutcome(Enum):
    ACKNOWLEDGED = auto()     # final-ack received / AUN Ack
    NOT_LISTENING = auto()    # no scout-ack: destination not listening on that port
    NO_CLOCK = auto()         # no network clock present
    LINE_JAMMED = auto()
    TIMEOUT = auto()
    HANDSHAKE_FAILED = auto()
    NETWORK_ERROR = auto()    # collision/underrun/misc

@dataclass(frozen=True, slots=True)
class TransmitResult:
    outcome: TransmitOutcome
    # immediate-reply payload when transmitting an IMMEDIATE that returns inline, else None
    reply: EconetPacket | None = None
```

The enum is the union of the failure modes the three transports actually report (Piconet `TX_RESULT`, PiEconetHAT TX status codes, AUN ack/nack/timeout). Mapping tables in each transport translate native codes into this set.

### The transport contract

```python
class EconetTransport(Extension, abc.ABC):
    """A logical-packet conduit between this host and one Econet/AUN segment.

    Analogous to `asyncio.Transport`, but one layer up: it carries whole Econet
    packets rather than bytes, and presents a pull (async-iterator) interface
    rather than `asyncio`'s push (Protocol-callback) interface.
    """

    def _kind(self) -> str:               # oaknut-extension axis
        return "econet.transport"

    @property
    @abc.abstractmethod
    def capabilities(self) -> frozenset["TransportCapability"]: ...

    @property
    @abc.abstractmethod
    def local_station(self) -> Address | None: ...

    @abc.abstractmethod
    async def open(self) -> None: ...
    @abc.abstractmethod
    async def close(self) -> None: ...

    async def __aenter__(self) -> "EconetTransport": ...
    async def __aexit__(self, *exc) -> None: ...

    @abc.abstractmethod
    async def transmit(self, packet: EconetPacket) -> TransmitResult:
        """Reliable four-way unicast. Returns when ack'd, refused, or timed out."""

    @abc.abstractmethod
    async def broadcast(self, payload: bytes, *, port: int, control: int) -> None:
        """Fire-and-forget broadcast to 255.255."""

    @abc.abstractmethod
    async def immediate(self, packet: EconetPacket) -> TransmitResult:
        """Two-way immediate op; reply (if any) is on the result."""

    @abc.abstractmethod
    def __aiter__(self) -> AsyncIterator[EconetPacket]:
        """Yield inbound packets (already wire-acknowledged)."""
```

### Capabilities

```python
class TransportCapability(Enum):
    MONITOR = auto()           # promiscuous receive of all traffic
    IMMEDIATE_REPLY = auto()   # can send host-generated immediate replies
    BROADCAST = auto()         # can originate broadcasts
    MULTI_NET = auto()         # honours network numbers beyond the local net
    DISCOVERY = auto()         # participates in mDNS advertise/discover
```

Worked example from the validated Piconet findings: a Piconet transport advertises `{BROADCAST, MONITOR}` but **not** `IMMEDIATE_REPLY` (the firmware `REPLY` path is currently non-functional), and it must **reclassify a received port-0 `RX_TRANSMIT` as `PacketKind.IMMEDIATE`** because the firmware never emits `RX_IMMEDIATE` and auto-answers only `MachinePeek`.

### Errors

A small hierarchy in `oaknut.econet.core`, fitting `oaknut-exception`:

- `EconetError(DataError)` — base for wire/protocol data faults (malformed AUN datagram, bad serial frame).
- `TransportConfigurationError(ConfigurationError)` — unknown transport name, missing/unopenable device, bad station number.
- Transport unavailability (device unplugged, no clock) surfaces as a `TransmitResult` outcome where it is an expected runtime condition, and as an exception only where it prevents `open()`.

---

## 7. Pluggability (`oaknut-extension`)

Transports plug in on a **new extension axis**: `kind = "econet.transport"`, giving the entry-point group `oaknut.econet.transport` (via `namespace_for`). Each transport distribution registers its class:

```toml
# packages/oaknut-econet-aun/pyproject.toml
[project.entry-points."oaknut.econet.transport"]
aun = "oaknut.econet.aun:AunTransport"
```

```toml
# packages/oaknut-econet-piconet/pyproject.toml
[project.entry-points."oaknut.econet.transport"]
piconet = "oaknut.econet.piconet:PiconetTransport"
```

An application resolves transports by name at startup, exactly as the `disc` CLI resolves filesystems today:

```python
aun = create_extension("econet.transport", "oaknut.econet.transport", "aun", **aun_config)
```

This makes a multi-transport application (a bridge) a matter of instantiating several named transports from a config file — no code change to add a transport kind to the ecosystem.

---

## 8. Async model and the relationship to `asyncio` Transports/Protocols

**Decided:** raw `asyncio`, not `anyio`. Rationale: Python ≥ 3.12 provides `asyncio.TaskGroup`, `asyncio.timeout()`, and `eager_task_factory` natively (the bulk of `anyio`'s value), every transport library we use is `asyncio`-native, and `anyio`'s remaining edge (trio portability) is not wanted. `anyio` on its default backend *is* `asyncio` anyway — same loop — so nothing is lost.

Our `EconetTransport` is deliberately **one layer above** the stdlib `asyncio.Transport`/`Protocol` pair, and uses it internally:

```
  Application  (file server, bridge/router)
       │   async for pkt in transport  /  await transport.transmit(pkt)        ← PULL, packet-level (ours)
  ─────┼────────────────────────────────────────────────────────────────────
  EconetTransport   (oaknut.econet.core ABC)
       │   each concrete transport bridges push → pull via asyncio.Queue
  ─────┼────────────────────────────────────────────────────────────────────
  asyncio.Transport + Protocol   (or loop.add_reader for the char device)     ← stdlib PLUMBING, push (callbacks)
       │   bytes / datagrams
  ─────┴────────────────────────────────────────────────────────────────────
  OS socket  /  serial port  /  /dev/econet-gpio
```

`asyncio`'s `Protocol` is **push**: the loop calls `data_received(bytes)` / `datagram_received(data, addr)`. Our public API is **pull**. Each concrete transport's `Protocol` callback parses bytes into an `EconetPacket` and `put_nowait`s it onto a bounded `asyncio.Queue`; the transport's `__aiter__` does `await queue.get()`. The bounded queue gives natural backpressure. Outbound, `transmit()` writes via the underlying transport and awaits a per-request future that the inbound path (or a timeout) resolves with a `TransmitResult`.

Concretely:

- **AUN** → `loop.create_datagram_endpoint(DatagramProtocol, …)`; `datagram_received` decodes the AUN header → queue.
- **Piconet** → `serial_asyncio.create_serial_connection(Protocol, …)`; `data_received` buffers CR/LF-delimited lines, parses the event keyword, base64-decodes the payload → queue.
- **PiEconetHAT** → no clean stdlib `Transport` exists for an arbitrary character device. Use `loop.add_reader(fd, callback)` for readiness and a `loop.run_in_executor` thread for the **blocking ioctls** (replacing PiEconetBridge's busy-wait on `ECONETGPIO_IOC_TXERR`). This is the one transport that does not fit the `Protocol` mould.
- **TestTransport** → no `asyncio` I/O at all; a pair of in-process queues (optionally cross-wired to a peer `TestTransport`) so tests run with no sockets and no hardware.

Concurrency/ownership: a transport owns its endpoint and a single background consume path. Applications drive it from their own tasks; an `asyncio.TaskGroup` in the application supervises one task per transport for a bridge.

---

## 9. Package topology

**Decided:** nested namespace. Both `oaknut` and `oaknut.econet` are PEP 420 namespace packages (**no `__init__.py` at `src/oaknut/` *or* `src/oaknut/econet/` in any distribution**); core code lives one level deeper at `oaknut.econet.core`.

| Distribution | Import path | Depends on | Scope |
|---|---|---|---|
| `oaknut-econet-core` | `oaknut.econet.core` | `oaknut-exception`, `oaknut-extension` | `Address`, `EconetPacket`, `PacketKind`, `TransmitResult`, `EconetTransport` ABC, `TransportCapability`, errors, `TestTransport`. **No transport/runtime deps.** |
| `oaknut-econet-aun` | `oaknut.econet.aun` | `oaknut-econet-core`, `zeroconf` | AUN/UDP transport + `_aun._udp` mDNS advertise/discover |
| `oaknut-econet-piconet` | `oaknut.econet.piconet` | `oaknut-econet-core`, `pyserial-asyncio` | Serial transport |
| `oaknut-econet-hat` | `oaknut.econet.hat` | `oaknut-econet-core` | `/dev/econet-gpio` char-device client (Linux + HAT only) |
| *future* `oaknut-econet-fileserver` | `oaknut.econet.fileserver` | `oaknut-econet-core`, `oaknut-afs`, … | `&99` file server |
| *future* `oaknut-econet-bridge` | `oaknut.econet.bridge` | `oaknut-econet-core` | bridge/router/switch composing transports |

The `TestTransport` ships **in** `oaknut-econet-core` (not a test-only helper) so downstream packages and applications can depend on it for their own tests.

**Workspace wiring to touch when adding each package:**
1. New `packages/oaknut-econet-*/pyproject.toml` (templated from `packages/oaknut-dfs/pyproject.toml`).
2. Root `pyproject.toml`: add to `[tool.uv.sources]`, the `workspace` dependency-group, `[tool.bumpversion.files]` (each new `src/oaknut/econet/<name>/__init__.py`), and `[tool.pytest.ini_options] testpaths`.
3. **Extend `scripts/check_no_namespace_init.sh`** (and its CI step) to also fail on `src/oaknut/econet/__init__.py`, mirroring the existing `src/oaknut/__init__.py` guard — a stray one there shadows the econet sub-namespace identically.
4. **Bump the whole workspace `requires-python` to `>=3.12`** and the matching `ruff`/classifier metadata.

---

## 10. Transport designs

> Wire-level details below are transcribed from the reference codebases at the fidelity reached during exploration and the Piconet agent consultation. Byte-exact layouts are to be re-confirmed against source during implementation (the per-codebase agents are the fastest way to do so).

### 10.1 AUN (`oaknut.econet.aun`)

The easiest to validate the whole abstraction against — pure UDP, no hardware.

**Wire format** — 8-byte header + payload:

| Offset | Field | Notes |
|---|---|---|
| 0 | type | 1 Broadcast, 2 Unicast, 3 Ack, 4 Nack, 5 Immediate, 6 ImmReply |
| 1 | port | |
| 2 | control | Econet high bit cleared |
| 3 | pad | `0` |
| 4–7 | handle/sequence | little-endian `uint32`, echoed in Ack/ImmReply for correlation |
| 8+ | payload | Econet data after control+port |

**Addressing/peer map** — `(net, stn) ↔ (ip, udp_port)`. UDP port is conventionally a `32768`-based scheme but is per-map configurable. Network `0` is local-relative and translated to/from the configured local net on the boundary. The peer map is **transport configuration**, not routing — a static operator map plus mDNS-discovered entries (operator entries win).

**Reliability** — the transport owns handle/sequence generation and retransmission/timeout; `transmit()` resolves on `Ack` (→ `ACKNOWLEDGED`), `Nack` (→ `NOT_LISTENING`), or timeout (→ `TIMEOUT`).

**Capabilities** — `{BROADCAST, IMMEDIATE_REPLY, MULTI_NET, DISCOVERY}` (no `MONITOR` — UDP unicast has no promiscuous mode).

**mDNS** — see §11.

### 10.2 Piconet (`oaknut.econet.piconet`)

**Link** — USB-CDC serial, 115200 baud, VID `0x2e8a` / PID `0x000a`; line-based, CR/LF-delimited; binary payloads base64-encoded.

**Commands (host → Pico):** `STATUS`, `SET_MODE STOP|LISTEN|MONITOR`, `SET_STATION <n>`, `TX <stn> <net> <ctrl> <port> <data_b64> [<scout_extra_b64>]`, `BCAST <data_b64>`, `REPLY <id> <data_b64>`, `RESTART`, `TEST`.

**Events (Pico → host):** `STATUS <ver> <stn> <sr1> <mode>`, `TX_RESULT <code>`, `RX_BROADCAST <frame_b64>`, `RX_TRANSMIT <scout_b64> <data_b64>`, `RX_IMMEDIATE …` (defined but never emitted), `MONITOR <frame_b64>`, `ERROR <text>`, `REPLY_RESULT <code>`.

**TX_RESULT codes** map to `TransmitOutcome`: `OK`→ACKNOWLEDGED, `NO_SCOUT_ACK`→NOT_LISTENING, `NO_DATA_ACK`/`HANDSHAKEFAIL`→HANDSHAKE_FAILED, `LINE_JAMMED`→LINE_JAMMED, `TIMEOUT`→TIMEOUT, `OVERFLOW`/`UNDERRUN`/`MISC`/`UNEXPECTED`→NETWORK_ERROR, `UNINITIALISED`→(raise `TransportConfigurationError`).

**Validated firmware semantics (via the piconet project agent):**
- The firmware completes the full four-way handshake, **including the final data ack**, before emitting `RX_TRANSMIT` (`econet.c:586`, returns `:593`). Inbound packets are already acknowledged.
- Host-side `REPLY` is currently **non-functional** (`_pending_reply.valid` never set on the RX path; always fails `INVALID_RECEIVE_ID`). → no `IMMEDIATE_REPLY` capability today.
- `RX_IMMEDIATE` is never emitted; `MachinePeek` (control `0x88`) is auto-answered in firmware. Other inbound immediates arrive as `RX_TRANSMIT` with a **port-0 scout** and must be reclassified to `PacketKind.IMMEDIATE`.

**Capabilities** — `{BROADCAST, MONITOR}` (revisit `IMMEDIATE_REPLY` if/when firmware `REPLY` is fixed; that may be a chance to feed improvements back upstream to piconet).

**Init** — open port, `STATUS` to read/verify firmware semver, `SET_STATION`, `SET_MODE LISTEN` (or `MONITOR`).

### 10.3 PiEconetHAT (`oaknut.econet.hat`)

A clean user-space client of the existing kernel module — Linux + HAT only.

**Interface** — character device `/dev/econet-gpio`; `read()` returns a `struct __econet_packet_aun` (≈12-byte header: dst net/stn, src net/stn, control, port, sequence + up to ~32 KB data); `write()` submits one. **ioctl** magic `0xa9`, including: `PACKETSIZE`, `AVAIL`, `TXERR` (last TX status), `GETAUNSTATE`, `RESET`, `READMODE`, `AUNMODE`, `FLAGFILL`, `SET_STATIONS` (8192-byte interest bitmap of 256 nets × 256 stations), `IMMSPOOF`, `RESILIENTACK`, `NETCLOCK`. Exact numbers/struct: `include/econet-gpio-consumer.h`.

**TX status codes** (`ECONET_TX_*`: SUCCESS/BUSY/NOCLOCK/NOTLISTENING/JAMMED/UNDERRUN/COLLISION/HANDSHAKEFAIL) map to `TransmitOutcome` analogously to Piconet.

**Async strategy** — `loop.add_reader(fd, …)` for inbound readiness; **blocking ioctls in a thread executor**. Explicitly **do not** replicate PiEconetBridge's tight `TXERR` busy-wait (NFR3): submit, then await completion via readiness/executor rather than spinning.

**Capabilities** — `{BROADCAST, MONITOR, MULTI_NET, IMMEDIATE_REPLY}` (subject to confirmation of `IMMSPOOF`/immediate handling).

**Note** — this transport's interface is also a logical AUN packet, so much of its decode/encode is shared with AUN's payload handling (different envelope, same packet body).

### 10.4 TestTransport (`oaknut.econet.core`)

In-process loopback double, shipped in core. Two modes: (a) standalone, where transmits resolve against a programmable script of outcomes/inbound packets for unit tests; (b) paired, where two `TestTransport`s are cross-wired so one's `transmit()` appears on the other's `__aiter__`, for testing application logic (a toy file server against a toy client) entirely in memory. Advertises a configurable capability set so capability-branching code can be exercised both ways.

---

## 11. mDNS / Bonjour station advertisement

**Decided:** adopt Beebium's vendor-neutral standard so we interoperate with it (and invite BeebEm/PiEconetBridge to adopt it too).

- **Service type:** `_aun._udp`
- **Instance name:** `<impl>-<station>._aun._udp.local.` (e.g. `oaknut-32._aun._udp.local.`)
- **TXT records:**

| Key | Required | Meaning |
|---|---|---|
| `version` | yes | TXT schema version (`1`) |
| `station` | yes | Econet station (1–254) |
| `port` | yes | UDP port |
| `net` | yes | Econet net number (0–127) — **must not** be defaulted; net 0 is local-relative and ambiguous across segments |
| `impl` | no | implementation id (diagnostic only) |
| `impl-version` | no | implementation version (diagnostic) |
| `impl-identity` | no | opaque per-instance id (diagnostic) |

Implemented with `zeroconf.asyncio.AsyncZeroconf` (advertise) and `AsyncServiceBrowser` (discover). Discovered peers populate the AUN transport's peer map as evictable entries; operator-configured entries take precedence and never expire. `impl*` fields are never used for behavioural decisions.

---

## 12. Higher-level applications (forward-looking)

Not built yet, but the core abstraction is shaped to enable them without rework:

- **File server (`&99`)** — an application that listens on port `&99`, decodes the file-server protocol (per the NFS/ANFS disassembly), and serves data from an `oaknut-afs`/`oaknut-adfs`/`oaknut-dfs` backing store. Replies are fresh `transmit()`s to the client's reply port. Immediate ops handled via `immediate()`/inbound `IMMEDIATE`.
- **Bridge / router / switch** — an application owning **several** transports and a routing table `network → transport`, plus optional NAT/pools/firewalling — all in the application, none in the transports. Forwarding is: `async for pkt in transport_a: await route(pkt)`. This is the concrete path to superseding PiEconetBridge: the routing logic that PiEconetBridge fuses with its device layer (one global `networks[]` under a single mutex) becomes a testable, transport-agnostic service over clean `EconetTransport` instances.
- **True bridge** — a bridge goes further than routing packets: to be a *true* Econet bridge it implements the `&9C` bridge protocol so that other bridges and stations recognise it as a genuine Acorn bridge (answering `WhatNet`/`IsNet`, originating and honouring bridge `Reset`/`Update`), manages each segment's network number, and reproduces the appliance's forwarding behaviour for four-way data, immediate operations, and broadcasts — including the timing/flag-fill discipline the four-way relay demands. The Acorn Econet Bridge disassembly is the authority for these behaviours; the protocol breakdown is in §12.1 below.

### 12.1 The native bridge protocol (`&9C`)

From the Acorn Econet Bridge disassembly (consulted read-only via its project agent; cited there to `versions/econet-bridge-variant_1/output/…asm` and `docs/analysis/`):

- **A bridge has no station number.** It advertises the **networks it can reach**, not a station identity. Each side's own net number is configured per port (the appliance jumpered `net_num_a` / `net_num_b`; 7-bit, 1–127) and never changes at runtime.
- **`&9C` frames are full broadcasts only** (`dst = 255.255`, a fixed bridge source convention, `port = &9C`); the control byte selects the operation:

  | ctrl | Name | Role |
  |---|---|---|
  | `&80` | BridgeReset | "I just came up — relearn"; payload = the announcer's net on the *opposite* side |
  | `&81` | BridgeReply | re-announcement listing reachable nets; the list grows by one (the forwarder's own net) per hop |
  | `&82` | WhatNet | "which nets do you reach?"; reply enumerates reachable nets |
  | `&83` | IsNet | "can you reach net X?"; reachable → reply, otherwise dropped |

- **Routing is distance-vector reachability, learned by flooding.** Two 256-byte tables (`reachable_via_a` / `reachable_via_b`) index reachability by net; seeded with the own net + broadcast, then populated from `&80`/`&81`. On learning, the bridge appends its own net and re-broadcasts out the *other* side.
- **Reset/Update is event-driven, not timed.** Receiving a `&80` is the only trigger that wipes the tables and schedules a burst of staggered `&81` re-announcements; a `&81` only *learns* (it never re-triggers a burst — this is what stops an announce loop between two bridges). A lone bridge sends two frames at boot, then goes silent.
- **Net 0 is rewritten at the boundary, never carried across.** Inbound `dst_net == 0` is rejected; `src_net == 0` is replaced with the arrival side's net before forwarding; a `dst_net` equal to the far side's own net is normalised back to `0` so it reads as "local" on the destination segment.

### 12.2 The forwarding model — and a real design tension

The crux: **the Acorn bridge is a transparent layer-2 HDLC frame relay.** It does *not* terminate a transaction on the near side and re-originate it on the far side. It **store-and-forwards each individual frame** — scout, scout-ack, data, final-ack — verbatim onto the other segment, so the *two real endpoints run the four-way handshake through it*. It holds no per-transaction state; any missing / invalid / unroutable frame aborts cleanly and the endpoints time out and retry. It does real CSMA + flag-fill and is bound by Econet's microsecond-scale inter-frame timing; each hop adds a full frame of store-and-forward latency, which the disassembly notes already tightens the endpoints' timing budget. Forwarding is port-agnostic and net-based (`dst_net` not local **and** reachable via the other side); immediate ops and broadcasts ride the same path (immediate-op fidelity through the appliance is unverified).

**This collides with §3's decision** to sit at the logical-packet level. A faithful true bridge operates one layer *down*, at the frame level — exactly the layer that stock Piconet firmware, the HAT kernel module, and AUN all hide by completing (or obviating) the handshake below the host. Resolution:

- The logical-packet abstraction stays correct and primary for **clients, servers, and transaction-level routers** — the bulk of the project.
- A **true bridge in the verbatim sense (model A, §12.3) needs a frame-level facet**: an optional, lower-level capability (`FRAME_RELAY`) exposing raw frames with full 4-byte addressing, *no* auto-ack and *no* auto-handshake, offered only by transports that can provide it. This is additive — it does not change the core packet API. (The alternative *proxy* bridge, model B, does **not** need it — see §12.3.)
- **AUN can never be a true-bridge segment** — it is already transaction-level; there are no frames to relay.
- **Stock Piconet firmware cannot do this** (it auto-completes the handshake and surfaces only completed transactions). A frame-relay mode requires **firmware changes** — in scope, since the piconet repo is ours to modify. See §12.3 for the two bridge architectures and the concrete change list.

**Feasibility concern to settle early.** A host-mediated, frame-by-frame relay across *two USB-serial Picos* inserts USB-CDC + OS + Python latency into every frame hop. Econet's handshake timing is tight enough that the 6502 appliance — with both ADLCs on one board — was already near the edge. Relaying each frame up to Python and back down to a second Pico may simply not meet the inter-frame deadlines. If so, a faithful frame-relay bridge needs the relay to live *below* the host — in Pico firmware, or on a single dual-ADLC controller — with the host configuring and coordinating rather than relaying each frame. The buildable-today alternative (transaction-level store-and-forward on the logical-packet abstraction) is exactly what PiEconetBridge does and what we've agreed is *not* a true bridge, so it is a documented fallback, not the goal. **Where the frame relay must physically live is the central open question for FR10 (§15.9).**

### 12.3 Two bridge architectures, and the Piconet firmware delta

The firmware consultation (Piconet agent, read-only) clarifies that "true bridge" splits into **two distinct architectures**, and the Piconet path naturally lands on the second:

- **(A) Verbatim frame relay** — the Acorn appliance. Each scout/ack/data/ack frame is relayed across unchanged; the two endpoints handshake *through* the bridge. Frame-level, fully transparent, no proxying. Demands the relay sit where both ADLCs share microsecond-tight timing (a single dual-ADLC controller, or a firmware-resident relay). **A host-in-the-loop relay over two USB Picos is almost certainly too slow for this.**
- **(B) Proxy store-and-forward** — the bridge *proxies* the remote station: it scout-ACKs locally on the originator's segment (holding the line with flag-fill), accepts the whole transaction, then re-originates it to the real destination on the far segment. Transaction-level. Structurally this is what PiEconetBridge does — but a Piconet-based version stays **native Econet on both sides**, preserves the original 4-byte addressing, and speaks the `&9C` protocol, so it is materially closer to a true bridge than PiEconetBridge's AUN/IP hop. Whether (B) counts as a "true bridge" is a definitional call (transparency vs native-Econet-both-sides + `&9C` + addressing fidelity) — **open question, see §15.9.**

The Piconet firmware architecture is *favourable* for model (B): the MC68B54 already receives **all** frames (no hardware address filter to fight — filtering is a software check on the destination-station byte only), and the ACK builder is **already address-transparent** (it sources the ACK from the incoming frame's destination fields, not from the configured station). So relaxing the software filter automatically yields correctly-addressed proxy ACKs. The ranked firmware changes (from the consultation; the agent's full write-up with citations is in its plan file):

- **Easy** — (1) add arbitrary **source** addressing to the `TX` command (it currently forces src = configured station, src-net = 0), so the host can relay preserving the original source; (2) gate the **MachinePeek auto-answer** behind "is this one of *my* real stations?" so it does not shadow every proxied station's identity.
- **Medium** — (3) replace the 2-entry station filter with a configurable **proxy set/range** plus a host command to load it; (4) add a combined **active-promiscuous / bridge mode** (receive for the proxy set, complete the handshake, report the full transaction to the host) alongside STOP/LISTEN/MONITOR — today no mode both receives-all *and* can transmit/ack; (5) re-enable/finish the disabled **held-open REPLY path** and make `reply()` write a full 4-byte header.
- **Harder (design, host-side)** — (6) the bridge state machine + `&9C` topology logic lives in host Python on top of these primitives; (7) **timing/flag-fill correctness while proxying** — the Pico must scout-ACK fast enough to hold the originator while the far-segment transaction is driven; today the four-way runs synchronously to completion, so the held-open flag-fill approach is required. **This is the main real-time risk and needs bench testing.**

Upshot: model (B) over two Picos is a realistic build given these firmware changes; model (A) verbatim relay over two USB Picos is not.

**Decision (2026-06-01):** model (A) is **parked** — host-mediated verbatim relay over two USB Picos cannot meet per-frame handshake timing, and it needs a single dual-ADLC controller or a firmware-resident relay to be viable. Importantly, **model (B) is *not* latency-bound**: each segment's four-way completes locally in the proxying Pico's firmware, so host (USB + Python) latency only adds end-to-end store-and-forward delay, not per-frame timing pressure. Model (B) therefore remains a feasible future bridge — **deferred** behind the foundational phases (core + AUN + Piconet client/server), not abandoned. The analysis above is retained for that revisit.

### 12.4 Plug-and-play: Dynamic Station Configuration Protocol (DSCP) — long-term

A long-term goal (FR11): DSCP plays the role DHCP plays on IP — a station comes up with no pre-assigned number and is configured automatically. A detailed speculative spec already exists at **`beebium/docs/discussion/dynamic-station-config-protocol.md`**; that document is the design basis and is not restated here. The points salient to oaknut-econet:

- **Two flavours.** (i) An *IP-native* UDP protocol that runs *alongside* AUN (never inside it, so AUN interop is never compromised) for soft-stations — fixed binary wire format (magic `0xD5`; Allocate / Release / Renew / List), a lease model, mDNS-discovered server, and a peer-table bootstrap carried in the Allocate response. (ii) A *wire-side* variant carried over Econet itself (an immediate op or a data frame on a reserved DSCP station/port) so real hardware can self-configure — the `*AUTOSETSTATION` idea, writing CMOS byte `0x0E` exactly as `*SETSTATION` does.
- **Layering.** DSCP is a higher-level application, like the file server — it does not touch the core abstraction. The IP-native server is a small asyncio app (UDP + `zeroconf`), matching the spec's "zero exotic dependencies, any language can implement it" goal. The wire-side server/client maps directly onto `EconetTransport` (`immediate()` or a reserved port), with station-occupancy discovery via a `MachinePeek` (`&88`) sweep plus passive source-address observation.
- **Where oaknut-econet adds something Beebium can't.** Beebium is an emulator, so its wire-side DSCP needs PiEconetBridge's PIPESERVER. An oaknut-econet process with a Piconet or HAT transport can *be* the wire-side DSCP station directly on real Econet — a natural fit for the cross-emulator/cross-hardware reference implementation the spec calls for.
- **Naming.** The spec itself flags that the published protocol name and mDNS service type must be vendor-neutral (not `_beebium-dscp`); candidates include `_econet-dscp._udp` and the names "DSCP" or "ESAP". Open question (§15.10).
- **Client support is the long pole.** DSCP needs station-side client software (a 6502 ROM/utility for real hardware; a startup step for soft-stations), which is what makes this a long arc rather than a near-term deliverable.

---

## 13. The application layer: the service host and port dispatch

Legacy Acorn networks ran roughly one service per station — `254` the file server, a print server on its own station, and so on. That was a *deployment* constraint (one machine per station, no multitasking OS), **not** a protocol one: the Econet **port** — the receiver-chosen demultiplexing byte carried in every scout — has always let a single station offer many services at once. oaknut is not bound by the one-service-per-station tradition, and this is a key thing for Econet application authors to internalise.

**The model.** A **`Station`** is one network identity — an `Address` plus an `EconetTransport` — that hosts one or more **`Service`s**. It owns the inbound loop and dispatches each received packet to the service registered for its **port**:

```python
class Service(abc.ABC):
    """A handler for one Econet protocol, bound to one or more ports."""

    @property
    @abc.abstractmethod
    def ports(self) -> frozenset[int]: ...          # e.g. {Port.FS_COMMAND}

    @abc.abstractmethod
    async def handle(self, request: EconetPacket, station: "Station") -> None: ...


class Station:
    """A logical Econet station hosting services over one transport."""

    def __init__(self, transport: EconetTransport, *, address: Address) -> None: ...

    def register(self, service: Service) -> None: ...     # claims service.ports

    async def serve(self) -> None:
        async with self._transport:
            async for request in self._transport:
                service = self._services_by_port.get(request.port)
                if service is not None:
                    self._spawn(service.handle(request, self))   # concurrent task

    async def reply(self, to: Address, *, port: int, control: int, payload: bytes): ...
        # a fresh transmit back to the client's nominated reply port
```

**Several services, one station, concurrently.** A file server (`&99` plus its data ports), a print server, a DSCP server, and bespoke services can all run on the same `Station`, dispatched by port, each handling requests as independent `asyncio` tasks — so a slow operation (a large `*LOAD`) never blocks the others. This is precisely what single-tasking 6502 hardware could not do, and it is the main way oaknut transcends the legacy model.

**Two levels of selection.** The **port** routes a packet to a *service*; the **control byte** (and, within the file-server protocol, the request's function code) selects the *operation* within that service. Services receive whole `EconetPacket`s (already wire-acknowledged below the transport) and respond by initiating *fresh* transmits to the **reply port** the client nominated in its request — never by "returning" on the inbound path.

**Immediate operations (port 0)** are dispatched on their own path: a station may answer `MachinePeek` itself (advertising its machine type/version) and route other immediates to an immediate handler, subject to the transport's `IMMEDIATE_REPLY` capability.

**Composition.** The common case is one `Station`, many services. A host process may equally run **several `Station`s** — distinct identities, each over its own transport — which is how media-converters and the (model-B) bridge are built: those *forward* between transports rather than *terminating* services, but share the same "own a transport, consume its inbound loop" footing.

This service-host layer is the foundation the `&99` file server, the print server, and the DSCP server all plug into; it will land as its own package (working name `oaknut.econet.station`). Its exact API — the `Station`/`Service` naming, static vs dynamic port claims, and the immediate-op dispatch hook — is the first thing to settle when we start the application layer (see the open questions in §15).

---

## 14. Testing strategy

- **Unit** — packet/header encode-decode for each transport (AUN header, Piconet line grammar + base64, HAT struct), outcome-code mapping tables, capability advertisement. Pure functions, no I/O.
- **Contract** — a shared `EconetTransport` conformance suite parametrised over `TestTransport` (and, when hardware is present, the real transports) to pin the abstraction's behaviour.
- **Integration** — paired `TestTransport` exercising application logic (toy client ↔ toy server) end-to-end in memory.
- **Hardware-in-the-loop** — opt-in, marker-gated tests for Piconet (a connected Pico) and HAT (a connected HAT), skipped by default.
- **Tooling** — add `pytest-asyncio` to the econet packages' `test` dependency group; respect the workspace's `--import-mode=importlib` and the dual `sys.path` injection in each package's `tests/conftest.py` (see root `CLAUDE.md`). Per `feedback_test_data_in_git`, any captured packet corpora are committed, not synthesised at runtime.

---

## 15. Open questions

1. **Well-known ports & immediate control codes** — *resolved*: enumerated from the NFS/ANFS disassembly (and the bridge disassembly for `&9C`) and frozen as the `Port` and `ImmediateOp` enums in `oaknut.econet.core`. Notable corrections: the print server is `&D1` in NFS/ANFS (not `&9F`), and `&9C` is the bridge appliance's port, not referenced by NFS/ANFS.
2. **AUN UDP port scheme** — *decided*: fully map-driven. `AunTransport` binds a configurable `(host, port)` (default `DEFAULT_AUN_PORT = 32768`) and resolves peers via an explicit peer map; no fixed per-station formula, which is the most interoperable choice.
3. **`seq`/handle exposure** — confirm the file server never needs the AUN handle at the application layer (reply correlation is by reply-port, not handle). If it does, surface it deliberately rather than leaking it.
4. **HAT immediate handling** — confirm `IMMSPOOF`/`RESILIENTACK` semantics before claiming `IMMEDIATE_REPLY`.
5. **Configuration format** — how applications declare transports + maps at startup (TOML? reuse an existing oaknut config convention?). Bridges need this most.
6. **Piconet `REPLY` upstream** — whether to fix the firmware `REPLY` path upstream so Piconet can gain `IMMEDIATE_REPLY`.
7. **True-bridge forwarding semantics** — *largely resolved* in §12.2: the Acorn bridge is a frame-by-frame store-and-forward HDLC relay reproducing the full `&9C` protocol, not a transaction terminator. Remaining: immediate-op fidelity through the relay (unverified in the appliance).
8. **Piconet firmware changes** — *answered* in §12.3 (ranked): the favourable news is that the MC68B54 already receives all frames and the ACK builder is address-transparent, so a proxy (model B) bridge is a realistic firmware delta; verbatim relay (model A) over two USB Picos is not. The held-open flag-fill timing while proxying is the main real-time risk and needs bench testing.
9. **Which definition of "true bridge" we commit to** (the central FR10 question) — verbatim frame relay (model A: transparent, frame-level; needs a single dual-ADLC controller or firmware-resident relay) vs native proxy store-and-forward (model B: two Picos + firmware changes + host `&9C` logic; native Econet both sides, addressing-preserving, but not byte-transparent). This drives where the relay lives and how much firmware work FR10 entails.
10. **DSCP scope & name** — IP-native first (the Beebium draft's Option A) vs wire-side-first (leveraging our real-transport advantage as a wire-side DSCP station); and the vendor-neutral protocol / mDNS service name. Builds directly on `beebium/docs/discussion/dynamic-station-config-protocol.md`.
11. **Service-host API** (§13) — the `Station`/`Service` naming, how a service claims ports (a static `ports` set vs dynamic registration), and the reply-port and immediate-op dispatch hooks. The first thing to settle when the application layer starts.

---

## 16. Roadmap (phased)

**Implementation status (2026-06-02, `econet` branch, test-first; `master` untouched):**
- Phase 1 **(done)** — workspace at Python ≥3.12; namespace-init guard extended for `oaknut.econet`; ruff config consolidated into `pyproject.toml` (was split with a stale `ruff.toml`).
- Phase 2 **(done)** — `oaknut-econet-core`: value types, the `EconetTransport` ABC, `TestTransport`, the error hierarchy, the reusable conformance suite, and the well-known `Port`/`ImmediateOp` constants.
- Phase 3 **(done, bar live mDNS)** — `oaknut-econet-aun`: AUN wire codec, the `EconetPacket`↔`AunPacket` mapping, `AunTransport` over asyncio UDP (validated over 127.0.0.1 loopback + conformance), and the `_aun._udp` mDNS TXT codec. Live AsyncZeroconf advertiser/browser deferred.
- Phase 4 **(done, Stage A)** — `oaknut-econet-piconet`: serial protocol codec, Econet frame mapping, `PiconetTransport` driven over a `PicoLink`, the shipped `FakePiconet` firmware simulation (CI-testable with no hardware), `status()`, and `SerialPicoLink` (real board, `[serial]` extra). On-Econet hardware tests are gated/opt-in (Stage B; the two-Piconet + HAT/PiEconetBridge rig supplies the clock and peers).
- Phase 5 **(done, Stage A)** — `oaknut-econet-hat`: the `struct __econet_packet_aun` codec, the `EconetPacket`↔kernel mapping + station-interest bitmap, `HatTransport` over a `KernelDevice`, the shipped `FakeKernelDevice` (CI-testable with no hardware), and `EconetGpioDevice` (the real `/dev/econet-gpio` client — stdlib-only, ioctl numbers hermetically verified, non-busy-wait TXERR poll). Hardware tests gated/opt-in.
- **All three transports (AUN, Piconet, HAT) now plug into the `oaknut.econet.transport` axis**, each CI-tested via a shipped fake plus the shared conformance suite. Full workspace suite green (3507 tests, 4 hardware-gated skips).

1. **Workspace prep** — bump `requires-python` to `>=3.12` across the workspace; extend the namespace-init guard for `src/oaknut/econet/`.
2. **`oaknut-econet-core`** — addressing, packet, outcome, capability types; the `EconetTransport` ABC; `TestTransport`; the conformance suite. Test-first. No transport deps. *(First vertical slice.)*
3. **`oaknut-econet-aun`** — AUN transport against the core contract (pure UDP, easiest real validation), then `_aun._udp` mDNS. Interop-tested against Beebium.
4. **`oaknut-econet-piconet`** — serial transport; hardware-in-the-loop tests with a real Pico.
5. **`oaknut-econet-hat`** — char-device client; hardware-in-the-loop tests with a real HAT.
6. **Applications** — file server (`&99`) on the AFS/ADFS/DFS backing stores. *Deferred:* a native proxy bridge (model B, `&9C`) once the Piconet firmware delta is done; *parked:* a verbatim bridge (model A) pending dual-ADLC hardware. Separate design docs each.
