# Stand: Molekül-Viewer

## 2026-09-19 (Fortsetzung): Insulin an seinem Rezeptor (4OGA) ergänzt

Direkte Folge auf den Eintrag unten, in derselben Sitzung: Niki wollte Insulin
doch noch in die Bibliothek aufnehmen, obwohl die vorherige Runde 4INS (Insulin
allein, ohne Rezeptor) dafür als ungeeignet verworfen hatte.

**4OGA gefunden und verifiziert** ("Insulin in complex with Site 1 of the
human insulin receptor", per echtem RCSB-Abruf bestätigt) — aber ein
komplizierterer Fall als Semaglutid: 6 Ketten (A=21, B=21 sichtbare Reste
[volle B-Kette hat 30, der Rest ist im Kristall ungeordnet — beim Andocken an
den Rezeptor löst sich das B-Ketten-Ende bekanntermaßen vom Insulin-Kern,
passt also zur echten Biologie], C=118, D=114, E=288, F=15/16). Insulin
besteht aus **zwei** Ketten (A+B, über 3 Disulfidbrücken verbunden) — die
bestehende "kürzeste-Kette"-Heuristik aus dem Eintrag unten kann das nicht
abbilden. Schlimmer: **Kette F (15 Reste) ist selbst kürzer als A oder B**
und gehört zum Rezeptor (das "α-CT-Peptid", ein rezeptor-eigenes Fragment,
das an der Bindungsstelle mitwirkt) — die Heuristik hätte also nicht nur
"nur eine Kette statt zwei" gewählt, sondern die **falsche** Kette.

**Lösung: `chain_ids` als dritte, explizite Auswahl-Möglichkeit in
`_find_ligand_lines()`** (`backend/docking.py`), geprüft VOR der Peptid-
Heuristik und dem HETATM-Fall. Übergibt man `chain_ids: ["A", "B"]`, werden
genau diese Ketten kombiniert und die Heuristik komplett übersprungen — kein
Rätselraten mehr nötig, wenn die Kettenzugehörigkeit ohnehin bekannt ist (wie
hier: aus der Biologie, nicht aus der Struktur allein ableitbar). Per
Diagnose-Skript vorab bestätigt, dass RDKits `ConnectTheDots`-Bindungs-
erkennung dabei alle **3 echten Insulin-Disulfidbrücken** (A6-A11, A7-B7,
A20-B19 — mit der Literatur abgeglichen) über die Kettengrenze hinweg
korrekt findet, rein aus dem 3D-Abstand der Schwefelatome. `hetero_code` und
`chain_ids` schließen sich gegenseitig aus (chain_ids hat Vorrang, falls
beide angegeben würden — kommt in der Praxis aber nicht vor, das Frontend
nutzt nur eins von beiden pro Bibliothek-Karte).

`POST /api/pdb-ligand` und `pdb_ligand()` haben dafür ein neues optionales
Feld/Argument `chain_ids` bekommen. Frontend: neue Karte "Insulin (an seinem
Rezeptor)" in der "Peptid-Wirkstoffe"-Kategorie (`frontend/app.js`,
`{pdbId: "4OGA", chainIds: ["A", "B"]}`), `loadPdbLigandIntoSlot()`/
`resolvePdbLigand()` geben `chainIds` einfach durch.

Backend-Tests ergänzt: expliziter Zwei-Ketten-Fall (prüft u.a. die 6
Schwefelatome), unbekannte Ketten-ID → 400.

**Getestet im Browser:** Klick auf "Insulin (an seinem Rezeptor)" lädt
sichtbar eine kompakte, verknäulte Kernstruktur mit einem längeren,
freihängenden Ende (genau die erwartete Form — kompakter A/B-Kern plus das
ungeordnete B-Ketten-Ende) statt einer einzelnen kurzen Kette. Fakten-Panel
zeigt Summenformel (`C207N51O63S6`, 6 Schwefel — stimmt mit den 3
Disulfidbrücken überein) und Molmasse korrekt, die übrigen fünf Felder als
"–". Hinweistext erklärt korrekt, dass eine feste Kettenauswahl statt der
Längen-Heuristik verwendet wurde. Keine Konsolenfehler.

## 2026-09-19 (autonomer Durchlauf, ~45 Min.): PDB-Liganden direkt anzeigen + Bibliothek-Bereich

Niki war ~30-60 Min. weg und hat zwei zusammenhängende Erweiterungen als fertige
Prompts vorgelegt: bei normalen Umsetzungsentscheidungen selbst entscheiden statt
zu warten, nur bei echten Sackgassen anhalten. Beide Teile sind fertig geworden.

**Teil 1 — `POST /api/pdb-ligand` (neu, `backend/docking.py` + `backend/app.py`):**
Lädt eine PDB-Struktur und zeigt den darin gefundenen Liganden als eigenständiges
Molekül, ganz ohne Docking-Rechnung — gleiches Antwortformat wie `/api/resolve`
(`atoms`/`bonds`/`facts`/`common_name`/`iupac_name`/`note`), damit das Frontend
nichts Neues dafür bauen musste.

- Bewusst **keine** ergänzten Wasserstoffe (anders als `chem._build_structure()`)
  — das wären erfundene H-Positionen auf einer real gemessenen Geometrie. Aus
  dem gleichen Grund auch keine RDKit-Deskriptoren (LogP/TPSA/H-Brücken/drehbare
  Bindungen) — die bräuchten korrekte Valenzen inkl. H. Diese fünf Fakten-Felder
  zeigen für PDB-Liganden ein `"–"`. Nur Summenformel und Molmasse werden direkt
  aus den vorhandenen (Schwer-)Atomen berechnet, per RDKits Periodensystem
  (`Chem.GetPeriodicTable()`) statt einer selbst gepflegten Atomgewichts-Tabelle.
- Bindungen kommen aus `Chem.MolFromPDBBlock(..., proximityBonding=True)` —
  RDKits eigene Abstands-Bindungserkennung (`ConnectTheDots`), unsanitisiert.
  Bindungsordnung ist damit geraten, nicht chemisch bewiesen — für die reine
  3D-Darstellung egal, weil der Viewer Bindungen ohnehin nur als Zylinder ohne
  Doppelbindungs-Unterscheidung zeichnet.
- **Zwei Liganden-Fälle, in dieser Reihenfolge geprüft** (`_find_ligand_lines()`):
  1. **Peptid-Ligand-Heuristik, bewusst VOR der Klein-Molekül-Suche geprüft:**
     gibt es eine Protein-Kette in Peptid-Wirkstoff-Länge (5-60 Reste) UND eine
     deutlich längere Kette (das vermutliche Zielprotein), wird die kürzeste
     solche Kette als Ligand behandelt. Musste vor dem HETATM-Fall kommen, weil
     4ZGM (siehe unten) zusätzlich ein für den Liganden irrelevantes HETATM-
     Molekül (`32M`, ein PEG-artiger Kristallisationszusatz, laut RCSB-Chemcomp-
     API "3,6,9,12,15,18-hexaoxahexacosan-1-ol") neben der Peptidkette hat — mit
     der ursprünglichen Reihenfolge (HETATM zuerst) wäre fälschlich das PEG-
     Molekül als "Ligand" gewählt worden. Per echtem RCSB-Abruf verifiziert:
     4ZGM hat Kette A (100 Reste, GLP-1-Rezeptor-ECD) und Kette B (28 Reste,
     Semaglutid) — B wird korrekt gewählt. 7KI0 (Kette P, 29 Reste, unter A/B/G/N/R
     mit 56-384 Resten) ebenso. Offen benannt in der zurückgegebenen `note`:
     reine Längen-Heuristik, keine chemische Bestätigung der Identität.
  2. **Klein-Molekül-HETATM** (wie schon beim Docking, `_find_reference_ligand`):
     die größte Nicht-Ignorierte HETATM-Gruppe, optional per `hetero_code`
     (PDB-Chemical-Component-ID, z. B. `"BEN"`) gezielt ausgewählt.
- **Insulin (4INS) zuerst geprüft, aber NICHT verwendet:** 4INS enthält nur
  die vier kurzen Insulin-Ketten (A/B/C/D, 21-30 Reste) ohne Rezeptor — die
  Peptid-Heuristik braucht eine deutlich längere Gegenkette, um zwischen
  "Ligand" und "Rezeptor" zu unterscheiden, die hier fehlt. Stattdessen
  **4OGA** ("Insulin in complex with Site 1 of the human insulin receptor")
  verwendet — siehe Folge-Eintrag unten, dort kam noch eine dritte
  Auswahl-Möglichkeit (`chain_ids`) dazu, die dieser erste Durchlauf noch
  nicht hatte.
- Backend-Tests ergänzt (`backend/tests/test_api.py`): Klein-Molekül-Fall
  (3PTB/Benzamidin), Peptid-Fallback (4ZGM/Semaglutid), ungültige PDB-ID.

**Teil 2 — Bibliothek-Bereich (`frontend/index.html`, `style.css`, `app.js`):**
Neue Sektion direkt unter dem Header, über dem Eingabefeld (als der zuerst
sichtbare, einfachste Einstieg für Chemie-Anfänger) — Kategorien mit
anklickbaren Karten, kein Fachjargon in der Auswahl selbst (Formel/SMILES
zeigt das Fakten-Panel nach dem Laden ohnehin automatisch).

- Kategorien wie vorgegeben (Alltagsstoffe, Schmerz & Fieber, Bausteine des
  Körpers, Vitamine, Süßes & Fette), plus zwei zusätzliche, die zum schon
  vorhandenen `CHEMSPACE_EXAMPLE_SET` passen: **Hormone** (Testosteron war
  schon im chemspace-Set; dazu Östrogen/Estradiol, Adrenalin/Epinephrin) und
  **Haushalt & Reinigung** (Essigsäure — auch Edukt der Veresterungs-Reaktion
  weiter unten —, Isopropanol als "Desinfektionsmittel").
- Eigene Kategorie **"Peptid-Wirkstoffe (aus echten 3D-Messungen)"** mit einer
  Karte "Ozempic / Semaglutid" (PDB `4ZGM`), die **nicht** `/api/resolve`
  aufruft, sondern den neuen `/api/pdb-ligand`-Endpunkt aus Teil 1 — visuell
  durch gestrichelte Kartenränder (`.library-category-peptide`) leicht von den
  übrigen, per Namen auflösbaren Karten abgesetzt, plus ein erklärender
  Hinweistext direkt unter dem Kategorietitel.
- Technisch: hartkodierte `LIBRARY_CATEGORIES`-Liste in `app.js` (gleiches
  Muster wie `CHEMSPACE_EXAMPLE_SET`), Karten dynamisch gerendert. Ein Klick
  ruft `loadIntoSlot()` bzw. (Peptid-Karte) das neue `loadPdbLigandIntoSlot()`
  auf — beide teilen sich jetzt eine gemeinsame `applyResolvedData()`-Funktion
  (kleiner Refactor von `loadIntoSlot()`, das vorher die Anzeige-Logik direkt
  enthielt), landen im Haupt-Viewer wie beim Chemischer-Raum-Klick, inkl.
  sanftem Scroll nach oben.

**Getestet im Browser** (`http://localhost:8001`, alle über die neuen
Bibliothek-Karten UND direkt per `/api/resolve`-Aufruf gegengeprüft): Aspirin
lädt korrekt aus der Bibliothek; Vitamin C löst zu "L-Ascorbic Acid" auf;
Vitamin D (`cholecalciferol`), Testosteron, Östrogen (`estradiol`), Adrenalin
(`epinephrine`), Essig (`acetic acid`), Desinfektionsmittel (`isopropanol`)
und Zucker (`sucrose`) lösen alle korrekt auf. **Ozempic/Semaglutid-Karte**
(der wichtigste Testfall): lädt die reale Semaglutid-Kette aus 4ZGM, zeigt
sichtbar eine lange, verzweigte Peptidkette (keine kompakte kleine
Molekülform), Fakten-Panel zeigt Summenformel/Molmasse korrekt und die
restlichen fünf Felder korrekt als "–", Hinweistext erklärt die
Peptid-Heuristik offen. Keine Konsolenfehler. Regressionscheck: normale
Auflösung ("water" über das Eingabefeld) danach nochmal geprüft, lief
einwandfrei.

**Nebenbei aufgetreten — ein neuer Cache-Fallstrick, dokumentiert statt
behoben (Browser-Verhalten, kein Code-Fehler):** Der allererste Ladeversuch
zeigte die neuen Bibliothek-Karten optisch falsch (helle Standard-Button-
Farben statt der dunklen `.library-card`-Gestaltung), obwohl `style.css` auf
der Platte längst korrekt war. Ursache gefunden: `backend/app.py`s
`StaticFiles`-Mount setzt keine `Cache-Control`-Header, und der Browser hatte
`style.css` von einer früheren Sitzung (vor dieser Änderung) noch im
HTTP-Cache und hat nicht neu validiert — selbst ein neuer Tab traf denselben
Cache. Ein `fetch(..., {cache: "no-store"})` bekam sofort die korrekte,
aktuelle Version. Für Niki relevant: **falls nach einer Frontend-Änderung an
`style.css`/`app.js` die Seite optisch/funktional noch alt aussieht, obwohl
der Server-Neustart nichts bringt (das ist ja ein reiner Static-File-Mount,
kein `--reload`-Ziel) — harter Neu-Laden im Browser (Strg+Shift+R) oder
Cache leeren, nicht am Code suchen.**

## 2026-09-19 (später): Ausbaustufe — Gleichungslöser, plus PubChem-Cache und Backend-Tests

Niki wollte eine 10. Ausbaustufe: eine frei eingetippte Reaktionsgleichung
(z. B. `CH4 + O2 -> CO2 + H2O`) automatisch ausgleichen lassen und gleich
als Morph-Animation zeigen, so wie die schon bestehende, handkuratierte
Reaktions-Animation. Dazu noch "die anderen Sachen" aus der letzten
Verbesserungsliste, soweit sinnvoll in einer Sitzung machbar.

**Neue Datei `backend/equation.py`.** Wichtiger Unterschied zu
`reactions.py`: dort ist die Atom-Zuordnung zwischen Edukt und Produkt von
Hand über Atom-Map-Nummern hinterlegt (100% korrekt, aber nur für die paar
vorbereiteten Beispiele). Bei einer frei eingetippten Gleichung gibt es
diese Handarbeit nicht -- welches Atom zu welchem wird, ist ein eigenes,
in der echten Cheminformatik ungelöstes Problem (reaction atom mapping,
normalerweise per ML-Modell angenähert, z. B. RXNMapper). Deshalb zwei
getrennte, unterschiedlich sichere Teile:

1. **Stöchiometrie-Ausgleich: exakt, kein Kompromiss.** Für jeden Stoff
   werden per RDKit die Elementzahlen gezählt, daraus eine Matrix gebaut
   (Edukte positiv, Produkte negativ) und deren Nullraum per Gauß-Jordan
   **über exakte Brüche** (`fractions.Fraction`, keine Gleitkomma-
   Rundungsfehler) berechnet, dann auf die kleinsten positiven Ganzzahlen
   skaliert. Klare Fehler statt stillem Rateversuch, wenn: kein Nullraum
   existiert (Elemente passen nicht zusammen), der Nullraum mehr als 1-
   dimensional ist (z. B. `C + O2 -> CO + CO2` -- durch Atomerhaltung
   allein nicht eindeutig lösbar), oder gemischte Vorzeichen nötig wären
   (Stoff steht auf der falschen Seite). Getestet: `CH4 + O2 -> CO2 + H2O`
   → `CH4 + 2 O2 -> CO2 + 2 H2O`, `H2 + O2 -> H2O` → `2 H2 + O2 -> 2 H2O`,
   `N2 + H2 -> NH3` → `N2 + 3 H2 -> 2 NH3` -- alle drei von Hand
   nachgerechnet korrekt.
2. **Atom-Zuordnung fürs Morphen: bewusst nur eine Näherung, offen
   benannt.** `_match_atoms()` löst pro Element ein Zuordnungsproblem
   (`scipy.optimize.linear_sum_assignment`, Ungarische Methode) nach
   räumlichem Abstand zwischen den unabhängig eingebetteten Start- und
   End-Layouts. Kein Versuch, echte Bindungsumlagerung nachzuvollziehen --
   für einfache Lehrbuch-Gleichungen (Verbrennung, Synthese) sieht das
   trotzdem chemisch sinnvoll aus (im Browser geprüft: `N2 + H2 -> NH3`
   morpht sauber zu zwei getrennten NH3-Klumpen, keine Atome springen
   chaotisch durcheinander), ist aber nicht chemisch bewiesen wie bei den
   handgemappten Beispielen oben. Gleiche "ehrliche Vereinfachung"-Linie
   wie bei der Formel-Heuristik, dem Docking und der MD -- im Frontend
   auch so als Hinweistext angezeigt, nicht versteckt.

**Datenformat bewusst identisch zu `reactions.build_reaction()`**
(`start`/`end`/`correspondence`/`persistent_bonds`/`broken_bonds`/
`formed_bonds`) -- dadurch war an `frontend/viewer.js` (`playReaction()`)
**keine einzige Zeile** zu ändern, nur `app.js` bekam eine neue, zum
bestehenden Muster passende Sektion (Eingabefeld, "Beispiel laden",
"Lösen & animieren", eigener Viewer). Ein bewusster Unterschied zu
`reactions.py`: dort werden Wasserstoffe nicht animiert (Skelett-Stil),
hier **schon** -- sonst wären viele der interessantesten Alltagsgleichungen
(Verbrennung, Ammoniak-Synthese, Neutralisation) fast leer, weil sie fast
nur aus Wasserstoff bestehen.

**Route:** `POST /api/equation {equation: str}` in `app.py`.

**PubChem-Caching ergänzt** (`chem.py`, `_name_cache`/`_smiles_cache`/
`_formula_cache`, einfache In-Memory-Dicts) -- war schon länger als
Verbesserungsidee notiert (siehe unten) und wurde jetzt gebraucht, weil
der Gleichungslöser pro Anfrage mehrere PubChem-Lookups auf einmal macht.
Bewusst kein Disk-Cache wie bei `pdb_cache/`: eine rohe Nutzereingabe als
Dateiname zu verwenden bräuchte erst eine Sanitisierung, ein In-Memory-
Dict ist für die Prozesslaufzeit genauso wirksam und hat dieses Problem
gar nicht erst.

**Backend-Tests ergänzt** (`backend/tests/`, `pytest` + FastAPI
`TestClient`, neue `backend/requirements-dev.txt`). Bewusst **keine**
Mocks -- die Tests rufen echte PubChem-/RCSB-/Vina-Aufrufe auf, genau wie
die App selbst, damit sie auch reale API-Änderungen auffangen (wie die
schon einmal erlebte PubChem-Feldumbenennung, siehe Fallstrick 2 weiter
unten). 11 Tests, alle grün: `/api/resolve` (Name, direktes SMILES,
Formel, unbekannte Eingabe), `/api/equation` (Verbrennung ausgeglichen,
fehlender Pfeil, unlösbare Gleichung), `/api/reactions`, `/api/dock`
(3PTB+Benzamidin wie von Niki vorgeschlagen, plus zwei Fehlerfälle).
Einzige Anpassung unterwegs: ein Test verließ sich darauf, dass PubChems
Formel-Mehrdeutigkeit für `C6H12O6` immer eine Notiz auslöst -- das ist
aber ein von PubChems aktuellem Datenbestand abhängiges Verhalten, kein
stabiler Vertrag, deshalb abgeschwächt auf "Formel wird korrekt aufgelöst".

**Nicht umgesetzt aus der letzten Ideen-Liste, bewusst zurückgestellt:**
Ladungszustände beim Docking (pKa-Vorhersage ist ein eigenes, nicht
triviales Teilproblem), SHAKE/RATTLE bei der MD (würde den Integrator
deutlich umbauen), Export/Screenshot-Funktion, Deployment auf
Render/Fly.io (braucht eigenen Account, Linux-Vina-Build). Alle vier
bleiben unten in der Ideen-Liste stehen.

**Getestet im Browser:** `CH4 + O2 -> CO2 + H2O` geladen und gelöst --
Label zeigt korrekt "Methane + 2 Oxygen → Carbon Dioxide + 2 Water",
Animation läuft sichtbar (CH4+2 O2 morphen zu CO2+2 H2O). Danach
`N2 + H2 -> NH3` von Hand eingetippt -- Label "Nitrogen + 3 Hydrogen →
2 Ammonia", Animation zeigt N2 + 3×H2 sauber zu 2× NH3 morphend. Keine
Konsolenfehler in beiden Fällen. Regressionscheck: normale Auflösung
("water") danach nochmal geprüft, lief einwandfrei.

## 2026-09-19: Fallstricke überprüft, ein echter Sicherheitsfund behoben, auf GitHub veröffentlicht

Niki hat gebeten, die dokumentierten Fallstricke/Verbesserungsideen nochmal
zu prüfen, selbst weiterzudenken, und das Projekt auf GitHub anzulegen.

**Fallstricke erneut geprüft — beide weiterhin gültig, keine akute
Blockade:** Aktuell hängt kein alter Uvicorn-Prozess auf Port 8001
(`netstat` leer). Der `--reload`-Fallstrick ist nicht reproduzierbar
prüfbar (trat unregelmäßig auf), bleibt aber als Hinweis stehen. Der
`ANTHROPIC_API_KEY`-Gap ist weiterhin offen (`backend/.env` existiert
noch nicht) — Ausbaustufe 5 wartet weiter auf Nikis eigenen Key.

**Beim Selbst-Nachdenken einen echten, bisher nicht dokumentierten Fund
gemacht: Path-Traversal über `pdb_id`.** `docking.fetch_pdb()` hat die
Nutzereingabe nur `.strip().upper()`t und dann ungeprüft in einen
Dateipfad eingesetzt (`PDB_CACHE_DIR / f"{pdb_id}.pdb"`). Eine PDB-ID wie
`../../irgendwas` hätte das Ergebnis der RCSB-Anfrage an eine beliebige
Stelle außerhalb von `pdb_cache/` schreiben können — bei einem Projekt,
das gerade öffentlich wird, ein echtes Risiko, nicht nur ein
Lehrbuch-Fall. **Behoben:** `_PDB_ID_RE = re.compile(r"^[0-9][A-Z0-9]{3}$")`
validiert jetzt gegen das echte PDB-ID-Format (4 Zeichen, erste Ziffer),
bevor irgendein Pfad gebaut wird — echte IDs wie `3PTB`/`1UBQ` bleiben
gültig, `../..`-artige Eingaben werden klar abgelehnt (per Testskript
gegengeprüft).

**Zwei weitere kleine Lücken schließen, bevor der Code öffentlich wird:**
- `backend/requirements.txt` ergänzt (`fastapi`, `uvicorn`, `rdkit`,
  `requests`, `anthropic`, `python-dotenv`, `numpy`, `meeko`, `scipy`,
  `gemmi`) — vorher stand die Paketliste nur als Freitext hier in
  `stand.md`, nicht als installierbare Datei.
- `README.md` im Projekt-Wurzelverzeichnis ergänzt — kurzer
  öffentlicher Überblick (Funktionen, Setup, bekannte Einschränkungen)
  für GitHub-Besucher, getrennt von `CLAUDE.md`/`docs/stand.md`, die
  für Claude-Sessions gedacht sind.

**Weitere Verbesserungsideen geprüft, aber (noch) nicht umgesetzt —
bewusst nur dokumentiert, um den Commit fokussiert zu halten:**
- PubChem-Caching (bestätigt: `chem.py` hat aktuell kein Retry/Cache,
  jede Anfrage geht neu raus) — sinnvoller nächster Schritt für
  gefühlte Geschwindigkeit.
- Ladungszustände des Liganden vor dem Docken (siehe bestehende
  Einschränkung weiter unten) — nicht trivial (pKa-Vorhersage), bleibt
  offen.
- SHAKE/RATTLE-Constraints bei der MD (siehe bestehende Einschränkung
  weiter unten) — würde den Integrator deutlich komplexer machen.
- Export/Screenshot-Funktion, Backend-Tests (`pytest` gegen
  `/api/resolve`, `/api/dock`), Deployment-Option — alles sinnvoll,
  aber jeweils eigene kleine Ausbaustufen, kein Ein-Zeiler.

**GitHub-Repo angelegt und gepusht:**
[github.com/nikiweikhart/molecule-viewer](https://github.com/nikiweikhart/molecule-viewer)
(öffentlich, auf Nikis Wunsch — Portfolio-tauglich für die VWA). `gh`
CLI war nicht installiert, deshalb Repo-Erstellung über den Chrome-
Browser (Nikis eingeloggte GitHub-Session) gemacht, Push lief über den
schon konfigurierten Git Credential Manager ohne weiteren Login-Schritt.
Branch heißt `main` (vorher `master`, umbenannt vor dem Push).

## 2026-09-15 (Abend): Ausbaustufe — Molekulardynamik-Simulation

Letzte der drei "richtig aufwendigen", API-freien Folge-Ausbaustufen
(nach chemischem Raum und Protein-Docking). Bauplan lag in
`C:\Users\nikiw\.claude\plans\ethereal-dancing-corbato.md`.

**Ergebnis: fertig und im Browser getestet.** Man gibt ein Molekül ein
(Name/Formel/SMILES, gleiches Format wie überall), klickt "Simulieren",
und sieht das Molekül — inklusive Wasserstoffe, bewusst nicht ausgeblendet
diesmal — kontinuierlich unter echter thermischer Bewegung wackeln
(Ping-Pong-Loop, kein Sprung beim Wiederholen).

**Bewusste Kursänderung gegenüber der ursprünglichen Idee "via OpenMM":**
OpenMM selbst hat saubere Windows-Wheels, aber um aus einem **beliebigen**
SMILES automatisch Kraftfeld-Parameter zu erzeugen, bräuchte es zusätzlich
`openmmforcefields` + `openff-toolkit`, und die hängen an `AmberTools` —
offiziell nur auf macOS/Linux getestet, nicht zuverlässig per pip unter
Windows installierbar. Gleiches Muster wie bei AutoDock Vina, nur diesmal
ohne die einfache "eine `.exe` laden"-Abkürzung, weil es ein verschachtelter
Python-Abhängigkeitsbaum ist. **Deshalb: kein OpenMM.** Stattdessen
RDKits MMFF94-Kraftfeld (schon seit dem allerersten Baustein im Einsatz,
`chem.py`) direkt für einen selbstgeschriebenen Velocity-Verlet-Integrator
genutzt — `ForceField.CalcGrad()` liefert echte Kraftfeld-Gradienten,
genug für eine echte numerische Lösung von Newtons Bewegungsgleichungen.
**Bringt exakt null neue Abhängigkeiten** (nur RDKit + numpy, beide schon
da) — diese Ausbaustufe ist damit sogar "kostenloser" als die anderen
beiden API-freien Stufen.

**Architektur (`backend/dynamics.py`, neue Datei):**
- Ligand über `chem._resolve_to_names()` auflösen, RDKit-Mol mit `AddHs`
  + `EmbedMolecule` + `MMFFOptimizeMolecule` aufbauen (gleiches Muster wie
  in `chem.py` und `docking.py`).
- `AllChem.MMFFGetMoleculeForceField` + `ff.Initialize()`, dann eine
  Velocity-Verlet-Schleife: `ff.CalcGrad(positions)` pro Schritt (explizite
  Positionsübergabe, kein Verlass auf implizite Mutation — per Diagnose-
  Skript bestätigt: Gradient an der schon MMFF-optimierten Startgeometrie
  ist praktisch null, API funktioniert wie erwartet).
- Start-Geschwindigkeiten aus einer Maxwell-Boltzmann-Verteilung bei
  300 K, Einheiten-System Å/Femtosekunden/amu/kcal-mol mit sauber aus
  SI-Einheiten hergeleiteter Umrechnungskonstante (`ACC_CONST = 4.184e-4`).

**Ein echtes Stabilitätsproblem unterwegs, ausführlich per Testskripten
diagnostiziert (nicht nur geraten):**
1. Erster Versuch (`dt=0.5 fs`, wie in Lehrbüchern für Standard-MD oft
   genannt) explodierte nach wenigen Dutzend Schritten zu `NaN`.
2. Kleinere Schrittweite allein hat das Problem nur verschoben, nicht
   gelöst: `dt=0.2 fs` blieb ~250 Schritte "sauber" (Energie driftet nur
   langsam), `dt=0.1 fs` ~450, `dt=0.05 fs` ~450-500 — dann explodierte
   jede der drei irgendwann trotzdem. Auch der reine Integrator **ohne**
   Thermostat driftete schon leicht (bestätigt per Diagnose ohne
   Thermostat) — die Lehrbuch-Schrittweiten (0.5-1 fs) setzen implizit
   Bindungslängen-Constraints (SHAKE/RATTLE) voraus, die die schnellen
   X-H-Streckschwingungen einfrieren; ohne die ist ein einfacher
   Integrator bei diesen Schrittweiten grundsätzlich nicht stabil.
3. **Was tatsächlich geholfen hat: Force-Capping** (`_ACCEL_CAP` in
   `dynamics.py`) — einzelne Beschleunigungs-Spitzen (entstehen, wenn zwei
   Atome sich in einem Integrationsschritt zu nah kommen und MMFFs steile
   Terme dann eine riesige Kraft liefern) werden der Richtung nach
   erhalten, aber der Höhe nach gekappt. Damit über 2000 Testschritte
   stabil (keine `NaN` mehr), auch bei Caffein (24 Atome, mehrere Ringe)
   gegengeprüft. Pendelt sich dabei auf ein etwas höheres Energieniveau
   ein als das nominelle 300-K-Ziel (~15-16 statt ~8 kcal/mol bei Ethanol)
   — für eine visuelle Demo (sichtbares, stabiles Wackeln) ausreichend,
   aber **keine quantitativ exakte NVT-Simulation**. Offen benannt im
   Modul-Docstring von `dynamics.py`, gleiche "ehrliche Vereinfachung"-
   Linie wie bei der Formel-Heuristik in `chem.py` oder den Docking-
   Bindungsenergien.
- Finale Werte: `dt=0.1 fs`, `n_steps=800` (80 fs simuliert),
  Geschwindigkeits-Rescaling-Thermostat jeden Schritt (sanft geklemmt,
  0.97-1.03), Frames alle 3 Schritte aufgezeichnet (~268 Frames).
  Rechenzeit pro Anfrage: ~1 Sekunde für ein ~20-30-Atom-Molekül.

**Frontend:**
- `frontend/viewer.js`: neue Methode `playTrajectory(data)` — baut Kugeln
  + Zylinder einmalig aus Frame 0 (gleiches Baumuster wie `playReaction`),
  spielt die Frame-Liste per `requestAnimationFrame` in einer
  **Ping-Pong-Schleife** ab (vorwärts bis zum letzten Frame, dann
  rückwärts, dann wieder vorwärts) statt hart zu Frame 0 zurückzuspringen
  — keine sichtbare Ruckel-Stelle beim Loopen. Kamera wird einmalig auf
  Frame 0 (+ Puffer) gefittet, da thermische Bewegung nur eine kleine
  Auslenkung um die Ausgangslage ist. Wasserstoffe werden diesmal bewusst
  **gezeigt** (Gegensatz zur Reaktions-Animation) — die schnelle
  X-H-Wackelbewegung ist genau das, was "vibriert wirklich" visuell zeigt.
  Neuer `clearTrajectory()`-Aufräummechanismus, ins bestehende
  `clearReaction()`/`clearDocking()`-Muster eingehängt.
- `frontend/index.html` + `app.js`: neuer Bereich "Molekulardynamik" —
  Eingabefeld, "Beispiel laden" (füllt `caffeine`), "Simulieren"-Button,
  Info-Zeile (Temperatur, simulierte Zeit, Atomzahl). Keine neuen
  CSS-Klassen nötig — bestehende `.docking-controls`/`.chemspace-info`
  wiederverwendet.

**Getestet im Browser:** Caffein simuliert — sichtbare, kontinuierliche
Wackelbewegung (Positionsvergleich zwischen zwei Screenshots im
Sekundenabstand bestätigt echte Bewegung), Molekül bleibt auch nach
mehreren Sekunden Dauerlauf kompakt und erkennbar (keine Explosion, keine
sichtbaren Sprünge). Keine Konsolenfehler. Regressionscheck der normalen
Molekülanzeige (`water`) danach — lief einwandfrei, der Eingriff in die
gemeinsame Aufräum-Logik (`clearTrajectory()` in `rebuild()`/
`playReaction()`/`setDockingResult()`) hat nichts kaputt gemacht.

**Damit sind alle 3 der "richtig aufwendigen", API-freien Folge-
Ausbaustufen fertig: Chemischer Raum ✅, Protein-Docking ✅,
Molekulardynamik ✅.** Alle drei bringen zusammen genau eine neue externe
Binary (`vina.exe`) und eine Handvoll pip-Pakete (`meeko`, `scipy`,
`gemmi`) mit — die Molekulardynamik-Stufe selbst kam am Ende ganz ohne
neue Abhängigkeit aus.

## 2026-09-15 (autonomer Durchlauf, ~1 Std.): Ausbaustufe — Protein-Docking

Niki wollte Tennis spielen gehen und hat gesagt: alles bauen, was schon
besprochen war (Protein-Docking), bei Fragen selbst entscheiden statt zu
warten, und gern noch selbst draufgepackte Ideen einbauen. Bauplan lag in
`C:\Users\nikiw\.claude\plans\ethereal-dancing-corbato.md` (Protein-Docking-
Version — der chemische Raum davor hat den gleichen Dateinamen benutzt,
Plan-Dateien werden pro Session wiederverwendet, nicht pro Ausbaustufe).

**Ergebnis: fertig und im Browser getestet, funktioniert end-to-end.**
Man gibt eine PDB-ID (z. B. `3PTB`) und einen Liganden (Name/Formel/SMILES,
z. B. `benzamidine`) ein, klickt "Docken", und sieht nach ein paar Sekunden
das Protein-Rückgrat als Röhre mit dem angedockten Molekül in der
Bindetasche, dazu Proteinname und die drei besten Bindungsenergien.

**Neue externe Werkzeuge (einmalig, mit Nikis vorherigem Okay
heruntergeladen bzw. installiert):**
- `backend/tools/vina.exe` — offizielle AutoDock-Vina-1.2.7-Windows-Binary
  von `github.com/ccsb-scripps/AutoDock-Vina/releases` (1.233.920 Bytes,
  Prüfsumme beim Download bestätigt). Grund: die Python-Bindings von Vina
  haben kein funktionierendes Windows-Paket (`pip install vina` schlägt
  auf Windows an fehlenden Build-Abhängigkeiten wie Boost fehl — bekanntes,
  offenes Problem, siehe
  [GitHub-Issue #305](https://github.com/ccsb-scripps/AutoDock-Vina/issues/305)).
  Die `.exe` ist eigenständig, kein Installer, keine Systemänderung.
- `meeko` (0.8.0), `scipy`, `gemmi` in der venv installiert — `meeko`
  bereitet sowohl Rezeptor (Protein) als auch Liganden für Vina vor
  (`mk_prepare_receptor.exe`, `mk_prepare_ligand.exe`, `mk_export.exe`,
  alle als Kommandozeilen-Skripte in `.venv/Scripts/` installiert). `scipy`
  und `gemmi` waren nicht in `meekos` PyPI-Metadaten als Abhängigkeiten
  gelistet, wurden aber beim ersten Ausführen als fehlend gemeldet und
  nachinstalliert — beim Neuaufsetzen der venv einfach mit einplanen.

**Architektur (`backend/docking.py`, neue Datei):**
1. `fetch_pdb()` lädt die Struktur von `files.rcsb.org` (frei, kein Key,
   wie PubChem) und cached sie unter `backend/pdb_cache/{ID}.pdb`, plus den
   Proteinnamen von `data.rcsb.org`s REST-API.
2. `_find_reference_ligand()` durchsucht die `HETATM`-Zeilen der PDB-Datei,
   filtert eine Denyliste aus Wasser/Ionen/Kristallisationshilfsstoffen
   (`HOH`, `SO4`, `GOL`, `NAG`, …), nimmt die größte verbleibende Gruppe
   als Referenz-Ligand und berechnet deren Bounding-Box (+5 Å Puffer,
   mindestens 15 Å pro Achse) als Such-Box für Vina. **Kein blindes
   Docking** — PDB-Einträge ohne brauchbaren Liganden (reine Apo-
   Strukturen, z. B. `1UBQ` getestet) geben eine klare Fehlermeldung statt
   eines langsamen, ungenauen Rateversuchs über die ganze Oberfläche.
3. `prepare_receptor()` ruft `mk_prepare_receptor.exe --read_pdb …
   --delete_bad_res` auf — das `-x/--delete_bad_res`-Flag entfernt
   automatisch jeden Rest ohne bekanntes Chemie-Template (den
   Referenz-Liganden selbst, Kristallwasser, exotische Kofaktoren), ohne
   dass man Resten einzeln von Hand angeben muss.
4. Der Ligand wird über das schon vorhandene `chem._resolve_to_names()`
   aufgelöst, lokal mit RDKit 3D eingebettet (gleiches Muster wie in
   `chem.py`), als SDF geschrieben und über `mk_prepare_ligand.exe` zu
   PDBQT vorbereitet.
5. `run_vina()` ruft `vina.exe` mit Rezeptor/Ligand/Box auf, liest die
   Bindungsenergien direkt aus Vinas eigener Konsolenausgabe (per Regex).
6. `mk_export.exe` konvertiert Vinas Ausgabe-PDBQT zurück zu SDF (mit
   sauber rekonstruierten Bindungen statt sie selbst aus Distanzen zu
   raten), RDKit liest daraus die beste Pose als Atome/Bindungen im
   gleichen Format wie überall sonst in der App.
7. Alle Schritte werfen eine sprechende `DockingError` bei Fehlschlag —
   gleiches Muster wie `ResolveError`.

**Frontend:**
- `frontend/viewer.js`: neue Methode `setDockingResult(data)` auf dem
  `createViewer()`-Objekt. Protein-Rückgrat als glatte Röhre
  (`THREE.CatmullRomCurve3` + `TubeGeometry` durch die Cα-Positionen pro
  Kette, gedämpfter Warmton `#7a6a52`, matt statt glänzend, damit es den
  Liganden nicht optisch erschlägt). Ligand ganz normal per
  `buildMolecule()` (Wiederverwendung, keine neue Kugel-Stab-Logik nötig).
  **Zusatz, spontan noch ergänzt:** eine halbtransparente
  Drahtgitter-Box (`THREE.BoxGeometry` + `EdgesGeometry`) um die
  Such-Box herum — macht sichtbar, wo Vina eigentlich gesucht hat, statt
  dass die Bindetasche nur implizit aus der Ligand-Position erschlossen
  werden muss.
- `frontend/index.html` + `app.js` + `style.css`: neuer Bereich —
  PDB-ID-Feld, Liganden-Feld, "Beispiel laden" (füllt `3PTB` +
  `benzamidine`), "Docken"-Button mit "wird berechnet …"-Anzeige während
  der Anfrage (Rezeptor-Vorbereitung + Docking-Suche dauert ein paar
  Sekunden bis niedrige Minuten, je nach PDB-Größe).

**Getestet im Browser:**
- `3PTB` + `benzamidine` (das vereinbarte Lehrbeispiel — Trypsin,
  1 Kette/223 Reste, Referenz-Ligand korrekt als `BEN` erkannt): Protein-
  Röhre + Ligand + Such-Box sichtbar, Ligand liegt beim Drehen erkennbar
  *zwischen* den Schleifen (nicht nur davor) — also wirklich in der
  Tasche. Bindungsenergien um die −4 kcal/mol.
- Fehlerfall 1: ungültige PDB-ID (`ZZZZ`) → klare Meldung "wurde bei RCSB
  nicht gefunden" statt Absturz.
- Fehlerfall 2: PDB-ID ohne brauchbaren Liganden (`1UBQ`, Ubiquitin, reine
  Apo-Struktur) → klare Meldung statt stillem Blind-Docking-Versuch.
- Keine Konsolenfehler bei keinem der drei Fälle.

**Bekannte Einschränkung, offen benannt (wie bei der Formel-Heuristik in
`chem.py`):** Die Bindungsenergie für Trypsin+Benzamidin liegt bei den
Testläufen bei etwa −4 kcal/mol; Literaturwerte für diese sehr bekannte,
gut untersuchte Bindung deuten (über ΔG=−RT·ln(Ka) aus dem bekannten
Ki im niedrigen µM-Bereich) eher auf ungefähr −6 bis −7 kcal/mol hin. Vina
selbst ist ohnehin nur eine Scoring-Funktions-Näherung, keine exakte
Berechnung — zusätzlich benutzt diese Ausbaustufe die **neutrale**
Benzamidin-Form aus der PubChem/RDKit-SMILES-Auflösung, während die reale
Bindung über die protonierte Amidinium-Form (positiv geladen) läuft, die
eine Salzbrücke mit Asp189 im Protein eingeht — das fehlt hier und drückt
den berechneten Wert nach oben (schwächer). Richtige Ladungszustände vor
dem Docken zu bestimmen ist ein eigenes, nicht triviales Teilproblem
(pKa-Vorhersage) und bewusst nicht Teil dieser Ausbaustufe. Die Werte sind
also eher "richtige Größenordnung, richtiges Vorzeichen, richtige
Bindestelle" als exakt — für eine Lern-/Demo-Ausbaustufe die richtige
Erwartungshaltung, genau wie beim Kugel-Stab- statt Sekundärstruktur-
Protein-Rückgrat.

**Nebenbei aufgetreten:** Nach einer Backend-Änderung zeigte
`--reload` das erwartete "Reloading..."-Log, aber die geänderte Funktion
lieferte trotzdem noch die alte Antwort — half nur ein harter Neustart
(`taskkill` + `__pycache__` löschen + neu starten). Vermutlich eine
Eigenheit des Datei-Watchers auf dem OneDrive-synchronisierten
Projektordner (Sync-Verzögerung beim Melden der geänderten mtime). Falls
das nochmal passiert: nicht auf `--reload` verlassen, hart neu starten.

**Stand der 3 API-freien Folge-Ausbaustufen:** Chemischer Raum ✅, Protein-
Docking ✅ (dieser Eintrag), Molekulardynamik (OpenMM) offen — der letzte
der drei ursprünglich besprochenen "richtig aufwendigen" nächsten Schritte.

## 2026-09-15 (später): Ausbaustufe — Chemischer Raum / Ähnlichkeits-Explorer

Nach den 6 ursprünglich vereinbarten Ausbaustufen wollte Niki eine der drei
"richtig aufwendigen" Folge-Ideen bauen, die komplett ohne bezahlte API
laufen (siehe Gedächtnis `project_molecule_viewer.md` für die anderen
zwei — Protein-Docking und Molekulardynamik, noch offen). Gewählt: viele
Moleküle auf einmal eingeben, nach struktureller Ähnlichkeit auf einer 2D-
Karte anordnen und gruppieren. Bauplan lag in
`C:\Users\nikiw\.claude\plans\ethereal-dancing-corbato.md`.

**Keine neue Abhängigkeit installiert** — `numpy` war schon als RDKit-
Abhängigkeit in der venv vorhanden, PCA und k-Means sind selbst mit numpy
geschrieben statt `scikit-learn` zu installieren (bei den kleinen
Molekül-Mengen, um die es hier geht, robuster als t-SNE/UMAP und hält die
venv schlank).

**Backend:**
- `backend/chem.py` — kleiner, nicht brechender Refactor: `_compute_facts(mol)`
  aus `_build_structure()` herausgezogen (reine Funktionstrennung, mit
  `python chem.py` gegen den alten Output geprüft — identisch). Existiert
  jetzt separat, weil der chemische Raum nur die schnellen Fakten braucht,
  kein 3D-Embedding pro Molekül (das wäre bei Dutzenden Molekülen zu
  langsam).
- Neue Datei `backend/chemspace.py`: `build_chemical_space(queries)` löst
  jede Zeile über `chem._resolve_to_names()` auf (gleiche Logik wie die
  Haupt-Suche), berechnet pro Molekül einen Morgan-Fingerprint
  (`rdFingerprintGenerator.GetMorganGenerator`, radius=2, 1024 Bit),
  reduziert die Fingerprint-Matrix per selbstgeschriebener PCA
  (Zentrieren + `np.linalg.svd`) auf 2D, und gruppiert die 2D-Punkte per
  selbstgeschriebenem k-Means (deterministisch initialisiert — Punkte nach
  1. Hauptkomponente sortiert, k gleichmäßig verteilte Startzentren, keine
  Zufallszahlen). `k` heuristisch aus der Molekülzahl:
  `min(6, max(2, n // 3))`, bei <4 Molekülen nur 1 Cluster. Fehlschläge
  (nicht auflösbare Zeilen) werden gesammelt statt den ganzen Request
  abzubrechen. Eigener `if __name__ == "__main__":`-Testblock mit einem
  18-Molekül-Beispiel-Set — Cluster-Verteilung per `python chemspace.py`
  geprüft: Steroide (Cholesterol/Testosteron) und Zucker
  (Glucose/Fructose/Sucrose) bilden erwartungsgemäß saubere eigene
  Cluster; ein paar Aminosäuren landeten überraschend im
  Schmerzmittel-Cluster (Fingerprints gruppieren nach Struktur, nicht nach
  Pharmakologie — z. B. wegen des aromatischen Rings bei Phenylalanin —
  chemisch nachvollziehbar, keine Fehlfunktion).
- `backend/app.py`: neue Route `POST /api/chemical-space`.

**Frontend:**
- `frontend/index.html`: neuer Bereich unter der Reaktions-Animation —
  Textarea (ein Molekül pro Zeile), "Beispiel-Set laden"- und "Karte
  erzeugen"-Button, `<canvas>` in einem wiederverwendeten `.viewer-frame`,
  Info-Zeile für Hover/Auswahl.
- Neue Datei `frontend/chemspace.js`: `createChemSpacePlot(canvas)`, ein
  selbstgebautes Canvas-2D-Scatterplot (keine Chart-Bibliothek von einem
  CDN — passt zur bestehenden "kein Build-Schritt, minimale
  Abhängigkeiten"-Linie). Normalisiert PCA-Koordinaten auf Canvas-Pixel,
  zeichnet Punkte farbig nach Cluster (Farbpalette bewusst aus den
  Element-Farben in `viewer.js` übernommen statt neu erfunden), Hover
  vergrößert den nächstgelegenen Punkt und feuert einen Callback, Klick
  ebenso.
- `frontend/app.js`: hartkodiertes 18-Molekül-Beispiel-Set (5 Klassen:
  Schmerzmittel, Zucker, Alkohole, Aminosäuren, Steroide), Fetch-Aufruf an
  `/api/chemical-space`, Hover zeigt Name+Fakten im Info-Feld. **Klick auf
  einen Punkt lädt die 3D-Struktur direkt in den bestehenden
  Haupt-Viewer** — ruft dafür die schon vorhandene `loadIntoSlot(0, …)`
  mit dem vom Backend gelieferten SMILES auf (keine zweite, separate
  3D-Anzeige gebaut) und scrollt sanft nach oben.

**Getestet im Browser:** Beispiel-Set geladen, Karte erzeugt — 5 farblich
klar getrennte Gruppen sichtbar (Screenshot geprüft). Hover auf einen
Punkt vergrößert ihn und zeigt Name/Formel/Molmasse/LogP im Info-Feld.
Klick auf Cholesterol hat die 3D-Struktur oben im Haupt-Viewer geladen und
dorthin gescrollt — funktioniert einwandfrei. Fehlerfall geprüft: nur 1
Zeile im Textfeld → klare Fehlermeldung "Mindestens 2 Moleküle nötig …"
statt Absturz. Keine Konsolenfehler.

**Kleine, beiläufig aufgefallene Beobachtung (kein Bug, nur Notiz):** Wenn
man einen Punkt anklickt, kann der angezeigte Name leicht vom Namen in der
Chemischer-Raum-Liste abweichen (z. B. "Cholesterol" in der Eingabe →
"Cholest-5-en-3-ol" im Haupt-Viewer). Grund: der Klick lädt über den
SMILES-Code nach (`_pubchem_lookup_by_smiles`), und PubChems "Title"-Feld
ist für die SMILES-Rückwärtssuche manchmal ein anderes registriertes
Synonym als bei der Namens-Suche — chemisch identische Struktur, nur eine
andere von mehreren gültigen Bezeichnungen. Kein Fehlverhalten, nur eine
PubChem-Eigenheit.

**Nebenbei aufgetreten — der bekannte Server-Fallstrick war wieder da:**
Der alte Uvicorn-Prozess von der letzten Sitzung hing noch auf Port 8001
(`netstat` zeigte zwei "ABHÖREN"-Einträge gleichzeitig), dadurch gingen
manche Requests an die alte Prozess-Instanz ohne die neue Route (405
Method Not Allowed, obwohl die Route im Code längst da war). Gelöst mit
`taskkill /F /PID <pid> /T` auf die alte PID statt nur `pkill` — `pkill -f
"uvicorn app:app"` allein reicht offenbar nicht zuverlässig, um den
Reloader-Elternprozess mitsamt Kindprozess zu beenden.

## 2026-09-15: Ausbaustufe 6 fertiggebaut — Reaktions-Animation läuft

Frontend-Teil ergänzt (Backend stand schon vom Vortag):
- `frontend/index.html` — neuer Bereich unter den Karten: `<select
  id="reaction-select">` (per JS aus `/api/reactions` befüllt), Button
  "▶ Ablaufen lassen", eigener `.viewer-frame`-Block (`#reaction-viewer`).
- `frontend/viewer.js` — `createViewer()` gibt jetzt zusätzlich
  `playReaction(data, durationMs=3000)` zurück. Baut eine Kugel pro
  Start-Atom plus Zylinder für `persistent_bonds`/`broken_bonds`/
  `formed_bonds`, interpoliert Positionen über `correspondence` mit
  Ease-in-out (`requestAnimationFrame`-Loop, 3s), blendet `broken_bonds` in
  der ersten Hälfte aus und `formed_bonds` in der zweiten Hälfte ein.
  Kamera wird einmalig auf die Vereinigung aus Start- und End-Positionen
  gefittet (kein Nachjustieren während der Animation nötig). Die
  Kamera-Fit-Logik wurde dafür aus `fitCameraToObject` in ein wiederverwend-
  bares `frameBox(box)` extrahiert.
- `frontend/app.js` — Dropdown wird beim Laden aus `/api/reactions` befüllt,
  Button-Handler holt `/api/reactions/{id}` und ruft `playReaction` auf
  einem eigenen, dauerhaften Viewer auf (kein Card-Template nötig, da es nur
  eine Reaktions-Ansicht gibt, kein Vergleichsmodus dafür).
- `frontend/style.css` — `.section-label` (dünne Trennlinie mit Mono-Label)
  und `.reaction-row` (Select + Button nebeneinander, gleicher Stil wie die
  restlichen Eingabefelder) ergänzt.

**Getestet im Browser (Screenshots bei t≈0, t≈Übergang, t≈Ende):**
Start zeigt Essigsäure und Ethanol räumlich getrennt, in der Mitte ist die
C-OH-Bindung der Säure sichtbar am Ausblassen während sich die Atome schon
in Richtung Endposition bewegen, am Ende steht eine durchgehend verbundene
Ester-Kette (5 Schweratome) neben einem einzelnen, klar abgetrennten
Wasser-Sauerstoffatom — chemisch korrekt und mit sichtbarer Bewegung.
Keine Konsolenfehler während der Animation. Danach zur Sicherheit noch
"aspirin" aufgelöst, um zu prüfen, dass der Umbau von `fitCameraToObject`
(jetzt intern über das neue gemeinsame `frameBox()`) die normale
Molekül-Anzeige nicht kaputt gemacht hat — lief einwandfrei.

**Damit sind alle 6 ursprünglich vereinbarten Ausbaustufen erledigt**, bis
auf die eine seit Tag 1 offene Lücke: Ausbaustufe 5 (KI-Erklärtext) wartet
weiter auf einen `ANTHROPIC_API_KEY` von Niki (siehe unten, unverändert).

**Rezept, um eine weitere Reaktion zu ergänzen:** In `backend/reactions.py`
einen neuen Eintrag an `REACTIONS` anhängen mit `id`, `label` und
atom-gemappten `reactants_smiles`/`products_smiles` (SMILES mit `[C:1]`-
artigen Map-Nummern; jede Nummer, die auf beiden Seiten vorkommt, markiert
ein Atom, das erhalten bleibt und morpht). Kein Frontend- oder
Framework-Code nötig — das Dropdown befüllt sich automatisch aus
`/api/reactions`.

## 2026-09-14 (Nacht): Ausbaustufe 6 angefangen — Backend fertig, Frontend fehlt noch

Niki hat mitten in der Umsetzung gesagt, an der nächstbesten Stelle
anzuhalten und für heute zu speichern. Sauberer Zwischenstand:

**Fertig und einzeln getestet (`python reactions.py`, dann per Server-Neustart
und `curl` bestätigt):**
- `backend/reactions.py` — neue Datei. Enthält die erste Beispiel-Reaktion
  (Veresterung: Essigsäure + Ethanol → Ethylacetat + Wasser) als
  atom-gemappte SMILES, plus `build_reaction()`, die daraus Start-/End-3D-
  Struktur, Atom-Korrespondenz und die drei Bindungs-Listen
  (`persistent_bonds`, `broken_bonds`, `formed_bonds`) berechnet. Testlauf
  bestätigt: 7 Atome auf beiden Seiten, vollständige 1:1-Zuordnung, genau 1
  gebrochene Bindung (C-OH der Säure) und genau 1 neu gebildete (die
  Ester-C-O-C-Bindung) — chemisch korrekt.
- `backend/app.py` — zwei neue Routen ergänzt und funktionsfähig:
  `GET /api/reactions` (Liste fürs Auswahlmenü) und
  `GET /api/reactions/{id}` (die vollen Animationsdaten). Per `curl`
  bestätigt: beide liefern 200 OK mit den erwarteten Daten.

**Noch nicht angefasst — das ist der Rest von Ausbaustufe 6:**
- `frontend/index.html`: Auswahl-Menü (`<select>`) + "Ablaufen lassen"-Button
  + eigener Viewer-Bereich für die Reaktion fehlen noch im Markup.
- `frontend/viewer.js`: die eigentliche Animationslogik (`playReaction`)
  fehlt komplett — Kugeln pro Atom bauen, Positionen jeden Frame zwischen
  Start- und End-Koordinaten interpolieren (über `correspondence`), Bindungen
  ein-/ausblenden (`broken_bonds` verblassen in der ersten Hälfte,
  `formed_bonds` erscheinen in der zweiten Hälfte, `persistent_bonds` bleiben
  durchgehend sichtbar).
- `frontend/app.js`: Dropdown aus `/api/reactions` befüllen, Button-Handler,
  der `/api/reactions/{id}` holt und `playReaction` anstößt.
- Noch keinerlei Browser-Test der Animation selbst (nur die Backend-Daten
  sind geprüft, nicht das Rendering/die Bewegung).

Der volle Bauplan mit allen Details (genaue Interpolations-/Opazitäts-Logik,
Elementfarben-Wiederverwendung usw.) steht unverändert in
`C:\Users\nikiw\.claude\plans\swirling-knitting-wadler.md` — beim
Weitermachen zuerst dort nachlesen, dann direkt bei Schritt 3
("Umsetzungsschritte") weitermachen.

Server wurde für heute sauber gestoppt (lief auf Port 8001).

## 2026-09-14 (Abend, autonomer Durchlauf): Ausbaustufen 2, 4, 5 gebaut

Niki war für ~30-40 Min. weg vom PC und hat gesagt: alles Übrige bauen, nicht
fragen, bei echten Blockern eine Lücke lassen statt zu warten. Ergebnis:

**Ausbaustufe 2 — Darstellungs-Layer erledigt.** Drei Modi über Buttons
oberhalb des Viewers: Kugel-Stab (Standard), Raumfüllend (van-der-Waals-
Radien, keine Bindungen sichtbar — der "Blob"-Look), Ladung (Kugeln nach
Gasteiger-Partialladung eingefärbt, Rot=negativ/Blau=positiv/Creme=neutral).
`backend/chem.py` berechnet die Partialladungen jetzt zusätzlich pro Atom
(`AllChem.ComputeGasteigerCharges`). Die gesamte Three.js-Logik wurde dafür
aus `app.js` in ein eigenes Modul `frontend/viewer.js` ausgelagert
(`createViewer(container)` als Fabrik-Funktion) — nötig, damit auch der
Vergleichsmodus mehrere unabhängige Viewer-Instanzen bekommen kann.

**Ausbaustufe 4 — Vergleichsmodus erledigt.** "+ Vergleichen"-Button öffnet
ein zweites Eingabefeld; beim Auflösen erscheinen zwei Karten (Viewer +
Fakten + Erklärung) nebeneinander in einem Grid (`#cards.cards-compare`),
beide mit dem gleichen Darstellungsmodus. Karten werden aus einem
HTML-`<template>` geklont, nicht mehr fest im Markup.

**Ausbaustufe 5 — KI-Erklärtext eingebaut, aber mit einer bewussten Lücke:**
`backend/explain.py` schickt Name+Formel an Claude (`claude-haiku-4-5-20251001`
— bewusst das kleine/günstige Modell, weil die Aufgabe eng und einfach ist,
siehe Gedächtnis-Eintrag zur Modell-Wahl) und lässt sich die Erklärung in
2-3 einfachen Sätzen geben. **Braucht einen `ANTHROPIC_API_KEY`, den ich
nicht habe und nicht raten sollte** — Niki muss dafür `backend/.env.example`
nach `backend/.env` kopieren und seinen eigenen Key eintragen. Ohne Key
zeigt das Erklärungs-Feld einen klaren "noch nicht verfügbar"-Hinweis statt
abzustürzen — Rest der App funktioniert komplett unabhängig davon. **Das ist
die Lücke, die noch auf Niki wartet.**

**Nebenbei aufgetreten — ein hartnäckiger Server-Fallstrick:** Port 8000
hing an einem alten Uvicorn-Prozess fest, der sich weder per `taskkill`
noch per Neustart mit `--reload` abschütteln ließ (`netstat` zeigte ihn
weiter als "ABHÖREN", obwohl `tasklist` keinen solchen Prozess mehr kannte —
vermutlich ein Anzeige-/Cache-Problem des Sandbox-Netzwerkstacks, nicht ein
echtes Zombie-Problem). Lösung: Server läuft jetzt auf **Port 8001** statt
8000. Falls Niki Port 8000 wieder freibekommen will: Rechner neu starten
sollte reichen, oder im Task-Manager nach einem alten `python.exe`/
`uvicorn`-Prozess suchen.

## 2026-09-14 (Abend): Redesign auf Three.js + Fakten-Panel (Ausbaustufe 3 erledigt)

Niki gefiel die Cyan-Scanline-HUD-Optik nicht — er fand als Referenz
**arrakis.tech** (warmes Schwarz, dünne Haarlinien, Bernstein-Akzentfarbe,
Statistik-Kacheln, sanftes Glühen). Außerdem wollte er einen echten
"Blender-Look" für das Molekül selbst — das konnte 3Dmol.js technisch nicht
(nur flache Cartoon-Materialien).

**Größte Änderung: Wechsel der 3D-Engine von 3Dmol.js auf Three.js.**
Läuft als ES-Modul über eine Importmap (`index.html`) von jsdelivr, kein
Bundler nötig. Damit gibt es jetzt echte glänzende Materialien
(`MeshPhysicalMaterial` mit Clearcoat), eine Umgebungsreflexion
(`RoomEnvironment` + `PMREMGenerator`), weiches Studio-Licht (Haupt-/Füll-/
Ambient-Licht) und einen echten weichen Kontaktschatten unter dem Molekül
(`ShadowMaterial` auf einer unsichtbaren Boden-Ebene). Maus-Drehen/Zoomen
läuft jetzt über `OrbitControls` statt 3Dmol.js' eigener Steuerung.

**Datenformat geändert:** Das Backend gibt keinen Molblock-Text mehr aus,
sondern fertiges JSON (`atoms: [{element,x,y,z}]`, `bonds: [{a,b}]`) —
`chem.py`s `_build_structure()` baut das direkt aus dem RDKit-Mol-Objekt
(ersetzt `_smiles_to_3d_molblock`). `app.js` baut daraus selbst die
Kugeln/Zylinder in der Three.js-Szene.

**Fakten-Panel (Ausbaustufe 3) eingebaut:** Summenformel, molare Masse,
LogP, TPSA, H-Brücken-Donoren/-Akzeptoren, drehbare Bindungen — als
Statistik-Kacheln unter dem Viewer, im arrakis-artigen Kachel-Stil. Wichtig:
diese Werte werden **lokal mit RDKit berechnet** (`Descriptors`/
`rdMolDescriptors`), nicht bei PubChem abgefragt — spart einen
Netzwerk-Aufruf und funktioniert auch für Strukturen, die PubChem nicht
kennt. RDKits LogP-Berechnung ist nicht identisch mit PubChems
XLogP-Algorithmus, deshalb Panel-Label "LogP (berechnet)".

**Neue Design-Tokens** (`style.css`): warmes Nahe-Schwarz (`#0c0a08`),
cremefarbener Text, gedämpfte Bernstein-Akzentfarbe (`#e0965a`), dünne
1px-Rahmen statt Neon-Glow, kleine Eckstriche als dezentes Detail, Google
Fonts "Inter" (Fließtext) + "JetBrains Mono" (kleine Großbuchstaben-Labels).

**Getestet:** "aspirin" und "water" per Browser-Tool durchgeklickt — Kugeln
glänzen sichtbar (echtes Glanzlicht + weicher Schatten), Fakten-Kacheln
zeigen plausible Werte, Drehen per Maus-Drag funktioniert.

**Kleiner Fallstrick beim Testen:** Nach Code-Änderungen an `chem.py`/
`app.py` muss der Uvicorn-Server neu gestartet werden (jetzt mit
`--reload`-Flag gestartet, damit das künftig automatisch passiert) — sonst
liefert er weiter die alte Antwortstruktur, während das Frontend schon auf
das neue Format wartet (genau das ist beim ersten Testlauf heute passiert).

## 2026-09-14 (Nachmittag): Beide Namen anzeigen — 2 Fallstricke behoben

Niki wollte, dass Fallstrick 1 und 3 von unten (generischer statt
gebräuchlicher Name; SMILES statt hübschem Namen) besser gelöst werden, indem
**beide Namen gleichzeitig** angezeigt werden: der gebräuchliche Name groß,
der IUPAC-Fachname klein darunter ("Fachname: ...").

Lösung: PubChem hat neben `IUPACName` auch ein Feld `Title` — das ist genau
der gebräuchliche/umgangssprachliche Name (z. B. "Aspirin", "D-Glucose",
"Ethanol"), getrennt vom systematischen `IUPACName`. Beide werden jetzt bei
jeder Anfrage mitgeholt (`ConnectivitySMILES,Title,IUPACName` in einem
Property-Aufruf statt vorher nur SMILES + Synonyme).

Für den direkten-SMILES-Fall (Fallstrick 3) gibt's jetzt zusätzlich eine
Rückwärtssuche: die eingegebene SMILES wird per POST an
`/compound/smiles/property/...` geschickt, um Title + IUPACName aus PubChem
zu holen (POST statt GET, weil SMILES Sonderzeichen wie `()=` enthalten kann,
die in einer URL Probleme machen würden). Kennt PubChem die Struktur nicht,
fällt es sauber zurück auf die reine SMILES-Anzeige — kein Absturz.

`chem.py`s `ResolvedMolecule` hat jetzt `common_name` und `iupac_name` statt
nur `resolved_name`. Frontend blendet die Fachname-Zeile aus, wenn sie
(fast) identisch mit dem gebräuchlichen Namen wäre (z. B. bei Ethanol/ethanol).

Fallstrick 1 (Formel-Heuristik wählt manchmal einen Oberbegriff wie "Hexose"
statt "Glukose") besteht weiterhin — das war nicht Teil dieser Änderung und
bleibt unten als offener Punkt stehen.

## 2026-09-14: Kern gebaut und getestet

Erster Baustein steht: man tippt einen Molekülnamen, eine Summenformel oder
einen SMILES-Code ins Eingabefeld, und bekommt ein rotierbares 3D-Modell im
Browser, im dunklen "Iron-Man-HUD"-Look.

**Architektur:**
- `backend/chem.py` — die eigentliche Logik. Versucht die Eingabe in dieser
  Reihenfolge zu lesen: 1) direkt als SMILES (RDKit lokal), 2) als Name bei
  PubChem, 3) als Summenformel bei PubChem (Mehrdeutigkeits-Fall — wenn
  mehrere Stoffe zur Formel passen, wird automatisch die niedrigste PubChem-
  CID gewählt und im Antworttext offen gesagt, welcher Stoff gewählt wurde
  und warum). Danach wird immer lokal mit RDKit eine 3D-Struktur berechnet
  (`EmbedMolecule` + `MMFFOptimizeMolecule`) und als Molblock zurückgegeben.
- `backend/app.py` — dünner FastAPI-Wrapper: `/api/resolve` (POST) ruft
  `chem.resolve()` auf, liefert `{molblock, common_name, iupac_name, note}`
  als JSON (Stand nach der Namens-Erweiterung vom Nachmittag, siehe oben).
  Dient außerdem den `frontend/`-Ordner statisch unter `/` (kein CORS-Ärger,
  kein zweiter Server).
- `frontend/` — ein Eingabefeld, ein 3Dmol.js-Viewport, ein Hinweistext-
  Bereich für die Mehrdeutigkeits-Notiz. Reines HTML/CSS/JS, kein Build.

**Getestet (alle vier Fälle laufen, per Browser-Tool durchgeklickt):**
"aspirin" (Name), "C6H12O6" (Mehrdeutige Formel), "CCO" (direktes SMILES),
"water" (Name). Rotation per Maus-Drag funktioniert (3Dmol.js-eigene Steuerung).

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

```bash
cd "Claude Code Projekte/molecule-viewer/backend"
./.venv/Scripts/python.exe -m uvicorn app:app --reload --port 8001
```

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
ein paar Karten klicken (z. B. "Aspirin", "Vitamin C"), und unter "Peptid-
Wirkstoffe" auf "Ozempic / Semaglutid" (PDB `4ZGM`) und "Insulin (an seinem
Rezeptor)" (PDB `4OGA`, zwei Ketten A+B) — beide über `/api/pdb-ligand`,
kein Docking, dauert beim ersten Mal einen Moment. Danach Eingabefeld
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
schnell), und ganz unten bei "Molekulardynamik" "Beispiel laden" (füllt
`caffeine`) + "Simulieren" — sollte nach ~1 Sekunde ein sichtbar
wackelndes Molekül zeigen.

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
Raum, Protein-Docking, Molekulardynamik), plus eine 10. (Gleichungslöser)
und eine 11., zweiteilige Ausbaustufe vom 2026-09-19 (autonomer Durchlauf):
PDB-Liganden direkt anzeigen (`/api/pdb-ligand`) + Bibliothek-Bereich im
Frontend, samt Folge-Ergänzung um Insulin an seinem Rezeptor (4OGA, per
neuem `chain_ids`-Parameter).** Einzige offene Lücke aus dem Kern:
KI-Erklärtext (Ausbaustufe 5)
wartet weiter auf einen `ANTHROPIC_API_KEY` von Niki — `backend/.env.example`
nach `backend/.env` kopieren, echten Key eintragen, Server neu starten.
Alles andere läuft schon ohne das.

**Nächste Schritte sind komplett offen** — es gibt keine vereinbarte
Ausbaustufe mehr, die noch aussteht. Ideen für kleinere Lücken/Politur,
falls gefragt: weitere Reaktionen zu `backend/reactions.py` ergänzen
(Rezept siehe oben), die Formel-Mehrdeutigkeits-Heuristik verbessern
(Fallstrick 1 unten), beim Protein-Docking die Ladungszustände des
Liganden vor dem Docken berücksichtigen (siehe Einschränkung oben), bei
der Molekulardynamik echte Bindungslängen-Constraints (SHAKE/RATTLE)
einbauen (siehe Einschränkung oben), die Atom-Zuordnung im Gleichungslöser
verbessern (z. B. per lokaler Bindungsumgebung statt reinem Abstand vor-
matchen, siehe Eintrag vom 2026-09-19), weitere Peptid-Wirkstoffe/Klein-
Molekül-Karten zur Bibliothek ergänzen (z. B. per `hetero_code` oder
`chain_ids`, siehe die beiden 2026-09-19-Einträge oben), oder ein
Export/Screenshot-Feature
und ein echtes Deployment (Render/Fly.io, braucht Linux-Vina-Build) —
aber erst wieder anfangen, wenn Niki eine neue Richtung vorgibt.
