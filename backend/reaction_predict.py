"""Produktvorhersage für den Gleichungslöser: aus den eingetippten Edukten
allein (ohne "->") die wahrscheinlichen Produkte für eine kleine, bewusst
begrenzte Menge an Schul-Reaktionstypen ableiten, dann exakt dieselbe
Ausgleichs-/Layout-/Animations-Pipeline wie beim vollständigen
Gleichungslöser weiterverwenden (equation.build_reaction_from_species).

Bewusst NUR vier eindeutige, klassische Reaktionstypen aus dem
Chemieunterricht: Verbrennung, Neutralisation (Säure+Base), Metall+Säure,
Synthese aus zwei Elementen. Alles andere (Redox mit mehrdeutiger
Oxidationsstufe wie Eisen, Zersetzung, organische Mechanismen, ...) bekommt
eine ehrliche "nicht erkannt"-Fehlermeldung statt einer geratenen, im
Zweifel falschen Antwort -- gleiche Linie wie der Rest der App (siehe
docs/stand.md, z.B. Docking-Ladungszustände oder MD-Force-Capping)."""

from collections import Counter

from rdkit import Chem

import docking
import equation
import salts


class PredictionError(Exception):
    pass


# Formel (docking._hill_formula-Konvention, kein "*") -> Anion-Schlüssel aus salts.py.
ACIDS = {
    "ClH": "chlorid",
    "H2O4S": "sulfat",
    "HNO3": "nitrat",
    "H3O4P": "phosphat",
    "C2H4O2": "acetat",
    "CH2O3": "carbonat",
}

# Formel -> (Kation-Schlüssel, bildet die Neutralisation zusätzlich Wasser?).
# Ammoniak (H3N) reagiert mit einer Säure direkt zum Ammoniumsalz OHNE Wasser
# (NH3 + HCl -> NH4Cl) -- anders als Metallhydroxide, wo das Hydroxid-Ion mit
# dem Säure-Proton zu Wasser reagiert.
BASES = {
    "HNaO": ("natrium", True),
    "HKO": ("kalium", True),
    "CaH2O2": ("calcium", True),
    "H2MgO2": ("magnesium", True),
    "AlH3O3": ("aluminium", True),
    "FeH2O2": ("eisen(ii)", True),
    "FeH3O3": ("eisen(iii)", True),
    "H3N": ("ammonium", False),
    "H5NO": ("ammonium", True),
}

# Nur Metalle mit eindeutiger, fixer Oxidationsstufe -- Eisen/Chrom/Blei bewusst
# NICHT dabei (siehe Moduldocstring): deren tatsächliches Produkt hängt vom
# Reaktionspartner ab (z.B. Fe+Cl2 -> FeCl3, aber Fe+S -> FeS), das lässt sich
# aus dem Element allein nicht sicher herleiten.
METALS_FOR_ACID = {
    "Na": "natrium", "K": "kalium", "Li": "lithium", "Ca": "calcium",
    "Mg": "magnesium", "Al": "aluminium", "Zn": "zink", "Ba": "barium",
}
METALS_FOR_SYNTHESIS = {**METALS_FOR_ACID, "Ag": "silber", "Cu": "kupfer(ii)"}

NONMETALS_FOR_SYNTHESIS = {
    "Cl": "chlorid", "Br": "bromid", "I": "iodid", "F": "fluorid",
    "O": "oxid", "S": "sulfid",
}


def _formula(species: equation._Species) -> str:
    return docking._hill_formula(list(species.element_counts.elements()))


def _is_pure_element(species: equation._Species) -> str | None:
    """Elementsymbol, wenn diese Spezies nur aus einem einzigen Element
    besteht (egal welche Anzahl -- Cl2, O2, ein einzelnes Na-Atom sind alle
    'rein'), sonst None."""
    if len(species.element_counts) == 1:
        return next(iter(species.element_counts))
    return None


def _species_from_smiles(smiles: str, name: str) -> equation._Species:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    counts = Counter(atom.GetSymbol() for atom in mol.GetAtoms())
    return equation._Species(query=name, smiles=smiles, common_name=name, element_counts=counts)


def _salt_species(cation_key: str, anion_key: str) -> equation._Species:
    info = salts.compute(cation_key, anion_key)
    return _species_from_smiles(info["smiles"], info["name"])


def _water() -> equation._Species:
    return _species_from_smiles("O", "Wasser")


def _hydrogen() -> equation._Species:
    return _species_from_smiles("[HH]", "Wasserstoff")


def _carbon_dioxide() -> equation._Species:
    return _species_from_smiles("O=C=O", "Kohlenstoffdioxid")


def predict_products(reactant_species: list[equation._Species]) -> tuple[list[equation._Species], str]:
    if len(reactant_species) != 2:
        raise PredictionError("Produktvorhersage funktioniert aktuell nur für genau zwei Edukte.")
    a, b = reactant_species

    # 1) Verbrennung: ein Edukt ist reiner Sauerstoff, das andere besteht nur aus C/H/O.
    for fuel, other in ((a, b), (b, a)):
        if _formula(other) != "O2" or not fuel.element_counts:
            continue
        if not set(fuel.element_counts) <= {"C", "H", "O"}:
            continue
        has_c = "C" in fuel.element_counts
        has_h = "H" in fuel.element_counts
        if has_c and has_h:
            return [_carbon_dioxide(), _water()], "Verbrennung"
        if has_c:
            return [_carbon_dioxide()], "Verbrennung (reiner Kohlenstoff)"
        if has_h:
            return [_water()], "Verbrennung (Knallgasreaktion)"

    # 2) Neutralisation: eine Säure + eine Base (Metallhydroxid oder Ammoniak).
    for acid, base in ((a, b), (b, a)):
        acid_anion = ACIDS.get(_formula(acid))
        base_entry = BASES.get(_formula(base))
        if acid_anion and base_entry:
            cation_key, makes_water = base_entry
            products = [_salt_species(cation_key, acid_anion)]
            if makes_water:
                products.append(_water())
            return products, "Neutralisation (Säure-Base-Reaktion)"

    # 3) Metall + Säure -> Salz + Wasserstoff.
    for metal, acid in ((a, b), (b, a)):
        element = _is_pure_element(metal)
        acid_anion = ACIDS.get(_formula(acid))
        if element in METALS_FOR_ACID and acid_anion:
            return [_salt_species(METALS_FOR_ACID[element], acid_anion), _hydrogen()], "Metall + Säure"

    # 4) Synthese aus zwei Elementen (Metall + Nichtmetall -> Salz/Oxid/Sulfid).
    element_a, element_b = _is_pure_element(a), _is_pure_element(b)
    if element_a and element_b:
        for metal_el, nonmetal_el in ((element_a, element_b), (element_b, element_a)):
            if metal_el in METALS_FOR_SYNTHESIS and nonmetal_el in NONMETALS_FOR_SYNTHESIS:
                salt = _salt_species(METALS_FOR_SYNTHESIS[metal_el], NONMETALS_FOR_SYNTHESIS[nonmetal_el])
                return [salt], "Synthese aus Elementen"

    raise PredictionError(
        "Reaktionstyp nicht erkannt -- die automatische Produktvorhersage kennt aktuell nur "
        "Verbrennung, Neutralisation (Säure + Base), Metall + Säure und Synthese aus zwei "
        'Elementen. Für andere Reaktionen bitte die Produkte selbst mit "->" angeben.'
    )


def build_predicted_reaction(reactant_queries: list[str]) -> dict:
    reactant_species = [equation._resolve_species(q) for q in reactant_queries]
    product_species, reaction_type = predict_products(reactant_species)
    result = equation.build_reaction_from_species(reactant_species, product_species)
    result["reaction_type"] = reaction_type
    return result


if __name__ == "__main__":
    for reactants in [
        ["CH4", "O2"],
        ["H2", "O2"],
        ["graphite", "O2"],  # "C" allein waere als SMILES Methan, nicht Kohlenstoff -- siehe chem.py
        ["HCl", "NaOH"],
        ["H2SO4", "calcium hydroxide"],
        ["ammonia", "HCl"],
        ["zinc", "HCl"],
        ["sodium", "Cl2"],
        ["magnesium", "O2"],
        ["Fe", "Cl2"],  # soll ehrlich scheitern (Eisen bewusst ausgeschlossen)
    ]:
        try:
            data = build_predicted_reaction(reactants)
            # ASCII-Pfeil fuers Windows-Konsolen-cp1252 statt "->" in formula_label/reaction_type.
            label = data["formula_label"].replace("*", "").encode("ascii", "replace").decode("ascii")
            rtype = data["reaction_type"].encode("ascii", "replace").decode("ascii")
            print(f"{' + '.join(reactants):30} -> [{rtype}] {label}")
        except (equation.EquationError, PredictionError) as e:
            msg = str(e).encode("ascii", "replace").decode("ascii")
            print(f"{' + '.join(reactants):30} -> ERROR: {msg}")
