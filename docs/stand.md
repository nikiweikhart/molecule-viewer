# Stand: Molekül-Viewer

## 2026-09-21 (parallel, autonomer Lasttest-Durchlauf): ~1000 Alltagsbegriffe durchgetestet, drei systemische Ursachen statt Einzelpatches behoben

Niki wollte keine Einzelfall-Fixes, sondern wissen, ob ~1000 der
alltäglichsten/wichtigsten Begriffe durch `/api/resolve` funktionieren, und
falls nicht, die **Ursache** beheben statt jeden Fall einzeln zu patchen.
Lief zeitlich parallel zu einer anderen Chat-Sitzung mit Niki (Bibliothek-
Suche/Salzlöser/Gleichungslöser-Vorhersage, siehe Eintrag direkt unten) --
beide Arbeitsstände sind sauber zusammengeführt, keine Konflikte.

**Testaufbau:** 1034 deduplizierte Begriffe zusammengestellt (Elemente,
anorganische Grundstoffe, Haushaltschemikalien, Loesungsmittel, Zucker,
Aminosäuren, Vitamine, Hormone, ~60 Generika- und ~40 Marken-Arzneinamen,
Polymere, Gase, Minerale, Chemie-Unterrichtsstoffe, Formeln, SMILES, Aromen,
psychoaktive Stoffe u.a.) -- bewusst mit deutlichem Schwerpunkt auf
**deutschen** Alltagsnamen, weil die App komplett auf Deutsch läuft und für
einen deutschsprachigen Nutzer gebaut ist. Alle einzeln per Skript gegen den
lokalen Server (`POST /api/resolve`) gejagt, Ergebnisse in JSON geloggt.

**Erster Durchlauf: 767/1034 ok (74%).** Analyse der 267 Fehlschläge (nicht
einzeln durchgeschaut, sondern nach Fehlermeldung gruppiert) ergab **drei
echte, generalisierbare Ursachen** statt hunderter Einzelfälle:

**1. Bug: PubChems Rate-Limit (HTTP 429) wurde wie ein echtes "nicht
gefunden" behandelt.** `chem._request_with_retry()` hat bisher nur bei
Timeout/Verbindungsfehler/5xx wiederholt (`resp.status_code < 500` galt
als "fertig, kein Retry") -- ein 429 fiel mit rein und wurde sofort als
Nichttreffer gewertet und so gecacht. Beim harten Lasttest hat PubChem das
ausgelöst: völlig normale Stoffe wie Alprazolam oder Xylol schlugen mitten
im Testlauf fehl, funktionierten Minuten später beim manuellen Nachtesten
aber sofort wieder. **Fix:** 429 zählt jetzt als transient, wird mit
Backoff wiederholt (respektiert `Retry-After`, falls PubChem den mitschickt),
und wenn selbst nach allen Retries noch 429 kommt, gibt es eine ehrliche
"PubChem drosselt gerade"-Fehlermeldung statt eines stillen
Fake-Nichttreffers. Betrifft nicht nur den Testlauf: jede Anfrage, die
mehrere Stoffe kurz hintereinander auflöst (Gleichungslöser, chemischer
Raum), war vorher für dasselbe Muster anfällig.

**2. Fehlende Übersetzung deutscher Alltagsnamen -- der mit Abstand größte
Batzen.** PubChems Namenssuche ist englisch-zentriert und kennt Wörter wie
"Kochsalz", "Essigsäure", "Natron" oder "Blauer Vitriol" nicht, obwohl der
gemeinte Stoff eindeutig ist und unter seinem englischen Namen (Sodium
Chloride, Acetic Acid, Sodium Bicarbonate, Copper Sulfate) sofort gefunden
wird. Exakt das gleiche Muster, das `brand_names.py` schon für Markennamen
löst -- jetzt als eigenes Modul **`backend/common_names.py`**
(`COMMON_NAME_TRANSLATIONS`, ~95 Einträge, echte Umlaute UND die
ae/oe/ue/ss-Ersatzschreibweise als je eigener Key) nachgebaut und an
derselben Stelle in `chem._resolve_to_names()` eingehängt (Markenname zuerst
geprüft, dann Alltagsname, beide schließen sich gegenseitig aus). Bewusst
NICHT aufgenommen: reine Produkt-/Gemisch-Bezeichnungen ohne einen klar
dominanten Reinstoff ("Waschmittel", "Entkalker", "Desinfektionsmittel",
"Motoröl") -- da wäre jede Zuordnung zu einem Molekül eine Erfindung, gleiche
ehrliche Linie wie bei Dulaglutide/Trulicity in `large_peptides.py`. Ein
paar Fälle mit einem klar überwiegenden Wirkstoff sind trotzdem drin
(Backpulver/Backtriebmittel → Natriumbicarbonat, Abflussreiniger →
Natriumhydroxid), der Hinweistext beim Treffer macht die Übersetzung dabei
immer transparent.

**3. RDKits Standard-3D-Einbettung scheitert bei manchen validen, aber
komplexeren Molekülen zuverlässig.** Gerbsäure (Tannic Acid, 122
Schweratome, korrekt aufgelöst) lieferte bei `AllChem.EmbedMolecule(mol,
AllChem.ETKDGv3())` reproduzierbar `-1` (3 von 3 Versuchen) -- nicht weil das
Molekül ungültig wäre, sondern weil ETKDGv3s Standardstrategie für so einen
Fall nicht konvergiert. `useRandomCoords=True` (das gleiche Mittel, das
`peptide.py` schon für die zyklischen Disulfidbrücken-Strukturen nutzt)
behebt das zuverlässig, per Test bestätigt. **Fix in
`chem._build_structure()`:** erst der normale (schnellere) Versuch, bei
Fehlschlag automatisch ein zweiter Versuch mit `useRandomCoords=True` --
kein Spezialfall für Gerbsäure, gilt für jedes Molekül, das denselben Weg
nimmt.

**Ergebnis nach den drei Fixes, gegen dieselben 267 vorherigen Fehlschläge
erneut getestet (Server neu gestartet, damit der In-Memory-Cache leer ist):**
767 + 65 (Retest 1, v.a. Retry-Fix + erste Übersetzungen) + 5 (Retest 2, nach
zwei nachträglich ergänzten Übersetzungen + Embed-Fallback) = **837 von 1034
(81%)**.

**Die verbleibenden ~197 Fehlschläge sind nach Durchsicht keine Bugs mehr,
sondern korrekte, ehrliche Grenzen** (gleiche Linie wie der Rest des
Projekts an vielen Stellen): Polymere ohne eine einzelne definierte Struktur
(Polyethylen, PVC, Teflon, ...), echte Stoffgemische (Öle, Wachse, Teer,
Kohle, Reinigungsprodukte), komplexe Biomoleküle ohne PubChem-Kleinmolekül-
Eintrag (Stärke, Cellulose, DNA/RNA, Kollagen, ...; per direkter PubChem-
Autocomplete-Abfrage verifiziert, dass es dafür wirklich keinen sauberen
Treffer gibt), Kombi-/Kräuterpräparate (Iberogast, Sinupret, Neo Citran),
ein paar noch fehlende AT/DE-Markennamen (Perskindol, Otriven, ...) und ein
Dutzend absichtlich konstruierte Test-Wortkombinationen, die kein echter
Nutzer so eintippen würde (z.B. "banana isoamyl acetate"). Eine Ausnahme
notiert, aber nicht behoben: **Glucagon** (echtes Hormon-Peptid) fällt
zwischen die Stühle -- zu groß für die normale Auflösung (>150 Schweratome),
zu lang für den 15-Reste-Peptidmodus. Wäre ein Kandidat für
`large_peptides.py`, falls eine passende PDB-Struktur existiert (nicht
recherchiert, außerhalb des heutigen Auftrags).

**Neue Backend-Tests** (`tests/test_api.py`, 5 neue): deutscher Alltagsname
("Kochsalz" → Sodium Chloride, mit Hinweistext-Check), echter Umlaut
("Essigsäure"), Embed-Fallback (Gerbsäure liefert eine Struktur statt
Fehler), plus zwei isolierte Unit-Tests für `_request_with_retry()` mit
einer Fake-Response (429 → Retry → 200 erfolgreich; dauerhaftes 429 → saubere
`ResolveError` statt stillem Fake-Nichttreffer) -- einzige bewusste Ausnahme
von der sonstigen "kein Mocking"-Linie der Testdatei, weil sich PubChem
nicht auf Kommando drosseln lässt, um einen echten 429 zu erzeugen. Alle 45
Tests grün (40 vorher + 5 neue).

**Nicht gemacht, bewusst außerhalb des heutigen Auftrags:** eine breitere
Lösung für Polymere/Materialien (z.B. eine repräsentative
Wiederholungseinheit statt einer echten Kette anzeigen, ähnlich der
"vereinfacht dargestellt"-Linie bei Insulin-Analoga) wäre möglich, wurde
aber nicht umgesetzt -- Niki hat nach Root-Cause-Fixes gefragt, nicht nach
einer Erweiterung des Funktionsumfangs. Testskripte/Rohdaten liegen nur im
Scratchpad dieser Sitzung, nicht im Repo.

## 2026-09-21 (später, im Chat mit Niki): Bibliothek-Suche, Salzformel-Löser, Produktvorhersage im Gleichungslöser

Niki wollte drei Ergänzungen, alle umgesetzt, getestet (Backend-Tests +
Browser) und gepusht:

**1. Bibliothek-Suchfeld.** Neues Eingabefeld oben im Bibliothek-Flyout
(`frontend/index.html`/`app.js`, `filterLibrary()`) — filtert live nach
Kartentext ODER Kategorietitel (z.B. "Hormone" zeigt alle drei
Hormon-Karten, auch wenn kein einzelnes Label "Hormone" enthält), zeigt
"Keine Treffer." wenn nichts passt, leert sich beim erneuten Öffnen
automatisch.

**2. Neuer Salzformel-Löser (`backend/salts.py`, neuer Sidebar-Modus).**
Kation + Anion per Dropdown auswählen, Formel wird per Kreuzregel berechnet
(Ladungen kreuzweise als Indizes, z.B. Aluminium (+3) + Sulfat (-2) →
Al₂(SO₄)₃) — keine PubChem-Anfrage nötig, alles aus bekannten Ionenladungen.
15 Kationen (Alkali-/Erdalkalimetalle, Ammonium, gängige Übergangsmetalle
mit fixer Oxidationsstufe), 18 Anionen (Halogenide, Oxid/Sulfid, Hydroxid,
die klassischen Säurereste Nitrat/Sulfat/Phosphat/Carbonat/Acetat/Cyanid
+ deren Hydrogen-Varianten). 3D-Ansicht baut RDKit lokal aus
Ionen-SMILES-Fragmenten zusammen (`_layout_ions`, gleiches
Nebeneinander-Muster wie `equation.py::_layout_instances`) — **bewusst als
lose Ionenpaare dargestellt, keine echte Kristallstruktur** (ein reales
Salz hat ein Ionengitter aus sehr vielen Ionen), im `note`-Feld immer klar
benannt. MMFF-Optimierung schlägt für manche Ionen (z.B. Al³⁺) mangels
Kraftfeld-Parametern fehl — abgefangen, unoptimierte ETKDG-Koordinaten
reichen für die Darstellung. Neue Routen `GET /api/salt-ions`,
`POST /api/salt`.

**3. Produktvorhersage im Gleichungslöser (`backend/reaction_predict.py`).**
Tippt man nur Edukte ohne "->" ein (z.B. nur "CH4 + O2"), werden die
Produkte automatisch hergeleitet, dann läuft dieselbe
Ausgleichs-/Animations-Pipeline wie beim Text-Gleichungslöser
(`equation.py` dafür refaktoriert: `build_reaction_from_species()` als
gemeinsamer Kern, `build_equation_reaction()` ruft ihn nach dem
Text-Parsing auf). Erkannt werden **bewusst nur vier eindeutige
Reaktionstypen**, keine allgemeine Vorhersage:
- Verbrennung (CxHyOz + O2 → CO2 + H2O, Sonderfälle für reinen Kohlenstoff
  und Knallgas H2+O2 → H2O).
- Neutralisation (Säure + Metallhydroxid/Ammoniak → Salz + ggf. Wasser —
  Ammoniak bildet bewusst KEIN Wasser, NH3 + HCl → NH4Cl direkt, andere
  Basen schon).
- Metall + Säure → Salz + Wasserstoff.
- Synthese aus zwei Elementen (Metall + Nichtmetall → Salz/Oxid/Sulfid).

Reaktanten werden über die normale `chem._resolve_to_names()`-Pipeline
aufgelöst (Name/Formel/SMILES, wie überall sonst in der App) und dann
anhand ihrer resultierenden Summenformel klassifiziert (nicht anhand des
eingetippten Texts) — dadurch funktionieren automatisch auch Synonyme wie
"Salzsäure" statt "HCl", ohne eigene deutsche Namenslisten. Säuren/Basen
sind über ihre Hill-Formel identifiziert (`ACIDS`/`BASES`-Dicts), Metalle
für die beiden elementbasierten Regeln nur mit **eindeutiger, fixer
Oxidationsstufe** zugelassen — **Eisen, Chrom, Blei bewusst
ausgeschlossen**, weil ihr tatsächliches Produkt vom Reaktionspartner
abhängt (z.B. Fe + Cl2 → FeCl3, aber Fe + S → FeS, aus dem Element allein
nicht sicher herleitbar) — führt zu einer ehrlichen "Reaktionstyp nicht
erkannt"-Fehlermeldung statt einer geratenen, im Zweifel falschen Antwort.
Frontend erkennt automatisch, ob ein Pfeil in der Eingabe steht, und
schickt an `/api/equation` oder das neue `/api/equation/predict`.

**Getestet:** alle drei Features per Selbsttest-Skript + neuen
Backend-Tests (Bibliothek-Suche ist reines Frontend, im Browser geprüft:
Vitamin-Suche, Hormone-Kategorie-Match, "keine Treffer"). Salzformel-Löser:
Aluminiumsulfat (Al₂(SO₄)₃, Klammer-Fall), Calciumchlorid (CaCl₂) im
Browser bestätigt. Gleichungslöser-Vorhersage: HCl+NaOH → NaCl+Wasser (mit
Animation) und Fe+Cl2 → korrekte Fehlermeldung, beide im Browser bestätigt.
44 Backend-Tests grün (36 vorher + 4 Salz + 4 Vorhersage — auch
`salts.compute()`/`build_salt()` refaktoriert, ein gemeinsamer Kern für
Frontend-Route und Vorhersage-Modul statt doppelter Kreuzregel-Logik).

**Bekannte Grenzen, offen benannt:** die Produktvorhersage deckt nur die
vier genannten Reaktionstypen ab, alles andere (Zersetzung, Redox mit
mehrdeutiger Oxidationsstufe, organische Reaktionsmechanismen, ...) muss
weiterhin über die vollständige Gleichung mit "->" eingegeben werden. Der
Salzformel-Löser hat keine 3D-Kristallstruktur (siehe oben) und keine
Löslichkeitsregeln (jede Kation/Anion-Kombination wird berechnet, auch
wenn das reale Salz z.B. unlöslich wäre oder in der Praxis kaum vorkommt).

## 2026-09-21 (später): Gleichungslöser — tiefgestellte Indizes per "*"-Schreibweise

Niki fand die Formel-Anzeige im Gleichungslöser unbefriedigend: Zahlen standen
bisher überall "normal groß" (z.B. "CH4"), nicht als echter chemischer Index
("CH₄"). Wunsch: eine Eingabe-Konvention, bei der ein "*" direkt vor einer
Ziffer sie als tiefgestellt markiert (z.B. "CH*4"), plus Erklärung dazu im
Hinweistext für Erstbesucher. Vorab per Rückfrage geklärt, wo das sichtbar
werden soll -- Niki wollte die umfassendste Variante: sowohl eine Live-
Vorschau beim Tippen als auch im Ergebnis nach dem Lösen.

**Eine einzige Konvention für beide Stellen:** "*<Zahl>" wird durchgehend als
tiefgestellte Zahl gerendert -- sowohl auf das, was Niki selbst eintippt, als
auch auf die vom Backend berechnete Summenformel. Kein Sonderfall zwischen
Nutzereingabe und Server-Antwort.

- **Frontend (`frontend/app.js`):** neue Funktion `formatSubscripts()` --
  escaped den Text (HTML-sicher, falls z.B. Namen mit `<`/`>` eingetippt
  würden) und ersetzt danach `*<Ziffern>` durch `<sub>Ziffern</sub>`, plus
  kosmetisch `->`/`=` durch `→`. Live-Vorschau (`#equation-preview`, neues
  Element unter dem Eingabefeld) aktualisiert sich bei jedem `input`-Event am
  Eingabefeld. Beim Absenden wird `*` aus dem Text entfernt, bevor er an
  `/api/equation` geht -- die Schreibweise ist rein kosmetisch, ändert nichts
  an der eigentlichen Gleichung ("CH*4" wird genau wie "CH4" aufgelöst).
  "Beispiel laden" füllt jetzt "CH*4 + O*2 -> CO*2 + H*2O" statt der alten
  Version ohne Sternchen -- demonstriert die neue Schreibweise sofort beim
  ersten Ausprobieren.
- **Backend (`backend/equation.py`):** neue Funktion `_hill_formula()` baut
  aus dem schon vorhandenen `element_counts`-Counter jeder Spezies eine
  Summenformel im Hill-System (C zuerst, dann H, dann Rest alphabetisch --
  ohne C: alles alphabetisch), mit "*" vor jeder Elementanzahl >1 -- exakt
  dieselbe Konvention wie im Frontend, keine Duplikation der Formatierungs-
  Logik in zwei Sprachen nötig (Backend liefert nur den rohen "*"-Text, das
  Rendering zu `<sub>` passiert einzig in `formatSubscripts()`). Neues Feld
  `formula_label` in der `/api/equation`-Antwort, parallel zum bisherigen
  `label` (Stoffnamen von PubChem, z.B. "Methane + 2 Oxygen"). Ergebnis-
  Anzeige zeigt jetzt beides: `formula_label` (z.B. "CH₄ + 2 O₂ → CO₂ + 2
  H₂O") als Haupttext, `label` als kleinere "Erkannt als: ..."-Zeile darunter
  -- damit bleibt sichtbar, welcher Stoff tatsächlich erkannt wurde (wichtig
  bei mehrdeutigen Eingaben), auch wenn die Formel jetzt im Vordergrund steht.
- **Hinweistext ergänzt** (`MODE_INTROS.equation`): erklärt die "*"-
  Schreibweise mit einem Beispiel, das echte Unicode-Tiefstellungszeichen
  nutzt ("CH₄"), da der Hinweistext selbst per `textContent` gesetzt wird
  (kein HTML-Rendering dort, aber Unicode-Zeichen funktionieren direkt ohne
  Sonderbehandlung).
- **Backend-Test ergänzt** (`tests/test_api.py`,
  `test_equation_combustion_is_balanced` erweitert): prüft, dass
  `formula_label` die erwarteten "*"-markierten Formeln enthält (`CH*4`,
  `O*2`, `CO*2`, `H*2O`) und dass Elementanzahl 1 unmarkiert bleibt (kein
  `*1`). Alle 32 Tests grün.
- **Im Browser getestet** (Desktop, Live-Server neu gestartet -- Backend
  läuft nicht mit `--reload`-Hot-Reload für neue Prozesse, ein reiner
  Datei-Save reicht bei laufendem `--reload`-Server aber danach): "Beispiel
  laden" gefüllt und geprüft, dass die Live-Vorschau sofort "CH₄ + O₂ → CO₂ +
  H₂O" mit echten Tiefstellungen zeigt (nicht nur Text mit Sternchen). Nach
  "Lösen & animieren" zeigt das Ergebnis korrekt "CH₄ + 2 O₂ → CO₂ + 2 H₂O"
  (ausgeglichener Koeffizient "2" bleibt normal groß, nur die Formel-eigenen
  Zahlen sind tiefgestellt) plus "Erkannt als: Methane + 2 Oxygen → Carbon
  Dioxide + 2 Water" darunter. Zusätzlich mit zweistelligem Index getestet
  (Glucose, "C*6H*12O*6") -- "C₆H₁₂O₆" korrekt in der Vorschau, bestätigt,
  dass die Regex auch mehrstellige Zahlen nach "*" erfasst, nicht nur
  Einzelziffern.

## 2026-09-21: Frontend umgebaut — Sidebar-Navigation statt einer langen Stapel-Seite

Niki fand die alte Seite (alle 8 Bereiche untereinander gestapelt, von der
Suche bis zur Boltz-2-Faltung) unübersichtlich und wünschte sich ein
Cloud-artiges Layout (gemeint: die Struktur von claude.ai — Seitenleiste mit
Funktionen + ein zentrales Fenster, NICHT claude.ais eigene visuelle
Elemente wie die "Vorgeschlagen"-Chips, die er ausdrücklich hässlich fand).
Rein strukturelle Übernahme, keine optische.

**Neues Layout (`frontend/index.html`, `frontend/style.css`):**
- Linke Seitenleiste (`sidebar`, 240px, auf Mobile eine horizontale
  Icon-Leiste) mit einem Eintrag pro Funktion: Struktur-Suche,
  Reaktions-Animation, Gleichungslöser, Chemischer Raum, Protein-Docking,
  Molekulardynamik, Protein-Faltung (Boltz-2) — plus "Bibliothek" separat
  oben.
- **Nur ein zentrales Fenster** (`main-panel`) zeigt jeweils den aktiven
  Bereich (`.mode-view[data-mode-view]`, alle anderen `[hidden]`) — vorher
  standen alle 8 Bereiche permanent untereinander.
- **Bibliothek klappt links als eigenes Fenster auf** (`#library-flyout`,
  `position: fixed`, neben der Seitenleiste, mit Backdrop zum Schließen),
  statt ein eigener Modus zu sein — genau wie von Niki beschrieben ("soll
  links aufpoppen"). Kartendesign/-inhalt selbst unverändert übernommen
  (bewusst, Niki wollte das Bibliothek-Design behalten). Klick auf eine
  Karte lädt die Struktur, schließt die Bibliothek automatisch und
  schaltet auf "Struktur-Suche" um.
- Alle IDs/Elemente innerhalb der Bereiche unverändert gelassen (nur in
  `<section class="mode-view" data-mode-view="...">`-Wrapper verpackt) --
  `app.js` brauchte dadurch nur eine neue Schicht am Ende (Umschalt-Logik),
  keine Änderungen an der bestehenden Fetch-/Render-Logik jedes Bereichs.
- **Stolperstein gelöst:** Three.js-Viewer (und der Chemischer-Raum-Canvas)
  lesen ihre Größe beim Erzeugen aus `container.clientWidth/Height` — bei
  `[hidden]`-Panels ist das 0, wodurch ein Viewer, der nicht der
  Start-Modus ist, verzerrt/leer bliebe. Gelöst mit `MODE_RESIZE` in
  `app.js`: bei jedem Moduswechsel wird auf `requestAnimationFrame` der
  passende `viewer.resize()`/`chemspacePlot.resize()` nachgeholt. Per
  echtem Test bestätigt (Reaktions-Animation nach Umschalten korrekt
  sichtbar und animiert, nicht leer).
- `#note`/`#error` liegen jetzt einmalig im `main-header`-Bereich (statt
  Teil der alten "Struktur-Suche"-Sektion) -- sie werden von praktisch
  jedem Bereich befüllt (Docking, Chemischer Raum, Bibliothek, ...), waren
  vorher aber nur direkt unter der Suche sichtbar; jetzt sind sie unabhängig
  vom aktiven Modus sichtbar.

**Erklärhilfen für Erstbesucher (Nikis zweiter Wunsch in derselben
Nachricht):** jeder Modus (plus die Bibliothek) hat einen kurzen
Hinweistext, der nur erscheint, bis er einmal mit "Verstanden" weggeklickt
wurde (`localStorage`-Key `mv_seen_intros`, `app.js`: `maybeShowIntro()`).
Kein Server-Zustand, rein browserlokal -- bei geleertem `localStorage` oder
einem neuen Gerät erscheinen die Hinweise erneut, das ist gewollt (dann ist
es wieder ein "Erstbesuch").

**Getestet im Browser (Desktop 1024px + Mobile-Emulation 375px):**
Moduswechsel zwischen allen 7 Bereichen (Titel/aktiver Sidebar-Eintrag/
Hinweistext wechseln korrekt), Bibliothek-Flyout öffnet/schließt per Klick
auf den Eintrag, per X-Button und per Klick auf den Hintergrund
(`elementFromPoint`-Check bestätigt korrekte Stapelreihenfolge: Flyout über
Backdrop über Hauptbereich), Klick auf eine Bibliothek-Karte (Aspirin)
schließt die Bibliothek automatisch, schaltet auf Struktur-Suche um und
zeigt die geladene 3D-Struktur samt Fakten-Panel korrekt. Reaktions-
Animation nach Moduswechsel abgespielt -- sichtbar animiert, nicht leer/
verzerrt (bestätigt den Resize-Fix). "Verstanden" auf den Hinweistext
geklickt, Seite neu geladen -- Hinweistext blieb korrekt weg
(`localStorage`-Persistenz bestätigt). Mobile-Ansicht (375px): Seitenleiste
wird zur horizontalen Icon-Leiste oben, scrollbar, aktiver Eintrag farblich
hervorgehoben, restliches Layout bleibt nutzbar.

**Nicht angetastet:** `viewer.js`, `chemspace.js`, das gesamte Backend --
reine Frontend-Strukturänderung, keine neue Route, kein geändertes
API-Verhalten.

## 2026-09-20 (später, mehrstündiger Durchlauf): Öffentliches Deployment — jetzt live

**Live-URL: https://molecule-viewer.onrender.com** (Render, kostenloser Free-Tier).
Niki hatte einen 5-Phasen-Auftrag gegeben: offene Punkte aus dem letzten
Durchlauf schließen, die dokumentierten kleineren Lücken abarbeiten, das
Projekt deploy-fähig machen, tatsächlich veröffentlichen, und den Stand hier
festhalten. Alle fünf Phasen sind durch.

**Phase 1 — offene Punkte geschlossen:**
- **Boltz-2-Rendering visuell bestätigt, diesmal mit wirklich sichtbarem
  Browser-Pane** (der letzte Durchlauf hatte das Pane unsichtbar laufen
  lassen, wodurch `requestAnimationFrame` nie feuerte). Oxytocin vorhergesagt
  und per Screenshot bestätigt: kompakte, sichtbar gefaltete Struktur mit
  erkennbarer Disulfidbrücke (gelbe Schwefelatome), per Maus-Drag rotierbar.
  "Wasser" als Regressionscheck ebenfalls sauber gerendert.
- **`MAX_RESIDUES=50` empirisch getestet** (vorher nur eine konservative
  Setzung ohne Messung): 36 Reste (Pankreatisches Polypeptid) ~50s, 50 Reste
  (GB1-Domänen-Fragment) ~73s — beide weit unter dem 600s-Zeitbudget,
  Skalierung mit der Länge spürbar überlinear, aber nicht explosionsartig.
  Grenze bleibt bei 50 stehen (Begründung jetzt in `folding.py` als
  Kommentar: eine Fortsetzung des Trends könnte bei deutlich längeren
  Sequenzen ans Zeitbudget herankommen), aber jetzt mit echten Messwerten
  statt einer Vermutung.

**Phase 2 — dokumentierte kleinere Lücken abgearbeitet (Qualität vor
Vollständigkeit, wie gefordert):**
- **PubChem-Retry ergänzt** (`chem._request_with_retry`): wiederholt bei
  Timeout/Verbindungsfehler/5xx bis zu 2x mit kurzem Backoff — ein echter
  404 ("Molekül existiert nicht") wird bewusst NICHT wiederholt, das ist eine
  gültige Antwort, kein Fehler. Ohne das hätte ein einzelner kurzer
  Netzwerk-Hänger fälschlich dauerhaft im In-Memory-Cache gelandet (der
  bestand schon seit dem 2026-09-19-Eintrag, nur ohne Retry).
- **Formel-Mehrdeutigkeits-Heuristik verbessert** (`chem._pick_most_common_cid`):
  wählt jetzt unter den (bis zu 8) niedrigsten CIDs den mit den meisten
  bekannten Synonymen bei PubChem, statt einfach die niedrigste CID zu nehmen
  — Näherung für "am bekanntesten" statt "am frühesten dokumentiert". Dabei
  ein reales Problem gefunden und behoben: der erste Versuch wählte für
  `C6H12O6` "An inositol" (545 Synonyme, aber ein ChEBI-Pseudo-Titel, kein
  echter Stoffname) statt "D-Glucose" (162 Synonyme) — jetzt werden Titel mit
  führendem unbestimmtem Artikel ("An ...", "A ...") bei der Auswahl
  übersprungen, solange es eine "echt benannte" Alternative gibt. Ergebnis
  jetzt: `C6H12O6` → **D-Glucose**, nicht mehr "Hexopyranose".
- **PNG-Export/Screenshot-Feature ergänzt** — der in der letzten Ideen-Liste
  offene Punkt. `viewer.js` bekam `captureScreenshot()` (rendert einmal neu
  und liest sofort danach `canvas.toDataURL()`, bevor der Browser den
  Drawing-Buffer leert — der Renderer läuft bewusst ohne
  `preserveDrawingBuffer`, siehe die `gl.readPixels()`-Notiz im
  2026-09-20-Eintrag oben). "PNG speichern"-Button jetzt auf jedem
  Viewer-Frame (Haupt-Karte, Docking, Molekulardynamik, Boltz-2, Reaktion,
  Gleichungslöser) — `app.js::downloadScreenshot()` als gemeinsamer Helfer.
- **Backend-Tests für die drei genannten Lücken ergänzt**
  (`tests/test_api.py`): `/api/fold` (Erfolgsfall + zwei Fehlerfälle —
  der Erfolgsfall braucht `backend/.venv-boltz` und wird sauber
  übersprungen, wenn die fehlt, z.B. auf einem frischen Deployment-Host),
  Schweratom-Limit direkt per 155-Kohlenstoff-SMILES getestet (unabhängig
  vom Ozempic-Umweg), Markennamen-Auflösung war schon vom letzten Durchlauf
  abgedeckt. Alle 29 Tests grün (28 ohne den Boltz-Erfolgstest).
- **Bewusst zurückgestellt, wie von Niki ausdrücklich erlaubt:**
  Ladungszustände des Liganden vor dem Docken (pKa-Vorhersage ist ein
  eigenes, nicht triviales Teilproblem) und SHAKE/RATTLE bei der MD (würde
  den selbstgeschriebenen Velocity-Verlet-Integrator grundlegend umbauen) —
  beide bleiben unten in der Ideen-Liste offen, keine halbgare Umsetzung.
- **`no-cache`-Header für alle Nicht-API-Routen ergänzt** (`app.py`-Middleware),
  weil beim Testen der Export-Funktion der altbekannte Cache-Fallstrick
  (siehe 2026-09-19-Eintrag) erneut zuschlug — jetzt erzwingt jede
  Frontend-Datei eine bedingte Anfrage (`If-Modified-Since`) statt
  heuristisch lang gecacht zu werden. Wichtig für Niki: **selbst damit kann
  ein once-cachter Browser-Tab noch die alte Version einer schon vorher
  (ohne den Header) geladenen Datei behalten** — bei Verdacht auf eine
  hängende alte Version hilft ein neuer Tab zuverlässiger als Strg+Shift+R
  in einem schon offenen Tab (per echtem Test bestätigt, nicht nur
  vermutet).

**Phase 3 — Deployment-Vorbereitung, beide bekannten Blocker gelöst:**
- **Docking läuft nicht mehr nur unter Windows.** `docking.py` löst
  meeko-Skriptpfade jetzt über `sys.executable`s Verzeichnis auf (statt
  hartkodiert `.venv/Scripts`) und probiert beim Aufruf `.exe` →
  endungslos → `.py` (über `sys.executable` ausgeführt) — die genaue Form
  unterscheidet sich pro Plattform und wurde erst am echten Deployment
  entdeckt, nicht vorher angenommen (siehe Phase 4 unten). Für Vina selbst:
  `backend/tools/vina.exe` bleibt der Windows-Weg, neu ist ein Fallback auf
  das **pip-Paket `vina`** (echte manylinux-Wheels, anders als unter
  Windows) über Vinas Python-Bindings, wenn die `.exe` fehlt.
  `requirements.txt` installiert es nur auf Nicht-Windows
  (`vina; sys_platform != "win32"`), damit Nikis lokale Windows-venv
  unverändert bleibt.
- **Boltz-2 sauber gated statt zu crashen.** Neue Route
  `GET /api/fold-available` (`folding.BOLTZ_AVAILABLE`, prüft nur, ob
  `.venv-boltz/Scripts/boltz.exe` existiert) — das Frontend fragt das beim
  Laden ab und graut Eingabefeld/Buttons im Boltz-2-Bereich aus, mit
  erklärendem Hinweistext, statt dass ein Vorhersage-Versuch auf einem
  GPU-losen Host in einer kryptischen Fehlermeldung endet. Genau Option (a)
  aus Nikis Vorgabe — ein CPU-Fallback (Option b) wäre für ein
  AlphaFold3-artiges Modell auf einem 512-MB-Free-Tier ohnehin unrealistisch
  gewesen.
- **Dockerfile + `.dockerignore` + `render.yaml`** (Render-Blueprint) neu.
  `python:3.12-slim`-Basis, `libgomp1` für scipy/vina, installiert
  `requirements.txt` direkt ins System-Python (kein venv im Container
  nötig). `render.yaml` deklariert den Web-Service inkl. optionalem
  `ANTHROPIC_API_KEY`-Feld, damit die Render-Oberfläche den Service beim
  Verbinden automatisch mit den richtigen Einstellungen anlegt.

**Phase 4 — tatsächlich deployt, mit drei echten Stolpersteinen, alle vor
Ort am lebenden Deployment gefunden und gelöst (nicht vorab erraten):**

1. **Konto-Erstellung ist mir laut meinen eigenen Sicherheitsregeln
   verboten**, auch mit Nikis vorheriger pauschaler Erlaubnis — das habe ich
   offen angehalten und Niki gebeten, das Render-Konto selbst anzulegen
   (mit seinem Google-Account). Alles danach (Blueprint verbinden,
   Environment-Variable, Deploys auslösen) habe ich übernommen.
2. **Öffentliches GitHub-Repo direkt per URL verbunden** (`select-repo` →
   "Public Git Repository"-Feld), nicht über die GitHub-App-OAuth-Verbindung
   — vermeidet eine OAuth-Berechtigungsanfrage an Niki. **Korrektur, per
   echtem Test im selben Durchlauf widerlegt:** Auto-Deploy funktioniert
   auch so — ein `git push` löste beim nächsten Feature (siehe
   "große Peptid-Wirkstoffe" unten) tatsächlich automatisch einen neuen
   Deploy aus (Trigger zeigte "Auto-Deploy", nicht "Manual"). Render
   pollt das öffentliche Repo offenbar selbst auf neue Commits, auch ohne
   die GitHub-App-Verbindung. Ein `git push origin main` allein reicht
   also doch.
3. **Stolperstein 1 — Build lief safort durch, inkl. `vina-1.2.7` aus
   PyPI** (bestätigt: echte manylinux-Wheels für alle Kern-Pakete,
   `rdkit`/`meeko`/`gemmi`/`scipy`/`vina` installierten sich alle sauber).
   Der erste `/api/dock`-Testaufruf über die echte, öffentliche Seite schlug
   aber mit `FileNotFoundError: /usr/local/bin/mk_prepare_receptor` fehl
   (500). **Ursache: meekos Konsolen-Skripte liegen unter Linux als
   `mk_prepare_receptor.py`-Datei mit Shebang, nicht als endungsloser
   Launcher wie erwartet** (unter Windows sind es `.exe`-Launcher ohne
   `.py`) — das war eine plattformspezifische Eigenheit von meekos
   0.8.0-Distribution, die sich vorher nicht ohne einen echten Linux-Host
   prüfen ließ (kein Docker lokal verfügbar). Gelöst mit `_tool_cmd()`
   (`docking.py`): probiert `.exe` → endungslos → `.py` (über
   `sys.executable` aufgerufen, verlässt sich nicht auf Ausführungsrechte/
   Shebang). Ohne Shell-Zugriff auf den Free-Tier-Container (Render Shell
   ist ein bezahltes Feature) wurde das über eine temporär eingebaute
   Diagnose in `_run()` gefunden (listet den Skript-Ordner bei einem
   `FileNotFoundError` auf) statt zu raten.
4. **Stolperstein 2 — danach ein `502 Bad Gateway`, ohne jeden
   Python-Traceback im Log:** der Uvicorn-Prozess wurde beim ersten echten
   Docking-Versuch (3PTB + Benzamidin) kommentarlos neu gestartet
   ("Started server process" erscheint erneut, keine Fehlermeldung dazwischen)
   — das klassische Muster eines OOM-Kills, nicht eines Python-Fehlers.
   Render Free-Tier hat ein **512-MB-RAM-Limit** (im Dashboard unter
   Metrics bestätigt). Ursache vermutet und behoben: Vinas Python-Bindings
   nutzen standardmäßig `cpu=0` (alle erkannten Kerne) — in einem
   Container mit CPU-Kontingent meldet `/proc` oft die volle Kernzahl des
   Host-Rechners, wodurch Vina so viele parallele Suchthreads (jeder mit
   eigenen Gitter-Puffern) startet, wie **gemeldete**, nicht tatsächlich
   verfügbare Kerne da sind. `Vina(sf_name="vina", cpu=1, ...)` erzwingt
   einen einzigen Thread. **Nach dem Fix: `200 OK`, echtes Docking-Ergebnis,
   Protein-Röhre + Ligand + Suchbox sichtbar im Browser, exakt wie lokal.**
   Nicht per Shell-Zugriff bestätigt (den gibt es auf dem Free-Tier nicht),
   aber die Korrelation (Fix eingespielt → sofort funktionierend, keine
   weiteren Restarts) ist deutlich.
5. **Alle anderen Endpunkte gegen die echte, öffentliche URL durchgetestet:**
   `/api/resolve`, `/api/equation`, `/api/chemical-space`, `/api/reactions`,
   `/api/dynamics`, `/api/peptide`, `/api/pdb-ligand` — alle `200 OK`.
   `/api/fold-available` liefert korrekt `false` (kein `.venv-boltz` im
   Container), Frontend graut den Boltz-2-Bereich sichtbar aus, mit dem
   erklärenden Hinweistext. **Bekannte Grenze, offen benannt:** `/api/peptide`
   und `/api/dynamics` liefen deutlich langsamer als lokal (mehrere Sekunden
   statt "quasi sofort") — Render Free-Tier gibt nur einen kleinen,
   geteilten CPU-Anteil, das ist erwartbar und für eine Demo/Portfolio-Seite
   hinnehmbar, aber falls Niki das stört: eine bezahlte Instanz mit mehr
   CPU wäre der Hebel, nicht weitere Code-Änderungen.
6. **Weitere bekannte Free-Tier-Eigenheit, nicht behoben, weil es genau der
   Kompromiss des kostenlosen Tiers ist:** die Instanz fährt nach
   Inaktivität herunter, ein erster Aufruf danach kann 50+ Sekunden dauern
   (Render zeigt diesen Hinweis selbst im Dashboard an).

**Phase 5 — dieser Eintrag + README.** `README.md` hat jetzt den Live-Link
ganz oben (Portfolio-tauglich für die VWA, wie gewünscht). Alle
Zwischenstände wurden committet und gepusht (5 Commits diesen Durchlauf:
Haupt-Feature-Bündel, Render-Blueprint, Diagnose-Hilfe, meeko-Fix,
Vina-CPU-Fix) — `git log` zeigt den vollen Weg inklusive der drei
Stolpersteine, falls das später nochmal relevant wird.

**Nachtrag, direkt im Anschluss: große Peptid-Wirkstoffe auch über das
Haupt-Suchfeld.** Niki fragte nach dem Deployment, ob "sowas wie Ozempic"
auch normal eingebbar geht -- bis dahin lief das nur über die eigene
Bibliothek-Karte, die generische Auflösung endete für alle GLP-1-/Insulin-
Präparate bewusst in der "zu groß"-Fehlermeldung (`MAX_HEAVY_ATOMS`).

**Neue Datei `backend/large_peptides.py`**: kuratierte Zuordnung
Wirkstoffname → reale RCSB-Struktur (PDB-ID + optionale `chain_ids`), jeder
Eintrag einzeln gegen die echte RCSB-Struktur verifiziert (Kettenlänge UND
Entity-Beschreibung abgeglichen, nicht nur aus der Volltextsuche-Trefferliste
geraten):
- **Semaglutide** (Ozempic/Wegovy/Rybelsus) → `4ZGM` (schon vorher als
  Bibliothek-Karte im Einsatz).
- **Liraglutide** (Victoza/Saxenda) → `4APD` -- eigenständige, unkomplizierte
  Ein-Ketten-Struktur (per RCSB-Volltextsuche gefunden, Kette A mit genau 31
  Resten bestätigt, exakt Liraglutides bekannte Länge).
- **Tirzepatide** (Mounjaro) → `7FIM`, ein Cryo-EM-Komplex mit dem
  GLP-1-Rezeptor + G-Protein + Nanobody (6 Ketten insgesamt) -- hier war
  Vorsicht nötig: die bestehende Peptid-Längen-Heuristik (kürzeste Kette im
  Bereich 5-60 Reste) hätte ohne Prüfung leicht die falsche Kette treffen
  können (Kette G, G-Protein-γ-Untereinheit, hat mit 57 Resten fast die
  gleiche Länge wie Tirzepatid selbst mit 27 modellierten Resten) -- per
  echtem RCSB-Entity-Abruf verifiziert, dass Kette P (die kürzere) wirklich
  "Tirzepatide" ist, nicht geraten.
- **Insulin und gängige Analoga** (Lispro/Humalog, Aspart/Novorapid,
  Glargin/Lantus) → alle über die schon bewährte `4OGA`-Struktur (explizite
  `chain_ids: ["A","B"]`, wie bei der bestehenden Insulin-Bibliothekskarte).
  Da die Analoga sich strukturell leicht vom gezeigten Wildtyp-Insulin
  unterscheiden (einzelne Aminosäure-Austausche, keine öffentliche
  Kristallstruktur für die Analoga selbst gefunden), bekommt der
  Anzeigename einen klaren Zusatz ("Wildtyp-Struktur gezeigt") plus einen
  erklärenden Satz im Hinweistext -- keine stillschweigende Vereinfachung.
- **Bewusst NICHT aufgenommen: Dulaglutide/Trulicity** -- RCSB-Volltextsuche
  lieferte keinen einzigen Treffer (es ist ein Fusionsprotein mit einem
  IgG4-Fc-Teil, vermutlich nie öffentlich strukturell gelöst) -- bleibt bei
  der ehrlichen "nicht erkannt"-Fehlermeldung, statt eine falsche PDB-ID
  einzutragen.

**Routing in `app.py`** (`/api/resolve`): prüft die Eingabe (direkt UND über
`brand_names.BRAND_TO_SUBSTANCE` übersetzt) zuerst gegen
`large_peptides.match()`, bevor die normale `chem.resolve()`-Auflösung
überhaupt versucht wird -- vermeidet auch unnötige PubChem-Anfragen für
Fälle, die ohnehin nur mit "zu groß" enden würden. Bei Treffer wird
`docking.pdb_ligand()` aufgerufen (exakt der gleiche Code-Pfad wie die
Bibliothek-Karten) und `common_name`/`note` mit dem hübschen Anzeigenamen
bzw. dem Analog-Hinweis überschrieben.

**Backend-Tests ergänzt**: Ozempic → echte Struktur statt Fehler (der alte
Test, der die "zu groß"-Meldung erwartete, wurde entsprechend ersetzt),
Wegovy/Mounjaro/Victoza/insulin liefern die richtigen Anzeigenamen, Lantus
zeigt den Wildtyp-Hinweis, Trulicity scheitert weiterhin ehrlich. Alle 31
Tests grün.

**Getestet, lokal und auf der echten Live-Seite**: "Ozempic" ins
Haupt-Eingabefeld getippt und aufgelöst -- zeigt jetzt die reale,
verzweigte Semaglutid-Kette (`C137H207N...`, 3044 g/mol ohne H) statt der
Fehlermeldung, keine Konsolenfehler. Ozempic/Wegovy/Mounjaro/Victoza/
Lantus/insulin auch direkt gegen die Live-URL per `fetch()` durchgetestet,
alle `200 OK` mit den erwarteten Anzeigenamen; Trulicity weiterhin `400`.
Deploy lief diesmal komplett automatisch (`git push` allein reichte, siehe
Korrektur oben) und war nach ca. 35 Sekunden live.

## 2026-09-20 (autonomer Durchlauf, ~1,5 Std.): Ausbaustufe — echte Protein-Faltung mit Boltz-2

Niki war ~1,5 Std. weg und hat eine neue, größere Ausbaustufe vorgegeben:
echte ML-basierte Struktur-Vorhersage (Boltz-2, AlphaFold3-artige Architektur)
als Ergänzung zur reinen RDKit-Kraftfeld-Näherung in `peptide.py`. Bauplan kam
als vollständiger Prompt mit vier Phasen (Machbarkeits-Check, Backend,
Frontend, Doku) und expliziter Hardware-Einordnung (RX 7900 XTX, ROCm 10.0
Windows-Preview) — bei normalen Umsetzungsentscheidungen selbst entschieden,
nicht gewartet. **Ergebnis: funktioniert, inklusive echter GPU-Beschleunigung
auf der AMD-Karte — mit drei echten Stolpersteinen unterwegs, die alle
gelöst wurden.**

**Phase 0 — Machbarkeits-Check (der wichtigste Teil, hat sich gelohnt):**

1. **Python-Versionskonflikt zuerst gefunden, bevor irgendwas installiert
   wurde:** Boltz-2 braucht `>=3.10,<3.13` (per Recherche bestätigt), auf
   diesem Rechner war nur Python 3.14 installiert (auch `backend/.venv`
   läuft auf 3.14) — und PyTorchs eigene 3.14-Unterstützung hat laut
   offenen GitHub-Issues (`pytorch/pytorch#169929`, `ROCm/TheRock#2640`)
   ohnehin noch keine GPU-Wheels, nur CPU. **Lösung: Python 3.12 separat
   installiert** (`winget install Python.Python.3.12`, koexistiert
   problemlos neben 3.14 über den `py`-Launcher) und eine **komplett
   eigene venv `backend/.venv-boltz`** angelegt — `backend/.venv` (die
   normale FastAPI-App) bleibt unangetastet auf 3.14. `folding.py` läuft
   selbst in `.venv/Scripts/python.exe` (Python 3.14, wie der Rest der
   App), ruft Boltz-2 aber als externen Prozess in `.venv-boltz` auf —
   gleiches Muster wie `vina.exe` in `docking.py`, nur mit einer ganzen
   Python-Umgebung statt einer einzelnen `.exe`.
2. **ROCm-PyTorch für Windows tatsächlich installierbar, genau wie im Prompt
   vermutet.** AMDs aktuelle Doku (`rocm.docs.amd.com/.../pytorch/install.html`)
   nennt für die RX 7900 XTX (gfx1100) unter Windows Python 3.11–3.14 und
   einen fertigen Install-Befehl gegen einen eigenen Paket-Index
   (`repo.amd.com/rocm/whl-multi-arch/`). Installiert:
   `torch==2.12.0+rocm7.14.1` (mit `[device-gfx1100]`-Extra) +
   `torchvision`/`torchaudio` derselben Serie. **Download ca. 1,5 GB**
   (`rocm-sdk-core` allein 758 MB). Danach bestätigt:
   `torch.cuda.is_available() == True`, `torch.cuda.get_device_name(0)`
   → `"AMD Radeon RX 7900 XTX"` — ROCms CUDA-Kompatibilitätsschicht macht
   die AMD-Karte für PyTorch als ganz normales `cuda`-Gerät sichtbar.
3. **`pip install boltz` (ohne `[cuda]`-Extra, wie geplant) lief sauber** in
   `.venv-boltz` (Boltz **2.2.1**, zieht u.a. `pytorch-lightning`,
   `biopython`, `hydra-core`, ein eigenes `rdkit` mit — degradiert dabei
   `numpy` von 2.4.4 auf 1.26.4, aber `torch`+`numpy`+`boltz` importieren
   danach weiterhin gemeinsam ohne Konflikt, geprüft).
4. **Testlauf mit Oxytocin (9 AS) — drei echte Probleme unterwegs, alle
   gelöst, siehe auch die Kurzfassung ganz unten in "Bekannte Grenzen":**
   - **Stolperstein 1 — der erste Versuch lief in mein eigenes
     600s-Zeitbudget hinein, aber nicht weil die Berechnung selbst
     lange dauerte:** Boltz-2 lädt seine Gewichte (`boltz2_conf.ckpt`,
     `boltz2_aff.ckpt`, `mols.tar` — zusammen **ca. 5,8 GB**) beim
     allerersten Aufruf automatisch nach `C:\Users\<user>\.boltz\`. Das
     hat beim ersten Testlauf länger als 600s gedauert und wurde vom
     Timeout abgewürgt.
   - **Stolperstein 2 — dadurch eine ECHTE, nicht offensichtliche Falle:
     der abgewürgte Download hinterließ eine unvollständige
     `boltz2_conf.ckpt` (745 MB statt der fertigen 2,29 GB), und Boltz-2
     prüft beim nächsten Start nur "existiert die Datei?", nicht ob sie
     vollständig/korrekt ist.** Der nächste Versuch lief prompt in einen
     `RuntimeError: PytorchStreamReader failed reading zip archive`
     beim Laden des Checkpoints. **Lösung:** die kaputte Datei gezielt
     gelöscht (`rm ~/.boltz/boltz2_conf.ckpt`), sauber neu heruntergeladen
     -- **wichtig für Niki, falls das nochmal passiert: bei einem
     abgebrochenen/getimeouteten Boltz-Lauf immer die zuletzt
     wachsende Datei in `~/.boltz/` löschen, bevor man es nochmal
     versucht, nicht einfach neu starten.**
   - **Stolperstein 3 — danach ein echter Kompatibilitäts-Fund:** Boltz-2
     nutzt standardmäßig NVIDIAs `cuequivariance`-Bibliothek für schnellere
     Dreiecks-Multiplikations-Kernel — die existiert nur für CUDA, nicht
     für ROCm, und der erste GPU-Versuch brach mit
     `ModuleNotFoundError: No module named 'cuequivariance_torch'` mitten
     in der Vorhersage ab (Checkpoint war da schon korrekt geladen, GPU
     korrekt erkannt: "You are using a CUDA device ('AMD Radeon RX 7900
     XTX')"). **Lösung:** Boltz-2 hat dafür extra ein Flag,
     `--no_kernels` (laut eigener Doku "disables cuequivariance library
     for older GPUs, trades performance for compatibility") — damit lief
     der Testlauf durch. Jetzt fest in `folding.py`s Boltz-Aufruf
     eingebaut, nicht optional.
   - **Mit allen drei Fixes: Oxytocin (9 AS) komplett in 47s** (inkl.
     Python-Subprozess-Start, echtem MSA-Server-Aufruf an
     `api.colabfold.com` [~1-10s], GPU-Inferenz [~8s laut Boltz' eigenem
     Fortschrittsbalken], CIF→PDB-Konvertierung). Konfidenzwerte real und
     plausibel: `complex_plddt` 0.84-0.88, `confidence_score` 0.70-0.74,
     `ptm` niedrig (~0.13-0.17 — für ein derart kurzes, unstrukturiertes
     Peptid ohne festes Fold plausibel, pTM misst globale Faltähnlichkeit
     und ist bei 9 Resten kaum aussagekräftig).
5. **Zusätzlich, aus der bekannten "RDNA3 + PyTorch<2.14"-Performance-Notiz
   in AMDs eigener Doku:** `TORCH_BLAS_PREFER_HIPBLASLT=1` wird jetzt als
   Umgebungsvariable für den Boltz-Subprozess gesetzt (`folding.py`,
   `_run_boltz()`) — AMDs Empfehlung gegen "lower-than-expected
   performance" bei dieser PyTorch/ROCm-Kombination.

**Phase 1 — Backend (`backend/folding.py`, neue Datei, analog zu
`peptide.py`/`docking.py` aufgebaut):**
- `build_folding(name?, sequence?)` -- gleiche Namens-/Sequenz-Auflösung wie
  `peptide.py` (dieselbe kuratierte Kurzliste: Oxytocin, Vasopressin,
  Met-/Leu-Enkephalin, plus freie Sequenzeingabe), aber **kein** RDKit-Mol
  aus der Sequenz gebaut -- die 3D-Koordinaten kommen komplett aus Boltz-2s
  Vorhersage.
- Schreibt eine minimale FASTA (`>A|protein\n<SEQUENZ>`, bewusst **ohne**
  `|empty` im Header -- das würde die MSA für diese Kette abschalten, hier
  soll `--use_msa_server` sie echt berechnen), ruft
  `.venv-boltz/Scripts/boltz.exe predict` per `subprocess` auf (`--use_msa_server
  --recycling_steps 3 --diffusion_samples 1 --no_kernels`, `TIMEOUT_SECONDS =
  600` fürs eigentliche Zeitbudget je Anfrage -- der einmalige
  Gewichts-Download ist davon *nicht* mehr betroffen, da die Gewichte durch
  Phase 0 jetzt dauerhaft in `~/.boltz/` liegen).
- Ergebnis-Dateien werden per `Path.rglob()` gesucht statt über einen starr
  angenommenen Ordnerpfad (Boltz-Ordnernamen können je nach Version
  variieren) -- CIF-Struktur + `confidence_*.json` werden so gefunden, auch
  wenn sich das genaue Verzeichnis-Layout mal ändert.
- **CIF → PDB-Block per `gemmi`** (war als ungenutzte `meeko`-Abhängigkeit
  schon in `backend/.venv`, siehe frühere Einträge), dann exakt das gleiche
  Muster wie bei PDB-Liganden in `docking.py`: `Chem.MolFromPDBBlock(...,
  proximityBonding=True)` für die Bindungserkennung (Boltz-2 selbst liefert
  keine Bindungsliste, nur Atompositionen), **keine** Wasserstoffe ergänzt
  (reale vorhergesagte Geometrie, keine erfundenen H-Positionen), Fakten-Panel
  entsprechend nur Summenformel+Molmasse (die anderen fünf Felder "–") --
  `docking._hill_formula`/`docking._atoms_molweight` direkt wiederverwendet
  statt dupliziert.
- Konfidenzwerte (`confidence_score`, `complex_plddt`, `ptm` aus Boltz-2s
  `confidence_*.json`) werden in die `note` eingebaut (z.B. "pLDDT (Komplex)
  87/100, pTM 0.15, Gesamt-Konfidenz 0.73") und zusätzlich als eigenes
  `confidence`-Feld in der Antwort mitgegeben -- wichtig, um "echte
  Vorhersage mit Konfidenz" von "geraten" zu unterscheiden, wie im Auftrag
  gefordert.
- `MAX_RESIDUES = 50` -- **bewusst konservativ und NICHT empirisch
  verifiziert** (nur mit 9 Resten getestet, siehe "Bekannte Grenzen" unten).
- Route `POST /api/fold {name?, sequence?}` in `app.py`, exakt gleiches
  Antwortformat wie `/api/resolve`/`/api/peptide` -- am Frontend musste dafür
  nichts Neues gebaut werden, nur die neue Sektion selbst.
- **Bewusst kein neuer `pytest`-Test in `test_api.py`:** ein einzelner
  Boltz-2-Aufruf dauert (nach dem einmaligen Gewichts-Download) ~30-60s und
  braucht eine Internetverbindung zum MSA-Server -- das würde die sonst
  sekundenschnelle Test-Suite drastisch verlangsamen. Stattdessen manuell
  getestet: `python folding.py` (eigener `__main__`-Testblock, analog zu
  `peptide.py`) und ein echter Request über den laufenden Server (siehe
  Phase 2).

**Phase 2 — Frontend (`frontend/index.html`, `app.js`):**
- Neue Sektion "Protein-Struktur-Vorhersage (Boltz-2)" ganz unten, nach dem
  Muster von Molekulardynamik/Docking (`docking-controls`-Klasse
  wiederverwendet, kein neues CSS nötig) -- Eingabefeld (erkennt automatisch,
  ob Sequenz oder kuratierter Name eingegeben wurde, per Regex auf die 20
  Aminosäure-Buchstaben), "Beispiel laden" (füllt "Oxytocin"),
  "Vorhersagen"-Button.
- Erklärender Absatz direkt unter der Sektions-Überschrift, der den
  Unterschied zur RDKit-Näherung oben ("Kleine Peptide") und die deutlich
  längere Wartezeit vorab benennt -- genau wie im Auftrag gefordert
  ("deutlich sichtbare 'wird berechnet…'-Anzeige mit realistischer
  Zeit-Erwartung"). Während der Berechnung: "Wird mit Boltz-2 berechnet …
  das kann je nach Sequenzlänge und Hardware mehrere Minuten dauern."

**Getestet, inklusive echter visueller Bestätigung (Nachtrag kurz nach dem
autonomen Durchlauf, sobald das Browser-Pane wieder sichtbar war):**
- **API/Daten-Ebene vollständig bestätigt, über den echten laufenden
  Server:** `POST /api/fold {"name": "oxytocin"}` im Browser über die neue
  UI ausgelöst → `200 OK`, `common_name` "oxytocin (Boltz-2-Vorhersage, 9
  Reste)", 68 Atome/70 Bindungen, Summenformel `C43N11O12S2`, Konfidenz-Text
  korrekt gerendert im Info-Feld, keine Konsolenfehler. Atomkoordinaten
  direkt geprüft (per Skript aus dem echten CIF extrahiert) -- plausible
  Werte im Å-Bereich, keine NaN/Ausreißer.
- **3D-Rendering per echtem Screenshot bestätigt, sobald das Browser-Pane
  sichtbar war:** kompakte, sichtbar gefaltete Peptidstruktur (Kugel-Stab,
  Elemente korrekt eingefärbt) statt einer offenen Kette -- deutlich vom
  Aussehen der RDKit-Näherung unterscheidbar. Im autonomen Durchlauf selbst
  war das Pane ohne sichtbares Fenster, wodurch `requestAnimationFrame`
  nachweislich gar nicht feuerte (bestätigt per Zähler-Test, betraf auch die
  längst bewährte "Wasser"-Karte -- also ein reines Sichtbarkeits-Merkmal
  des Panes, keine Regression durch diese Änderung). Ein direkter
  `gl.readPixels()`-Check von außen war zusätzlich unzuverlässig (0 non-
  schwarze Pixel gemeldet, obwohl der echte Screenshot danach das Molekül
  korrekt zeigte) -- vermutlich Timing/Buffer-Clearing bei
  `preserveDrawingBuffer: false`. **Für künftige Sichtprüfungen: echten
  Screenshot nehmen, nicht `gl.readPixels()` von außen.**
- Server läuft bereits (`uvicorn app:app --port 8001`, im Hintergrund
  gestartet) -- `http://localhost:8001` direkt öffnen, keine weiteren
  Schritte nötig.

**Bekannte Grenzen, offen benannt (gleiche Linie wie beim Rest des
Projekts):**
- **`MAX_RESIDUES = 50` ist eine konservative Setzung, keine gemessene
  Grenze** -- aus Zeitgründen (1,5-Std.-Fenster, ein Großteil davon ging in
  Phase 0 drauf) wurde nur eine einzige, sehr kurze Sequenz (Oxytocin, 9 AS)
  tatsächlich durchgerechnet. Wie sich die Laufzeit mit der Sequenzlänge
  skaliert (Boltz-2s Aufwand wächst überproportional mit der Länge, wie bei
  AlphaFold-artigen Modellen üblich) ist auf dieser Hardware **nicht**
  empirisch geprüft. Vor produktivem Vertrauen in die 50-Reste-Grenze: eine
  mittelgroße (~30-40 AS) und eine nahe an der Grenze liegende Sequenz einmal
  testen und Zeit stoppen.
- **ROCm-Nutzung bestätigt, aber nicht tiefenoptimiert:** `--no_kernels`
  schaltet AMDs fehlende cuequivariance-Kernel ab -- das kostet Performance
  gegenüber einer echten NVIDIA-Karte mit den optimierten Kerneln, ist aber
  die einzige Möglichkeit, dass es auf dieser Hardware überhaupt läuft. Ob
  `bfloat16`-AMP auf RDNA3 tatsächlich schneller ist als reines `float32`,
  wurde nicht separat gemessen.
- **MSA-Server-Abhängigkeit:** `--use_msa_server` schickt die Sequenz an den
  öffentlichen `api.colabfold.com`-Dienst -- funktioniert nur mit
  Internetverbindung, keine eigene Kontrolle über dessen Verfügbarkeit/
  Rate-Limits. Für sehr kurze Peptide (wie die 9 AS von Oxytocin) liefert
  eine MSA ohnehin kaum zusätzliches evolutionäres Signal -- der Nutzen
  wächst mit der Sequenzlänge.
- **Erster Aufruf auf einer neuen Maschine lädt ca. 5,8 GB** (einmalig, dann
  dauerhaft unter `~/.boltz/` gecacht) -- das `TIMEOUT_SECONDS = 600`-Budget
  in `folding.py` ist NICHT für diesen einmaligen Download ausgelegt (siehe
  Stolperstein 1 oben). Falls Niki das Projekt auf einem anderen Rechner
  aufsetzt: die Gewichte vorher einmal manuell/mit großzügigerem Timeout
  herunterladen lassen, nicht direkt über die App-Route.
- Keine Bindungsaffinitäts-Vorhersage, kein Multi-Ligand-Co-Folding -- wie
  im Auftrag als Nicht-Ziel dieser Stufe festgelegt.

## 2026-09-20: Eingabe vereinfacht — Markennamen statt Wirkstoffnamen

Nikis Wunsch: im Haupt-Suchfeld (und überall sonst, wo `chem.resolve`/
`chem._resolve_to_names` verwendet wird) sollen Nutzer:innen keinen
wissenschaftlichen/generischen Wirkstoffnamen kennen müssen, sondern den
Markennamen eingeben können, den sie tatsächlich kennen (z.B. "Mexalen" statt
"Paracetamol"). Ausdrücklich außerhalb des Scopes: Ozempic/Semaglutid soll
weiterhin **nicht** als 3D-Struktur im Hauptfeld funktionieren -- laut Niki
"noch zu schwierig", siehe unten, wie das trotzdem sauber statt mit einem
wirren Fehler abgefangen wird.

**Neue Datei `backend/brand_names.py`**: `BRAND_TO_SUBSTANCE`, ein Dict von
kleingeschriebenem Markennamen auf den Wirkstoffnamen, den PubChems
Namenssuche sicher kennt. Aktuell ~20 Einträge, Schwerpunkt
österreichische/deutsche OTC-Marken (Mexalen, Ben-u-ron, Voltaren, Nurofen,
Novalgin, Buscopan, Thomapyrin) plus ein paar international bekannte (Xanax,
Valium, Prozac, Ritalin, Viagra, Tylenol, Advil) und die GLP-1-/
Insulin-Präparate (Ozempic, Wegovy, Mounjaro, Victoza, Trulicity, Lantus,
...) -- Letztere werden zwar über den Markennamen gefunden, laufen aber
bewusst in den neuen Fehlerfall unten statt in eine Struktur.

**`backend/chem.py`, `_resolve_to_names()` erweitert**: neuer Schritt
zwischen SMILES-Versuch und PubChem-Namenssuche -- Markenname (lowercase,
getrimmt) in `BRAND_TO_SUBSTANCE` nachschlagen, bei Treffer den übersetzten
Wirkstoffnamen statt der Rohangabe an PubChem schicken. `note` sagt dann z.B.
„Mexalen" wurde als Markenname für Acetaminophen erkannt." -- nutzt das
schon vorhandene `note`-Feld/UI-Element, keine Frontend-Logik-Änderung dafür
nötig. Kein Treffer im Dict → Ablauf komplett wie vorher (viele
internationale Marken kennt PubChems eigene Synonymliste ohnehin schon
direkt, z.B. Aspirin).

**Neuer Schutz `MAX_HEAVY_ATOMS = 150` in `_build_structure()`**: bricht mit
klarer Fehlermeldung ab, statt ein `EmbedMolecule` auf einem riesigen
Peptid/Protein zu versuchen (kann ewig laufen oder eine sinnlose Struktur
liefern). Das ist der generelle Fall, der auch Ozempic (Semaglutid, großes
modifiziertes Peptid) sauber abfängt, sobald es über den Markennamen bei
PubChem gefunden wurde -- ohne dass Ozempic einzeln im Code speziell
behandelt werden musste. Betrifft nur `chem._build_structure` -- der
separate Peptid-Modus (`peptide.py`, nutzt `chem._compute_facts` direkt,
eigenes Limit von 15 Resten) ist davon nicht berührt.

**Generalisiert automatisch auf Docking- und MD-Eingabe**, weil `docking.py`
(Ligand-Feld) und `dynamics.py` beide direkt `chem._resolve_to_names()`
aufrufen -- keine Änderungen dort nötig.

**Frontend (`frontend/index.html`)**: Placeholder-Texte in den Eingabefeldern,
die über `chem.resolve`/`_resolve_to_names` laufen (Haupt-Suchfeld,
Chemischer Raum, Docking-Ligand, Molekulardynamik) von "Name, Formel oder
SMILES" auf "Name, Markenname, Formel oder SMILES" erweitert, mit Mexalen als
Beispiel im Haupt- und MD-Feld -- signalisiert von vornherein, dass
Markennamen funktionieren, ohne dass man es erst ausprobieren muss.

**Backend-Tests ergänzt** (`backend/tests/test_api.py`, 3 neue): Mexalen →
Paracetamol/Acetaminophen mit Markennamen-Hinweis im `note`-Feld,
Groß-/Kleinschreibung ("mexalen"), Ozempic → 400 mit erklärender
"zu groß"-Fehlermeldung.

**Nicht selbst ausgeführt/getestet:** diese Änderung kam aus einer
Cloud-Sitzung ohne Terminalzugriff auf diesem PC (nur Datei-Lesen/Schreiben
über die Gerätebrücke) -- pytest lief hier nicht, der Browser-Test auch
nicht. Vor dem nächsten "richtigen" Arbeiten an diesem Projekt:
`cd backend && pytest` laufen lassen (v.a. die 3 neuen Tests -- die genauen
PubChem-Titel/Synonyme für Mexalen/Ozempic wurden aus Wissen heraus
angenommen, nicht live geprüft) und die Markennamen kurz im Browser
ausprobieren.

**Bekannte Grenzen, offen:** `BRAND_TO_SUBSTANCE` ist eine reine
Handlisten-Lösung -- neue/exotische Marken (v.a. außerhalb AT/DE oder ganz
neue Präparate) funktionieren nur, wenn PubChems eigene Synonymliste sie
kennt oder jemand sie manuell in die Liste einträgt. Eine "richtige" Fuzzy-/
Autocomplete-Lösung (z.B. PubChems Autocomplete-Endpunkt) wäre der nächste
Schritt, falls das im Alltag zu oft nicht reicht.

## 2026-09-19 (noch später): Ausbaustufe — kleine Peptide per Sequenzeingabe

Niki wollte die "mittlere Stufe" aus einer vorherigen Besprechung: kleine
Peptide (bis ~15 Aminosäuren) lokal mit RDKit als angenäherte 3D-Struktur
anzeigen -- explizit **nicht** die Semaglutid/Ozempic-Größenordnung (die läuft
weiter über echte Kristallstrukturen, siehe `docking.pdb_ligand()`) und
**nicht** echtes Protein-Folding (Boltz-2 o.ä., eigenes späteres Vorhaben).
Kernproblem: Namen wie "Oxytocin"/"Vasopressin" scheitern an PubChems
unzuverlässiger Peptid-Namenssuche, und selbst wenn die Auflösung klappt, ist
ein einzelner `EmbedMolecule`-Versuch für Moleküle mit vielen drehbaren
Bindungen zu zufällig.

**Neue Datei `backend/peptide.py`** (eigene Datei statt Erweiterung von
`chem.py` -- andere Eingabeform, kein PubChem-Netzwerkaufruf nötig, passt als
eigenständiges Modul besser zum bestehenden Muster wie `docking.py`/
`chemspace.py`):

1. **Sequenz statt Name als primärer Eingabeweg.** `Chem.MolFromSequence()`
   baut aus einem Ein-Buchstaben-Aminosäurecode (z.B. `CYIQNCPLG` für
   Oxytocin) direkt ein RDKit-Mol -- kein PubChem nötig, keine Namensauflösung,
   die für Peptide ohnehin unzuverlässig ist.
2. **Längenlimit 15 Reste, hart durchgesetzt** (`MAX_RESIDUES`), gleiche Linie
   wie beim Docking ohne brauchbaren Liganden (1UBQ-Fall) -- klare
   Fehlermeldung statt eines langsamen/sinnlosen Embedding-Versuchs.
3. **Bessere Einbettung: `EmbedMultipleConfs` (12 Konformere) + MMFF-Optimierung
   jedes einzelnen + das energieärmste behalten** (`_embed_lowest_energy`),
   statt nur einem einzelnen `EmbedMolecule`-Versuch. `useRandomCoords=True`
   gesetzt -- hilft besonders bei den durch die Disulfidbrücke (siehe Punkt 5)
   zyklischen Strukturen. Immer noch keine biologisch validierte Faltung, aber
   deutlich weniger Zufallsergebnis.
4. **Ehrlich gekennzeichnet, gleiche Linie wie bei Formel-Heuristik/Docking-
   Ladungszuständen/MD-Force-Capping:** die zurückgegebene `note` sagt klar,
   dass es eine berechnete Niedrigenergie-Konformation ist (keine gemessene
   oder biologisch bestätigte Struktur), UND dass die Termini als freies Amin/
   freie Carbonsäure aufgebaut sind -- posttranslationale Modifikationen wie
   die C-terminale Amidierung bei echtem Oxytocin/Vasopressin fehlen (per
   Testlauf entdeckt: ohne Amidierung hat unser Oxytocin ein N/O zu wenig/viel
   gegenüber der echten Summenformel -- kein Fehler, sondern eine bewusste,
   jetzt offen benannte Vereinfachung).
5. **Spontane Ergänzung, nicht in Nikis ursprünglicher Liste, aber ohne sie
   wäre die namensgebende Ringstruktur von Oxytocin/Vasopressin komplett
   verloren gegangen:** `_add_disulfide_if_two_cysteines()` -- enthält die
   Sequenz genau 2 Cystein-Reste, wird eine Disulfidbrücke zwischen ihren
   Thiolschwefeln geknüpft (Atome über `GetPDBResidueInfo()` gefunden, Bindung
   per `RWMol.AddBond` + `SetNoImplicit`/`SetNumExplicitHs(0)` auf den beiden
   Schwefeln, dann neu sanitisiert). Ohne das wären es nur zwei lose SH-Enden
   statt eines Rings -- optisch und chemisch der auffälligste Unterschied.
   Reine Heuristik (genau 2 Cystein → verbinden), keine chemische Bestätigung,
   dass diese beiden Reste in der echten Struktur wirklich verbrückt sind, aber
   für die beiden kuratierten Beispiele stimmt es. Im Browser bestätigt: die
   3D-Struktur ist sichtbar kompakt/geknäult statt einer langen offenen Kette.
6. **Kuratierte Namens-Liste** (`_KNOWN_PEPTIDES`): Oxytocin, Vasopressin,
   Met-Enkephalin, Leu-Enkephalin → feste Sequenz. `sequence`-Feld hat Vorrang
   vor `name`, falls beide angegeben würden (kommt in der Praxis nicht vor,
   das Frontend nutzt pro Aufruf nur eins von beiden).
7. **Route `POST /api/peptide {name?, sequence?}`** (`app.py`), exakt gleiches
   Antwortformat wie `/api/resolve` (`atoms`/`bonds`/`facts`/`common_name`/
   `iupac_name`/`note`) -- am Frontend musste dafür nichts Neues gebaut werden,
   nur `applyResolvedData()` wiederverwendet.

**Frontend (`frontend/app.js`):** neue Bibliothek-Kategorie "Kleine Peptide
(angenäherte Faltung)" nach dem Muster der bestehenden "Peptid-Wirkstoffe"-
Kategorie (`className: "library-category-peptide"`, gleicher gestrichelter
Rand über die schon vorhandene CSS-Regel, erklärender Hinweistext), mit 4
Karten (Oxytocin/Vasopressin/Met-Enkephalin/Leu-Enkephalin) die
`loadPeptideIntoSlot(0, peptideName, null)` aufrufen. Zusätzlich ein eigenes
Eingabefeld+Button ("Peptid laden") direkt unter den Karten
(`createPeptideSequenceRow()`, `category.customSequenceInput`-Flag in
`renderLibrary()`), für alle, die eine eigene Sequenz eintippen wollen --
ruft `loadPeptideIntoSlot(0, null, sequence)`. CSS: nur eine Zeile
(`.peptide-sequence-row { margin-top: 10px; }`) ergänzt, sonst komplett
`.docking-controls`-Klasse wiederverwendet (Input+Button-Styling schon
vorhanden).

**Backend-Tests ergänzt** (`backend/tests/test_api.py`, 6 neue): Oxytocin per
kuratiertem Namen (prüft auch explizit die Disulfidbrücken-Heuristik -- genau
2 Schwefelatome, echte S-S-Bindung zwischen ihnen in den zurückgegebenen
`bonds`), eigene Sequenz (`YGGFM`), zu lange Sequenz → 400, ungültige
Aminosäure-Buchstaben → 400, unbekannter kuratierter Name → 400, weder Name
noch Sequenz → 400. Alle 22 Backend-Tests grün (16 alte + 6 neue).

**Getestet im Browser:** Oxytocin- und Vasopressin-Karte laden sichtbar
kompakte, geknäulte Strukturen (nicht offene Ketten) mit korrektem
Namens-Label ("OXYTOCIN (PEPTID, 9 RESTE)") und Fakten-Panel (Oxytocin:
`C43H65N11O13S2`, 1008.19 g/mol); Hinweistext erscheint korrekt mit allen drei
Ehrlichkeits-Punkten (Näherung/Termini/Disulfidbrücke). Eigene Sequenz manuell
eingetippt (`GRGDSP`, RGD-Zelladhäsionsmotiv) -- lädt korrekt, Fakten-Panel
stimmt. Zu lange Sequenz (Insulin-A-Kette, 21 Reste) über dasselbe Feld
eingetippt -- klare rote Fehlermeldung mit der 15-Reste-Grenze, kein Absturz.
Danach Regressionscheck: normale Auflösung ("water") über das Haupt-Eingabefeld
nochmal geprüft, lief einwandfrei (Hinweistext wurde korrekt geleert). Keine
unerwarteten Konsolenfehler (nur der erwartete, vom Frontend sauber behandelte
400 beim Zu-lang-Test).

**Nebenbei aufgetreten -- der bekannte Server-Fallstrick war wieder da:** Ein
alter Uvicorn-Prozess von einer früheren Sitzung hing noch auf Port 8001
(`netstat -ano | grep ":8001"` zeigte ihn als `ABHÖREN`, wegen deutscher
Locale nicht als "LISTENING" -- Grep-Filter darauf muss das berücksichtigen).
`taskkill /F /PID <pid> /T` auf die gefundene PID hat wie gewohnt gereicht.

## 2026-09-19 (Fortsetzung): Insulin an seinem Rezeptor (4OGA) ergänzt

Direkte Folge auf den Eintrag unten, in derselben Sitzung: Niki wollte Insulin
doch noch in die Bibliothek aufnehmen, obwohl die vorherige Runde 4INS (Insulin
allein, ohne Rezeptor) dafür als ungeeignet verworfen hatte.

**4OGA gefunden und verifiziert** ("Insulin in complex with Site 1 of the
human insulin receptor", per echtem RCSB-Abruf bestätigt) — aber ein
komplizierterer Fall als Semaglutid: 6 Ketten (A=21, B=21 sichtbare Reste
[volle B-Kette hat 30, der Rest ist im Kristall ungeordnet — beim Andocken an
den Rezeptor löst sich das B-Ketten-Ende bekanntermaßen vom Insulin-Kern,
passt also zur echten Biologie], C=118, D=114, E=288, F=15/16). Insulin
besteht aus **zwei** Ketten (A+B, über 3 Disulfidbrücken verbunden) — die
bestehende "kürzeste-Kette"-Heuristik aus dem Eintrag unten kann das nicht
abbilden. Schlimmer: **Kette F (15 Reste) ist selbst kürzer als A oder B**
und gehört zum Rezeptor (das "α-CT-Peptid", ein rezeptor-eigenes Fragment,
das an der Bindungsstelle mitwirkt) — die Heuristik hätte also nicht nur
"nur eine Kette statt zwei" gewählt, sondern die **falsche** Kette.

**Lösung: `chain_ids` als dritte, explizite Auswahl-Möglichkeit in
`_find_ligand_lines()`** (`backend/docking.py`), geprüft VOR der Peptid-
Heuristik und dem HETATM-Fall. Übergibt man `chain_ids: ["A", "B"]`, werden
genau diese Ketten kombiniert und die Heuristik komplett übersprungen — kein
Rätselraten mehr nötig, wenn die Kettenzugehörigkeit ohnehin bekannt ist (wie
hier: aus der Biologie, nicht aus der Struktur allein ableitbar). Per
Diagnose-Skript vorab bestätigt, dass RDKits `ConnectTheDots`-Bindungs-
erkennung dabei alle **3 echten Insulin-Disulfidbrücken** (A6-A11, A7-B7,
A20-B19 — mit der Literatur abgeglichen) über die Kettengrenze hinweg
korrekt findet, rein aus dem 3D-Abstand der Schwefelatome. `hetero_code` und
`chain_ids` schließen sich gegenseitig aus (chain_ids hat Vorrang, falls
beide angegeben würden — kommt in der Praxis aber nicht vor, das Frontend
nutzt nur eins von beiden pro Bibliothek-Karte).

`POST /api/pdb-ligand` und `pdb_ligand()` haben dafür ein neues optionales
Feld/Argument `chain_ids` bekommen. Frontend: neue Karte "Insulin (an seinem
Rezeptor)" in der "Peptid-Wirkstoffe"-Kategorie (`frontend/app.js`,
`{pdbId: "4OGA", chainIds: ["A", "B"]}`), `loadPdbLigandIntoSlot()`/
`resolvePdbLigand()` geben `chainIds` einfach durch.

Backend-Tests ergänzt: expliziter Zwei-Ketten-Fall (prüft u.a. die 6
Schwefelatome), unbekannte Ketten-ID → 400.

**Getestet im Browser:** Klick auf "Insulin (an seinem Rezeptor)" lädt
sichtbar eine kompakte, verknäulte Kernstruktur mit einem längeren,
freihängenden Ende (genau die erwartete Form — kompakter A/B-Kern plus das
ungeordnete B-Ketten-Ende) statt einer einzelnen kurzen Kette. Fakten-Panel
zeigt Summenformel (`C207N51O63S6`, 6 Schwefel — stimmt mit den 3
Disulfidbrücken überein) und Molmasse korrekt, die übrigen fünf Felder als
"–". Hinweistext erklärt korrekt, dass eine feste Kettenauswahl statt der
Längen-Heuristik verwendet wurde. Keine Konsolenfehler.

## 2026-09-19 (autonomer Durchlauf, ~45 Min.): PDB-Liganden direkt anzeigen + Bibliothek-Bereich

Niki war ~30-60 Min. weg und hat zwei zusammenhängende Erweiterungen als fertige
Prompts vorgelegt: bei normalen Umsetzungsentscheidungen selbst entscheiden statt
zu warten, nur bei echten Sackgassen anhalten. Beide Teile sind fertig geworden.

**Teil 1 — `POST /api/pdb-ligand` (neu, `backend/docking.py` + `backend/app.py`):**
Lädt eine PDB-Struktur und zeigt den darin gefundenen Liganden als eigenständiges
Molekül, ganz ohne Docking-Rechnung — gleiches Antwortformat wie `/api/resolve`
(`atoms`/`bonds`/`facts`/`common_name`/`iupac_name`/`note`), damit das Frontend
nichts Neues dafür bauen musste.

- Bewusst **keine** ergänzten Wasserstoffe (anders als `chem._build_structure()`)
  — das wären erfundene H-Positionen auf einer real gemessenen Geometrie. Aus
  dem gleichen Grund auch keine RDKit-Deskriptoren (LogP/TPSA/H-Brücken/drehbare
  Bindungen) — die bräuchten korrekte Valenzen inkl. H. Diese fünf Fakten-Felder
  zeigen für PDB-Liganden ein `"–"`. Nur Summenformel und Molmasse werden direkt
  aus den vorhandenen (Schwer-)Atomen berechnet, per RDKits Periodensystem
  (`Chem.GetPeriodicTable()`) statt einer selbst gepflegten Atomgewichts-Tabelle.
- Bindungen kommen aus `Chem.MolFromPDBBlock(..., proximityBonding=True)` —
  RDKits eigene Abstands-Bindungserkennung (`ConnectTheDots`), unsanitisiert.
  Bindungsordnung ist damit geraten, nicht chemisch bewiesen — für die reine
  3D-Darstellung egal, weil der Viewer Bindungen ohnehin nur als Zylinder ohne
  Doppelbindungs-Unterscheidung zeichnet.
- **Zwei Liganden-Fälle, in dieser Reihenfolge geprüft** (`_find_ligand_lines()`):
  1. **Peptid-Ligand-Heuristik, bewusst VOR der Klein-Molekül-Suche geprüft:**
     gibt es eine Protein-Kette in Peptid-Wirkstoff-Länge (5-60 Reste) UND eine
     deutlich längere Kette (das vermutliche Zielprotein), wird die kürzeste
     solche Kette als Ligand behandelt. Musste vor dem HETATM-Fall kommen, weil
     4ZGM (siehe unten) zusätzlich ein für den Liganden irrelevantes HETATM-
     Molekül (`32M`, ein PEG-artiger Kristallisationszusatz, laut RCSB-Chemcomp-
     API "3,6,9,12,15,18-hexaoxahexacosan-1-ol") neben der Peptidkette hat — mit
     der ursprünglichen Reihenfolge (HETATM zuerst) wäre fälschlich das PEG-
     Molekül als "Ligand" gewählt worden. Per echtem RCSB-Abruf verifiziert:
     4ZGM hat Kette A (100 Reste, GLP-1-Rezeptor-ECD) und Kette B (28 Reste,
     Semaglutid) — B wird korrekt gewählt. 7KI0 (Kette P, 29 Reste, unter A/B/G/N/R
     mit 56-384 Resten) ebenso. Offen benannt in der zurückgegebenen `note`:
     reine Längen-Heuristik, keine chemische Bestätigung der Identität.
  2. **Klein-Molekül-HETATM** (wie schon beim Docking, `_find_reference_ligand`):
     die größte Nicht-Ignorierte HETATM-Gruppe, optional per `hetero_code`
     (PDB-Chemical-Component-ID, z. B. `"BEN"`) gezielt ausgewählt.
- **Insulin (4INS) zuerst geprüft, aber NICHT verwendet:** 4INS enthält nur
  die vier kurzen Insulin-Ketten (A/B/C/D, 21-30 Reste) ohne Rezeptor — die
  Peptid-Heuristik braucht eine deutlich längere Gegenkette, um zwischen
  "Ligand" und "Rezeptor" zu unterscheiden, die hier fehlt. Stattdessen
  **4OGA** ("Insulin in complex with Site 1 of the human insulin receptor")
  verwendet — siehe Folge-Eintrag unten, dort kam noch eine dritte
  Auswahl-Möglichkeit (`chain_ids`) dazu, die dieser erste Durchlauf noch
  nicht hatte.
- Backend-Tests ergänzt (`backend/tests/test_api.py`): Klein-Molekül-Fall
  (3PTB/Benzamidin), Peptid-Fallback (4ZGM/Semaglutid), ungültige PDB-ID.

**Teil 2 — Bibliothek-Bereich (`frontend/index.html`, `style.css`, `app.js`):**
Neue Sektion direkt unter dem Header, über dem Eingabefeld (als der zuerst
sichtbare, einfachste Einstieg für Chemie-Anfänger) — Kategorien mit
anklickbaren Karten, kein Fachjargon in der Auswahl selbst (Formel/SMILES
zeigt das Fakten-Panel nach dem Laden ohnehin automatisch).

- Kategorien wie vorgegeben (Alltagsstoffe, Schmerz & Fieber, Bausteine des
  Körpers, Vitamine, Süßes & Fette), plus zwei zusätzliche, die zum schon
  vorhandenen `CHEMSPACE_EXAMPLE_SET` passen: **Hormone** (Testosteron war
  schon im chemspace-Set; dazu Östrogen/Estradiol, Adrenalin/Epinephrin) und
  **Haushalt & Reinigung** (Essigsäure — auch Edukt der Veresterungs-Reaktion
  weiter unten —, Isopropanol als "Desinfektionsmittel").
- Eigene Kategorie **"Peptid-Wirkstoffe (aus echten 3D-Messungen)"** mit einer
  Karte "Ozempic / Semaglutid" (PDB `4ZGM`), die **nicht** `/api/resolve`
  aufruft, sondern den neuen `/api/pdb-ligand`-Endpunkt aus Teil 1 — visuell
  durch gestrichelte Kartenränder (`.library-category-peptide`) leicht von den
  übrigen, per Namen auflösbaren Karten abgesetzt, plus ein erklärender
  Hinweistext direkt unter dem Kategorietitel.
- Technisch: hartkodierte `LIBRARY_CATEGORIES`-Liste in `app.js` (gleiches
  Muster wie `CHEMSPACE_EXAMPLE_SET`), Karten dynamisch gerendert. Ein Klick
  ruft `loadIntoSlot()` bzw. (Peptid-Karte) das neue `loadPdbLigandIntoSlot()`
  auf — beide teilen sich jetzt eine gemeinsame `applyResolvedData()`-Funktion
  (kleiner Refactor von `loadIntoSlot()`, das vorher die Anzeige-Logik direkt
  enthielt), landen im Haupt-Viewer wie beim Chemischer-Raum-Klick, inkl.
  sanftem Scroll nach oben.

**Getestet im Browser** (`http://localhost:8001`, alle über die neuen
Bibliothek-Karten UND direkt per `/api/resolve`-Aufruf gegengeprüft): Aspirin
lädt korrekt aus der Bibliothek; Vitamin C löst zu "L-Ascorbic Acid" auf;
Vitamin D (`cholecalciferol`), Testosteron, Östrogen (`estradiol`), Adrenalin
(`epinephrine`), Essig (`acetic acid`), Desinfektionsmittel (`isopropanol`)
und Zucker (`sucrose`) lösen alle korrekt auf. **Ozempic/Semaglutid-Karte**
(der wichtigste Testfall): lädt die reale Semaglutid-Kette aus 4ZGM, zeigt
sichtbar eine lange, verzweigte Peptidkette (keine kompakte kleine
Molekülform), Fakten-Panel zeigt Summenformel/Molmasse korrekt und die
restlichen fünf Felder korrekt als "–", Hinweistext erklärt die
Peptid-Heuristik offen. Keine Konsolenfehler. Regressionscheck: normale
Auflösung ("water" über das Eingabefeld) danach nochmal geprüft, lief
einwandfrei.

**Nebenbei aufgetreten — ein neuer Cache-Fallstrick, dokumentiert statt
behoben (Browser-Verhalten, kein Code-Fehler):** Der allererste Ladeversuch
zeigte die neuen Bibliothek-Karten optisch falsch (helle Standard-Button-
Farben statt der dunklen `.library-card`-Gestaltung), obwohl `style.css` auf
der Platte längst korrekt war. Ursache gefunden: `backend/app.py`s
`StaticFiles`-Mount setzt keine `Cache-Control`-Header, und der Browser hatte
`style.css` von einer früheren Sitzung (vor dieser Änderung) noch im
HTTP-Cache und hat nicht neu validiert — selbst ein neuer Tab traf denselben
Cache. Ein `fetch(..., {cache: "no-store"})` bekam sofort die korrekte,
aktuelle Version. Für Niki relevant: **falls nach einer Frontend-Änderung an
`style.css`/`app.js` die Seite optisch/funktional noch alt aussieht, obwohl
der Server-Neustart nichts bringt (das ist ja ein reiner Static-File-Mount,
kein `--reload`-Ziel) — harter Neu-Laden im Browser (Strg+Shift+R) oder
Cache leeren, nicht am Code suchen.**

## 2026-09-19 (später): Ausbaustufe — Gleichungslöser, plus PubChem-Cache und Backend-Tests

Niki wollte eine 10. Ausbaustufe: eine frei eingetippte Reaktionsgleichung
(z. B. `CH4 + O2 -> CO2 + H2O`) automatisch ausgleichen lassen und gleich
als Morph-Animation zeigen, so wie die schon bestehende, handkuratierte
Reaktions-Animation. Dazu noch "die anderen Sachen" aus der letzten
Verbesserungsliste, soweit sinnvoll in einer Sitzung machbar.

**Neue Datei `backend/equation.py`.** Wichtiger Unterschied zu
`reactions.py`: dort ist die Atom-Zuordnung zwischen Edukt und Produkt von
Hand über Atom-Map-Nummern hinterlegt (100% korrekt, aber nur für die paar
vorbereiteten Beispiele). Bei einer frei eingetippten Gleichung gibt es
diese Handarbeit nicht -- welches Atom zu welchem wird, ist ein eigenes,
in der echten Cheminformatik ungelöstes Problem (reaction atom mapping,
normalerweise per ML-Modell angenähert, z. B. RXNMapper). Deshalb zwei
getrennte, unterschiedlich sichere Teile:

1. **Stöchiometrie-Ausgleich: exakt, kein Kompromiss.** Für jeden Stoff
   werden per RDKit die Elementzahlen gezählt, daraus eine Matrix gebaut
   (Edukte positiv, Produkte negativ) und deren Nullraum per Gauß-Jordan
   **über exakte Brüche** (`fractions.Fraction`, keine Gleitkomma-
   Rundungsfehler) berechnet, dann auf die kleinsten positiven Ganzzahlen
   skaliert. Klare Fehler statt stillem Rateversuch, wenn: kein Nullraum
   existiert (Elemente passen nicht zusammen), der Nullraum mehr als 1-
   dimensional ist (z. B. `C + O2 -> CO + CO2` -- durch Atomerhaltung
   allein nicht eindeutig lösbar), oder gemischte Vorzeichen nötig wären
   (Stoff steht auf der falschen Seite). Getestet: `CH4 + O2 -> CO2 + H2O`
   → `CH4 + 2 O2 -> CO2 + 2 H2O`, `H2 + O2 -> H2O` → `2 H2 + O2 -> 2 H2O`,
   `N2 + H2 -> NH3` → `N2 + 3 H2 -> 2 NH3` -- alle drei von Hand
   nachgerechnet korrekt.
2. **Atom-Zuordnung fürs Morphen: bewusst nur eine Näherung, offen
   benannt.** `_match_atoms()` löst pro Element ein Zuordnungsproblem
   (`scipy.optimize.linear_sum_assignment`, Ungarische Methode) nach
   räumlichem Abstand zwischen den unabhängig eingebetteten Start- und
   End-Layouts. Kein Versuch, echte Bindungsumlagerung nachzuvollziehen --
   für einfache Lehrbuch-Gleichungen (Verbrennung, Synthese) sieht das
   trotzdem chemisch sinnvoll aus (im Browser geprüft: `N2 + H2 -> NH3`
   morpht sauber zu zwei getrennten NH3-Klumpen, keine Atome springen
   chaotisch durcheinander), ist aber nicht chemisch bewiesen wie bei den
   handgemappten Beispielen oben. Gleiche "ehrliche Vereinfachung"-Linie
   wie bei der Formel-Heuristik, dem Docking und der MD -- im Frontend
   auch so als Hinweistext angezeigt, nicht versteckt.

**Datenformat bewusst identisch zu `reactions.build_reaction()`**
(`start`/`end`/`correspondence`/`persistent_bonds`/`broken_bonds`/
`formed_bonds`) -- dadurch war an `frontend/viewer.js` (`playReaction()`)
**keine einzige Zeile** zu ändern, nur `app.js` bekam eine neue, zum
bestehenden Muster passende Sektion (Eingabefeld, "Beispiel laden",
"Lösen & animieren", eigener Viewer). Ein bewusster Unterschied zu
`reactions.py`: dort werden Wasserstoffe nicht animiert (Skelett-Stil),
hier **schon** -- sonst wären viele der interessantesten Alltagsgleichungen
(Verbrennung, Ammoniak-Synthese, Neutralisation) fast leer, weil sie fast
nur aus Wasserstoff bestehen.

**Route:** `POST /api/equation {equation: str}` in `app.py`.

**PubChem-Caching ergänzt** (`chem.py`, `_name_cache`/`_smiles_cache`/
`_formula_cache`, einfache In-Memory-Dicts) -- war schon länger als
Verbesserungsidee notiert (siehe unten) und wurde jetzt gebraucht, weil
der Gleichungslöser pro Anfrage mehrere PubChem-Lookups auf einmal macht.
Bewusst kein Disk-Cache wie bei `pdb_cache/`: eine rohe Nutzereingabe als
Dateiname zu verwenden bräuchte erst eine Sanitisierung, ein In-Memory-
Dict ist für die Prozesslaufzeit genauso wirksam und hat dieses Problem
gar nicht erst.

**Backend-Tests ergänzt** (`backend/tests/`, `pytest` + FastAPI
`TestClient`, neue `backend/requirements-dev.txt`). Bewusst **keine**
Mocks -- die Tests rufen echte PubChem-/RCSB-/Vina-Aufrufe auf, genau wie
die App selbst, damit sie auch reale API-Änderungen auffangen (wie die
schon einmal erlebte PubChem-Feldumbenennung, siehe Fallstrick 2 weiter
unten). 11 Tests, alle grün: `/api/resolve` (Name, direktes SMILES,
Formel, unbekannte Eingabe), `/api/equation` (Verbrennung ausgeglichen,
fehlender Pfeil, unlösbare Gleichung), `/api/reactions`, `/api/dock`
(3PTB+Benzamidin wie von Niki vorgeschlagen, plus zwei Fehlerfälle).
Einzige Anpassung unterwegs: ein Test verließ sich darauf, dass PubChems
Formel-Mehrdeutigkeit für `C6H12O6` immer eine Notiz auslöst -- das ist
aber ein von PubChems aktuellem Datenbestand abhängiges Verhalten, kein
stabiler Vertrag, deshalb abgeschwächt auf "Formel wird korrekt aufgelöst".

**Nicht umgesetzt aus der letzten Ideen-Liste, bewusst zurückgestellt:**
Ladungszustände beim Docking (pKa-Vorhersage ist ein eigenes, nicht
triviales Teilproblem), SHAKE/RATTLE bei der MD (würde den Integrator
deutlich umbauen), Export/Screenshot-Funktion, Deployment auf
Render/Fly.io (braucht eigenen Account, Linux-Vina-Build). Alle vier
bleiben unten in der Ideen-Liste stehen.

**Getestet im Browser:** `CH4 + O2 -> CO2 + H2O` geladen und gelöst --
Label zeigt korrekt "Methane + 2 Oxygen → Carbon Dioxide + 2 Water",
Animation läuft sichtbar (CH4+2 O2 morphen zu CO2+2 H2O). Danach
`N2 + H2 -> NH3` von Hand eingetippt -- Label "Nitrogen + 3 Hydrogen →
2 Ammonia", Animation zeigt N2 + 3×H2 sauber zu 2× NH3 morphend. Keine
Konsolenfehler in beiden Fällen. Regressionscheck: normale Auflösung
("water") danach nochmal geprüft, lief einwandfrei.

## 2026-09-19: Fallstricke überprüft, ein echter Sicherheitsfund behoben, auf GitHub veröffentlicht

Niki hat gebeten, die dokumentierten Fallstricke/Verbesserungsideen nochmal
zu prüfen, selbst weiterzudenken, und das Projekt auf GitHub anzulegen.

**Fallstricke erneut geprüft — beide weiterhin gültig, keine akute
Blockade:** Aktuell hängt kein alter Uvicorn-Prozess auf Port 8001
(`netstat` leer). Der `--reload`-Fallstrick ist nicht reproduzierbar
prüfbar (trat unregelmäßig auf), bleibt aber als Hinweis stehen. Der
`ANTHROPIC_API_KEY`-Gap ist weiterhin offen (`backend/.env` existiert
noch nicht) — Ausbaustufe 5 wartet weiter auf Nikis eigenen Key.

**Beim Selbst-Nachdenken einen echten, bisher nicht dokumentierten Fund
gemacht: Path-Traversal über `pdb_id`.** `docking.fetch_pdb()` hat die
Nutzereingabe nur `.strip().upper()`t und dann ungeprüft in einen
Dateipfad eingesetzt (`PDB_CACHE_DIR / f"{pdb_id}.pdb"`). Eine PDB-ID wie
`../../irgendwas` hätte das Ergebnis der RCSB-Anfrage an eine beliebige
Stelle außerhalb von `pdb_cache/` schreiben können — bei einem Projekt,
das gerade öffentlich wird, ein echtes Risiko, nicht nur ein
Lehrbuch-Fall. **Behoben:** `_PDB_ID_RE = re.compile(r"^[0-9][A-Z0-9]{3}$")`
validiert jetzt gegen das echte PDB-ID-Format (4 Zeichen, erste Ziffer),
bevor irgendein Pfad gebaut wird — echte IDs wie `3PTB`/`1UBQ` bleiben
gültig, `../..`-artige Eingaben werden klar abgelehnt (per Testskript
gegengeprüft).

**Zwei weitere kleine Lücken schließen, bevor der Code öffentlich wird:**
- `backend/requirements.txt` ergänzt (`fastapi`, `uvicorn`, `rdkit`,
  `requests`, `anthropic`, `python-dotenv`, `numpy`, `meeko`, `scipy`,
  `gemmi`) — vorher stand die Paketliste nur als Freitext hier in
  `stand.md`, nicht als installierbare Datei.
- `README.md` im Projekt-Wurzelverzeichnis ergänzt — kurzer
  öffentlicher Überblick (Funktionen, Setup, bekannte Einschränkungen)
  für GitHub-Besucher, getrennt von `CLAUDE.md`/`docs/stand.md`, die
  für Claude-Sessions gedacht sind.

**Weitere Verbesserungsideen geprüft, aber (noch) nicht umgesetzt —
bewusst nur dokumentiert, um den Commit fokussiert zu halten:**
- PubChem-Caching (bestätigt: `chem.py` hat aktuell kein Retry/Cache,
  jede Anfrage geht neu raus) — sinnvoller nächster Schritt für
  gefühlte Geschwindigkeit.
- Ladungszustände des Liganden vor dem Docken (siehe bestehende
  Einschränkung weiter unten) — nicht trivial (pKa-Vorhersage), bleibt
  offen.
- SHAKE/RATTLE-Constraints bei der MD (siehe bestehende Einschränkung
  weiter unten) — würde den Integrator deutlich komplexer machen.
- Export/Screenshot-Funktion, Backend-Tests (`pytest` gegen
  `/api/resolve`, `/api/dock`), Deployment-Option — alles sinnvoll,
  aber jeweils eigene kleine Ausbaustufen, kein Ein-Zeiler.

**GitHub-Repo angelegt und gepusht:**
[github.com/nikiweikhart/molecule-viewer](https://github.com/nikiweikhart/molecule-viewer)
(öffentlich, auf Nikis Wunsch — Portfolio-tauglich für die VWA). `gh`
CLI war nicht installiert, deshalb Repo-Erstellung über den Chrome-
Browser (Nikis eingeloggte GitHub-Session) gemacht, Push lief über den
schon konfigurierten Git Credential Manager ohne weiteren Login-Schritt.
Branch heißt `main` (vorher `master`, umbenannt vor dem Push).

## 2026-09-15 (Abend): Ausbaustufe — Molekulardynamik-Simulation

Letzte der drei "richtig aufwendigen", API-freien Folge-Ausbaustufen
(nach chemischem Raum und Protein-Docking). Bauplan lag in
`C:\Users\nikiw\.claude\plans\ethereal-dancing-corbato.md`.

**Ergebnis: fertig und im Browser getestet.** Man gibt ein Molekül ein
(Name/Formel/SMILES, gleiches Format wie überall), klickt "Simulieren",
und sieht das Molekül — inklusive Wasserstoffe, bewusst nicht ausgeblendet
diesmal — kontinuierlich unter echter thermischer Bewegung wackeln
(Ping-Pong-Loop, kein Sprung beim Wiederholen).

**Bewusste Kursänderung gegenüber der ursprünglichen Idee "via OpenMM":**
OpenMM selbst hat saubere Windows-Wheels, aber um aus einem **beliebigen**
SMILES automatisch Kraftfeld-Parameter zu erzeugen, bräuchte es zusätzlich
`openmmforcefields` + `openff-toolkit`, und die hängen an `AmberTools` —
offiziell nur auf macOS/Linux getestet, nicht zuverlässig per pip unter
Windows installierbar. Gleiches Muster wie bei AutoDock Vina, nur diesmal
ohne die einfache "eine `.exe` laden"-Abkürzung, weil es ein verschachtelter
Python-Abhängigkeitsbaum ist. **Deshalb: kein OpenMM.** Stattdessen
RDKits MMFF94-Kraftfeld (schon seit dem allerersten Baustein im Einsatz,
`chem.py`) direkt für einen selbstgeschriebenen Velocity-Verlet-Integrator
genutzt — `ForceField.CalcGrad()` liefert echte Kraftfeld-Gradienten,
genug für eine echte numerische Lösung von Newtons Bewegungsgleichungen.
**Bringt exakt null neue Abhängigkeiten** (nur RDKit + numpy, beide schon
da) — diese Ausbaustufe ist damit sogar "kostenloser" als die anderen
beiden API-freien Stufen.

**Architektur (`backend/dynamics.py`, neue Datei):**
- Ligand über `chem._resolve_to_names()` auflösen, RDKit-Mol mit `AddHs`
  + `EmbedMolecule` + `MMFFOptimizeMolecule` aufbauen (gleiches Muster wie
  in `chem.py` und `docking.py`).
- `AllChem.MMFFGetMoleculeForceField` + `ff.Initialize()`, dann eine
  Velocity-Verlet-Schleife: `ff.CalcGrad(positions)` pro Schritt (explizite
  Positionsübergabe, kein Verlass auf implizite Mutation — per Diagnose-
  Skript bestätigt: Gradient an der schon MMFF-optimierten Startgeometrie
  ist praktisch null, API funktioniert wie erwartet).
- Start-Geschwindigkeiten aus einer Maxwell-Boltzmann-Verteilung bei
  300 K, Einheiten-System Å/Femtosekunden/amu/kcal-mol mit sauber aus
  SI-Einheiten hergeleiteter Umrechnungskonstante (`ACC_CONST = 4.184e-4`).

**Ein echtes Stabilitätsproblem unterwegs, ausführlich per Testskripten
diagnostiziert (nicht nur geraten):**
1. Erster Versuch (`dt=0.5 fs`, wie in Lehrbüchern für Standard-MD oft
   genannt) explodierte nach wenigen Dutzend Schritten zu `NaN`.
2. Kleinere Schrittweite allein hat das Problem nur verschoben, nicht
   gelöst: `dt=0.2 fs` blieb ~250 Schritte "sauber" (Energie driftet nur
   langsam), `dt=0.1 fs` ~450, `dt=0.05 fs` ~450-500 — dann explodierte
   jede der drei irgendwann trotzdem. Auch der reine Integrator **ohne**
   Thermostat driftete schon leicht (bestätigt per Diagnose ohne
   Thermostat) — die Lehrbuch-Schrittweiten (0.5-1 fs) setzen implizit
   Bindungslängen-Constraints (SHAKE/RATTLE) voraus, die die schnellen
   X-H-Streckschwingungen einfrieren; ohne die ist ein einfacher
   Integrator bei diesen Schrittweiten grundsätzlich nicht stabil.
3. **Was tatsächlich geholfen hat: Force-Capping** (`_ACCEL_CAP` in
   `dynamics.py`) — einzelne Beschleunigungs-Spitzen (entstehen, wenn zwei
   Atome sich in einem Integrationsschritt zu nah kommen und MMFFs steile
   Terme dann eine riesige Kraft liefern) werden der Richtung nach
   erhalten, aber der Höhe nach gekappt. Damit über 2000 Testschritte
   stabil (keine `NaN` mehr), auch bei Caffein (24 Atome, mehrere Ringe)
   gegengeprüft. Pendelt sich dabei auf ein etwas höheres Energieniveau
   ein als das nominelle 300-K-Ziel (~15-16 statt ~8 kcal/mol bei Ethanol)
   — für eine visuelle Demo (sichtbares, stabiles Wackeln) ausreichend,
   aber **keine quantitativ exakte NVT-Simulation**. Offen benannt im
   Modul-Docstring von `dynamics.py`, gleiche "ehrliche Vereinfachung"-
   Linie wie bei der Formel-Heuristik in `chem.py` oder den Docking-
   Bindungsenergien.
- Finale Werte: `dt=0.1 fs`, `n_steps=800` (80 fs simuliert),
  Geschwindigkeits-Rescaling-Thermostat jeden Schritt (sanft geklemmt,
  0.97-1.03), Frames alle 3 Schritte aufgezeichnet (~268 Frames).
  Rechenzeit pro Anfrage: ~1 Sekunde für ein ~20-30-Atom-Molekül.

**Frontend:**
- `frontend/viewer.js`: neue Methode `playTrajectory(data)` — baut Kugeln
  + Zylinder einmalig aus Frame 0 (gleiches Baumuster wie `playReaction`),
  spielt die Frame-Liste per `requestAnimationFrame` in einer
  **Ping-Pong-Schleife** ab (vorwärts bis zum letzten Frame, dann
  rückwärts, dann wieder vorwärts) statt hart zu Frame 0 zurückzuspringen
  — keine sichtbare Ruckel-Stelle beim Loopen. Kamera wird einmalig auf
  Frame 0 (+ Puffer) gefittet, da thermische Bewegung nur eine kleine
  Auslenkung um die Ausgangslage ist. Wasserstoffe werden diesmal bewusst
  **gezeigt** (Gegensatz zur Reaktions-Animation) — die schnelle
  X-H-Wackelbewegung ist genau das, was "vibriert wirklich" visuell zeigt.
  Neuer `clearTrajectory()`-Aufräummechanismus, ins bestehende
  `clearReaction()`/`clearDocking()`-Muster eingehängt.
- `frontend/index.html` + `app.js`: neuer Bereich "Molekulardynamik" —
  Eingabefeld, "Beispiel laden" (füllt `caffeine`), "Simulieren"-Button,
  Info-Zeile (Temperatur, simulierte Zeit, Atomzahl). Keine neuen
  CSS-Klassen nötig — bestehende `.docking-controls`/`.chemspace-info`
  wiederverwendet.

**Getestet im Browser:** Caffein simuliert — sichtbare, kontinuierliche
Wackelbewegung (Positionsvergleich zwischen zwei Screenshots im
Sekundenabstand bestätigt echte Bewegung), Molekül bleibt auch nach
mehreren Sekunden Dauerlauf kompakt und erkennbar (keine Explosion, keine
sichtbaren Sprünge). Keine Konsolenfehler. Regressionscheck der normalen
Molekülanzeige (`water`) danach — lief einwandfrei, der Eingriff in die
gemeinsame Aufräum-Logik (`clearTrajectory()` in `rebuild()`/
`playReaction()`/`setDockingResult()`) hat nichts kaputt gemacht.

**Damit sind alle 3 der "richtig aufwendigen", API-freien Folge-
Ausbaustufen fertig: Chemischer Raum ✅, Protein-Docking ✅,
Molekulardynamik ✅.** Alle drei bringen zusammen genau eine neue externe
Binary (`vina.exe`) und eine Handvoll pip-Pakete (`meeko`, `scipy`,
`gemmi`) mit — die Molekulardynamik-Stufe selbst kam am Ende ganz ohne
neue Abhängigkeit aus.

## 2026-09-15 (autonomer Durchlauf, ~1 Std.): Ausbaustufe — Protein-Docking

Niki wollte Tennis spielen gehen und hat gesagt: alles bauen, was schon
besprochen war (Protein-Docking), bei Fragen selbst entscheiden statt zu
warten, und gern noch selbst draufgepackte Ideen einbauen. Bauplan lag in
`C:\Users\nikiw\.claude\plans\ethereal-dancing-corbato.md` (Protein-Docking-
Version — der chemische Raum davor hat den gleichen Dateinamen benutzt,
Plan-Dateien werden pro Session wiederverwendet, nicht pro Ausbaustufe).

**Ergebnis: fertig und im Browser getestet, funktioniert end-to-end.**
Man gibt eine PDB-ID (z. B. `3PTB`) und einen Liganden (Name/Formel/SMILES,
z. B. `benzamidine`) ein, klickt "Docken", und sieht nach ein paar Sekunden
das Protein-Rückgrat als Röhre mit dem angedockten Molekül in der
Bindetasche, dazu Proteinname und die drei besten Bindungsenergien.

**Neue externe Werkzeuge (einmalig, mit Nikis vorherigem Okay
heruntergeladen bzw. installiert):**
- `backend/tools/vina.exe` — offizielle AutoDock-Vina-1.2.7-Windows-Binary
  von `github.com/ccsb-scripps/AutoDock-Vina/releases` (1.233.920 Bytes,
  Prüfsumme beim Download bestätigt). Grund: die Python-Bindings von Vina
  haben kein funktionierendes Windows-Paket (`pip install vina` schlägt
  auf Windows an fehlenden Build-Abhängigkeiten wie Boost fehl — bekanntes,
  offenes Problem, siehe
  [GitHub-Issue #305](https://github.com/ccsb-scripps/AutoDock-Vina/issues/305)).
  Die `.exe` ist eigenständig, kein Installer, keine Systemänderung.
- `meeko` (0.8.0), `scipy`, `gemmi` in der venv installiert — `meeko`
  bereitet sowohl Rezeptor (Protein) als auch Liganden für Vina vor
  (`mk_prepare_receptor.exe`, `mk_prepare_ligand.exe`, `mk_export.exe`,
  alle als Kommandozeilen-Skripte in `.venv/Scripts/` installiert). `scipy`
  und `gemmi` waren nicht in `meekos` PyPI-Metadaten als Abhängigkeiten
  gelistet, wurden aber beim ersten Ausführen als fehlend gemeldet und
  nachinstalliert — beim Neuaufsetzen der venv einfach mit einplanen.

**Architektur (`backend/docking.py`, neue Datei):**
1. `fetch_pdb()` lädt die Struktur von `files.rcsb.org` (frei, kein Key,
   wie PubChem) und cached sie unter `backend/pdb_cache/{ID}.pdb`, plus den
   Proteinnamen von `data.rcsb.org`s REST-API.
2. `_find_reference_ligand()` durchsucht die `HETATM`-Zeilen der PDB-Datei,
   filtert eine Denyliste aus Wasser/Ionen/Kristallisationshilfsstoffen
   (`HOH`, `SO4`, `GOL`, `NAG`, …), nimmt die größte verbleibende Gruppe
   als Referenz-Ligand und berechnet deren Bounding-Box (+5 Å Puffer,
   mindestens 15 Å pro Achse) als Such-Box für Vina. **Kein blindes
   Docking** — PDB-Einträge ohne brauchbaren Liganden (reine Apo-
   Strukturen, z. B. `1UBQ` getestet) geben eine klare Fehlermeldung statt
   eines langsamen, ungenauen Rateversuchs über die ganze Oberfläche.
3. `prepare_receptor()` ruft `mk_prepare_receptor.exe --read_pdb …
   --delete_bad_res` auf — das `-x/--delete_bad_res`-Flag entfernt
   automatisch jeden Rest ohne bekanntes Chemie-Template (den
   Referenz-Liganden selbst, Kristallwasser, exotische Kofaktoren), ohne
   dass man Resten einzeln von Hand angeben muss.
4. Der Ligand wird über das schon vorhandene `chem._resolve_to_names()`
   aufgelöst, lokal mit RDKit 3D eingebettet (gleiches Muster wie in
   `chem.py`), als SDF geschrieben und über `mk_prepare_ligand.exe` zu
   PDBQT vorbereitet.
5. `run_vina()` ruft `vina.exe` mit Rezeptor/Ligand/Box auf, liest die
   Bindungsenergien direkt aus Vinas eigener Konsolenausgabe (per Regex).
6. `mk_export.exe` konvertiert Vinas Ausgabe-PDBQT zurück zu SDF (mit
   sauber rekonstruierten Bindungen statt sie selbst aus Distanzen zu
   raten), RDKit liest daraus die beste Pose als Atome/Bindungen im
   gleichen Format wie überall sonst in der App.
7. Alle Schritte werfen eine sprechende `DockingError` bei Fehlschlag —
   gleiches Muster wie `ResolveError`.

**Frontend:**
- `frontend/viewer.js`: neue Methode `setDockingResult(data)` auf dem
  `createViewer()`-Objekt. Protein-Rückgrat als glatte Röhre
  (`THREE.CatmullRomCurve3` + `TubeGeometry` durch die Cα-Positionen pro
  Kette, gedämpfter Warmton `#7a6a52`, matt statt glänzend, damit es den
  Liganden nicht optisch erschlägt). Ligand ganz normal per
  `buildMolecule()` (Wiederverwendung, keine neue Kugel-Stab-Logik nötig).
  **Zusatz, spontan noch ergänzt:** eine halbtransparente
  Drahtgitter-Box (`THREE.BoxGeometry` + `EdgesGeometry`) um die
  Such-Box herum — macht sichtbar, wo Vina eigentlich gesucht hat, statt
  dass die Bindetasche nur implizit aus der Ligand-Position erschlossen
  werden muss.
- `frontend/index.html` + `app.js` + `style.css`: neuer Bereich —
  PDB-ID-Feld, Liganden-Feld, "Beispiel laden" (füllt `3PTB` +
  `benzamidine`), "Docken"-Button mit "wird berechnet …"-Anzeige während
  der Anfrage (Rezeptor-Vorbereitung + Docking-Suche dauert ein paar
  Sekunden bis niedrige Minuten, je nach PDB-Größe).

**Getestet im Browser:**
- `3PTB` + `benzamidine` (das vereinbarte Lehrbeispiel — Trypsin,
  1 Kette/223 Reste, Referenz-Ligand korrekt als `BEN` erkannt): Protein-
  Röhre + Ligand + Such-Box sichtbar, Ligand liegt beim Drehen erkennbar
  *zwischen* den Schleifen (nicht nur davor) — also wirklich in der
  Tasche. Bindungsenergien um die −4 kcal/mol.
- Fehlerfall 1: ungültige PDB-ID (`ZZZZ`) → klare Meldung "wurde bei RCSB
  nicht gefunden" statt Absturz.
- Fehlerfall 2: PDB-ID ohne brauchbaren Liganden (`1UBQ`, Ubiquitin, reine
  Apo-Struktur) → klare Meldung statt stillem Blind-Docking-Versuch.
- Keine Konsolenfehler bei keinem der drei Fälle.

**Bekannte Einschränkung, offen benannt (wie bei der Formel-Heuristik in
`chem.py`):** Die Bindungsenergie für Trypsin+Benzamidin liegt bei den
Testläufen bei etwa −4 kcal/mol; Literaturwerte für diese sehr bekannte,
gut untersuchte Bindung deuten (über ΔG=−RT·ln(Ka) aus dem bekannten
Ki im niedrigen µM-Bereich) eher auf ungefähr −6 bis −7 kcal/mol hin. Vina
selbst ist ohnehin nur eine Scoring-Funktions-Näherung, keine exakte
Berechnung — zusätzlich benutzt diese Ausbaustufe die **neutrale**
Benzamidin-Form aus der PubChem/RDKit-SMILES-Auflösung, während die reale
Bindung über die protonierte Amidinium-Form (positiv geladen) läuft, die
eine Salzbrücke mit Asp189 im Protein eingeht — das fehlt hier und drückt
den berechneten Wert nach oben (schwächer). Richtige Ladungszustände vor
dem Docken zu bestimmen ist ein eigenes, nicht triviales Teilproblem
(pKa-Vorhersage) und bewusst nicht Teil dieser Ausbaustufe. Die Werte sind
also eher "richtige Größenordnung, richtiges Vorzeichen, richtige
Bindestelle" als exakt — für eine Lern-/Demo-Ausbaustufe die richtige
Erwartungshaltung, genau wie beim Kugel-Stab- statt Sekundärstruktur-
Protein-Rückgrat.

**Nebenbei aufgetreten:** Nach einer Backend-Änderung zeigte
`--reload` das erwartete "Reloading..."-Log, aber die geänderte Funktion
lieferte trotzdem noch die alte Antwort — half nur ein harter Neustart
(`taskkill` + `__pycache__` löschen + neu starten). Vermutlich eine
Eigenheit des Datei-Watchers auf dem OneDrive-synchronisierten
Projektordner (Sync-Verzögerung beim Melden der geänderten mtime). Falls
das nochmal passiert: nicht auf `--reload` verlassen, hart neu starten.

**Stand der 3 API-freien Folge-Ausbaustufen:** Chemischer Raum ✅, Protein-
Docking ✅ (dieser Eintrag), Molekulardynamik (OpenMM) offen — der letzte
der drei ursprünglich besprochenen "richtig aufwendigen" nächsten Schritte.

## 2026-09-15 (später): Ausbaustufe — Chemischer Raum / Ähnlichkeits-Explorer

Nach den 6 ursprünglich vereinbarten Ausbaustufen wollte Niki eine der drei
"richtig aufwendigen" Folge-Ideen bauen, die komplett ohne bezahlte API
laufen (siehe Gedächtnis `project_molecule_viewer.md` für die anderen
zwei — Protein-Docking und Molekulardynamik, noch offen). Gewählt: viele
Moleküle auf einmal eingeben, nach struktureller Ähnlichkeit auf einer 2D-
Karte anordnen und gruppieren. Bauplan lag in
`C:\Users\nikiw\.claude\plans\ethereal-dancing-corbato.md`.

**Keine neue Abhängigkeit installiert** — `numpy` war schon als RDKit-
Abhängigkeit in der venv vorhanden, PCA und k-Means sind selbst mit numpy
geschrieben statt `scikit-learn` zu installieren (bei den kleinen
Molekül-Mengen, um die es hier geht, robuster als t-SNE/UMAP und hält die
venv schlank).

**Backend:**
- `backend/chem.py` — kleiner, nicht brechender Refactor: `_compute_facts(mol)`
  aus `_build_structure()` herausgezogen (reine Funktionstrennung, mit
  `python chem.py` gegen den alten Output geprüft — identisch). Existiert
  jetzt separat, weil der chemische Raum nur die schnellen Fakten braucht,
  kein 3D-Embedding pro Molekül (das wäre bei Dutzenden Molekülen zu
  langsam).
- Neue Datei `backend/chemspace.py`: `build_chemical_space(queries)` löst
  jede Zeile über `chem._resolve_to_names()` auf (gleiche Logik wie die
  Haupt-Suche), berechnet pro Molekül einen Morgan-Fingerprint
  (`rdFingerprintGenerator.GetMorganGenerator`, radius=2, 1024 Bit),
  reduziert die Fingerprint-Matrix per selbstgeschriebener PCA
  (Zentrieren + `np.linalg.svd`) auf 2D, und gruppiert die 2D-Punkte per
  selbstgeschriebenem k-Means (deterministisch initialisiert — Punkte nach
  1. Hauptkomponente sortiert, k gleichmäßig verteilte Startzentren, keine
  Zufallszahlen). `k` heuristisch aus der Molekülzahl:
  `min(6, max(2, n // 3))`, bei <4 Molekülen nur 1 Cluster. Fehlschläge
  (nicht auflösbare Zeilen) werden gesammelt statt den ganzen Request
  abzubrechen. Eigener `if __name__ == "__main__":`-Testblock mit einem
  18-Molekül-Beispiel-Set — Cluster-Verteilung per `python chemspace.py`
  geprüft: Steroide (Cholesterol/Testosteron) und Zucker
  (Glucose/Fructose/Sucrose) bilden erwartungsgemäß saubere eigene
  Cluster; ein paar Aminosäuren landeten überraschend im
  Schmerzmittel-Cluster (Fingerprints gruppieren nach Struktur, nicht nach
  Pharmakologie — z. B. wegen des aromatischen Rings bei Phenylalanin —
  chemisch nachvollziehbar, keine Fehlfunktion).
- `backend/app.py`: neue Route `POST /api/chemical-space`.

**Frontend:**
- `frontend/index.html`: neuer Bereich unter der Reaktions-Animation —
  Textarea (ein Molekül pro Zeile), "Beispiel-Set laden"- und "Karte
  erzeugen"-Button, `<canvas>` in einem wiederverwendeten `.viewer-frame`,
  Info-Zeile für Hover/Auswahl.
- Neue Datei `frontend/chemspace.js`: `createChemSpacePlot(canvas)`, ein
  selbstgebautes Canvas-2D-Scatterplot (keine Chart-Bibliothek von einem
  CDN — passt zur bestehenden "kein Build-Schritt, minimale
  Abhängigkeiten"-Linie). Normalisiert PCA-Koordinaten auf Canvas-Pixel,
  zeichnet Punkte farbig nach Cluster (Farbpalette bewusst aus den
  Element-Farben in `viewer.js` übernommen statt neu erfunden), Hover
  vergrößert den nächstgelegenen Punkt und feuert einen Callback, Klick
  ebenso.
- `frontend/app.js`: hartkodiertes 18-Molekül-Beispiel-Set (5 Klassen:
  Schmerzmittel, Zucker, Alkohole, Aminosäuren, Steroide), Fetch-Aufruf an
  `/api/chemical-space`, Hover zeigt Name+Fakten im Info-Feld. **Klick auf
  einen Punkt lädt die 3D-Struktur direkt in den bestehenden
  Haupt-Viewer** — ruft dafür die schon vorhandene `loadIntoSlot(0, …)`
  mit dem vom Backend gelieferten SMILES auf (keine zweite, separate
  3D-Anzeige gebaut) und scrollt sanft nach oben.

**Getestet im Browser:** Beispiel-Set geladen, Karte erzeugt — 5 farblich
klar getrennte Gruppen sichtbar (Screenshot geprüft). Hover auf einen
Punkt vergrößert ihn und zeigt Name/Formel/Molmasse/LogP im Info-Feld.
Klick auf Cholesterol hat die 3D-Struktur oben im Haupt-Viewer geladen und
dorthin gescrollt — funktioniert einwandfrei. Fehlerfall geprüft: nur 1
Zeile im Textfeld → klare Fehlermeldung "Mindestens 2 Moleküle nötig …"
statt Absturz. Keine Konsolenfehler.

**Kleine, beiläufig aufgefallene Beobachtung (kein Bug, nur Notiz):** Wenn
man einen Punkt anklickt, kann der angezeigte Name leicht vom Namen in der
Chemischer-Raum-Liste abweichen (z. B. "Cholesterol" in der Eingabe →
"Cholest-5-en-3-ol" im Haupt-Viewer). Grund: der Klick lädt über den
SMILES-Code nach (`_pubchem_lookup_by_smiles`), und PubChems "Title"-Feld
ist für die SMILES-Rückwärtssuche manchmal ein anderes registriertes
Synonym als bei der Namens-Suche — chemisch identische Struktur, nur eine
andere von mehreren gültigen Bezeichnungen. Kein Fehlverhalten, nur eine
PubChem-Eigenheit.

**Nebenbei aufgetreten — der bekannte Server-Fallstrick war wieder da:**
Der alte Uvicorn-Prozess von der letzten Sitzung hing noch auf Port 8001
(`netstat` zeigte zwei "ABHÖREN"-Einträge gleichzeitig), dadurch gingen
manche Requests an die alte Prozess-Instanz ohne die neue Route (405
Method Not Allowed, obwohl die Route im Code längst da war). Gelöst mit
`taskkill /F /PID <pid> /T` auf die alte PID statt nur `pkill` — `pkill -f
"uvicorn app:app"` allein reicht offenbar nicht zuverlässig, um den
Reloader-Elternprozess mitsamt Kindprozess zu beenden.

## 2026-09-15: Ausbaustufe 6 fertiggebaut — Reaktions-Animation läuft

Frontend-Teil ergänzt (Backend stand schon vom Vortag):
- `frontend/index.html` — neuer Bereich unter den Karten: `<select
  id="reaction-select">` (per JS aus `/api/reactions` befüllt), Button
  "▶ Ablaufen lassen", eigener `.viewer-frame`-Block (`#reaction-viewer`).
- `frontend/viewer.js` — `createViewer()` gibt jetzt zusätzlich
  `playReaction(data, durationMs=3000)` zurück. Baut eine Kugel pro
  Start-Atom plus Zylinder für `persistent_bonds`/`broken_bonds`/
  `formed_bonds`, interpoliert Positionen über `correspondence` mit
  Ease-in-out (`requestAnimationFrame`-Loop, 3s), blendet `broken_bonds` in
  der ersten Hälfte aus und `formed_bonds` in der zweiten Hälfte ein.
  Kamera wird einmalig auf die Vereinigung aus Start- und End-Positionen
  gefittet (kein Nachjustieren während der Animation nötig). Die
  Kamera-Fit-Logik wurde dafür aus `fitCameraToObject` in ein wiederverwend-
  bares `frameBox(box)` extrahiert.
- `frontend/app.js` — Dropdown wird beim Laden aus `/api/reactions` befüllt,
  Button-Handler holt `/api/reactions/{id}` und ruft `playReaction` auf
  einem eigenen, dauerhaften Viewer auf (kein Card-Template nötig, da es nur
  eine Reaktions-Ansicht gibt, kein Vergleichsmodus dafür).
- `frontend/style.css` — `.section-label` (dünne Trennlinie mit Mono-Label)
  und `.reaction-row` (Select + Button nebeneinander, gleicher Stil wie die
  restlichen Eingabefelder) ergänzt.

**Getestet im Browser (Screenshots bei t≈0, t≈Übergang, t≈Ende):**
Start zeigt Essigsäure und Ethanol räumlich getrennt, in der Mitte ist die
C-OH-Bindung der Säure sichtbar am Ausblassen während sich die Atome schon
in Richtung Endposition bewegen, am Ende steht eine durchgehend verbundene
Ester-Kette (5 Schweratome) neben einem einzelnen, klar abgetrennten
Wasser-Sauerstoffatom — chemisch korrekt und mit sichtbarer Bewegung.
Keine Konsolenfehler während der Animation. Danach zur Sicherheit noch
"aspirin" aufgelöst, um zu prüfen, dass der Umbau von `fitCameraToObject`
(jetzt intern über das neue gemeinsame `frameBox()`) die normale
Molekül-Anzeige nicht kaputt gemacht hat — lief einwandfrei.

**Damit sind alle 6 ursprünglich vereinbarten Ausbaustufen erledigt**, bis
auf die eine seit Tag 1 offene Lücke: Ausbaustufe 5 (KI-Erklärtext) wartet
weiter auf einen `ANTHROPIC_API_KEY` von Niki (siehe unten, unverändert).

**Rezept, um eine weitere Reaktion zu ergänzen:** In `backend/reactions.py`
einen neuen Eintrag an `REACTIONS` anhängen mit `id`, `label` und
atom-gemappten `reactants_smiles`/`products_smiles` (SMILES mit `[C:1]`-
artigen Map-Nummern; jede Nummer, die auf beiden Seiten vorkommt, markiert
ein Atom, das erhalten bleibt und morpht). Kein Frontend- oder
Framework-Code nötig — das Dropdown befüllt sich automatisch aus
`/api/reactions`.

## 2026-09-14 (Nacht): Ausbaustufe 6 angefangen — Backend fertig, Frontend fehlt noch

Niki hat mitten in der Umsetzung gesagt, an der nächstbesten Stelle
anzuhalten und für heute zu speichern. Sauberer Zwischenstand:

**Fertig und einzeln getestet (`python reactions.py`, dann per Server-Neustart
und `curl` bestätigt):**
- `backend/reactions.py` — neue Datei. Enthält die erste Beispiel-Reaktion
  (Veresterung: Essigsäure + Ethanol → Ethylacetat + Wasser) als
  atom-gemappte SMILES, plus `build_reaction()`, die daraus Start-/End-3D-
  Struktur, Atom-Korrespondenz und die drei Bindungs-Listen
  (`persistent_bonds`, `broken_bonds`, `formed_bonds`) berechnet. Testlauf
  bestätigt: 7 Atome auf beiden Seiten, vollständige 1:1-Zuordnung, genau 1
  gebrochene Bindung (C-OH der Säure) und genau 1 neu gebildete (die
  Ester-C-O-C-Bindung) — chemisch korrekt.
- `backend/app.py` — zwei neue Routen ergänzt und funktionsfähig:
  `GET /api/reactions` (Liste fürs Auswahlmenü) und
  `GET /api/reactions/{id}` (die vollen Animationsdaten). Per `curl`
  bestätigt: beide liefern 200 OK mit den erwarteten Daten.

**Noch nicht angefasst — das ist der Rest von Ausbaustufe 6:**
- `frontend/index.html`: Auswahl-Menü (`<select>`) + "Ablaufen lassen"-Button
  + eigener Viewer-Bereich für die Reaktion fehlen noch im Markup.
- `frontend/viewer.js`: die eigentliche Animationslogik (`playReaction`)
  fehlt komplett — Kugeln pro Atom bauen, Positionen jeden Frame zwischen
  Start- und End-Koordinaten interpolieren (über `correspondence`), Bindungen
  ein-/ausblenden (`broken_bonds` verblassen in der ersten Hälfte,
  `formed_bonds` erscheinen in der zweiten Hälfte, `persistent_bonds` bleiben
  durchgehend sichtbar).
- `frontend/app.js`: Dropdown aus `/api/reactions` befüllen, Button-Handler,
  der `/api/reactions/{id}` holt und `playReaction` anstößt.
- Noch keinerlei Browser-Test der Animation selbst (nur die Backend-Daten
  sind geprüft, nicht das Rendering/die Bewegung).

Der volle Bauplan mit allen Details (genaue Interpolations-/Opazitäts-Logik,
Elementfarben-Wiederverwendung usw.) steht unverändert in
`C:\Users\nikiw\.claude\plans\swirling-knitting-wadler.md` — beim
Weitermachen zuerst dort nachlesen, dann direkt bei Schritt 3
("Umsetzungsschritte") weitermachen.

Server wurde für heute sauber gestoppt (lief auf Port 8001).

## 2026-09-14 (Abend, autonomer Durchlauf): Ausbaustufen 2, 4, 5 gebaut

Niki war für ~30-40 Min. weg vom PC und hat gesagt: alles Übrige bauen, nicht
fragen, bei echten Blockern eine Lücke lassen statt zu warten. Ergebnis:

**Ausbaustufe 2 — Darstellungs-Layer erledigt.** Drei Modi über Buttons
oberhalb des Viewers: Kugel-Stab (Standard), Raumfüllend (van-der-Waals-
Radien, keine Bindungen sichtbar — der "Blob"-Look), Ladung (Kugeln nach
Gasteiger-Partialladung eingefärbt, Rot=negativ/Blau=positiv/Creme=neutral).
`backend/chem.py` berechnet die Partialladungen jetzt zusätzlich pro Atom
(`AllChem.ComputeGasteigerCharges`). Die gesamte Three.js-Logik wurde dafür
aus `app.js` in ein eigenes Modul `frontend/viewer.js` ausgelagert
(`createViewer(container)` als Fabrik-Funktion) — nötig, damit auch der
Vergleichsmodus mehrere unabhängige Viewer-Instanzen bekommen kann.

**Ausbaustufe 4 — Vergleichsmodus erledigt.** "+ Vergleichen"-Button öffnet
ein zweites Eingabefeld; beim Auflösen erscheinen zwei Karten (Viewer +
Fakten + Erklärung) nebeneinander in einem Grid (`#cards.cards-compare`),
beide mit dem gleichen Darstellungsmodus. Karten werden aus einem
HTML-`<template>` geklont, nicht mehr fest im Markup.

**Ausbaustufe 5 — KI-Erklärtext eingebaut, aber mit einer bewussten Lücke:**
`backend/explain.py` schickt Name+Formel an Claude (`claude-haiku-4-5-20251001`
— bewusst das kleine/günstige Modell, weil die Aufgabe eng und einfach ist,
siehe Gedächtnis-Eintrag zur Modell-Wahl) und lässt sich die Erklärung in
2-3 einfachen Sätzen geben. **Braucht einen `ANTHROPIC_API_KEY`, den ich
nicht habe und nicht raten sollte** — Niki muss dafür `backend/.env.example`
nach `backend/.env` kopieren und seinen eigenen Key eintragen. Ohne Key
zeigt das Erklärungs-Feld einen klaren "noch nicht verfügbar"-Hinweis statt
abzustürzen — Rest der App funktioniert komplett unabhängig davon. **Das ist
die Lücke, die noch auf Niki wartet.**

**Nebenbei aufgetreten — ein hartnäckiger Server-Fallstrick:** Port 8000
hing an einem alten Uvicorn-Prozess fest, der sich weder per `taskkill`
noch per Neustart mit `--reload` abschütteln ließ (`netstat` zeigte ihn
weiter als "ABHÖREN", obwohl `tasklist` keinen solchen Prozess mehr kannte —
vermutlich ein Anzeige-/Cache-Problem des Sandbox-Netzwerkstacks, nicht ein
echtes Zombie-Problem). Lösung: Server läuft jetzt auf **Port 8001** statt
8000. Falls Niki Port 8000 wieder freibekommen will: Rechner neu starten
sollte reichen, oder im Task-Manager nach einem alten `python.exe`/
`uvicorn`-Prozess suchen.

## 2026-09-14 (Abend): Redesign auf Three.js + Fakten-Panel (Ausbaustufe 3 erledigt)

Niki gefiel die Cyan-Scanline-HUD-Optik nicht — er fand als Referenz
**arrakis.tech** (warmes Schwarz, dünne Haarlinien, Bernstein-Akzentfarbe,
Statistik-Kacheln, sanftes Glühen). Außerdem wollte er einen echten
"Blender-Look" für das Molekül selbst — das konnte 3Dmol.js technisch nicht
(nur flache Cartoon-Materialien).

**Größte Änderung: Wechsel der 3D-Engine von 3Dmol.js auf Three.js.**
Läuft als ES-Modul über eine Importmap (`index.html`) von jsdelivr, kein
Bundler nötig. Damit gibt es jetzt echte glänzende Materialien
(`MeshPhysicalMaterial` mit Clearcoat), eine Umgebungsreflexion
(`RoomEnvironment` + `PMREMGenerator`), weiches Studio-Licht (Haupt-/Füll-/
Ambient-Licht) und einen echten weichen Kontaktschatten unter dem Molekül
(`ShadowMaterial` auf einer unsichtbaren Boden-Ebene). Maus-Drehen/Zoomen
läuft jetzt über `OrbitControls` statt 3Dmol.js' eigener Steuerung.

**Datenformat geändert:** Das Backend gibt keinen Molblock-Text mehr aus,
sondern fertiges JSON (`atoms: [{element,x,y,z}]`, `bonds: [{a,b}]`) —
`chem.py`s `_build_structure()` baut das direkt aus dem RDKit-Mol-Objekt
(ersetzt `_smiles_to_3d_molblock`). `app.js` baut daraus selbst die
Kugeln/Zylinder in der Three.js-Szene.

**Fakten-Panel (Ausbaustufe 3) eingebaut:** Summenformel, molare Masse,
LogP, TPSA, H-Brücken-Donoren/-Akzeptoren, drehbare Bindungen — als
Statistik-Kacheln unter dem Viewer, im arrakis-artigen Kachel-Stil. Wichtig:
diese Werte werden **lokal mit RDKit berechnet** (`Descriptors`/
`rdMolDescriptors`), nicht bei PubChem abgefragt — spart einen
Netzwerk-Aufruf und funktioniert auch für Strukturen, die PubChem nicht
kennt. RDKits LogP-Berechnung ist nicht identisch mit PubChems
XLogP-Algorithmus, deshalb Panel-Label "LogP (berechnet)".

**Neue Design-Tokens** (`style.css`): warmes Nahe-Schwarz (`#0c0a08`),
cremefarbener Text, gedämpfte Bernstein-Akzentfarbe (`#e0965a`), dünne
1px-Rahmen statt Neon-Glow, kleine Eckstriche als dezentes Detail, Google
Fonts "Inter" (Fließtext) + "JetBrains Mono" (kleine Großbuchstaben-Labels).

**Getestet:** "aspirin" und "water" per Browser-Tool durchgeklickt — Kugeln
glänzen sichtbar (echtes Glanzlicht + weicher Schatten), Fakten-Kacheln
zeigen plausible Werte, Drehen per Maus-Drag funktioniert.

**Kleiner Fallstrick beim Testen:** Nach Code-Änderungen an `chem.py`/
`app.py` muss der Uvicorn-Server neu gestartet werden (jetzt mit
`--reload`-Flag gestartet, damit das künftig automatisch passiert) — sonst
liefert er weiter die alte Antwortstruktur, während das Frontend schon auf
das neue Format wartet (genau das ist beim ersten Testlauf heute passiert).

## 2026-09-14 (Nachmittag): Beide Namen anzeigen — 2 Fallstricke behoben

Niki wollte, dass Fallstrick 1 und 3 von unten (generischer statt
gebräuchlicher Name; SMILES statt hübschem Namen) besser gelöst werden, indem
**beide Namen gleichzeitig** angezeigt werden: der gebräuchliche Name groß,
der IUPAC-Fachname klein darunter ("Fachname: ...").

Lösung: PubChem hat neben `IUPACName` auch ein Feld `Title` — das ist genau
der gebräuchliche/umgangssprachliche Name (z. B. "Aspirin", "D-Glucose",
"Ethanol"), getrennt vom systematischen `IUPACName`. Beide werden jetzt bei
jeder Anfrage mitgeholt (`ConnectivitySMILES,Title,IUPACName` in einem
Property-Aufruf statt vorher nur SMILES + Synonyme).

Für den direkten-SMILES-Fall (Fallstrick 3) gibt's jetzt zusätzlich eine
Rückwärtssuche: die eingegebene SMILES wird per POST an
`/compound/smiles/property/...` geschickt, um Title + IUPACName aus PubChem
zu holen (POST statt GET, weil SMILES Sonderzeichen wie `()=` enthalten kann,
die in einer URL Probleme machen würden). Kennt PubChem die Struktur nicht,
fällt es sauber zurück auf die reine SMILES-Anzeige — kein Absturz.

`chem.py`s `ResolvedMolecule` hat jetzt `common_name` und `iupac_name` statt
nur `resolved_name`. Frontend blendet die Fachname-Zeile aus, wenn sie
(fast) identisch mit dem gebräuchlichen Namen wäre (z. B. bei Ethanol/ethanol).

Fallstrick 1 (Formel-Heuristik wählt manchmal einen Oberbegriff wie "Hexose"
statt "Glukose") besteht weiterhin — das war nicht Teil dieser Änderung und
bleibt unten als offener Punkt stehen.

## 2026-09-14: Kern gebaut und getestet

Erster Baustein steht: man tippt einen Molekülnamen, eine Summenformel oder
einen SMILES-Code ins Eingabefeld, und bekommt ein rotierbares 3D-Modell im
Browser, im dunklen "Iron-Man-HUD"-Look.

**Architektur:**
- `backend/chem.py` — die eigentliche Logik. Versucht die Eingabe in dieser
  Reihenfolge zu lesen: 1) direkt als SMILES (RDKit lokal), 2) als Name bei
  PubChem, 3) als Summenformel bei PubChem (Mehrdeutigkeits-Fall — wenn
  mehrere Stoffe zur Formel passen, wird automatisch die niedrigste PubChem-
  CID gewählt und im Antworttext offen gesagt, welcher Stoff gewählt wurde
  und warum). Danach wird immer lokal mit RDKit eine 3D-Struktur berechnet
  (`EmbedMolecule` + `MMFFOptimizeMolecule`) und als Molblock zurückgegeben.
- `backend/app.py` — dünner FastAPI-Wrapper: `/api/resolve` (POST) ruft
  `chem.resolve()` auf, liefert `{molblock, common_name, iupac_name, note}`
  als JSON (Stand nach der Namens-Erweiterung vom Nachmittag, siehe oben).
  Dient außerdem den `frontend/`-Ordner statisch unter `/` (kein CORS-Ärger,
  kein zweiter Server).
- `frontend/` — ein Eingabefeld, ein 3Dmol.js-Viewport, ein Hinweistext-
  Bereich für die Mehrdeutigkeits-Notiz. Reines HTML/CSS/JS, kein Build.

**Getestet (alle vier Fälle laufen, per Browser-Tool durchgeklickt):**
"aspirin" (Name), "C6H12O6" (Mehrdeutige Formel), "CCO" (direktes SMILES),
"water" (Name). Rotation per Maus-Drag funktioniert (3Dmol.js-eigene Steuerung).

**Bekannte Fallstricke:**
1. Die "niedrigste-CID"-Heuristik für die Formel-Mehrdeutigkeit ist eine
   einfache Näherung, kein echtes "Popularitäts-Ranking". Bei C6H12O6 hat sie
   z. B. "Hexopyranose" gewählt (ein allgemeiner Zucker-Oberbegriff), nicht
   konkret "D-Glukose". Der Hinweistext ist trotzdem korrekt und ehrlich —
   nur die Wahl selbst ist manchmal nicht die intuitivste. Mögliche
   Verbesserung später: nach Literatur-/Annotation-Anzahl bei PubChem filtern
   statt nach roher CID, oder Kandidaten mit definierter Stereochemie
   bevorzugen.
2. PubChems Property-Feld heißt aktuell `ConnectivitySMILES`, nicht
   `CanonicalSMILES` (API hat sich offenbar geändert) — falls PubChem das
   nochmal umbenennt, ist das die erste Stelle zum Nachschauen
   (`backend/chem.py`, Funktionen `_pubchem_lookup_by_name` /
   `_pubchem_lookup_by_formula`).
3. ~~Bei direkter SMILES-Eingabe wird als Anzeigename einfach der SMILES-Code
   selbst zurückgegeben~~ — behoben am Nachmittag des 2026-09-14, siehe oben
   (Rückwärtssuche bei PubChem per SMILES).
4. ~~PubChem-Anfragen haben kein Retry/Caching — bei wiederholten Anfragen zum
   selben Molekül wird jedes Mal neu angefragt.~~ — Caching ergänzt am
   2026-09-19 (später), siehe Eintrag oben (`chem.py`, einfacher
   In-Memory-Cache). Retry gibt es weiterhin nicht, war auch nicht das
   eigentliche Problem.

**Stand der 6 vereinbarten Ausbaustufen** (Details siehe Claude-Gedächtnis,
`project_molecule_viewer.md`, oder frag einfach danach; Stand: Abend des
2026-09-14, nach dem autonomen Durchlauf):
1. ✅ Erledigt — web-basiert statt Blender (Three.js statt 3Dmol.js).
2. ✅ Erledigt — drei Darstellungs-Layer (Kugel-Stab, Raumfüllend, Ladung),
   umschaltbar über Buttons.
3. ✅ Erledigt — Fakten-Panel (Summenformel, Molmasse, LogP, TPSA, H-Brücken,
   drehbare Bindungen), lokal mit RDKit berechnet.
4. ✅ Erledigt — Vergleichsmodus (zwei Moleküle nebeneinander, "+ Vergleichen").
5. ⚠️ Fast erledigt — KI-Erklärtext ist eingebaut und läuft, **wartet aber
   auf einen `ANTHROPIC_API_KEY` von Niki** (siehe Eintrag oben). Zeigt bis
   dahin einen klaren "nicht verfügbar"-Hinweis statt zu crashen.
6. ✅ Erledigt — Reaktions-Animation (Veresterung als Beispiel), Auswahl-Menü
   + Abspiel-Button + Morph-Animation mit Bindungs-Fade. Siehe Eintrag ganz
   oben für den genauen Stand und das Rezept für weitere Reaktionen.

## Zum Wiedereinsteigen

**Das Projekt ist jetzt live: https://molecule-viewer.onrender.com** (Render
Free-Tier, Deployment-Details siehe Eintrag ganz oben). Render-Dashboard:
einloggen mit Nikis Google-Account, Service heißt `molecule-viewer`,
Service-ID `srv-dantbfjtqb8s73d39tfg`.

**Neuen Stand veröffentlichen:** einfach `git push origin main` — Render
deployt automatisch neu, auch ohne die GitHub-App-Verbindung (siehe Eintrag
oben Punkt 2, per echtem Test bestätigt). Dauert ca. 1-2 Minuten
(Docker-Layer-Cache macht wiederholte Builds schnell, sofern sich
`requirements.txt` nicht ändert). Build-/Laufzeit-Logs direkt im
Render-Dashboard unter "Logs" (Chrome-Browser mit Nikis eingeloggter
Render-Session, gleiches Muster wie beim GitHub-Repo) — Shell-Zugriff gibt
es auf dem Free-Tier nicht (nur per Upgrade).

**Lokal weiterentwickeln, wie gewohnt:**
```bash
cd "Claude Code Projekte/molecule-viewer/backend"
./.venv/Scripts/python.exe -m uvicorn app:app --reload --port 8001
```

**Server läuft nach dem 2026-09-20-Durchlauf bereits im Hintergrund** (ohne
`--reload`, PID siehe `netstat -ano | grep ":8001"` falls nötig) — vor einem
Neustart kurz prüfen, ob das noch die gewünschte Instanz ist.

**Neu seit der Boltz-2-Ausbaustufe:** für die Protein-Struktur-Vorhersage
(`/api/fold`) gibt es eine zweite, komplett separate venv,
`backend/.venv-boltz` (Python 3.12, nicht 3.14 wie `backend/.venv` --
Boltz-2 braucht `<3.13`). Die läuft nicht automatisch mit, ist aber schon
fertig eingerichtet (ROCm-PyTorch + Boltz 2.2.1, Gewichte bereits unter
`~/.boltz/` gecacht, ca. 5,8 GB). `folding.py` findet sie automatisch über
`BOLTZ_VENV`/`BOLTZ_BINARY` in seinem Modul-Kopf. Falls diese venv fehlt
oder neu aufgesetzt werden muss, siehe den vollen Befehlsablauf im Eintrag
vom 2026-09-20 oben (Phase 0) -- **wichtig: `--no_kernels` beim
`boltz predict`-Aufruf nicht vergessen** (steht schon fest in
`folding.py` eingebaut), sonst bricht jede Vorhersage auf der AMD-GPU mit
`ModuleNotFoundError: cuequivariance_torch` ab.

**Falls Port 8001 "Method Not Allowed" auf neuen Routen zurückgibt, obwohl
der Code sie enthält:** ein alter Uvicorn-Prozess von einer früheren
Sitzung hängt noch am Port (`netstat -ano | grep ":8001.*ABH"` zeigt dann
zwei Einträge). `pkill -f "uvicorn app:app"` reicht nicht zuverlässig —
stattdessen die PID(s) aus `netstat` mit `taskkill /F /PID <pid> /T`
beenden, dann neu starten.

**Falls nach einer Backend-Änderung `--reload` "Reloading..." loggt, die
Antwort aber trotzdem alt bleibt:** hart neu starten — alte Prozesse per
`taskkill /F /PID <pid> /T` beenden (PID aus `netstat -ano | grep
":8001.*ABH"`), `rm -rf backend/__pycache__`, dann neu starten. Trat beim
Bau von Protein-Docking einmal auf, vermutlich eine mtime-Verzögerung durch
OneDrive-Sync im Projektordner.

**Falls die Seite nach einer Frontend-Änderung (`style.css`/`app.js`) optisch
oder funktional noch alt aussieht:** Browser-Cache, kein Server-Problem (der
Static-File-Mount hat keine `--reload`-Funktion und braucht keine) — hart neu
laden (Strg+Shift+R), siehe Fallstrick im Eintrag vom 2026-09-19 (autonomer
Durchlauf) oben.

Dann **`http://localhost:8001`** im Browser öffnen (Port 8001, nicht 8000 —
siehe Fallstrick oben). Ganz oben die neue **Bibliothek** ausprobieren — auf
ein paar Karten klicken (z. B. "Aspirin", "Vitamin C"), unter "Peptid-
Wirkstoffe" auf "Ozempic / Semaglutid" (PDB `4ZGM`) und "Insulin (an seinem
Rezeptor)" (PDB `4OGA`, zwei Ketten A+B) — beide über `/api/pdb-ligand`,
kein Docking, dauert beim ersten Mal einen Moment — und unter "Kleine Peptide
(angenäherte Faltung)" auf "Oxytocin" oder "Vasopressin" (über `/api/peptide`,
zeigt die per Disulfidbrücken-Heuristik geknäulte Struktur), plus im
Eingabefeld darunter eine eigene Sequenz eintippen (z. B. `GRGDSP`) oder eine
zu lange (>15 Reste) zum Prüfen der Fehlermeldung. Danach Eingabefeld
testen mit z. B. `aspirin`, `C6H12O6`,
`CCO`, die drei Darstellungs-Buttons durchklicken, "+ Vergleichen" mit einem
zweiten Molekül ausprobieren, unten die Veresterung über "▶ Ablaufen
lassen" abspielen, beim neuen "Gleichungslöser"-Bereich "Beispiel laden"
(füllt `CH4 + O2 -> CO2 + H2O`) + "Lösen & animieren" ausprobieren (oder
z. B. `N2 + H2 -> NH3` von Hand eintippen), beim "Chemischer Raum"-Bereich
"Beispiel-Set laden" + "Karte erzeugen" ausprobieren, bei "Protein-Docking"
"Beispiel laden" (füllt `3PTB` + `benzamidine`) + "Docken" ausprobieren
(dauert beim allerersten Mal am längsten, danach ist die Rezeptor-
Vorbereitung für `3PTB` in `backend/pdb_cache/` gecacht und es geht
schnell), und bei "Molekulardynamik" "Beispiel laden" (füllt
`caffeine`) + "Simulieren" — sollte nach ~1 Sekunde ein sichtbar
wackelndes Molekül zeigen. **Ganz unten neu: "Protein-Struktur-Vorhersage
(Boltz-2)"** — "Beispiel laden" (füllt "Oxytocin") + "Vorhersagen", dauert
diesmal wirklich ~30-60s (echter GPU-Rechenlauf + MSA-Server-Aufruf, siehe
Eintrag vom 2026-09-20 oben). 3D-Rendering per Screenshot bestätigt
(kompakte, sichtbar gefaltete Peptidstruktur).

Falls die venv fehlt oder kaputt ist: `python -m venv .venv` im `backend`-
Ordner, dann `./.venv/Scripts/python.exe -m pip install -r requirements.txt`
(für Backend-Tests zusätzlich `-r requirements-dev.txt`, siehe README).
**Zusätzlich** liegt unter `backend/tools/vina.exe` die AutoDock-Vina-Binary
— die ist keine Python-Abhängigkeit und muss beim venv-Neuaufsetzen nicht
neu installiert werden, nur falls der ganze `backend`-Ordner fehlt: neu
laden von `github.com/ccsb-scripps/AutoDock-Vina/releases` (Datei
`vina_1.2.7_win.exe`, umbenennen zu `vina.exe`). Für die Molekulardynamik
und den Gleichungslöser ist nichts Zusätzliches nötig — beide nutzen nur
schon vorhandene Pakete (RDKit, numpy, scipy).

**Alle 6 ursprünglich vereinbarten Ausbaustufen sind erledigt, plus alle
3 der "richtig aufwendigen" API-freien Folge-Ausbaustufen (chemischer
Raum, Protein-Docking, Molekulardynamik), plus eine 10. (Gleichungslöser),
eine 11., zweiteilige Ausbaustufe vom 2026-09-19 (autonomer Durchlauf):
PDB-Liganden direkt anzeigen (`/api/pdb-ligand`) + Bibliothek-Bereich im
Frontend, samt Folge-Ergänzung um Insulin an seinem Rezeptor (4OGA, per
neuem `chain_ids`-Parameter), eine 12.: kleine Peptide per
Sequenzeingabe (`/api/peptide`, bis 15 Reste, mit Disulfidbrücken-Heuristik
und energieärmster von mehreren Konformeren, siehe Eintrag ganz oben), und
eine 13. (2026-09-20, autonomer Durchlauf): echte Protein-Struktur-
Vorhersage mit Boltz-2 (`/api/fold`, GPU-beschleunigt über ROCm auf der RX
7900 XTX, separate venv, siehe Eintrag ganz oben — 3D-Rendering per
Screenshot bestätigt).**
Einzige offene Lücke aus dem Kern: KI-Erklärtext (Ausbaustufe 5)
wartet weiter auf einen `ANTHROPIC_API_KEY` von Niki — `backend/.env.example`
nach `backend/.env` kopieren, echten Key eintragen, Server neu starten.
Alles andere läuft schon ohne das.

**Projekt ist seit dem 2026-09-20-Durchlauf (später) live deployt, siehe
Eintrag ganz oben: https://molecule-viewer.onrender.com.** Formel-
Mehrdeutigkeits-Heuristik, PubChem-Retry und das Export/Screenshot-Feature
sind ebenfalls erledigt (gleicher Eintrag). **Nächste Schritte sind
komplett offen** — es gibt keine vereinbarte Ausbaustufe mehr, die noch
aussteht. Ideen für kleinere Lücken/Politur, falls gefragt: weitere
Reaktionen zu `backend/reactions.py` ergänzen (Rezept siehe oben), beim
Protein-Docking die Ladungszustände des Liganden vor dem Docken
berücksichtigen (bewusst zurückgestellt, siehe Einschränkung oben), bei der
Molekulardynamik echte Bindungslängen-Constraints (SHAKE/RATTLE) einbauen
(ebenfalls bewusst zurückgestellt), die Atom-Zuordnung im Gleichungslöser
verbessern (z. B. per lokaler Bindungsumgebung statt reinem Abstand vor-
matchen, siehe Eintrag vom 2026-09-19), weitere Peptid-Wirkstoffe/Klein-
Molekül-Karten zur Bibliothek ergänzen (z. B. per `hetero_code` oder
`chain_ids`, siehe die beiden 2026-09-19-Einträge oben), die kuratierte
Peptid-Namensliste in `peptide.py` erweitern, GitHub-Auto-Deploy in Render
verbinden (braucht Nikis OAuth-Freigabe, siehe Deployment-Eintrag), oder
einen eigenen `ANTHROPIC_API_KEY` im Render-Dashboard eintragen, damit die
KI-Erklärung auch auf der öffentlichen Instanz läuft — aber erst wieder
anfangen, wenn Niki eine neue Richtung vorgibt.
