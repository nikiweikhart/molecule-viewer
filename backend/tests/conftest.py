import sys
from pathlib import Path

# backend/ auf den Modul-Suchpfad legen, damit "import app"/"import chem" funktioniert,
# egal von wo aus pytest gestartet wird.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
