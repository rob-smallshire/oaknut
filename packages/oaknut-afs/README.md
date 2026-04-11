# oaknut-afs

Python library for reading and writing Acorn Level 3 File Server (AFS)
disc partitions — the private on-disc filesystem that the Level 3 File
Server serves to BBC Micro, Master, and Archimedes clients over Econet.

AFS (identified by the `AFS0` magic in its info sectors) coexists with
ADFS on the same disc: WFSINIT — or oaknut's `initialise()` — shrinks
the ADFS partition and carves an AFS region out of the tail cylinders.

Part of the [oaknut](https://github.com/rob-smallshire/oaknut) monorepo.
