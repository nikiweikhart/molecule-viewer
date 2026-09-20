"""Löst eine Nutzereingabe (Name, Summenformel oder SMILES) zu einer 3D-Molekülstruktur auf."""

import re
import time
from dataclasses import dataclass

import requests
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

from brand_names import BRAND_TO_SUBSTANCE

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# Schweratom-Grenze für die 3D-Berechnung hier. Große Peptide/Proteine (Insulin,
# GLP-1-Wirkstoffe wie Semaglutid/Ozempic, Antikörper, ...) lassen sich zwar über PubChem
# per Name finden, aber ein einzelnes AllChem.EmbedMolecule liefert dafür keine sinnvolle
# Struktur (zu viele drehbare Bindungen) und kann sehr lange laufen. Lieber eine klare,
# erklärende Fehlermeldung als ein stundenlanges Hängen oder eine wirre Struktur. Für
# kleinere Peptide (bis 15 Reste) gibt es den eigenen, robusteren Weg über /api/peptide
# (peptide.py, EmbedMultipleConfs + Energieauswahl).
MAX_HEAVY_ATOMS = 150


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

    # 2) Markennamen (z.B. "Mexalen", "Ozempic") in den zugehörigen Wirkstoffnamen
    # übersetzen, damit Nutzer:innen nicht den wissenschaftlichen/generischen Namen
    # wissen müssen -- siehe brand_names.py für Details und die Liste selbst.
    brand_substance = BRAND_TO_SUBSTANCE.get(query.strip().lower())
    lookup_name = brand_substance or query

    # 3) Als Name bei PubChem nachschlagen (ggf. mit dem übersetzten Wirkstoffnamen).
    info = _pubchem_lookup_by_name(lookup_name)
    if info is not None:
        note = None
        if brand_substance is not None:
            note = f"„{query}“ wurde als Markenname für {info.common_name} erkannt."
        return info, note

    # 4) Als Summenformel bei PubChem suchen (Mehrdeutigkeits-Fall) -- ergibt bei einem
    # erkannten Markennamen keinen Sinn (Markennamen sehen nie wie Formeln aus), daher nur
    # versuchen, wenn Schritt 2 nichts gefunden hat.
    if brand_substance is None:
        info, note = _pubchem_lookup_by_formula(query)
        if info is not None:
            return info, note

    raise ResolveError(f"Konnte '{query}' nicht als Molekül erkennen.")


# Einfacher In-Memory-Cache für PubChem-Anfragen -- läuft nur für die Lebensdauer des
# Prozesses (kein Disk-Cache wie pdb_cache/), aber spart bei wiederholten Anfragen zum
# selben Molekül (z.B. beim Gleichungslöser, der mehrere Stoffe pro Anfrage auflöst,
# oder beim erneuten Testen derselben Beispiele) jedes Mal einen Netzwerk-Roundtrip.
_name_cache: dict[str, "_NameInfo | None"] = {}
_smiles_cache: dict[str, "_NameInfo | None"] = {}
_formula_cache: dict[str, "tuple[_NameInfo | None, str | None]"] = {}

_MAX_RETRIES = 2
_RETRY_BACKOFF_S = 0.5


def _request_with_retry(method, url, **kwargs):
    """Wiederholt eine PubChem-Anfrage bei transienten Fehlern (Timeout,
    Verbindungsabbruch, 5xx) -- ein 404 o.ä. ("dieser Name/diese Formel
    existiert nicht bei PubChem") ist eine normale, gültige Antwort und wird
    NICHT wiederholt, nur echte Netzwerk-/Serverfehler. Ohne das würde ein
    einzelner kurzer Netzwerk-Hänger fälschlich dauerhaft im Cache landen
    (siehe _name_cache/_smiles_cache/_formula_cache oben -- die cachen auch
    "nicht gefunden", was für einen echten 404 richtig ist, für einen
    transienten Fehler aber ein falsches Dauer-Ergebnis wäre)."""
    last_exc = None
    resp = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = method(url, timeout=10, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
        else:
            if resp.status_code < 500:
                return resp
            last_exc = None
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
    if last_exc is not None:
        raise ResolveError(
            "PubChem ist gerade nicht erreichbar -- bitte in ein paar Sekunden nochmal versuchen."
        ) from last_exc
    return resp


def _pubchem_lookup_by_name(name: str) -> _NameInfo | None:
    if name in _name_cache:
        return _name_cache[name]
    url = f"{PUBCHEM_BASE}/compound/name/{name}/property/ConnectivitySMILES,Title,IUPACName/JSON"
    resp = _request_with_retry(requests.get, url)
    if resp.status_code != 200:
        _name_cache[name] = None
        return None
    props = resp.json()["PropertyTable"]["Properties"][0]
    info = _NameInfo(
        smiles=props["ConnectivitySMILES"],
        common_name=props.get("Title", name),
        iupac_name=props.get("IUPACName"),
    )
    _name_cache[name] = info
    return info


def _pubchem_lookup_by_smiles(smiles: str) -> _NameInfo | None:
    if smiles in _smiles_cache:
        return _smiles_cache[smiles]
    url = f"{PUBCHEM_BASE}/compound/smiles/property/ConnectivitySMILES,Title,IUPACName/JSON"
    resp = _request_with_retry(requests.post, url, data={"smiles": smiles})
    if resp.status_code != 200:
        _smiles_cache[smiles] = None
        return None
    props = resp.json()["PropertyTable"]["Properties"][0]
    info = _NameInfo(
        smiles=props.get("ConnectivitySMILES", smiles),
        common_name=props.get("Title", smiles),
        iupac_name=props.get("IUPACName"),
    )
    _smiles_cache[smiles] = info
    return info


def _pubchem_lookup_by_formula(formula: str) -> tuple[_NameInfo | None, str | None]:
    if formula in _formula_cache:
        return _formula_cache[formula]

    result = _pubchem_lookup_by_formula_uncached(formula)
    _formula_cache[formula] = result
    return result


# Wie viele der (nach CID sortierten) Formel-Treffer per Synonym-Anzahl verglichen werden --
# begrenzt, damit eine Formel mit vielen Isomeren (z.B. Hexosen) nicht Dutzende zusätzliche
# PubChem-Anfragen auslöst.
_FORMULA_CANDIDATE_LIMIT = 8


def _pick_most_common_cid(cids: list[int]) -> int:
    """Wählt unter mehreren zur gleichen Formel passenden CIDs den vermutlich
    gebräuchlichsten Stoff aus -- vorher wurde einfach min(cids) genommen
    (niedrigste/früheste CID), was z.B. bei C6H12O6 den Oberbegriff
    "Hexopyranose" statt "D-Glucose" ergab (siehe docs/stand.md, Fallstrick 1).

    Bessere Näherung: die Anzahl bekannter Synonyme pro CID abfragen (ein
    Sammelbegriff wie "Hexopyranose" hat typischerweise deutlich weniger
    Namen/Handelsbezeichnungen hinterlegt als ein konkreter, gut dokumentierter
    Stoff wie Glucose) und den mit den meisten Synonymen wählen. Immer noch
    eine Heuristik, kein echtes Popularitäts-Ranking -- fällt bei jedem Fehler
    (Netzwerk, leere Antwort) sauber auf die alte min(cids)-Regel zurück.
    """
    candidates = sorted(cids)[:_FORMULA_CANDIDATE_LIMIT]
    if len(candidates) == 1:
        return candidates[0]

    ids_param = ",".join(str(cid) for cid in candidates)
    try:
        syn_resp = _request_with_retry(requests.get, f"{PUBCHEM_BASE}/compound/cid/{ids_param}/synonyms/JSON")
        syn_resp.raise_for_status()
        counts = {
            entry["CID"]: len(entry.get("Synonym", []))
            for entry in syn_resp.json()["InformationList"]["Information"]
        }

        title_resp = _request_with_retry(
            requests.get, f"{PUBCHEM_BASE}/compound/cid/{ids_param}/property/Title/JSON"
        )
        title_resp.raise_for_status()
        titles = {p["CID"]: p.get("Title", "") for p in title_resp.json()["PropertyTable"]["Properties"]}

        # PubChem hat für manche Einträge (oft ChEBI-Importe) beschreibende
        # Pseudo-Titel wie "An inositol that is ..." statt eines echten Stoffnamens --
        # erkennbar an der führenden unbestimmten Artikel-Phrase. Diese haben oft
        # viele Synonyme (Handelsnamen etc.), sind aber als Anzeigename schlecht --
        # werden bei der Auswahl übersprungen, solange es eine "echt benannte"
        # Alternative gibt.
        real_name_candidates = [
            cid for cid in candidates if not re.match(r"^(a|an)\s+[a-z]", titles.get(cid, ""), re.IGNORECASE)
        ]
        pool = real_name_candidates or candidates
        if counts:
            return max(pool, key=lambda cid: counts.get(cid, 0))
    except (requests.RequestException, KeyError, ValueError):
        pass
    return min(cids)


def _pubchem_lookup_by_formula_uncached(formula: str) -> tuple[_NameInfo | None, str | None]:
    url = f"{PUBCHEM_BASE}/compound/fastformula/{formula}/cids/JSON"
    resp = _request_with_retry(requests.get, url)
    if resp.status_code != 200:
        return None, None

    cids = resp.json()["IdentifierList"]["CID"]
    if not cids:
        return None, None

    chosen_cid = _pick_most_common_cid(cids)

    prop_url = f"{PUBCHEM_BASE}/compound/cid/{chosen_cid}/property/ConnectivitySMILES,Title,IUPACName/JSON"
    prop_resp = _request_with_retry(requests.get, prop_url)
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
            f"Automatisch gewählt: {info.common_name} (Treffer mit den meisten bekannten Namen/Synonymen bei PubChem, als Näherung für \"am bekanntesten\")."
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

    heavy_atoms = mol.GetNumHeavyAtoms()
    if heavy_atoms > MAX_HEAVY_ATOMS:
        raise ResolveError(
            f"Dieser Stoff hat {heavy_atoms} Schweratome -- zu groß für die 3D-Berechnung "
            "hier. Das ist typisch für große Peptide/Proteine (z.B. Insulin oder "
            "GLP-1-Wirkstoffe wie Semaglutid/Ozempic) oder Antikörper. Für kleinere Peptide "
            "(bis 15 Aminosäuren) gibt es den eigenen Peptid-Modus."
        )

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
    for test_query in ["water", "aspirin", "mexalen", "ozempic", "C6H12O6", "CCO"]:
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
