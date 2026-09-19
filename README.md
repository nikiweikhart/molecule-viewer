# Molekül-Viewer

Ein Tool, das aus einem Molekülnamen, einer Summenformel oder einem
SMILES-Code ein rotierbares 3D-Modell im Browser baut — inklusive
Fakten-Panel, Vergleichsmodus, Reaktions-Animationen, chemischem
Ähnlichkeits-Explorer, Protein-Docking (AutoDock Vina) und einer
Molekulardynamik-Simulation.

Backend ist Python (FastAPI + RDKit), Frontend ist reines HTML/CSS/JS ohne
Build-Schritt (Three.js als ES-Modul von einem CDN). Beides läuft im selben
Prozess: `uvicorn` dient das Frontend und die API zugleich.

## Funktionen

- **Auflösung**: Name, Summenformel oder SMILES → 3D-Struktur (PubChem +
  RDKit-Embedding).
- **Fakten-Panel**: Summenformel, Molmasse, LogP, TPSA, H-Brücken,
  drehbare Bindungen — lokal mit RDKit berechnet.
- **Drei Darstellungs-Layer**: Kugel-Stab, raumfüllend, Ladung
  (Gasteiger-Partialladungen).
- **Vergleichsmodus**: zwei Moleküle nebeneinander.
- **KI-Erklärtext**: kurze Erklärung über die Claude-API (braucht eigenen
  API-Key, siehe unten).
- **Reaktions-Animation**: Moleküle morphen zwischen Edukt und Produkt,
  Bindungen brechen/entstehen sichtbar.
- **Chemischer Raum**: viele Moleküle auf einmal, nach struktureller
  Ähnlichkeit (Morgan-Fingerprints, eigene PCA + k-Means) auf einer 2D-Karte
  angeordnet und gruppiert.
- **Protein-Docking**: PDB-ID + Ligand → AutoDock Vina dockt den Liganden in
  die Bindetasche, Ergebnis inkl. Bindungsenergien.
- **Molekulardynamik**: Molekül unter simulierter thermischer Bewegung bei
  300 K (selbstgeschriebener Velocity-Verlet-Integrator auf RDKits
  MMFF94-Kraftfeld).

Details zu Architektur, Design-Entscheidungen und bekannten Einschränkungen
stehen in [`docs/stand.md`](docs/stand.md).

## Setup

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Für Protein-Docking zusätzlich `backend/tools/vina.exe` (AutoDock Vina
1.2.7, Windows-Binary) von den
[AutoDock-Vina-Releases](https://github.com/ccsb-scripps/AutoDock-Vina/releases)
laden.

Für die KI-Erklärung `backend/.env.example` nach `backend/.env` kopieren und
einen eigenen `ANTHROPIC_API_KEY` eintragen. Ohne Key läuft der Rest der App
normal weiter, die Erklärung zeigt nur einen Hinweis statt abzustürzen.

## Starten

```bash
cd backend
./.venv/Scripts/python.exe -m uvicorn app:app --reload --port 8001
```

Dann `http://localhost:8001` im Browser öffnen.

## Bekannte Einschränkungen

- Die Formel-Mehrdeutigkeits-Heuristik (z. B. bei `C6H12O6`) wählt die
  niedrigste PubChem-CID, nicht immer den intuitivsten Treffer.
- Beim Docking wird nur die neutrale Ligandenform berücksichtigt — reale
  Ladungszustände (z. B. Salzbrücken) fehlen, Bindungsenergien liegen daher
  in der richtigen Größenordnung, aber nicht exakt.
- Die Molekulardynamik nutzt Force-Capping statt echter
  Bindungslängen-Constraints (SHAKE/RATTLE) und pendelt sich auf ein etwas
  höheres Energieniveau als das nominelle 300-K-Ziel ein.

Alle drei sind bewusst offen benannt — siehe `docs/stand.md` für den vollen
Kontext.
