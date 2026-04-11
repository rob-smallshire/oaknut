"""Base exception hierarchy for the oaknut filesystem family.

`FSError` is the shared root for every filesystem-level exception
raised across oaknut-dfs, oaknut-adfs, and future filesystem
packages. Callers that want to catch "any oaknut filesystem error"
catch FSError; callers that care about a specific format catch its
own subclass (DFSError, ADFSError, …).
"""


class FSError(Exception):
    """Base exception for every oaknut filesystem error.

    Format-specific subclasses live inside each filesystem package
    (e.g. oaknut.dfs.exceptions.DFSError, oaknut.adfs.exceptions.ADFSError).
    """

    pass
