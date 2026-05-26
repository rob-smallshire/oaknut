# oaknut-extension

The entry-point plug-in framework shared by every extensible *axis* of the
`oaknut` package family.

An **axis** is one extension point — a family of interchangeable plug-ins that
all answer the same question. The first axis is *probers* (disc-image format
identification, in `oaknut-identify`); future axes — filesystems, output
formatters, importers — plug into the same machinery.

Each axis declares a `kind` (a short identifier such as `"prober"`). Concrete
extensions for that axis subclass `Extension`, override `_kind()`, and register
themselves under the `oaknut.<kind>` entry-point namespace in their package's
`pyproject.toml`:

```toml
[project.entry-points."oaknut.prober"]
acorn_dfs = "oaknut.dfs.probers:AcornDFSProber"
```

Consumers discover and load them through `list_extensions()`,
`create_extension()`, and friends, which wrap [stevedore](https://docs.openstack.org/stevedore/).
Because discovery is by installed entry point, a plug-in shipped by any package
appears automatically — no central registry to edit.

This package is deliberately domain-agnostic: it knows nothing about discs,
files, or formats. It depends only on `oaknut-exception` (for the shared error
hierarchy) and `stevedore`.
