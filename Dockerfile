# Läuft NICHT die Boltz-2-Ausbaustufe (backend/folding.py) mit -- die braucht eine
# lokale GPU + eine 5,8 GB Gewichte-venv, siehe docs/stand.md. Auf einem normalen
# kostenlosen/günstigen Hosting-Tier ohne GPU meldet /api/fold-available das sauber
# ans Frontend, das den Bereich dann ausgraut, statt dass die App abstürzt.
FROM python:3.12-slim

WORKDIR /app

# libgomp1: manche wissenschaftlichen Wheels (scipy, vina) linken zur Laufzeit
# gegen OpenMP, das python:slim-Basisimage bringt es nicht standardmäßig mit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

# Render/Fly.io geben den Port über $PORT vor -- 8000 ist nur der lokale Fallback
# (nicht 8001 wie in der lokalen Windows-Entwicklung, siehe docs/stand.md; die
# Portwahl dort war nur nötig, weil ein alter Prozess auf 8000 feststeckte, das
# gilt für einen frischen Container nicht).
ENV PORT=8000
EXPOSE 8000

WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
