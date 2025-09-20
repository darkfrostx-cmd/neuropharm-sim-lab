# Neuropharm Simulation Lab Frontend

This directory contains the Vite-powered React cockpit used by Neuropharm Simulation Lab.

## Development

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Set `VITE_API_BASE_URL` in `.env.local` if the API is hosted on a different origin.

## Tests

Run the vitest unit smoke checks and Playwright E2E flow with:

```bash
npm test -- --watch=false
```

During Playwright runs the heavy NiiVue canvas is disabled automatically to avoid WebGL flakiness. The production build retains the atlas experience.
