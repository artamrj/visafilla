#!/usr/bin/env python3
"""Export source geometry and high-resolution renders, without approving a map."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pymupdf as fitz

from script.core.utils import ROOT, TEMPLATE, render_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', nargs='?', type=Path, default=TEMPLATE)
    parser.add_argument('--output-dir', type=Path, default=ROOT.parent / 'output/inspection')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    evidence = []
    with fitz.open(args.pdf) as doc:
        manifest = {
            'sha256': hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
            'pages': [{'mediabox': list(p.mediabox), 'cropbox': list(p.cropbox), 'rotation': p.rotation} for p in doc],
        }
        for n, page in enumerate(doc):
            text = page.get_text('dict')
            text['blocks'] = [b for b in text['blocks'] if b['type'] == 0]
            squares = [
                c
                for b in page.get_text('rawdict')['blocks']
                for line in b.get('lines', [])
                for s in line['spans']
                for c in s['chars']
                if c['c'] == '□'
            ]
            evidence.append(
                {
                    'page': n,
                    'rect': list(page.rect),
                    'text': text,
                    'checkbox_glyphs': squares,
                    'vector_rules': [
                        list(d['rect']) for d in page.get_drawings() if d['rect'].width < 1 or d['rect'].height < 1
                    ],
                }
            )
    (args.output_dir / 'layout_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    (args.output_dir / 'candidate-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    render_pdf(args.pdf, args.output_dir, 300)
    print(f'Inspection only: {args.output_dir}; no production coordinates or manifest changed')


if __name__ == '__main__':
    main()
