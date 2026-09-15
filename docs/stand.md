# Stand: Molekül-Viewer

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
4. PubChem-Anfragen haben kein Retry/Caching — bei wiederholten Anfragen zum
   selben Molekül wird jedes Mal neu angefragt. Für den Kern okay, könnte bei
   echter Nutzung ein einfacher In-Memory-Cache werden.

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

Dann **`http://localhost:8001`** im Browser öffnen (Port 8001, nicht 8000 —
siehe Fallstrick oben). Eingabefeld testen mit z. B. `aspirin`, `C6H12O6`,
`CCO`, die drei Darstellungs-Buttons durchklicken, "+ Vergleichen" mit einem
zweiten Molekül ausprobieren, unten die Veresterung über "▶ Ablaufen
lassen" abspielen, beim "Chemischer Raum"-Bereich "Beispiel-Set laden" +
"Karte erzeugen" ausprobieren, bei "Protein-Docking" "Beispiel laden"
(füllt `3PTB` + `benzamidine`) + "Docken" ausprobieren (dauert beim
allerersten Mal am längsten, danach ist die Rezeptor-Vorbereitung für
`3PTB` in `backend/pdb_cache/` gecacht und es geht schnell), und ganz
unten bei "Molekulardynamik" "Beispiel laden" (füllt `caffeine`) +
"Simulieren" — sollte nach ~1 Sekunde ein sichtbar wackelndes Molekül
zeigen.

Falls die venv fehlt oder kaputt ist: `python -m venv .venv` im `backend`-
Ordner, dann `./.venv/Scripts/python.exe -m pip install fastapi uvicorn rdkit
requests anthropic python-dotenv numpy meeko scipy gemmi`. **Zusätzlich**
liegt unter `backend/tools/vina.exe` die AutoDock-Vina-Binary — die ist
keine Python-Abhängigkeit und muss beim venv-Neuaufsetzen nicht neu
installiert werden, nur falls der ganze `backend`-Ordner fehlt: neu laden
von `github.com/ccsb-scripps/AutoDock-Vina/releases` (Datei
`vina_1.2.7_win.exe`, umbenennen zu `vina.exe`). Für die Molekulardynamik
ist nichts Zusätzliches nötig — `dynamics.py` nutzt nur RDKit + numpy.

**Alle 6 ursprünglich vereinbarten Ausbaustufen sind erledigt, plus alle
3 der "richtig aufwendigen" API-freien Folge-Ausbaustufen (chemischer
Raum, Protein-Docking, Molekulardynamik).** Damit ist die ursprünglich
besprochene Roadmap komplett durch. Einzige offene Lücke aus dem Kern:
KI-Erklärtext (Ausbaustufe 5) wartet weiter auf einen `ANTHROPIC_API_KEY`
von Niki — `backend/.env.example` nach `backend/.env` kopieren, echten
Key eintragen, Server neu starten. Alles andere läuft schon ohne das.

**Nächste Schritte sind komplett offen** — es gibt keine vereinbarte
Ausbaustufe mehr, die noch aussteht. Ideen für kleinere Lücken/Politur,
falls gefragt: weitere Reaktionen zu `backend/reactions.py` ergänzen
(Rezept siehe oben), die Formel-Mehrdeutigkeits-Heuristik verbessern
(Fallstrick 1 unten), beim Protein-Docking die Ladungszustände des
Liganden vor dem Docken berücksichtigen (siehe Einschränkung oben), oder
bei der Molekulardynamik echte Bindungslängen-Constraints (SHAKE/RATTLE)
einbauen, um näher am nominellen Temperatur-Ziel zu bleiben (siehe
Einschränkung oben) — aber erst wieder anfangen, wenn Niki eine neue
Richtung vorgibt.
