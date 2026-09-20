"""Bekannte, real gemessene Strukturen für große Peptid-Wirkstoffe, die für
die normale 3D-Berechnung (chem._build_structure, EmbedMolecule) zu groß sind
(siehe MAX_HEAVY_ATOMS in chem.py) -- wird im Haupt-Suchfeld VOR der
normalen Auflösung geprüft (app.py), damit z.B. "Ozempic" nicht mehr mit
einer "zu groß"-Fehlermeldung endet, sondern die reale Kristall-/Cryo-EM-
Struktur zeigt. Gleicher Mechanismus wie die "Peptid-Wirkstoffe"-Karten in
der Bibliothek (docking.pdb_ligand), nur jetzt auch über die freie
Texteingabe erreichbar statt nur über eine eigene Karte.

Jeder Eintrag wurde einzeln gegen die echte RCSB-Struktur geprüft (Ketten-
länge UND Entity-Beschreibung abgeglichen, nicht nur aus der Volltext-
Trefferliste geraten) -- siehe docs/stand.md für die Belege. Fehlt ein
Wirkstoff hier (z.B. Dulaglutide/Trulicity -- keine öffentliche
RCSB-Struktur gefunden), bleibt die bisherige "zu groß"-Fehlermeldung
stehen, statt eine geratene PDB-ID einzutragen.

Keys sind Wirkstoffnamen (klein geschrieben) -- werden sowohl direkt als
auch über brand_names.BRAND_TO_SUBSTANCE erreicht.
"""

_GLARGINE_CAVEAT = (
    " Zeigt die Struktur von normalem Wildtyp-Humaninsulin -- für diesen "
    "gentechnisch veränderten Insulin-Abkömmling (unterscheidet sich nur in "
    "wenigen Aminosäuren) liegt keine frei zugängliche Kristallstruktur vor."
)

LARGE_PEPTIDE_STRUCTURES: dict[str, dict] = {
    # GLP-1-Rezeptor-Agonisten -- jeweils die eigenständige (bzw. rezeptor-
    # gebundene) Peptidstruktur, kein Docking nötig.
    "semaglutide": {"pdb_id": "4ZGM", "chain_ids": None, "display_name": "Semaglutide"},
    "liraglutide": {"pdb_id": "4APD", "chain_ids": None, "display_name": "Liraglutide"},
    "tirzepatide": {"pdb_id": "7FIM", "chain_ids": None, "display_name": "Tirzepatide"},
    # Insulin und seine gängigen Analoga -- alle über die gleiche, schon
    # bewährte 4OGA-Struktur (Insulin an Site 1 seines Rezeptors, A+B-Kette
    # explizit ausgewählt, siehe docking.py/docs/stand.md).
    "insulin": {"pdb_id": "4OGA", "chain_ids": ["A", "B"], "display_name": "Insulin"},
    "insulin glargine": {
        "pdb_id": "4OGA", "chain_ids": ["A", "B"],
        "display_name": "Insulin glargin (Wildtyp-Struktur gezeigt)",
        "caveat": _GLARGINE_CAVEAT,
    },
    "insulin lispro": {
        "pdb_id": "4OGA", "chain_ids": ["A", "B"],
        "display_name": "Insulin lispro (Wildtyp-Struktur gezeigt)",
        "caveat": _GLARGINE_CAVEAT,
    },
    "insulin aspart": {
        "pdb_id": "4OGA", "chain_ids": ["A", "B"],
        "display_name": "Insulin aspart (Wildtyp-Struktur gezeigt)",
        "caveat": _GLARGINE_CAVEAT,
    },
}


def match(query: str, brand_to_substance: dict[str, str]) -> dict | None:
    """Prüft eine Rohanfrage direkt UND über die Markennamen-Übersetzung
    (z.B. "Ozempic" -> "semaglutide") gegen die obige Liste."""
    key = query.strip().lower()
    if key in LARGE_PEPTIDE_STRUCTURES:
        return LARGE_PEPTIDE_STRUCTURES[key]
    substance = brand_to_substance.get(key)
    if substance in LARGE_PEPTIDE_STRUCTURES:
        return LARGE_PEPTIDE_STRUCTURES[substance]
    return None
