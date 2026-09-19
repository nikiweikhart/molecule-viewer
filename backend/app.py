from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chem import ResolveError, resolve
from chemspace import ChemicalSpaceError, build_chemical_space
from docking import DockingError, dock, pdb_ligand
from dynamics import run_md
from equation import EquationError, build_equation_reaction
from explain import explain
from peptide import PeptideError, build_peptide
from reactions import get_reaction, list_reactions

app = FastAPI()

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


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


@app.post("/api/resolve")
def api_resolve(req: ResolveRequest):
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


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
