"""Löst eine Nutzereingabe (Name, Summenformel oder SMILES) zu einer 3D-Molekülstruktur auf."""

from dataclasses import dataclass

import requests
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


class ResolveError(Exception):
    pass


@dataclass
class ResolvedMolecule:
    atoms: list[dict]
    bonds: list[dict]
    facts: dict
    common_name: str
    iupac_name: str | None = None
    note: str | None = None


@dataclass
class _NameInfo:
    smiles: str
    common_name: str
    iupac_name: str | None


def resolve(query: str) -> ResolvedMolecule:
    query = query.strip()
    if not query:
        raise ResolveError("Eingabe ist leer.")

    info, note = _resolve_to_names(query)
    atoms, bonds, facts = _build_structure(info.smiles)
    return ResolvedMolecule(
        atoms=atoms,
        bonds=bonds,
        facts=facts,
        common_name=info.common_name,
        iupac_name=info.iupac_name,
        note=note,
    )


def _resolve_to_names(query: str) -> tuple[_NameInfo, str | None]:
    # 1) Direkt als SMILES versuchen — kein Netzwerk nötig, um die Struktur zu bekommen.
    mol = Chem.MolFromSmiles(query)
    if mol is not None:
        info = _pubchem_lookup_by_smiles(query)
        if info is None:
            # PubChem kennt die Struktur nicht (z.B. sehr exotisch/neu) — trotzdem anzeigen,
            # nur ohne hübschen Namen.
            info = _NameInfo(smiles=query, common_name=query, iupac_name=None)
        return info, None

    # 2) Als Name bei PubChem nachschlagen.
    info = _pubchem_lookup_by_name(query)
    if info is not None:
        return info, None

    # 3) Als Summenformel bei PubChem suchen (Mehrdeutigkeits-Fall).
    info, note = _pubchem_lookup_by_formula(query)
    if info is not None:
        return info, note

    raise ResolveError(f"Konnte '{query}' nicht als Molekül erkennen.")


def _pubchem_lookup_by_name(name: str) -> _NameInfo | None:
    url = f"{PUBCHEM_BASE}/compound/name/{name}/property/ConnectivitySMILES,Title,IUPACName/JSON"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        return None
    props = resp.json()["PropertyTable"]["Properties"][0]
    return _NameInfo(
        smiles=props["ConnectivitySMILES"],
        common_name=props.get("Title", name),
        iupac_name=props.get("IUPACName"),
    )


def _pubchem_lookup_by_smiles(smiles: str) -> _NameInfo | None:
    url = f"{PUBCHEM_BASE}/compound/smiles/property/ConnectivitySMILES,Title,IUPACName/JSON"
    resp = requests.post(url, data={"smiles": smiles}, timeout=10)
    if resp.status_code != 200:
        return None
    props = resp.json()["PropertyTable"]["Properties"][0]
    return _NameInfo(
        smiles=props.get("ConnectivitySMILES", smiles),
        common_name=props.get("Title", smiles),
        iupac_name=props.get("IUPACName"),
    )


def _pubchem_lookup_by_formula(formula: str) -> tuple[_NameInfo | None, str | None]:
    url = f"{PUBCHEM_BASE}/compound/fastformula/{formula}/cids/JSON"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        return None, None

    cids = resp.json()["IdentifierList"]["CID"]
    if not cids:
        return None, None

    # Niedrigste CID = am frühesten registriert, in der Praxis meist der bekannteste Treffer
    # (grobe Näherung — siehe bekannte Fallstricke in docs/stand.md).
    chosen_cid = min(cids)

    prop_url = f"{PUBCHEM_BASE}/compound/cid/{chosen_cid}/property/ConnectivitySMILES,Title,IUPACName/JSON"
    prop_resp = requests.get(prop_url, timeout=10)
    prop_resp.raise_for_status()
    props = prop_resp.json()["PropertyTable"]["Properties"][0]

    info = _NameInfo(
        smiles=props["ConnectivitySMILES"],
        common_name=props.get("Title", f"CID {chosen_cid}"),
        iupac_name=props.get("IUPACName"),
    )

    note = None
    if len(cids) > 1:
        note = (
            f"Die Formel {formula} passt zu {len(cids)} bekannten Stoffen. "
            f"Automatisch gewählt: {info.common_name} (bekanntester/am frühesten dokumentierter Treffer)."
        )

    return info, note


def _compute_facts(mol) -> dict:
    """Berechnet die Fakten-Panel-Werte aus einem Schweratom-Mol (vor AddHs) —
    RDKits Deskriptoren zählen implizite H schon korrekt mit. Schnell, kein
    3D-Embedding nötig — deshalb auch für den chemischen Raum (chemspace.py)
    genutzt, wo Dutzende Moleküle auf einmal verarbeitet werden."""
    return {
        "formula": rdMolDescriptors.CalcMolFormula(mol),
        "molweight": round(Descriptors.MolWt(mol), 2),
        "logp": round(Descriptors.MolLogP(mol), 2),
        "tpsa": round(Descriptors.TPSA(mol), 1),
        "h_donors": Descriptors.NumHDonors(mol),
        "h_acceptors": Descriptors.NumHAcceptors(mol),
        "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
    }


def _build_structure(smiles: str) -> tuple[list[dict], list[dict], dict]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ResolveError(f"SMILES '{smiles}' konnte nicht gelesen werden.")

    facts = _compute_facts(mol)

    mol = Chem.AddHs(mol)
    embed_result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    if embed_result != 0:
        raise ResolveError("Konnte keine 3D-Struktur berechnen.")
    AllChem.MMFFOptimizeMolecule(mol)

    # Gasteiger-Partialladungen für den Ladungs-Darstellungsmodus im Frontend.
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

    return atoms, bonds, facts


if __name__ == "__main__":
    for test_query in ["water", "aspirin", "C6H12O6", "CCO"]:
        print(f"--- {test_query} ---")
        try:
            result = resolve(test_query)
            print("common_name:", result.common_name)
            print("iupac_name:", result.iupac_name)
            print("note:", result.note)
            print("facts:", result.facts)
            print("atoms:", len(result.atoms), "bonds:", len(result.bonds))
        except ResolveError as e:
            print("ERROR:", e)
        print()
