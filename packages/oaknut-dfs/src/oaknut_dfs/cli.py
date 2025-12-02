"""Command-line interface for oaknut-dfs.

Provides BBC Micro DFS-style commands for managing disk images.
"""

import sys
from pathlib import Path
from typing import Optional

import click

from oaknut_dfs.dfs_filesystem import DFSFilesystem, BootOption


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
def cat(image_path):
    """List files on disk (*CAT equivalent).

    Displays disk title, boot option, and file catalog.
    """
    disk = DFSFilesystem.open(image_path, writable=False)

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
def info(image_path):
    """Show detailed disk information (*INFO equivalent)."""
    disk = DFSFilesystem.open(image_path, writable=False)
    info_obj = disk.info

    click.echo("\nDisk Information:")
    click.echo(f"  Path: {image_path}")
    click.echo(f"  Format: {info_obj.format}")
    click.echo(f"  Title: {info_obj.title}")
    click.echo(f"  Boot option: {info_obj.boot_option.name} ({info_obj.boot_option.value})")
    click.echo(f"  Total sectors: {info_obj.total_sectors}")
    click.echo(f"  Free sectors: {info_obj.free_sectors}")
    click.echo(f"  Used sectors: {info_obj.total_sectors - info_obj.free_sectors}")
    click.echo(f"  Files: {info_obj.num_files}")
    click.echo()


# ========== File Operations ==========


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('dfs_filename')
@click.argument('output_path', type=click.Path(), required=False)
def load(image_path, dfs_filename, output_path):
    """Load file from disk (*LOAD equivalent).

    If OUTPUT_PATH is not specified, writes to current directory
    using the DFS filename (with '$.' replaced by '_').
    """
    disk = DFSFilesystem.open(image_path, writable=False)

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
def save(image_path, source_path, dfs_filename, load_addr, exec_addr, locked):
    """Save file to disk (*SAVE equivalent).

    Addresses should be specified in hexadecimal (e.g., --load 1900).
    """
    disk = DFSFilesystem.open(image_path)

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
        click.echo(
            f"Saved {source_path} → {dfs_filename} "
            f"({len(data)} bytes, load={load_address:08X}, exec={exec_address:08X})"
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('filename')
def delete(image_path, filename):
    """Delete file from disk (*DELETE equivalent)."""
    disk = DFSFilesystem.open(image_path)

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
def rename(image_path, old_name, new_name):
    """Rename file (*RENAME equivalent)."""
    disk = DFSFilesystem.open(image_path)

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
def lock(image_path, filename):
    """Lock file (*ACCESS <file> L equivalent)."""
    disk = DFSFilesystem.open(image_path)

    try:
        disk.lock(filename)
        click.echo(f"Locked {filename}")
    except FileNotFoundError:
        click.echo(f"Error: File not found: {filename}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('filename')
def unlock(image_path, filename):
    """Unlock file (*ACCESS <file> equivalent)."""
    disk = DFSFilesystem.open(image_path)

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
        with DFSFilesystem.create(
            image_path,
            title=title,
            num_tracks=tracks,
            double_sided=double_sided
        ) as disk:
            format_str = "DSD (double-sided)" if double_sided else "SSD (single-sided)"
            click.echo(f"Created {format_str} disk: {image_path}")
            click.echo(f"  Title: {disk.title if disk.title else '(none)'}")
            click.echo(f"  Tracks: {tracks}")
            click.echo(f"  Total sectors: {disk.info.total_sectors}")
            click.echo(f"  Capacity: {disk.info.total_sectors * 256:,} bytes")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('new_title')
def title(image_path, new_title):
    """Change disk title (*TITLE equivalent)."""
    disk = DFSFilesystem.open(image_path)

    try:
        disk.title = new_title
        click.echo(f"Changed title to: {new_title}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command('opt')
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('option', type=click.Choice(['0', '1', '2', '3', 'NONE', 'LOAD', 'RUN', 'EXEC']))
def boot_option(image_path, option):
    """Set boot option (*OPT 4,<n> equivalent).

    Options:
      0/NONE - Do nothing on boot
      1/LOAD - *LOAD $.!BOOT
      2/RUN  - *RUN $.!BOOT
      3/EXEC - *EXEC $.!BOOT
    """
    disk = DFSFilesystem.open(image_path)

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
def compact(image_path):
    """Defragment disk (*COMPACT equivalent).

    Moves files to eliminate gaps from deleted files.
    """
    disk = DFSFilesystem.open(image_path)

    try:
        files_moved = disk.compact()
        if files_moved == 0:
            click.echo("Disk already compact (no fragmentation)")
        else:
            click.echo(f"Compacted disk ({files_moved} files moved)")
    except PermissionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('image_path', type=click.Path(exists=True))
def validate(image_path):
    """Check disk integrity.

    Validates catalog structure and file layout.
    """
    disk = DFSFilesystem.open(image_path, writable=False)

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
def export_all(image_path, output_dir, no_metadata):
    """Export all files from disk to directory.

    Creates .inf files with load/exec addresses and locked status.
    """
    disk = DFSFilesystem.open(image_path, writable=False)

    output_path = Path(output_dir)
    disk.export_all(output_path, preserve_metadata=not no_metadata)

    click.echo(f"Exported {len(disk.files)} files to {output_dir}")
    if not no_metadata:
        click.echo("(with .inf metadata files)")


@cli.command('import-inf')
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('data_file', type=click.Path(exists=True))
@click.option('--inf', 'inf_file', type=click.Path(exists=True), help='Metadata file (default: <data_file>.inf)')
def import_inf(image_path, data_file, inf_file):
    """Import file with .inf metadata.

    Reads load address, exec address, and locked status from .inf file.
    """
    disk = DFSFilesystem.open(image_path)

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
def dump(image_path, filename, show_hex):
    """Display file contents.

    By default shows ASCII. Use --hex for hexadecimal dump.
    """
    disk = DFSFilesystem.open(image_path, writable=False)

    try:
        data = disk.load(filename)
        info = disk.get_file_info(filename)

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

    except FileNotFoundError:
        click.echo(f"Error: File not found: {filename}", err=True)
        sys.exit(1)


@cli.command('copy')
@click.argument('image_path', type=click.Path(exists=True))
@click.argument('source')
@click.argument('dest')
def copy(image_path, source, dest):
    """Copy file within disk."""
    disk = DFSFilesystem.open(image_path)

    try:
        disk.copy_file(source, dest)
        click.echo(f"Copied {source} → {dest}")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
