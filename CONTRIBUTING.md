# Ablauf bei neuem Feature oder Fix

Die verbindlichen Grundsätze (Branching, Prüfungen, Secrets, Betrieb) stehen in der [DevOps-Vorlage](https://github.com/dla-marbach/devops). Regeln für KI-Agenten stehen in der `AGENTS.md`.

## Entwicklung

1. **Ticket:** Redmine-Ticket anlegen oder übernehmen. Darin die geplante Änderung, wesentliche Schritte und den Abschluss dokumentieren.
2. **Branch anlegen:** `git switch main && git pull && git switch -c feature/1234-kurzbeschreibung` (bzw. `fix/…`, mit Ticketnummer). Branches, die KI-Agenten selbst anlegen (z. B. `copilot/…`), behalten ihren Namen; die Ticketnummer steht dann im PR-Titel.
3. **Im Devcontainer entwickeln:** Codespace auf dem Branch oder lokal „Reopen in Container“. Tests ergänzen, Linter und Tests lokal ausführen: `ruff check . && ruff format --check .` und `pytest -q`. Der Sicherheitsscan (`trivy fs`) läuft in der CI.
4. **Pushen und Pull Request nach `main` öffnen:**
   - Titel mit Ticketnummer ohne „#“, z. B. „CSV-Export für Ergebnisse (Ticket 1234)“. `#1234` würde auf GitHub verlinken statt auf Redmine.
   - Beschreibung: Link zum Ticket, was sich ändert und warum, Breaking Changes und manuelle Upgrade-Schritte.
5. **Copilot-Review anfordern** (unter „Reviewers“). Hinweise umsetzen oder im PR begründen, warum nicht.
6. **CI abwarten:** Alle Checks müssen grün sein, bei Funden nachbessern. Ist `main` weitergegangen, „Update branch“ und erneut abwarten.
7. **Squash-Merge:** Prüfen, dass die Ticketnummer in der Commit-Nachricht steht. Danach lokal aufräumen: `git switch main && git pull --prune && git branch -D feature/1234-kurzbeschreibung`

## Release

`btc2premis` wird nicht als Container betrieben, deshalb weichen Release, Deployment und Rollback von der Vorlage ab (siehe „Projekte ohne Container-Betrieb“ in der DevOps-Vorlage). Ein Release ist ein Git-Tag; es gibt kein Image und kein Paket in einer Registry. Releases und Tags legen nur Menschen an, Tags werden nie verschoben oder wiederverwendet.

1. **CI prüfen:** Der letzte Lauf auf `main` muss grün sein.
2. **Version festlegen:** Patch (`v1.2.1`) für Fixes, Minor (`v1.3.0`) für Features, Major (`v2.0.0`) für Breaking Changes. Maßgeblich ist die größte Änderung seit dem letzten Release. Breaking Changes sind auch geänderte Inputs, Secrets oder Ausgabepfade der wiederverwendbaren Workflows sowie Änderungen an Dateinamen oder Struktur der Ausgabe.
3. **Version eintragen:** `version` in `pyproject.toml` per Pull Request auf die neue Version setzen (ohne „v“) und mergen.
4. **Release anlegen:** „Releases“ → „Draft a new release“, neuen Tag `vX.Y.Z` auf `main`, „Generate release notes“. Breaking Changes und manuelle Upgrade-Schritte im Daten-Repo (z. B. neue Secrets oder Inputs) ergänzen, dann „Publish release“.

## Deployment

Produktiv läuft `btc2premis` über die wiederverwendbaren Workflows `export-reusable.yml` und `api-snapshot-reusable.yml`, die die Trigger-Workflows im Daten-Repo aufrufen. Diese verweisen immer auf ein Release, nie auf `main`, und zwar an zwei Stellen mit derselben Version: im `uses:` (Workflow-Datei) und im Input `ref` (installierter Code):

```yaml
jobs:
  export:
    uses: dla-marbach/btc2premis/.github/workflows/export-reusable.yml@v1.3.0
    with:
      output-dir: data
      ref: v1.3.0
```

Neue Version im Daten-Repo einführen, zuerst als Test, dann produktiv:

1. **Vorbereiten:** Release Notes lesen, ggf. neue Secrets im Daten-Repo anlegen.
2. **Testen:** Im Daten-Repo einen Branch anlegen, in den Trigger-Workflows `uses:` und `ref` auf die neue Version setzen, `data/websites/` und `data/collections/` löschen (sonst exportiert der Lauf nur geänderte Crawl Configs neu, und die übrigen Dateien stammen noch von der alten Version), committen und Pull Request öffnen. Über „Actions“ → „Run workflow“ die Workflows auf diesem Branch starten. Sie committen das Ergebnis in den Branch; der Diff im Pull Request zeigt die Auswirkungen der neuen Version auf die Exportdaten.
3. **Produktiv nehmen:** Ist der Diff wie erwartet, den Pull Request per Squash mergen. Ab dem nächsten geplanten Lauf auf `main` gilt die neue Version. Sonst den Pull Request schließen und den Fix als neues Patch-Release ausliefern.

## Rollback

Die Exportdaten sind im Daten-Repo per Git versioniert; die Git-Historie ist die Sicherung. Ein Export schreibt nur geänderte Crawl Configs neu, falsch erzeugte Dateien bleiben deshalb stehen, bis sie zurückgesetzt werden.

1. **Version zurücksetzen:** Im Daten-Repo per Pull Request `uses:` und `ref` in den Trigger-Workflows wieder auf die vorherige Version setzen.
2. **Daten zurücksetzen:** Die Export-Commits seit dem Update im selben Pull Request mit `git revert` zurücknehmen. Der nächste Lauf exportiert dann alle seither geänderten Crawl Configs erneut mit der vorherigen Version. Alternativ `data/websites/` und `data/collections/` löschen; der nächste Lauf exportiert dann alle Crawl Configs neu.
3. **Prüfen:** Workflow über „Run workflow“ starten und das Ergebnis im Daten-Repo kontrollieren.

## Projektspezifisch

- Kein Container-Betrieb: Release, Deployment und Rollback wie oben beschrieben statt nach der Vorlage. Entsprechend entfallen Image-Build, Image-Scan, Smoketest, `release.yml` und `scan.yml`.
- Die wiederverwendbaren Workflows committen Exportdaten direkt auf `main` des aufrufenden Daten-Repos. Das ist zulässig, weil es sich um ein eigenes Daten-Repo handelt; in dieses Repository schreiben sie nicht.
