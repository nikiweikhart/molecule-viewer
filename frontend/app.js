import { createViewer } from "./viewer.js";
import { createChemSpacePlot } from "./chemspace.js";

function downloadScreenshot(viewer, filenameBase) {
  const dataUrl = viewer.captureScreenshot();
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = `${filenameBase}.png`;
  link.click();
}

const FACT_DEFS = [
  { key: "formula", label: "Summenformel", unit: "" },
  { key: "molweight", label: "Molare Masse", unit: "g/mol" },
  { key: "logp", label: "LogP (berechnet)", unit: "" },
  { key: "tpsa", label: "TPSA", unit: "Å²" },
  { key: "h_donors", label: "H-Brücken-Donoren", unit: "" },
  { key: "h_acceptors", label: "H-Brücken-Akzeptoren", unit: "" },
  { key: "rotatable_bonds", label: "Drehbare Bindungen", unit: "" },
];

const form = document.getElementById("query-form");
const input = document.getElementById("query-input");
const input2 = document.getElementById("query-input-2");
const compareToggle = document.getElementById("compare-toggle");
const modeRow = document.getElementById("mode-row");
const noteEl = document.getElementById("note");
const errorEl = document.getElementById("error");
const cardsEl = document.getElementById("cards");
const cardTemplate = document.getElementById("card-template");
const reactionSelect = document.getElementById("reaction-select");
const reactionPlayButton = document.getElementById("reaction-play");
const reactionViewerContainer = document.getElementById("reaction-viewer");

const equationInput = document.getElementById("equation-input");
const equationExampleButton = document.getElementById("equation-example");
const equationSolveButton = document.getElementById("equation-solve");
const equationViewerContainer = document.getElementById("equation-viewer");
const equationInfoEl = document.getElementById("equation-info");

const chemspaceInput = document.getElementById("chemspace-input");
const chemspaceExampleButton = document.getElementById("chemspace-example");
const chemspaceBuildButton = document.getElementById("chemspace-build");
const chemspaceCanvas = document.getElementById("chemspace-canvas");
const chemspaceInfoEl = document.getElementById("chemspace-info");

const CHEMSPACE_EXAMPLE_SET = [
  "aspirin", "ibuprofen", "paracetamol", "naproxen",
  "glucose", "fructose", "sucrose", "ribose",
  "methanol", "ethanol", "isopropanol",
  "glycine", "alanine", "serine", "phenylalanine",
  "cholesterol", "testosterone",
];

const libraryEl = document.getElementById("library");

// Bibliothek: Alternative zum manuellen Eintippen, für Chemie-Anfänger --
// bewusst nur Alltagsnamen, keine Formeln/SMILES sichtbar (die zeigt das
// Fakten-Panel nach dem Laden ohnehin automatisch). Kategorien orientieren
// sich am CHEMSPACE_EXAMPLE_SET oben, plus zwei zusätzliche ("Hormone",
// "Haushalt & Reinigung"), die zu den dort schon vorhandenen Beispiel-
// Molekülen passen (Testosteron war schon im chemspace-Set, Isopropanol war
// im "Alkohole"-Cluster). Bewusst KEINE großen Peptid-Wirkstoffe über
// /api/resolve -- RDKits EmbedMolecule wäre dafür unzuverlässig/langsam.
// Semaglutid und Insulin gehen trotzdem, aber über den separaten
// /api/pdb-ligand-Pfad (echte Kristallstruktur-Koordinaten, kein Embedding).
const LIBRARY_CATEGORIES = [
  {
    title: "Alltagsstoffe",
    items: [
      { label: "Wasser", query: "water" },
      { label: "Zucker", query: "sucrose" },
      { label: "Koffein", query: "caffeine" },
      { label: "Alkohol", query: "ethanol" },
    ],
  },
  {
    title: "Schmerz & Fieber",
    items: [
      { label: "Aspirin", query: "aspirin" },
      { label: "Ibuprofen", query: "ibuprofen" },
      { label: "Paracetamol", query: "paracetamol" },
    ],
  },
  {
    title: "Bausteine des Körpers",
    items: [
      { label: "Glycin", query: "glycine" },
      { label: "Alanin", query: "alanine" },
      { label: "Phenylalanin", query: "phenylalanine" },
    ],
  },
  {
    title: "Vitamine",
    items: [
      { label: "Vitamin C", query: "ascorbic acid" },
      { label: "Vitamin D", query: "cholecalciferol" },
    ],
  },
  {
    title: "Süßes & Fette",
    items: [
      { label: "Traubenzucker", query: "glucose" },
      { label: "Fruchtzucker", query: "fructose" },
      { label: "Cholesterin", query: "cholesterol" },
    ],
  },
  {
    title: "Hormone",
    items: [
      { label: "Testosteron", query: "testosterone" },
      { label: "Östrogen", query: "estradiol" },
      { label: "Adrenalin", query: "epinephrine" },
    ],
  },
  {
    title: "Haushalt & Reinigung",
    items: [
      { label: "Essig", query: "acetic acid" },
      { label: "Desinfektionsmittel", query: "isopropanol" },
    ],
  },
  {
    title: "Peptid-Wirkstoffe (aus echten 3D-Messungen)",
    hint: "Lädt die reale, gemessene Struktur direkt aus der Proteindatenbank (RCSB PDB) statt sie neu zu berechnen — deshalb funktioniert das auch für Wirkstoffe, die für die normale Auflösung zu groß wären.",
    className: "library-category-peptide",
    items: [
      { label: "Ozempic / Semaglutid", pdbId: "4ZGM" },
      { label: "Insulin (an seinem Rezeptor)", pdbId: "4OGA", chainIds: ["A", "B"] },
    ],
  },
  {
    title: "Kleine Peptide (angenäherte Faltung)",
    hint: "Baut die Struktur lokal aus dem Ein-Buchstaben-Aminosäurecode auf (RDKit-Embedding, energieärmste von mehreren Konformeren) — eine berechnete Näherung, keine gemessene oder biologisch bestätigte Faltung. Bis ca. 15 Aminosäuren, siehe Eingabefeld unten für eigene Sequenzen.",
    className: "library-category-peptide",
    items: [
      { label: "Oxytocin", peptideName: "oxytocin" },
      { label: "Vasopressin", peptideName: "vasopressin" },
      { label: "Met-Enkephalin", peptideName: "met-enkephalin" },
      { label: "Leu-Enkephalin", peptideName: "leu-enkephalin" },
    ],
    customSequenceInput: true,
  },
];

const dockingPdbInput = document.getElementById("docking-pdb-input");
const dockingLigandInput = document.getElementById("docking-ligand-input");
const dockingExampleButton = document.getElementById("docking-example");
const dockingDockButton = document.getElementById("docking-dock");
const dockingViewerContainer = document.getElementById("docking-viewer");
const dockingInfoEl = document.getElementById("docking-info");

const dynamicsInput = document.getElementById("dynamics-input");
const dynamicsExampleButton = document.getElementById("dynamics-example");
const dynamicsRunButton = document.getElementById("dynamics-run");
const dynamicsViewerContainer = document.getElementById("dynamics-viewer");
const dynamicsInfoEl = document.getElementById("dynamics-info");

const foldingInput = document.getElementById("folding-input");
const foldingExampleButton = document.getElementById("folding-example");
const foldingRunButton = document.getElementById("folding-run");
const foldingViewerContainer = document.getElementById("folding-viewer");
const foldingInfoEl = document.getElementById("folding-info");

let compareActive = false;
let currentMode = "ball-stick";

// Jede Karte (1 normal, 2 im Vergleichsmodus) hält ihren eigenen Viewer + DOM-Referenzen.
const slots = [null, null];

function hide(el) {
  el.hidden = true;
}

function show(el, text) {
  el.textContent = text;
  el.hidden = false;
}

function createSlot() {
  const node = cardTemplate.content.firstElementChild.cloneNode(true);
  cardsEl.appendChild(node);

  const viewerContainer = node.querySelector(".viewer");
  const viewer = createViewer(viewerContainer);

  const exportButton = node.querySelector(".export-button");
  exportButton.addEventListener("click", () => downloadScreenshot(viewer, "molekuel"));

  return {
    node,
    viewer,
    resultNamesEl: node.querySelector(".result-names"),
    commonNameEl: node.querySelector(".result-common-name"),
    iupacNameEl: node.querySelector(".result-iupac-name"),
    factsEl: node.querySelector(".facts"),
    explainEl: node.querySelector(".explain"),
  };
}

function ensureSlot(index) {
  if (!slots[index]) {
    slots[index] = createSlot();
  }
  return slots[index];
}

function removeSlot(index) {
  if (slots[index]) {
    slots[index].viewer.dispose();
    slots[index].node.remove();
    slots[index] = null;
  }
}

function renderFacts(slot, facts) {
  slot.factsEl.innerHTML = "";
  for (const def of FACT_DEFS) {
    const tile = document.createElement("div");
    tile.className = "fact-tile";

    const value = document.createElement("div");
    value.className = "fact-value";
    value.textContent = facts[def.key];
    if (def.unit) {
      const unit = document.createElement("span");
      unit.className = "unit";
      unit.textContent = def.unit;
      value.appendChild(unit);
    }

    const label = document.createElement("div");
    label.className = "fact-label";
    label.textContent = def.label;

    tile.appendChild(value);
    tile.appendChild(label);
    slot.factsEl.appendChild(tile);
  }
  slot.factsEl.hidden = false;
}

function renderNames(slot, data) {
  slot.commonNameEl.textContent = data.common_name.toUpperCase();
  const isRedundant =
    !data.iupac_name || data.iupac_name.toLowerCase() === data.common_name.toLowerCase();
  slot.iupacNameEl.textContent = isRedundant ? "" : data.iupac_name;
  slot.resultNamesEl.hidden = false;
}

async function loadExplanation(slot, data) {
  slot.explainEl.hidden = false;
  slot.explainEl.className = "explain loading";
  slot.explainEl.textContent = "KI-Erklärung wird geladen …";

  let response;
  try {
    response = await fetch("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        common_name: data.common_name,
        iupac_name: data.iupac_name,
        formula: data.facts.formula,
      }),
    });
  } catch (err) {
    slot.explainEl.className = "explain unavailable";
    slot.explainEl.textContent = "KI-Erklärung: Verbindung fehlgeschlagen.";
    return;
  }

  const result = await response.json();
  if (result.available) {
    slot.explainEl.className = "explain";
    slot.explainEl.textContent = result.text;
  } else {
    slot.explainEl.className = "explain unavailable";
    slot.explainEl.textContent = `KI-Erklärung noch nicht verfügbar (${result.reason})`;
  }
}

async function resolveQuery(query) {
  const response = await fetch("/api/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Unbekannter Fehler.");
  }
  return data;
}

function applyResolvedData(slot, data) {
  slot.viewer.setMolecule(data.atoms, data.bonds);
  slot.viewer.setMode(currentMode);
  renderFacts(slot, data.facts);
  renderNames(slot, data);
  loadExplanation(slot, data); // läuft im Hintergrund weiter, blockiert nichts
}

async function loadIntoSlot(index, query) {
  const slot = ensureSlot(index);
  const data = await resolveQuery(query);
  applyResolvedData(slot, data);
  return data;
}

async function resolvePdbLigand(pdbId, heteroCode, chainIds) {
  const response = await fetch("/api/pdb-ligand", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pdb_id: pdbId, hetero_code: heteroCode || null, chain_ids: chainIds || null }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Unbekannter Fehler.");
  }
  return data;
}

async function loadPdbLigandIntoSlot(index, pdbId, heteroCode, chainIds) {
  const slot = ensureSlot(index);
  const data = await resolvePdbLigand(pdbId, heteroCode, chainIds);
  applyResolvedData(slot, data);
  return data;
}

async function resolvePeptide(name, sequence) {
  const response = await fetch("/api/peptide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name || null, sequence: sequence || null }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Unbekannter Fehler.");
  }
  return data;
}

async function loadPeptideIntoSlot(index, name, sequence) {
  const slot = ensureSlot(index);
  const data = await resolvePeptide(name, sequence);
  applyResolvedData(slot, data);
  return data;
}

function createLibraryCard(item) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "library-card";
  card.textContent = item.label;

  card.addEventListener("click", async () => {
    if (card.classList.contains("loading")) return;
    card.classList.add("loading");
    hide(errorEl);
    hide(noteEl);

    try {
      const data = item.pdbId
        ? await loadPdbLigandIntoSlot(0, item.pdbId, item.heteroCode, item.chainIds)
        : item.peptideName
        ? await loadPeptideIntoSlot(0, item.peptideName, null)
        : await loadIntoSlot(0, item.query);
      if (data.note) show(noteEl, data.note);
      cardsEl.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      show(errorEl, err.message || "Unbekannter Fehler.");
    } finally {
      card.classList.remove("loading");
    }
  });

  return card;
}

function createPeptideSequenceRow() {
  const row = document.createElement("div");
  row.className = "docking-controls peptide-sequence-row";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Eigene Sequenz — Ein-Buchstaben-Code, z. B. CYIQNCPLG";
  input.autocomplete = "off";

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Peptid laden";

  button.addEventListener("click", async () => {
    const sequence = input.value.trim();
    if (!sequence || button.classList.contains("loading")) return;
    button.classList.add("loading");
    hide(errorEl);
    hide(noteEl);

    try {
      const data = await loadPeptideIntoSlot(0, null, sequence);
      if (data.note) show(noteEl, data.note);
      cardsEl.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      show(errorEl, err.message || "Unbekannter Fehler.");
    } finally {
      button.classList.remove("loading");
    }
  });

  row.appendChild(input);
  row.appendChild(button);
  return row;
}

function renderLibrary() {
  for (const category of LIBRARY_CATEGORIES) {
    const section = document.createElement("div");
    section.className = "library-category";
    if (category.className) section.classList.add(category.className);

    const title = document.createElement("div");
    title.className = "library-category-title";
    title.textContent = category.title;
    section.appendChild(title);

    if (category.hint) {
      const hint = document.createElement("div");
      hint.className = "library-category-hint";
      hint.textContent = category.hint;
      section.appendChild(hint);
    }

    const grid = document.createElement("div");
    grid.className = "library-grid";
    for (const item of category.items) {
      grid.appendChild(createLibraryCard(item));
    }
    section.appendChild(grid);

    if (category.customSequenceInput) {
      section.appendChild(createPeptideSequenceRow());
    }

    libraryEl.appendChild(section);
  }
}

renderLibrary();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = input.value.trim();
  const query2 = input2.value.trim();
  if (!query) return;

  hide(noteEl);
  hide(errorEl);

  try {
    const primary = await loadIntoSlot(0, query);
    if (primary.note) show(noteEl, primary.note);

    if (compareActive && query2) {
      const secondary = await loadIntoSlot(1, query2);
      if (secondary.note) show(noteEl, `${primary.note ? primary.note + " " : ""}${secondary.note}`);
    } else {
      removeSlot(1);
    }
  } catch (err) {
    show(errorEl, err.message || "Unbekannter Fehler.");
  }
});

compareToggle.addEventListener("click", () => {
  compareActive = !compareActive;
  compareToggle.classList.toggle("active", compareActive);
  compareToggle.textContent = compareActive ? "− Vergleichen" : "+ Vergleichen";
  input2.hidden = !compareActive;
  cardsEl.classList.toggle("cards-compare", compareActive);
  if (!compareActive) {
    removeSlot(1);
  }
  // Grid-Spalten haben sich geändert — bestehenden Viewer neu einpassen.
  requestAnimationFrame(() => {
    if (slots[0]) slots[0].viewer.resize();
  });
});

modeRow.addEventListener("click", (event) => {
  const btn = event.target.closest(".mode-btn");
  if (!btn) return;

  currentMode = btn.dataset.mode;
  for (const b of modeRow.querySelectorAll(".mode-btn")) {
    b.classList.toggle("active", b === btn);
  }
  for (const slot of slots) {
    if (slot) slot.viewer.setMode(currentMode);
  }
});

const reactionViewer = createViewer(reactionViewerContainer);
document
  .getElementById("reaction-export")
  .addEventListener("click", () => downloadScreenshot(reactionViewer, "reaktion"));

async function loadReactionList() {
  const response = await fetch("/api/reactions");
  const reactions = await response.json();
  reactionSelect.innerHTML = "";
  for (const reaction of reactions) {
    const option = document.createElement("option");
    option.value = reaction.id;
    option.textContent = reaction.label;
    reactionSelect.appendChild(option);
  }
}

reactionPlayButton.addEventListener("click", async () => {
  const id = reactionSelect.value;
  if (!id) return;

  hide(errorEl);
  reactionPlayButton.disabled = true;
  try {
    const response = await fetch(`/api/reactions/${id}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unbekannter Fehler.");
    }
    reactionViewer.playReaction(data);
  } catch (err) {
    show(errorEl, err.message || "Unbekannter Fehler.");
  } finally {
    reactionPlayButton.disabled = false;
  }
});

loadReactionList();

const equationViewer = createViewer(equationViewerContainer);
document
  .getElementById("equation-export")
  .addEventListener("click", () => downloadScreenshot(equationViewer, "gleichung"));

equationExampleButton.addEventListener("click", () => {
  equationInput.value = "CH4 + O2 -> CO2 + H2O";
});

equationSolveButton.addEventListener("click", async () => {
  const equation = equationInput.value.trim();
  if (!equation) {
    show(errorEl, "Bitte eine Reaktionsgleichung eingeben.");
    return;
  }

  hide(errorEl);
  equationInfoEl.hidden = false;
  equationInfoEl.className = "chemspace-info";
  equationInfoEl.textContent = "Wird gelöst …";
  equationSolveButton.disabled = true;

  try {
    const response = await fetch("/api/equation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ equation }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unbekannter Fehler.");
    }

    equationViewer.playReaction(data);

    equationInfoEl.innerHTML = "";
    const name = document.createElement("span");
    name.className = "chemspace-info-name";
    name.textContent = data.label;
    const detail = document.createElement("span");
    detail.className = "chemspace-info-detail";
    detail.textContent =
      "Automatisch ausgeglichen und animiert — Atom-Zuordnung ist eine Näherung " +
      "(nächstgelegene Zuordnung je Element), nicht chemisch exakt wie bei der " +
      "handkuratierten Reaktion oben.";
    equationInfoEl.appendChild(name);
    equationInfoEl.appendChild(document.createElement("br"));
    equationInfoEl.appendChild(detail);
  } catch (err) {
    equationInfoEl.hidden = true;
    show(errorEl, err.message || "Unbekannter Fehler.");
  } finally {
    equationSolveButton.disabled = false;
  }
});

const chemspacePlot = createChemSpacePlot(chemspaceCanvas);

function formatChemspaceInfo(point) {
  chemspaceInfoEl.innerHTML = "";
  const name = document.createElement("span");
  name.className = "chemspace-info-name";
  name.textContent = point.common_name;
  const detail = document.createElement("span");
  detail.className = "chemspace-info-detail";
  detail.textContent = `${point.facts.formula} · ${point.facts.molweight} g/mol · LogP ${point.facts.logp}`;
  chemspaceInfoEl.appendChild(name);
  chemspaceInfoEl.appendChild(detail);
  chemspaceInfoEl.hidden = false;
}

chemspacePlot.setOnHover((point) => {
  if (point) {
    formatChemspaceInfo(point);
    chemspaceCanvas.style.cursor = "pointer";
  } else {
    chemspaceInfoEl.hidden = true;
    chemspaceCanvas.style.cursor = "default";
  }
});

chemspacePlot.setOnSelect(async (point) => {
  formatChemspaceInfo(point);
  try {
    await loadIntoSlot(0, point.smiles);
    cardsEl.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    show(errorEl, err.message || "Unbekannter Fehler.");
  }
});

chemspaceExampleButton.addEventListener("click", () => {
  chemspaceInput.value = CHEMSPACE_EXAMPLE_SET.join("\n");
});

chemspaceBuildButton.addEventListener("click", async () => {
  const queries = chemspaceInput.value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (queries.length < 2) {
    show(errorEl, "Mindestens 2 Moleküle nötig, um eine Karte zu erzeugen.");
    return;
  }

  hide(errorEl);
  hide(noteEl);
  chemspaceBuildButton.disabled = true;
  try {
    const response = await fetch("/api/chemical-space", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ queries }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unbekannter Fehler.");
    }
    chemspacePlot.setPoints(data.points);
    if (data.failed.length > 0) {
      show(noteEl, `Nicht erkannt: ${data.failed.join(", ")}`);
    }
  } catch (err) {
    show(errorEl, err.message || "Unbekannter Fehler.");
  } finally {
    chemspaceBuildButton.disabled = false;
  }
});

const dockingViewer = createViewer(dockingViewerContainer);
document
  .getElementById("docking-export")
  .addEventListener("click", () => downloadScreenshot(dockingViewer, "docking"));

dockingExampleButton.addEventListener("click", () => {
  dockingPdbInput.value = "3PTB";
  dockingLigandInput.value = "benzamidine";
});

dockingDockButton.addEventListener("click", async () => {
  const pdbId = dockingPdbInput.value.trim();
  const ligandQuery = dockingLigandInput.value.trim();
  if (!pdbId || !ligandQuery) {
    show(errorEl, "PDB-ID und Ligand werden beide gebraucht.");
    return;
  }

  hide(errorEl);
  dockingInfoEl.hidden = false;
  dockingInfoEl.className = "chemspace-info";
  dockingInfoEl.textContent = "Wird berechnet … (Rezeptor-Vorbereitung + Docking-Suche, kann eine Weile dauern)";
  dockingDockButton.disabled = true;

  try {
    const response = await fetch("/api/dock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdb_id: pdbId, ligand_query: ligandQuery }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unbekannter Fehler.");
    }

    dockingViewer.setDockingResult(data);

    const affinities = data.affinities.map((a) => `${a} kcal/mol`).join(", ");
    dockingInfoEl.innerHTML = "";
    const name = document.createElement("span");
    name.className = "chemspace-info-name";
    name.textContent = data.protein_name;
    const detail = document.createElement("span");
    detail.className = "chemspace-info-detail";
    detail.textContent = `Referenz-Ligand: ${data.reference_ligand} · Bindungsenergien: ${affinities}`;
    dockingInfoEl.appendChild(name);
    dockingInfoEl.appendChild(document.createElement("br"));
    dockingInfoEl.appendChild(detail);
  } catch (err) {
    dockingInfoEl.hidden = true;
    show(errorEl, err.message || "Unbekannter Fehler.");
  } finally {
    dockingDockButton.disabled = false;
  }
});

const dynamicsViewer = createViewer(dynamicsViewerContainer);
document
  .getElementById("dynamics-export")
  .addEventListener("click", () => downloadScreenshot(dynamicsViewer, "molekulardynamik"));

dynamicsExampleButton.addEventListener("click", () => {
  dynamicsInput.value = "caffeine";
});

dynamicsRunButton.addEventListener("click", async () => {
  const query = dynamicsInput.value.trim();
  if (!query) {
    show(errorEl, "Bitte ein Molekül eingeben.");
    return;
  }

  hide(errorEl);
  dynamicsInfoEl.hidden = false;
  dynamicsInfoEl.className = "chemspace-info";
  dynamicsInfoEl.textContent = "Wird simuliert …";
  dynamicsRunButton.disabled = true;

  try {
    const response = await fetch("/api/dynamics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unbekannter Fehler.");
    }

    dynamicsViewer.playTrajectory(data);

    dynamicsInfoEl.innerHTML = "";
    const name = document.createElement("span");
    name.className = "chemspace-info-name";
    name.textContent = query;
    const detail = document.createElement("span");
    detail.className = "chemspace-info-detail";
    detail.textContent = `${data.temperature} K · ${data.fs_simulated} fs simuliert · ${data.elements.length} Atome`;
    dynamicsInfoEl.appendChild(name);
    dynamicsInfoEl.appendChild(document.createElement("br"));
    dynamicsInfoEl.appendChild(detail);
  } catch (err) {
    dynamicsInfoEl.hidden = true;
    show(errorEl, err.message || "Unbekannter Fehler.");
  } finally {
    dynamicsRunButton.disabled = false;
  }
});

const foldingViewer = createViewer(foldingViewerContainer);
document
  .getElementById("folding-export")
  .addEventListener("click", () => downloadScreenshot(foldingViewer, "proteinfaltung"));

foldingExampleButton.addEventListener("click", () => {
  foldingInput.value = "Oxytocin";
});

// Boltz-2 braucht eine lokale GPU (siehe backend/folding.py) -- auf einem Hosting-Tier
// ohne GPU (z.B. der öffentlichen Deployment-Instanz) proaktiv ausgrauen statt erst
// nach einem fehlgeschlagenen Versuch zu erklären, warum es nicht geht.
fetch("/api/fold-available")
  .then((r) => r.json())
  .then(({ available }) => {
    if (available) return;
    foldingInput.disabled = true;
    foldingExampleButton.disabled = true;
    foldingRunButton.disabled = true;
    foldingInfoEl.hidden = false;
    foldingInfoEl.className = "chemspace-info";
    foldingInfoEl.textContent =
      "Auf dieser öffentlichen Instanz nicht verfügbar -- Boltz-2 braucht eine lokale GPU " +
      "und läuft nur auf Nikis eigenem Rechner.";
  })
  .catch(() => {
    /* Verfügbarkeitscheck ist reine Komfort-Politur -- bei Fehlschlag bleibt der
       Bereich einfach normal nutzbar, /api/fold selbst meldet den Fehler dann wie gehabt. */
  });

foldingRunButton.addEventListener("click", async () => {
  const raw = foldingInput.value.trim();
  if (!raw) {
    show(errorEl, "Bitte eine Sequenz oder einen Namen eingeben.");
    return;
  }
  // Sequenz erkannt: nur Buchstaben aus den 20 Standard-Aminosäure-Codes, min. 2 Zeichen.
  const isSequence = /^[ACDEFGHIKLMNPQRSTVWY]{2,}$/i.test(raw);

  hide(errorEl);
  foldingInfoEl.hidden = false;
  foldingInfoEl.className = "chemspace-info";
  foldingInfoEl.textContent =
    "Wird mit Boltz-2 berechnet … das kann je nach Sequenzlänge und Hardware " +
    "mehrere Minuten dauern (echte ML-Struktur-Vorhersage, keine Näherung).";
  foldingRunButton.disabled = true;

  try {
    const response = await fetch("/api/fold", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        isSequence ? { sequence: raw.toUpperCase() } : { name: raw }
      ),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unbekannter Fehler.");
    }

    foldingViewer.setMolecule(data.atoms, data.bonds);

    foldingInfoEl.innerHTML = "";
    const name = document.createElement("span");
    name.className = "chemspace-info-name";
    name.textContent = data.common_name;
    const detail = document.createElement("span");
    detail.className = "chemspace-info-detail";
    detail.textContent = data.note;
    foldingInfoEl.appendChild(name);
    foldingInfoEl.appendChild(document.createElement("br"));
    foldingInfoEl.appendChild(detail);
  } catch (err) {
    foldingInfoEl.hidden = true;
    show(errorEl, err.message || "Unbekannter Fehler.");
  } finally {
    foldingRunButton.disabled = false;
  }
});
