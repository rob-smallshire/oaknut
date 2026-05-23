"""AFSPath.export_file / import_file — symmetric host-bridge methods.

Mirrors the DFSPath.export_file / import_file and
ADFSPath.export_file / import_file coverage. Cover the round-trip
through each :class:`oaknut.file.MetaFormat` and assert the AFS-specific
access translation lands as expected.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs import AFSAccess
from oaknut.file import Access, MetaFormat


class TestExportFile:
    def test_export_writes_data_and_inf_sidecar(self, tmp_path: Path) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "Greeting"
        path.write_bytes(b"hi from AFS", load_address=0x1900, exec_address=0x8023)
        out = tmp_path / "Greeting"
        result = path.export_file(out, meta_format=MetaFormat.INF_TRAD)
        assert result == out
        assert out.read_bytes() == b"hi from AFS"
        inf = out.with_suffix(out.suffix + ".inf")
        assert inf.exists()
        assert "00001900" in inf.read_text()

    def test_export_root_raises(self, tmp_path: Path) -> None:
        from oaknut.afs.exceptions import AFSPathError

        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError, match="root"):
            afs.root.export_file(tmp_path / "out")

    def test_export_no_metadata_writes_only_data(self, tmp_path: Path) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "DataOnly"
        path.write_bytes(b"\x00\x01\x02", load_address=0xCAFE)
        out = tmp_path / "DataOnly"
        path.export_file(out, meta_format=None)
        assert out.read_bytes() == b"\x00\x01\x02"
        # No sidecar emitted.
        assert not out.with_suffix(out.suffix + ".inf").exists()


class TestImportFile:
    def test_import_with_inf_sidecar_round_trips_metadata(
        self, tmp_path: Path
    ) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        host = tmp_path / "Hello"
        host.write_bytes(b"Hello AFS")
        inf = host.with_suffix(host.suffix + ".inf")
        # Traditional INF: filename load exec length access
        inf.write_text("Hello 00001900 00008023 00000009 03\n")
        path = afs.root / "Hello"
        path.import_file(host)
        assert path.read_bytes() == b"Hello AFS"
        st = path.stat()
        assert st.load_address == 0x1900
        assert st.exec_address == 0x8023

    def test_import_no_sidecar_uses_zeros(self, tmp_path: Path) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        host = tmp_path / "Plain"
        host.write_bytes(b"plain")
        path = afs.root / "Plain"
        path.import_file(host)
        assert path.read_bytes() == b"plain"
        st = path.stat()
        assert st.load_address == 0
        assert st.exec_address == 0

    def test_import_root_raises(self, tmp_path: Path) -> None:
        from oaknut.afs.exceptions import AFSPathError

        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        host = tmp_path / "x"
        host.write_bytes(b"x")
        with pytest.raises(AFSPathError, match="root"):
            afs.root.import_file(host)


class TestRoundTrip:
    def test_export_then_import_preserves_data_and_addresses(
        self, tmp_path: Path
    ) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        original = afs.root / "Original"
        original.write_bytes(
            b"round trip payload",
            load_address=0x1234,
            exec_address=0xCAFE,
        )

        out = tmp_path / "Original"
        original.export_file(out, meta_format=MetaFormat.INF_PIEB)

        # Bring it back into a sibling AFS path.
        restored = afs.root / "Restored"
        restored.import_file(out, meta_formats=[MetaFormat.INF_PIEB])

        assert restored.read_bytes() == b"round trip payload"
        st = restored.stat()
        assert st.load_address == 0x1234
        assert st.exec_address == 0xCAFE

    def test_export_then_import_preserves_locked_attribute(
        self, tmp_path: Path
    ) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        original = afs.root / "Locked"
        original.write_bytes(b"locked content", access=AFSAccess.from_string("LR/"))
        out = tmp_path / "Locked"
        original.export_file(out, meta_format=MetaFormat.INF_PIEB)

        restored = afs.root / "Restored"
        restored.import_file(out, meta_formats=[MetaFormat.INF_PIEB])
        assert restored.stat().afs_access & AFSAccess.LOCKED
