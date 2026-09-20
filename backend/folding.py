"""Echte ML-basierte Protein-Struktur-Vorhersage über Boltz-2
(github.com/jwohlwend/boltz, AlphaFold3-artige Architektur) -- im Gegensatz zu
peptide.py (reines RDKit-Konformer-Embedding, MAX_RESIDUES=15, ausdrücklich
KEINE echte Faltung) sagt Boltz-2 die Struktur aus einem trainierten Modell
vorher, inklusive pro-Rest-Konfidenz (pLDDT-artig).

Läuft NICHT in backend/.venv (Python 3.14) -- Boltz-2 braucht Python
>=3.10,<3.13, siehe docs/stand.md Phase 0. Stattdessen eine separate venv
backend/.venv-boltz (Python 3.12) mit ROCm-PyTorch für die RX 7900 XTX
(gfx1100). Dieses Modul ruft den `boltz`-Konsolenbefehl aus dieser venv per
subprocess auf (gleiches Muster wie vina.exe/meeko in docking.py -- ein
externes Werkzeug, kein Python-Import), und liest das Ergebnis (CIF-Struktur
+ Konfidenz-JSON) wieder ein.

Bewusst kein Bau eines RDKit-Mols direkt aus der Sequenz (anders als
peptide.py) -- die 3D-Koordinaten kommen komplett aus Boltz-2s Vorhersage,
nicht aus einem Kraftfeld-Konformer. Bindungen werden trotzdem per RDKits
Abstands-Heuristik (ConnectTheDots) aus den vorhergesagten Positionen
geraten, gleiches Vorgehen wie bei PDB-Liganden in docking.py -- Boltz-2
selbst liefert keine explizite Bindungsliste.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import gemmi
from rdkit import Chem

import docking  # _hill_formula / _atoms_molweight wiederverwenden

BACKEND_DIR = Path(__file__).parent
BOLTZ_VENV = BACKEND_DIR / ".venv-boltz" / "Scripts"
BOLTZ_BINARY = BOLTZ_VENV / "boltz.exe"

# Boltz-2 braucht eine lokale GPU (siehe docs/stand.md, Phase 0 -- ROCm auf Nikis
# AMD-Karte) und eine ~5,8 GB Gewichte-venv, die auf einem normalen kostenlosen/
# günstigen Hosting-Tier nicht existiert. Statt das Feature dort mit einem
# kryptischen Absturz enden zu lassen, wird es sauber erkannt (BOLTZ_AVAILABLE)
# und mit einer erklärenden, öffentlichkeitstauglichen Meldung abgefangen --
# app.py exponiert das zusätzlich über GET /api/fold-available, damit das
# Frontend den Bereich proaktiv ausgrauen kann statt erst nach einem Fehlversuch.
BOLTZ_AVAILABLE = BOLTZ_BINARY.exists()
_UNAVAILABLE_MESSAGE = (
    "Protein-Struktur-Vorhersage (Boltz-2) läuft nur auf Nikis eigenem Rechner mit "
    "lokaler GPU -- auf dieser öffentlichen Instanz nicht verfügbar."
)

# Empirisch getestet auf dieser Hardware (siehe docs/stand.md, 2026-09-20):
# 36 Reste ~50s, 50 Reste ~73s -- deutlich unter TIMEOUT_SECONDS, Skalierung
# mit der Länge ist spürbar überlinear, aber nicht explosionsartig. 50 bleibt
# als Grenze stehen, weil eine Fortsetzung dieses Trends (statt linear
# extrapoliert) bei deutlich längeren Sequenzen an das 600s-Zeitbudget
# herankommen könnte -- konservativ statt bis an den Rand ausgereizt.
MAX_RESIDUES = 50

_ONE_LETTER_CODES = set("ACDEFGHIKLMNPQRSTVWY")

# Gleiche kuratierte Kurz-Peptide wie in peptide.py, hier nur zur bequemen
# Wiederverwendung fürs Testen -- keine eigene, größere Namensliste (Boltz-2
# braucht keine Namensauflösung, nur eine Sequenz).
_KNOWN_PEPTIDES = {
    "oxytocin": "CYIQNCPLG",
    "vasopressin": "CYFQNCPRG",
    "met-enkephalin": "YGGFM",
    "met enkephalin": "YGGFM",
    "leu-enkephalin": "YGGFL",
    "leu enkephalin": "YGGFL",
}

# Boltz-2 selbst hat kein hartes Zeitlimit -- diese Ausbaustufe begrenzt es
# selbst, damit eine falsch eingeschätzte Sequenzlänge nicht endlos hängt.
TIMEOUT_SECONDS = 600


class FoldingError(Exception):
    pass


def _resolve_sequence(name: str | None, sequence: str | None) -> tuple[str, str]:
    if sequence:
        seq = sequence.strip().upper()
        if not seq:
            raise FoldingError("Sequenz ist leer.")
        invalid = sorted(set(seq) - _ONE_LETTER_CODES)
        if invalid:
            raise FoldingError(
                f"Ungültige(r) Aminosäure-Code(s): {', '.join(invalid)}. Erlaubt sind "
                "die 20 Standard-Ein-Buchstaben-Codes (z.B. G, A, C, Y, ...)."
            )
        return seq, seq

    if name:
        key = name.strip().lower()
        if key in _KNOWN_PEPTIDES:
            return _KNOWN_PEPTIDES[key], name.strip()
        known = sorted({"Oxytocin", "Vasopressin", "Met-Enkephalin", "Leu-Enkephalin"})
        raise FoldingError(
            f"'{name}' ist nicht in der kuratierten Liste ({', '.join(known)}). "
            "Alternativ die Sequenz direkt als Ein-Buchstaben-Code eingeben."
        )

    raise FoldingError("Weder Name noch Sequenz angegeben.")


def _run_boltz(fasta_path: Path, out_dir: Path) -> subprocess.CompletedProcess:
    if not BOLTZ_BINARY.exists():
        raise FoldingError(_UNAVAILABLE_MESSAGE)
    cmd = [
        str(BOLTZ_BINARY), "predict", str(fasta_path),
        "--out_dir", str(out_dir),
        "--use_msa_server",
        "--recycling_steps", "3",
        "--diffusion_samples", "1",
        "--override",
        # cuequivariance ist NVIDIA/CUDA-spezifisch (kein ROCm-Support) -- ohne
        # dieses Flag bricht jede Vorhersage auf der AMD-GPU sofort mit
        # "ModuleNotFoundError: No module named 'cuequivariance_torch'" ab
        # (siehe docs/stand.md, Phase 0).
        "--no_kernels",
    ]
    env = {**os.environ, "TORCH_BLAS_PREFER_HIPBLASLT": "1"}  # AMD-Empfehlung für RDNA3+PyTorch<2.14
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, env=env,
        )
    except subprocess.TimeoutExpired:
        raise FoldingError(
            f"Boltz-2-Vorhersage hat das Zeitbudget von {TIMEOUT_SECONDS}s "
            "überschritten -- Sequenz vermutlich zu lang für diese Hardware."
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise FoldingError(f"Boltz-2-Vorhersage fehlgeschlagen: {detail[-1500:]}")
    return result


def _find_output_files(out_dir: Path, stem: str) -> tuple[Path, Path | None]:
    """Sucht die Ausgabedateien per rglob statt über einen starr angenommenen
    Ordnerpfad -- Boltz-Versionen benennen den Ergebnisordner unterschiedlich
    (z.B. mit/ohne "boltz_results_"-Präfix)."""
    candidates = sorted(out_dir.rglob(f"{stem}_model_0.cif"))
    if not candidates:
        raise FoldingError("Boltz-2 hat keine Struktur-Datei erzeugt.")
    cif_path = candidates[0]
    pred_dir = cif_path.parent

    confidence_candidates = sorted(pred_dir.glob(f"confidence_{stem}_model_0.json"))
    confidence_path = confidence_candidates[0] if confidence_candidates else None
    return cif_path, confidence_path


def _cif_to_pdb_block(cif_path: Path, workdir: Path) -> str:
    structure = gemmi.read_structure(str(cif_path))
    structure.setup_entities()
    pdb_path = workdir / "predicted.pdb"
    structure.write_pdb(str(pdb_path))
    return pdb_path.read_text(encoding="utf-8")


def build_folding(name: str | None = None, sequence: str | None = None) -> dict:
    seq, display_name = _resolve_sequence(name, sequence)

    if len(seq) < 2:
        raise FoldingError("Sequenz braucht mindestens 2 Aminosäuren.")
    if len(seq) > MAX_RESIDUES:
        raise FoldingError(
            f"Sequenz hat {len(seq)} Reste -- diese Ausbaustufe ist auf "
            f"{MAX_RESIDUES} begrenzt (siehe docs/stand.md: oberhalb dieser Länge "
            "wurde die Laufzeit auf dieser Hardware noch nicht geprüft)."
        )

    with tempfile.TemporaryDirectory(prefix="boltz_") as tmp:
        workdir = Path(tmp)
        stem = "input"
        fasta_path = workdir / f"{stem}.fasta"
        # Kein "|empty" im Header -- das würde die MSA für diese Kette explizit
        # abschalten. --use_msa_server soll sie stattdessen wirklich berechnen
        # (bessere Vorhersagequalität als ganz ohne MSA).
        fasta_path.write_text(f">A|protein\n{seq}\n", encoding="utf-8")

        start = time.monotonic()
        _run_boltz(fasta_path, workdir)
        elapsed = time.monotonic() - start

        cif_path, confidence_path = _find_output_files(workdir, stem)
        pdb_block = _cif_to_pdb_block(cif_path, workdir)

        confidence = None
        if confidence_path is not None:
            confidence = json.loads(confidence_path.read_text(encoding="utf-8"))

    mol = Chem.MolFromPDBBlock(pdb_block, sanitize=False, removeHs=False, proximityBonding=True)
    if mol is None or mol.GetNumAtoms() == 0:
        raise FoldingError("Konnte die von Boltz-2 vorhergesagte Struktur nicht als Molekül lesen.")

    conformer = mol.GetConformer()
    atoms = []
    elements = []
    for atom in mol.GetAtoms():
        pos = conformer.GetAtomPosition(atom.GetIdx())
        elements.append(atom.GetSymbol())
        atoms.append({"element": atom.GetSymbol(), "x": pos.x, "y": pos.y, "z": pos.z})
    bonds = [{"a": b.GetBeginAtomIdx(), "b": b.GetEndAtomIdx()} for b in mol.GetBonds()]

    facts = {
        "formula": docking._hill_formula(elements),
        "molweight": docking._atoms_molweight(elements),
        "logp": "–",
        "tpsa": "–",
        "h_donors": "–",
        "h_acceptors": "–",
        "rotatable_bonds": "–",
    }

    confidence_note = ""
    if confidence:
        plddt = confidence.get("complex_plddt")
        ptm = confidence.get("ptm")
        score = confidence.get("confidence_score")
        parts = []
        if plddt is not None:
            parts.append(f"pLDDT (Komplex) {plddt * 100:.0f}/100")
        if ptm is not None:
            parts.append(f"pTM {ptm:.2f}")
        if score is not None:
            parts.append(f"Gesamt-Konfidenz {score:.2f}")
        if parts:
            confidence_note = " Konfidenz der Vorhersage: " + ", ".join(parts) + "."

    note = (
        f"Echte ML-Struktur-Vorhersage mit Boltz-2 (keine Kraftfeld-Näherung wie "
        f"bei den kleinen Peptiden über /api/peptide) -- Berechnung dauerte "
        f"{elapsed:.0f}s auf dieser Hardware. Bindungsordnung aus den vorhergesagten "
        "3D-Positionen geschätzt (RDKit-Abstandsheuristik), da Boltz-2 selbst keine "
        "Bindungsliste liefert." + confidence_note
    )

    return {
        "atoms": atoms,
        "bonds": bonds,
        "facts": facts,
        "common_name": f"{display_name} (Boltz-2-Vorhersage, {len(seq)} Reste)",
        "iupac_name": None,
        "note": note,
        "confidence": confidence,
    }


if __name__ == "__main__":
    import sys

    seq_arg = sys.argv[1] if len(sys.argv) > 1 else None
    name_arg = "oxytocin" if seq_arg is None else None
    print(f"--- build_folding(name={name_arg!r}, sequence={seq_arg!r}) ---")
    t0 = time.monotonic()
    try:
        result = build_folding(name=name_arg, sequence=seq_arg)
        print("common_name:", result["common_name"])
        print("facts:", result["facts"])
        print("atoms:", len(result["atoms"]), "bonds:", len(result["bonds"]))
        print("note:", result["note"])
        print("confidence:", result["confidence"])
    except FoldingError as e:
        print("ERROR:", e)
    print(f"Gesamtzeit inkl. Subprozess-Start: {time.monotonic() - t0:.1f}s")
