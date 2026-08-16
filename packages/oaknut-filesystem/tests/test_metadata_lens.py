"""The metadata-presentation lens capability.

A mount may declare how its load/exec fields should be read by default:
as raw ``addresses`` (DFS, 8-bit ADFS) or as a RISC OS filetype and
datestamp folded into them (``type-date`` — Arthur/RISC OS ADFS). The
CLI resolves ``--metadata=auto`` against this, and treats a mount that
does not implement the capability as ``addresses``.
"""

from oaknut.filesystem import Lens, MetadataLensed


class _Lensed:
    def __init__(self, lens: Lens) -> None:
        self._lens = lens

    @property
    def metadata_lens(self) -> Lens:
        return self._lens


class _Plain:
    """A mount with no lens preference."""


def test_lens_values_are_the_cli_vocabulary():
    assert Lens.ADDRESSES.value == "addresses"
    assert Lens.TYPE_DATE.value == "type-date"


def test_lensed_mount_is_recognised():
    assert isinstance(_Lensed(Lens.TYPE_DATE), MetadataLensed)


def test_mount_without_lens_is_not_recognised():
    assert not isinstance(_Plain(), MetadataLensed)


def test_reported_lens_round_trips():
    assert _Lensed(Lens.ADDRESSES).metadata_lens is Lens.ADDRESSES
    assert _Lensed(Lens.TYPE_DATE).metadata_lens is Lens.TYPE_DATE
