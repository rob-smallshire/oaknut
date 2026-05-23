Cookbook
=======


Recipes for common tasks using the oaknut Python API.


Reading files from a DFS floppy
--------------------------------

.. code-block:: python

   from oaknut.dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED

   with DFS.from_file("games.ssd", ACORN_DFS_80T_SINGLE_SIDED) as dfs:
       for entry in dfs.root.iterdir():
           for child in entry.iterdir():
               st = child.stat()
               print(f"{child.path:12s} {st.load_address:08X} {st.length}")


Creating a DFS floppy from scratch
-----------------------------------

.. code-block:: python

   from oaknut.dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED

   with DFS.create_file("new.ssd", ACORN_DFS_80T_SINGLE_SIDED, title="MY DISC") as dfs:
       (dfs.root / "$.HELLO").write_bytes(
           b'PRINT "Hello!"\r',
           load_address=0xFFFF,
           exec_address=0xFFFF,
       )
       (dfs.root / "$.DATA").write_bytes(
           b"\x00" * 256,
           load_address=0x3000,
       )


Working with ADFS images
-------------------------

.. code-block:: python

   from oaknut.adfs import ADFS

   # Open a floppy image (format auto-detected from size)
   with ADFS.from_file("disc.adl") as adfs:
       print(f"Title: {adfs.title}")
       print(f"Free:  {adfs.free_space:,} bytes")
       print(f"Geometry: {adfs.geometry}")

       for entry in adfs.root.iterdir():
           print(f"  {entry.name}")

   # Create a hard disc image
   with ADFS.create_file("scsi0.dat", capacity_bytes=10*1024*1024, title="Server") as adfs:
       (adfs.root / "ReadMe").write_bytes(b"Hello from ADFS\r")
       (adfs.root / "Programs").mkdir()
       (adfs.root / "Programs" / "Test").write_bytes(b"test data")


Accessing AFS partitions
-------------------------

An AFS partition lives in the tail cylinders of an ADFS hard disc
image. Access it through the ADFS handle:

.. code-block:: python

   from oaknut.adfs import ADFS

   with ADFS.from_file("scsi0.dat") as adfs:
       afs = adfs.afs_partition
       if afs is None:
           print("No AFS partition")
       else:
           print(f"AFS disc name: {afs.disc_name}")
           print(f"Free sectors:  {afs.free_sectors}")

           for user in afs.users.active:
               flag = "S" if user.is_system else " "
               print(f"  {flag} {user.full_id}")

           for entry in afs.root.iterdir():
               print(f"  {entry.name}")


Copying files between disc images
-----------------------------------

Use :func:`oaknut.file.copy_file` to copy a file between any two
path objects (DFS, ADFS, or AFS), with access attribute mapping:

.. code-block:: python

   from oaknut.adfs import ADFS
   from oaknut.dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED
   from oaknut.file import copy_file

   with DFS.from_file("source.ssd", ACORN_DFS_80T_SINGLE_SIDED) as dfs:
       src = dfs.path("$.HELLO")

       with ADFS.from_file("target.adl", mode="r+b") as adfs:
           dst = adfs.root / "Hello"
           copy_file(src, dst, target_fs="adfs")


Exporting with metadata sidecars
----------------------------------

.. code-block:: python

   from pathlib import Path
   from oaknut.adfs import ADFS
   from oaknut.file import AcornMeta, MetaFormat, export_with_metadata

   with ADFS.from_file("disc.adl") as adfs:
       for entry in adfs.root.iterdir():
           if entry.is_dir():
               continue
           data = entry.read_bytes()
           st = entry.stat()
           meta = AcornMeta(
               load_addr=st.load_address,
               exec_addr=st.exec_address,
               attr=int(st.access),
           )
           export_with_metadata(
               data,
               Path("output") / entry.name,
               meta,
               meta_format=MetaFormat.INF_TRAD,
           )


Initialising an AFS partition
-------------------------------

.. code-block:: python

   from oaknut.adfs import ADFS
   from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise
   from oaknut.afs.libraries import emplace_library

   with ADFS.create_file("server.dat", capacity_bytes=10*1024*1024) as adfs:
       # Partition and initialise AFS
       initialise(
           adfs,
           spec=InitSpec(
               disc_name="Server",
               size=AFSSizeSpec.cylinders(200),
               users=[
                   UserSpec("Syst", system=True),
                   UserSpec("guest", quota=2*1024*1024),
               ],
           ),
       )

       # Emplace library files
       afs = adfs.afs_partition
       with afs:
           emplace_library(afs, "Library")
           emplace_library(afs, "Library1")
