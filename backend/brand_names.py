"""Kuratierte Markennamen → Wirkstoff-Zuordnung.

Ziel: Eingabe vereinfachen, damit Nutzer:innen im Haupt-Suchfeld einfach den
Namen sagen können, den sie kennen (Markenname), statt den wissenschaftlichen/
generischen Wirkstoffnamen nachschlagen zu müssen -- z.B. "Mexalen" statt
"Paracetamol", "Xanax" statt "Alprazolam".

PubChems eigene Namenssuche (siehe `_pubchem_lookup_by_name` in chem.py) kennt
bereits viele internationale Markennamen als Synonym (z.B. "Aspirin",
"Viagra"), aber nicht zuverlässig österreichische/deutsche Markennamen oder
ganz neue Präparate. Diese Tabelle wird VOR der PubChem-Suche geprüft
(`chem._resolve_to_names`) und übersetzt den eingegebenen Markennamen in den
Wirkstoffnamen, den PubChem sicher findet. Steht ein Markenname hier nicht
drin, läuft die Eingabe einfach normal weiter zur PubChem-Namenssuche (die bei
vielen international bekannten Marken ohnehin schon direkt trifft).

Bei Kombinationspräparaten (mehrere Wirkstoffe, z.B. Thomapyrin = ASS +
Koffein + Paracetamol) steht hier nur der namensgebende/dominante Wirkstoff --
das Fakten-Panel zeigt also nicht die ganze Zusammensetzung, sondern eine
sinnvolle Vereinfachung (mit Kommentar unten markiert).

Für sehr große Wirkstoffe (z.B. die GLP-1-Präparate wie Ozempic) reicht die
Namensauflösung hier zwar aus, um den richtigen Stoff bei PubChem zu finden --
die 3D-Darstellung selbst scheitert danach aber bewusst mit einer erklärenden
Fehlermeldung (siehe `MAX_HEAVY_ATOMS` in chem.py), weil ein einzelnes
`EmbedMolecule` für ein ~30-70 Aminosäuren großes, modifiziertes Peptid keine
sinnvolle Struktur liefert. Das ist der aktuell bekannte, offen
dokumentierte Stand -- siehe docs/stand.md.

Neue Einträge einfach ergänzen: Key lowercase, ohne ®/™-Zeichen.
"""

BRAND_TO_SUBSTANCE: dict[str, str] = {
    # Schmerz-/Fiebermittel, v.a. AT/DE-Markennamen
    "mexalen": "paracetamol",
    "ben-u-ron": "paracetamol",
    "voltaren": "diclofenac",
    "nurofen": "ibuprofen",
    "novalgin": "metamizole",
    "buscopan": "hyoscine butylbromide",
    "thomapyrin": "acetylsalicylic acid",  # Kombi mit Koffein+Paracetamol, ASS ist namensgebend

    # Psychopharmaka
    "xanax": "alprazolam",
    "valium": "diazepam",
    "prozac": "fluoxetine",
    "ritalin": "methylphenidate",
    "insidon": "opipramol",

    # weitere international bekannte Marken
    "viagra": "sildenafil",
    "tylenol": "paracetamol",
    "advil": "ibuprofen",

    # GLP-1-/Diabetes-/Abnehm-Präparate und Insuline -- siehe Hinweis oben,
    # Struktur wird aktuell noch nicht dargestellt (zu große Moleküle).
    "ozempic": "semaglutide",
    "wegovy": "semaglutide",
    "rybelsus": "semaglutide",
    "mounjaro": "tirzepatide",
    "victoza": "liraglutide",
    "saxenda": "liraglutide",
    "trulicity": "dulaglutide",
    "lantus": "insulin glargine",
    "humalog": "insulin lispro",
    "novorapid": "insulin aspart",
}
