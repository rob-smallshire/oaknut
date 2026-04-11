"""UnifiedDisc: presents multiple surfaces as a single linear disc address space.

ADFS treats both sides of a double-sided floppy as a single logical disc.
Sectors are numbered sequentially: all of side 0 (tracks 0..N), then all
of side 1 (tracks 0..N). UnifiedDisc translates these unified sector numbers
to the correct (surface_index, surface_sector) pair and delegates to Surface.

For single-sided discs, this is a trivial pass-through.
"""

from __future__ import annotations

from oaknut_dfs.sectors_view import SectorsView
from oaknut_dfs.surface import DiscImage


class UnifiedDisc:
    """Presents multiple surfaces as a single linear sector address space."""

    def __init__(self, disc_image: DiscImage):
        self._disc_image = disc_image

        # Build cumulative sector boundaries for each surface
        # e.g. for two surfaces of 1280 sectors each: [0, 1280, 2560]
        self._boundaries: list[int] = [0]
        for i in range(disc_image.num_surfaces):
            surface = disc_image.surface(i)
            self._boundaries.append(self._boundaries[-1] + surface.num_sectors)

        # Validate all surfaces have the same bytes_per_sector
        bps_values = {
            disc_image.surface(i).bytes_per_sector
            for i in range(disc_image.num_surfaces)
        }
        if len(bps_values) != 1:
            raise ValueError(
                f"All surfaces must have the same bytes_per_sector, got {bps_values}"
            )
        self._bytes_per_sector = bps_values.pop()

    @property
    def num_sectors(self) -> int:
        """Total sectors across all surfaces."""
        return self._boundaries[-1]

    @property
    def num_bytes(self) -> int:
        """Total bytes across all surfaces."""
        return self.num_sectors * self._bytes_per_sector

    @property
    def bytes_per_sector(self) -> int:
        return self._bytes_per_sector

    def _locate(self, unified_sector: int) -> tuple[int, int]:
        """Map a unified sector number to (surface_index, surface_sector).

        Raises:
            ValueError: If sector number is out of range.
        """
        if unified_sector < 0 or unified_sector >= self.num_sectors:
            raise ValueError(
                f"Sector {unified_sector} out of range (0-{self.num_sectors - 1})"
            )
        for i in range(len(self._boundaries) - 1):
            if unified_sector < self._boundaries[i + 1]:
                return i, unified_sector - self._boundaries[i]
        raise ValueError(
            f"Sector {unified_sector} out of range (0-{self.num_sectors - 1})"
        )

    def sector_range(self, start_sector: int, num_sectors: int) -> SectorsView:
        """Read/write sectors from the unified address space.

        Handles ranges that span the boundary between surfaces by combining
        SectorsViews from each surface.

        Args:
            start_sector: First unified sector number (0-based).
            num_sectors: Number of sectors to include.

        Returns:
            SectorsView wrapping the requested sector range.

        Raises:
            ValueError: If range is invalid or out of bounds.
        """
        if num_sectors <= 0:
            raise ValueError(f"num_sectors must be positive, got {num_sectors}")
        if start_sector < 0 or start_sector + num_sectors > self.num_sectors:
            raise ValueError(
                f"Sector range [{start_sector}, {start_sector + num_sectors}) "
                f"exceeds disc bounds (0-{self.num_sectors})"
            )

        # Collect sector views, splitting at surface boundaries
        all_views: list[memoryview] = []
        remaining = num_sectors
        current_sector = start_sector

        while remaining > 0:
            surface_idx, surface_sector = self._locate(current_sector)
            surface = self._disc_image.surface(surface_idx)

            # How many sectors can we take from this surface?
            available = surface.num_sectors - surface_sector
            take = min(remaining, available)

            view = surface.sector_range(surface_sector, take)
            # SectorsView wraps memoryviews; extract them
            all_views.extend(view._views)

            current_sector += take
            remaining -= take

        return SectorsView(all_views)
