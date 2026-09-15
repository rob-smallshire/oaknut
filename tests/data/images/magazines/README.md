# Magazine cover-disc fixtures

A curated dozen 1980s BBC Micro / Acorn magazine cover discs, used by the
`disc gather` tests and the CLI cookbook's "gather" recipe. They give a
realistic, mixed-filesystem corpus for consolidating many floppies into
one image:

- `micro-user/` — *The Micro User* cover discs, Acorn DFS (`.ssd`).
- `a-and-b/` — *A&B Computing* cover discs, Acorn DFS (`.ssd`).
- `acorn-user/` — *Acorn User* cover discs, ADFS-L (`.adl`).

The mix is deliberate: DFS and ADFS sources exercise same-filesystem and
cross-filesystem gathering, and the on-disc titles are inconsistent with
the filenames (e.g. `D-MU05_01.ssd` is titled `MU05_11`), which is why
`disc gather` names directories from the host filename by default.

Provenance: the *owl-basic* local BASIC corpus. These are cover discs of
long-defunct magazines with no history of rights enforcement, retained
here purely as test data.
