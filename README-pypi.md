# oaknut

This distribution is a **namespace placeholder**. It ships no code and has no
runtime dependencies. It exists so that the `oaknut` name on PyPI is owned by
the same project that publishes the `oaknut-*` family of packages.

You almost certainly want one of:

| Package | Purpose |
|---|---|
| [`oaknut-adfs`](https://pypi.org/project/oaknut-adfs/) | Acorn ADFS disc image support for Archimedes, RISC OS, and BBC Master |
| [`oaknut-afs`](https://pypi.org/project/oaknut-afs/) | Acorn Level 3 File Server (AFS) filesystem support — the private on-disc format WFSINIT prepares in the tail of an old-map ADFS disc |
| [`oaknut-basic`](https://pypi.org/project/oaknut-basic/) | BBC BASIC tools: program tokeniser/de-tokeniser and PRINT#/INPUT# data-file reader/writer |
| [`oaknut-cli`](https://pypi.org/project/oaknut-cli/) | Shared CLI toolkit for the oaknut family: the contributed-command axis and report-rendering helpers a disc command needs, below the filesystem packages |
| [`oaknut-codecs`](https://pypi.org/project/oaknut-codecs/) | Text codecs for Acorn computer character sets (BBC Micro / Electron) |
| [`oaknut-dfs`](https://pypi.org/project/oaknut-dfs/) | Python library for handling Acorn DFS disc images (SSD/DSD format) |
| [`oaknut-disc`](https://pypi.org/project/oaknut-disc/) | CLI for working with Acorn DFS, ADFS, and AFS disc images |
| [`oaknut-discimage`](https://pypi.org/project/oaknut-discimage/) | Disc image sector abstractions shared by Acorn filesystem packages |
| [`oaknut-econet-aun`](https://pypi.org/project/oaknut-econet-aun/) | AUN (Acorn Universal Networking) transport for oaknut-econet: logical Econet over UDP/IP, with optional mDNS station discovery |
| [`oaknut-econet-core`](https://pypi.org/project/oaknut-econet-core/) | Core abstractions for Econet networking in the oaknut family: packet types, addressing, the EconetTransport interface, capabilities, and an in-process test transport |
| [`oaknut-econet-hat`](https://pypi.org/project/oaknut-econet-hat/) | PiEconetHAT transport for oaknut-econet: a user-space client of the econet-gpio kernel module, with a fake kernel device for hardware-free testing |
| [`oaknut-econet-host`](https://pypi.org/project/oaknut-econet-host/) | The econet-host program: a CLI that configures Econet transports and service plug-ins and runs a station |
| [`oaknut-econet-kvstore`](https://pypi.org/project/oaknut-econet-kvstore/) | A tiny key-value store over Econet — the worked-example oaknut-econet application: a Service plug-in (server) and a matching client |
| [`oaknut-econet-piconet`](https://pypi.org/project/oaknut-econet-piconet/) | Piconet transport for oaknut-econet: a Raspberry Pi Pico serial-to-Econet adapter, with a fake Piconet for hardware-free testing |
| [`oaknut-econet-station`](https://pypi.org/project/oaknut-econet-station/) | The Econet service host for oaknut: a Station that dispatches inbound packets by port to registered Services, the foundation for Econet applications |
| [`oaknut-exception`](https://pypi.org/project/oaknut-exception/) | Categorised exceptions and CLI error-reporting boundary for the oaknut package family |
| [`oaknut-extension`](https://pypi.org/project/oaknut-extension/) | Entry-point plug-in framework shared by every extensible axis of the oaknut package family |
| [`oaknut-file`](https://pypi.org/project/oaknut-file/) | Acorn file metadata handling: INF sidecars, filename encoding, xattrs, and access flags |
| [`oaknut-filesystem`](https://pypi.org/project/oaknut-filesystem/) | The pluggable filesystem contract for the oaknut family: detection, capabilities, geometry, partitions, and the identification coordinator |
| [`oaknut-hfe`](https://pypi.org/project/oaknut-hfe/) | Python library for reading HFE (HxC Floppy Emulator) flux-level disc images |
| [`oaknut-romfs`](https://pypi.org/project/oaknut-romfs/) | Python library for Acorn ROM Filing System (ROMFS) paged-ROM images |
| [`oaknut-zip`](https://pypi.org/project/oaknut-zip/) | Work with ZIP files containing Acorn computer metadata |

Source: https://github.com/rob-smallshire/oaknut
