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

## Running locally

1. **Clone this repository** and navigate into it:

   ```bash
   git clone https://github.com/your-user/neuropharm-sim-lab.git
   cd neuropharm-sim-lab
   ```

2. **Install backend dependencies** (requires Python ≥3.9):

   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Start the API** with Uvicorn:

   ```bash
   uvicorn main:app --reload
   ```

   By default the API runs on `http://127.0.0.1:8000`.  You can browse
   auto‑generated Swagger documentation at `http://127.0.0.1:8000/docs`.

4. **Serve the frontend**.  The simplest way is to run a tiny HTTP server
   from the project root.  Python provides one out of the box:

   ```bash
   # from the project root
   python -m http.server 8080
   ```

   Then navigate to `http://localhost:8080/frontend/index.html` in your browser.

   The page will allow you to move sliders and toggles to set receptor
   occupancy and mechanisms, choose phenotypic modifiers (ADHD, gut
   bias, acute 5‑HT1A modulation and PVT weighting) and click **Run
   simulation** to fetch results from the backend.  A bar chart will
   display the synthetic scores and a list of citations will appear below.

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
