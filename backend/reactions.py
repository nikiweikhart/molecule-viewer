"""Handkuratierte Beispiel-Reaktionen für die Reaktions-Animation.

Kein allgemeiner Reaktions-Löser — Reaktanten/Produkte sind von Hand als
atom-gemappte SMILES hinterlegt (z.B. [CH3:1]...), damit die Zuordnung
"welches Atom wird zu welchem" exakt feststeht, statt sich auf RDKits
Reaktions-Engine zu verlassen. Wasserstoffe werden bewusst nicht animiert
(Skelett-Stil) — siehe docs/stand.md für die Begründung.

Weitere Reaktion ergänzen: einfach einen neuen Eintrag in REACTIONS anhängen,
mit passenden Atom-Map-Nummern in reactants_smiles/products_smiles (jede
Map-Nummer, die auf beiden Seiten vorkommt, markiert ein Atom, das erhalten
bleibt und morpht).
"""

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import AllChem

REACTIONS = [
    {
        "id": "esterification",
        "label": "Veresterung — Essigsäure + Ethanol → Ethylacetat + Wasser",
        "reactants_smiles": "[CH3:1][C:2](=[O:3])[OH:4].[CH3:5][CH2:6][OH:7]",
        "products_smiles": "[CH3:1][C:2](=[O:3])[O:7][CH2:6][CH3:5].[OH2:4]",
    },
]

_FRAGMENT_GAP = 3.5  # Å Abstand zwischen nebeneinander platzierten Fragmenten


def _embed_fragment_heavy_atoms(frag_mol):
    """Bettet ein Fragment in 3D ein und gibt (map_num -> {element,x,y,z}) zurück."""
    mol_h = Chem.AddHs(frag_mol)
    embed_result = AllChem.EmbedMolecule(mol_h, AllChem.ETKDGv3())
    if embed_result != 0:
        raise ValueError("Konnte 3D-Struktur für Reaktions-Fragment nicht berechnen.")
    AllChem.MMFFOptimizeMolecule(mol_h)

    conformer = mol_h.GetConformer()
    atoms_by_map = {}
    for atom in mol_h.GetAtoms():
        if atom.GetSymbol() == "H":
            continue
        map_num = atom.GetAtomMapNum()
        pos = conformer.GetAtomPosition(atom.GetIdx())
        atoms_by_map[map_num] = {"element": atom.GetSymbol(), "x": pos.x, "y": pos.y, "z": pos.z}

    # Bindungen zwischen Schweratomen, referenziert über Map-Nummern.
    bonds = []
    for bond in mol_h.GetBonds():
        a, b = bond.GetBeginAtom(), bond.GetEndAtom()
        if a.GetSymbol() == "H" or b.GetSymbol() == "H":
            continue
        bonds.append((a.GetAtomMapNum(), b.GetAtomMapNum()))

    return atoms_by_map, bonds


def _layout_side(smiles: str):
    """Parst Multi-Komponenten-SMILES, bettet jedes Fragment ein und reiht sie nebeneinander auf.

    Gibt (atoms_by_map, bonds) zurück — atoms_by_map: {map_num: {element,x,y,z}} über alle
    Fragmente, mit World-Space-Positionen nach dem Nebeneinander-Layout.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Reaktions-SMILES konnte nicht gelesen werden: {smiles}")

    frag_mols = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)

    all_atoms = {}
    all_bonds = []
    x_offset = 0.0

    for frag in frag_mols:
        atoms_by_map, bonds = _embed_fragment_heavy_atoms(frag)
        if not atoms_by_map:
            continue

        xs = [a["x"] for a in atoms_by_map.values()]
        frag_width = max(xs) - min(xs)
        shift = x_offset - min(xs)

        for map_num, atom in atoms_by_map.items():
            all_atoms[map_num] = {
                "element": atom["element"],
                "x": atom["x"] + shift,
                "y": atom["y"],
                "z": atom["z"],
            }
        all_bonds.extend(bonds)

        x_offset += frag_width + _FRAGMENT_GAP

    return all_atoms, all_bonds


def build_reaction(entry: dict) -> dict:
    start_atoms_by_map, start_bonds_map = _layout_side(entry["reactants_smiles"])
    end_atoms_by_map, end_bonds_map = _layout_side(entry["products_smiles"])

    # Feste Reihenfolge für die Start-Atome (Index i im Ergebnis = i-tes Element dieser Liste).
    start_map_nums = sorted(start_atoms_by_map.keys())
    start_index_of = {m: i for i, m in enumerate(start_map_nums)}
    end_index_of = {m: i for i, m in enumerate(sorted(end_atoms_by_map.keys()))}

    start_atoms = [start_atoms_by_map[m] for m in start_map_nums]
    end_atoms = [end_atoms_by_map[sorted(end_atoms_by_map.keys())[i]] for i in range(len(end_atoms_by_map))]

    correspondence = []
    for m in start_map_nums:
        if m in end_index_of:
            correspondence.append([start_index_of[m], end_index_of[m]])

    def to_start_idx_pair(map_a, map_b):
        return [start_index_of[map_a], start_index_of[map_b]]

    def to_end_idx_pair(map_a, map_b):
        return [end_index_of[map_a], end_index_of[map_b]]

    start_bond_set = {tuple(sorted((a, b))) for a, b in start_bonds_map}
    end_bond_set = {tuple(sorted((a, b))) for a, b in end_bonds_map}

    persistent_bonds = [to_start_idx_pair(a, b) for a, b in start_bond_set & end_bond_set]
    broken_bonds = [to_start_idx_pair(a, b) for a, b in start_bond_set - end_bond_set]
    # Neu geformte Bindungen: als Start-Indizes ausgedrückt (über die Korrespondenz), damit das
    # Frontend sie genauso wie die anderen über die interpolierten Positionen zeichnen kann.
    end_to_start = {end_index_of[m]: start_index_of[m] for m in start_map_nums if m in end_index_of}
    formed_bonds = []
    for a, b in end_bond_set - start_bond_set:
        ia, ib = end_index_of[a], end_index_of[b]
        if ia in end_to_start and ib in end_to_start:
            formed_bonds.append([end_to_start[ia], end_to_start[ib]])

    return {
        "label": entry["label"],
        "start": {"atoms": start_atoms},
        "end": {"atoms": end_atoms},
        "correspondence": correspondence,
        "persistent_bonds": persistent_bonds,
        "broken_bonds": broken_bonds,
        "formed_bonds": formed_bonds,
    }


def list_reactions():
    return [{"id": r["id"], "label": r["label"]} for r in REACTIONS]


def get_reaction(reaction_id: str) -> dict | None:
    for entry in REACTIONS:
        if entry["id"] == reaction_id:
            return build_reaction(entry)
    return None


if __name__ == "__main__":
    for entry in REACTIONS:
        print(f"--- {entry['id']} ---")
        data = build_reaction(entry)
        print("start atoms:", len(data["start"]["atoms"]))
        print("end atoms:", len(data["end"]["atoms"]))
        print("correspondence:", data["correspondence"])
        print("persistent_bonds:", data["persistent_bonds"])
        print("broken_bonds:", data["broken_bonds"])
        print("formed_bonds:", data["formed_bonds"])
