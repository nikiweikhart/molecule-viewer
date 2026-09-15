import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const ELEMENT_STYLE = {
  H: { color: 0xf2ede3, radius: 0.28, vdw: 1.2 },
  C: { color: 0x4a4744, radius: 0.42, vdw: 1.7 },
  N: { color: 0x4a7ebd, radius: 0.42, vdw: 1.55 },
  O: { color: 0xd1553f, radius: 0.42, vdw: 1.52 },
  S: { color: 0xd6b64c, radius: 0.46, vdw: 1.8 },
  P: { color: 0xd68a4c, radius: 0.46, vdw: 1.8 },
  F: { color: 0x7fbf7f, radius: 0.38, vdw: 1.47 },
  Cl: { color: 0x63c264, radius: 0.44, vdw: 1.75 },
  Br: { color: 0xa14a3a, radius: 0.46, vdw: 1.85 },
  I: { color: 0x8f4ab0, radius: 0.48, vdw: 1.98 },
  DEFAULT: { color: 0xb9a8c9, radius: 0.42, vdw: 1.7 },
};

const BOND_RADIUS = 0.11;
const BOND_COLOR = 0x2a2724;

const CHARGE_NEG = new THREE.Color(0xd1553f); // negativ = warmes Rot
const CHARGE_MID = new THREE.Color(0xefe8dd); // neutral = cremeweiß
const CHARGE_POS = new THREE.Color(0x4a7ebd); // positiv = Blau
const CHARGE_SCALE = 0.4; // Ladung ab hier voll gesättigt dargestellt

function styleFor(element) {
  return ELEMENT_STYLE[element] || ELEMENT_STYLE.DEFAULT;
}

function colorForCharge(charge) {
  const t = Math.max(-1, Math.min(1, charge / CHARGE_SCALE));
  const color = new THREE.Color();
  if (t < 0) {
    color.lerpColors(CHARGE_MID, CHARGE_NEG, -t);
  } else {
    color.lerpColors(CHARGE_MID, CHARGE_POS, t);
  }
  return color;
}

/**
 * Baut einen eigenständigen 3D-Molekül-Viewer in `container` auf.
 * Jede Instanz hat eine eigene Three.js-Szene/Kamera/Renderloop, damit
 * mehrere Viewer (Vergleichsmodus) unabhängig nebeneinander laufen können.
 */
export function createViewer(container) {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  container.appendChild(renderer.domElement);

  const pmremGenerator = new THREE.PMREMGenerator(renderer);
  scene.environment = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 2;
  controls.maxDistance = 60;

  const keyLight = new THREE.DirectionalLight(0xffdcb0, 3.2);
  keyLight.position.set(4, 6, 5);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(1024, 1024);
  keyLight.shadow.bias = -0.0005;
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0x9fbfff, 0.9);
  fillLight.position.set(-5, 2, -4);
  scene.add(fillLight);

  const hemiLight = new THREE.HemisphereLight(0x3a352e, 0x0a0908, 0.6);
  scene.add(hemiLight);

  const shadowPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(60, 60),
    new THREE.ShadowMaterial({ opacity: 0.35 })
  );
  shadowPlane.rotation.x = -Math.PI / 2;
  shadowPlane.receiveShadow = true;
  scene.add(shadowPlane);

  let moleculeGroup = null;
  let currentAtoms = null;
  let currentBonds = null;
  let currentMode = "ball-stick";
  let running = true;

  let reactionGroup = null;
  let reactionFrameHandle = null;

  let dockingGroup = null;
  const PROTEIN_TUBE_COLOR = 0x7a6a52;
  const PROTEIN_TUBE_RADIUS = 0.7;

  let trajectoryGroup = null;
  let trajectoryFrameHandle = null;

  function resize() {
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (width === 0 || height === 0) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  function animate() {
    if (!running) return;
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }

  function buildMolecule(atoms, bonds, mode) {
    const group = new THREE.Group();
    const positions = atoms.map((atom) => new THREE.Vector3(atom.x, atom.y, atom.z));
    const isSpaceFilling = mode === "space-filling";

    for (let i = 0; i < atoms.length; i++) {
      const style = styleFor(atoms[i].element);
      const radius = isSpaceFilling ? style.vdw : style.radius;
      const color = mode === "charge" ? colorForCharge(atoms[i].charge ?? 0) : style.color;

      const geometry = new THREE.SphereGeometry(radius, 32, 32);
      const material = new THREE.MeshPhysicalMaterial({
        color,
        roughness: 0.28,
        metalness: 0.05,
        clearcoat: 0.6,
        clearcoatRoughness: 0.25,
      });
      const sphere = new THREE.Mesh(geometry, material);
      sphere.position.copy(positions[i]);
      sphere.castShadow = true;
      sphere.receiveShadow = true;
      group.add(sphere);
    }

    if (!isSpaceFilling) {
      const bondMaterial = new THREE.MeshPhysicalMaterial({
        color: BOND_COLOR,
        roughness: 0.4,
        metalness: 0.1,
        clearcoat: 0.3,
      });

      for (const bond of bonds) {
        const start = positions[bond.a];
        const end = positions[bond.b];
        const mid = start.clone().add(end).multiplyScalar(0.5);
        const direction = end.clone().sub(start);
        const length = direction.length();

        const geometry = new THREE.CylinderGeometry(BOND_RADIUS, BOND_RADIUS, length, 12);
        const cylinder = new THREE.Mesh(geometry, bondMaterial);
        cylinder.position.copy(mid);
        cylinder.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
        cylinder.castShadow = true;
        cylinder.receiveShadow = true;
        group.add(cylinder);
      }
    }

    return group;
  }

  function frameBox(box) {
    const sphere = new THREE.Sphere();
    box.getBoundingSphere(sphere);

    const radius = Math.max(sphere.radius, 1.5);
    const distance = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.35;

    camera.position.set(
      sphere.center.x + distance * 0.6,
      sphere.center.y + distance * 0.45,
      sphere.center.z + distance * 0.7
    );
    camera.near = distance / 100;
    camera.far = distance * 20;
    camera.updateProjectionMatrix();

    controls.target.copy(sphere.center);
    controls.update();

    shadowPlane.position.y = box.min.y - 0.05;
  }

  function fitCameraToObject(group) {
    frameBox(new THREE.Box3().setFromObject(group));
  }

  function clearReaction() {
    if (reactionFrameHandle !== null) {
      cancelAnimationFrame(reactionFrameHandle);
      reactionFrameHandle = null;
    }
    if (reactionGroup) {
      scene.remove(reactionGroup);
      reactionGroup = null;
    }
  }

  function clearDocking() {
    if (dockingGroup) {
      scene.remove(dockingGroup);
      dockingGroup = null;
    }
  }

  function clearTrajectory() {
    if (trajectoryFrameHandle !== null) {
      cancelAnimationFrame(trajectoryFrameHandle);
      trajectoryFrameHandle = null;
    }
    if (trajectoryGroup) {
      scene.remove(trajectoryGroup);
      trajectoryGroup = null;
    }
  }

  function rebuild(keepCamera) {
    clearReaction();
    clearDocking();
    clearTrajectory();
    if (moleculeGroup) {
      scene.remove(moleculeGroup);
    }
    if (!currentAtoms) return;
    moleculeGroup = buildMolecule(currentAtoms, currentBonds, currentMode);
    scene.add(moleculeGroup);
    resize();
    if (!keepCamera) {
      fitCameraToObject(moleculeGroup);
    }
  }

  function playReaction(data, durationMs = 3000) {
    clearReaction();
    clearDocking();
    clearTrajectory();
    if (moleculeGroup) {
      scene.remove(moleculeGroup);
      moleculeGroup = null;
    }
    currentAtoms = null;
    currentBonds = null;

    const startAtoms = data.start.atoms;
    const endAtoms = data.end.atoms;
    const endAtomByStartIdx = new Map();
    for (const [startIdx, endIdx] of data.correspondence) {
      endAtomByStartIdx.set(startIdx, endAtoms[endIdx]);
    }

    const group = new THREE.Group();

    const spheres = startAtoms.map((atom) => {
      const style = styleFor(atom.element);
      const geometry = new THREE.SphereGeometry(style.radius, 32, 32);
      const material = new THREE.MeshPhysicalMaterial({
        color: style.color,
        roughness: 0.28,
        metalness: 0.05,
        clearcoat: 0.6,
        clearcoatRoughness: 0.25,
      });
      const sphere = new THREE.Mesh(geometry, material);
      sphere.castShadow = true;
      sphere.receiveShadow = true;
      group.add(sphere);
      return sphere;
    });

    function addBondEntry(pair, kind) {
      const geometry = new THREE.CylinderGeometry(BOND_RADIUS, BOND_RADIUS, 1, 12);
      const material = new THREE.MeshPhysicalMaterial({
        color: BOND_COLOR,
        roughness: 0.4,
        metalness: 0.1,
        clearcoat: 0.3,
        transparent: true,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      group.add(mesh);
      return { mesh, a: pair[0], b: pair[1], kind };
    }

    const bondEntries = [
      ...data.persistent_bonds.map((pair) => addBondEntry(pair, "persistent")),
      ...data.broken_bonds.map((pair) => addBondEntry(pair, "broken")),
      ...data.formed_bonds.map((pair) => addBondEntry(pair, "formed")),
    ];

    function opacityFor(kind, t) {
      if (kind === "broken") return t < 0.5 ? 1 - t / 0.5 : 0;
      if (kind === "formed") return t > 0.5 ? (t - 0.5) / 0.5 : 0;
      return 1;
    }

    function setFrame(t) {
      for (let i = 0; i < startAtoms.length; i++) {
        const start = startAtoms[i];
        const end = endAtomByStartIdx.get(i);
        spheres[i].position.set(
          end ? THREE.MathUtils.lerp(start.x, end.x, t) : start.x,
          end ? THREE.MathUtils.lerp(start.y, end.y, t) : start.y,
          end ? THREE.MathUtils.lerp(start.z, end.z, t) : start.z
        );
      }

      for (const entry of bondEntries) {
        const a = spheres[entry.a].position;
        const b = spheres[entry.b].position;
        const mid = a.clone().add(b).multiplyScalar(0.5);
        const direction = b.clone().sub(a);
        const length = Math.max(direction.length(), 0.0001);

        entry.mesh.position.copy(mid);
        entry.mesh.scale.set(1, length, 1);
        entry.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());

        const opacity = opacityFor(entry.kind, t);
        entry.mesh.material.opacity = opacity;
        entry.mesh.visible = opacity > 0.001;
      }
    }

    scene.add(group);
    reactionGroup = group;
    resize();

    const allPositions = [...startAtoms, ...endAtoms].map(
      (atom) => new THREE.Vector3(atom.x, atom.y, atom.z)
    );
    frameBox(new THREE.Box3().setFromPoints(allPositions));

    setFrame(0);

    const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
    const startTime = performance.now();

    function tick(now) {
      const raw = Math.min(1, (now - startTime) / durationMs);
      setFrame(easeInOutCubic(raw));
      if (raw < 1) {
        reactionFrameHandle = requestAnimationFrame(tick);
      } else {
        reactionFrameHandle = null;
      }
    }
    reactionFrameHandle = requestAnimationFrame(tick);
  }

  function setDockingResult(data) {
    clearReaction();
    clearDocking();
    clearTrajectory();
    if (moleculeGroup) {
      scene.remove(moleculeGroup);
      moleculeGroup = null;
    }
    currentAtoms = null;
    currentBonds = null;

    const group = new THREE.Group();

    const proteinMaterial = new THREE.MeshPhysicalMaterial({
      color: PROTEIN_TUBE_COLOR,
      roughness: 0.8,
      metalness: 0,
      clearcoat: 0,
    });

    for (const chain of data.chains) {
      if (chain.length < 2) continue;
      const points = chain.map((p) => new THREE.Vector3(p.x, p.y, p.z));
      const curve = new THREE.CatmullRomCurve3(points);
      const tubularSegments = Math.max(points.length * 4, 8);
      const geometry = new THREE.TubeGeometry(curve, tubularSegments, PROTEIN_TUBE_RADIUS, 8, false);
      const tube = new THREE.Mesh(geometry, proteinMaterial);
      tube.castShadow = true;
      tube.receiveShadow = true;
      group.add(tube);
    }

    const ligandGroup = buildMolecule(data.ligand.atoms, data.ligand.bonds, "ball-stick");
    group.add(ligandGroup);

    if (data.pocket_center && data.pocket_size) {
      const boxGeometry = new THREE.BoxGeometry(
        data.pocket_size.x,
        data.pocket_size.y,
        data.pocket_size.z
      );
      const boxEdges = new THREE.EdgesGeometry(boxGeometry);
      const boxLines = new THREE.LineSegments(
        boxEdges,
        new THREE.LineBasicMaterial({ color: 0xe0965a, transparent: true, opacity: 0.35 })
      );
      boxLines.position.set(data.pocket_center.x, data.pocket_center.y, data.pocket_center.z);
      group.add(boxLines);
    }

    scene.add(group);
    dockingGroup = group;
    resize();

    const allPositions = [];
    for (const chain of data.chains) {
      for (const p of chain) allPositions.push(new THREE.Vector3(p.x, p.y, p.z));
    }
    for (const atom of data.ligand.atoms) {
      allPositions.push(new THREE.Vector3(atom.x, atom.y, atom.z));
    }
    frameBox(new THREE.Box3().setFromPoints(allPositions));
  }

  const TRAJECTORY_FRAME_INTERVAL_MS = 40; // ~25fps Wiedergabe

  function playTrajectory(data) {
    clearReaction();
    clearDocking();
    clearTrajectory();
    if (moleculeGroup) {
      scene.remove(moleculeGroup);
      moleculeGroup = null;
    }
    currentAtoms = null;
    currentBonds = null;

    const elements = data.elements;
    const frames = data.frames;

    const group = new THREE.Group();

    const spheres = elements.map((element) => {
      const style = styleFor(element);
      const geometry = new THREE.SphereGeometry(style.radius, 24, 24);
      const material = new THREE.MeshPhysicalMaterial({
        color: style.color,
        roughness: 0.28,
        metalness: 0.05,
        clearcoat: 0.6,
        clearcoatRoughness: 0.25,
      });
      const sphere = new THREE.Mesh(geometry, material);
      sphere.castShadow = true;
      sphere.receiveShadow = true;
      group.add(sphere);
      return sphere;
    });

    const bondMaterial = new THREE.MeshPhysicalMaterial({
      color: BOND_COLOR,
      roughness: 0.4,
      metalness: 0.1,
      clearcoat: 0.3,
    });

    const bondEntries = data.bonds.map((bond) => {
      const geometry = new THREE.CylinderGeometry(BOND_RADIUS, BOND_RADIUS, 1, 10);
      const mesh = new THREE.Mesh(geometry, bondMaterial);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      group.add(mesh);
      return { mesh, a: bond.a, b: bond.b };
    });

    function setFrame(frameIndex) {
      const frame = frames[frameIndex];
      for (let i = 0; i < frame.length; i++) {
        spheres[i].position.set(frame[i].x, frame[i].y, frame[i].z);
      }
      for (const entry of bondEntries) {
        const a = spheres[entry.a].position;
        const b = spheres[entry.b].position;
        const mid = a.clone().add(b).multiplyScalar(0.5);
        const direction = b.clone().sub(a);
        const length = Math.max(direction.length(), 0.0001);
        entry.mesh.position.copy(mid);
        entry.mesh.scale.set(1, length, 1);
        entry.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
      }
    }

    scene.add(group);
    trajectoryGroup = group;
    resize();

    setFrame(0);
    const box = new THREE.Box3().setFromObject(group);
    box.expandByScalar(1.5);
    frameBox(box);

    let frameIndex = 0;
    let direction = 1;
    let lastTime = performance.now();

    function tick(now) {
      if (now - lastTime >= TRAJECTORY_FRAME_INTERVAL_MS) {
        lastTime = now;
        frameIndex += direction;
        if (frameIndex >= frames.length - 1) {
          frameIndex = frames.length - 1;
          direction = -1;
        } else if (frameIndex <= 0) {
          frameIndex = 0;
          direction = 1;
        }
        setFrame(frameIndex);
      }
      trajectoryFrameHandle = requestAnimationFrame(tick);
    }
    trajectoryFrameHandle = requestAnimationFrame(tick);
  }

  resize();
  animate();
  window.addEventListener("resize", resize);

  return {
    setMolecule(atoms, bonds) {
      currentAtoms = atoms;
      currentBonds = bonds;
      rebuild(false);
    },
    setMode(mode) {
      currentMode = mode;
      rebuild(true);
    },
    playReaction,
    setDockingResult,
    playTrajectory,
    resize() {
      resize();
      if (moleculeGroup) fitCameraToObject(moleculeGroup);
      if (reactionGroup) resize();
      if (dockingGroup) resize();
      if (trajectoryGroup) resize();
    },
    dispose() {
      running = false;
      clearReaction();
      clearDocking();
      clearTrajectory();
      window.removeEventListener("resize", resize);
      renderer.dispose();
      container.innerHTML = "";
    },
  };
}
