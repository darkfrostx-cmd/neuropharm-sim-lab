/*
 * Front-end logic for the Neuropharm Simulation Lab. This script wires up
 * interactive controls for receptor occupancy and mechanism, phenotype
 * toggles, and PVT weight. It sends a POST request to the FastAPI backend
 * to compute simulation scores and citations, renders the results via
 * Plotly, and displays citations. It also draws a simple 3D brain network
 * using Three.js. The network is static but could be extended to show
 * dynamic changes based on simulation results.
 */

// Base URL for the API. When running locally, the backend listens on
// localhost:8000. In production, this may be replaced by a configured
// environment variable or relative path.
const API_BASE = 'http://localhost:8000';

// Once DOM is loaded, attach handlers and initialize the 3D scene
document.addEventListener('DOMContentLoaded', () => {
  // Set up event listener on Run Simulation button
  const runButton = document.getElementById('runButton');
  runButton.addEventListener('click', async () => {
    runButton.disabled = true;
    runButton.textContent = 'Running...';
    try {
      await runSimulation();
    } catch (err) {
      console.error(err);
      alert('Simulation failed. See console for details.');
    } finally {
      runButton.disabled = false;
      runButton.textContent = 'Run Simulation';
    }
  });

  // Initialize the 3D brain network
  initThree();
});

/**
 * Gather input values from the receptor controls, phenotype toggles and PVT
 * weight slider, send them to the backend, and update the UI with the
 * results.
 */
async function runSimulation() {
  // Build the receptors object
  const receptors = {};
  document.querySelectorAll('.receptor').forEach(div => {
    const key = div.getAttribute('data-receptor');
    const occ = parseFloat(div.querySelector('.occ-slider').value);
    const mech = div.querySelector('.mech-select').value;
    receptors[key] = { occ: occ, mech: mech };
  });
  // Phenotype toggles
  const adhd = document.getElementById('adhdToggle').checked;
  const acute = document.getElementById('acuteToggle').checked;
  const gut = document.getElementById('gutToggle').checked;
  const pvtWeight = parseFloat(document.getElementById('pvtWeight').value);

  const payload = {
    receptors: receptors,
    adhd: adhd,
    acute_1a: acute,
    gut_bias: gut,
    pvt_weight: pvtWeight
  };
  // Call the backend
  const response = await fetch(`${API_BASE}/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`API responded with status ${response.status}`);
  }
  const result = await response.json();
  // Update the chart
  renderChart(result.scores);
  // Display citations
  renderCitations(result.citations);
}

/**
 * Render the simulation scores as a bar chart using Plotly. Expects an
 * object of the form { metricName: value, ... }.
 * @param {Object} scores
 */
function renderChart(scores) {
  const metrics = Object.keys(scores);
  const values = metrics.map(m => scores[m]);
  const data = [
    {
      x: metrics,
      y: values,
      type: 'bar',
      text: values.map(v => v.toFixed(1)),
      textposition: 'auto'
    }
  ];
  const layout = {
    title: 'Simulation Metrics',
    yaxis: { title: 'Score (0–100)', range: [0, 100] },
    xaxis: { title: 'Metric' },
    margin: { t: 40, r: 20, b: 60, l: 50 },
    plot_bgcolor: '#fafafa',
    paper_bgcolor: '#fafafa'
  };
  Plotly.newPlot('chart', data, layout, { displayModeBar: false });
}

/**
 * Render citations returned from the backend. Expects an object mapping
 * receptor names to arrays of citation objects with title, pmid and doi.
 * @param {Object} citations
 */
function renderCitations(citations) {
  const container = document.getElementById('citations');
  container.innerHTML = '';
  const keys = Object.keys(citations || {});
  if (keys.length === 0) {
    container.textContent = 'No citations available.';
    return;
  }
  const fragment = document.createDocumentFragment();
  keys.forEach(key => {
    const list = document.createElement('ul');
    list.classList.add('citation-list');
    const heading = document.createElement('h3');
    heading.textContent = `${key} References`;
    fragment.appendChild(heading);
    citations[key].forEach(ref => {
      const item = document.createElement('li');
      const anchor = document.createElement('a');
      anchor.href = ref.doi ? `https://doi.org/${ref.doi}` : '#';
      anchor.target = '_blank';
      anchor.rel = 'noopener noreferrer';
      anchor.textContent = ref.title;
      item.appendChild(anchor);
      list.appendChild(item);
    });
    fragment.appendChild(list);
  });
  container.appendChild(fragment);
}

// 3D Visualisation using Three.js
let scene, camera, renderer, controls;

/**
 * Set up the Three.js scene, camera, renderer, brain region spheres
 * and connecting lines. This function runs once on page load. The
 * network is static, but you can extend it to visualise simulation
 * results by updating node colours or sizes.
 */
function initThree() {
  const container = document.getElementById('threeContainer');
  const width = container.clientWidth;
  const height = container.clientHeight;
  // Create scene and camera
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
  camera.position.set(0, 0, 120);
  // Renderer
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(width, height);
  container.appendChild(renderer.domElement);
  // Orbit controls
  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  // Define brain regions and positions (approximate)
  const regions = {
    DRN: { x: 0, y: 60, z: -30, color: 0x3B82F6 },
    VTA: { x: -20, y: 40, z: -20, color: 0x10B981 },
    NAc: { x: 0, y: 0, z: 40, color: 0xF59E0B },
    mPFC: { x: 0, y: -40, z: 60, color: 0x8B5CF6 },
    vHipp: { x: 40, y: 20, z: 0, color: 0xEC4899 },
    BLA: { x: -40, y: 20, z: 0, color: 0xEF4444 },
    PVT: { x: 0, y: 30, z: 0, color: 0x06B6D4 },
    OFC: { x: -20, y: -30, z: 50, color: 0x84CC16 },
    ACC: { x: 20, y: -30, z: 50, color: 0xF97316 }
  };
  // Create spheres for each region
  const regionMeshes = {};
  const sphereGeo = new THREE.SphereGeometry(4, 16, 16);
  for (const key in regions) {
    const { x, y, z, color } = regions[key];
    const material = new THREE.MeshStandardMaterial({ color });
    const sphere = new THREE.Mesh(sphereGeo, material);
    sphere.position.set(x, y, z);
    scene.add(sphere);
    regionMeshes[key] = sphere;
    // Add label sprite
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    ctx.font = '12px Arial';
    const textWidth = ctx.measureText(key).width;
    canvas.width = textWidth + 8;
    canvas.height = 20;
    // draw white background for better visibility
    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#1f2937';
    ctx.fillText(key, 4, 14);
    const texture = new THREE.CanvasTexture(canvas);
    const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
    const sprite = new THREE.Sprite(spriteMaterial);
    sprite.scale.set(canvas.width * 0.1, canvas.height * 0.1, 1);
    sprite.position.set(x, y + 6, z);
    scene.add(sprite);
  }
  // Lighting
  const ambient = new THREE.AmbientLight(0xffffff, 0.8);
  scene.add(ambient);
  const directional = new THREE.DirectionalLight(0xffffff, 0.5);
  directional.position.set(50, 100, 100);
  scene.add(directional);
  // Connections between regions (draw as lines)
  const edges = [
    ['DRN', 'VTA'], ['DRN', 'NAc'], ['DRN', 'mPFC'], ['DRN', 'vHipp'],
    ['DRN', 'BLA'], ['DRN', 'PVT'], ['DRN', 'OFC'], ['DRN', 'ACC'],
    ['VTA', 'NAc'], ['NAc', 'mPFC'], ['NAc', 'vHipp'], ['BLA', 'NAc'],
    ['PVT', 'NAc'], ['OFC', 'NAc'], ['ACC', 'NAc'],
    ['vHipp', 'mPFC'], ['BLA', 'mPFC'], ['OFC', 'mPFC'], ['ACC', 'mPFC']
  ];
  const materialLine = new THREE.LineBasicMaterial({ color: 0x94A3B8 });
  edges.forEach(([a, b]) => {
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array([
      regions[a].x, regions[a].y, regions[a].z,
      regions[b].x, regions[b].y, regions[b].z
    ]);
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const line = new THREE.Line(geometry, materialLine);
    scene.add(line);
  });
  // Animation loop
  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}
