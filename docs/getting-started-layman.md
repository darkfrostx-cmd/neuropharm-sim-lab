# Hands-on guide: run the Neuropharm Simulation Lab like a layperson

This guide assumes you are comfortable typing a few commands but have no
background in pharmacology or Python packaging. Follow the steps in order—you
will see results in a couple of minutes.

## 1. Install the basics

1. [Install Python 3.10 or newer](https://www.python.org/downloads/).
2. Open a terminal (PowerShell on Windows, Terminal on macOS/Linux).
3. Navigate to the folder that contains this project, then run:
   ```bash
   python -m venv .venv
   # macOS/Linux
   source .venv/bin/activate
   # Windows PowerShell
   # .venv\Scripts\Activate.ps1
   pip install -r backend/requirements.txt
   ```
   Activating the virtual environment keeps the project dependencies separate
   from the rest of your system. If you close the terminal later, run the
   `activate` command again before using the project.

## 2. Try the simulation without the web app

1. Still inside the activated environment, run:
   ```bash
   python -m backend.quickstart
   ```
2. The command prints three sections:
   - **Top predicted effects** – a ranked list of behavioural outcomes (e.g.
     motivation, anxiety) with confidence scores.
   - **Receptor inputs** – which receptors were simulated, how strong their graph
     evidence is, and where that evidence came from.
   - **Simulation backends** – which internal models ran (molecular, PK/PD,
     circuit) and whether any fallbacks were needed.
3. Swap to a different preset or add your own receptors:
   ```bash
   python -m backend.quickstart --list-presets
   python -m backend.quickstart --preset sleep_support
   python -m backend.quickstart --receptor 5HT1A=0.7:agonist --receptor 5HT2A=0.2:antagonist
   ```
   Each receptor entry uses the format `NAME=OCCUPANCY:MECHANISM`, where
   occupancy ranges from 0 to 1 and mechanism is one of `agonist`,
   `antagonist`, `partial`, or `inverse`.

## 3. Explore the full API and dashboard (optional)

1. **Launch the backend**
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
   Keep this window running. Open <http://localhost:8000/docs> in a browser to
   poke the API with the auto-generated interface.
2. **Start the dashboard** (in a new terminal tab, with the virtual environment
   activated):
   ```bash
   cd frontend
   npm install
   echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
   npm run dev -- --host 0.0.0.0 --port 5173
   ```
   Visit <http://localhost:5173>. The cockpit lets you drag sliders for receptor
   occupancy, run the simulator, inspect evidence trails, and view atlas
   overlays—no code required.

## 4. Troubleshooting

- **Command not found errors** – confirm the virtual environment is active
  (`source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\Activate.ps1` on
  Windows PowerShell).
- **Port already in use** – another app is using the port. Change the port when
  launching (`uvicorn backend.main:app --port 8001`). Update the frontend `.env`
  file to match.
- **Dependency build errors** – the default requirements avoid heavy optional
  packages. If you want the full mechanistic stack, install `pip install -e
  backend[mechanistic]` and ensure system BLAS/LAPACK libraries are present.

You now have a functioning local copy of the Neuropharm Simulation Lab. When you
are ready to contribute, run the quality checks listed in the main README before
opening a pull request.
