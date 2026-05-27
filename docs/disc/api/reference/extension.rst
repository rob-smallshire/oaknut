``oaknut.extension``
====================

The entry-point plug-in framework shared by every extensible *axis* of
the oaknut family. An axis is one extension point — a family of
interchangeable plug-ins that all answer the same question. The first
axis is :doc:`probers <identify>` (disc-image identification); others
will follow.

A concrete extension subclasses :class:`~oaknut.extension.Extension`,
declares a ``kind`` (a short identifier such as ``"prober"``), and is
registered under the ``oaknut.<kind>`` entry-point namespace in its
package's ``pyproject.toml``::

    [project.entry-points."oaknut.prober"]
    acorn_dfs = "oaknut.dfs.probers:AcornDFSProber"

Consumers discover and load extensions with the functions below, which
wrap `stevedore <https://docs.openstack.org/stevedore/>`_. Discovery is
by installed entry point, so a plug-in shipped by any package appears
automatically — there is no central registry to edit.

This module is deliberately domain-agnostic: it knows nothing about
discs, files, or formats. Per-axis packages build a thin convenience
layer on top.

Every name documented here is importable directly from
``oaknut.extension``.


The extension base class
------------------------

.. autoclass:: oaknut.extension.Extension
   :members:

.. autoexception:: oaknut.extension.ExtensionError


Namespaces
----------

.. autofunction:: oaknut.extension.namespace_for


Discovery and loading
---------------------

.. autofunction:: oaknut.extension.list_extensions

.. autofunction:: oaknut.extension.create_extension

.. autofunction:: oaknut.extension.extension

.. autofunction:: oaknut.extension.describe_extension

.. autofunction:: oaknut.extension.extension_name_from_class

.. autofunction:: oaknut.extension.list_dirpaths

.. autofunction:: oaknut.extension.load_failure_callback
