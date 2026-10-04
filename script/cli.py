#!/usr/bin/env python3
"""Command-line entry point for entirely local Schengen form processing."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from script.core.renderer import calibrate, fill_pdf, prepare
from script.core.utils import ROOT, ensure_workspace_dirs, output_name, render_pdf
from script.core.validator import load_applicant


def main(argv: list[str] | None = None) -> int:
    """Process inputs independently, returning nonzero on any failed applicant."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', type=Path, help='applicant JSON or directory')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--validate-only', action='store_true', help='validate JSON and layout without writing output')
    modes.add_argument('--calibrate', action='store_true', help='render measured layout with diagnostic grid')
    modes.add_argument('--render-pdf', type=Path, help='render any local PDF to PNG')
    parser.add_argument('--preview', action='store_true', help='also render generated pages to PNG')
    parser.add_argument('--overwrite', action='store_true', help='replace existing generated PDFs')
    parser.add_argument('--output-dir', type=Path, default=ROOT.parent / 'output')
    parser.add_argument('--font-file', type=Path, help='local TTF/OTF with required Unicode glyphs')
    parser.add_argument('--dpi', type=int, default=300)
    args = parser.parse_args(argv)
    if not 72 <= args.dpi <= 600:
        parser.error('--dpi must be between 72 and 600')
    if (args.calibrate or args.render_pdf) and (args.input or args.preview):
        parser.error('calibration/render modes cannot be combined with input or --preview')
    if args.validate_only and args.preview:
        parser.error('--validate-only cannot be combined with --preview')
    try:
        ensure_workspace_dirs()
        if args.calibrate:
            destination = args.output_dir / 'calibration'
            calibrate(destination, args.dpi)
            print(f'Calibration: {destination}')
            return 0
        if args.render_pdf:
            destination = args.output_dir / (args.render_pdf.stem + '_render')
            render_pdf(args.render_pdf, destination, args.dpi)
            print(f'Rendered: {destination}')
            return 0
        if args.input is None:
            parser.error('supply a JSON file/directory, --calibrate or --render-pdf')
        files = sorted(args.input.glob('*.json')) if args.input.is_dir() else [args.input]
        if not files:
            raise ValueError('directory contains no *.json files')
        names: dict[Path, str] = {}
        failed = 0
        for path in files:
            try:
                if path.suffix.lower() != '.json' or not path.is_file():
                    raise ValueError('input must be an existing JSON file')
                names[path] = output_name(path)
            except (ValueError, OSError) as exc:
                failed += 1
                print(f'ERROR {path.name}: {exc}', file=sys.stderr)
        counts = Counter(name.casefold() for name in names.values())
        for path, name in names.items():
            try:
                if counts[name.casefold()] > 1:
                    raise ValueError('output filename collision; rename the colliding JSON files')
                applicant = load_applicant(path)
                if args.validate_only:
                    prepare(applicant, path.parent, args.font_file)
                    print(f'VALID {path.name}')
                else:
                    target = args.output_dir / name
                    fill_pdf(applicant, target, path.parent, overwrite=args.overwrite, font_file=args.font_file)
                    if args.preview:
                        render_pdf(target, args.output_dir / (target.stem + '_preview'), args.dpi)
                    print(f'OK {path.name} -> {target}')
            except Exception as exc:
                # Isolate applicants in a batch, but surface every failure.
                failed += 1
                print(f'ERROR {path.name}: {exc}', file=sys.stderr)
        print(f'{len(files) - failed} succeeded; {failed} failed')
        return 1 if failed else 0
    except (ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
