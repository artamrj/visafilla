"""Safe paths, template checks and local diagnostic rendering."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import pymupdf as fitz

from .paths import SCRIPT_ROOT as ROOT
from .paths import SPAIN_FORM_DIR as TEMPLATE_DIR
from .paths import TEMPLATE

_checked_template: tuple[str, bytes] | None = None


def ensure_workspace_dirs() -> None:
    """Create local input/output folders without touching their contents."""
    for name in ('input', 'output'):
        (ROOT.parent / name).mkdir(parents=True, exist_ok=True)


def check_template(path: Path = TEMPLATE) -> tuple[str, bytes]:
    """Reject any template version other than the one measured for this map."""
    global _checked_template
    manifest_bytes = (TEMPLATE_DIR / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != manifest['sha256']:
        raise ValueError(
            'template SHA-256 mismatch: inspect and recalibrate the new template before updating the manifest'
        )
    identity = (digest, manifest_bytes)
    if identity == _checked_template:
        return identity
    with fitz.open(path) as doc:
        actual = [{'mediabox': list(p.mediabox), 'cropbox': list(p.cropbox), 'rotation': p.rotation} for p in doc]
        if actual != manifest['pages'] or len(doc) != 4:
            raise ValueError('template page count/geometry mismatch')
    _checked_template = identity
    return identity


def output_name(source: Path) -> str:
    """Keep only portable ASCII filename characters, never applicant contents."""
    stem = re.sub(r'[^A-Za-z0-9_-]+', '_', source.stem).strip('_-')
    if not stem:
        raise ValueError('JSON filename has no safe ASCII letters or digits; rename it')
    return stem + '_schengen_application.pdf'


def atomic_save(doc: fitz.Document, target: Path, overwrite: bool = False) -> None:
    """Publish a complete PDF atomically, without a no-overwrite race."""
    if target.resolve() == TEMPLATE.resolve():
        raise ValueError('output must never be the template')
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix='.schengen-', suffix='.pdf', dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        doc.save(tmp, garbage=0, deflate=False)
        if overwrite:
            os.replace(tmp, target)
        else:
            try:
                os.link(tmp, target)
            except FileExistsError:
                raise ValueError('output exists; use --overwrite to replace a generated file') from None
    finally:
        tmp.unlink(missing_ok=True)


def render_pdf(source: Path, destination: Path, dpi: int = 300) -> list[Path]:
    """Render all pages as PNG; the PDF itself remains vector-based."""
    if not 72 <= dpi <= 600:
        raise ValueError('dpi must be between 72 and 600')
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    with fitz.open(source) as doc:
        for n, page in enumerate(doc, 1):
            target = destination / f'page-{n}.png'
            page.get_pixmap(dpi=dpi, alpha=False).save(target)
            paths.append(target)
    return paths
