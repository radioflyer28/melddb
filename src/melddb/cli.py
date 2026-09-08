"""Read-oriented inspector; never creates a database on a misspelled path."""
import argparse
import json

import melddb


def main():
    parser = argparse.ArgumentParser(prog="melddb")
    parser.add_argument("command", choices=["inspect", "check", "backup", "export"])
    parser.add_argument("database")
    parser.add_argument("destination", nargs="?")
    args = parser.parse_args()
    if args.command in ("backup", "export") and not args.destination:
        parser.error("This command requires a new destination path")
    if args.command in ("inspect", "check") and args.destination:
        parser.error("This command does not accept a destination")
    try:
        with melddb.open(args.database, readonly=True) as db:
            operation = getattr(db, args.command)
            result = operation(args.destination) if args.destination else operation()
            print(json.dumps(result, indent=2))
            if args.command == "check" and not result["ok"]:
                raise SystemExit(1)
    except melddb.errors.MeldDBError as exc:
        parser.exit(1, f"{exc.code}: {exc}\n")
    except OSError as exc:
        parser.exit(1, f"io: {exc}\n")


if __name__ == "__main__":
    main()
