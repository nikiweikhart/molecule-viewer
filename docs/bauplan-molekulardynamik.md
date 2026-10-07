# Molekül-Viewer — Molekulardynamik-Simulation

## Context

Letzte der drei "richtig aufwendigen", API-freien Folge-Ausbaustufen (nach
chemischem Raum und Protein-Docking, siehe `docs/stand.md`). Ziel: ein
Molekül nicht nur statisch zeigen oder zwischen zwei Zuständen morphen
lassen, sondern echte thermische Bewegung über die Zeit simulieren —
Atome, die unter einem echten Kraftfeld wackeln/vibrieren, nicht nur
hübsch rotieren.

## Recherche-Ergebnis — bewusste Kursänderung gegenüber der ursprünglichen Idee

Ursprünglich war "via OpenMM" angedacht. Recherche-Ergebnis:

- **OpenMM selbst hat saubere Windows-Unterstützung** (`pip install
  openmm` funktioniert plattformübergreifend, offizielle Wheels).
- **Aber:** OpenMMs eigene Kraftfelder (Amber/CHARMM) kennen nur
  Standard-Bausteine (Aminosäuren, Wasser, Nukleinsäuren) — für ein
  **beliebiges** Molekül aus der Nutzereingabe (wie überall sonst in
  dieser App) bräuchte es zusätzlich `openmmforcefields` +
  `openff-toolkit`, um aus SMILES automatisch Kraftfeld-Parameter (GAFF
  oder SMIRNOFF) zu erzeugen. Recherche zeigt: `openff-toolkit` wird
  offiziell nur auf macOS/Linux getestet, volle Funktionalität hängt an
  `AmberTools`, das **nicht zuverlässig per pip unter Windows**
  installierbar ist (klassisch nur über conda) — genau das gleiche
  Windows-Problem wie bei Vina, nur diesmal ohne die einfache
  "eine fertige `.exe` laden"-Abkürzung, weil es ein tief verschachtelter
  Python-Abhängigkeitsbaum ist, keine einzelne Binary.
- **Entscheidung: kein OpenMM.** Stattdessen die Dynamik direkt mit dem
  MMFF94-Kraftfeld bauen, das RDKit ohnehin schon mitbringt und in dieser
  App längst im Einsatz ist (`AllChem.MMFFOptimizeMolecule` in `chem.py`
  seit dem allerersten Baustein). RDKits `ForceField`-Objekt gibt über
  `CalcGrad()` echte Kraftfeld-Gradienten zurück (bestätigt per RDKit-
  Doku/Community-Beispiele) — genug, um selbst einen Velocity-Verlet-
  Integrator zu schreiben (Standard-Lehrbuch-Algorithmus für MD: Position
  und Geschwindigkeit abwechselnd aus der Kraft fortschreiben). Das ist
  **echte** Molekulardynamik (numerische Integration von Newtons
  Bewegungsgleichungen mit einem echten Kraftfeld), nur selbstgeschrieben
  statt über ein Industriestandard-Paket — und **bringt exakt null neue
  Abhängigkeiten** mit (nur RDKit + numpy, beide schon installiert). Damit
  ist diese Ausbaustufe sogar noch "kostenloser" als die anderen beiden.
  Trade-off, offen benannt: kein Thermostat/Barostat auf Lehrbuch-Niveau,
  keine Perioden-Randbedingungen, keine GPU — für "ein Molekül sichtbar
  wackeln lassen" mehr als ausreichend.

## Physik (kurz, Details im Code als Kommentar)

- Einheiten-System Å / Femtosekunden / amu / kcal·mol⁻¹ (Standard in der
  Chemie-MD-Literatur). Umrechnungskonstante Kraft→Beschleunigung
  hergeleitet: `4.184e-4` (kcal·mol⁻¹·Å⁻¹·amu⁻¹ → Å·fs⁻²) — sauber aus
  SI-Einheiten abgeleitet, keine geratene Zahl.
- Start-Geschwindigkeiten aus einer Maxwell-Boltzmann-Verteilung bei einer
  Zieltemperatur (300 K), damit von Anfang an echte thermische Bewegung
  da ist statt nur ein Sich-Beruhigen zum Minimum hin.
- Velocity-Verlet-Integration, `dt = 0.5 fs` (Standard-Schrittweite bei
  expliziten Wasserstoffen — deren Streckschwingungen sind die
  schnellsten Bewegungen im System).
- Einfacher Geschwindigkeits-Rescaling-Thermostat alle paar Schritte (auf
  die per Äquipartitionssatz erwartete Gesamt-kinetische-Energie
  reskalieren, Skalierung sanft begrenzt) — verhindert, dass sich
  Integrationsfehler über hunderte Schritte zu einer explodierenden
  Struktur aufschaukeln. Kein rigoroser NVT-Thermostat, aber genug für
  eine stabile, hübsche Demo-Trajektorie.
- Wasserstoffe werden **diesmal bewusst gezeigt** (Gegensatz zur
  Reaktions-Animation, die sie versteckt) — die schnelle X-H-Wackel-
  Bewegung ist genau das, was "Molekül vibriert wirklich" visuell zeigt.

## Backend

**Neue Datei `backend/dynamics.py`:**
- `run_md(query: str, temperature=300.0, n_steps=600, dt_fs=0.5,
  record_every=2) -> dict`:
  1. Ligand über `chem._resolve_to_names()` auflösen (Wiederverwendung,
     gleiches Muster wie in `chemspace.py`/`docking.py`).
  2. RDKit-Mol mit `AddHs` + `EmbedMolecule` + `MMFFOptimizeMolecule`
     aufbauen (gleiches Muster wie `chem.py::_build_structure`) — liefert
     eine sinnvolle Startgeometrie statt aus einer zufälligen Embedding-
     Konformation heraus zu simulieren.
  3. `AllChem.MMFFGetMoleculeProperties` + `MMFFGetMoleculeForceField`,
     `ff.Initialize()`.
  4. Massen (`atom.GetMass()`) und Startpositionen aus dem Konformer
     auslesen, Start-Geschwindigkeiten aus Maxwell-Boltzmann.
  5. Velocity-Verlet-Schleife: `ff.CalcGrad(positions)` pro Schritt
     (explizite Positionsübergabe statt sich auf implizite FF-interne
     Mutation zu verlassen — robuster), Thermostat alle 10 Schritte,
     Positionen alle `record_every` Schritte als Frame aufzeichnen.
  6. Rückgabe: `{elements, bonds, frames: [[{x,y,z}, ...], ...],
     temperature, steps_simulated, fs_simulated}` — `bonds` einmalig
     (ändert sich während der MD nicht), `frames` eine Liste von
     Positions-Snapshots.
  7. Eigener `if __name__ == "__main__":`-Testblock (z. B. Ethanol) —
     Energie-Erhaltung grob prüfen (Gesamtenergie sollte über die
     Trajektorie nicht explodieren), Frame-/Atomanzahl ausgeben.

**`backend/app.py`:** neues Pydantic-Model `DynamicsRequest {query: str}`,
neue Route `POST /api/dynamics` (kein neuer Error-Typ nötig über das
Muster hinaus — `chem.ResolveError` wird abgefangen und wie bei den
anderen Routen als 400 zurückgegeben).

## Frontend

**`frontend/viewer.js`:** neue Methode `playTrajectory(data)` auf dem
`createViewer()`-Objekt — analog zu `playReaction`, aber mit einer langen
Frame-Liste statt nur Start/Ende: baut eine Kugel pro Atom + einen
Zylinder pro Bindung einmalig aus Frame 0 (gleiches Baumuster wie in
`playReaction`, Bindungslänge/-rotation pro Frame neu berechnet statt
interpoliert), spielt die Frames per `requestAnimationFrame` in einer
Endlosschleife ab — **Ping-Pong** (vorwärts bis zum letzten Frame, dann
rückwärts, dann wieder vorwärts, …) statt einem harten Sprung zurück zu
Frame 0, damit die Schleife nahtlos wirkt statt sichtbar zu "ruckeln".
Kamera wird einmalig auf Frame 0 (+ Puffer) gefittet, da thermische
Bewegung nur eine kleine Auslenkung um die Ausgangslage ist. Neuer
`clearTrajectory()`-Aufräummechanismus, ins bestehende Muster von
`clearReaction()`/`clearDocking()` eingehängt (jede der drei Methoden
räumt die jeweils anderen beiden mit auf, wie es dort schon gemacht wird).

**`frontend/index.html` + `app.js` + `style.css`:** neuer Bereich
"Molekulardynamik" — ein Eingabefeld (Name/Formel/SMILES, gleiches Format
wie überall), "Beispiel laden" (füllt `caffeine` — mehrere Ringe plus frei
drehbare Gruppen, zeigt reichhaltigere Bewegung als z. B. Ethanol),
"Simulieren"-Button mit Ladeanzeige, eigener `.viewer-frame`. Info-Zeile
zeigt simulierte Zeit/Temperatur (z. B. "300 K, 300 fs simuliert").

## Umsetzungsschritte

1. `backend/dynamics.py` schreiben, exakte RDKit-`ForceField`-API-Details
   (Signatur von `CalcGrad`, `Positions()`) beim ersten Testlauf
   gegenprüfen (gleiches Vorgehen wie bei den `meeko`-CLI-Flags zuvor —
   Doku gibt die grobe Form vor, Feinheiten am echten Objekt bestätigen).
   Isoliert mit `python dynamics.py` testen (Ethanol) — Energie-Verlauf
   über die Trajektorie auf Plausibilität prüfen (bleibt in einem
   vernünftigen Band, explodiert nicht).
2. `app.py`: neue Route, per `curl` gegenprüfen.
3. `index.html` + `style.css`: neuer Abschnitt.
4. `viewer.js`: `playTrajectory()` inkl. Ping-Pong-Loop.
5. `app.js`: Verdrahtung, Ladezustand, Info-Anzeige.
6. Server neu starten, im Browser: Beispiel laden ("caffeine"),
   simulieren, prüfen dass sichtbare, kontinuierliche Wackel-/Vibrations-
   bewegung ohne Sprünge/Explosion läuft, Konsole ohne Fehler.
7. `docs/stand.md` aktualisieren: neue Ausbaustufe, die bewusste
   Kursänderung weg von OpenMM klar erklärt (nicht nur "ist fertig"),
   Physik-Vereinfachungen offen benannt (einfacher Thermostat, kein
   rigoroses Ensemble), Hinweis dass dies **keine neue Abhängigkeit**
   bringt.

## Verifikation

- `python dynamics.py` — Ethanol-Testlauf, Energie bleibt über alle
  Schritte in einem stabilen Band, korrekte Frame-/Atomanzahl.
- `curl -X POST http://127.0.0.1:8001/api/dynamics -d
  '{"query":"caffeine"}'` — 200 mit vollständiger Frame-Liste.
- Browser: Beispiel laden → simulieren → sichtbare, flüssige,
  endlos-loopende Wackelbewegung (inkl. sichtbarer H-Atome), keine
  Konsolenfehler, keine sichtbaren Sprünge beim Loop-Übergang.
