#!/usr/bin/env python
"""Command-line interface."""
import logging
import sys

import click
import rich.logging
from rich import traceback

from pertpy import pertpy_pypi_latest
from pertpy.cli.custom_cli.click import CustomHelpSubcommand, HelpErrorHandling, print_pertpy_version
from pertpy.cli.custom_cli.rich import console

log = logging.getLogger()


def main() -> None:
    traceback.install(width=200, word_wrap=True)
    console.print(
        r"""[bold blue]
██████  ███████ ██████  ████████ ██████  ██    ██
██   ██ ██      ██   ██    ██    ██   ██  ██  ██
██████  █████   ██████     ██    ██████    ████
██      ██      ██   ██    ██    ██         ██
██      ███████ ██   ██    ██    ██         ██
        """
    )

    console.print("[bold blue]Run [green]pertpy --help [blue]for an overview of all commands\n")

    # Is the latest pertpy version installed? Upgrade if not!
    if not pertpy_pypi_latest.check_latest():
        console.print("[bold blue]Run [green]pertpy upgrade [blue]to get the latest version.")
    pertpy_cli()


@click.group(cls=HelpErrorHandling)
@click.option(
    "--version",
    is_flag=True,
    callback=print_pertpy_version,
    expose_value=False,
    is_eager=True,
    help="Print the currently installed pertpy version.",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose output (print debug statements).")
@click.option("-l", "--log-file", help="Save a verbose log to a file.")
@click.pass_context
def pertpy_cli(ctx, verbose, log_file) -> None:
    """Access the pertpy api through commands.

    Primarily useful for complex pipelines which call pertpy functions directly from the command line.
    """
    # Set the base logger to output DEBUG
    log.setLevel(logging.DEBUG)

    # Set up logs to the console
    log.addHandler(
        rich.logging.RichHandler(
            level=logging.DEBUG if verbose else logging.INFO,
            console=rich.console.Console(file=sys.stderr),
            show_time=True,
            markup=True,
        )
    )

    # Set up logs to a file if we asked for one
    if log_file:
        log_fh = logging.FileHandler(log_file, encoding="utf-8")
        log_fh.setLevel(logging.DEBUG)
        log_fh.setFormatter(logging.Formatter("[%(asctime)s] %(name)-20s [%(levelname)-7s]  %(message)s"))
        log.addHandler(log_fh)


@pertpy_cli.command(short_help="Reads an input file to get an AnnData object.", cls=CustomHelpSubcommand)
def read() -> None:
    """Not yet implemented!

    Returns:
        AnnData object containing the data of the read file.
    """
    print("[bold red]Not yet implemented.")


@pertpy_cli.command(short_help="Check for a newer version of pertpy and upgrade if required.", cls=CustomHelpSubcommand)
def upgrade() -> None:
    """Checks whether the locally installed version of pertpy is the latest & upgrades if not."""
    pertpy_pypi_latest.check_upgrade()


if __name__ == "__main__":
    traceback.install()
    main()