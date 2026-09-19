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
from pathlib import Path

import requests
from rdkit import Chem
from rdkit.Chem import AllChem

import chem

BACKEND_DIR = Path(__file__).parent
PDB_CACHE_DIR = BACKEND_DIR / "pdb_cache"
VINA_BINARY = BACKEND_DIR / "tools" / "vina.exe"
VENV_SCRIPTS = BACKEND_DIR / ".venv" / "Scripts"
MEEKO_RECEPTOR = VENV_SCRIPTS / "mk_prepare_receptor.exe"
MEEKO_LIGAND = VENV_SCRIPTS / "mk_prepare_ligand.exe"
MEEKO_EXPORT = VENV_SCRIPTS / "mk_export.exe"

RCSB_FILES = "https://files.rcsb.org/download"
RCSB_DATA = "https://data.rcsb.org/rest/v1/core/entry"

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
    result = subprocess.run(cmd, capture_output=True, text=True)
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
    if not VINA_BINARY.exists():
        raise DockingError(f"Vina-Programm fehlt unter {VINA_BINARY}.")

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
