"""Command-line interface for oaknut-dfs.

Provides BBC Micro DFS-style commands for managing disk images.
"""

import sys
from pathlib import Path
from typing import Optional

import click

from oaknut_dfs.dfs_filesystem import DFSImage, BootOption
from oaknut_dfs.exceptions import InvalidFormatError


@click.group()
@click.version_option()
def cli():
    """Acorn DFS disk image tool.

    Manage BBC Micro/Acorn Electron DFS disk images (SSD/DSD format).
    Commands mirror BBC Micro DFS star commands where applicable.
    """
    pass


# ========== Disk Information ==========


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def cat(image_path, side):
    """List files on disk (*CAT equivalent).

    Displays disk title, boot option, and file catalog.
    For DSD (double-sided) disks, use --side to select which side to list.
    """
    try:
        disk = DFSImage.open(image_path, writable=False, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Display disk info
    click.echo(f"\nDisk: {disk.title}")
    click.echo(f"Boot option: {disk.boot_option.name}")
    click.echo(f"Free space: {disk.free_bytes:,} bytes ({disk.free_sectors} sectors)")
    click.echo()

    # Display files
    if len(disk.files) == 0:
        click.echo("(empty disk)")
    else:
        click.echo("Files:")
        for file in disk.files:
            locked = "L" if file.locked else " "
            load_hex = f"{file.load_address:08X}"
            exec_hex = f"{file.exec_address:08X}"
            click.echo(
                f"  {file.name:12} {locked} {file.length:6} bytes  "
                f"Load: {load_hex}  Exec: {exec_hex}"
            )
    click.echo()


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def info(image_path, side):
    """Show detailed disk information (*INFO equivalent).

    For DSD (double-sided) disks, use --side to select which side to display.
    """
    try:
        disk = DFSImage.open(image_path, writable=False, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    info_obj = disk.info

    click.echo("\nDisk Information:")
    click.echo(f"  Path: {image_path}")
    click.echo(f"  Format: {info_obj.format}")
    click.echo(f"  Title: {info_obj.title}")
    click.echo(f"  Boot option: {info_obj.boot_option.name} ({info_obj.boot_option.value})")
    click.echo(f"  Total sectors: {info_obj.num_sectors}")
    click.echo(f"  Free sectors: {info_obj.free_sectors}")
    click.echo(f"  Used sectors: {info_obj.num_sectors - info_obj.free_sectors}")
    click.echo(f"  Files: {info_obj.num_files}")
    click.echo()


# ========== File Operations ==========


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('dfs_filename')
@click.argument('output_path', type=click.Path(), required=False)
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def load(image_path, dfs_filename, output_path, side):
    """Load file from disk (*LOAD equivalent).

    If OUTPUT_PATH is not specified, writes to current directory
    using the DFS filename (with '$.' replaced by '_').
    For DSD (double-sided) disks, use --side to select which side to load from.
    """
    try:
        disk = DFSImage.open(image_path, writable=False, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Load file
    try:
        data = disk.load(dfs_filename)
    except FileNotFoundError:
        click.echo(f"Error: File not found: {dfs_filename}", err=True)
        sys.exit(1)

    # Determine output path
    if output_path is None:
        safe_name = dfs_filename.replace('$', '_').replace('.', '_')
        output_path = Path(safe_name)
    else:
        output_path = Path(output_path)

    # Write file
    output_path.write_bytes(data)
    click.echo(f"Loaded {dfs_filename} → {output_path} ({len(data)} bytes)")


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('source_path', type=click.Path(exists=True))
@click.argument('dfs_filename')
@click.option('--load', 'load_addr', type=str, help='Load address (hex)')
@click.option('--exec', 'exec_addr', type=str, help='Exec address (hex)')
@click.option('--locked', is_flag=True, help='Lock file after saving')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def save(image_path, source_path, dfs_filename, load_addr, exec_addr, locked, side):
    """Save file to disk (*SAVE equivalent).

    Addresses should be specified in hexadecimal (e.g., --load 1900).
    For DSD (double-sided) disks, use --side to select which side to save to.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Parse addresses
    load_address = int(load_addr, 16) if load_addr else 0
    exec_address = int(exec_addr, 16) if exec_addr else 0

    # Read source file
    data = Path(source_path).read_bytes()

    # Save to disk
    try:
        disk.save(
            dfs_filename,
            data,
            load_address=load_address,
            exec_address=exec_address,
            locked=locked
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(
        f"Saved {source_path} → {dfs_filename} "
        f"({len(data)} bytes, load={load_address:08X}, exec={exec_address:08X})"
    )


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('filename')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def delete(image_path, filename, side):
    """Delete file from disk (*DELETE equivalent).

    For DSD (double-sided) disks, use --side to select which side to delete from.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        disk.delete(filename)
        click.echo(f"Deleted {filename}")
    except FileNotFoundError:
        click.echo(f"Error: File not found: {filename}", err=True)
        sys.exit(1)
    except PermissionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('old_name')
@click.argument('new_name')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def rename(image_path, old_name, new_name, side):
    """Rename file (*RENAME equivalent).

    For DSD (double-sided) disks, use --side to select which side to rename on.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        disk.rename(old_name, new_name)
        click.echo(f"Renamed {old_name} → {new_name}")
    except (FileNotFoundError, ValueError, PermissionError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ========== File Attributes ==========


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('filename')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def lock(image_path, filename, side):
    """Lock file (*ACCESS <file> L equivalent).

    For DSD (double-sided) disks, use --side to select which side to lock on.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        disk.lock(filename)
        click.echo(f"Locked {filename}")
    except FileNotFoundError:
        click.echo(f"Error: File not found: {filename}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('filename')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def unlock(image_path, filename, side):
    """Unlock file (*ACCESS <file> equivalent).

    For DSD (double-sided) disks, use --side to select which side to unlock on.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        disk.unlock(filename)
        click.echo(f"Unlocked {filename}")
    except FileNotFoundError:
        click.echo(f"Error: File not found: {filename}", err=True)
        sys.exit(1)


# ========== Disk Management ==========


@cli.command()
@click.argument('image_path', type=click.Path())
@click.option('--title', default='', help='Disk title (max 12 chars)')
@click.option('--tracks', type=int, default=40, help='Number of tracks (40 or 80)')
@click.option('--double-sided', is_flag=True, help='Create double-sided disk (DSD)')
def create(image_path, title, tracks, double_sided):
    """Create new disk image (*FORM equivalent).

    Creates an empty formatted disk image.
    """
    if Path(image_path).exists():
        if not click.confirm(f"{image_path} already exists. Overwrite?"):
            sys.exit(0)

    try:
        disk = DFSImage.create(
            image_path,
            title=title,
            num_tracks=tracks,
            double_sided=double_sided
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    with disk:
        format_str = "DSD (double-sided)" if double_sided else "SSD (single-sided)"
        click.echo(f"Created {format_str} disk: {image_path}")
        click.echo(f"  Title: {disk.title if disk.title else '(none)'}")
        click.echo(f"  Tracks: {tracks}")
        click.echo(f"  Total sectors: {disk.info.num_sectors}")
        click.echo(f"  Capacity: {disk.info.num_sectors * 256:,} bytes")


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('new_title')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def title(image_path, new_title, side):
    """Change disk title (*TITLE equivalent).

    For DSD (double-sided) disks, use --side to select which side's title to change.
    Each side has its own independent title.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        disk.title = new_title
        click.echo(f"Changed title to: {new_title}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command('opt')
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('option', type=click.Choice(['0', '1', '2', '3', 'NONE', 'LOAD', 'RUN', 'EXEC']))
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def boot_option(image_path, option, side):
    """Set boot option (*OPT 4,<n> equivalent).

    Options:
      0/NONE - Do nothing on boot
      1/LOAD - *LOAD $.!BOOT
      2/RUN  - *RUN $.!BOOT
      3/EXEC - *EXEC $.!BOOT

    For DSD (double-sided) disks, use --side to select which side's boot option to set.
    Each side has its own independent boot option.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Map string to BootOption
    option_map = {
        '0': BootOption.NONE, 'NONE': BootOption.NONE,
        '1': BootOption.LOAD, 'LOAD': BootOption.LOAD,
        '2': BootOption.RUN, 'RUN': BootOption.RUN,
        '3': BootOption.EXEC, 'EXEC': BootOption.EXEC,
    }

    boot_opt = option_map[option.upper()]
    disk.boot_option = boot_opt
    click.echo(f"Set boot option to: {boot_opt.name} ({boot_opt.value})")


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def compact(image_path, side):
    """Defragment disk (*COMPACT equivalent).

    Moves files to eliminate gaps from deleted files.
    For DSD (double-sided) disks, use --side to select which side to compact.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        files_moved = disk.compact()
    except PermissionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if files_moved == 0:
        click.echo("Disk already compact (no fragmentation)")
    else:
        click.echo(f"Compacted disk ({files_moved} files moved)")


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def validate(image_path, side):
    """Check disk integrity.

    Validates catalog structure and file layout.
    For DSD (double-sided) disks, use --side to select which side to validate.
    """
    try:
        disk = DFSImage.open(image_path, writable=False, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    errors = disk.validate()
    if not errors:
        click.echo("✓ Disk is valid")
    else:
        click.echo("✗ Disk has errors:", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)


# ========== Batch Operations ==========


@cli.command('export-all')
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('output_dir', type=click.Path())
@click.option('--no-metadata', is_flag=True, help='Skip .inf metadata files')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def export_all(image_path, output_dir, no_metadata, side):
    """Export all files from disk to directory.

    Creates .inf files with load/exec addresses and locked status.
    For DSD (double-sided) disks, use --side to select which side to export from.
    """
    try:
        disk = DFSImage.open(image_path, writable=False, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    output_path = Path(output_dir)
    disk.export_all(output_path, preserve_metadata=not no_metadata)

    click.echo(f"Exported {len(disk.files)} files to {output_dir}")
    if not no_metadata:
        click.echo("(with .inf metadata files)")


@cli.command('import-inf')
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('data_file', type=click.Path(exists=True))
@click.option('--inf', 'inf_file', type=click.Path(exists=True), help='Metadata file (default: <data_file>.inf)')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def import_inf(image_path, data_file, inf_file, side):
    """Import file with .inf metadata.

    Reads load address, exec address, and locked status from .inf file.
    For DSD (double-sided) disks, use --side to select which side to import to.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        disk.import_from_inf(data_file, inf_file)
        click.echo(f"Imported {data_file}")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ========== Utilities ==========


@cli.command('dump')
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('filename')
@click.option('--hex', 'show_hex', is_flag=True, help='Show hex dump')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def dump(image_path, filename, show_hex, side):
    """Display file contents.

    By default shows ASCII. Use --hex for hexadecimal dump.
    For DSD (double-sided) disks, use --side to select which side to dump from.
    """
    try:
        disk = DFSImage.open(image_path, writable=False, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        data = disk.load(filename)
        info = disk.get_file_info(filename)
    except FileNotFoundError:
        click.echo(f"Error: File not found: {filename}", err=True)
        sys.exit(1)

    click.echo(f"\nFile: {info.name}")
    click.echo(f"Size: {info.length} bytes")
    click.echo(f"Load: {info.load_address:08X}")
    click.echo(f"Exec: {info.exec_address:08X}")
    click.echo(f"Locked: {'Yes' if info.locked else 'No'}")
    click.echo()

    if show_hex:
        # Hex dump
        for i in range(0, len(data), 16):
            hex_bytes = ' '.join(f'{b:02X}' for b in data[i:i+16])
            ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
            click.echo(f'{i:04X}:  {hex_bytes:48}  {ascii_repr}')
    else:
        # ASCII dump
        try:
            text = data.decode('utf-8')
            click.echo(text)
        except UnicodeDecodeError:
            click.echo("(binary data - use --hex for hexadecimal dump)")


@cli.command('copy')
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('source')
@click.argument('dest')
@click.option('--side', type=int, default=0, help='Disk side for DSD (0 or 1, default: 0)')
def copy(image_path, source, dest, side):
    """Copy file within disk.

    For DSD (double-sided) disks, use --side to select which side to copy on.
    """
    try:
        disk = DFSImage.open(image_path, side=side)
    except (ValueError, InvalidFormatError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        disk.copy_file(source, dest)
        click.echo(f"Copied {source} → {dest}")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
