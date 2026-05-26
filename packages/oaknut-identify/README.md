# oaknut-identify

Content-based identification of Acorn disc-image formats.

Disc-image file extensions (`.ssd`, `.dsd`, `.adf`, `.adl`, `.dat`, …) are
conventions, and they are frequently missing or wrong. This package answers
the question *"what is actually in this image?"* by reading the bytes, not by
trusting the name.

Identification runs a **cascade of probers** — pluggable detectors, one per
format, discovered through the `oaknut.prober` entry-point namespace (built on
`oaknut-extension`). Each prober inspects cheap, fixed regions of the image
(magic numbers, catalogue structure, free-space-map checksums) and emits zero
or more ranked `Identification` candidates carrying:

- the **family** (`dfs`, `adfs`, `afs`, `zip`, …) and the prober that matched,
- a **confidence** level — from `CERTAIN` (an unambiguous magic number) down to
  `POSSIBLE` (only weak signals such as size),
- human-readable **evidence** for *why* it matched,
- the concrete `DiscFormat` when geometry is determinable, plus any
  equally-plausible `alternatives` (e.g. interleaved vs. sequential, which are
  byte-for-byte indistinguishable), and
- any **contained** sub-identifications (e.g. an ADFS host with an AFS tail).

```python
from oaknut.identify import identify

for candidate in identify("mystery.img"):
    print(candidate.family, candidate.confidence.name, candidate.evidence)
```

The file extension is treated as a *prior* that breaks ties between
equally-confident candidates — never as the authority.

Probers are registered by the format packages themselves (`oaknut-dfs`,
`oaknut-adfs`, …), so a newly-installed format package adds its detector to the
cascade automatically.
