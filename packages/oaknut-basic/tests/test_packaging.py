"""Packaging-metadata guards for the standalone ``oaknut-basic`` command.

Unlike the filesystem plugin packages (``oaknut-dfs``/``oaknut-adfs`` …),
which only contribute ``disc`` subcommands via entry points and ship no
console script of their own, ``oaknut-basic`` declares its own
``[project.scripts]`` entry point. A console script that is always
installed must have everything it imports as an *unconditional* runtime
dependency, otherwise ``pip install oaknut-basic`` / ``uvx oaknut-basic``
produces an executable that dies with ``ModuleNotFoundError`` at import
(see issue #49).
"""

from importlib.metadata import entry_points, requires

_DISTRIBUTION = "oaknut-basic"

# Everything oaknut/basic/cli.py imports at module load, mapped to the
# distribution that supplies it.
_CLI_REQUIREMENTS = ("oaknut-cli", "click", "asyoulikeit")


def _unconditional_requirements():
    """Distribution names required without an ``extra ==`` marker."""
    names = set()
    for requirement in requires(_DISTRIBUTION) or []:
        # "oaknut-cli>=10.0; extra == 'cli'" -> skip; extras are optional.
        spec, _, marker = requirement.partition(";")
        if "extra" in marker:
            continue
        name = (
            spec.strip()
            .split("[")[0]
            .split("<")[0]
            .split(">")[0]
            .split("=")[0]
            .split("!")[0]
            .split("~")[0]
            .strip()
        )
        names.add(name.lower())
    return names


def test_console_script_is_declared():
    scripts = entry_points(group="console_scripts")
    assert any(ep.name == "oaknut-basic" for ep in scripts)


def test_cli_dependencies_are_unconditional():
    unconditional = _unconditional_requirements()
    missing = [
        name for name in _CLI_REQUIREMENTS if name.lower() not in unconditional
    ]
    assert not missing, (
        f"{_DISTRIBUTION} ships a console script but these imports of "
        f"oaknut.basic.cli are not unconditional dependencies: {missing}. "
        "Promote them out of the [cli] extra into [project.dependencies]."
    )
