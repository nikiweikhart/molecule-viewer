# Molekül-Viewer

**Bevor irgendetwas an diesem Projekt gemacht wird: zuerst `docs\stand.md`
lesen, ganz durch.** Das ist die Kurzfassung — neueste Einträge, bekannte
Fallstricke, und „Zum Wiedereinsteigen“ mit den ersten Befehlen.
Ältere Historie steht in `docs\verlauf.md` — nur gezielt per grep, nie komplett.

Backend ist Python (FastAPI + RDKit, venv unter `backend\.venv`; Boltz-2 in
separater `backend\.venv-boltz`), Frontend ist reines HTML/CSS/JS (keine
Build-Schritte, kein npm), Rendering mit Three.js (ES-Modul vom CDN; seit
2026-09-14 statt 3Dmol.js). Beides läuft im selben Prozess: `uvicorn` dient
Frontend und API zugleich, lokal auf **Port 8001** (nicht 8000).
Baupläne: `docs/bauplan-reaktions-animation.md`, `docs/bauplan-molekulardynamik.md`.

Nie in `.venv*/`, `.git/`, `backend/pdb_cache/` lesen oder dort rekursiv suchen.

Nach jedem Commit/Push: neuen Eintrag oben in `docs/stand.md` + Update von
`Second Brain/Vision/wiki/themen/chemie-3d-tool.md` und `wiki/log.md`. Wird
`stand.md` größer als ~20 KB, älteste datierte Einträge nach `verlauf.md` (oben) verschieben.
