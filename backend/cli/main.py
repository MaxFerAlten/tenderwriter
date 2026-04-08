"""Minimal CLI entrypoint for TenderClaw (Wave 1).

This module provides a small command-line interface surface to exercise
the runtime and orchestration features without a full backend server.
"""

from __future__ import annotations

import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="TenderClaw CLI (Wave 1 placeholder)")
    subparsers = parser.add_subparsers(dest="cmd", help="sub-command help")

    subparsers.add_parser("doctor", help="show doctor info (placeholder)")
    subparsers.add_parser("status", help="show status (placeholder)")
    subparsers.add_parser("hud", help="hud surface (placeholder)")
    subparsers.add_parser("session", help="session management (placeholder)")

    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        print("TenderClaw CLI: doctor (placeholder)")
    elif args.cmd == "status":
        print("TenderClaw CLI: status (placeholder)")
    elif args.cmd == "hud":
        print("TenderClaw CLI: hud (placeholder)")
    elif args.cmd == "session":
        print("TenderClaw CLI: session (placeholder)")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
