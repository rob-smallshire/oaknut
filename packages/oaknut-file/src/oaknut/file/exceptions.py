"""Base exception hierarchy for the oaknut filesystem family.

``FSError`` is the shared root for every filesystem-level exception
raised across ``oaknut-dfs``, ``oaknut-adfs``, ``oaknut-afs``, and
future filesystem packages. Callers that want to catch "any oaknut
filesystem error" catch ``FSError``; callers that care about a
specific format catch its own subclass (``DFSError``, ``ADFSError``,
``AFSError``).

``FSError`` itself derives from :class:`oaknut.exception.DataError`,
so every filesystem-level error is by default a *data* category
problem — the operation could not be satisfied with the bytes on
disc or the names the caller asked for. Specific subclasses override
:attr:`_exit_code` to pin a more precise :class:`ExitCode`
(``ExitCode.OS_FILE`` for path-not-found, ``ExitCode.NO_PERM`` for
locked entries, and so on). The CLI boundary in ``oaknut-disc``
needs no per-class mapping table — it just reads ``exc.exit_code``.

A handful of conditions are programming bugs rather than data
problems (corrupted on-disc structures *should* be impossible after
internal validation). Those subclass :class:`InternalError`
explicitly instead of ``FSError`` so a traceback survives to the
user — the report-an-issue path.
"""

from oaknut.exception import DataError


class FSError(DataError):
    """Base exception for every oaknut filesystem error.

    Format-specific subclasses live inside each filesystem package
    (e.g. ``oaknut.dfs.exceptions.DFSError``,
    ``oaknut.adfs.exceptions.ADFSError``,
    ``oaknut.afs.exceptions.AFSError``). The default
    :class:`ExitCode` is :data:`ExitCode.DATA_ERR` inherited from
    :class:`DataError`; specific subclasses override
    :attr:`_exit_code` to a more precise code.
    """


class FilesystemClosedError(FSError):
    """An I/O operation was attempted on a closed filesystem handle.

    Raised when a path object outlives the ``with`` block that
    opened its filesystem and a method is called that would have
    needed to touch the underlying disc image. Pure path
    manipulation (slash-join, ``parent``, ``name``, ``parts``,
    ``path``, equality) does not raise this.
    """


class TitleNotSupportedError(FSError):
    """The target entity cannot carry a title.

    A *title* is a human-readable label distinct from a name. Only
    some Acorn entities have a slot for one: the disc (every
    filesystem) and — on ADFS only — every directory. DFS and AFS
    directories have no title field, and files never do. Attempting
    to read or set a title on such an entity raises this.
    """


class InvalidAddressError(FSError):
    """A load or execution address could not be parsed.

    Addresses are written as integer literals whose base comes from
    the prefix — ``0x`` hex, ``0o`` octal, ``0b`` binary, or none for
    decimal. Input that is not a valid literal (non-numeric text, or
    the Acorn ``&`` hex sigil) raises this. As an :class:`FSError` it
    carries the data-error exit code and is rendered by the CLI
    boundary without a traceback.
    """
