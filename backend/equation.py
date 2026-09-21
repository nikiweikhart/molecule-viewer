"""Allgemeiner Reaktionsgleichungs-Löser: nimmt eine Textgleichung wie
"CH4 + O2 -> CO2 + H2O" (Namen/Formeln/SMILES gemischt erlaubt), gleicht
die stöchiometrischen Koeffizienten exakt aus und baut daraus eine
Morph-Animation im selben Datenformat wie reactions.build_reaction().

Unterschied zu reactions.py: dort sind die paar Beispiel-Reaktionen von Hand
mit exakten Atom-Map-Nummern hinterlegt -- 100% korrekte, chemisch bewiesene
Zuordnung. Hier kann es das nicht geben, weil die Gleichung frei eingetippt
wird: welches Atom im Edukt zu welchem Atom im Produkt "wird", ist ein
eigenes, in der echten Cheminformatik ungelöstes Problem (reaction atom
mapping, üblicherweise per ML-Modell angenähert). Diese Datei löst nur die
Stöchiometrie exakt und schätzt die Atom-Zuordnung fürs Morphen mit einer
einfachen, ehrlich benannten Heuristik (_match_atoms): pro Element eine
optimale Zuordnung nach räumlicher Nähe (Ungarische Methode). Für die
meisten einfachen Lehrbuch-Gleichungen (Verbrennung, Synthese, einfache
Zersetzung) sieht das Ergebnis plausibel aus; bei komplexeren Umlagerungen
ist es nur eine Annäherung, keine chemisch bewiesene Atom-Verfolgung.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from math import gcd

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from scipy.optimize import linear_sum_assignment

import chem

_FRAGMENT_GAP = 3.5  # Å, gleicher Wert wie in reactions.py


class EquationError(Exception):
    pass


@dataclass
class _Species:
    query: str
    smiles: str
    common_name: str
    element_counts: Counter


def _split_terms(side: str) -> list[str]:
    terms = []
    for raw in side.split("+"):
        term = raw.strip()
        if not term:
            continue
        # Führenden Koeffizienten abstreifen (z.B. "2 H2O") -- wird ohnehin neu berechnet,
        # damit Eingaben mit falschen/fehlenden Koeffizienten trotzdem funktionieren.
        m = re.match(r"^\d+\s*(.+)$", term)
        terms.append(m.group(1).strip() if m else term)
    return terms


def _parse_equation(text: str) -> tuple[list[str], list[str]]:
    normalized = text.replace("=", "->").replace("→", "->")
    if "->" not in normalized:
        raise EquationError(
            "Gleichung braucht einen Pfeil zwischen Edukten und Produkten ('->', '=' oder '→')."
        )
    left, right = normalized.split("->", 1)
    reactants = _split_terms(left)
    products = _split_terms(right)
    if not reactants or not products:
        raise EquationError("Sowohl Edukt- als auch Produktseite brauchen mindestens einen Stoff.")
    return reactants, products


def _resolve_species(query: str) -> _Species:
    try:
        info, _note = chem._resolve_to_names(query)
    except chem.ResolveError as e:
        raise EquationError(f"'{query}' nicht erkannt: {e}")
    mol = Chem.MolFromSmiles(info.smiles)
    if mol is None:
        raise EquationError(f"SMILES für '{query}' konnte nicht gelesen werden.")
    mol = Chem.AddHs(mol)
    counts = Counter(atom.GetSymbol() for atom in mol.GetAtoms())
    return _Species(query=query, smiles=info.smiles, common_name=info.common_name, element_counts=counts)


def _null_space(matrix: list[list[Fraction]], n_cols: int) -> list[list[int]]:
    """Gauß-Jordan über Q (exakte Brüche, keine Rundungsfehler) -> Basis des Nullraums,
    jeweils auf kleinste positive Ganzzahlen skaliert."""
    rows = [row[:] for row in matrix]
    pivot_cols = []
    r = 0
    for c in range(n_cols):
        pivot = next((i for i in range(r, len(rows)) if rows[i][c] != 0), None)
        if pivot is None:
            continue
        rows[r], rows[pivot] = rows[pivot], rows[r]
        pivot_val = rows[r][c]
        rows[r] = [v / pivot_val for v in rows[r]]
        for i in range(len(rows)):
            if i != r and rows[i][c] != 0:
                factor = rows[i][c]
                rows[i] = [v - factor * rows[r][idx] for idx, v in enumerate(rows[i])]
        pivot_cols.append(c)
        r += 1
        if r == len(rows):
            break

    free_cols = [c for c in range(n_cols) if c not in pivot_cols]
    basis = []
    for free_col in free_cols:
        vec = [Fraction(0)] * n_cols
        vec[free_col] = Fraction(1)
        for row_idx, pc in enumerate(pivot_cols):
            vec[pc] = -rows[row_idx][free_col]
        basis.append(_to_min_integers(vec))
    return basis


def _to_min_integers(vec: list[Fraction]) -> list[int]:
    denom_lcm = 1
    for v in vec:
        denom_lcm = denom_lcm * v.denominator // gcd(denom_lcm, v.denominator)
    ints = [int(v * denom_lcm) for v in vec]
    g = 0
    for v in ints:
        g = gcd(g, abs(v))
    if g > 1:
        ints = [v // g for v in ints]
    return ints


def _balance(reactant_species: list[_Species], product_species: list[_Species]) -> list[int]:
    """Löst M @ x = 0 für die stöchiometrischen Koeffizienten (Edukte positiv, Produkte
    negativ im gleichen Vorzeichen-System) -- Standardverfahren für Gleichungsausgleich."""
    elements = sorted({el for sp in reactant_species + product_species for el in sp.element_counts})
    if not elements:
        raise EquationError("Keine Atome gefunden.")

    n = len(reactant_species) + len(product_species)
    matrix = [[Fraction(0) for _ in range(n)] for _ in elements]
    for col, sp in enumerate(reactant_species):
        for row, el in enumerate(elements):
            matrix[row][col] = Fraction(sp.element_counts.get(el, 0))
    for col, sp in enumerate(product_species):
        for row, el in enumerate(elements):
            matrix[row][len(reactant_species) + col] = -Fraction(sp.element_counts.get(el, 0))

    basis = _null_space(matrix, n)
    if not basis:
        raise EquationError(
            "Gleichung ist nicht ausgleichbar -- die Elemente auf beiden Seiten passen nicht "
            "zusammen (Tippfehler bei einem Stoff, oder es fehlt ein Produkt/Edukt)."
        )
    if len(basis) > 1:
        raise EquationError(
            "Gleichung hat mehr als eine unabhängige Lösung -- das ist bei einer einzelnen "
            "echten Reaktion untypisch (z.B. bei 'C + O2 -> CO + CO2"
            "'). Bitte die Gleichung eindeutiger aufschlüsseln."
        )

    coeffs = basis[0]
    if any(c == 0 for c in coeffs):
        raise EquationError(
            "Ein Stoff bekommt Koeffizient 0 -- er kommt in der ausgeglichenen Gleichung gar "
            "nicht vor. Gehört er wirklich in diese Reaktion?"
        )
    signs = {1 if c > 0 else -1 for c in coeffs}
    if len(signs) > 1:
        raise EquationError(
            "Gleichung lässt sich mit dieser Aufteilung in Edukte/Produkte nicht ausgleichen "
            "-- vielleicht steht ein Stoff auf der falschen Seite?"
        )
    if next(iter(signs)) < 0:
        coeffs = [-c for c in coeffs]

    return coeffs


def _embed_species(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise EquationError(f"SMILES '{smiles}' konnte nicht gelesen werden.")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) != 0:
        raise EquationError("Konnte keine 3D-Struktur berechnen.")
    AllChem.MMFFOptimizeMolecule(mol)

    conformer = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        pos = conformer.GetAtomPosition(atom.GetIdx())
        atoms.append({"element": atom.GetSymbol(), "x": pos.x, "y": pos.y, "z": pos.z})
    bonds = [(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()) for bond in mol.GetBonds()]
    return atoms, bonds


def _layout_instances(species_list: list[_Species]) -> tuple[list[dict], list[tuple[int, int]]]:
    """Bettet jede Molekül-Instanz einzeln ein und reiht sie nebeneinander auf --
    gleiches Nebeneinander-Layout wie reactions._layout_side(), nur über mehrere
    unabhängige Moleküle statt Fragmente eines Multi-Komponenten-SMILES."""
    all_atoms = []
    all_bonds = []
    x_offset = 0.0

    for sp in species_list:
        atoms, bonds = _embed_species(sp.smiles)
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
            })
        for a, b in bonds:
            all_bonds.append((base_index + a, base_index + b))

        x_offset += (max(xs) - min(xs)) + _FRAGMENT_GAP

    return all_atoms, all_bonds


def _match_atoms(start_atoms, start_bonds, end_atoms, end_bonds):
    """Schätzt eine 1:1-Atomzuordnung Start->Ende, getrennt pro Element, per optimaler
    Zuordnung nach räumlichem Abstand (Ungarische Methode/`linear_sum_assignment`).
    Siehe Modul-Docstring für die Einordnung dieser Näherung."""
    start_by_el = defaultdict(list)
    end_by_el = defaultdict(list)
    for i, a in enumerate(start_atoms):
        start_by_el[a["element"]].append(i)
    for i, a in enumerate(end_atoms):
        end_by_el[a["element"]].append(i)

    if sorted(start_by_el) != sorted(end_by_el) or any(
        len(start_by_el[el]) != len(end_by_el[el]) for el in start_by_el
    ):
        raise EquationError(
            "Interner Fehler: Elementzahlen stimmen nach dem Ausgleichen nicht überein."
        )

    correspondence = []
    end_of_start = {}
    for el, start_indices in start_by_el.items():
        end_indices = end_by_el[el]
        cost = np.zeros((len(start_indices), len(end_indices)))
        for i, si in enumerate(start_indices):
            sp = start_atoms[si]
            for j, ei in enumerate(end_indices):
                ep = end_atoms[ei]
                cost[i, j] = (sp["x"] - ep["x"]) ** 2 + (sp["y"] - ep["y"]) ** 2 + (sp["z"] - ep["z"]) ** 2
        row_idx, col_idx = linear_sum_assignment(cost)
        for i, j in zip(row_idx, col_idx):
            si, ei = start_indices[i], end_indices[j]
            correspondence.append([si, ei])
            end_of_start[si] = ei

    start_of_end = {ei: si for si, ei in end_of_start.items()}
    start_bond_set = {tuple(sorted(b)) for b in start_bonds}
    end_bond_set = {tuple(sorted(b)) for b in end_bonds}

    persistent_bonds = []
    broken_bonds = []
    for a, b in start_bond_set:
        ea, eb = end_of_start.get(a), end_of_start.get(b)
        if ea is not None and eb is not None and tuple(sorted((ea, eb))) in end_bond_set:
            persistent_bonds.append([a, b])
        else:
            broken_bonds.append([a, b])

    formed_bonds = []
    for a, b in end_bond_set:
        sa, sb = start_of_end.get(a), start_of_end.get(b)
        if sa is not None and sb is not None and tuple(sorted((sa, sb))) not in start_bond_set:
            formed_bonds.append([sa, sb])

    return correspondence, persistent_bonds, broken_bonds, formed_bonds


def _format_side(species_list: list[_Species], coeffs: list[int]) -> str:
    parts = []
    for sp, n in zip(species_list, coeffs):
        prefix = f"{n} " if n != 1 else ""
        parts.append(f"{prefix}{sp.common_name}")
    return " + ".join(parts)


def _hill_formula(counts: Counter) -> str:
    """Baut eine Summenformel im Hill-System (C zuerst, dann H, dann Rest
    alphabetisch -- ohne C: alles alphabetisch). Jede Elementanzahl >1 wird mit
    einem führenden '*' markiert (z.B. 'C*6H*12O*6') -- das ist dieselbe
    Escape-Konvention wie im Gleichungslöser-Eingabefeld (siehe app.js
    formatSubscripts()): das Frontend rendert '*<Zahl>' als tiefgestellte
    Zahl, egal ob sie vom Menschen eingetippt oder hier berechnet wurde."""
    if "C" in counts:
        ordered = ["C"] + (["H"] if "H" in counts else [])
        ordered += sorted(el for el in counts if el not in ("C", "H"))
    else:
        ordered = sorted(counts)
    parts = []
    for el in ordered:
        n = counts[el]
        parts.append(f"{el}*{n}" if n > 1 else el)
    return "".join(parts)


def _format_formula_side(species_list: list[_Species], coeffs: list[int]) -> str:
    parts = []
    for sp, n in zip(species_list, coeffs):
        prefix = f"{n} " if n != 1 else ""
        parts.append(f"{prefix}{_hill_formula(sp.element_counts)}")
    return " + ".join(parts)


def build_equation_reaction(text: str) -> dict:
    reactant_queries, product_queries = _parse_equation(text)

    reactant_species = [_resolve_species(q) for q in reactant_queries]
    product_species = [_resolve_species(q) for q in product_queries]

    coeffs = _balance(reactant_species, product_species)
    n_react = len(reactant_species)
    reactant_coeffs = coeffs[:n_react]
    product_coeffs = coeffs[n_react:]

    start_instances = [sp for sp, n in zip(reactant_species, reactant_coeffs) for _ in range(n)]
    end_instances = [sp for sp, n in zip(product_species, product_coeffs) for _ in range(n)]

    start_atoms, start_bonds = _layout_instances(start_instances)
    end_atoms, end_bonds = _layout_instances(end_instances)

    correspondence, persistent_bonds, broken_bonds, formed_bonds = _match_atoms(
        start_atoms, start_bonds, end_atoms, end_bonds
    )

    label = (
        f"{_format_side(reactant_species, reactant_coeffs)} → "
        f"{_format_side(product_species, product_coeffs)}"
    )
    formula_label = (
        f"{_format_formula_side(reactant_species, reactant_coeffs)} → "
        f"{_format_formula_side(product_species, product_coeffs)}"
    )

    return {
        "label": label,
        "formula_label": formula_label,
        "start": {"atoms": start_atoms},
        "end": {"atoms": end_atoms},
        "correspondence": correspondence,
        "persistent_bonds": persistent_bonds,
        "broken_bonds": broken_bonds,
        "formed_bonds": formed_bonds,
    }


if __name__ == "__main__":
    for eq in ["CH4 + O2 -> CO2 + H2O", "H2 + O2 -> H2O", "N2 + H2 -> NH3"]:
        print(f"--- {eq} ---")
        try:
            data = build_equation_reaction(eq)
            # ASCII-Pfeil fuers Windows-Konsolen-cp1252 statt "->" in data["label"].
            print("label:", data["label"].encode("ascii", "replace").decode("ascii"))
            print("start atoms:", len(data["start"]["atoms"]), "end atoms:", len(data["end"]["atoms"]))
            print("persistent:", len(data["persistent_bonds"]), "broken:", len(data["broken_bonds"]),
                  "formed:", len(data["formed_bonds"]))
        except EquationError as e:
            print("ERROR:", e)
        print()
