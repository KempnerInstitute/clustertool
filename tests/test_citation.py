"""Tests for the citation file."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CITATION = ROOT / "CITATION.cff"
PYPROJECT = ROOT / "pyproject.toml"


def _cited_version() -> str:
    return re.search(r"^version: (\S+)$", CITATION.read_text(), re.M).group(1)


def _package_version() -> str:
    return re.search(r'^version = "(\S+)"$', PYPROJECT.read_text(), re.M).group(1)


def test_the_cited_version_is_the_package_version():
    """A release raises both, since the citation names the version it is for."""
    assert _cited_version() == _package_version()


def test_the_citation_names_the_author_and_the_license():
    text = CITATION.read_text()
    assert "Research Engineering Team, Kempner Institute, Harvard University" in text
    assert "license: MIT" in text
