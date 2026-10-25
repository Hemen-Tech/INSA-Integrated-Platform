# Probe

> **Put your idea under pressure.**
> Real-world research discovery, living evidence graphs, and authentic product testing.

Probe is a cross-source research search engine and validation system. It challenges product assumptions by retrieving semantically relevant, source-backed discussions from **Reddit**, **X**, **LinkedIn**, and academic papers from **ScholarXIV**, alongside authentic user testing sessions on real products like **[links.et](https://links.et/)**.

---

## Architecture Overview

```text
probe/
├── apps/
│   ├── web/                         # Probe frontend
│   │   ├── src/
│   │   │   ├── app/                # routing, providers, global layout
│   │   │   ├── features/
│   │   │   │   ├── research/       # Cross-source research engine & workspace
│   │   │   │   ├── evidence/       # React Flow living evidence graph
│   │   │   │   ├── testing/        # Real product usability testing
│   │   │   │   ├── voice/          # Voice synthesis/playback interfaces
│   │   │   │   └── workspace/      # Idea challenge & signal review
│   │   │   ├── components/          # Truly shared UI only (PillNav, TechText, Icons)
│   │   │   ├── lib/                 # Frontend infrastructure & utilities
│   │   │   ├── hooks/               # Core React hooks
│   │   │   ├── styles/              # Global Tailwind styles
│   │   │   └── main.tsx
│   │   ├── public/
│   │   └── package.json
│   │
│   └── api/                         # Backend / API
│       ├── src/
│       │   ├── modules/
│       │   │   ├── research/       # Query parsing, expansion & retrieval
│       │   │   ├── evidence/       # Graph layout & synthesis
│       │   │   ├── testing/        # Session capture & analysis
│       │   │   ├── voice/          # Voice processing
│       │   │   └── workspace/      # Workspace orchestration
│       │   ├── providers/
│       │   │   ├── searxng/        # Multi-engine search provider
│       │   │   ├── scholarxiv/     # arXiv and semantic scholar gateway
│       │   │   ├── gemini/         # Query understanding & reranking
│       │   │   └── browser/        # Headless testing runner
│       │   ├── lib/                 # Server utilities & cache
│       │   ├── middleware/          # Rate limiting, validation & CORS
│       │   └── server.ts
│       └── package.json
│
├── packages/
│   ├── shared/                      # Shared types/contracts
│   ├── ui/                          # Shared design-system components
│   ├── schemas/                     # Zod/API schemas
│   └── config/                      # ESLint, tsconfig, etc.
│
├── tests/
│   ├── integration/                 # Search engine integration tests
│   └── fixtures/                    # Test query sets & response payloads
│
├── docs/
│   ├── architecture/                # System diagrams & data flow
│   ├── decisions/                   # Architecture Decision Records (ADRs)
│   └── api/                         # REST & WebSocket specifications
│
├── .github/
│   └── workflows/                   # GitHub Actions CI/CD
├── .env.example
├── CONTRIBUTING.md
├── README.md
├── package.json
└── pnpm-workspace.yaml
```

---

## Quickstart

```bash
# Clone repository
git clone https://github.com/yab-g4u/Novarion.git
cd Novarion

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

---

## INSA platform destinations (Phase 1)

PROBE remains the central interface. Drought Intelligence and PNIS continue to run as independent applications; the links between them are navigation only, with no shared authentication, database, or live data exchange.

Start each application in its own terminal:

| Application | Start command | Local URL |
| --- | --- | --- |
| PROBE | From `Novarion/`, run `bun .\server.ts` (or `npm run dev` when Node and the `tsx` loader are available) | `http://localhost:3000/` |
| Drought Intelligence | From `frontend11/front_end/`, run `py -3.14 -m http.server 5501` | `http://localhost:5501/` |
| PNIS — Preview — In Development | From `PNIS/`, run `.\.venv\Scripts\python.exe -m streamlit run .\pnis_dashboard\app.py --server.port 8503` | `http://localhost:8503/` |

The Drought Intelligence command uses Python's built-in static server and does not install packages. The configured VS Code Live Server port is also 5501; if using Live Server with a different document root, adjust its destination URL below. The integrated PNIS destination is the existing nested `pnis_dashboard/app.py`; the separate root `PNIS/app.py` is not used as the platform destination. `bun .\server.ts` runs PROBE with the installed Bun runtime; the standard `npm run dev` command requires the `tsx` loader in the Node dependency tree.

PROBE's links are public frontend configuration. Set these in `Novarion/.env.local` and restart the dev server to override the local defaults:

```dotenv
VITE_DROUGHT_INTELLIGENCE_URL=http://localhost:5501/
VITE_PNIS_URL=http://localhost:8503/
```

PROBE's landing header and workspace sidebar provide links to both modules; the workspace sidebar also links back to the PROBE landing page. Drought Intelligence keeps its existing translated **Back to PROBE** link and adds module links in its existing sidebar. Its local URLs are configured in `frontend11/front_end/js/platform-config.js`; an embedding page can set `window.INSA_PLATFORM_CONFIG` before loading that script to override `probeUrl`, `droughtUrl`, or `pnisUrl`. The PNIS sidebar links back to PROBE and to Drought Intelligence; its URLs can be configured with `PROBE_URL` and `DROUGHT_URL`.

The Drought Intelligence dashboard and forecast show a translated notice that their metrics and generated forecast outputs are simulated, not validated live predictions. Its chatbot uses an external AI provider. PNIS uses the existing local project artifacts; calculated graph paths do not verify road conditions or grant dispatch approval.

---

## Core Capabilities

1. **Cross-Source Retrieval Pipeline**:
   - Searches Reddit, X, LinkedIn, and ScholarXIV in parallel.
   - Normalizes citations, handles rate limits gracefully, and prevents AI hallucination.
2. **Living Evidence Graph**:
   - Memoized `@xyflow/react` node layout with dynamic ELK hierarchy.
   - Categorizes evidence into Supporting, Contradicting, and Unknown blind spots.
3. **Real Product Usability Testing**:
   - Test live products (e.g. `https://links.et/`) against concrete tasks.
   - Captures genuine user friction and generates agentic graphic diagnostic reports.
