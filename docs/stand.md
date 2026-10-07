# Stand: Molekül-Viewer

> **Kurzfassung — ganz lesen.** Enthält: die zwei neuesten Einträge, die bekannten Fallstricke + Stand der Ausbaustufen, und „Zum Wiedereinsteigen“.
> Alle älteren Einträge (jede Ausbaustufe im Detail, Deployment, Boltz-2-Einrichtung, Docking, MD …) stehen unverändert in `docs/verlauf.md`. Verweise wie „siehe Eintrag oben“ meinen meist dort — **nur gezielt per grep lesen, nie komplett.**
> Pflege: neue Einträge oben einfügen; wird diese Datei größer als ~20 KB, die ältesten datierten Einträge nach `verlauf.md` (oben) verschieben.

## 2026-10-06 (später): Grill-Runde mit Niki + Ausbau, ZWISCHENSTAND (Nutzungslimit)

Leitlinie von Niki: **„wie Apple“, intuitiv, einfach**. Gute Standardwerte,
Schalter in Alltagssprache, Details aufklappbar (`createDetails()` in app.js).

**Fertig + gepusht:** Glucagon (1GCN im Suchfeld/Bibliothek, Name im
Boltz-Bereich, `28c1b87`). **Docking** (`c71c348`): Bindetasche war vom
Kristall-Liganden + Wasser besetzt (meeko bekam ganze PDB-Datei), jetzt nur
ATOM-Zeilen -> Benzamidin 0,2 Å neben Kristallposition, Salzbrücke zu
Asp189 2,95 Å, −6,1 statt −4,0 kcal/mol; Ligand in Ladungsform bei pH 7,4
(Dimorphite-DL, Schalter „Wie im Körper“); lesbarer Proteinname; Protein
halbtransparent, Kamera auf Tasche. **MD** (`744562f`): echte Ursache der
Instabilität = RDKit `CalcGrad(pos)` nutzt Abstands-Cache, den nur
`CalcEnergy(pos)` erneuert -> Fix, Force-Capping raus, RATTLE für X-H
(1 fs, 800 fs), Schalter „Schnelle Wasserstoff-Schwingungen zeigen“, erste
MD-Tests. **4 Reaktionen** (`04276ca`): Aspirin-Synthese, Peptidbindung,
Diels-Alder, Verseifung + Balance-Test.

**Im letzten Commit, nur teilweise geprüft:** Handy-Ansicht (Canvas drückte
Seite auf 618 px -> alle 9 Bereiche jetzt 375 px ohne Seitwärts-Scrollen,
geprüft), Summenformel tiefgestellt, leere „–“-Kacheln + Entwickler-Hinweis
zum API-Key ausgeblendet (geprüft), UTF-8 beim Lesen der Boltz-/Vina-Ausgabe.
Boltz-Röhren-Ansicht ab 60 Resten + Schalter „Alle Atome zeigen“ +
vereinfachte Ergebnisanzeige: **Code fertig, im Browser NOCH NICHT getestet.**

**Boltz-Grenze:** 515 Reste (verkettete Testproteine) liefen in 193 s,
VRAM-Spitze 11,8 GB. 1030-Reste-Lauf gestartet, Ergebnis nicht mehr
abgewartet. `MAX_RESIDUES` steht weiter auf 250.

**Offen:** Röhren-Ansicht im Browser testen (z.B. GFP), 1030er-Lauf
wiederholen und Limit (vermutlich ~500) setzen, Bildausschnitt/Schatten
großer Moleküle, Bibliothek-Karten mit echtem Namen statt „Peptid-Ligand aus
1GCN“, Einfachheits-Durchgang über die übrigen Hinweistexte, ausführliche
Doku dieses Eintrags + Wiki-Seite, Live-Seite nach Render-Deploy prüfen
(neue Abhängigkeit dimorphite_dl).

## 2026-10-06: Boltz-2-Darstellung erneut end-to-end bestätigt, Limit 50 → 250 Reste, zwei Viewer-Fixes

Auftrag von Niki: Boltz-2-Faltung im sichtbaren Browser mit Screenshot und
fehlerfreier Konsole nachweisen, `MAX_RESIDUES` empirisch testen (Laufzeit
**und VRAM**), Limit falls nötig anpassen. Die visuelle Bestätigung und
eine erste Laufzeitmessung gab es schon am 2026-09-20 (siehe unten), aber
noch keine VRAM-Messung, und seitdem wurde das Frontend auf die Sidebar
umgebaut. Deshalb heute frisch nachgewiesen.

**Darstellung: funktioniert, mit Screenshots belegt (`docs/screenshots/`).**
Alle Läufe über die normale Oberfläche (Sidebar → „Protein-Faltung
(Boltz-2)“ → Sequenz eintippen → „Vorhersagen“), Konsole nach jedem Lauf
komplett leer (keine Fehler, keine Warnungen). Zusätzlich die Rohdaten aus
der `/api/fold`-Antwort im Browser geprüft (Fetch-Hook): keine NaN-Werte,
keine isolierten Atome, Bindungslängen plausibel. Atomzahlen und
Summenformeln passen exakt zu den echten Proteinen (Boltz' CIF lässt nur
das C-terminale OXT weg, daher jeweils ein O weniger):
- `boltz2-oxytocin.jpg`: Oxytocin (9 AS), Ring mit sichtbarer
  Disulfidbrücke (gelbe S-Atome) und Schwanz.
- `boltz2-melittin-26.jpg`: Melittin (26 AS), 200 Atome, C131N38O31,
  202 Bindungen (= 199 Kette + 3 Ringschlüsse Trp/Pro), längliche
  helikale Form.
- `boltz2-crambin-46.jpg`: Crambin (46 AS, PDB 1CRN), 326 Atome,
  C202N55O63S6, **alle 3 Disulfidbrücken** korrekt erkannt, 336 Bindungen
  (= 325 + 3 SS + 8 Ringe), kompakt-globulär.
- `boltz2-gfp-238.jpg`: GFP (238 AS), 1895 Atome. Die Szene läuft mit
  ~62 fps, das Rendering ist also kein Engpass.

**Messwerte (RX 7900 XTX, ROCm; Gesamtzeit inkl. Prozessstart,
Gewichte-Laden und MSA-Server; VRAM = Spitze des Boltz-Prozesses laut
Windows-GPU-Leistungsindikator, Sampling ca. alle 1,5 s, kurze Spitzen
können also etwas höher liegen):**

| Sequenz | Reste | Zeit | VRAM-Spitze | pLDDT / pTM |
|---|---|---|---|---|
| Oxytocin | 9 | 63 s (erster, kalter Lauf) | 2,7 GB | 88 / 0,15 |
| Melittin | 26 | 51 s | 2,7 GB | 93 / 0,52 |
| Crambin | 46 | 50 s | 2,7 GB | 95 / 0,87 |
| Ubiquitin | 76 | 52 s | 4,6 GB | 94 / 0,92 |
| Lysozym (Hühnerei) | 129 | 53 s | 5,2 GB | 98 / 0,96 |
| GFP | 238 | 57-58 s | 4,1-5,2 GB | 95 / 0,93 |

Kernbefund: **Die Laufzeit hängt bis 238 Reste praktisch nicht von der
Länge ab.** Die eigentliche GPU-Phase dauert nur ~15 s, der Rest ist
Overhead. Der VRAM bleibt weit unter den 24 GB der Karte. Die
Messung vom 2026-09-20 („50 Reste ~73 s, überlinear“) ließ sich nicht
bestätigen; vermutlich war damals der MSA-Server langsamer, die Daten von
damals sind nicht mehr vorhanden. Ubiquitin/Lysozym/GFP liefen über ein
Benchmark-Skript direkt gegen `folding.build_folding()` (Limit
vorübergehend umgangen), GFP danach mit neuem Limit nochmal echt über die UI.

**`MAX_RESIDUES` 50 → 250** (`folding.py`, Kommentar mit den Messwerten).
250 = knapp über der längsten Sequenz, die end-to-end inklusive Darstellung
geprüft wurde (GFP). Mehr wäre von Laufzeit und VRAM her wohl möglich, ist
aber nicht getestet, daher bewusst nicht weiter. Fehlermeldung und
`test_fold_too_long_sequence_returns_400` (jetzt 251 Reste) angepasst.

**Zwei Viewer-Bugs dabei gefunden und behoben:**
1. **Kamera-Zoom-Grenze schnitt größere Strukturen ab** (`viewer.js`,
   `frameBox()`). `frameBox()` berechnet den passenden Kameraabstand
   (~3,95 × Radius bei 40° FOV), aber `controls.maxDistance = 60` war fest,
   und `controls.update()` zog die Kamera damit ab ~15 Å Radius wieder auf
   60 heran. Ab ~40 Resten wird das Molekül so zu nah gezeigt, bei
   GFP-Größe wäre es abgeschnitten gewesen, und man konnte auch per Mausrad
   nicht weiter herauszoomen. Fix: `maxDistance` skaliert jetzt mit
   (`Math.max(60, distance * 3)`). Kleine Moleküle sind unverändert
   (Regressionscheck mit Aspirin). Docking/Reaktionen nutzen dieselbe
   Funktion und profitieren mit. Nebeneffekt: mittelgroße Faltungen (Melittin,
   Crambin) wirken jetzt kleiner als vorher, weil die Bounding-Sphere der
   Box großzügig ist. Per Mausrad lässt sich heranzoomen.
2. **Lange Sequenzen liefen aus dem Info-Kasten** (`style.css`,
   `.chemspace-info`): der Anzeigename ist die rohe Sequenz ohne
   Leerzeichen. Fix: `overflow-wrap: anywhere`.

**Sichtbarkeit des Browser-Panes, für künftige Sichtprüfungen:** Das Pane
war in dieser Session laut `tabs_context` die ganze Zeit „hidden“. Direkt
nach dem Öffnen lief `requestAnimationFrame` trotzdem (145 fps), später
lieferte es 0 Frames, bis ein Screenshot einen echten Frame anstieß (danach
wieder ~62 fps). Das ist die bekannte Pane-Drosselung, kein App-Fehler. Die
Screenshots sind echte gerenderte Frames. **Wer live zusehen will: im
Claude-Desktop-App Strg+Shift+B drücken.**

**Getestet:** 4 Browser-Läufe über die UI + 3 Benchmark-Läufe, alle 45
Backend-Tests grün (inkl. echtem Boltz-Lauf), Aspirin-Regressionscheck.


**Bekannte Fallstricke:**
1. Die "niedrigste-CID"-Heuristik für die Formel-Mehrdeutigkeit ist eine
   einfache Näherung, kein echtes "Popularitäts-Ranking". Bei C6H12O6 hat sie
   z. B. "Hexopyranose" gewählt (ein allgemeiner Zucker-Oberbegriff), nicht
   konkret "D-Glukose". Der Hinweistext ist trotzdem korrekt und ehrlich —
   nur die Wahl selbst ist manchmal nicht die intuitivste. Mögliche
   Verbesserung später: nach Literatur-/Annotation-Anzahl bei PubChem filtern
   statt nach roher CID, oder Kandidaten mit definierter Stereochemie
   bevorzugen.
2. PubChems Property-Feld heißt aktuell `ConnectivitySMILES`, nicht
   `CanonicalSMILES` (API hat sich offenbar geändert) — falls PubChem das
   nochmal umbenennt, ist das die erste Stelle zum Nachschauen
   (`backend/chem.py`, Funktionen `_pubchem_lookup_by_name` /
   `_pubchem_lookup_by_formula`).
3. ~~Bei direkter SMILES-Eingabe wird als Anzeigename einfach der SMILES-Code
   selbst zurückgegeben~~ — behoben am Nachmittag des 2026-09-14, siehe oben
   (Rückwärtssuche bei PubChem per SMILES).
4. ~~PubChem-Anfragen haben kein Retry/Caching — bei wiederholten Anfragen zum
   selben Molekül wird jedes Mal neu angefragt.~~ — Caching ergänzt am
   2026-09-19 (später), siehe Eintrag oben (`chem.py`, einfacher
   In-Memory-Cache). Retry gibt es weiterhin nicht, war auch nicht das
   eigentliche Problem.

**Stand der 6 vereinbarten Ausbaustufen** (Details siehe Claude-Gedächtnis,
`project_molecule_viewer.md`, oder frag einfach danach; Stand: Abend des
2026-09-14, nach dem autonomen Durchlauf):
1. ✅ Erledigt — web-basiert statt Blender (Three.js statt 3Dmol.js).
2. ✅ Erledigt — drei Darstellungs-Layer (Kugel-Stab, Raumfüllend, Ladung),
   umschaltbar über Buttons.
3. ✅ Erledigt — Fakten-Panel (Summenformel, Molmasse, LogP, TPSA, H-Brücken,
   drehbare Bindungen), lokal mit RDKit berechnet.
4. ✅ Erledigt — Vergleichsmodus (zwei Moleküle nebeneinander, "+ Vergleichen").
5. ⚠️ Fast erledigt — KI-Erklärtext ist eingebaut und läuft, **wartet aber
   auf einen `ANTHROPIC_API_KEY` von Niki** (siehe Eintrag oben). Zeigt bis
   dahin einen klaren "nicht verfügbar"-Hinweis statt zu crashen.
6. ✅ Erledigt — Reaktions-Animation (Veresterung als Beispiel), Auswahl-Menü
   + Abspiel-Button + Morph-Animation mit Bindungs-Fade. Siehe Eintrag ganz
   oben für den genauen Stand und das Rezept für weitere Reaktionen.


## Zum Wiedereinsteigen

**Das Projekt ist jetzt live: https://molecule-viewer.onrender.com** (Render
Free-Tier, Deployment-Details siehe Eintrag ganz oben). Render-Dashboard:
einloggen mit Nikis Google-Account, Service heißt `molecule-viewer`,
Service-ID `srv-dantbfjtqb8s73d39tfg`.

**Neuen Stand veröffentlichen:** einfach `git push origin main` — Render
deployt automatisch neu, auch ohne die GitHub-App-Verbindung (siehe Eintrag
oben Punkt 2, per echtem Test bestätigt). Dauert ca. 1-2 Minuten
(Docker-Layer-Cache macht wiederholte Builds schnell, sofern sich
`requirements.txt` nicht ändert). Build-/Laufzeit-Logs direkt im
Render-Dashboard unter "Logs" (Chrome-Browser mit Nikis eingeloggter
Render-Session, gleiches Muster wie beim GitHub-Repo) — Shell-Zugriff gibt
es auf dem Free-Tier nicht (nur per Upgrade).

**Lokal weiterentwickeln, wie gewohnt:**
```bash
cd "Claude Code Projekte/molecule-viewer/backend"
./.venv/Scripts/python.exe -m uvicorn app:app --reload --port 8001
```

**Server läuft nach dem 2026-09-20-Durchlauf bereits im Hintergrund** (ohne
`--reload`, PID siehe `netstat -ano | grep ":8001"` falls nötig) — vor einem
Neustart kurz prüfen, ob das noch die gewünschte Instanz ist.

**Neu seit der Boltz-2-Ausbaustufe:** für die Protein-Struktur-Vorhersage
(`/api/fold`) gibt es eine zweite, komplett separate venv,
`backend/.venv-boltz` (Python 3.12, nicht 3.14 wie `backend/.venv` --
Boltz-2 braucht `<3.13`). Die läuft nicht automatisch mit, ist aber schon
fertig eingerichtet (ROCm-PyTorch + Boltz 2.2.1, Gewichte bereits unter
`~/.boltz/` gecacht, ca. 5,8 GB). `folding.py` findet sie automatisch über
`BOLTZ_VENV`/`BOLTZ_BINARY` in seinem Modul-Kopf. Falls diese venv fehlt
oder neu aufgesetzt werden muss, siehe den vollen Befehlsablauf im Eintrag
vom 2026-09-20 oben (Phase 0) -- **wichtig: `--no_kernels` beim
`boltz predict`-Aufruf nicht vergessen** (steht schon fest in
`folding.py` eingebaut), sonst bricht jede Vorhersage auf der AMD-GPU mit
`ModuleNotFoundError: cuequivariance_torch` ab.

**Falls Port 8001 "Method Not Allowed" auf neuen Routen zurückgibt, obwohl
der Code sie enthält:** ein alter Uvicorn-Prozess von einer früheren
Sitzung hängt noch am Port (`netstat -ano | grep ":8001.*ABH"` zeigt dann
zwei Einträge). `pkill -f "uvicorn app:app"` reicht nicht zuverlässig —
stattdessen die PID(s) aus `netstat` mit `taskkill /F /PID <pid> /T`
beenden, dann neu starten.

**Falls nach einer Backend-Änderung `--reload` "Reloading..." loggt, die
Antwort aber trotzdem alt bleibt:** hart neu starten — alte Prozesse per
`taskkill /F /PID <pid> /T` beenden (PID aus `netstat -ano | grep
":8001.*ABH"`), `rm -rf backend/__pycache__`, dann neu starten. Trat beim
Bau von Protein-Docking einmal auf, vermutlich eine mtime-Verzögerung durch
OneDrive-Sync im Projektordner.

**Falls die Seite nach einer Frontend-Änderung (`style.css`/`app.js`) optisch
oder funktional noch alt aussieht:** Browser-Cache, kein Server-Problem (der
Static-File-Mount hat keine `--reload`-Funktion und braucht keine) — hart neu
laden (Strg+Shift+R), siehe Fallstrick im Eintrag vom 2026-09-19 (autonomer
Durchlauf) oben.

Dann **`http://localhost:8001`** im Browser öffnen (Port 8001, nicht 8000 —
siehe Fallstrick oben). Ganz oben die neue **Bibliothek** ausprobieren — auf
ein paar Karten klicken (z. B. "Aspirin", "Vitamin C"), unter "Peptid-
Wirkstoffe" auf "Ozempic / Semaglutid" (PDB `4ZGM`) und "Insulin (an seinem
Rezeptor)" (PDB `4OGA`, zwei Ketten A+B) — beide über `/api/pdb-ligand`,
kein Docking, dauert beim ersten Mal einen Moment — und unter "Kleine Peptide
(angenäherte Faltung)" auf "Oxytocin" oder "Vasopressin" (über `/api/peptide`,
zeigt die per Disulfidbrücken-Heuristik geknäulte Struktur), plus im
Eingabefeld darunter eine eigene Sequenz eintippen (z. B. `GRGDSP`) oder eine
zu lange (>15 Reste) zum Prüfen der Fehlermeldung. Danach Eingabefeld
testen mit z. B. `aspirin`, `C6H12O6`,
`CCO`, die drei Darstellungs-Buttons durchklicken, "+ Vergleichen" mit einem
zweiten Molekül ausprobieren, unten die Veresterung über "▶ Ablaufen
lassen" abspielen, beim neuen "Gleichungslöser"-Bereich "Beispiel laden"
(füllt `CH4 + O2 -> CO2 + H2O`) + "Lösen & animieren" ausprobieren (oder
z. B. `N2 + H2 -> NH3` von Hand eintippen), beim "Chemischer Raum"-Bereich
"Beispiel-Set laden" + "Karte erzeugen" ausprobieren, bei "Protein-Docking"
"Beispiel laden" (füllt `3PTB` + `benzamidine`) + "Docken" ausprobieren
(dauert beim allerersten Mal am längsten, danach ist die Rezeptor-
Vorbereitung für `3PTB` in `backend/pdb_cache/` gecacht und es geht
schnell), und bei "Molekulardynamik" "Beispiel laden" (füllt
`caffeine`) + "Simulieren" — sollte nach ~1 Sekunde ein sichtbar
wackelndes Molekül zeigen. **Ganz unten neu: "Protein-Struktur-Vorhersage
(Boltz-2)"** — "Beispiel laden" (füllt "Oxytocin") + "Vorhersagen", dauert
diesmal wirklich ~30-60s (echter GPU-Rechenlauf + MSA-Server-Aufruf, siehe
Eintrag vom 2026-09-20 oben). 3D-Rendering per Screenshot bestätigt
(kompakte, sichtbar gefaltete Peptidstruktur), zuletzt am 2026-10-06 bis
238 Reste (GFP); Limit jetzt 250 Reste, ~50-60 s unabhängig von der Länge,
siehe Eintrag ganz oben.

Falls die venv fehlt oder kaputt ist: `python -m venv .venv` im `backend`-
Ordner, dann `./.venv/Scripts/python.exe -m pip install -r requirements.txt`
(für Backend-Tests zusätzlich `-r requirements-dev.txt`, siehe README).
**Zusätzlich** liegt unter `backend/tools/vina.exe` die AutoDock-Vina-Binary
— die ist keine Python-Abhängigkeit und muss beim venv-Neuaufsetzen nicht
neu installiert werden, nur falls der ganze `backend`-Ordner fehlt: neu
laden von `github.com/ccsb-scripps/AutoDock-Vina/releases` (Datei
`vina_1.2.7_win.exe`, umbenennen zu `vina.exe`). Für die Molekulardynamik
und den Gleichungslöser ist nichts Zusätzliches nötig — beide nutzen nur
schon vorhandene Pakete (RDKit, numpy, scipy).

**Alle 6 ursprünglich vereinbarten Ausbaustufen sind erledigt, plus alle
3 der "richtig aufwendigen" API-freien Folge-Ausbaustufen (chemischer
Raum, Protein-Docking, Molekulardynamik), plus eine 10. (Gleichungslöser),
eine 11., zweiteilige Ausbaustufe vom 2026-09-19 (autonomer Durchlauf):
PDB-Liganden direkt anzeigen (`/api/pdb-ligand`) + Bibliothek-Bereich im
Frontend, samt Folge-Ergänzung um Insulin an seinem Rezeptor (4OGA, per
neuem `chain_ids`-Parameter), eine 12.: kleine Peptide per
Sequenzeingabe (`/api/peptide`, bis 15 Reste, mit Disulfidbrücken-Heuristik
und energieärmster von mehreren Konformeren, siehe Eintrag ganz oben), und
eine 13. (2026-09-20, autonomer Durchlauf): echte Protein-Struktur-
Vorhersage mit Boltz-2 (`/api/fold`, GPU-beschleunigt über ROCm auf der RX
7900 XTX, separate venv, siehe Eintrag ganz oben — 3D-Rendering per
Screenshot bestätigt).**
Einzige offene Lücke aus dem Kern: KI-Erklärtext (Ausbaustufe 5)
wartet weiter auf einen `ANTHROPIC_API_KEY` von Niki — `backend/.env.example`
nach `backend/.env` kopieren, echten Key eintragen, Server neu starten.
Alles andere läuft schon ohne das.

**Projekt ist seit dem 2026-09-20-Durchlauf (später) live deployt, siehe
Eintrag ganz oben: https://molecule-viewer.onrender.com.** Formel-
Mehrdeutigkeits-Heuristik, PubChem-Retry und das Export/Screenshot-Feature
sind ebenfalls erledigt (gleicher Eintrag). **Nächste Schritte sind
komplett offen** — es gibt keine vereinbarte Ausbaustufe mehr, die noch
aussteht. Ideen für kleinere Lücken/Politur, falls gefragt: weitere
Reaktionen zu `backend/reactions.py` ergänzen (Rezept siehe oben), beim
Protein-Docking die Ladungszustände des Liganden vor dem Docken
berücksichtigen (bewusst zurückgestellt, siehe Einschränkung oben), bei der
Molekulardynamik echte Bindungslängen-Constraints (SHAKE/RATTLE) einbauen
(ebenfalls bewusst zurückgestellt), die Atom-Zuordnung im Gleichungslöser
verbessern (z. B. per lokaler Bindungsumgebung statt reinem Abstand vor-
matchen, siehe Eintrag vom 2026-09-19), weitere Peptid-Wirkstoffe/Klein-
Molekül-Karten zur Bibliothek ergänzen (z. B. per `hetero_code` oder
`chain_ids`, siehe die beiden 2026-09-19-Einträge oben), die kuratierte
Peptid-Namensliste in `peptide.py` erweitern, GitHub-Auto-Deploy in Render
verbinden (braucht Nikis OAuth-Freigabe, siehe Deployment-Eintrag), oder
einen eigenen `ANTHROPIC_API_KEY` im Render-Dashboard eintragen, damit die
KI-Erklärung auch auf der öffentlichen Instanz läuft — aber erst wieder
anfangen, wenn Niki eine neue Richtung vorgibt.

