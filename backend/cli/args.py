"""Arg definitions for TenderClaw CLI (Wave 1 placeholder)."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TenderClaw CLI placeholder")
    sub = parser.add_subparsers(dest="cmd", help="sub-command help")
    sub.add_parser("doctor")
    sub.add_parser("status")
    sub.add_parser("hud")
    sub.add_parser("session")
    return parser
