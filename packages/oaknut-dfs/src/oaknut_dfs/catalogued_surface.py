"""Generic file operations layer for catalogued surfaces."""

from typing import Type

from oaknut_dfs.catalogue import Catalogue, FileEntry
from oaknut_dfs.surface import Surface


class CataloguedSurface:
    """
    A surface with a catalog providing file operations.

    This is a generic class that works with any Catalogue implementation.
    """

    def __init__(self, surface: Surface, catalogue_class: Type[Catalogue]):
        """
        Initialize with a surface and catalog class.

        Args:
            surface: The surface to use
            catalogue_class: Catalogue class (not instance) - e.g., AcornDFSCatalogue
        """
        self._surface = surface
        self._catalogue = catalogue_class(surface)  # Instantiate catalog

    # Delegate catalog operations
    def list_files(self) -> list[FileEntry]:
        """List all files."""
        return self._catalogue.list_files()

    def find_file(self, filename: str):
        """Find file by name."""
        return self._catalogue.find_file(filename)

    @property
    def disk_info(self):
        """Get disk info."""
        return self._catalogue.get_disk_info()

    @property
    def catalogue(self) -> Catalogue:
        """Access to underlying catalogue."""
        return self._catalogue

    # File operations
    def read_file(self, filename: str) -> bytes:
        """Read file data by filename."""
        entry = self._catalogue.find_file(filename)
        if entry is None:
            raise FileNotFoundError(f"File not found: {filename}")

        # Read file sectors using Surface
        file_sectors = self._surface.sector_range(
            entry.start_sector, entry.sectors_required
        )

        # Return exact file length (trim sector padding)
        return file_sectors.tobytes()[: entry.length]

    def write_file(
        self,
        filename: str,
        directory: str,
        data: bytes,
        load_address: int,
        exec_address: int,
        locked: bool = False,
    ) -> None:
        """Write a new file."""
        # Find free space using First Fit algorithm
        start_sector = self._first_fit(len(data))

        # Write data to sectors (pad to sector boundary)
        sectors_needed = (len(data) + 255) // 256
        padded_data = data.ljust(sectors_needed * 256, b"\x00")

        file_sectors = self._surface.sector_range(start_sector, sectors_needed)
        file_sectors[:] = padded_data

        # Add catalog entry
        self._catalogue.add_file_entry(
            filename=filename,
            directory=directory,
            load_address=load_address,
            exec_address=exec_address,
            length=len(data),
            start_sector=start_sector,
            locked=locked,
        )

    def delete_file(self, filename: str) -> None:
        """Delete a file."""
        self._catalogue.remove_file_entry(filename)

    @property
    def free_sectors(self) -> int:
        """Get number of free sectors."""
        total_sectors = self._surface.num_sectors

        # Count used sectors
        used_sectors = self._catalogue.CATALOG_NUM_SECTORS
        for entry in self._catalogue.list_files():
            used_sectors += entry.sectors_required

        return total_sectors - used_sectors

    def get_free_map(self) -> list[tuple[int, int]]:
        """
        Get list of free space regions.

        Returns:
            List of (start_sector, length) tuples for contiguous free regions
        """
        # Build used sector map
        used_sectors = set()

        # Catalog sectors
        catalog_end = (
            self._catalogue.CATALOG_START_SECTOR + self._catalogue.CATALOG_NUM_SECTORS
        )
        for sector in range(self._catalogue.CATALOG_START_SECTOR, catalog_end):
            used_sectors.add(sector)

        # File sectors
        for entry in self._catalogue.list_files():
            for sector in range(
                entry.start_sector, entry.start_sector + entry.sectors_required
            ):
                used_sectors.add(sector)

        # Find contiguous free regions
        free_regions = []
        in_free_region = False
        region_start = 0
        region_length = 0

        for sector in range(self._surface.num_sectors):
            if sector in used_sectors:
                if in_free_region:
                    free_regions.append((region_start, region_length))
                    in_free_region = False
            else:
                if not in_free_region:
                    region_start = sector
                    region_length = 1
                    in_free_region = True
                else:
                    region_length += 1

        # Don't forget final region
        if in_free_region:
            free_regions.append((region_start, region_length))

        return free_regions

    def _first_fit(self, bytes_needed: int) -> int:
        """
        Find contiguous free space using First Fit algorithm.

        First Fit searches from the beginning of the disk and returns the
        first gap large enough to hold the file.

        Args:
            bytes_needed: Number of bytes to allocate

        Returns:
            Start sector of the first suitable free space

        Raises:
            IOError: If no contiguous space large enough is found
        """
        sectors_needed = (bytes_needed + 255) // 256

        # Build used sector map
        used_sectors = set()

        # Catalog sectors are always used
        catalog_end = (
            self._catalogue.CATALOG_START_SECTOR + self._catalogue.CATALOG_NUM_SECTORS
        )
        for sector in range(self._catalogue.CATALOG_START_SECTOR, catalog_end):
            used_sectors.add(sector)

        # Mark file sectors as used
        for entry in self._catalogue.list_files():
            for sector in range(
                entry.start_sector, entry.start_sector + entry.sectors_required
            ):
                used_sectors.add(sector)

        # Find first contiguous gap
        current_sector = 0
        consecutive_free = 0

        for sector in range(self._surface.num_sectors):
            if sector in used_sectors:
                consecutive_free = 0
            else:
                if consecutive_free == 0:
                    current_sector = sector
                consecutive_free += 1

                if consecutive_free >= sectors_needed:
                    return current_sector

        raise IOError(
            f"Not enough contiguous free space ({sectors_needed} sectors needed)"
        )
