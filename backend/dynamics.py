"""Molekulardynamik: ein Molekül unter einem echten Kraftfeld (RDKits MMFF94)
per Velocity-Verlet-Integration simulieren -- keine Interpolation, keine
Vortäuschung, echte numerische Lösung von Newtons Bewegungsgleichungen.

Bewusst kein OpenMM: OpenMM selbst hat saubere Windows-Wheels, aber die
Werkzeuge, die man bräuchte, um aus einem beliebigen SMILES automatisch
Kraftfeld-Parameter zu erzeugen (openmmforcefields/openff-toolkit), hängen
an AmberTools -- offiziell nur auf macOS/Linux getestet, nicht zuverlässig
per pip unter Windows installierbar (gleiches Problem wie AutoDock Vina,
siehe docking.py, nur ohne die "eine Binary laden"-Abkürzung). Stattdessen:
RDKits MMFF94-Kraftfeld (schon länger im Einsatz, siehe chem.py) liefert
über ForceField.CalcGrad() echte Gradienten -- genug für einen
selbstgeschriebenen Velocity-Verlet-Integrator. Bringt keine einzige neue
Abhängigkeit mit (nur RDKit + numpy, beide schon installiert).

Einheiten-System: Å, Femtosekunden, amu, kcal/mol (Standard in der
Chemie-MD-Literatur). Die Umrechnungskonstante von Kraft/Masse
(kcal/mol/Å/amu) zu Beschleunigung (Å/fs^2) ist sauber aus SI-Einheiten
hergeleitet (siehe ACC_CONST unten), keine geratene Zahl.

Schrittweite bewusst klein (0.1 fs statt der in Lehrbüchern oft genannten
0.5-1 fs): jene größeren Werte setzen üblicherweise Bindungslängen-
Constraints (SHAKE/RATTLE) voraus, die die schnellen X-H-Streck-
schwingungen einfrieren. Ohne solche Constraints (hier nicht
implementiert) ist unser einfacher Integrator bei JEDER getesteten
Schrittweite irgendwann numerisch instabil geworden (Testläufe: 0.2 fs
nach ~250 Schritten, 0.1 fs nach ~450, 0.05 fs nach ~450 -- kleinere
Schritte verschieben das Problem nur, lösen es nicht). Die eigentliche
Rettung ist **Force-Capping** (ACCEL_CAP unten): einzelne Beschleunigungs-
Spitzen (die entstehen, wenn zwei Atome sich in einem Integrationsschritt
zu nah kommen und MMFFs steile Abstoßungs-/Bindungsterme dann eine riesige
Kraft liefern) werden der Richtung nach erhalten, aber der Höhe nach
gekappt -- verhindert die Rückkopplungsschleife, die sonst zur Explosion
führt. Über 2000 Testschritte damit stabil (keine NaN mehr), pendelt sich
aber auf ein etwas höheres Energieniveau als das nominelle 300-K-Ziel ein
(~15 statt ~8 kcal/mol bei Ethanol) -- für eine visuelle Demo (sichtbares,
stabiles Wackeln) ausreichend, aber keine quantitativ exakte NVT-Simulation.
Siehe docs/stand.md für die Messwerte.
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

_THERMOSTAT_INTERVAL = 1
_THERMOSTAT_MIN_SCALE = 0.97
_THERMOSTAT_MAX_SCALE = 1.03
_ACCEL_CAP = 0.05  # Å/fs^2 -- siehe Modul-Docstring


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


def run_md(
    query: str,
    temperature: float = 300.0,
    n_steps: int = 800,
    dt_fs: float = 0.1,
    record_every: int = 3,
) -> dict:
    info, _note = chem._resolve_to_names(query)
    mol = _embed_and_optimize(info.smiles)

    props = AllChem.MMFFGetMoleculeProperties(mol)
    ff = AllChem.MMFFGetMoleculeForceField(mol, props)
    ff.Initialize()

    n_atoms = mol.GetNumAtoms()
    conformer = mol.GetConformer()
    pos = np.array([list(conformer.GetAtomPosition(i)) for i in range(n_atoms)])
    masses = np.array([mol.GetAtomWithIdx(i).GetMass() for i in range(n_atoms)])
    elements = [mol.GetAtomWithIdx(i).GetSymbol() for i in range(n_atoms)]
    bonds = [{"a": b.GetBeginAtomIdx(), "b": b.GetEndAtomIdx()} for b in mol.GetBonds()]

    rng = np.random.default_rng(0)
    vel = _maxwell_boltzmann_velocities(masses, temperature, rng)

    def accel_at(flat_pos: np.ndarray) -> np.ndarray:
        grad = np.array(ff.CalcGrad(list(flat_pos)), dtype=float).reshape(n_atoms, 3)
        a = -grad * ACC_CONST / masses[:, None]
        # Force-Capping: Richtung erhalten, Betrag kappen (siehe Modul-Docstring).
        magnitude = np.linalg.norm(a, axis=1, keepdims=True)
        scale = np.minimum(1.0, _ACCEL_CAP / np.maximum(magnitude, 1e-12))
        return a * scale

    accel = accel_at(pos.flatten())
    target_total_ke = 1.5 * n_atoms * KB * temperature  # 3 DOF/Atom, Äquipartition

    frames = [pos.copy()]
    energies = []

    for step in range(n_steps):
        pos = pos + vel * dt_fs + 0.5 * accel * dt_fs**2
        new_accel = accel_at(pos.flatten())
        vel = vel + 0.5 * (accel + new_accel) * dt_fs
        accel = new_accel

        if step % _THERMOSTAT_INTERVAL == 0:
            current_ke = 0.5 * np.sum(masses[:, None] * vel**2) / ACC_CONST
            if current_ke > 1e-8:
                scale = np.sqrt(target_total_ke / current_ke)
                scale = min(max(scale, _THERMOSTAT_MIN_SCALE), _THERMOSTAT_MAX_SCALE)
                vel *= scale

        if step % record_every == 0:
            frames.append(pos.copy())
            potential = ff.CalcEnergy(list(pos.flatten()))
            kinetic = 0.5 * np.sum(masses[:, None] * vel**2) / ACC_CONST
            energies.append(potential + kinetic)

    frame_dicts = [
        [{"x": round(float(x), 3), "y": round(float(y), 3), "z": round(float(z), 3)} for x, y, z in frame]
        for frame in frames
    ]

    return {
        "elements": elements,
        "bonds": bonds,
        "frames": frame_dicts,
        "temperature": temperature,
        "steps_simulated": n_steps,
        "fs_simulated": round(n_steps * dt_fs, 1),
        "energies": [round(e, 2) for e in energies],
    }


if __name__ == "__main__":
    result = run_md("ethanol")
    print("atoms:", len(result["elements"]))
    print("bonds:", len(result["bonds"]))
    print("frames:", len(result["frames"]))
    print("fs simulated:", result["fs_simulated"])
    energies = result["energies"]
    print("energy range (kcal/mol):", min(energies), "..", max(energies))
    print("first 5 energies:", energies[:5])
    print("last 5 energies:", energies[-5:])
