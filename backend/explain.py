"""Erzeugt eine kurze, laienverständliche Erklärung eines Moleküls per Claude.

Braucht einen Anthropic-API-Key in der Umgebungsvariable ANTHROPIC_API_KEY
(z.B. über eine .env-Datei in backend/, siehe .env.example). Ohne Key liefert
explain() einfach `available=False` zurück — kein Absturz, die Fakten/3D-
Ansicht funktionieren unabhängig davon weiter.
"""

import os

from dotenv import load_dotenv

load_dotenv()

_MODEL = "claude-haiku-4-5-20251001"  # kleines, günstiges Modell reicht für diese enge Aufgabe


def explain(common_name: str, iupac_name: str | None, formula: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "available": False,
            "reason": "Kein ANTHROPIC_API_KEY gesetzt (siehe backend/.env.example).",
        }

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        name_bit = common_name
        if iupac_name and iupac_name.lower() != common_name.lower():
            name_bit += f" (Fachname: {iupac_name})"

        response = client.messages.create(
            model=_MODEL,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Erkläre das Molekül {name_bit} (Summenformel {formula}) in 2-3 "
                        "kurzen, einfachen Sätzen für jemanden ohne Chemie-Vorwissen. "
                        "Was ist es, wofür ist es bekannt/wozu wird es benutzt. "
                        "Keine Einleitung, keine Überschrift, direkt der Erklärtext auf Deutsch."
                    ),
                }
            ],
        )
        text = response.content[0].text.strip()
        return {"available": True, "text": text}
    except Exception as e:
        return {"available": False, "reason": f"KI-Anfrage fehlgeschlagen: {e}"}
