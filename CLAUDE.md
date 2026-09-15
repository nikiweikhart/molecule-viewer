# Molekül-Viewer

**Bevor irgendetwas an diesem Projekt gemacht wird: zuerst `docs\stand.md`
lesen, ganz durch.** Dort steht der aktuelle Stand — was fertig ist, was
offen ist, bekannte Fallstricke, und ganz unten der Abschnitt „Zum
Wiedereinsteigen" mit den ersten Befehlen.

Backend ist Python (FastAPI + RDKit, venv unter `backend\.venv`), Frontend ist
reines HTML/CSS/JS (keine Build-Schritte, kein npm), Rendering über
3Dmol.js von einem CDN. Beides läuft im selben Prozess: `uvicorn` dient das
Frontend und die API zugleich.
