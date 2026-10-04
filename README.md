# VisaFilla

A free, open-source helper for filling in the **Spanish Schengen short-stay visa application form** (PDF). It guides you through every question step by step, checks your answers for common mistakes, and produces the official four-page form ready to print and sign.

**Your data never leaves your device.** Everything runs inside your browser tab: checking your answers, filling the official PDF and showing the previews. There is no account, no upload and no tracking, whether you use the website or run it on your own computer.

> **Disclaimer.** VisaFilla is an independent community project. It is **not** an official government service and is not affiliated with, endorsed by or connected to the Government of Spain, any consulate, any visa application centre or the European Union. It does not give legal or immigration advice. Visa rules, forms and required documents change; always check the current requirements with the consulate or visa centre handling your application, and review every answer on the generated PDF against your own documents before you sign and submit it. You use this software at your own risk.

## Features

- Guided form covering all fields of the Spanish Schengen application, in eight steps.
- Validation for dates, passport validity, journey and stay consistency, and whether text fits each box on the form.
- Multiple applicants (for example, everyone travelling together), each saved separately in your browser.
- Multiple accommodation stays printed within the original four pages.
- Preview of all four pages before downloading.
- Import and export of applicant data as JSON, plus a command-line tool for batch use.
- Field guidance in Persian (فارسی); field labels are in English, matching the official form.

## Use it online

Open the hosted site in any modern browser (Chrome, Edge, Firefox or Safari, on desktop or phone). Nothing to install.

## Run it on your own computer

You need Python **3.12 or newer** ([python.org](https://www.python.org/downloads/)) and internet access the first time only, to install the two Python dependencies.

Download or clone this repository, then open a terminal in its folder.

**macOS:** double-click **Start VisaFilla.command**. It sets everything up on first run and opens the app in your browser.

**Windows:**

```bat
py -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m webapp --open
```

**macOS / Linux (manual):**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m webapp --open
```

The app opens at `http://127.0.0.1:8765`. Keep the terminal window open while you work; press **Control+C** to stop. If the port is busy, add `--port 8766`.

## Filling in an application

1. Click **Add applicant** to start a blank application.
2. Work through the eight steps, copying details exactly as they appear in your passport and booking documents.
3. Click **Check application** and fix any errors it points you to.
4. Generate the PDF in the final step, review all four pages, and download it.
5. Print at **Actual size / 100%** and sign where required.

If any answer is still unconfirmed, or the fingerprint question is left blank, the downloaded file name is marked as a draft. Validation checks consistency and fit on the form, not whether your answers are true or sufficient for a visa.

## Privacy

- Answers are validated and the PDF is filled **in your browser**. The site only ever downloads its own files (the app, the form description and the blank official PDF); it never sends anything back.
- This is enforced, not just promised: a strict Content-Security-Policy (`connect-src 'self'`, see `webapp/static/_headers`) stops the page from contacting any other server, and there is no server-side code that could receive data.
- Drafts are stored in your browser (IndexedDB). Clearing your browser data deletes them, so use **Export applicant JSON** to keep a backup. Generated PDFs exist only in the open tab.
- The local app serves the same files from `127.0.0.1` only and logs nothing.
- The `input/` and `output/` folders are git-ignored, so your applicant files and PDFs are never committed by accident.

## Command line

The PDF engine also works without the browser, using applicant JSON files:

```bash
# Create a blank applicant file to fill in
.venv/bin/python -m script.tools.create_blank spain --output input/Applicant.json

# Validate, preview or generate PDFs for every JSON file in input/
.venv/bin/python -m script input --validate-only
.venv/bin/python -m script input --preview
.venv/bin/python -m script input --overwrite
```

On macOS, `"./Start VisaFilla.command" <arguments>` forwards arguments to the same CLI. Relative paths are resolved from the project folder.

### Applicant JSON format

The browser app and CLI share one format, based on `template/base.template.json` (89 fields). Dates use `DD-MM-YYYY`. Unknown values are `null`; unused optional sections can be set to `null`. A blank file fails validation until it is completed.

`accommodation` is a list with one entry per stay:

```json
"accommodation": [
  {
    "city": "Madrid",
    "country": "Spain",
    "type": "temporary_accommodation",
    "name": "Example apartment",
    "address": "123 Example Street, Madrid, Spain",
    "email": null,
    "phone": "+34 000 000 000",
    "check_in": "01-06-2027",
    "check_out": "04-06-2027",
    "confirmation_code": "EXAMPLE001"
  }
]
```

Check-out must follow check-in, and every stay must fall within the journey dates. Names, addresses, phones and emails print in field 30; booking dates and confirmation codes print in field 24. Text wraps and shrinks to fit its box; text that still does not fit fails validation instead of being cut off. Older single-object `accommodation` values are still accepted.

Set `previous_biometrics.fingerprints_taken` to `null` to leave both fingerprint boxes blank. Previous visas can be recorded with `visa_issuing_country` and `visa_entry_date`; leave `date` as `null` unless you know the actual fingerprint collection date.

## Project structure

| Path | Contents |
| --- | --- |
| `template/base.template.json` | Shared blank Schengen applicant structure |
| `template/spain/` | Spain's blank form PDF, checkbox layout, geometry evidence, manifest and country template |
| `script/` | Python PDF engine, CLI, tools and template loader; tests in `script/tests/` |
| `webapp/static/` | **The complete website**: interface, in-browser engine (`engine/`), vendored libraries (`vendor/`), generated `meta.json` and `form/spain.pdf`, and security `_headers` |
| `webapp/` | Form labels (`fields.py`), Persian guidance (`guidance_fa.py`), build script, local static server; tests in `webapp/tests/` |

The browser engine in `webapp/static/engine/` is a port of the Python engine. Parity tests run both on every test scenario and require identical errors, field values, checkboxes, line wrapping, font sizes and rendered pages.

### Adding another Schengen country

Add `template/<country>/<country>.template.json` that extends the shared base, overriding fields or adding country-only fields under `extras`:

```json
{
  "extends": "../base.template.json",
  "overrides": { "personal": { "surname": null } },
  "extras": { "national_scheme": null }
}
```

The country also needs its blank PDF, field coordinates and checkbox layout, following `template/spain/`.

## Development

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

After changing the schema, labels, Persian guidance, coordinates or template, regenerate the website's data files (a test fails if you forget):

```bash
.venv/bin/python -m webapp.build
```

Parity tests need [Node.js](https://nodejs.org/) to run the browser engine; browser tests need Google Chrome or Playwright Chromium (`.venv/bin/python -m playwright install chromium`, or set `CHROME_PATH`). Tests that need a missing tool are skipped. All test data is fictional and lives in `script/tests/`.

## Deploying

`webapp/static/` is a plain static site with no build step, so any static host works. The repository is set up for Cloudflare Workers static assets (`wrangler.jsonc`): connect the GitHub repository in the Cloudflare dashboard (Workers & Pages → Create → Import a repository) and use `npx wrangler deploy` as the deploy command. Every push to `main` then redeploys, and `_headers` applies the security headers.

Contributions are welcome. Please never include real personal data in issues, pull requests, test fixtures or screenshots.

## Licence

VisaFilla is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE). It uses [PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL) and [Pydantic](https://docs.pydantic.dev/) (MIT) in Python, and ships [pdf-lib](https://pdf-lib.js.org/) 1.17.1 (MIT) and Mozilla's [pdf.js](https://mozilla.github.io/pdf.js/) 6.4.299 (Apache-2.0) unmodified in `webapp/static/vendor/`.

The blank application form in `template/spain/` is the public Schengen visa application form published by the Spanish authorities and is included unchanged, for filling in only.
