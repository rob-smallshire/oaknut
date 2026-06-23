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

## Sources

- Stardot thread "oaknut-disc : DFS, ADFS and AFS0 (L3FS) tools", June 2026 —
  Sophira's research that RISC OS stores datestamps in UTC and the Filer
  applies the prevailing (proleptic) timezone + DST on display; and Stuart
  Swales's clarification that RISC OS 2 and earlier used the uncorrected,
  usually local-time, system clock.
