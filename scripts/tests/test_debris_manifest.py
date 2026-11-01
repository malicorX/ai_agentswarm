"""Tests fuer docs/REPO-DEBRIS-MANIFEST.md.

Das Dokument ist eine reine Liste der getrackten Altlasten in der Repo-Wurzel.
Es wird erst hier im Test gelesen (UTF-8); ohne Dokument schlagen beide Tests
fehl (Rot vor Gruen).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "REPO-DEBRIS-MANIFEST.md"

# Pfade exakt wie im Auftrag: Ordner mit abschliessendem '/', Dateien ohne.
DEBRIS_PATHS = [
    ".pytest-tmp/",
    ".pytest_basetemp/",
    ".git_e2e_out.txt",
    "git_sandbox_test_out.txt",
    "git_vol_test_out.txt",
    "logs/",
    "apps/agentswarm-task-console/target/",
    "ROADMAP_20260603_153456.md",
]


def _table_rows(text):
    """Liefert alle Markdown-Tabellenzeilen als Liste von Zellen."""
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def test_manifest_lists_debris():
    text = MANIFEST.read_text(encoding="utf-8")
    rows = _table_rows(text)
    for path in DEBRIS_PATHS:
        matches = [row for row in rows if path in row[0]]
        assert len(matches) == 1, f"erwarte genau eine Tabellenzeile fuer {path}"
        row = matches[0]
        assert len(row) >= 6, f"zu wenige Spalten fuer {path}: {row}"
        # Spalten: Pfad | Dateien | Bytes | lesbar | Grund | Vorschlag
        assert row[1].isdigit(), f"Dateien ist keine ganze Zahl fuer {path}: {row[1]!r}"
        assert row[2].isdigit(), f"Bytes ist keine ganze Zahl fuer {path}: {row[2]!r}"
        assert row[4], f"Grund fehlt fuer {path}"
        assert row[5], f"Vorschlag fehlt fuer {path}"


def test_manifest_says_nothing_deleted():
    text = MANIFEST.read_text(encoding="utf-8")
    assert "Rule 9" in text
    for heading in ("Nicht in diesem Sprint", "Bewusst nicht aufgenommen"):
        assert heading in text, f"Ueberschrift fehlt: {heading}"
    tail = text[text.index("Bewusst nicht aufgenommen"):]
    assert "INFO.txt" in tail, "INFO.txt fehlt hinter 'Bewusst nicht aufgenommen'"
