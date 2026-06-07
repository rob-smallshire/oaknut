"""Generic entry-point plug-in machinery shared by every oaknut extension axis.

An *axis* is a single extension point — a family of interchangeable
plug-ins that all answer the same question (for example the *filesystem*
axis, where each plug-in detects and operates on one disc format). Each
axis declares a ``kind`` (a short identifier such as ``"filesystem"``).
Concrete extensions subclass :class:`Extension`, override
:meth:`Extension._kind`, and are registered under the ``oaknut.<kind>``
entry-point namespace in their package's ``pyproject.toml``::

    [project.entry-points."oaknut.filesystem"]
    acorn-dfs = "oaknut.dfs.filesystem:AcornDFS"

Consumers discover and load them via :func:`list_extensions`,
:func:`create_extension`, :func:`extension`, and :func:`describe_extension`,
which wrap `stevedore <https://docs.openstack.org/stevedore/>`_. Because
discovery is by installed entry point, a plug-in shipped by any package
appears automatically — there is no central registry to edit.

This module is the clone-and-own foundation for the family: it is
deliberately domain-agnostic, knowing nothing about discs, files, or
formats. Per-axis packages build a thin convenience layer on top (see
``oaknut.filesystem`` for the filesystem axis).
"""

from __future__ import annotations

import functools
import importlib.resources
import inspect
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Type

import stevedore
import stevedore.driver
import stevedore.exception
import stevedore.extension
from oaknut.exception import ConfigurationError
from oaknut.extension._text import first_line, normalize_name, strip_lines

__version__ = "12.6.1"

#: Entry-point namespaces are formed as ``"<NAMESPACE_PREFIX>.<kind>"``.
NAMESPACE_PREFIX = "oaknut"

__all__ = [
    "Extension",
    "ExtensionError",
    "namespace_for",
    "create_extension",
    "extension",
    "describe_extension",
    "list_extensions",
    "list_dirpaths",
    "extension_name_from_class",
    "load_failure_callback",
]

logger = logging.getLogger(__name__)


def namespace_for(kind: str) -> str:
    """Return the entry-point namespace for an extension *kind*.

    The convention is ``"oaknut.<kind>"`` — e.g.
    ``namespace_for("filesystem")`` is ``"oaknut.filesystem"``.
    """
    return f"{NAMESPACE_PREFIX}.{kind}"


class Extension(ABC):
    """Base class for every oaknut plug-in extension.

    A concrete extension overrides :meth:`_kind` to name its axis and
    is instantiated with the entry-point ``name`` it was registered
    under. The class docstring doubles as its human-readable
    description (see :meth:`describe`).
    """

    def __init__(self, name: str, **kwargs):
        super().__init__(**kwargs)
        self._name = name

    @classmethod
    def kind(cls) -> str:
        """The kind of extension — the axis this plug-in belongs to."""
        return cls._kind()

    @classmethod
    @abstractmethod
    def _kind(cls) -> str:
        raise NotImplementedError

    @property
    def name(self) -> str:
        """The entry-point name this extension was loaded under."""
        return self._name

    @classmethod
    def dirpath(cls) -> Path:
        """The directory path to the package providing this extension."""
        package_name = inspect.getmodule(cls).__package__
        return Path(importlib.resources.files(package_name))

    @classmethod
    def version(cls) -> str:
        """The extension version. Override to report something meaningful."""
        return __version__

    @classmethod
    def describe(cls, *, single_line: bool = False) -> str:
        """A human-readable description of the extension.

        By default this is the extension class's docstring. Override it
        if you want something different.

        Args:
            single_line: If True, return only the first non-empty line of
                the description. Defaults to False for the full text.

        Returns:
            The description. If *single_line* is True, only the first
            non-empty line; otherwise the complete (de-indented) docstring.
        """
        if cls.__doc__ is None:
            return "No description available."
        full_description = strip_lines(inspect.cleandoc(cls.__doc__))
        if single_line:
            return first_line(full_description)
        return full_description

    @classmethod
    @functools.lru_cache(maxsize=None)
    def entry_point_name(cls) -> str:
        """The entry-point name (key) this extension class is registered under.

        Performs a reverse lookup from class to entry-point name by
        searching the axis's namespace. Cached indefinitely since
        entry-point names are immutable for the life of the process.

        Raises:
            ExtensionError: If this class is not a registered extension.
        """
        return extension_name_from_class(namespace_for(cls.kind()), cls)


class ExtensionError(ConfigurationError):
    """Raised when an extension cannot be discovered or loaded.

    A plug-in that is missing, mis-registered, or fails at import time
    is an environment/setup problem rather than bad input or a library
    bug — hence a :class:`~oaknut.exception.ConfigurationError`.
    """


def create_extension(
    kind: str,
    namespace: str,
    name: str,
    exception_type: Optional[type[BaseException]] = None,
    **kwargs,
) -> Extension:
    """Instantiate an extension by name.

    Args:
        kind: The kind of extension (for error messages).
        namespace: The entry-point namespace to search.
        name: The name of the extension to load.
        exception_type: Exception raised if the extension cannot be
            loaded. Defaults to :class:`ExtensionError`.
        **kwargs: Forwarded to the extension constructor.

    Returns:
        An :class:`Extension` instance.
    """
    ext = extension(kind, namespace, name, exception_type)
    return ext(name=normalize_name(name), **kwargs)


def extension(
    kind: str,
    namespace: str,
    name: str,
    exception_type: Optional[type[BaseException]] = None,
) -> Type[Extension]:
    """Get an extension *class* (without instantiating it).

    Args:
        kind: The kind of extension (for error messages).
        namespace: The entry-point namespace to search.
        name: The name of the extension to load.
        exception_type: Exception raised if the extension cannot be
            loaded. Defaults to :class:`ExtensionError`.

    Returns:
        The extension class.
    """
    exception_type = exception_type or ExtensionError
    normal_name = normalize_name(name)
    try:
        manager = stevedore.driver.DriverManager(
            namespace=namespace,
            name=normal_name,
            invoke_on_load=False,
            on_load_failure_callback=load_failure_callback,
        )
    except stevedore.exception.NoMatches as no_matches:
        name_list = ", ".join(list_extensions(namespace))
        raise exception_type(
            f"No {kind} matching {name!r}. Available {kind}s: {name_list}"
        ) from no_matches
    return manager.driver


def describe_extension(
    kind: str,
    namespace: str,
    name: str,
    exception_type: Optional[type[BaseException]] = None,
    *,
    single_line: bool = False,
) -> str:
    """Return the description of an extension by name.

    Args:
        kind: The kind of extension (for error messages).
        namespace: The entry-point namespace to search.
        name: The name of the extension.
        exception_type: Exception raised if the extension cannot be loaded.
        single_line: If True, return only the first non-empty line.

    Returns:
        The extension's description string.
    """
    driver = extension(kind, namespace, name, exception_type)
    return driver.describe(single_line=single_line)


def list_extensions(namespace: str) -> list[str]:
    """List the names of the extensions registered in *namespace*."""
    manager = stevedore.ExtensionManager(
        namespace=namespace,
        invoke_on_load=False,
        on_load_failure_callback=load_failure_callback,
    )
    return manager.names()


def list_dirpaths(namespace: str) -> dict[str, Path]:
    """Map each extension name in *namespace* to its package directory path."""
    manager = stevedore.ExtensionManager(
        namespace=namespace,
        invoke_on_load=False,
        on_load_failure_callback=load_failure_callback,
    )
    return {name: _extension_dirpath(ext) for name, ext in manager.items()}


def _extension_dirpath(ext: stevedore.extension.Extension) -> Path:
    """The directory path to the package providing a stevedore extension."""
    return Path(importlib.resources.files(ext.module_name))


def extension_name_from_class(namespace: str, extension_class: Type[Extension]) -> str:
    """Reverse-lookup the entry-point name for an extension *class*.

    Iterates the extensions in *namespace* until one whose plug-in is
    *extension_class* is found.

    Raises:
        ExtensionError: If the class is not registered in *namespace*.
    """
    manager = stevedore.ExtensionManager(
        namespace=namespace,
        invoke_on_load=False,
        on_load_failure_callback=load_failure_callback,
    )
    for ext in manager:
        if ext.plugin is extension_class:
            return ext.name
    raise ExtensionError(
        f"Extension class {extension_class.__name__} not found in namespace {namespace!r}"
    )


def load_failure_callback(manager, entrypoint, exception):
    """Turn a stevedore load failure into an :class:`ExtensionError`."""
    raise ExtensionError(
        f"Could not load extension {entrypoint.name!r} from namespace "
        f"{manager.namespace!r}: {exception}"
    ) from exception
