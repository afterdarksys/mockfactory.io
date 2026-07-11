#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def rendered_schema() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="openapi.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)
    expected = rendered_schema()

    if args.check:
        if not output.exists() or output.read_text() != expected:
            print(f"{output} is not synchronized with the application")
            return 1
        return 0

    output.write_text(expected)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
