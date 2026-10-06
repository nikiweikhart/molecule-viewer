"""Molekulardynamik: ein Molekül unter einem echten Kraftfeld (RDKits MMFF94)
per Velocity-Verlet-Integration simulieren -- keine Interpolation, keine
Vortäuschung, echte numerische Lösung von Newtons Bewegungsgleichungen.

Bewusst kein OpenMM: OpenMM selbst hat saubere Windows-Wheels, aber die
Werkzeuge, die man bräuchte, um aus einem beliebigen SMILES automatisch
Kraftfeld-Parameter zu erzeugen (openmmforcefields/openff-toolkit), hängen
an AmberTools -- offiziell nur auf macOS/Linux getestet, nicht zuverlässig
per pip unter Windows installierbar. Stattdessen: RDKits MMFF94-Kraftfeld
liefert über ForceField.CalcGrad() echte Gradienten -- genug für einen
selbstgeschriebenen Integrator. Keine zusätzliche Abhängigkeit (RDKit + numpy).

Einheiten-System: Å, Femtosekunden, amu, kcal/mol. ACC_CONST rechnet
kcal/mol/Å pro amu in Å/fs^2 um (Herleitung unten).

**RDKit-Fallstrick (2026-10-06 gefunden, war die eigentliche Ursache der
früheren Instabilität):** ForceField.CalcGrad(pos) rechnet mit einem intern
gecachten Abstands-Array, das nur CalcEnergy(pos) neu befüllt. Ruft man
CalcGrad(pos) mehrmals hintereinander mit neuen Positionen auf (genau das,
was ein MD-Integrator tut), bekommt man Gradienten zu teils veralteten
Abständen -- Kräfte, die nicht zur Energie passen. Folge: die Gesamtenergie
stieg unabhängig von der Schrittweite (selbst bei 0,002 fs) um ~10 kcal/mol
in 5 fs, und jede Simulation explodierte irgendwann. Früher wurde das mit
"Force-Capping" überdeckt. Fix: vor jedem CalcGrad(pos) einmal
CalcEnergy(pos) an derselben Stelle (_energy_and_accel). Damit bleibt die
Gesamtenergie ohne Thermostat auf ~1e-4 kcal/mol erhalten, das Capping ist weg.

Zwei Modi:
- **Mit Bindungs-Constraints (Standard):** alle Bindungen zu Wasserstoff
  werden per RATTLE (Andersen 1983, Velocity-Verlet-Variante von SHAKE) auf
  ihrer Gleichgewichtslänge festgehalten. Die schnellste Schwingung (X-H,
  ~10 fs Periode) fällt damit weg, 1 fs pro Schritt ist stabil -> 800 fs
  simuliert, sichtbar sind langsamere Bewegungen (Drehungen, Biegungen).
- **Ohne Constraints:** freie X-H-Schwingungen ("H-Wackeln"), kleiner
  Zeitschritt, 80 fs simuliert, fein abgetastet, damit die Schwingung in
  der Animation sichtbar bleibt.

Temperatur über einen Berendsen-Thermostat (Kopplungszeit 100 fs), mit
korrekter Zahl der Freiheitsgrade (3N - Constraints - 3 für die
Schwerpunktsbewegung). Keine quantitativ exakte NVT-Statistik (Berendsen
erzeugt kein exaktes kanonisches Ensemble), aber physikalisch sauber genug
für eine Demo -- und ohne Tricks.
"""

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

import chem

# kcal/mol/Å pro amu -> Å/fs^2. Herleitung: 1 kcal/mol = 6.9477e-21 J
# (pro Teilchen), 1 Å = 1e-10 m, 1 amu = 1.6605e-27 kg, 1 fs = 1e-15 s.
# a[m/s^2] = F[N]/m[kg] = (6.9477e-21/1e-10) / 1.6605e-27 = 4.1842e16
# a[Å/fs^2] = a[m/s^2] * 1e10 (m->Å) * 1e-30 (s^2->fs^2) = 4.1842e-4
ACC_CONST = 4.184e-4
KB = 1.987204e-3  # kcal/(mol*K)

_BERENDSEN_TAU_FS = 100.0
# Vor der Aufnahme: kurz mit straffer Kopplung einschwingen. Die Startenergie
# verteilt sich sonst erst zur Hälfte in potenzielle Energie (Äquipartition),
# und gerade der kurze 80-fs-Modus würde dann bei ~200 statt 300 K laufen.
_EQUILIBRATION_FS = 100.0
_EQUILIBRATION_TAU_FS = 10.0
_RATTLE_TOL = 1e-8
_RATTLE_MAX_ITER = 500

# (dt_fs, n_steps, record_every) pro Modus -- ~270 Frames in beiden Fällen.
_SETTINGS = {
    True: (1.0, 800, 3),    # mit Constraints: 800 fs
    False: (0.1, 800, 3),   # ohne: 80 fs, feine Abtastung fürs H-Wackeln
}


def _embed_and_optimize(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise chem.ResolveError(f"SMILES '{smiles}' konnte nicht gelesen werden.")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) != 0:
        raise chem.ResolveError("Konnte keine 3D-Startstruktur berechnen.")
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _maxwell_boltzmann_velocities(masses: np.ndarray, temperature: float, rng) -> np.ndarray:
    # v_std pro Achse aus Äquipartition: 0.5*m*v^2/ACC_CONST = 0.5*kT
    sigma = np.sqrt(KB * temperature * ACC_CONST / masses)[:, None]
    return rng.normal(0.0, 1.0, size=(len(masses), 3)) * sigma


def _kinetic_energy(masses: np.ndarray, vel: np.ndarray) -> float:
    return float(0.5 * np.sum(masses[:, None] * vel**2) / ACC_CONST)


def _hydrogen_bond_constraints(mol, pos: np.ndarray) -> list[tuple[int, int, float]]:
    constraints = []
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if mol.GetAtomWithIdx(i).GetAtomicNum() == 1 or mol.GetAtomWithIdx(j).GetAtomicNum() == 1:
            constraints.append((i, j, float(np.linalg.norm(pos[i] - pos[j]))))
    return constraints


def _rattle_positions(pos_new, vel_half, pos_old, inv_m, constraints, dt):
    """SHAKE-Schritt: neue Positionen (und die halben Geschwindigkeiten
    passend dazu) so korrigieren, dass jede Constraint-Länge wieder stimmt.
    Korrektur entlang der ALTEN Bindungsrichtung, iterativ (Gauss-Seidel)."""
    for _ in range(_RATTLE_MAX_ITER):
        converged = True
        for i, j, d in constraints:
            r = pos_new[i] - pos_new[j]
            diff = d * d - r @ r
            if abs(diff) > _RATTLE_TOL * d * d:
                converged = False
                r_old = pos_old[i] - pos_old[j]
                g = diff / (2.0 * (inv_m[i] + inv_m[j]) * (r @ r_old))
                pos_new[i] += g * inv_m[i] * r_old
                pos_new[j] -= g * inv_m[j] * r_old
                vel_half[i] += g * inv_m[i] * r_old / dt
                vel_half[j] -= g * inv_m[j] * r_old / dt
        if converged:
            return
    raise RuntimeError("RATTLE (Positionen) konvergiert nicht.")


def _rattle_velocities(pos, vel, inv_m, constraints):
    """Geschwindigkeits-Schritt: Relativgeschwindigkeit entlang jeder
    festgehaltenen Bindung auf null bringen (sonst würde sich die Länge im
    nächsten Schritt sofort wieder ändern)."""
    for _ in range(_RATTLE_MAX_ITER):
        converged = True
        for i, j, d in constraints:
            r = pos[i] - pos[j]
            rv = r @ (vel[i] - vel[j])
            if abs(rv) > _RATTLE_TOL * d:
                converged = False
                k = rv / ((inv_m[i] + inv_m[j]) * d * d)
                vel[i] -= k * inv_m[i] * r
                vel[j] += k * inv_m[j] * r
        if converged:
            return
    raise RuntimeError("RATTLE (Geschwindigkeiten) konvergiert nicht.")


def simulate(
    mol,
    temperature: float = 300.0,
    constraints_on: bool = True,
    n_steps: int | None = None,
    dt_fs: float | None = None,
    record_every: int | None = None,
    thermostat: bool = True,
    seed: int = 0,
) -> dict:
    """Kern der Simulation, getrennt von der Namensauflösung (testbar ohne
    PubChem). `thermostat=False` = reine NVE-Dynamik, zum Prüfen der
    Energieerhaltung."""
    default_dt, default_steps, default_record = _SETTINGS[constraints_on]
    dt_fs = dt_fs or default_dt
    n_steps = n_steps or default_steps
    record_every = record_every or default_record

    props = AllChem.MMFFGetMoleculeProperties(mol)
    ff = AllChem.MMFFGetMoleculeForceField(mol, props)
    ff.Initialize()

    n_atoms = mol.GetNumAtoms()
    pos = np.array(mol.GetConformer().GetPositions(), dtype=float)
    masses = np.array([mol.GetAtomWithIdx(i).GetMass() for i in range(n_atoms)])
    inv_m = 1.0 / masses

    def energy_and_accel(p: np.ndarray) -> tuple[float, np.ndarray]:
        flat = list(p.flatten())
        # CalcEnergy zuerst -- befüllt RDKits Abstands-Cache für genau diese
        # Positionen, sonst rechnet CalcGrad mit veralteten Abständen (siehe
        # Modul-Docstring).
        energy = ff.CalcEnergy(flat)
        grad = np.array(ff.CalcGrad(flat), dtype=float).reshape(n_atoms, 3)
        return energy, -grad * ACC_CONST * inv_m[:, None]

    constraints = _hydrogen_bond_constraints(mol, pos) if constraints_on else []
    dof = max(3 * n_atoms - len(constraints) - 3, 1)
    target_ke = 0.5 * dof * KB * temperature

    rng = np.random.default_rng(seed)
    vel = _maxwell_boltzmann_velocities(masses, temperature, rng)
    vel -= np.sum(masses[:, None] * vel, axis=0) / masses.sum()  # kein Schwerpunkts-Drift
    if constraints:
        _rattle_velocities(pos, vel, inv_m, constraints)
    vel *= np.sqrt(target_ke / max(_kinetic_energy(masses, vel), 1e-12))

    potential, accel = energy_and_accel(pos)

    def step(pos, vel, accel, tau):
        vel_half = vel + 0.5 * accel * dt_fs
        new_pos = pos + vel_half * dt_fs
        if constraints:
            _rattle_positions(new_pos, vel_half, pos, inv_m, constraints, dt_fs)
        potential, new_accel = energy_and_accel(new_pos)
        vel = vel_half + 0.5 * new_accel * dt_fs
        if constraints:
            _rattle_velocities(new_pos, vel, inv_m, constraints)
        if tau is not None:
            ke = _kinetic_energy(masses, vel)
            if ke > 1e-12:
                vel *= np.sqrt(max(1.0 + (dt_fs / tau) * (target_ke / ke - 1.0), 0.0))
        if not np.isfinite(new_pos).all():
            raise RuntimeError("Simulation numerisch instabil geworden.")
        return new_pos, vel, new_accel, potential

    if thermostat:
        for _ in range(int(round(_EQUILIBRATION_FS / dt_fs))):
            pos, vel, accel, potential = step(pos, vel, accel, _EQUILIBRATION_TAU_FS)

    frames = [pos.copy()]
    energies = [potential + _kinetic_energy(masses, vel)]
    production_tau = _BERENDSEN_TAU_FS if thermostat else None
    for i in range(1, n_steps + 1):
        pos, vel, accel, potential = step(pos, vel, accel, production_tau)
        if i % record_every == 0:
            frames.append(pos.copy())
            energies.append(potential + _kinetic_energy(masses, vel))

    return {
        "frames": frames,
        "energies": energies,
        "dt_fs": dt_fs,
        "n_steps": n_steps,
        "n_constraints": len(constraints),
    }


def run_md(query: str, temperature: float = 300.0, constraints: bool = True) -> dict:
    info, _note = chem._resolve_to_names(query)
    mol = _embed_and_optimize(info.smiles)
    result = simulate(mol, temperature=temperature, constraints_on=constraints)

    elements = [atom.GetSymbol() for atom in mol.GetAtoms()]
    bonds = [{"a": b.GetBeginAtomIdx(), "b": b.GetEndAtomIdx()} for b in mol.GetBonds()]
    frame_dicts = [
        [{"x": round(float(x), 3), "y": round(float(y), 3), "z": round(float(z), 3)} for x, y, z in frame]
        for frame in result["frames"]
    ]
    return {
        "elements": elements,
        "bonds": bonds,
        "frames": frame_dicts,
        "temperature": temperature,
        "steps_simulated": result["n_steps"],
        "fs_simulated": round(result["n_steps"] * result["dt_fs"], 1),
        "constraints": constraints,
        "energies": [round(e, 2) for e in result["energies"]],
    }


if __name__ == "__main__":
    import time

    mol = _embed_and_optimize("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")  # Koffein
    for on in (True, False):
        for dt in ((0.5, 1.0, 2.0) if on else (0.1, 0.25, 0.5)):
            t0 = time.time()
            r = simulate(Chem.Mol(mol), constraints_on=on, dt_fs=dt, n_steps=int(400 / dt), record_every=10, thermostat=False)
            e = np.array(r["energies"])
            print(f"constraints={on} dt={dt} fs, 400 fs NVE: Drift {e[-1] - e[0]:+.4f}, "
                  f"Schwankung {e.std():.4f} kcal/mol, {time.time() - t0:.1f}s")
