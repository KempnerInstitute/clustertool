"""Tests for the README properties that PyPI depends on."""

import pathlib
import re

README = pathlib.Path(__file__).resolve().parent.parent / "README.md"
RAW_PREFIX = "https://raw.githubusercontent.com/KempnerInstitute/clustertool/main/"


def _sources(text: str) -> list[str]:
    """Return every image source in the README, from both img and source tags."""
    return re.findall(r'(?:src|srcset)="([^"]+)"', text)


def test_every_image_source_is_absolute():
    """PyPI resolves a relative path against pypi.org, where it does not exist."""
    relative = [src for src in _sources(README.read_text()) if not src.startswith("https://")]
    assert relative == []


def test_referenced_assets_are_in_the_repository():
    text = README.read_text()
    root = README.parent
    assets = [src.removeprefix(RAW_PREFIX) for src in _sources(text) if src.startswith(RAW_PREFIX)]
    assert assets, "the README should serve its pictures from the repository"
    missing = [asset for asset in assets if not (root / asset).is_file()]
    assert missing == []


def test_no_mermaid_diagram():
    """PyPI prints a mermaid fence as source text instead of drawing it."""
    assert "```mermaid" not in README.read_text()
