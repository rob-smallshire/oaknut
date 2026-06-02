# oaknut-econet-hat

The **PiEconetHAT** transport for the `oaknut-econet` family — a user-space
client of the `econet-gpio` Linux kernel module that drives a Raspberry Pi HAT
carrying a real MC68B54 ADLC.

The kernel module runs the Econet four-way handshake in its interrupt handler
and exposes a character device, `/dev/econet-gpio`, through which user space
reads and writes AUN-format packets (`struct __econet_packet_aun`) and issues
ioctls (station-interest map, AUN mode, TX status, …). This package provides:

- the kernel packet-struct codec and the mapping to/from
  `oaknut.econet.core.EconetPacket`,
- `HatTransport`, an `EconetTransport` driven over a `KernelDevice`, and
- **`FakeKernelDevice`** — an in-process simulation of the char device, so the
  transport is fully testable in CI with no hardware.

The real device (`EconetGpioDevice`) uses only the standard library
(`os`/`fcntl`/`struct`); it is Linux-only at runtime and needs the `econet-gpio`
module loaded and the HAT present. It registers on the
`oaknut.econet.transport` axis as `hat`. The design — and the goal of cleanly
superseding PiEconetBridge — is in `docs/dev/econet-design.md`.
