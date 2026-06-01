"""AFS preserves filename case on write, matching case-insensitively.

AFS encodes a name as ASCII verbatim (space-padded) and folds case only
when comparing, so the case the caller gave is recorded and lookup is
case-insensitive — oaknut must not upper-case names into the directory.
"""

from __future__ import annotations

from helpers.afs_image import build_synthetic_adfs_with_afs


class TestCaseIsPreserved:
    def test_mixed_case_name_stored_verbatim(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        (afs.root / "MixedCase").write_bytes(b"x")
        names = [p.name for p in afs.root]
        assert "MixedCase" in names
        assert "MIXEDCASE" not in names

    def test_lookup_is_case_insensitive(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        (afs.root / "MixedCase").write_bytes(b"data")
        assert (afs.root / "MIXEDCASE").read_bytes() == b"data"
        assert (afs.root / "mixedcase").read_bytes() == b"data"
