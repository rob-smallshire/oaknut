"""Tests for the contributed-command axis."""

from oaknut.cli import COMMAND_NAMESPACE, contributed_commands


def test_command_namespace():
    assert COMMAND_NAMESPACE == "oaknut.command"


def test_contributed_commands_is_a_sorted_list():
    # Whatever command-contributing packages are installed, discovery
    # returns a list and does not raise. (Empty until a filesystem
    # registers an oaknut.command entry point.)
    commands = contributed_commands()
    assert isinstance(commands, list)
    names = [getattr(c, "name", "") for c in commands]
    assert names == sorted(names)


class TestSkipsUnloadable:
    def test_a_failing_entry_point_does_not_crash_discovery(self, monkeypatch):
        # Simulate one entry point importing nothing usable (e.g. a
        # filesystem installed without its [cli] extra): discovery must
        # skip it, not raise.
        import stevedore
        from oaknut.cli import commands as commands_module

        class _FakeExtension:
            name = "ok"
            plugin = type("Cmd", (), {"name": "ok"})()

        class _FakeManager:
            def __init__(self, *args, on_load_failure_callback=None, **kwargs):
                # Exercise the skip callback with a synthetic failure, then
                # yield one good extension.
                if on_load_failure_callback is not None:
                    on_load_failure_callback(self, _FakeEntryPoint(), ImportError("no click"))

            def __iter__(self):
                return iter([_FakeExtension()])

        class _FakeEntryPoint:
            name = "broken"

        monkeypatch.setattr(stevedore, "ExtensionManager", _FakeManager)
        result = commands_module.contributed_commands()
        assert [c.name for c in result] == ["ok"]
