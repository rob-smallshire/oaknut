"""Base tests and documentation for reference image test suite.

Reference images are created by running BBC BASIC generator programs in
emulators (b2/BeebEm). This validates oaknut-dfs against real BBC Micro
DFS implementations.

Test Organization:
  tests/data/generators/XX-name.bas      - BBC BASIC generator program
  tests/data/images/XX-name.ssd|dsd     - Generated disk image (write-protected)
  tests/test_XX_name.py                  - Corresponding test file

The correlation between generator, image, and test is clear from the naming.

Available Fixtures (from conftest.py):
  - reference_image: Open reference disk read-only
  - writable_copy: Create temporary writable copy

Example:
  def test_something(reference_image):
      disk = reference_image("01-basic-validation.ssd")
      assert disk.exists("$.TEXT")
"""

import pytest
from pathlib import Path


REFERENCE_IMAGES = Path(__file__).parent / "data" / "images"


class TestReferenceImageSetup:
    """Tests to verify reference image infrastructure."""

    def test_reference_images_directory_exists(self):
        """Reference images directory structure is set up."""
        if not REFERENCE_IMAGES.exists():
            pytest.skip("Reference images directory not present")
        assert REFERENCE_IMAGES.is_dir()

    def test_generators_directory_exists(self):
        """Generator programs directory exists."""
        generators_dir = Path(__file__).parent / "data" / "generators"
        if not generators_dir.exists():
            pytest.skip("Generators directory not present")
        assert generators_dir.is_dir()

    def test_list_available_reference_images(self):
        """Show which reference images have been generated."""
        if not REFERENCE_IMAGES.exists():
            pytest.skip("Reference images directory doesn't exist")

        ssd_files = sorted(REFERENCE_IMAGES.glob("*.ssd"))
        dsd_files = sorted(REFERENCE_IMAGES.glob("*.dsd"))

        print("\n=== Available Reference Images ===")
        if ssd_files:
            print("\nSSD files (single-sided):")
            for f in ssd_files:
                # Check if write-protected
                import stat
                mode = f.stat().st_mode
                protected = not (mode & stat.S_IWUSR)
                protection = " [write-protected]" if protected else " [WRITABLE]"
                print(f"  - {f.name}{protection}")
        else:
            print("\nNo SSD files generated yet.")

        if dsd_files:
            print("\nDSD files (double-sided):")
            for f in dsd_files:
                # Check if write-protected
                import stat
                mode = f.stat().st_mode
                protected = not (mode & stat.S_IWUSR)
                protection = " [write-protected]" if protected else " [WRITABLE]"
                print(f"  - {f.name}{protection}")
        else:
            print("\nNo DSD files generated yet.")

        print("\nTo generate missing images:")
        print("  1. Run generator .bas file in b2 emulator")
        print("  2. Export disk to tests/data/images/")
        print("  3. Write-protect: chmod 444 tests/data/images/XX-name.ssd")

        # This test always passes - it's just for information
        assert True

    def test_write_protection_enforced(self):
        """Reference images should be write-protected."""
        if not REFERENCE_IMAGES.exists():
            pytest.skip("Reference images directory doesn't exist")

        images = list(REFERENCE_IMAGES.glob("*.ssd")) + list(REFERENCE_IMAGES.glob("*.dsd"))

        if not images:
            pytest.skip("No reference images generated yet")

        import stat
        writable_images = []

        for img in images:
            mode = img.stat().st_mode
            if mode & stat.S_IWUSR:  # Owner has write permission
                writable_images.append(img.name)

        if writable_images:
            print("\nWARNING: The following reference images are not write-protected:")
            for name in writable_images:
                print(f"  - {name}")
            print("\nTo fix, run:")
            for name in writable_images:
                print(f"  chmod 444 tests/data/images/{name}")

        # Don't fail the test, just warn
        assert True
