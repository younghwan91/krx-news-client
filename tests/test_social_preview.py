"""Social preview card: the pitch is the README's, and the committed PNG fits GitHub's limits."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_social.py"

if not SCRIPT.exists():  # sdist ships tests without scripts/ and docs/
    pytest.skip("scripts/make_social.py not in this tree", allow_module_level=True)

_spec = importlib.util.spec_from_file_location("make_social", SCRIPT)
SP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SP)


def test_card_quotes_the_readme_pitch_verbatim():
    readme = SP.README.read_text("utf-8")
    name, pitch, _ = SP.readme_text(readme)
    bold = re.search(r"^\*\*(.+)\*\*\s*$", readme, re.MULTILINE).group(1)
    assert pitch == bold.replace("*", "")
    html = SP.card_html()
    assert SP.escape(pitch) in html and name in html


def test_card_makes_no_network_request():
    assert not re.search(r"https?://(?!www\.w3\.org/)", SP.card_html())


def test_committed_png_is_1280x640_and_under_1mb():
    assert SP.png_size(SP.OUT) == (1280, 640)
    assert SP.OUT.stat().st_size < SP.MAX_BYTES
