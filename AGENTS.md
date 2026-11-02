# AGENTS.md

Regeln für KI-Agenten in diesem Repository. Zweck, Aufbau und Befehle des Projekts stehen im README.

## Umgebung
- Lokal und in Codespaces läuft die Entwicklung im Devcontainer (`.devcontainer/`).
- Fehlt ein Werkzeug, benenne es im PR; die Ergänzung gehört in `.devcontainer/`.

## Checks vor Abschluss
- Maßgeblich sind die Schritte in `.github/workflows/ci.yml`. Führe Linter und Tests lokal genauso aus wie die CI: `ruff check . && ruff format --check .` und `pytest -q`. Der Sicherheitsscan (`trivy fs`) läuft nur in der CI; behebe seine Funde.
- Linter und alle Unit-Tests müssen grün sein. Neue Funktionen und Fixes bekommen eigene Tests.

## Git und Pull Requests
- Jede Änderung gehört zu einem Redmine-Ticket. Arbeite in einem Branch `feature/<ticket>-<kurzbeschreibung>` oder `fix/<ticket>-<kurzbeschreibung>`, nie direkt auf `main`. Vergibt dein Werkzeug den Branch-Namen selbst (z. B. `copilot/…`), behalte ihn und nenne die Ticketnummer im PR-Titel. Fehlt die Ticketnummer, frage danach.
- Halte Änderungen klein und auf eine Aufgabe beschränkt. Gemergt wird per Squash, und zwar nur durch Menschen.
- Nenne die Ticketnummer im PR-Titel ohne „#“ (z. B. „… (Ticket 1234)“), verlinke das Ticket in der Beschreibung und beschreibe, was sich ändert und warum. Breaking Changes und manuelle Upgrade-Schritte (z. B. geänderte Ausgabe, neue Workflow-Inputs oder Secrets) werden zusätzlich in die Release Notes übernommen.
- Setze Hinweise aus dem Copilot-Review um oder begründe im PR, warum nicht.

## Abhängigkeiten
- Updates von Abhängigkeiten, GitHub Actions und Base Images übernimmt Dependabot. Ändere Versionen nur, wenn die Aufgabe es erfordert.
- Füge neue Abhängigkeiten nur hinzu, wenn die Aufgabe es erfordert, und begründe sie im PR. Das Paket kommt zur Laufzeit ohne Abhängigkeiten aus; das soll so bleiben.
- Base Image in `.devcontainer/Dockerfile` immer mit festem Versionstag, nie `latest`. GitHub Actions per Commit-SHA.

## Betrieb
- `btc2premis` ist ein Kommandozeilenwerkzeug und wird nicht als Container betrieben. Produktiv läuft es über die wiederverwendbaren Workflows in `.github/workflows/*-reusable.yml`, die ein separates Daten-Repo per Release-Tag aufruft (siehe `CONTRIBUTING.md`).
- Konfiguration und Zugangsdaten nur über Umgebungsvariablen (`BTC_USER`, `BTC_PASSWORD`, `BTC_OID`, `BTC_BASE_URL`) oder `--password-file`, nie als Kommandozeilenargument.
- Änderungen an Inputs, Secrets oder Ausgabepfaden der wiederverwendbaren Workflows sind Breaking Changes für das Daten-Repo.
- Versionen folgen SemVer (`vX.Y.Z`). Tags und Releases legen nur Menschen an.

## No-Gos
- Keine Secrets, Tokens oder Passwörter in Code, Tests, Logs oder Commits.
- Keine personenbezogenen Daten oder Produktivdaten in Code, Tests, Beispieldaten, Logs oder Commits. Test- und Beispieldaten sind synthetisch.
- Tests nicht abschwächen oder löschen und Checks oder Scans nicht deaktivieren oder unterdrücken, um die CI grün zu bekommen.
- Keine Einträge in `.trivyignore`. Ausnahmen für Sicherheitsfunde legen nur Menschen an.
- `.github/` und `.devcontainer/` nur auf ausdrückliche Anweisung ändern.

## Projektspezifisch
- Die Tests laufen ohne Netzwerk gegen eine Fake-API aus `tests/fixtures/` (eine JSON-Datei je Endpunkt). Neue Fixtures sind synthetisch; echte Antworten aus der Browsertrix-Instanz nicht übernehmen.
- Ändert sich die Ausgabe, die Beispieldateien in `docs/` mit aktualisieren.
- README und `docs/` sind auf Englisch, `AGENTS.md` und `CONTRIBUTING.md` auf Deutsch.
