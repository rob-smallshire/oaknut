"""Entry point for running oaknut-zip as a module.

This allows oaknut-zip to be executed as:
    python -m oaknut.zip
"""

from .cli import cli

if __name__ == "__main__":
    cli()
