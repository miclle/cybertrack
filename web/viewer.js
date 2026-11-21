import {
  Box3, DirectionalLight, DoubleSide, HemisphereLight, Matrix3, Matrix4,
  MeshStandardMaterial, OrthographicCamera, Raycaster, Scene, Vector2, Vector3, WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const byId = id => document.getElementById(id);
const panel = document.querySelector(".viewer");
const host = byId("canvas-holder");
const status = byId("model-status");
const tree = byId("part-tree");
const slider = byId("explosion");
const orientation = byId("orientation");
const selection = byId("selection");

const directions = {
  iso: new Vector3(-0.82, 0.65, 1).normalize(),
  // CAD −Y is glTF +Z. The robot's right side is CAD −X.
  front: new Vector3(0, 0, 1),
  top: new Vector3(0, 1, 0.00001).normalize(),
  right: new Vector3(-1, 0, 0),
};

async function loadModel() {
  const response = await fetch(panel.dataset.model);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const bytes = await response.arrayBuffer();
  // Some static hosts decode the file while applying Content-Encoding.
  const raw = new Uint8Array(bytes)[0] === 0x1f
    ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer()
    : bytes;
  const { scene } = await new GLTFLoader().parseAsync(raw, "");
  return scene.children[0];
}

function installViewer(model, renderer) {
  const camera = new OrthographicCamera(-1, 1, 1, -1, 0.0001, 50);
  const canvas = renderer.domElement;
  canvas.setAttribute("aria-label", "三维装配模型，可拖动旋转");
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  host.append(canvas);

  const controls = new OrbitControls(camera, canvas);
  controls.minZoom = 0.25;
  controls.maxZoom = 30;
  const scene = new Scene();
  scene.add(model, new HemisphereLight(0xf7fbff, 0xb1bbcc, 1.75));
  for (const [position, intensity] of [[[2, 5, 5], 2.1], [[-4, 3, -3], 1.3]]) {
    const light = new DirectionalLight(0xffffff, intensity);
    light.position.set(...position);
    scene.add(light);
  }
  model.updateMatrixWorld(true);

  const parts = new Map();
  const partOfMesh = new Map();
  model.traverse(node => {
    node.visible = node.userData.visible ?? true;
    if (!node.userData.part) return;
    const meshes = [];
    const bounds = new Box3();
    node.traverse(mesh => {
      if (!mesh.isMesh) return;
      mesh.geometry.computeVertexNormals();
      mesh.geometry.computeBoundingBox();
      mesh.material.flatShading = false;
      bounds.union(mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrixWorld));
      partOfMesh.set(mesh, node);
      meshes.push({ mesh, material: mesh.material });
    });
    parts.set(node, {
      meshes, bounds, center: bounds.getCenter(new Vector3()),
      origin: node.position.clone(), offset: new Vector3(),
      worldToParent: new Matrix3().setFromMatrix4(node.parent.matrixWorld.clone().invert()),
    });
  });
  if (!parts.size) throw new Error("模型没有可显示的零件");

  let visible = [];
  let selected = null;
  let frame = 0;
  const highlight = new MeshStandardMaterial({ color: 0xe9632c, roughness: 0.6, side: DoubleSide });
  const raycaster = new Raycaster();
  const pointer = new Vector2();

  function draw() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      renderer.render(scene, camera);
    });
  }

  function select(node) {
    if (selected) {
      for (const { mesh, material } of parts.get(selected).meshes) mesh.material = material;
    }
    selected = node;
    selection.hidden = !node;
    if (node) {
      for (const { mesh, material } of parts.get(node).meshes) {
        if (material.opacity > 0) mesh.material = highlight;
      }
      selection.textContent = node.userData.label;
    }
    draw();
  }

  function explode() {
    const ratio = Number(slider.value) / 100;
    for (const node of visible) {
      const part = parts.get(node);
      node.position.copy(part.origin).addScaledVector(part.offset, ratio);
    }
    byId("amount").value = `${slider.value}%`;
    draw();
  }

  function updateVisibility() {
    visible = [];
    const bounds = new Box3();
    model.traverseVisible(node => {
      if (!parts.has(node)) return;
      visible.push(node);
      bounds.union(parts.get(node).bounds);
    });
    const center = bounds.getCenter(new Vector3());
    const span = bounds.getSize(new Vector3()).length();
    for (const node of visible) {
      const part = parts.get(node);
      part.offset.copy(part.center).sub(center);
      part.offset.multiplyScalar(0.8 + 0.055 * span / Math.max(part.offset.length(), 0.01 * span, 1e-6));
      part.offset.applyMatrix3(part.worldToParent);
    }
    slider.disabled = visible.length < 2;
    byId("fit").disabled = !visible.length;
    if (selected && !visible.includes(selected)) select(null);
    status.hidden = Boolean(visible.length);
    status.textContent = "当前没有可见零件";
    explode();
  }

  function fit(axis = camera.position.clone().sub(controls.target).normalize()) {
    if (!visible.length) return;
    model.updateMatrixWorld(true);
    const world = new Box3();
    for (const node of visible) {
      for (const { mesh } of parts.get(node).meshes) {
        world.union(mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrixWorld));
      }
    }
    world.getCenter(controls.target);
    const distance = Math.max(world.getSize(new Vector3()).length(), 0.001);
    camera.position.copy(controls.target).addScaledVector(axis, distance * 2);
    camera.lookAt(controls.target);
    camera.updateMatrixWorld(true);

    const projected = new Box3();
    const matrix = new Matrix4();
    for (const node of visible) {
      for (const { mesh } of parts.get(node).meshes) {
        matrix.multiplyMatrices(camera.matrixWorldInverse, mesh.matrixWorld);
        projected.union(mesh.geometry.boundingBox.clone().applyMatrix4(matrix));
      }
    }
    const aspect = host.clientWidth / Math.max(host.clientHeight, 1);
    const halfHeight = 1.12 * Math.max(
      Math.abs(projected.min.x) / aspect, Math.abs(projected.max.x) / aspect,
      Math.abs(projected.min.y), Math.abs(projected.max.y), 0.0001,
    );
    camera.left = -halfHeight * aspect;
    camera.right = halfHeight * aspect;
    camera.top = halfHeight;
    camera.bottom = -halfHeight;
    camera.zoom = 1;
    camera.updateProjectionMatrix();
    controls.update();
    draw();
  }

  function row(node) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = node.visible;
    label.append(checkbox, node.userData.label);
    checkbox.addEventListener("change", () => {
      node.visible = checkbox.checked;
      updateVisibility();
    });
    if (parts.has(node)) {
      const part = document.createElement("div");
      part.className = "part";
      part.dataset.label = node.userData.label.toLocaleLowerCase();
      part.append(label);
      return part;
    }
    const group = document.createElement("details");
    const summary = document.createElement("summary");
    group.dataset.label = node.userData.label.toLocaleLowerCase();
    summary.append(label);
    group.append(summary, ...node.children.map(row));
    return group;
  }

  const treeList = tree.querySelector(".parts");
  treeList.replaceChildren(...model.children.map(row));
  const groups = [...treeList.querySelectorAll("details")];
  let openGroups;
  byId("part-filter").addEventListener("input", event => {
    const query = event.target.value.trim().toLocaleLowerCase();
    if (query && !openGroups) openGroups = groups.map(group => group.open);
    function filter(row, matchesParent = false) {
      const match = matchesParent || row.dataset.label.includes(query);
      const children = [...row.children].filter(child => child.dataset.label !== undefined);
      const matchChild = children.map(child => filter(child, match)).some(Boolean);
      row.hidden = !(match || matchChild);
      if (query && row.tagName === "DETAILS") row.open = !row.hidden;
      return !row.hidden;
    }
    const found = [...treeList.children].map(row => filter(row)).some(Boolean);
    if (!query && openGroups) {
      groups.forEach((group, index) => { group.open = openGroups[index]; });
      openGroups = undefined;
    }
    byId("no-parts").hidden = found;
  });

  const treeToggle = byId("tree-toggle");
  function toggleTree(open) {
    tree.hidden = !open;
    treeToggle.setAttribute("aria-expanded", String(open));
    if (!open && tree.contains(document.activeElement)) treeToggle.focus();
  }
  toggleTree(matchMedia("(min-width: 1100px)").matches);
  treeToggle.addEventListener("click", () => toggleTree(tree.hidden));

  let down;
  canvas.addEventListener("pointerdown", event => {
    down = event.isPrimary && event.button === 0 ? [event.clientX, event.clientY] : undefined;
  });
  canvas.addEventListener("pointercancel", () => { down = undefined; });
  canvas.addEventListener("pointerup", event => {
    const origin = down;
    down = undefined;
    if (!origin || Math.hypot(event.clientX - origin[0], event.clientY - origin[1]) > 5) return;
    const rect = canvas.getBoundingClientRect();
    pointer.set(2 * (event.clientX - rect.left) / rect.width - 1, 1 - 2 * (event.clientY - rect.top) / rect.height);
    raycaster.setFromCamera(pointer, camera);
    const targets = visible.flatMap(node => parts.get(node).meshes
      .filter(({ material }) => material.opacity > 0).map(({ mesh }) => mesh));
    const hit = raycaster.intersectObjects(targets, false)[0];
    select(hit ? partOfMesh.get(hit.object) : null);
  });

  controls.addEventListener("change", draw);
  controls.addEventListener("end", () => {
    const direction = camera.position.clone().sub(controls.target).normalize();
    if (orientation.value !== "custom" && direction.distanceTo(directions[orientation.value]) > 0.001) {
      orientation.value = "custom";
    }
  });
  byId("fit").addEventListener("click", () => fit());
  orientation.addEventListener("change", () => fit(directions[orientation.value]));
  slider.addEventListener("input", explode);
  byId("reset").addEventListener("click", () => {
    slider.value = 0;
    explode();
  });
  for (const id of ["orientation", "tree-toggle", "reset"]) byId(id).disabled = false;

  updateVisibility();
  function resize() {
    renderer.setSize(host.clientWidth, host.clientHeight, false);
    fit();
  }
  renderer.setSize(host.clientWidth, host.clientHeight, false);
  fit(directions.iso);
  new ResizeObserver(resize).observe(host);
  canvas.addEventListener("webglcontextlost", event => {
    event.preventDefault();
    status.hidden = false;
    status.textContent = "三维绘图暂时中断。";
  });
  canvas.addEventListener("webglcontextrestored", () => { updateVisibility(); });
}

async function start() {
  let renderer;
  try {
    renderer = new WebGLRenderer({ antialias: true, alpha: true });
  } catch (error) {
    status.textContent = "浏览器无法启动 WebGL 2。可以通过上方链接查看设计说明或 FreeCAD 源档。";
    console.error(error);
    return;
  }
  try {
    const model = await loadModel();
    installViewer(model, renderer);
  } catch (error) {
    renderer.dispose();
    status.hidden = false;
    status.textContent = "模型载入失败。请刷新页面重试，或打开上方的 FreeCAD 源档。";
    console.error(error);
  }
}

start();
