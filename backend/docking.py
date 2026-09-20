"""Protein-Docking: eine echte Protein-Struktur laden, einen Liganden mit
AutoDock Vina in eine bekannte Bindetasche docken, das Ergebnis als
Atomkoordinaten für die 3D-Anzeige zurückgeben.

Pipeline: PDB laden -> Referenz-Liganden für die Bindetaschen-Box finden ->
Rezeptor vorbereiten (meeko) -> Liganden vorbereiten (meeko) -> Vina
ausführen -> Ergebnis-Posen zurück in Atome/Bindungen umwandeln (meeko).

Bewusst kein blindes Docking über die ganze Proteinoberfläche: nur PDB-
Einträge mit einem mitkristallisierten Referenz-Liganden werden
unterstützt (siehe _find_reference_ligand) -- ehrlicher und für eine
Lern-/Demo-Ausbaustufe die richtige Abwägung, statt eine langsame und
ungenaue Ganz-Protein-Suche vorzutäuschen. Siehe docs/stand.md.
"""

import re
import subprocess
import sys
from pathlib import Path

import requests
from rdkit import Chem
from rdkit.Chem import AllChem

import chem

BACKEND_DIR = Path(__file__).parent
PDB_CACHE_DIR = BACKEND_DIR / "pdb_cache"

# Pip installiert Konsolen-Skripte (meeko) immer direkt neben dem Python-Interpreter,
# der sie installiert hat -- egal ob das ein venv unter Windows (.venv/Scripts/*.exe)
# oder Linux (.venv/bin/*, ohne Endung) ist, oder gar kein venv (Docker-Container, siehe
# Dockerfile). sys.executable statt eines hartkodierten ".venv/Scripts"-Pfads zu nehmen
# macht das automatisch für alle drei Fälle richtig.
_SCRIPTS_DIR = Path(sys.executable).parent
_EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""
MEEKO_RECEPTOR = _SCRIPTS_DIR / f"mk_prepare_receptor{_EXE_SUFFIX}"
MEEKO_LIGAND = _SCRIPTS_DIR / f"mk_prepare_ligand{_EXE_SUFFIX}"
MEEKO_EXPORT = _SCRIPTS_DIR / f"mk_export{_EXE_SUFFIX}"

# Nur unter Windows genutzt (siehe run_vina()) -- Vinas Python-Bindings (pip-Paket
# "vina") haben dort kein funktionierendes Wheel (github.com/ccsb-scripps/
# AutoDock-Vina/issues/305), deshalb die offizielle Windows-Binary als Subprocess.
# Unter Linux/Docker gibt es diese Datei nicht; dort greift stattdessen automatisch
# der pip-Vina-Pfad in run_vina().
VINA_BINARY = BACKEND_DIR / "tools" / "vina.exe"

RCSB_FILES = "https://files.rcsb.org/download"
RCSB_DATA = "https://data.rcsb.org/rest/v1/core/entry"
RCSB_CHEMCOMP = "https://data.rcsb.org/rest/v1/core/chemcomp"

# Peptid-Wirkstoffe (z.B. Semaglutid, siehe pdb_ligand()) sind i.d.R. deutlich
# kürzer als das Zielprotein, an das sie binden -- diese Spanne grenzt eine
# plausible Peptid-Ligand-Kette von einer Rezeptor-/Enzym-Kette ab. Grobe
# Heuristik, an den beiden konkret getesteten Fällen (Semaglutid: 28-31 Reste,
# GLP-1-Rezeptor-ECD/-Volllänge: 100-380 Reste) kalibriert, siehe pdb_ligand().
_PEPTIDE_LIGAND_MAX_RESIDUES = 60

# Häufige Nicht-Liganden-HETATM-Reste: Wasser, Ionen, Kristallisationshilfsstoffe.
_IGNORED_HET_RESNAMES = {
    "HOH", "WAT", "NA", "K", "CL", "MG", "CA", "ZN", "MN", "FE", "NI", "CO",
    "SO4", "PO4", "GOL", "EDO", "PEG", "ACT", "TRS", "IPA", "DMS", "BME",
    "MPD", "FMT", "CIT", "NAG",
}

_MIN_BOX_SIZE = 15.0
_BOX_PADDING = 5.0


class DockingError(Exception):
    pass


def _run(cmd: list[str], step: str) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        # Diagnose-Hilfe für die Deployment-Umgebung, wo kein Shell-Zugriff möglich ist
        # (Render Free-Tier) -- zeigt, wo genau gesucht wurde und was tatsächlich im
        # Skript-Ordner liegt, statt nur "Datei fehlt" ohne weiteren Anhaltspunkt.
        try:
            listing = sorted(p.name for p in _SCRIPTS_DIR.glob("mk_*"))
        except OSError:
            listing = ["<Ordner nicht lesbar>"]
        raise DockingError(
            f"{step} fehlgeschlagen: {cmd[0]} nicht gefunden. sys.executable={sys.executable}, "
            f"_SCRIPTS_DIR={_SCRIPTS_DIR}, gefundene mk_*-Dateien dort: {listing}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise DockingError(f"{step} fehlgeschlagen: {detail[-800:]}")
    return result


def _pdb_cache_path(pdb_id: str) -> Path:
    return PDB_CACHE_DIR / f"{pdb_id}.pdb"


_PDB_ID_RE = re.compile(r"^[0-9][A-Z0-9]{3}$")


def fetch_pdb(pdb_id: str) -> tuple[Path, str]:
    pdb_id = pdb_id.strip().upper()
    if not pdb_id:
        raise DockingError("PDB-ID ist leer.")
    if not _PDB_ID_RE.match(pdb_id):
        # Verhindert u.a. Path-Traversal über pdb_id (z.B. "../../foo") beim Aufbau
        # von _pdb_cache_path() -- echte PDB-IDs sind immer 4 Zeichen, Ziffer + alnum.
        raise DockingError(f"'{pdb_id}' ist keine gültige PDB-ID (4 Zeichen, z.B. 3PTB).")

    PDB_CACHE_DIR.mkdir(exist_ok=True)
    path = _pdb_cache_path(pdb_id)
    if not path.exists():
        resp = requests.get(f"{RCSB_FILES}/{pdb_id}.pdb", timeout=20)
        if resp.status_code != 200:
            raise DockingError(f"PDB-ID '{pdb_id}' wurde bei RCSB nicht gefunden.")
        path.write_text(resp.text, encoding="utf-8")

    protein_name = pdb_id
    try:
        meta = requests.get(f"{RCSB_DATA}/{pdb_id}", timeout=10)
        if meta.status_code == 200:
            protein_name = meta.json().get("struct", {}).get("title", pdb_id)
    except requests.RequestException:
        pass

    return path, protein_name


def _parse_ca_backbone(pdb_text: str) -> list[list[dict]]:
    chains: dict[str, list[dict]] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue
        if line[12:16].strip() != "CA":
            continue
        chain_id = line[21].strip() or "A"
        try:
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
        except ValueError:
            continue
        chains.setdefault(chain_id, []).append({"x": x, "y": y, "z": z})
    return list(chains.values())


def _find_reference_ligand(pdb_text: str) -> dict:
    groups: dict[tuple, list[tuple]] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("HETATM"):
            continue
        resname = line[17:20].strip()
        if resname in _IGNORED_HET_RESNAMES:
            continue
        chain_id = line[21].strip() or "A"
        resseq = line[22:26].strip()
        try:
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
        except ValueError:
            continue
        groups.setdefault((resname, chain_id, resseq), []).append((x, y, z))

    if not groups:
        raise DockingError(
            "Diese Struktur hat keinen erkennbaren Liganden (nur Wasser/Ionen/"
            "Kristallisationshilfsstoffe gefunden) — probier eine PDB-ID mit "
            "einem gebundenen Wirkstoff/Inhibitor, z. B. 3PTB."
        )

    best_key = max(groups, key=lambda k: len(groups[k]))
    atoms = groups[best_key]
    xs, ys, zs = zip(*atoms)

    center = {"x": (min(xs) + max(xs)) / 2, "y": (min(ys) + max(ys)) / 2, "z": (min(zs) + max(zs)) / 2}
    size = {
        "x": max(max(xs) - min(xs) + 2 * _BOX_PADDING, _MIN_BOX_SIZE),
        "y": max(max(ys) - min(ys) + 2 * _BOX_PADDING, _MIN_BOX_SIZE),
        "z": max(max(zs) - min(zs) + 2 * _BOX_PADDING, _MIN_BOX_SIZE),
    }
    return {"resname": best_key[0], "center": center, "size": size}


def _group_hetero_ligands(pdb_text: str) -> dict[tuple, list[str]]:
    """Wie _find_reference_ligand(), aber gibt die rohen HETATM-Zeilen pro
    Nicht-Ignorierter Gruppe zurück statt nur die Box -- gebraucht von
    pdb_ligand(), um daraus tatsächlich Atome/Bindungen zu bauen."""
    groups: dict[tuple, list[str]] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("HETATM"):
            continue
        if line[16] not in (" ", "A"):  # AltLoc: nur die primäre Konformation
            continue
        resname = line[17:20].strip()
        if resname in _IGNORED_HET_RESNAMES:
            continue
        chain_id = line[21].strip() or "A"
        resseq = line[22:26].strip()
        groups.setdefault((resname, chain_id, resseq), []).append(line)
    return groups


def _protein_chain_lines(pdb_text: str) -> dict[str, list[str]]:
    chains: dict[str, list[str]] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue
        if line[16] not in (" ", "A"):
            continue
        chain_id = line[21].strip() or "A"
        chains.setdefault(chain_id, []).append(line)
    return chains


def _residue_count(lines: list[str]) -> int:
    return len({(line[22:26].strip(), line[26]) for line in lines})


def _find_ligand_lines(
    pdb_text: str, hetero_code: str | None, chain_ids: list[str] | None = None
) -> tuple[str, list[str], bool]:
    """Wählt die Atomzeilen des Liganden, den pdb_ligand() anzeigen soll.

    Drei Fälle, in dieser Reihenfolge geprüft:
    0. Explizite Ketten-Auswahl (chain_ids): überspringt jede Heuristik --
       gebraucht, wenn der Ligand aus mehreren Ketten besteht (z.B. Insulin:
       A- und B-Kette, über 3 Disulfidbrücken verbunden) oder wenn die
       Längen-Heuristik unten fehlschlagen würde, weil eine noch kürzere,
       aber gar nicht zum Liganden gehörende Kette existiert (bei 4OGA ist
       Kette F ein 16 Reste kurzes Rezeptor-eigenes Peptid, das ohne diese
       Override fälschlich als "der Ligand" gewählt würde -- kürzer als
       Insulins A-/B-Kette mit je 21 Resten).
    1. Peptid-Ligand-Heuristik: gibt es (mind.) eine Protein-Kette in Peptid-
       Wirkstoff-Länge (siehe _PEPTIDE_LIGAND_MAX_RESIDUES) UND eine deutlich
       längere Kette (das vermutliche Zielprotein), wird die kürzeste solche
       Kette als Ligand behandelt -- Fall Semaglutid an seinem Rezeptor.
       Kommt VOR dem HETATM-Fall, weil manche solcher Strukturen zusätzlich
       einen kleinen, für den Liganden irrelevanten Kristallisationszusatz
       als HETATM neben der Peptidkette haben (z.B. ein PEG-Molekül in
       4ZGM) -- ohne diese Reihenfolge würde der falsche, viel kleinere
       "Ligand" gewählt.
    2. Klein-Molekül-HETATM: wie beim Docking (_find_reference_ligand) die
       größte Nicht-Ignorierte HETATM-Gruppe, optional per hetero_code
       (PDB-Chemical-Component-ID, z.B. "BEN") gezielt ausgewählt.

    Gibt (label, Zeilen, ist_peptid_fallback) zurück.
    """
    if chain_ids:
        wanted = {c.strip().upper() for c in chain_ids}
        chains = _protein_chain_lines(pdb_text)
        missing = wanted - chains.keys()
        if missing:
            raise DockingError(f"Kette(n) {', '.join(sorted(missing))} nicht in dieser Struktur gefunden.")
        lines = [line for c in sorted(wanted) for line in chains[c]]
        return f"Peptid, Kette {'+'.join(sorted(wanted))}", lines, True

    if not hetero_code:
        chains = _protein_chain_lines(pdb_text)
        chain_sizes = {c: _residue_count(lines) for c, lines in chains.items()}
        peptide_chains = {c: n for c, n in chain_sizes.items() if 5 <= n <= _PEPTIDE_LIGAND_MAX_RESIDUES}
        receptor_chains = {c: n for c, n in chain_sizes.items() if n > _PEPTIDE_LIGAND_MAX_RESIDUES}
        if peptide_chains and receptor_chains:
            ligand_chain = min(peptide_chains, key=peptide_chains.get)
            return f"Peptid, Kette {ligand_chain}", chains[ligand_chain], True

    hetero_groups = _group_hetero_ligands(pdb_text)

    if hetero_code:
        code = hetero_code.strip().upper()
        matches = {k: v for k, v in hetero_groups.items() if k[0] == code}
        if not matches:
            raise DockingError(f"Kein HETATM-Rest '{code}' in dieser Struktur gefunden.")
        best_key = max(matches, key=lambda k: len(matches[k]))
        return best_key[0], matches[best_key], False

    if hetero_groups:
        best_key = max(hetero_groups, key=lambda k: len(hetero_groups[k]))
        return best_key[0], hetero_groups[best_key], False

    raise DockingError(
        "Diese Struktur hat weder einen erkennbaren Klein-Molekül-Liganden (nur "
        "Wasser/Ionen/Kristallisationshilfsstoffe gefunden) noch eine deutlich "
        "kürzere Kette, die sich als Peptid-Ligand deuten ließe."
    )


_PT = Chem.GetPeriodicTable()


def _hill_formula(elements: list[str]) -> str:
    from collections import Counter

    counts = Counter(elements)
    parts = []
    if "C" in counts:
        parts.append(("C", counts.pop("C")))
        if "H" in counts:
            parts.append(("H", counts.pop("H")))
    for el in sorted(counts):
        parts.append((el, counts[el]))
    return "".join(f"{el}{n if n > 1 else ''}" for el, n in parts)


def _atoms_molweight(elements: list[str]) -> float:
    return round(sum(_PT.GetAtomicWeight(el) for el in elements), 2)


def _lookup_chemcomp_name(resname: str) -> str | None:
    try:
        resp = requests.get(f"{RCSB_CHEMCOMP}/{resname}", timeout=10)
        if resp.status_code == 200:
            name = resp.json().get("chem_comp", {}).get("name")
            if name:
                return name.title()
    except requests.RequestException:
        pass
    return None


def pdb_ligand(pdb_id: str, hetero_code: str | None = None, chain_ids: list[str] | None = None) -> dict:
    """Lädt eine PDB-Struktur und zeigt den darin gefundenen Liganden als
    eigenständiges Molekül -- ganz ohne Docking-Rechnung, im gleichen
    Antwortformat wie chem.resolve() (atoms/bonds/facts/common_name), damit
    das Frontend nichts Neues dafür bauen muss.

    Bewusst KEINE Wasserstoffe ergänzt (anders als chem._build_structure()):
    das wären erfundene H-Positionen auf einer fremden, real gemessenen
    Geometrie. Aus dem gleichen Grund auch keine RDKit-Deskriptoren wie LogP/
    TPSA/H-Brücken -- die bräuchten korrekte Valenzen inkl. H, die wir hier
    nicht haben. Nur Summenformel und Molmasse werden direkt aus den
    vorhandenen Atomen berechnet (ehrlich, aber ohne H in beiden Werten).
    Bindungsordnung wird per RDKit-Abstandsheuristik geraten (ConnectTheDots)
    -- für die reine 3D-Darstellung (Kugel-Stab zeigt Bindungen ohnehin ohne
    Doppelbindungs-Unterscheidung) ausreichend, aber nicht chemisch bewiesen.
    """
    pdb_path, _protein_name = fetch_pdb(pdb_id)
    pdb_text = pdb_path.read_text(encoding="utf-8")

    label, lines, is_peptide = _find_ligand_lines(pdb_text, hetero_code, chain_ids)

    block = "\n".join(lines) + "\nEND\n"
    mol = Chem.MolFromPDBBlock(block, sanitize=False, removeHs=False, proximityBonding=True)
    if mol is None or mol.GetNumAtoms() == 0:
        raise DockingError(f"Konnte den Liganden aus '{pdb_id}' nicht als Molekül lesen.")

    conformer = mol.GetConformer()
    atoms = []
    elements = []
    for atom in mol.GetAtoms():
        pos = conformer.GetAtomPosition(atom.GetIdx())
        elements.append(atom.GetSymbol())
        atoms.append({"element": atom.GetSymbol(), "x": pos.x, "y": pos.y, "z": pos.z})
    bonds = [{"a": b.GetBeginAtomIdx(), "b": b.GetEndAtomIdx()} for b in mol.GetBonds()]

    facts = {
        "formula": _hill_formula(elements),
        "molweight": _atoms_molweight(elements),
        "logp": "–",
        "tpsa": "–",
        "h_donors": "–",
        "h_acceptors": "–",
        "rotatable_bonds": "–",
    }

    note = (
        "Reale, unveränderte Kristallstruktur -- keine Wasserstoffe enthalten "
        "(Summenformel/Molmasse deshalb ohne H), Bindungsordnung aus 3D-Abständen "
        "geschätzt, weitere Fakten (LogP, TPSA, H-Brücken) deshalb nicht verfügbar."
    )
    if is_peptide:
        common_name = f"Peptid-Ligand aus {pdb_id.upper()} ({label.split(', ')[1]})"
        if chain_ids:
            note += (
                " Ligand wurde über eine fest angegebene Kettenauswahl geladen "
                "(nicht über die Längen-Heuristik) -- z.B. nötig, wenn der Ligand "
                "aus mehreren Ketten besteht (wie Insulins A- und B-Kette)."
            )
        else:
            note += (
                " Kein Klein-Molekül-Ligand gefunden -- die kürzeste Protein-Kette wurde "
                "als vermutlicher Peptid-Wirkstoff angezeigt (Längen-Heuristik, keine "
                "chemische Bestätigung der Identität)."
            )
    else:
        common_name = _lookup_chemcomp_name(label) or label

    return {
        "atoms": atoms,
        "bonds": bonds,
        "facts": facts,
        "common_name": common_name,
        "iupac_name": None,
        "note": note,
    }


def prepare_receptor(pdb_path: Path) -> Path:
    basename = pdb_path.with_suffix("")
    pdbqt_path = basename.with_suffix(".pdbqt")
    if pdbqt_path.exists():
        return pdbqt_path

    _run([
        str(MEEKO_RECEPTOR),
        "--read_pdb", str(pdb_path),
        "-o", str(basename),
        "-p",
        "--delete_bad_res",
    ], "Rezeptor-Vorbereitung")

    if pdbqt_path.exists():
        return pdbqt_path
    rigid_path = Path(f"{basename}_rigid.pdbqt")
    if rigid_path.exists():
        return rigid_path
    raise DockingError("Rezeptor-Vorbereitung hat keine PDBQT-Datei erzeugt.")


def prepare_ligand(mol, workdir: Path) -> Path:
    sdf_path = workdir / "ligand.sdf"
    pdbqt_path = workdir / "ligand.pdbqt"

    writer = Chem.SDWriter(str(sdf_path))
    writer.write(mol)
    writer.close()

    _run([str(MEEKO_LIGAND), "-i", str(sdf_path), "-o", str(pdbqt_path)], "Liganden-Vorbereitung")

    if not pdbqt_path.exists():
        raise DockingError("Liganden-Vorbereitung hat keine PDBQT-Datei erzeugt.")
    return pdbqt_path


def _parse_affinities(vina_stdout: str) -> list[float]:
    affinities = []
    for line in vina_stdout.splitlines():
        m = re.match(r"\s*\d+\s+(-?\d+\.\d+)", line)
        if m:
            affinities.append(float(m.group(1)))
    return affinities


def run_vina(receptor_pdbqt: Path, ligand_pdbqt: Path, box: dict, out_path: Path) -> list[float]:
    if VINA_BINARY.exists():
        result = _run([
            str(VINA_BINARY),
            "--receptor", str(receptor_pdbqt),
            "--ligand", str(ligand_pdbqt),
            "--center_x", str(box["center"]["x"]),
            "--center_y", str(box["center"]["y"]),
            "--center_z", str(box["center"]["z"]),
            "--size_x", str(box["size"]["x"]),
            "--size_y", str(box["size"]["y"]),
            "--size_z", str(box["size"]["z"]),
            "--out", str(out_path),
            "--exhaustiveness", "8",
        ], "Docking (Vina)")
        return _parse_affinities(result.stdout)

    return _run_vina_python(receptor_pdbqt, ligand_pdbqt, box, out_path)


def _run_vina_python(receptor_pdbqt: Path, ligand_pdbqt: Path, box: dict, out_path: Path) -> list[float]:
    """Fallback für Umgebungen ohne backend/tools/vina.exe (Linux/Docker, siehe
    Dockerfile + requirements.txt) -- nutzt Vinas offizielle Python-Bindings
    (pip-Paket "vina", hat anders als unter Windows echte manylinux-Wheels).
    Gleiche Parameter/Exhaustiveness wie der Windows-Subprocess-Pfad oben, damit
    die Ergebnisse zwischen beiden Plattformen vergleichbar bleiben."""
    try:
        from vina import Vina
    except ImportError as exc:
        raise DockingError(
            "Kein Vina verfügbar -- weder backend/tools/vina.exe (Windows) noch "
            "das pip-Paket 'vina' (Linux, siehe requirements.txt) ist installiert."
        ) from exc

    v = Vina(sf_name="vina", verbosity=0)
    v.set_receptor(str(receptor_pdbqt))
    v.set_ligand_from_file(str(ligand_pdbqt))
    v.compute_vina_maps(
        center=[box["center"]["x"], box["center"]["y"], box["center"]["z"]],
        box_size=[box["size"]["x"], box["size"]["y"], box["size"]["z"]],
    )
    v.dock(exhaustiveness=8, n_poses=9)
    v.write_poses(str(out_path), n_poses=9, overwrite=True)
    # energies() liefert pro Pose eine Zeile, Spalte 0 ist die Gesamt-Affinität
    # (kcal/mol) -- exakt der Wert, den der Windows-Pfad oben per Regex aus
    # Vinas Konsolenausgabe zieht.
    return [float(row[0]) for row in v.energies(n_poses=9)]


def _export_poses(out_pdbqt: Path, workdir: Path) -> list[tuple[list[dict], list[dict]]]:
    sdf_path = workdir / "poses.sdf"
    _run([str(MEEKO_EXPORT), str(out_pdbqt), "-s", str(sdf_path)], "Posen-Export")

    supplier = Chem.SDMolSupplier(str(sdf_path), removeHs=False)
    poses = []
    for mol in supplier:
        if mol is None:
            continue
        conformer = mol.GetConformer()
        atoms = []
        for atom in mol.GetAtoms():
            pos = conformer.GetAtomPosition(atom.GetIdx())
            atoms.append({"element": atom.GetSymbol(), "x": pos.x, "y": pos.y, "z": pos.z})
        bonds = [{"a": b.GetBeginAtomIdx(), "b": b.GetEndAtomIdx()} for b in mol.GetBonds()]
        poses.append((atoms, bonds))
    return poses


def dock(pdb_id: str, ligand_query: str) -> dict:
    pdb_path, protein_name = fetch_pdb(pdb_id)
    pdb_text = pdb_path.read_text(encoding="utf-8")

    chains = _parse_ca_backbone(pdb_text)
    if not chains:
        raise DockingError("Konnte kein Protein-Rückgrat (Cα-Atome) in dieser Struktur finden.")

    box_info = _find_reference_ligand(pdb_text)

    try:
        ligand_info, _note = chem._resolve_to_names(ligand_query)
    except chem.ResolveError as e:
        raise DockingError(f"Ligand nicht auflösbar: {e}")

    mol = Chem.MolFromSmiles(ligand_info.smiles)
    if mol is None:
        raise DockingError(f"Liganden-SMILES konnte nicht gelesen werden: {ligand_info.smiles}")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) != 0:
        raise DockingError("Konnte keine 3D-Startstruktur für den Liganden berechnen.")
    AllChem.MMFFOptimizeMolecule(mol)

    receptor_pdbqt = prepare_receptor(pdb_path)

    pdb_id_upper = pdb_path.stem
    workdir = PDB_CACHE_DIR / f"{pdb_id_upper}_dock"
    workdir.mkdir(exist_ok=True)
    ligand_pdbqt = prepare_ligand(mol, workdir)

    out_pdbqt = workdir / "out.pdbqt"
    affinities = run_vina(receptor_pdbqt, ligand_pdbqt, box_info, out_pdbqt)
    poses = _export_poses(out_pdbqt, workdir)

    if not poses:
        raise DockingError("Vina hat keine Docking-Posen erzeugt.")

    best_atoms, best_bonds = poses[0]

    return {
        "protein_name": protein_name,
        "chains": chains,
        "ligand": {"atoms": best_atoms, "bonds": best_bonds},
        "pocket_center": box_info["center"],
        "pocket_size": box_info["size"],
        "reference_ligand": box_info["resname"],
        "affinities": affinities[:3],
    }


if __name__ == "__main__":
    result = dock("3PTB", "benzamidine")
    print("protein:", result["protein_name"])
    print("chains (CA pro Kette):", [len(c) for c in result["chains"]])
    print("referenz-ligand:", result["reference_ligand"])
    print("pocket_center:", result["pocket_center"])
    print("affinities (kcal/mol):", result["affinities"])
    print("ligand-pose atoms:", len(result["ligand"]["atoms"]), "bonds:", len(result["ligand"]["bonds"]))

    print()
    for pdb_id in ["3PTB", "4ZGM", "7KI0"]:
        print(f"--- pdb_ligand({pdb_id!r}) ---")
        try:
            lig = pdb_ligand(pdb_id)
            print("common_name:", lig["common_name"])
            print("formula:", lig["facts"]["formula"], "| molweight:", lig["facts"]["molweight"])
            print("atoms:", len(lig["atoms"]), "bonds:", len(lig["bonds"]))
            print("note:", lig["note"])
        except DockingError as e:
            print("ERROR:", e)
        print()
