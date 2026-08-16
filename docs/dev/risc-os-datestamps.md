# RISC OS / ADFS datestamps: what the value means

Status: settled. Records why oaknut reports ADFS (and PanOS DFS) datestamps
**at face value**, with no timezone or daylight-saving interpretation, and the
authoritative basis for that decision.

For the bit-level packing (the `&FFF` marker, the 12-bit filetype, the 40-bit
centisecond count split across load/exec) see the implementation in
`oaknut.file.datestamp` and `docs/dev/panos-dfs-timestamps.md` for the DFS
variant. This document is only about the **semantics** of the stored instant.

## The question

The field stores a 40-bit count of centiseconds since 1900-01-01 00:00:00, but
the disc records **no timezone**. So what does that instant represent — UTC, or
local wall-clock? And how should a tool display it?

## The authoritative answer

From discussion on Stardot (research by Sophira, and confirmed by Stuart Swales
— the author of the RISC OS filesystem code, which is as authoritative as it
gets):

- **RISC OS 3 and later** store file datestamps in **UTC**. The Filer displays
  them adjusted to the machine's currently-configured timezone **and DST**.
- The adjustment is **proleptic**, not historical: it applies the *current*
  offset to every file regardless of whether DST was actually in force on that
  file's date. So a file saved at 09:00 on 1 February, viewed in June, is shown
  by the Filer as 10:00 on 1 February — wrong by civil time, but a defensible
  choice in the absence of a historical timezone/DST database.
- **RISC OS 2 and earlier** did **not** correct the clock: they used the
  uncorrected system clock, which was **usually set to local time**. Files
  datestamped in the 1980s (Arthur / RISC OS 2 era) are therefore *very likely*
  local-time, not UTC.

So the meaning of the stored instant is **era- and configuration-dependent**,
and nothing on the disc records which convention was used. A 1986 file is most
likely local wall-clock; a modern one is UTC; oaknut cannot tell them apart.

## oaknut's decision: report at face value

oaknut decodes the stored centisecond count to a naive `datetime` and displays
it **verbatim** — no timezone conversion, no DST adjustment, no guess about
which era's convention produced it. Consequences:

- Output is **reproducible** and independent of the host machine's locale,
  timezone, or the season in which you happen to run it. Two people in
  different countries see the same value for the same file.
- It is the **faithful** value: for a local-time-era file it is the wall-clock
  that was really on the clock at save time; for a UTC-era file it is the UTC
  instant. We surface exactly what is on the disc and let the user interpret.
- A RISC OS Filer on a DST-active machine will read **up to an hour ahead** of
  oaknut (it is applying the proleptic local-time adjustment described above).
  This is expected, not a discrepancy in oaknut.

The same face-value policy applies to PanOS DFS timestamps
(`docs/dev/panos-dfs-timestamps.md`), which are additionally lossy and unmarked.

## Crossing into a fixed reference frame: naive is UTC

Reading and display never need a reference frame — and copying a datestamp
between Acorn filesystems does not either, because all of them (ADFS, AFS,
PanOS DFS) store **floating** wall-clock values with no fixed instant, so an
Acorn→Acorn copy is a pure passthrough.

A frame only has to be chosen when a datestamp crosses into a filesystem that
stores an **absolute** instant. The first such case is the **host filesystem**:
POSIX `mtime` is seconds since 1970 in **UTC**. So the question arises if/when
oaknut preserves datestamps as host modification times across the host
boundary, or vice versa — that is, on any of the four host-boundary commands
`disc get`, `disc put`, `disc export` and `disc import` (`get`/`put` are the
single-file forms of `export`/`import`, and cross exactly the same boundary).

**Decision — the default is: interpret a naive Acorn datestamp as UTC.** That
is, the stored wall-clock digits are taken to *be* UTC, with **no numeric
shift** — crossing the floating↔absolute boundary only attaches or strips a
`UTC` tzinfo; the displayed time never changes. This keeps the conversion
deterministic and independent of the host's locale, consistent with the
face-value policy above. A naive `12:05:10.57` becomes `12:05:10.57Z`, full
stop.

A future **`--assume-timezone`** option on the boundary commands would let a
user override this when they *know* a disc holds local time — for example a
RISC OS 2 / Arthur-era disc known to have been written in `Europe/London` —
shifting the value accordingly. Absent that flag, naive means UTC.

This is the intended model; it is **not yet implemented**, because no current
filesystem uses a non-floating frame and there is therefore nothing to convert.
When host-mtime preservation is built, the planned shape is: the `Datestamped`
capability gains a `datestamp_reference` (FLOATING vs UTC) so each filesystem
declares its frame; same-frame copies stay passthrough; cross-frame conversion
lives in the boundary layer and applies the naive-is-UTC default above.

## When a load/exec pair *is* a datestamp

Separate from what the instant means is the prior question of whether the
load/exec pair should be read as a filetype + datestamp at all. The `&FFF`
marker (top twelve bits of the load address set) is necessary but **not
sufficient**: it overlaps genuine addresses. RISC OS FileSwitch treats a
pair as *not* datestamped when any of these hold (from the FileSwitch source,
quoted by Gerald Holdsworth on Stardot):

| load | exec | meaning |
|---|---|---|
| `&00000000` | `&FFFFFFFF` | command file |
| `&FFFFFFFF` | `&FFFFFFFF` | command file |
| `< &FFF00000` | any | load/exec address pair (no marker) |
| `nnnnnnnn` | `nnnnnnnn` (load == exec) | address pair (e.g. a BBC `&FFFF0900`) |

All four collapse to one condition: **datestamped iff the marker is set *and*
`load != exec`.** oaknut encodes exactly this in
`oaknut.file.datestamp.is_datestamped(load, exec)`, used by `decode_datestamp`
and by the ADFS/AFS filesystem mounts. Without the `load != exec` clause a
module load address such as `&FFFFFA00/&FFFFFA00` decodes to a spurious date
in the 1900–1901 window (the only range a 32-bit exec word reaches when the
load's low byte — the datestamp's top eight bits — is zero); genuine Acorn
dates cannot fall there, since the hardware postdates the 1980s.

oaknut deliberately does **not** adopt J.G.Harston's stricter, size-dependent
heuristics (rejecting `exec == &FFFFFFFF`, or `load == &FFFFxxxx` with `exec`
inside the loaded image, or `load` in `&FFFF3000..&FFFF7FFF`). They exceed what
FileSwitch does and can hide genuine early dates; the `--metadata-lens=addresses`
override already covers any residual coincidence.

Note this rule is the **display / interpretation** rule for a live filesystem.
The archival conventions (SparkFS extra fields, INF sidecars, RISC OS filename
suffixes) record a filetype from the bare marker even for a `load == exec`
pair — real archives (e.g. the SJ Research NetUtils Econet commands, all
`&FFFF0Exx/&FFFF0Exx`) depend on it for a faithful round-trip — so
`AcornMeta.is_filetype_stamped` stays the pure structural marker and the
`load != exec` rule lives in the datestamp/mount layer.

## Sources

- Stardot thread "oaknut-disc : DFS, ADFS and AFS0 (L3FS) tools", June 2026 —
  Sophira's research that RISC OS stores datestamps in UTC and the Filer
  applies the prevailing (proleptic) timezone + DST on display; and Stuart
  Swales's clarification that RISC OS 2 and earlier used the uncorrected,
  usually local-time, system clock.
- Same thread, July 2026 — Gerald Holdsworth quoting the RISC OS FileSwitch
  source for the "not date stamped" cases, and J.G.Harston's stricter
  heuristic, prompted by acheton1984's Disc Image Manager (DIM) report.
