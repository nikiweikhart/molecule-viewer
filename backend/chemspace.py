"""Chemischer Raum: viele Moleküle auf einmal nach struktureller Ähnlichkeit
(Morgan-Fingerprints) auf einer 2D-Karte anordnen und gruppieren.

Bewusst ohne scikit-learn: numpy ist ohnehin schon als RDKit-Abhängigkeit
installiert, und bei den kleinen Molekül-Mengen, um die es hier geht (ein
Textfeld mit einer Handvoll bis ein paar Dutzend Zeilen), ist eine simple,
deterministische PCA+k-Means-Implementierung robuster als t-SNE/UMAP, die
bei wenigen Punkten Hyperparameter-Tuning brauchen und instabil werden.
"""

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator

import chem

_FP_GENERATOR = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=1024)


class ChemicalSpaceError(Exception):
    pass


def _fingerprint(mol) -> np.ndarray:
    return np.array(_FP_GENERATOR.GetFingerprint(mol), dtype=float)


def _pca_2d(fingerprints: np.ndarray) -> np.ndarray:
    """Deterministische PCA auf 2 Komponenten per SVD — kein scikit-learn nötig."""
    centered = fingerprints - fingerprints.mean(axis=0)
    u, s, _vt = np.linalg.svd(centered, full_matrices=False)
    return u[:, :2] * s[:2]


def _kmeans_labels(coords: np.ndarray, k: int, iterations: int = 50) -> list[int]:
    """Lloyd-Iteration mit deterministischer Initialisierung (Punkte nach 1.
    Hauptkomponente sortiert, k gleichmäßig verteilte Startzentren) — keine
    Zufallszahlen, also über mehrere Aufrufe hinweg reproduzierbar."""
    n = coords.shape[0]
    if k <= 1:
        return [0] * n

    order = np.argsort(coords[:, 0])
    init_indices = order[np.linspace(0, n - 1, k, dtype=int)]
    centroids = coords[init_indices].copy()
    labels = np.full(n, -1)

    for _ in range(iterations):
        dists = np.linalg.norm(coords[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = dists.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster_idx in range(k):
            members = coords[labels == cluster_idx]
            if len(members) > 0:
                centroids[cluster_idx] = members.mean(axis=0)

    return labels.tolist()


def _cluster_count(n: int) -> int:
    if n < 4:
        return 1
    return min(6, max(2, n // 3))


def build_chemical_space(queries: list[str]) -> dict:
    resolved = []  # (query, _NameInfo, mol)
    failed = []

    for query in queries:
        query = query.strip()
        if not query:
            continue
        try:
            info, _note = chem._resolve_to_names(query)
        except chem.ResolveError:
            failed.append(query)
            continue

        mol = Chem.MolFromSmiles(info.smiles)
        if mol is None:
            failed.append(query)
            continue

        resolved.append((query, info, mol))

    if len(resolved) < 2:
        raise ChemicalSpaceError(
            "Mindestens 2 auflösbare Moleküle nötig, um eine Karte zu erzeugen."
        )

    fingerprints = np.stack([_fingerprint(mol) for _, _, mol in resolved])
    coords = _pca_2d(fingerprints)
    k = _cluster_count(len(resolved))
    labels = _kmeans_labels(coords, k)

    points = []
    for (query, info, mol), (x, y), cluster in zip(resolved, coords, labels):
        points.append({
            "query": query,
            "common_name": info.common_name,
            "smiles": info.smiles,
            "x": float(x),
            "y": float(y),
            "cluster": int(cluster),
            "facts": chem._compute_facts(mol),
        })

    return {"points": points, "failed": failed}


if __name__ == "__main__":
    example_queries = [
        "aspirin", "ibuprofen", "paracetamol", "naproxen",
        "glucose", "fructose", "sucrose", "ribose",
        "methanol", "ethanol", "isopropanol",
        "glycine", "alanine", "serine", "phenylalanine",
        "cholesterol", "testosterone",
    ]
    result = build_chemical_space(example_queries)
    print("points:", len(result["points"]))
    print("failed:", result["failed"])
    by_cluster: dict[int, list[str]] = {}
    for point in result["points"]:
        by_cluster.setdefault(point["cluster"], []).append(point["common_name"])
    for cluster_id, names in sorted(by_cluster.items()):
        print(f"cluster {cluster_id}: {names}")
