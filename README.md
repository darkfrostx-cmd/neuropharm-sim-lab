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

Follow this numbered quick-start to see the simulator running on your own
computer. Each step is written in plain language, and we have included
call-outs for screenshots you can capture or replace later.

1. **Prepare your computer**

   * Install [Python 3.9 or newer](https://www.python.org/downloads/) with
     the "Add Python to PATH" option enabled on Windows.
   * Install [Git](https://git-scm.com/downloads) so you can download the
     project (or plan to use the green **Code → Download ZIP** button on
     GitHub).
   * Make sure you have a modern web browser such as Chrome, Edge, Firefox,
     or Safari.
   * Verify your setup by opening a terminal (Command Prompt on Windows,
     Terminal on macOS/Linux) and running `python --version`.

   > 📸 **Screenshot placeholder:** Capture the Python installer or the
   > terminal showing a successful `python --version` check.

2. **Get the project files**

   * Open a terminal and choose a folder where you want the project to
     live.
   * Run:

     ```bash
     git clone https://github.com/your-user/neuropharm-sim-lab.git
     cd neuropharm-sim-lab
     ```

     If you downloaded the ZIP instead, unzip it and open the folder in
     your file explorer.

   > 📸 **Screenshot placeholder:** Show the project folder visible in your
   > file explorer or terminal after cloning/extracting.

3. **Start the backend (the data engine)**

   * In the terminal, move into the backend folder and install the
     dependencies:

     ```bash
     cd backend
     pip install -r requirements.txt
     ```

   * Start the FastAPI server:

     ```bash
     uvicorn main:app --reload
     ```

     Keep this terminal window open. When you see "Uvicorn running on
     http://127.0.0.1:8000", the backend is ready. Visit
     `http://127.0.0.1:8000/docs` in a browser tab if you want to see the
     interactive API documentation.

   > 📸 **Screenshot placeholder:** Terminal window showing the Uvicorn
   > startup message.

4. **Point the frontend at your local backend**

   * The frontend defaults to the hosted demo API. Open
     `frontend/script.js` in any text editor (Notepad, VS Code, TextEdit) and
     update the top line so it reads:

     ```javascript
     const API_BASE = 'http://127.0.0.1:8000';
     ```

   * Save the file. This change tells the web page to talk to the backend
     you just started.

   > 📸 **Screenshot placeholder:** Text editor showing the updated
   > `API_BASE` line.

5. **Launch the frontend control panel**

   * Open a second terminal window so the backend can keep running in the
     first one.
   * Go to the project’s root folder (the one that contains both `backend`
     and `frontend`) and run:

     ```bash
     cd path/to/neuropharm-sim-lab
     python -m http.server 8080
     ```

     Leave this window open as well. It shares the frontend files at
     `http://localhost:8080`.
   * Open your browser and navigate to
     `http://localhost:8080/frontend/index.html`. You should now be able to
     move the sliders, choose modifiers, and click **Run simulation** to see
     the charts update.

   > 📸 **Screenshot placeholder:** Browser window showing the simulator
   > page with sliders and the chart.

### Use the simulator from another device on your network

Sometimes you want to explore the simulator from a tablet or phone while the
servers run on your computer. Follow these steps:

1. **Find your computer’s local IP address.**
   * Windows: open Command Prompt and run `ipconfig`, then look for the
     `IPv4 Address` in the section for your active Wi‑Fi/Ethernet adapter.
   * macOS: open Terminal and run `ipconfig getifaddr en0` (Wi‑Fi) or
     `ipconfig getifaddr en1` (Ethernet). If those do not work, run
     `ifconfig` and find the `inet` value under `en0`/`en1`.
   * Linux: run `hostname -I` or `ip addr` and pick the address that looks
     like `192.168.x.x` or `10.x.x.x`.

2. **Restart the servers so they listen on your network.**
   * Stop the backend with `Ctrl+C`, then run:

     ```bash
     uvicorn main:app --host 0.0.0.0 --port 8000
     ```

   * Stop the frontend server window with `Ctrl+C`, then run from the project
     root:

     ```bash
     python -m http.server 8080 --bind 0.0.0.0
     ```

3. **Update the frontend API setting.** Edit `frontend/script.js` again so the
   line reads:

   ```javascript
   const API_BASE = 'http://<your-ip-address>:8000';
   ```

   Replace `<your-ip-address>` with the value you found in step 1 (for example,
   `http://192.168.1.24:8000`). Save the file.

4. **Connect from the other device.** Make sure the device is on the same
   Wi‑Fi/network as your computer. Open its browser and visit
   `http://<your-ip-address>:8080/frontend/index.html`. Mobile browsers may
   show a warning about an "insecure" connection; choose **Proceed** if
   prompted.

### Troubleshooting and shutting everything down

* **Firewall pop-ups:** Allow Python to communicate on private networks when
  Windows or macOS asks for permission. If you accidentally blocked it, open
  your firewall settings and enable inbound connections for Python on ports
  8000 and 8080.
* **Port already in use:** If another application is using port 8000 or 8080,
  pick different numbers (for example 9000 and 9090) when starting Uvicorn and
  the HTTP server. Update `API_BASE` and the browser URL to match.
* **Browser cannot reach the backend:** Double-check that both terminal windows
  are still running and that `API_BASE` matches the server address exactly.
  Refresh the page after saving any changes.
* **Stopping the servers:** Press `Ctrl+C` in each terminal window when you are
  finished. On macOS you can also press `⌘ + .` in the Terminal app. Once the
  prompts return, both servers are fully stopped.

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
