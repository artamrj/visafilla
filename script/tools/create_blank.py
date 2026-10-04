#!/usr/bin/env python3
"""Generate a standalone blank applicant JSON from a country template."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from script.core.templates import TemplateError, load_country_template


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('country', help='template country name, e.g. spain')
    parser.add_argument('--output', required=True, type=Path, help='destination JSON path')
    args = parser.parse_args(argv)
    try:
        data = load_country_template(args.country)
    except TemplateError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    if args.output.exists():
        print(f'ERROR: {args.output} already exists; not overwriting', file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Wrote {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
