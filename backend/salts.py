"""Salzformel-Löser: aus einem Kation und einem Anion (Säurerest oder einfaches
Nichtmetall-Ion) die korrekt ladungsausgeglichene Verhältnisformel berechnen --
die "Kreuzregel" aus dem Chemieunterricht (Ionenverbindungen). Anders als beim
Rest der App gibt es hier keine PubChem-Anfrage: die Formel wird direkt aus
den bekannten Ionenladungen berechnet, die 3D-Ansicht baut RDKit lokal aus
Ionen-SMILES zusammen (siehe _embed_ion/_layout_ions unten -- gleiches Muster
wie equation.py::_embed_species/_layout_instances für mehrere nebeneinander
platzierte Moleküle, hier für mehrere Ionen-Instanzen)."""

from dataclasses import dataclass, field
from math import gcd

from rdkit import Chem
from rdkit.Chem import AllChem

import docking  # nur für _hill_formula/_atoms_molweight -- reine Zahlenhilfen, kein Docking

_FRAGMENT_GAP = 2.5  # Å Abstand zwischen den einzelnen Ionen in der 3D-Ansicht


class SaltError(Exception):
    pass


@dataclass
class _Ion:
    label: str  # deutscher Anzeigename, z.B. "Calcium", "Sulfat"
    symbol: str  # Formel-Baustein in der "*"-Tiefstellungs-Konvention (siehe app.js formatSubscripts), z.B. "SO*4"
    charge: int  # positiv fürs Kation, negativ fürs Anion
    smiles: str  # Ionen-SMILES mit expliziter Ladung, für die 3D-Ansicht
    atom_counts: dict = field(default_factory=dict)  # Element -> Anzahl in diesem einen Ion
    polyatomic: bool = False  # braucht Klammern in der Formel, wenn die Anzahl >1 ist


CATIONS: dict[str, _Ion] = {
    "natrium": _Ion("Natrium", "Na", 1, "[Na+]", {"Na": 1}),
    "kalium": _Ion("Kalium", "K", 1, "[K+]", {"K": 1}),
    "lithium": _Ion("Lithium", "Li", 1, "[Li+]", {"Li": 1}),
    "silber": _Ion("Silber", "Ag", 1, "[Ag+]", {"Ag": 1}),
    "ammonium": _Ion("Ammonium", "NH*4", 1, "[NH4+]", {"N": 1, "H": 4}, polyatomic=True),
    "calcium": _Ion("Calcium", "Ca", 2, "[Ca+2]", {"Ca": 1}),
    "magnesium": _Ion("Magnesium", "Mg", 2, "[Mg+2]", {"Mg": 1}),
    "zink": _Ion("Zink", "Zn", 2, "[Zn+2]", {"Zn": 1}),
    "kupfer(ii)": _Ion("Kupfer(II)", "Cu", 2, "[Cu+2]", {"Cu": 1}),
    "eisen(ii)": _Ion("Eisen(II)", "Fe", 2, "[Fe+2]", {"Fe": 1}),
    "blei(ii)": _Ion("Blei(II)", "Pb", 2, "[Pb+2]", {"Pb": 1}),
    "barium": _Ion("Barium", "Ba", 2, "[Ba+2]", {"Ba": 1}),
    "aluminium": _Ion("Aluminium", "Al", 3, "[Al+3]", {"Al": 1}),
    "eisen(iii)": _Ion("Eisen(III)", "Fe", 3, "[Fe+3]", {"Fe": 1}),
    "chrom(iii)": _Ion("Chrom(III)", "Cr", 3, "[Cr+3]", {"Cr": 1}),
}

ANIONS: dict[str, _Ion] = {
    "chlorid": _Ion("Chlorid", "Cl", -1, "[Cl-]", {"Cl": 1}),
    "bromid": _Ion("Bromid", "Br", -1, "[Br-]", {"Br": 1}),
    "iodid": _Ion("Iodid", "I", -1, "[I-]", {"I": 1}),
    "fluorid": _Ion("Fluorid", "F", -1, "[F-]", {"F": 1}),
    "oxid": _Ion("Oxid", "O", -2, "[O-2]", {"O": 1}),
    "sulfid": _Ion("Sulfid", "S", -2, "[S-2]", {"S": 1}),
    "hydroxid": _Ion("Hydroxid", "OH", -1, "[OH-]", {"O": 1, "H": 1}, polyatomic=True),
    "nitrat": _Ion("Nitrat", "NO*3", -1, "[O-][N+](=O)[O-]", {"N": 1, "O": 3}, polyatomic=True),
    "nitrit": _Ion("Nitrit", "NO*2", -1, "O=N[O-]", {"N": 1, "O": 2}, polyatomic=True),
    "sulfat": _Ion("Sulfat", "SO*4", -2, "[O-]S(=O)(=O)[O-]", {"S": 1, "O": 4}, polyatomic=True),
    "sulfit": _Ion("Sulfit", "SO*3", -2, "O=S([O-])[O-]", {"S": 1, "O": 3}, polyatomic=True),
    "carbonat": _Ion("Carbonat", "CO*3", -2, "[O-]C(=O)[O-]", {"C": 1, "O": 3}, polyatomic=True),
    "hydrogencarbonat": _Ion(
        "Hydrogencarbonat", "HCO*3", -1, "OC(=O)[O-]", {"H": 1, "C": 1, "O": 3}, polyatomic=True
    ),
    "phosphat": _Ion("Phosphat", "PO*4", -3, "[O-]P(=O)([O-])[O-]", {"P": 1, "O": 4}, polyatomic=True),
    "hydrogenphosphat": _Ion(
        "Hydrogenphosphat", "HPO*4", -2, "OP(=O)([O-])[O-]", {"H": 1, "P": 1, "O": 4}, polyatomic=True
    ),
    "dihydrogenphosphat": _Ion(
        "Dihydrogenphosphat", "H*2PO*4", -1, "OP(=O)(O)[O-]", {"H": 2, "P": 1, "O": 4}, polyatomic=True
    ),
    "acetat": _Ion("Acetat", "CH*3COO", -1, "CC(=O)[O-]", {"C": 2, "H": 3, "O": 2}, polyatomic=True),
    "cyanid": _Ion("Cyanid", "CN", -1, "[C-]#N", {"C": 1, "N": 1}, polyatomic=True),
}


def list_ions() -> dict:
    return {
        "cations": [{"key": k, "label": ion.label} for k, ion in CATIONS.items()],
        "anions": [{"key": k, "label": ion.label} for k, ion in ANIONS.items()],
    }


def _format_part(symbol: str, count: int, polyatomic: bool) -> str:
    if count == 1:
        return symbol
    if polyatomic:
        return f"({symbol})*{count}"
    return f"{symbol}*{count}"


def _embed_ion(smiles: str):
    """Baut eine einzelne Ionen-Instanz in 3D -- eigene, kleine Kopie statt
    chem._build_structure(), weil die dortige Schweratom-/Facts-Logik für
    Ionen nicht passt (siehe Moduldocstring) und equation.py denselben Ansatz
    schon für einzelne Spezies-Instanzen verwendet (_embed_species dort)."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) != 0:
        return None
    try:
        AllChem.MMFFOptimizeMolecule(mol)
    except Exception:
        pass  # manche Ionen (z.B. Al3+) haben kein MMFF-Atomtyp -- unoptimierte Koordinaten reichen hier

    conformer = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        pos = conformer.GetAtomPosition(atom.GetIdx())
        atoms.append({"element": atom.GetSymbol(), "x": pos.x, "y": pos.y, "z": pos.z})
    bonds = [{"a": b.GetBeginAtomIdx(), "b": b.GetEndAtomIdx()} for b in mol.GetBonds()]
    return atoms, bonds


def _layout_ions(smiles_list: list[str]) -> tuple[list[dict], list[dict]]:
    """Reiht jede Ionen-Instanz einzeln embedded nebeneinander auf (gleiches
    Nebeneinander-Layout wie equation.py::_layout_instances) -- sonst würde
    ein einzelnes Multi-Fragment-SMILES alle Ionen ungefähr am Ursprung
    übereinander platzieren."""
    all_atoms: list[dict] = []
    all_bonds: list[dict] = []
    x_offset = 0.0

    for smiles in smiles_list:
        embedded = _embed_ion(smiles)
        if embedded is None:
            continue
        atoms, bonds = embedded
        if not atoms:
            continue
        base_index = len(all_atoms)
        xs = [a["x"] for a in atoms]
        shift = x_offset - min(xs)

        for atom in atoms:
            all_atoms.append({
                "element": atom["element"],
                "x": atom["x"] + shift,
                "y": atom["y"],
                "z": atom["z"],
                "charge": 0.0,  # kein Gasteiger-Ladungsmodus für Ionen -- Formalladung steckt schon in der Chemie
            })
        for b in bonds:
            all_bonds.append({"a": base_index + b["a"], "b": base_index + b["b"]})

        x_offset += (max(xs) - min(xs)) + _FRAGMENT_GAP

    return all_atoms, all_bonds


def build_salt(cation_key: str, anion_key: str) -> dict:
    cation = CATIONS.get((cation_key or "").strip().lower())
    anion = ANIONS.get((anion_key or "").strip().lower())
    if cation is None:
        raise SaltError(f"Unbekanntes Kation: '{cation_key}'.")
    if anion is None:
        raise SaltError(f"Unbekanntes Anion: '{anion_key}'.")

    m = cation.charge
    n = -anion.charge  # anion.charge ist negativ gespeichert, n wird positiv
    g = gcd(m, n)
    cation_count = n // g
    anion_count = m // g

    formula_label = _format_part(cation.symbol, cation_count, cation.polyatomic) + _format_part(
        anion.symbol, anion_count, anion.polyatomic
    )

    name = (
        f"{cation.label}-{anion.label.lower()}"
        if "(" in cation.label
        else f"{cation.label}{anion.label.lower()}"
    )

    elements: list[str] = []
    for el, n_atoms in cation.atom_counts.items():
        elements += [el] * (n_atoms * cation_count)
    for el, n_atoms in anion.atom_counts.items():
        elements += [el] * (n_atoms * anion_count)

    facts = {
        "formula": docking._hill_formula(elements),
        "molweight": docking._atoms_molweight(elements),
        "logp": "–",
        "tpsa": "–",
        "h_donors": "–",
        "h_acceptors": "–",
        "rotatable_bonds": "–",
    }

    smiles_list = [cation.smiles] * cation_count + [anion.smiles] * anion_count
    atoms, bonds = _layout_ions(smiles_list)

    note = (
        f"Formel per Kreuzregel berechnet: {cation.label} ({m:+d}) mit {anion.label} ({-n:+d}) "
        f"→ Verhältnis {cation_count}:{anion_count}. Als lose Ionenpaare dargestellt, keine "
        "echte Kristallstruktur -- ein reales Salz bildet ein Ionengitter aus sehr vielen "
        "Ionen, kein einzelnes Molekül."
    )
    if not atoms:
        note += " 3D-Ansicht konnte für diese Kombination nicht berechnet werden, nur die Formel."

    return {
        "atoms": atoms,
        "bonds": bonds,
        "facts": facts,
        "common_name": name,
        "iupac_name": None,
        "note": note,
        "formula_label": formula_label,
    }


if __name__ == "__main__":
    for cation_key, anion_key in [
        ("calcium", "sulfat"),
        ("aluminium", "sulfat"),
        ("natrium", "phosphat"),
        ("eisen(iii)", "chlorid"),
        ("magnesium", "oxid"),
        ("ammonium", "nitrat"),
    ]:
        data = build_salt(cation_key, anion_key)
        print(f"{cation_key} + {anion_key} -> {data['formula_label'].replace('*', '')}  "
              f"({data['common_name']}), Summenformel {data['facts']['formula']}, "
              f"{data['facts']['molweight']} g/mol, {len(data['atoms'])} Atome")
