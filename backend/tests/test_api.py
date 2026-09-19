"""Einfache Backend-Tests gegen die echten externen Dienste (PubChem, RCSB) --
kein Mocking, damit die Tests auch echte API-Änderungen dort auffangen (siehe
die schon einmal erlebte PubChem-Feldumbenennung in docs/stand.md). Dafür
brauchen sie eine Internetverbindung und sind langsamer als reine Unit-Tests.

Ausführen: aus backend/ heraus `pytest` (mit requirements-dev.txt installiert).
"""

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


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


def test_equation_without_arrow_returns_400():
    resp = client.post("/api/equation", json={"equation": "CH4 + O2 CO2 + H2O"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_equation_impossible_returns_400():
    resp = client.post("/api/equation", json={"equation": "H2 -> O2"})
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
