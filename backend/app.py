from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from brand_names import BRAND_TO_SUBSTANCE
from chem import ResolveError, resolve
from chemspace import ChemicalSpaceError, build_chemical_space
from docking import DockingError, dock, pdb_ligand
from large_peptides import match as match_large_peptide
from dynamics import run_md
from equation import EquationError, build_equation_reaction
from explain import explain
from folding import BOLTZ_AVAILABLE, FoldingError, build_folding
from peptide import PeptideError, build_peptide
from reactions import get_reaction, list_reactions

app = FastAPI()

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.middleware("http")
async def no_cache_static_files(request, call_next):
    # StaticFiles setzt sonst gar keinen Cache-Control-Header -- Browser dürfen
    # dann nach eigenem Ermessen aggressiv cachen (siehe docs/stand.md, mehrfach
    # als Fallstrick aufgetreten: alte app.js/style.css bleiben auch nach einem
    # Server-Neustart oder neuem Tab hängen). "no-cache" erzwingt eine bedingte
    # Anfrage (If-Modified-Since) bei jedem Laden -- kein Neu-Download, wenn die
    # Datei unverändert ist, aber Änderungen kommen sofort an statt erst nach
    # einem harten Reload.
    response = await call_next(request)
    if request.url.path == "/" or not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class ResolveRequest(BaseModel):
    query: str


class ExplainRequest(BaseModel):
    common_name: str
    iupac_name: str | None = None
    formula: str


class ChemicalSpaceRequest(BaseModel):
    queries: list[str]


class DockRequest(BaseModel):
    pdb_id: str
    ligand_query: str


class PdbLigandRequest(BaseModel):
    pdb_id: str
    hetero_code: str | None = None
    chain_ids: list[str] | None = None


class DynamicsRequest(BaseModel):
    query: str


class EquationRequest(BaseModel):
    equation: str


class PeptideRequest(BaseModel):
    name: str | None = None
    sequence: str | None = None


class FoldingRequest(BaseModel):
    name: str | None = None
    sequence: str | None = None


@app.post("/api/resolve")
def api_resolve(req: ResolveRequest):
    # Große Peptid-Wirkstoffe (Ozempic/Semaglutid & Co.) zuerst gegen die
    # kuratierte Liste bekannter, real gemessener Strukturen prüfen -- die
    # normale Auflösung (RDKit-EmbedMolecule) würde daran wegen
    # MAX_HEAVY_ATOMS ohnehin nur mit einer "zu groß"-Fehlermeldung
    # scheitern, siehe large_peptides.py.
    peptide_match = match_large_peptide(req.query, BRAND_TO_SUBSTANCE)
    if peptide_match is not None:
        try:
            result = pdb_ligand(peptide_match["pdb_id"], chain_ids=peptide_match.get("chain_ids"))
        except DockingError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        result["common_name"] = peptide_match["display_name"]
        if peptide_match.get("caveat"):
            result["note"] = f"{result['note']}{peptide_match['caveat']}"
        return result

    try:
        result = resolve(req.query)
    except ResolveError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return {
        "atoms": result.atoms,
        "bonds": result.bonds,
        "facts": result.facts,
        "common_name": result.common_name,
        "iupac_name": result.iupac_name,
        "note": result.note,
    }


@app.post("/api/explain")
def api_explain(req: ExplainRequest):
    return explain(req.common_name, req.iupac_name, req.formula)


@app.get("/api/reactions")
def api_list_reactions():
    return list_reactions()


@app.get("/api/reactions/{reaction_id}")
def api_get_reaction(reaction_id: str):
    data = get_reaction(reaction_id)
    if data is None:
        return JSONResponse(status_code=404, content={"error": "Unbekannte Reaktion."})
    return data


@app.post("/api/chemical-space")
def api_chemical_space(req: ChemicalSpaceRequest):
    try:
        return build_chemical_space(req.queries)
    except ChemicalSpaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/dock")
def api_dock(req: DockRequest):
    try:
        return dock(req.pdb_id, req.ligand_query)
    except DockingError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/pdb-ligand")
def api_pdb_ligand(req: PdbLigandRequest):
    try:
        return pdb_ligand(req.pdb_id, req.hetero_code, req.chain_ids)
    except DockingError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/dynamics")
def api_dynamics(req: DynamicsRequest):
    try:
        return run_md(req.query)
    except ResolveError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/equation")
def api_equation(req: EquationRequest):
    try:
        return build_equation_reaction(req.equation)
    except EquationError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/peptide")
def api_peptide(req: PeptideRequest):
    try:
        return build_peptide(req.name, req.sequence)
    except PeptideError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/fold")
def api_fold(req: FoldingRequest):
    try:
        return build_folding(req.name, req.sequence)
    except FoldingError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/api/fold-available")
def api_fold_available():
    # Lässt das Frontend den Boltz-2-Bereich proaktiv ausgrauen, wenn diese Instanz
    # (z.B. das öffentliche Deployment ohne lokale GPU) die Vorhersage gar nicht
    # ausführen kann -- siehe folding.BOLTZ_AVAILABLE.
    return {"available": BOLTZ_AVAILABLE}


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
