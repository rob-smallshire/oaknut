# PanOS timestamps on DFS discs

Status: research notes, not implemented. Captured to record what is known
about how PanOS stores file timestamps in the DFS load/exec fields, and why
oaknut does **not** yet decode them. Awaiting more data (ideally captured
from PanOS running under emulation onto a DFS disc) before any design work.

This document is reverse-engineered from third-party notes, not a
specification. Where the sources hedge ("seems to", "realistic"), so does
this document — those parts are **unverified**.

## Background

PanOS is the operating system of the Acorn 32016 Second Processor. It has no
filing system of its own; file operations are delegated to the host BBC
Micro's filing system — DFS, ADFS, or NFS. When PanOS writes a file it stamps
it with a timestamp, stored (like RISC OS) inside the host catalogue's
load/exec address fields.

On **ADFS** (and any filing system with full 32-bit load/exec) PanOS uses the
ordinary RISC OS convention: the top twelve bits of the load address are
`&FFF`, marking the fields as a filetype + datestamp rather than a real
address. That case is handled by oaknut's `Datestamped`/`Filetyped`
capabilities — see the RISC OS datestamp codec in `oaknut.file.datestamp` and
the design notes alongside the ADFS/AFS work.

On **DFS** the fields are only 18 bits each, far too few for a 40-bit RISC OS
timestamp plus a 12-bit filetype and the `&FFF` marker. PanOS therefore stores
a **compressed, unmarked** timestamp instead. That is the subject of this
document.

## The timestamp

The RISC OS timestamp is a 40-bit (5-byte) count of centiseconds since
1900-01-01 00:00:00.00 — the same epoch oaknut already uses for ADFS.

## The DFS packing

PanOS drops the lowest byte of the 5-byte timestamp and splits the remaining
four bytes across the two 18-bit fields:

```
timestamp   &44 33 22 11 00      (byte 4 = MSB … byte 0 = LSB)

LOAD   = &xxxx4433               low 16 bits = bytes 4 and 3
EXEC   = &xxxx2211               low 16 bits = bytes 2 and 1
                                 byte 0 (LSB) is discarded
```

Dropping the lowest byte means the recorded value advances in steps of 256
centiseconds — a resolution of **2.56 seconds** (versus ADFS's 0.01s). The
`xxxx` high nibbles are the 18-bit fields' top bits; their role is one of the
open questions below.

### Two observed variants

Real discs are not consistent. The notes report two load-address patterns:

- most files have `LOAD = &0002xxxx` (e.g. `&00023F05`);
- some have `LOAD = &00007xxx` (e.g. `&00007DAD`), and for these *"dividing
  the load address by 2 seems to give a realistic timestamp"*.

The reconstruction code (BBC BASIC, from the notes) tolerates both by testing
the top two bits of the 18-bit load field:

```basic
mem%?0=0
mem%!1=exec%
IF (load% AND &30000)=0 THEN mem%!3=load% DIV 2 ELSE mem%!3=load%
time0%=mem%!0
time1%=mem%!4
```

That is: byte 0 is forced to zero; `exec%` supplies bytes 1–4; `load%`
(optionally halved) supplies bytes 3–6; and the 5-byte timestamp is read back
as the pair `(time0%, time1%)` with only the low byte of `time1%` significant.
The `÷2` branch for the `&00007xxx` form implies that variant stores the value
shifted left by one bit, but the cause is not established.

## Why oaknut does not decode this (yet)

The decisive difference from the ADFS/RISC OS case is that **a PanOS DFS
timestamp carries no marker**. On ADFS the `&FFF` top-twelve-bits flag says
unambiguously "these fields are a filetype + date, not an address". DFS has no
equivalent: a packed timestamp is byte-for-byte indistinguishable from a
genuine load/exec address. A real BASIC program loaded at `&1900`, a host I/O
address, and a PanOS timestamp all inhabit the same 18-bit space with no flag
to tell them apart.

Consequently oaknut **cannot safely auto-detect** PanOS timestamps: doing so
would misread ordinary load/exec addresses as nonsensical dates (false
positives) and miss genuine timestamps stored with unremarkable-looking values
(false negatives). The source notes themselves resort to "looks realistic"
heuristics rather than a rule, which is not a basis for transparent decoding.

This is also why the `Datestamped` capability is **not** implemented for DFS:
that capability promises a reliable round-trip, which the format cannot offer.

## Open questions

To be resolved with captured data before any implementation:

1. **Is there a marker after all?** Is `&0002xxxx` (bit 17 set, bit 16 clear)
   actually a deliberate PanOS flag for "this is a timestamp", or just an
   artefact of how the value is written? If it is a reliable marker, safe
   detection becomes possible.
2. **What distinguishes the `&0002xxxx` and `&00007xxx` forms?** Different
   PanOS versions? A write path that shifts left by one? A bug? The `÷2`
   correction is currently a guess.
3. **What does the `exec%` high half hold** in practice — always zero, or
   carrying bits that the reconstruction ignores?
4. **How does PanOS itself read these back** — i.e. the authoritative
   algorithm, ideally from PanOS sources or by observation, rather than the
   third-party reconstruction.
5. **Round-trip fidelity:** does writing a 2.56s-resolution value back match
   what PanOS wrote, byte-for-byte? (Relevant to the byte-exact goal.)

## Design options (deferred)

When/if we act, the likely choices are:

- **Leave DFS dates unsupported** (current state) — safest; no risk of
  misreading addresses.
- **Explicit, opt-in decode** — a flag (e.g. `--panos-dates`) on the read
  commands, or a standalone `decode_panos_dfs(load, exec)` helper in
  `oaknut.file.datestamp`, kept separate from the marker-based RISC OS codec
  and clearly labelled lossy (2.56s) and best-effort. The user asserts the
  interpretation; oaknut never guesses.
- **Heuristic auto-detection** — not recommended given the sources' own
  uncertainty.

## Sources

- J.G.Harston, stardot forum:
  <https://stardot.org.uk/forums/viewtopic.php?p=485883#p485883> — "Note that
  PanOS will also store the 5-byte timestamp on DFS disks as well in a
  compressed form that fits into the 18-bit load/exec addresses."
- 32016 Co-Processor notes:
  <https://mdfs.net/Docs/Books/32016CoPro/Notes.txt> — the packing, the two
  observed variants, and the reconstruction code quoted above.
