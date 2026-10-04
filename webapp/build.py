"""Write the generated files of the browser app into webapp/static/.

webapp/static/ is the complete website: Cloudflare (or any static host) publishes it as-is,
and the local launcher serves the same folder. Two files in it are generated from the Python
sources and committed, so hosting needs no build step:

- meta.json: form structure, English labels, Persian guidance, field coordinates and
  validation links, used by the in-browser engine.
- form/spain.pdf: an unmodified copy of the official template the engine fills.

Run this after changing the schema, labels, guidance, coordinates or template:

    python -m webapp.build           # write the files
    python -m webapp.build --check   # fail if they are out of date (used by the tests)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from script.core.coordinates import CHECKBOX_MAP, FIELD_MAP, SIGNATURE
from script.core.paths import SPAIN_FORM_DIR, TEMPLATE
from webapp.fields import metadata
from webapp.validation import ERROR_LINKS

STATIC = Path(__file__).resolve().parent / 'static'
TEMPLATE_URL = 'form/spain.pdf'


def site_meta() -> dict:
    """Everything the browser needs to render, validate and fill the form."""
    meta = {key: value for key, value in metadata().items() if key != 'schema'}
    manifest = json.loads((SPAIN_FORM_DIR / 'manifest.json').read_text(encoding='utf-8'))
    meta['layout'] = {
        'template': {'url': TEMPLATE_URL, 'sha256': manifest['sha256'], 'pages': len(manifest['pages'])},
        'fields': {key: asdict(field) for key, field in FIELD_MAP.items()},
        'checkboxes': {key: asdict(field) for key, field in CHECKBOX_MAP.items()},
        'signature': asdict(SIGNATURE),
    }
    meta['errorLinks'] = [{'phrase': phrase, 'paths': paths} for phrase, paths in ERROR_LINKS]
    return meta


def outputs() -> dict[Path, bytes]:
    text = json.dumps(site_meta(), ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    return {STATIC / 'meta.json': text.encode('utf-8'), STATIC / TEMPLATE_URL: TEMPLATE.read_bytes()}


def stale() -> list[Path]:
    return [path for path, data in outputs().items() if not path.exists() or path.read_bytes() != data]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='only report whether the generated files are current')
    args = parser.parse_args()
    if args.check:
        if paths := stale():
            sys.exit('Out of date, run python -m webapp.build: ' + ', '.join(str(p) for p in paths))
        print('Generated files are up to date.')
        return
    for path, data in outputs().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f'Wrote {path.relative_to(STATIC.parent.parent)}')


if __name__ == '__main__':
    main()
