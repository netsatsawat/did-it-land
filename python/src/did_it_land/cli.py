"""The did-it-land command line.

    did-it-land list              show the bundled capsules
    did-it-land validate [DIR]    validate a corpus (defaults to the bundled one)
    did-it-land demo              run the no-keys crash-and-reconcile demo
    did-it-land schema            print the schema version
"""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

import yaml

from . import __version__
from .capsule import SCHEMA_VERSION, CapsuleError, load_capsule
from .reconcile import EffectError
from .registry import Registry, bundled, load_dir


def _cmd_list(_args: argparse.Namespace) -> int:
    reg = bundled()
    print(f"{len(reg)} capsules:")
    for cap in sorted(reg.all(), key=lambda c: c.id):
        rev = cap.reversibility.cls
        comp = cap.compensation.kind if cap.compensation else "none"
        print(f"  {cap.id:22s} probe={cap.probe.kind:6s} reversibility={rev:24s} undo={comp}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        if args.path and Path(args.path).is_file():
            reg = Registry([load_capsule(args.path)])
        elif args.path:
            reg = load_dir(args.path)
        else:
            reg = bundled()
    except (CapsuleError, EffectError, TypeError, yaml.YAMLError, OSError) as exc:
        first = str(exc).strip().splitlines()[0]
        print(f"invalid: {first}", flush=True)
        return 1
    print(f"valid: {len(reg)} capsules ({', '.join(reg.ids())})")
    return 0


def _cmd_demo(_args: argparse.Namespace) -> int:
    from .demo import run_demo

    result = run_demo()
    ok = (
        result["naive_charges"] == 2
        and result["did_it_land_charges"] == 1
        and result["not_landed_charges"] == 1
        and result["unknown_then_charges"] == 1
        and result["unknown_status"] == "unknown")
    return 0 if ok else 1


def _cmd_schema(_args: argparse.Namespace) -> int:
    print(f"capsule schema version {SCHEMA_VERSION}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="did-it-land", description=__doc__)
    parser.add_argument("--version", action="version", version=f"did-it-land {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="show the bundled capsules").set_defaults(func=_cmd_list)

    p_val = sub.add_parser(
        "validate", help="validate a capsule file or a corpus directory")
    p_val.add_argument(
        "path", nargs="?", help="a .yaml capsule or a directory (default: bundled)")
    p_val.set_defaults(func=_cmd_validate)

    sub.add_parser("demo", help="run the no-keys demo").set_defaults(func=_cmd_demo)
    sub.add_parser("schema", help="print the schema version").set_defaults(func=_cmd_schema)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
