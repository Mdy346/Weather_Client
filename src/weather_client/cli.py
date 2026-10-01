"""Command-line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from weather_client import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="weather",
        description="异步天气 API 客户端（彩云天气 + Open-Meteo 地理编码）",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the requested command.

    City lookup and rendering are implemented during core development.
    """
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
