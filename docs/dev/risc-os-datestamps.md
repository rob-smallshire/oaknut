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
oaknut preserves datestamps as host modification times (e.g. on `disc export` /
`disc import`), or vice versa.

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

## Sources

- Stardot thread "oaknut-disc : DFS, ADFS and AFS0 (L3FS) tools", June 2026 —
  Sophira's research that RISC OS stores datestamps in UTC and the Filer
  applies the prevailing (proleptic) timezone + DST on display; and Stuart
  Swales's clarification that RISC OS 2 and earlier used the uncorrected,
  usually local-time, system clock.
