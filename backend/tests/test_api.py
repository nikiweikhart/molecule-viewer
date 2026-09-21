"""Einfache Backend-Tests gegen die echten externen Dienste (PubChem, RCSB) --
kein Mocking, damit die Tests auch echte API-Änderungen dort auffangen (siehe
die schon einmal erlebte PubChem-Feldumbenennung in docs/stand.md). Dafür
brauchen sie eine Internetverbindung und sind langsamer als reine Unit-Tests.

Ausführen: aus backend/ heraus `pytest` (mit requirements-dev.txt installiert).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chem
from app import app

client = TestClient(app)

# Boltz-2 braucht eine separate venv (backend/.venv-boltz, Python 3.12 + ROCm-PyTorch,
# siehe docs/stand.md Phase 0) und eine echte GPU/Internetverbindung -- auf einer
# frischen Maschine (z.B. dem Deployment-Host) existiert die nicht. Der Erfolgstest
# wird dann übersprungen statt rot zu laufen; die reinen Validierungstests unten
# brauchen Boltz-2 gar nicht erst (Längenprüfung passiert vor dem Subprocess-Start).
_BOLTZ_AVAILABLE = (Path(__file__).resolve().parent.parent / ".venv-boltz" / "Scripts" / "boltz.exe").exists()


def test_resolve_water_by_name():
    resp = client.post("/api/resolve", json={"query": "water"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["atoms"]) > 0
    assert data["facts"]["formula"] in ("H2O", "OH2")


def test_resolve_direct_smiles():
    resp = client.post("/api/resolve", json={"query": "CCO"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["facts"]["formula"] == "C2H6O"


def test_resolve_formula():
    # C6H12O6 passt zu mehreren Stoffen bei PubChem (siehe docs/stand.md, Fallstrick 1) --
    # welcher genau gewählt wird, kann sich mit PubChems Datenbestand ändern, deshalb hier
    # nur die Formel selbst prüfen, nicht den genauen Namen oder ob eine Mehrdeutigkeits-
    # Notiz dabei ist.
    resp = client.post("/api/resolve", json={"query": "C6H12O6"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["facts"]["formula"] == "C6H12O6"


def test_resolve_unknown_query_returns_400():
    resp = client.post("/api/resolve", json={"query": "definitiv-kein-molekuel-xyz-123"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_resolve_brand_name_mexalen_is_paracetamol():
    # "Mexalen" ist der österreichische Markenname für Paracetamol -- PubChem kennt den
    # Markennamen selbst nicht zuverlässig, daher muss die Übersetzung aus
    # backend/brand_names.py greifen (siehe chem._resolve_to_names).
    resp = client.post("/api/resolve", json={"query": "Mexalen"})
    assert resp.status_code == 200
    data = resp.json()
    # PubChems Titel dafür ist "Acetaminophen" (US-Bezeichnung für Paracetamol) -- beide
    # zulassen, falls sich das mit PubChems Datenbestand mal ändert.
    assert data["common_name"].lower() in ("acetaminophen", "paracetamol")
    assert data["note"] is not None and "Markenname" in data["note"]


def test_resolve_brand_name_is_case_insensitive():
    resp = client.post("/api/resolve", json={"query": "mexalen"})
    assert resp.status_code == 200


def test_resolve_german_common_name_kochsalz_is_sodium_chloride():
    # "Kochsalz" ist der deutsche Alltagsname fuer Natriumchlorid -- PubChems
    # Namenssuche ist englisch-zentriert und kennt ihn nicht direkt, siehe
    # backend/common_names.py (gefunden per echtem 1000-Begriffe-Lasttest,
    # docs/stand.md). Muss ueber COMMON_NAME_TRANSLATIONS aufgeloest werden.
    resp = client.post("/api/resolve", json={"query": "Kochsalz"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["common_name"].lower() == "sodium chloride"
    assert data["note"] is not None and "gebräuchlicher Name" in data["note"]


def test_resolve_german_common_name_with_umlaut():
    # Echte Umlaute (nicht die ae/oe/ue-Ersatzschreibweise) muessen genauso
    # funktionieren -- beide Schreibweisen stehen als eigene Dict-Keys in
    # common_names.py.
    resp = client.post("/api/resolve", json={"query": "Essigsäure"})
    assert resp.status_code == 200
    assert resp.json()["common_name"].lower() == "acetic acid"


def test_resolve_complex_molecule_uses_embed_fallback():
    # Gerbsaeure (Tannic Acid, 122 Schweratome) scheitert mit RDKits
    # Standard-ETKDGv3-Einbettung zuverlässig (per Lasttest gefunden) --
    # chem._build_structure() muss automatisch mit useRandomCoords=True
    # nachfassen, statt sofort aufzugeben.
    resp = client.post("/api/resolve", json={"query": "gerbsaeure"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["common_name"].lower() == "tannic acid"
    assert len(data["atoms"]) > 0


def test_resolve_ozempic_uses_real_pdb_structure():
    # Seit 2026-09-20: Ozempic/Semaglutid (und andere große Peptid-Wirkstoffe) werden
    # VOR der normalen EmbedMolecule-Auflösung gegen large_peptides.py geprüft und
    # zeigen die reale RCSB-Struktur (4ZGM) statt an MAX_HEAVY_ATOMS zu scheitern.
    resp = client.post("/api/resolve", json={"query": "Ozempic"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["common_name"] == "Semaglutide"
    assert len(data["atoms"]) > 0


def test_resolve_large_peptide_brand_names():
    for query, expected_name in [
        ("Wegovy", "Semaglutide"),
        ("Mounjaro", "Tirzepatide"),
        ("Victoza", "Liraglutide"),
        ("insulin", "Insulin"),
    ]:
        resp = client.post("/api/resolve", json={"query": query})
        assert resp.status_code == 200, query
        assert resp.json()["common_name"] == expected_name, query


def test_resolve_insulin_analog_shows_caveat_about_wildtype_structure():
    # Lantus (Insulin glargin) unterscheidet sich strukturell leicht vom Wildtyp-Insulin,
    # das die gezeigte 4OGA-Struktur tatsächlich ist -- das muss im Hinweistext stehen,
    # nicht nur der Markenname übersetzt werden.
    resp = client.post("/api/resolve", json={"query": "Lantus"})
    assert resp.status_code == 200
    data = resp.json()
    assert "glargin" in data["common_name"].lower()
    assert "Wildtyp" in data["note"]


def test_resolve_dulaglutide_still_gives_too_large_error():
    # Trulicity/Dulaglutid ist bewusst NICHT in large_peptides.py, weil keine öffentliche
    # RCSB-Struktur dafür gefunden wurde -- fällt weiterhin auf die normale (scheiternde)
    # Auflösung zurück, statt eine geratene PDB-ID zu verwenden.
    resp = client.post("/api/resolve", json={"query": "Trulicity"})
    assert resp.status_code == 400


def test_resolve_heavy_atom_limit_via_direct_smiles():
    # Direkter Test von MAX_HEAVY_ATOMS in chem._build_structure(), unabhängig vom
    # Ozempic/Markennamen-Umweg oben -- ein simpler linearer Alkan-SMILES mit 155
    # Kohlenstoffen (> MAX_HEAVY_ATOMS=150) braucht kein PubChem, da RDKit direktes
    # SMILES zuerst versucht.
    resp = client.post("/api/resolve", json={"query": "C" * 155})
    assert resp.status_code == 400
    assert "groß" in resp.json()["error"]


def test_reactions_list_contains_esterification():
    resp = client.get("/api/reactions")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert "esterification" in ids


def test_equation_combustion_is_balanced():
    resp = client.post("/api/equation", json={"equation": "CH4 + O2 -> CO2 + H2O"})
    assert resp.status_code == 200
    data = resp.json()
    # 1 CH4 (5 Atome inkl. H) + 2 O2 (2 Atome) = 7 Schwer+H-Atome auf beiden Seiten.
    assert len(data["start"]["atoms"]) == len(data["end"]["atoms"])
    assert "2" in data["label"]  # der Koeffizient 2 muss irgendwo auftauchen (O2 oder H2O)
    # formula_label nutzt Summenformeln statt Stoffnamen, mit "*" vor jeder
    # Elementanzahl >1 als Escape-Konvention fürs Frontend (formatSubscripts()).
    assert "CH*4" in data["formula_label"]
    assert "O*2" in data["formula_label"]
    assert "CO*2" in data["formula_label"]
    assert "H*2O" in data["formula_label"]
    assert "*1" not in data["formula_label"]  # Elementanzahl 1 bleibt unmarkiert


def test_salt_ions_list_contains_known_entries():
    resp = client.get("/api/salt-ions")
    assert resp.status_code == 200
    data = resp.json()
    cation_keys = [c["key"] for c in data["cations"]]
    anion_keys = [a["key"] for a in data["anions"]]
    assert "aluminium" in cation_keys
    assert "sulfat" in anion_keys


def test_salt_aluminium_sulfat_is_two_to_three():
    resp = client.post("/api/salt", json={"cation": "aluminium", "anion": "sulfat"})
    assert resp.status_code == 200
    data = resp.json()
    # Al(+3) + SO4(-2) -> Kreuzregel ergibt Al2(SO4)3.
    assert data["formula_label"].replace("*", "") == "Al2(SO4)3"
    assert data["facts"]["formula"] == "Al2O12S3"


def test_salt_calcium_chlorid_is_one_to_two():
    resp = client.post("/api/salt", json={"cation": "calcium", "anion": "chlorid"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["formula_label"].replace("*", "") == "CaCl2"


def test_salt_unknown_ion_returns_400():
    resp = client.post("/api/salt", json={"cation": "unobtainium", "anion": "chlorid"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_equation_without_arrow_returns_400():
    resp = client.post("/api/equation", json={"equation": "CH4 + O2 CO2 + H2O"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_equation_impossible_returns_400():
    resp = client.post("/api/equation", json={"equation": "H2 -> O2"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_equation_predict_combustion():
    resp = client.post("/api/equation/predict", json={"reactants": ["CH4", "O2"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reaction_type"] == "Verbrennung"
    assert "CO*2" in data["formula_label"]
    assert "H*2O" in data["formula_label"]


def test_equation_predict_neutralisation():
    resp = client.post("/api/equation/predict", json={"reactants": ["HCl", "NaOH"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reaction_type"] == "Neutralisation (Säure-Base-Reaktion)"
    assert "H*2O" in data["formula_label"]


def test_equation_predict_metal_plus_acid():
    resp = client.post("/api/equation/predict", json={"reactants": ["zinc", "HCl"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reaction_type"] == "Metall + Säure"


def test_equation_predict_unrecognized_returns_400():
    # Eisen ist absichtlich nicht auto-erkannt (mehrdeutige Oxidationsstufe je
    # nach Reaktionspartner, siehe reaction_predict.py).
    resp = client.post("/api/equation/predict", json={"reactants": ["Fe", "Cl2"]})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_dock_3ptb_benzamidine():
    resp = client.post("/api/dock", json={"pdb_id": "3PTB", "ligand_query": "benzamidine"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reference_ligand"] == "BEN"
    assert len(data["affinities"]) > 0
    assert all(a < 0 for a in data["affinities"])  # gebundene Posen -> negative Energie


def test_dock_invalid_pdb_id_returns_400():
    resp = client.post("/api/dock", json={"pdb_id": "not-an-id", "ligand_query": "benzamidine"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_dock_unknown_pdb_id_returns_400():
    resp = client.post("/api/dock", json={"pdb_id": "ZZZZ", "ligand_query": "benzamidine"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_pdb_ligand_small_molecule():
    resp = client.post("/api/pdb-ligand", json={"pdb_id": "3PTB"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["common_name"].lower() == "benzamidine"
    assert len(data["atoms"]) > 0
    assert all("H" != a["element"] for a in data["atoms"])  # keine ergänzten H


def test_pdb_ligand_peptide_fallback():
    # 4ZGM hat keinen Klein-Molekül-Liganden, nur die Semaglutid-Peptidkette --
    # prüft die Längen-Heuristik in docking._find_ligand_lines().
    resp = client.post("/api/pdb-ligand", json={"pdb_id": "4ZGM"})
    assert resp.status_code == 200
    data = resp.json()
    assert "Peptid" in data["common_name"]
    assert len(data["atoms"]) > 100  # ein ~28-Reste-Peptid, nicht nur ein paar Atome


def test_pdb_ligand_explicit_chain_ids():
    # 4OGA: Insulin (Ketten A+B) an Site 1 seines Rezeptors. Kette F ist ein noch
    # kürzeres, aber zum Rezeptor gehörendes Peptid -- ohne explizite chain_ids
    # würde die Längen-Heuristik das fälschlich als "Ligand" wählen, siehe
    # docs/stand.md. Prüft außerdem, dass RDKit alle 3 echten Insulin-
    # Disulfidbrücken (A6-A11, A7-B7, A20-B19) über die Ketten hinweg findet.
    resp = client.post("/api/pdb-ligand", json={"pdb_id": "4OGA", "chain_ids": ["A", "B"]})
    assert resp.status_code == 200
    data = resp.json()
    assert "A+B" in data["common_name"]
    sulfur_count = sum(1 for a in data["atoms"] if a["element"] == "S")
    assert sulfur_count == 6


def test_pdb_ligand_unknown_chain_id_returns_400():
    resp = client.post("/api/pdb-ligand", json={"pdb_id": "4OGA", "chain_ids": ["Z"]})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_pdb_ligand_invalid_pdb_id_returns_400():
    resp = client.post("/api/pdb-ligand", json={"pdb_id": "not-an-id"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_peptide_oxytocin_by_curated_name():
    # Prüft auch die Disulfidbrücken-Heuristik (peptide._add_disulfide_if_two_cysteines):
    # Oxytocins 2 Cystein-Reste sollten über ein S-S-Bindungspaar verbunden sein.
    resp = client.post("/api/peptide", json={"name": "oxytocin"})
    assert resp.status_code == 200
    data = resp.json()
    assert "oxytocin" in data["common_name"].lower()
    assert data["facts"]["formula"].count("S") >= 1
    sulfur_indices = [i for i, a in enumerate(data["atoms"]) if a["element"] == "S"]
    assert len(sulfur_indices) == 2
    assert any(
        {b["a"], b["b"]} == set(sulfur_indices) for b in data["bonds"]
    )  # echte S-S-Bindung zwischen den beiden Schwefelatomen


def test_peptide_custom_sequence():
    resp = client.post("/api/peptide", json={"sequence": "YGGFM"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["atoms"]) > 0
    assert data["facts"]["formula"].startswith("C")


def test_peptide_too_long_returns_400():
    resp = client.post("/api/peptide", json={"sequence": "A" * 20})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_peptide_invalid_letters_returns_400():
    resp = client.post("/api/peptide", json={"sequence": "GXYZ1"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_peptide_unknown_name_returns_400():
    resp = client.post("/api/peptide", json={"name": "definitiv-kein-peptid"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_peptide_neither_name_nor_sequence_returns_400():
    resp = client.post("/api/peptide", json={})
    assert resp.status_code == 400
    assert "error" in resp.json()


@pytest.mark.skipif(not _BOLTZ_AVAILABLE, reason="braucht backend/.venv-boltz (Boltz-2), siehe docs/stand.md")
def test_fold_oxytocin_by_curated_name():
    # Echter GPU-Rechenlauf inkl. MSA-Server-Aufruf -- dauert ~30-70s (siehe
    # docs/stand.md, empirisch gemessen), deutlich langsamer als der Rest der
    # Test-Suite, aber gleiche "keine Mocks"-Linie wie überall sonst hier.
    resp = client.post("/api/fold", json={"name": "oxytocin"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["atoms"]) > 0
    assert data["confidence"] is not None
    assert "complex_plddt" in data["confidence"]
    assert data["facts"]["formula"]


def test_fold_too_long_sequence_returns_400():
    # Längenprüfung passiert vor dem Boltz-Subprocess-Start -- läuft daher auch
    # ohne .venv-boltz und ohne GPU/Internet, keine Slow-/Skip-Markierung nötig.
    resp = client.post("/api/fold", json={"sequence": "A" * 51})
    assert resp.status_code == 400
    assert "51" in resp.json()["error"]


def test_fold_neither_name_nor_sequence_returns_400():
    resp = client.post("/api/fold", json={})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_request_with_retry_recovers_from_429(monkeypatch):
    # Einzige Ausnahme von der "kein Mocking"-Linie oben: PubChem laesst sich
    # nicht auf Kommando drosseln, um einen echten 429 zu erzeugen -- gefunden
    # per echtem 1000-Begriffe-Lasttest (docs/stand.md), wo genau das
    # passierte und fälschlich wie ein "nicht gefunden" behandelt wurde, weil
    # _request_with_retry nur < 500 als "fertig, kein Retry" wertete. Hier
    # wird nur die Wrapper-Funktion selbst isoliert getestet, nicht PubChem.
    calls = []

    class FakeResponse:
        def __init__(self, status_code, headers=None):
            self.status_code = status_code
            self.headers = headers or {}

    def fake_get(url, timeout=10, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(429, headers={"Retry-After": "0"})
        return FakeResponse(200)

    monkeypatch.setattr(chem, "_RETRY_BACKOFF_S", 0.01)
    resp = chem._request_with_retry(fake_get, "https://example.invalid")
    assert resp.status_code == 200
    assert len(calls) == 2  # erster Versuch 429, zweiter (Retry) 200


def test_request_with_retry_gives_up_after_persistent_429(monkeypatch):
    def fake_get(url, timeout=10, **kwargs):
        class FakeResponse:
            status_code = 429
            headers = {}
        return FakeResponse()

    monkeypatch.setattr(chem, "_RETRY_BACKOFF_S", 0.01)
    with pytest.raises(chem.ResolveError):
        chem._request_with_retry(fake_get, "https://example.invalid")
