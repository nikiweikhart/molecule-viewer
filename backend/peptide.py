"""Kleine Peptide (bis ~15 Aminosäuren) direkt aus dem Ein-Buchstaben-
Sequenzcode als angenäherte 3D-Struktur anzeigen -- ohne PubChem-Namensauflösung
(für Peptide unzuverlässig, siehe docs/stand.md) und ohne echtes Protein-Folding
(Boltz-2 o.ä. -- bewusst außen vor, eigenes späteres Vorhaben). Auch nicht die
Semaglutid/Ozempic-Größenordnung (31 Reste, nicht-natürliche Aminosäuren,
Fettsäure-Linker) -- die läuft weiterhin über echte Kristallstrukturen
(docking.pdb_ligand()), nicht über dieses Modul.

RDKit baut die Sequenz direkt über Chem.MolFromSequence() zu einem Molekül --
kein Netzwerk-Aufruf nötig, im Gegensatz zur normalen Namensauflösung in
chem.py. Für die 3D-Geometrie werden mehrere Konformere erzeugt und je mit
MMFF optimiert, das energieärmste wird behalten (_embed_lowest_energy) --
deutlich weniger zufällig als ein einzelner EmbedMolecule-Versuch, aber immer
noch keine gemessene oder biologisch bestätigte Faltung.
"""

from rdkit import Chem
from rdkit.Chem import AllChem

import chem

# Über 15 Reste wird RDKits Embedding für ein einfaches Kraftfeld-Konformer
# unzuverlässig/langsam (keine echte Faltungssimulation) -- gleiche Linie wie
# beim Docking ohne brauchbaren Liganden (1UBQ-Fall in docking.py): klare
# Fehlermeldung statt eines sinnlosen Versuchs.
MAX_RESIDUES = 15

_ONE_LETTER_CODES = set("ACDEFGHIKLMNPQRSTVWY")

# Kuratierte Namens-Liste für kurze Peptidhormone/-neurotransmitter, deren
# PubChem-Namenssuche unzuverlässig ist, aber die kurz genug für diese
# Ausbaustufe sind -- Name (klein geschrieben) -> Ein-Buchstaben-Sequenz.
_KNOWN_PEPTIDES = {
    "oxytocin": "CYIQNCPLG",
    "vasopressin": "CYFQNCPRG",
    "met-enkephalin": "YGGFM",
    "met enkephalin": "YGGFM",
    "leu-enkephalin": "YGGFL",
    "leu enkephalin": "YGGFL",
}


class PeptideError(Exception):
    pass


def _resolve_sequence(name: str | None, sequence: str | None) -> tuple[str, str]:
    """Gibt (Sequenz, Anzeigename) zurück. sequence hat Vorrang vor name, falls
    beide angegeben würden."""
    if sequence:
        seq = sequence.strip().upper()
        if not seq:
            raise PeptideError("Sequenz ist leer.")
        invalid = sorted(set(seq) - _ONE_LETTER_CODES)
        if invalid:
            raise PeptideError(
                f"Ungültige(r) Aminosäure-Code(s): {', '.join(invalid)}. Erlaubt sind "
                "die 20 Standard-Ein-Buchstaben-Codes (z.B. G, A, C, Y, ...)."
            )
        return seq, seq

    if name:
        key = name.strip().lower()
        if key in _KNOWN_PEPTIDES:
            return _KNOWN_PEPTIDES[key], name.strip()
        known = sorted({"Oxytocin", "Vasopressin", "Met-Enkephalin", "Leu-Enkephalin"})
        raise PeptideError(
            f"'{name}' ist nicht in der kuratierten Peptid-Liste ({', '.join(known)}). "
            "Alternativ die Sequenz direkt als Ein-Buchstaben-Code eingeben."
        )

    raise PeptideError("Weder Name noch Sequenz angegeben.")


def _add_disulfide_if_two_cysteines(mol) -> tuple[Chem.Mol, bool]:
    """Falls die Sequenz genau 2 Cystein-Reste enthält, wird eine Disulfidbrücke
    zwischen ihren Thiolschwefeln geknüpft -- typisch für kurze zyklische
    Peptidhormone wie Oxytocin/Vasopressin, deren namensgebende Ringstruktur ohne
    das komplett fehlen würde (nur zwei lose SH-Enden statt eines Rings).
    Reine Heuristik (genau 2 Cystein -> verbinden), keine chemische Bestätigung,
    dass diese beiden Reste in der echten Struktur wirklich verbrückt sind --
    für die kuratierten Beispiele (Oxytocin, Vasopressin) stimmt es aber."""
    sg_indices = []
    for atom in mol.GetAtoms():
        info = atom.GetPDBResidueInfo()
        if info and info.GetResidueName().strip() == "CYS" and info.GetName().strip() == "SG":
            sg_indices.append(atom.GetIdx())

    if len(sg_indices) != 2:
        return mol, False

    rw = Chem.RWMol(mol)
    rw.AddBond(sg_indices[0], sg_indices[1], Chem.BondType.SINGLE)
    for idx in sg_indices:
        atom = rw.GetAtomWithIdx(idx)
        atom.SetNoImplicit(True)
        atom.SetNumExplicitHs(0)
    mol = rw.GetMol()
    Chem.SanitizeMol(mol)
    return mol, True


def _embed_lowest_energy(mol, n_confs: int = 12) -> Chem.Mol:
    """Mehrere Konformere erzeugen, jedes mit MMFF optimieren, das energieärmste
    behalten. useRandomCoords hilft beim Embedding von (ggf. durch die
    Disulfidbrücke) zyklischen Strukturen. Deutlich weniger Zufallsergebnis als
    ein einzelner EmbedMolecule-Versuch, aber weiterhin keine gemessene Struktur."""
    params = AllChem.ETKDGv3()
    params.useRandomCoords = True
    conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=n_confs, params=params)
    if not conf_ids:
        raise PeptideError("Konnte keine 3D-Startstruktur berechnen (Embedding fehlgeschlagen).")

    results = AllChem.MMFFOptimizeMoleculeConfs(mol)
    energies = {cid: energy for cid, (_not_converged, energy) in zip(conf_ids, results)}
    best_id = min(energies, key=energies.get)

    for cid in list(conf_ids):
        if cid != best_id:
            mol.RemoveConformer(cid)
    return mol


def build_peptide(name: str | None = None, sequence: str | None = None) -> dict:
    seq, display_name = _resolve_sequence(name, sequence)

    if len(seq) < 2:
        raise PeptideError("Sequenz braucht mindestens 2 Aminosäuren.")
    if len(seq) > MAX_RESIDUES:
        raise PeptideError(
            f"Sequenz hat {len(seq)} Reste -- diese Ausbaustufe ist bewusst auf "
            f"{MAX_RESIDUES} begrenzt (RDKits Konformer-Embedding wird darüber "
            "unzuverlässig und langsam, keine echte Faltungssimulation)."
        )

    mol = Chem.MolFromSequence(seq)
    if mol is None:
        raise PeptideError(f"Konnte die Sequenz '{seq}' nicht als Peptid lesen.")

    mol, has_disulfide = _add_disulfide_if_two_cysteines(mol)

    facts = chem._compute_facts(mol)

    mol = Chem.AddHs(mol)
    mol = _embed_lowest_energy(mol)

    AllChem.ComputeGasteigerCharges(mol)

    conformer = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        pos = conformer.GetAtomPosition(atom.GetIdx())
        charge = atom.GetDoubleProp("_GasteigerCharge")
        if charge != charge:  # NaN-Check (kann bei seltenen Fällen auftreten)
            charge = 0.0
        atoms.append({
            "element": atom.GetSymbol(),
            "x": pos.x,
            "y": pos.y,
            "z": pos.z,
            "charge": round(charge, 4),
        })
    bonds = [{"a": bond.GetBeginAtomIdx(), "b": bond.GetEndAtomIdx()} for bond in mol.GetBonds()]

    note = (
        "Berechnete Niedrigenergie-Konformation aus mehreren MMFF-optimierten "
        "3D-Einbettungen (energieärmste von mehreren Versuchen) -- keine gemessene "
        "oder biologisch bestätigte Faltung, wie sie ein echtes Protein-Folding-"
        "Modell liefern würde. Termini als freies Amin (N) und freie Carbonsäure (C) "
        "aufgebaut -- posttranslationale Modifikationen wie die C-terminale "
        "Amidierung bei echtem Oxytocin/Vasopressin werden nicht nachgebildet."
    )
    if has_disulfide:
        note += " Die 2 Cystein-Reste wurden per Disulfidbrücke verbunden (Heuristik, siehe docs/stand.md)."

    return {
        "atoms": atoms,
        "bonds": bonds,
        "facts": facts,
        "common_name": f"{display_name} (Peptid, {len(seq)} Reste)",
        "iupac_name": None,
        "note": note,
    }


if __name__ == "__main__":
    for test_name, test_seq in [
        ("oxytocin", None),
        ("vasopressin", None),
        (None, "YGGFM"),
        (None, "AAAAAAAAAAAAAAAAAAAA"),
        ("unbekanntes peptid", None),
    ]:
        print(f"--- name={test_name!r} sequence={test_seq!r} ---")
        try:
            result = build_peptide(name=test_name, sequence=test_seq)
            print("common_name:", result["common_name"])
            print("facts:", result["facts"])
            print("atoms:", len(result["atoms"]), "bonds:", len(result["bonds"]))
            print("note:", result["note"])
        except PeptideError as e:
            print("ERROR:", e)
        print()
