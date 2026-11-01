# ai_agentSwarm — Repo-Debris-Manifest

Zweck: reine Bestandsaufnahme der getrackten Altlasten in der Repo-Wurzel. Dieses
Dokument listet nur; es wird in diesem Sprint nichts gelöscht, verschoben,
untracked oder in `.gitignore` eingetragen (Rule 9: Löschen braucht Probelauf und
zweite Prüfung).

Basis-Commit der Messung: `02beef0687674fe03ad4d351933504d089ae2d34` (kurz
`02beef0`).

## Messmethode

- **Dateien**: Zeilenzahl von
  `git ls-tree -r --name-only <basis> -- <pfad>`.
- **Bytes**: Summe der Blob-Größen aus
  `git ls-tree -r -l <basis> -- <pfad>` (Größen-Spalte), als ganze Zahl ohne
  Tausendertrennzeichen.
- Blob-Größen stammen aus dem Git-Objekt und sind damit unabhängig von
  Zeilenenden des Checkouts; Größen aus dem Arbeitsbaum wären wegen CRLF falsch
  und werden hier nicht verwendet.
- Referenzwerte des Planers auf `089e875`: alle acht Wertepaare stimmen mit der
  Messung am Basis-Commit überein — keine Abweichung.

## Altlasten

| Pfad | Dateien | Bytes | lesbar | Grund | Vorschlag für später |
|---|---:|---:|---|---|---|
| `.pytest-tmp/` | 14 | 4969 | ca. 4,9 KiB | pytest-Temp-Ausgabe, versehentlich getrackt | untracken + `.gitignore` nach Probelauf |
| `.pytest_basetemp/` | 4 | 1205 | ca. 1,2 KiB | pytest-Temp-Ausgabe, versehentlich getrackt | untracken + `.gitignore` nach Probelauf |
| `.git_e2e_out.txt` | 1 | 254956 | ca. 249 KiB | Ausgabe eines Git-E2E-Laufs | untracken + `.gitignore` nach Probelauf |
| `git_sandbox_test_out.txt` | 1 | 12768 | ca. 12,5 KiB | Testausgabe | untracken + `.gitignore` nach Probelauf |
| `git_vol_test_out.txt` | 1 | 12432 | ca. 12,1 KiB | Testausgabe | untracken + `.gitignore` nach Probelauf |
| `logs/` | 2 | 3704 | ca. 3,6 KiB | Goal-Laufprotokolle `logs/goals/*.json` | untracken + `.gitignore` nach Probelauf |
| `apps/agentswarm-task-console/target/` | 2181 | 855337272 | ca. 816 MiB | getrackte Cargo-Build-Ausgabe, größter Posten | untracken + `.gitignore` nach Probelauf (vorher Build-Reproduzierbarkeit prüfen) |
| `ROADMAP_20260603_153456.md` | 1 | 33170 | ca. 32,4 KiB | zeitgestempeltes Duplikat; Blob `e786eb4` (`e786eb4960a8051922cb5d1ed18e74c4ee6f48d4`) ist identisch mit `docs/reviews/ROADMAP_20260603_153456.md` (`git ls-tree`). Verweise (`git grep -n ROADMAP_20260603`): `ROADMAP_DISTRIBUTED_CLIENTS.md:416` nennt den Namen ohne Ordner, `docs/execution-plan.md:1160` verlinkt die Kopie unter `docs/reviews/`; sonst nur die Datei selbst. | vor einem späteren Untracken die Verweise in `ROADMAP_DISTRIBUTED_CLIENTS.md` prüfen, dann untracken (Kopie unter `docs/reviews/` bleibt) |

## Nicht in diesem Sprint

Rule 9: Löschen braucht einen Probelauf und eine zweite Prüfung — beides ist
nicht Teil dieses Sprints. In diesem Sprint wird daher **nichts gelöscht oder
verschoben**, nichts untracked und nichts in `.gitignore` eingetragen. Dieses
Dokument ist ausschließlich eine Liste.

## Bewusst nicht aufgenommen

Diese getrackten Wurzeldateien sind keine Altlasten, sondern gepflegte
Konfiguration oder Dokumentation für Menschen:

- `INFO.txt` — Hinweisdatei für Menschen, ausdrücklich `NEVER EDIT`.
- `.env.example` — Vorlage für Umgebungsvariablen.
- `.gitattributes` — Git-Konfiguration.
- `.gitignore` — Git-Konfiguration.
- `CONTRIBUTING.md` — Beitragsleitfaden.
- `GOAL.md` — Projektziel.
- `LICENSE` — Lizenz.
- `README.md` — Einstieg.
- `ROADMAP.md` — aktuelle Roadmap.
- `ROADMAP_CHANGES.md` — Roadmap-Änderungen.
- `ROADMAP_DISTRIBUTED_CLIENTS.md` — aktive Roadmap, enthält den Verweis auf das
  Duplikat oben.
