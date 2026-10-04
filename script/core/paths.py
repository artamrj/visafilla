"""Workspace assets, independent of the process working directory."""

from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SCRIPT_ROOT.parent
TEMPLATE_DIR = WORKSPACE_ROOT / 'template'
SPAIN_FORM_DIR = TEMPLATE_DIR / 'spain'
TEMPLATE = SPAIN_FORM_DIR / 'schengen_application.pdf'
