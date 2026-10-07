# Molekül-Viewer — Ausbaustufe 6: Reaktions-Animation

## Context

Letzte der 6 ursprünglich vereinbarten Ausbaustufen. Bewusst zuletzt, weil sie
am komplexesten ist: eine "echte" chemische Reaktion (welche Bindung bricht,
welche entsteht) ist kein reines Darstellungsproblem wie die anderen fünf,
sondern braucht einen tatsächlichen Reaktionsmechanismus als Datengrundlage.

**Wichtige Abgrenzung, die ich bewusst so gestalte statt zu versuchen, "jedes
beliebige Molekülpaar reagieren zu lassen":** Ein allgemeiner
Reaktions-Vorhersager (aus zwei beliebigen Molekülen automatisch das Produkt
erraten) ist ein eigenes, ungelöstes Forschungsproblem — das würde ich nicht
zuverlässig hinkriegen und würde am Ende falsche Chemie zeigen, ohne dass
das offensichtlich wäre. Stattdessen: eine kleine, **handkuratierte Liste**
bekannter Reaktionen (Reaktanten + Produkte + Atom-Zuordnung fest vorgegeben,
chemisch korrekt), aus der man wählt und die dann animiert abläuft. Klar
benannt als Beispielsammlung, nicht als allgemeiner Reaktions-Löser — das ist
ehrlicher und war auch immer der Rahmen, in dem die Ausbaustufe besprochen
wurde ("Reaktions-Animation zwischen zwei Molekülen").

**Technischer Kniff, der das handhabbar macht:** Ich schreibe Reaktant- und
Produkt-SMILES von Hand mit Atom-Map-Nummern (z.B. `[CH3:1][C:2](=[O:3])[OH:4]`)
— per Test bestätigt, dass RDKit diese Nummern beim Parsen zuverlässig auf
`atom.GetAtomMapNum()` durchreicht. Damit ist die Zuordnung "welches Atom im
Reaktanten wird zu welchem Atom im Produkt" fest bekannt, ohne mich auf
RDKits automatische Reaktions-Engine (SMARTS/SMIRKS-Ausführung) verlassen zu
müssen, deren Atom-Buchhaltung bei einem Testlauf verwirrend/unzuverlässig
aussah. Wasserstoffe werden in der Reaktions-Ansicht bewusst ausgeblendet
(Skelett-Stil, wie in Lehrbuch-Mechanismen üblich) — sie zuverlässig
zwischen zwei separat berechneten 3D-Strukturen einander zuzuordnen ist ein
eigenes, nicht lohnendes Problem für diese Ausbaustufe.

**Umfang:** Eine vollständig funktionierende, gut getestete Beispiel-Reaktion
(Veresterung: Essigsäure + Ethanol → Ethylacetat + Wasser), mit einer
Datenstruktur, die weitere Reaktionen später zu einer reinen
Daten-Ergänzung macht (kein Framework-Umbau nötig) — Qualität vor Quantität,
passend zum Zeitrahmen.

## Backend

Neue Datei `backend/reactions.py`:
- Eine Liste `REACTIONS` mit Einträgen `{id, label, reactants_smiles,
  products_smiles}` — beide SMILES-Strings sind Mehrkomponenten-SMILES
  (Punkt-getrennt) mit Atom-Map-Nummern, z.B.:
  - reactants: `[CH3:1][C:2](=[O:3])[OH:4].[CH3:5][CH2:6][OH:7]`
  - products: `[CH3:1][C:2](=[O:3])[O:7][CH2:6][CH3:5].[OH2:4]`
- Funktion `build_reaction(entry) -> dict`:
  1. Beide Multi-Komponenten-SMILES parsen, `Chem.GetMolFrags` nutzen, um die
     einzelnen Molekül-Fragmente zu trennen.
  2. Jedes Fragment einzeln 3D einbetten (gleiches Muster wie in
     `chem.py::_build_structure`: `AddHs` nur für die Embedding-Geometrie,
     danach beim Auslesen der Atome wieder nur Schweratome exportieren).
  3. Fragmente entlang der X-Achse nebeneinander verschieben (Start: zwei
     Reaktanten mit Lücke dazwischen; Ende: die Produkt-Fragmente analog),
     damit die Szene nicht überlappt.
  4. Über die Atom-Map-Nummern eine `correspondence`-Liste bauen (Start-Index
     → End-Index für jede Map-Nummer, die auf beiden Seiten vorkommt).
  5. Bindungen (nur zwischen Schweratomen) auf beiden Seiten sammeln, über
     die Korrespondenz abgleichen → `persistent_bonds` (auf beiden Seiten
     vorhanden), `broken_bonds` (nur Start), `formed_bonds` (nur Ende, als
     End-Indizes, über die Korrespondenz zurück auf Start-Indizes für die
     Positions-Interpolation auflösbar).
  6. Rückgabe: `{label, start: {atoms, }, end: {atoms}, correspondence,
     persistent_bonds, broken_bonds, formed_bonds}` — `atoms` jeweils nur
     `{element, x, y, z}`, nur Schweratome.

`backend/app.py`: zwei neue Routen:
- `GET /api/reactions` → `[{id, label}, ...]` (für das Auswahl-Menü).
- `GET /api/reactions/{id}` → `build_reaction(entry)`.

## Frontend

- **`index.html`**: neuer Bereich unterhalb der Karten — ein
  `<select id="reaction-select">` (befüllt per JS aus `/api/reactions`), ein
  "▶ Ablaufen lassen"-Button, und ein eigener `.viewer-frame`-Block für die
  Reaktions-Animation (wiederverwendet die bestehende CSS-Klasse).
- **`viewer.js`**: neue exportierte Funktion `playReaction(viewer, data)`,
  die auf der von `createViewer()` zurückgegebenen Instanz operiert (Zugriff
  auf Szene/Kamera/Renderer über eine neue interne Methode, z.B. indem
  `createViewer` intern zusätzlich `playReaction(data)` auf dem
  zurückgegebenen Objekt anbietet, analog zu `setMolecule`/`setMode`):
  - Baut eine Kugel pro Start-Atom (Schweratome, gleiche Elementfarben/
    -radien wie im Kugel-Stab-Modus, kein Bindungs-Radius-Unterschied nötig).
  - Baut Zylinder für `persistent_bonds`, `broken_bonds`, `formed_bonds` —
    Positionen jeden Frame neu berechnet aus den aktuell interpolierten
    Atom-Positionen.
  - Ein `requestAnimationFrame`-Loop interpoliert `t` von 0→1 über z.B. 3
    Sekunden (mit Ease-in-out), setzt pro Frame: Atom-Position =
    `lerp(startPos[i], endPos[correspondence[i]], t)`; `broken_bonds`-
    Opazität `1 → 0` in der ersten Hälfte; `formed_bonds`-Opazität `0 → 1`
    in der zweiten Hälfte; `persistent_bonds` bleiben durchgehend sichtbar.
  - Nach Ablauf bleibt die Endkonformation stehen (Loop stoppt bei t=1).

## Umsetzungsschritte

1. `backend/reactions.py` schreiben, `build_reaction()` isoliert testen
   (`python reactions.py`, Ausgabe auf Plausibilität prüfen: Atomanzahl,
   Korrespondenz-Länge, `broken_bonds`/`formed_bonds` chemisch sinnvoll —
   sollte genau 1 gebrochene und 1 neu geformte Bindung sein).
2. `app.py`: zwei neue Routen.
3. `index.html` + `style.css`: Auswahl-Bereich + Button ergänzen.
4. `viewer.js`: `playReaction` bauen.
5. `app.js`: Dropdown befüllen, Button-Handler, eigenen Viewer für die
   Reaktion anlegen (wiederverwendet `createViewer`).
6. Server neu starten (Port 8001), im Browser-Tool die Veresterung abspielen
   lassen und per Screenshots in 2-3 Zeitpunkten (Start, Mitte, Ende)
   prüfen: Reaktanten sichtbar getrennt → Bindung sichtbar bricht/entsteht →
   Endprodukt (Ester + Wasser, räumlich getrennt) sichtbar.
7. `docs/stand.md` aktualisieren (Ausbaustufe 6 erledigt, Hinweis auf
   Skelett-Stil ohne H in der Reaktionsansicht, Rezept zum Ergänzen weiterer
   Reaktionen).

## Verifikation

- `python reactions.py` (eigener Testblock wie bei `chem.py`) — Atomzahlen,
  Korrespondenz und Bindungs-Listen auf Plausibilität prüfen.
- Browser-Tool: Reaktion auswählen, abspielen, Screenshots bei t≈0, t≈0.5,
  t≈1 vergleichen — sichtbare Bewegung, sichtbares Bindungs-Fade.
- Konsole auf Fehler prüfen während der Animation läuft (v.a.
  Nullpunkt-Divisionen bei Bindungslänge 0, falls zwei Atome exakt
  übereinanderliegen sollten — unwahrscheinlich, aber kurz im Code
  abfangen).
