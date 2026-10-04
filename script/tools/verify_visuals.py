#!/usr/bin/env python3
"""Generate fictional conditional-case PDFs/PNGs for manual visual inspection."""

import pymupdf as fitz

from script.core.renderer import fill_pdf
from script.core.schema import Applicant
from script.core.utils import ROOT, render_pdf
from script.tests.scenarios import scenarios


def main() -> None:
    destination = ROOT.parent / 'output/verification'
    destination.mkdir(parents=True, exist_ok=True)
    # Synthetic text image, explicitly not a real person's signature.
    with fitz.open() as doc:
        page = doc.new_page(width=240, height=40)
        page.insert_text((8, 25), 'FICTIONAL SIGNATURE TEST', fontsize=12)
        page.get_pixmap(alpha=True).save(destination / 'fictional-signature.png')
    cases = scenarios()
    cases['minor']['application']['signature'] = {'enabled': True, 'image_path': 'fictional-signature.png'}
    for name, data in cases.items():
        target = destination / f'{name}.pdf'
        fill_pdf(Applicant.model_validate(data), target, destination, overwrite=True)
        render_pdf(target, destination / name, 300)
        print(name)


if __name__ == '__main__':
    main()
