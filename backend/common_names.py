"""Kuratierte Uebersetzung gebraeuchlicher (v.a. deutscher) Alltagsnamen zu den
Stoffnamen, die PubChems Namenssuche sicher kennt.

Hintergrund: PubChems Namenssuche ist stark englisch-zentriert. Deutsche
Alltagsbegriffe wie "Kochsalz", "Essigsaeure" oder "Natron" kennt sie meist
nicht, obwohl der dahinterliegende Stoff eindeutig ist und unter seinem
englischen/wissenschaftlichen Namen problemlos gefunden wird. Gefunden per
echtem Durchlauf von ~1000 Alltagsbegriffen durch /api/resolve (siehe
docs/stand.md): rund ein Viertel der deutschen Alltagsnamen scheiterte allein
daran.

Gleiches Prinzip und gleiche Einbindungsstelle wie `brand_names.py`
(`chem._resolve_to_names`), nur fuer normale Stoffnamen statt Markennamen --
wird VOR der PubChem-Suche geprueft. Key lowercase, ohne Sonderzeichen im
Aufruf (der Vergleich passiert nach `.strip().lower()`), aber mit echten
Umlauten UND der ae/oe/ue/ss-Ersatzschreibweise als jeweils eigenem Eintrag,
weil beide Schreibweisen in der Praxis vorkommen (Tastatur ohne Umlaute,
Spracherkennung).

Bewusst NICHT aufgenommen: reine Produkt-/Gemisch-Bezeichnungen ohne einen
eindeutigen, dominanten Reinstoff (z.B. "Waschmittel", "Spuelmittel",
"Entkalker", "Desinfektionsmittel", "Motoroel") -- da waere jede Zuordnung zu
EINEM Molekuel eine Erfindung, keine sinnvolle Vereinfachung. Bleiben bewusst
mit der ehrlichen "nicht erkannt"-Fehlermeldung, gleiche Linie wie
Dulaglutide/Trulicity in `large_peptides.py`. Ausnahme: ein paar Fälle mit
einem klar ueberwiegenden Wirkstoff (z.B. Backpulver -> Natriumbicarbonat,
Abflussreiniger -> Natriumhydroxid) sind trotzdem drin, mit der gleichen
Vereinfachungs-Logik wie schon bei Insulin-Analoga oder Backpulver an anderer
Stelle im Projekt -- der Hinweistext beim Treffer macht die Uebersetzung
transparent, keine stille Annahme.
"""

COMMON_NAME_TRANSLATIONS: dict[str, str] = {
    # Kohlenstoff-/Sauerstoff-Verbindungen
    "kohlendioxid": "carbon dioxide",
    "kohlenstoffdioxid": "carbon dioxide",
    "kohlendioxidgas": "carbon dioxide",
    "kohlenmonoxid": "carbon monoxide",
    "kohlenstoffmonoxid": "carbon monoxide",

    # Natrium-Verbindungen
    "natron": "sodium bicarbonate",
    "speisenatron": "sodium bicarbonate",
    "backpulver": "sodium bicarbonate",
    "natriumhydrogencarbonat": "sodium bicarbonate",
    "waschsoda": "sodium carbonate",
    "soda": "sodium carbonate",
    "natriumcarbonat": "sodium carbonate",
    "natriumhypochlorit": "sodium hypochlorite",
    "chlorbleiche": "sodium hypochlorite",
    "javelwasser": "sodium hypochlorite",
    "javelle wasser": "sodium hypochlorite",
    "klorix": "sodium hypochlorite",
    "kochsalz": "sodium chloride",
    "speisesalz": "sodium chloride",
    "salz": "sodium chloride",
    "kochsalzloesung": "sodium chloride",
    "kochsalzlösung": "sodium chloride",
    "natriumfluorid": "sodium fluoride",
    "aetznatron": "sodium hydroxide",
    "ätznatron": "sodium hydroxide",
    "natronlauge": "sodium hydroxide",
    "abflussreiniger": "sodium hydroxide",
    "rohrreiniger": "sodium hydroxide",

    # Kalium-Verbindungen
    "pottasche": "potassium carbonate",
    "kalilauge": "potassium hydroxide",
    "salpeter": "potassium nitrate",

    # Calcium-Verbindungen
    "kalkstein": "calcium carbonate",
    "marmor": "calcium carbonate",
    "kreide": "calcium carbonate",
    "kalk": "calcium oxide",
    "branntkalk": "calcium oxide",
    "loeschkalk": "calcium hydroxide",
    "löschkalk": "calcium hydroxide",
    "calciumsulfat": "calcium sulfate",
    "gips": "calcium sulfate",

    # Ammonium-Verbindungen
    "ammoniumnitrat": "ammonium nitrate",
    "backtriebmittel": "sodium bicarbonate",

    # Eisen/Metalle
    "rost": "iron oxide",
    "eisenoxid": "iron oxide",
    "blauer vitriol": "copper sulfate",
    "kupfersulfat": "copper sulfate",
    "hoellenstein": "silver nitrate",
    "höllenstein": "silver nitrate",
    "silbernitrat": "silver nitrate",

    # Saeuren
    "salzsaeure": "hydrochloric acid",
    "salzsäure": "hydrochloric acid",
    "schwefelsaeure": "sulfuric acid",
    "schwefelsäure": "sulfuric acid",
    "salpetersaeure": "nitric acid",
    "salpetersäure": "nitric acid",
    "phosphorsaeure": "phosphoric acid",
    "phosphorsäure": "phosphoric acid",
    "flusssaeure": "hydrofluoric acid",
    "flusssäure": "hydrofluoric acid",
    "fluorwasserstoffsaeure": "hydrofluoric acid",
    "fluorwasserstoffsäure": "hydrofluoric acid",
    "essigsaeure": "acetic acid",
    "essigsäure": "acetic acid",
    "essig": "acetic acid",
    "zitronensaeure": "citric acid",
    "zitronensäure": "citric acid",
    "ameisensaeure": "formic acid",
    "ameisensäure": "formic acid",
    "milchsaeure": "lactic acid",
    "milchsäure": "lactic acid",
    "weinsaeure": "tartaric acid",
    "weinsäure": "tartaric acid",
    "apfelsaeure": "malic acid",
    "apfelsäure": "malic acid",
    "harnsaeure": "uric acid",
    "harnsäure": "uric acid",
    "borsaeure": "boric acid",
    "borsäure": "boric acid",
    "blausaeure": "hydrogen cyanide",
    "blausäure": "hydrogen cyanide",
    "kohlensaeure": "carbonic acid",
    "kohlensäure": "carbonic acid",
    "gerbsaeure": "tannic acid",
    "gerbsäure": "tannic acid",

    # Alkohole/Loesungsmittel
    "spiritus": "ethanol",
    "brennspiritus": "ethanol",
    "reinigungsalkohol": "ethanol",
    "trinkalkohol": "ethanol",
    "alkohol": "ethanol",
    "nagellackentferner": "acetone",
    "frostschutzmittel": "ethylene glycol",
    "frostschutz": "ethylene glycol",
    "kuehlerfrostschutz": "ethylene glycol",
    "kühlerfrostschutz": "ethylene glycol",
    "ethylenglykol": "ethylene glycol",
    "ethylenglycol": "ethylene glycol",

    # Zucker
    "traubenzucker": "glucose",
    "glukose": "glucose",
    "fruchtzucker": "fructose",
    "fruktose": "fructose",
    "milchzucker": "lactose",
    "malzzucker": "maltose",
    "rohrzucker": "sucrose",
    "kristallzucker": "sucrose",
    "puderzucker": "sucrose",
    "haushaltszucker": "sucrose",

    # Gase
    "erdgas": "methane",
    "fluessiggas": "propane",
    "flüssiggas": "propane",
    "propangas": "propane",
    "butangas": "butane",
    "feuerzeuggas": "butane",
    "stickstoffgas": "nitrogen",
    "wasserstoffgas": "hydrogen",
    "sauerstoffgas": "oxygen",
    "acetylen gas": "acetylene",
    "acetylengas": "acetylene",
    "stickoxid": "nitric oxide",
    "lachgas": "nitrous oxide",

    # Sonstiges
    "harnstoff": "urea",
    "harnstoffloesung": "urea",
    "harnstofflösung": "urea",
    "hirschhornsalz": "ammonium carbonate",
    "salmiakgeist": "ammonia",
    "ammoniaklosung": "ammonia",
    "ammoniaklösung": "ammonia",
    "salmiak": "ammonium chloride",
    "fluorid": "fluoride",
    "cholesterin": "cholesterol",
    "adrenalin": "adrenaline",
    "koffein": "caffeine",
    "nikotin": "nicotine",
    "mottenkugeln": "naphthalene",

    # Allgemeine Luecken, nicht deutsch-spezifisch -- PubChem kennt die vage
    # Form ohne Nummer/Zusatz nicht, nur den konkreten Verbindungsnamen.
    "vitamin d": "vitamin d3",
}
