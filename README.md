# Neuropharm Simulation Lab

The **Neuropharm Simulation Lab** is an interactive sandbox for exploring the
neurobiological mechanisms of antidepressants and related neuromodulators.
It combines a Python backend built with [FastAPI](https://fastapi.tiangolo.com/)
and a lightweight HTML/JavaScript frontend to visualise how different
serotonin receptor subtypes, dopamine and glutamate pathways and phenotypic
modifiers (such as ADHD and gut–brain signalling) influence motivational
states.

This repository grew out of a series of discussions around
biologically‑plausible models of SSRIs, atypical antidepressants, and
adjunct therapies.  The backend exposes a `/simulate` endpoint that
takes receptor occupancy and mechanism settings and returns synthetic
scores for drive, apathy, motivation, cognitive flexibility, anxiety
and sleep quality, along with citations supporting the simulated
mechanisms.  The frontend provides interactive sliders, toggles and
visualisations (bar charts and a 3D brain network rendered with
Three.js) to explore the model in real time.

## Project structure

```
neuropharm-sim-lab/
├── backend
│   ├── engine/          # definitions of receptors, weights and helper functions
│   │   ├── __init__.py
│   │   └── receptors.py
│   ├── main.py          # FastAPI app exposing the simulation endpoint
│   ├── requirements.txt # Python dependencies
│   └── refs.json        # citation database for each receptor
├── frontend
│   ├── index.html       # main page containing controls and visualisations
│   ├── script.js        # browser logic for calling the API and rendering charts/3D
│   └── styles.css       # styling for the UI
├── .devcontainer
│   └── devcontainer.json # Codespaces/Dev Containers setup
├── .github
│   └── workflows
│       └── deploy-frontend.yml # GitHub Actions workflow for Pages deployment
└── README.md
```

## Quick start for everyone

The project ships as two parts: a Python API and a static web page. You
can run both on a laptop/desktop and view the UI either on that machine
or on a phone/tablet that is on the same Wi‑Fi network.

### A. Desktop or laptop setup (Windows, macOS, Linux)

1. **Install Python 3.9 or newer.**
   * Windows/macOS: download from [python.org](https://www.python.org/downloads/).
   * Linux: use your package manager (`sudo apt install python3 python3-pip`).

2. **Download the code.** Either clone via Git or grab the ZIP.

   ```bash
   git clone https://github.com/your-user/neuropharm-sim-lab.git
   cd neuropharm-sim-lab
   ```

   _No Git?_
   * Click the green **Code** button on GitHub → **Download ZIP**.
   * Extract it and open a terminal inside the new folder.

3. **Install the backend dependencies.**

   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. **Start the API server.**

   ```bash
   uvicorn main:app --reload
   ```

   Leave this terminal open. The API runs at `http://127.0.0.1:8000` and
   exposes live docs at `http://127.0.0.1:8000/docs`.

5. **Open a second terminal for the frontend.**

   ```bash
   cd ..  # back to the project root
   python -m http.server 8080
   ```

6. **Visit the app.**
   * On the same computer: open `http://localhost:8080/frontend/index.html`.
   * Adjust sliders/toggles, then press **Run simulation** to view scores and citations.

### B. Viewing on a phone or tablet (same network)

1. Keep both servers running on your computer (steps A4–A5).
2. Find your computer’s local IP address:
   * Windows: run `ipconfig` and look for `IPv4 Address`.
   * macOS/Linux: run `ip addr` (look for `inet 192.168.x.x`).
3. On your mobile device, open a browser and visit:

   ```
   http://<your-computer-ip>:8080/frontend/index.html
   ```

4. The page will use the same backend through your network. Tap the
   controls and run simulations as if you were on the desktop.

If it doesn’t load, ensure your firewall allows local connections or use
the Swagger UI on the computer to verify the API is running.

## Deploying

### GitHub Pages (frontend)

This repository includes a GitHub Actions workflow that publishes the
contents of the `frontend/` directory to the `gh-pages` branch on every push to
`main`.  To enable GitHub Pages for your fork:

1. Go to **Settings → Pages** in your repository.
2. Under **Build and deployment**, select **GitHub Actions** as the
   source.
3. After pushing to `main` the first time, the workflow will build and
   deploy the frontend.  The site will be available at
   `https://<your-username>.github.io/<repository-name>/index.html`.

### Backend hosting (Render, Fly.io, etc.)

The backend is a standard FastAPI application, so you can deploy it on
any service that supports ASGI apps.  One simple option is
[Render.com](https://render.com/): create a new **Web Service**, point
it at your GitHub repo, choose a Python environment and set the start
command to:

```
uvicorn backend.main:app --host 0.0.0.0 --port 10000
```

Render will build and run the API.  Make a note of the URL it assigns
to the service (e.g. `https://my-neuropharm-api.onrender.com`).  Then
set the `VITE_API_URL` environment variable or adjust the `script.js`
fetch code accordingly.

## Extending the model

The simulation logic lives in `backend/engine/receptors.py` and in the
calculation functions in `backend/main.py`.  Each receptor is defined
with a set of weights for different outcome metrics (drive, apathy,
motivation, cognitive flexibility, anxiety and sleep quality) and a
short description.  Mechanism factors for agonists, antagonists,
partial agonists and inverse agonists are defined as multipliers.  To
add a new receptor, simply insert a new entry into the `RECEPTORS`
dictionary with appropriate weights and description.  The citations
database in `refs.json` should also be updated with references for the
new receptor.

If you wish to introduce additional phenotypic modifiers or complex
pharmacokinetic/pharmacodynamic models, consider building new helper
functions in `engine/` and exposing additional parameters in the
`SimInput` model in `main.py`.  The frontend can then be updated to
include UI controls for these parameters.

## A note on citations

Each receptor in `refs.json` maps to one or more references from the
scientific literature.  These are provided as examples only.  In a
production system you would curate a richer set of references and
update them regularly.  When the simulation is run, the API returns
which receptors were involved and their associated references, which
the frontend displays.

## License

This project is released under the MIT License.  See the `LICENSE`
file for details.
