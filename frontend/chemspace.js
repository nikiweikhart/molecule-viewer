// Kleines, selbstgebautes Canvas-2D-Scatterplot für den chemischen Raum —
// bewusst ohne Chart-Bibliothek, analog zur "kein Build-Schritt, minimale
// Abhängigkeiten"-Linie des restlichen Frontends.

// Teilmenge der Element-Farben aus viewer.js (dort nicht exportiert, deshalb
// hier als eigene, aber bewusst gleiche Palette dupliziert) — bleibt visuell
// konsistent mit dem 3D-Viewer statt neue Farben zu erfinden.
const CLUSTER_COLORS = [
  "#e0965a", // Akzent-Amber
  "#4a7ebd", // Blau (wie Stickstoff)
  "#d1553f", // Rot (wie Sauerstoff)
  "#63c264", // Grün (wie Chlor)
  "#d6b64c", // Gelb (wie Schwefel)
  "#8f4ab0", // Violett (wie Iod)
];

const POINT_RADIUS = 6;
const HOVER_RADIUS = 9;
const HIT_RADIUS_PX = 16;
const PADDING_FRACTION = 0.12;

function colorForCluster(cluster) {
  return CLUSTER_COLORS[cluster % CLUSTER_COLORS.length];
}

export function createChemSpacePlot(canvas) {
  const ctx = canvas.getContext("2d");

  let points = [];
  let screenPoints = []; // {sx, sy, point} — Cache für Hit-Testing
  let hoveredIndex = -1;
  let onSelect = null;
  let onHover = null;

  function project() {
    if (points.length === 0) {
      screenPoints = [];
      return;
    }
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;

    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    let minX = Math.min(...xs);
    let maxX = Math.max(...xs);
    let minY = Math.min(...ys);
    let maxY = Math.max(...ys);

    // Entartete Achse (z.B. nur 2 identische Moleküle) — künstliche Spanne
    // vermeidet Division durch 0.
    if (maxX - minX < 1e-6) {
      maxX += 1;
      minX -= 1;
    }
    if (maxY - minY < 1e-6) {
      maxY += 1;
      minY -= 1;
    }

    const padX = (maxX - minX) * PADDING_FRACTION;
    const padY = (maxY - minY) * PADDING_FRACTION;
    minX -= padX;
    maxX += padX;
    minY -= padY;
    maxY += padY;

    screenPoints = points.map((point) => ({
      sx: ((point.x - minX) / (maxX - minX)) * width,
      // Y invertiert, damit "oben" im Datenraum auch oben im Bild ist.
      sy: height - ((point.y - minY) / (maxY - minY)) * height,
      point,
    }));
  }

  function draw() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    ctx.clearRect(0, 0, width, height);

    screenPoints.forEach(({ sx, sy, point }, index) => {
      const isHovered = index === hoveredIndex;
      const radius = isHovered ? HOVER_RADIUS : POINT_RADIUS;

      ctx.beginPath();
      ctx.arc(sx, sy, radius, 0, Math.PI * 2);
      ctx.fillStyle = colorForCluster(point.cluster);
      ctx.globalAlpha = isHovered ? 1 : 0.85;
      ctx.fill();

      if (isHovered) {
        ctx.globalAlpha = 1;
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#efe8dd";
        ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const dpr = Math.min(window.devicePixelRatio, 2);
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    project();
    draw();
  }

  function findNearest(mouseX, mouseY) {
    let nearestIndex = -1;
    let nearestDist = HIT_RADIUS_PX;
    for (let i = 0; i < screenPoints.length; i++) {
      const { sx, sy } = screenPoints[i];
      const dist = Math.hypot(sx - mouseX, sy - mouseY);
      if (dist < nearestDist) {
        nearestDist = dist;
        nearestIndex = i;
      }
    }
    return nearestIndex;
  }

  canvas.addEventListener("mousemove", (event) => {
    const rect = canvas.getBoundingClientRect();
    const index = findNearest(event.clientX - rect.left, event.clientY - rect.top);
    if (index !== hoveredIndex) {
      hoveredIndex = index;
      draw();
      if (onHover) onHover(index >= 0 ? screenPoints[index].point : null);
    }
  });

  canvas.addEventListener("mouseleave", () => {
    if (hoveredIndex !== -1) {
      hoveredIndex = -1;
      draw();
      if (onHover) onHover(null);
    }
  });

  canvas.addEventListener("click", (event) => {
    const rect = canvas.getBoundingClientRect();
    const index = findNearest(event.clientX - rect.left, event.clientY - rect.top);
    if (index >= 0 && onSelect) onSelect(screenPoints[index].point);
  });

  window.addEventListener("resize", resize);
  resize();

  return {
    setPoints(newPoints) {
      points = newPoints;
      hoveredIndex = -1;
      resize();
    },
    setOnSelect(fn) {
      onSelect = fn;
    },
    setOnHover(fn) {
      onHover = fn;
    },
    resize,
    dispose() {
      window.removeEventListener("resize", resize);
    },
  };
}
