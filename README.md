<!-- Generated from infrastructure/architecture/templates/README.md.in by infrastructure/scripts/generate_architecture.py. Edit the template, not this file. -->

# ArdvarkFood

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=venom&height=180&color=0:111827,100:334155&text=ArdvarkFood&fontColor=ffffff&fontSize=48&fontAlignY=50" width="100%" />
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/TheWildKaden/ArdvarkFood?style=for-the-badge&color=white&label=STARS" />
  <img src="https://img.shields.io/github/forks/TheWildKaden/ArdvarkFood?style=for-the-badge&color=white&label=FORKS" />
  <img src="https://img.shields.io/github/issues/TheWildKaden/ArdvarkFood?style=for-the-badge&color=white&label=ISSUES" />
  <img src="https://img.shields.io/github/last-commit/TheWildKaden/ArdvarkFood?style=for-the-badge&color=white&label=UPDATED" />
</p>

<p align="center">
  <a href="https://github.com/TheWildKaden/ArdvarkFood">Repository</a>
  ·
  <a href="https://github.com/TheWildKaden/ArdvarkFood/issues">Issues</a>
  ·
  <a href="https://github.com/TheWildKaden/ArdvarkFood/graphs/contributors">Contributors</a>
</p>

---

## About

ArdvarkFood is a Python-first monorepo for a web application, CLI, AI agent,
and shared runtime. The FastAPI application serves the Ardvark web interface
and its API. The agent and model/tool runtime are separate Python packages
mounted into that application under `/api/runtime`; core encoding and reusable
integrations remain independent modules.

The static project site can be published with GitHub Pages or Cloudflare Pages.
For fork and hosting setup, see [FORKING.md](./FORKING.md). For local
development, run `python -m cli serve --reload` or
`./cli/start-dev-preview.sh` (the **Start Ardvark Dev Preview** VS Code task
does the same). Open `http://localhost:8000`. The FastAPI app serves the
interface from `website/` at `/`, its project overview from `docs/index.html`
at `/project`, and API routes under `/api/`. Build the static project site
with `npm run build:pages`; preview it with `npm run preview:pages` at
`http://localhost:4173`.

## Project layout

```text
.
├── agent/                   Agent orchestration, context, planning, and memory
├── cli/                     Python command-line entry point and preview launcher
├── core/                    Shared foundations, including message encoding
├── docs/                    Project site, architecture, and technical guides
├── infrastructure/          Build/deployment scripts and architecture tooling
├── packages/                 Reusable integrations, including image generation
├── runtime/                 Model adapters, tools, config, API, and storage
├── services/api/             FastAPI application routes and app factory
├── tests/                    Application, runtime, agent, and architecture tests
├── website/                  Ardvark UI and separate Stock Watch source
├── app.py                    Stable ASGI entry point
└── local_image_generator.py  Legacy image-generator import compatibility
```

`local_image_generator.py` remains as a compatibility import for the image
generator, whose implementation now lives in `packages/image_generation/`.
The live UI markup, styles, and client behavior are in `website/index.html` and
`website/assets/`. `website/stock-watch/` retains a separate React/Fastify
project, but its source references missing local packages and has no
application dependency manifest; it is not currently a verified build target.
Generated runtime images and SQLite state stay local and are ignored by Git.

## Component boundaries

| Component | Responsibility | Interface |
| --- | --- | --- |
| `website/` | Browser UI and static project assets | HTTP from `services/api/` |
| `cli/` | Developer-facing command-line entry point | Starts the stable `app:app` ASGI application |
| `services/api/` | Web app factory and chat/image endpoints | FastAPI routes and the `ImageGenerator` protocol |
| `agent/` | Context, planning, memory, and agent loop | Python interfaces consumed by `runtime/` |
| `runtime/` | Model inference, tools, permissions, persistence, and runtime API | Python interfaces plus `/api/runtime/*` |
| `core/` | Shared encoding and foundational logic | Importable Python modules |
| `packages/` | Reusable integrations | Typed Python interfaces |
| `infrastructure/` | Build, deployment, and architecture-generation tooling | CLI scripts and GitHub Actions |

For the request flow, ownership boundaries, and state locations, see the
[monorepo architecture guide](docs/architecture/monorepo.md).

## Architecture

This architecture is regenerated from the checked-out source. Imports and
literal route declarations are parser-detected; direct calls are resolved only
when the local target is unambiguous. Dynamic dispatch and external runtime
behavior are not claimed as detected facts.

The diagrams below are local SVG previews; every one links to its editable Mermaid source.
For analyzer details, local commands, rate-limit behavior, and workflow policy, see the [architecture generator guide](docs/architecture/README.md).

<details>
<summary>Project structure · <a href="docs/architecture/project-structure.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/project-structure.svg" alt="Project structure generated from repository source" width="100%" />

</details>

<details>
<summary>Declared dependencies · <a href="docs/architecture/dependencies.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/dependencies.svg" alt="Declared dependencies generated from repository source" width="100%" />

</details>

<details>
<summary>Module and package imports · <a href="docs/architecture/modules.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/modules.svg" alt="Module and package imports generated from repository source" width="100%" />

</details>

<details>
<summary>Detected local call graph · <a href="docs/architecture/call-graph.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/call-graph.svg" alt="Detected local call graph generated from repository source" width="100%" />

</details>

<details>
<summary>Class inheritance · <a href="docs/architecture/class-relationships.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/class-relationships.svg" alt="Class inheritance generated from repository source" width="100%" />

</details>

<details>
<summary>Message lexer/parser and encoder · <a href="docs/architecture/lexer-parser.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/lexer-parser.svg" alt="Message lexer/parser and encoder generated from repository source" width="100%" />

</details>

<details>
<summary>Detected API routes · <a href="docs/architecture/api-architecture.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/api-architecture.svg" alt="Detected API routes generated from repository source" width="100%" />

</details>

<details>
<summary>LLM and model runtime · <a href="docs/architecture/llm-runtime.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/llm-runtime.svg" alt="LLM and model runtime generated from repository source" width="100%" />

</details>

<details>
<summary>Agent execution loop · <a href="docs/architecture/agent-execution.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/agent-execution.svg" alt="Agent execution loop generated from repository source" width="100%" />

</details>

<details>
<summary>Tool permission gates · <a href="docs/architecture/permissions.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/permissions.svg" alt="Tool permission gates generated from repository source" width="100%" />

</details>

<details>
<summary>Persistent runtime storage · <a href="docs/architecture/storage.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/storage.svg" alt="Persistent runtime storage generated from repository source" width="100%" />

</details>

<details>
<summary>Build and deployment pipelines · <a href="docs/architecture/build-pipelines.mmd">Mermaid source</a></summary>

<img src="docs/architecture/previews/build-pipelines.svg" alt="Build and deployment pipelines generated from repository source" width="100%" />

</details>

Regenerate locally with `npm ci`, `npx puppeteer browsers install chrome`, and `npm run architecture:generate`. The source and dependency analysis uses Python AST and Babel; unsupported or dynamic relationships are omitted or explicitly marked as inferred. On a minimal Debian/Ubuntu host missing Chromium libraries, run `sudo npx puppeteer browsers install chrome --install-deps` before rendering.

### Technology stack

- **Python**
- **FastAPI**
- **Pydantic**
- **httpx**
- **llama.cpp Python binding**
- **PyTorch**
- **Diffusers**
- **React source**
- **Fastify source**
- **SQLite**
- **Node.js**
- **Mermaid CLI**
- **Babel parser**

## Development

Use Python 3.10+ and Node.js 22. Install the application, runtime, core, and
test dependencies with `python -m pip install -r requirements.txt`. The local
image model is optional; install its dependencies separately with
`python -m pip install -r requirements-image-generator.txt`. Install the
Node.js tooling with `npm ci`.

Run the API and interactive application locally:

```bash
python -m cli serve --reload --host 0.0.0.0 --port 8000
```

Build the static project site with `npm run build:pages`; serve that build with
`npm run preview:pages`. Run the application, runtime, and architecture tests
with:

```bash
python -m pytest -q
```

The standalone encoding suite is:

```bash
python -m pytest -q tests/core/test_encoding.py
```

Two optional example-based encoding tests are skipped when the upstream
inference fixtures are not present under `tests/fixtures/inference/`.
To contribute, fork the repository, create a focused branch, make and test your
change, then open a pull request. Read [CONTRIBUTING.md](./CONTRIBUTING.md) for
the full workflow and review expectations. Architecture diagrams can be
regenerated with `npm run architecture:generate`.

## LLM and agent runtime

The runtime defaults to local GGUF inference through `llama.cpp`. No model
weights are bundled. Install the optional runtime dependencies and provide a
GGUF model:

```bash
pip install -r runtime/requirements.txt
export AI_RUNTIME_MODEL_PATH=/path/to/model.gguf
uvicorn app:app --host 0.0.0.0 --port 8000
```

`POST /api/runtime/models/load` loads the configured model; use
`POST /api/runtime/models/unload` to release it. Model settings can be supplied
through environment variables or `runtime/config/settings.json`. An
OpenAI-compatible backend is available only when explicitly selected with
`AI_RUNTIME_BACKEND=openai_compatible` and configured with
`AI_RUNTIME_BASE_URL` (and, if needed, `AI_RUNTIME_API_KEY`). The existing
`/api/chat` endpoint remains unchanged.

The agent keeps inference separate from orchestration. It builds conversation
context, invokes the model, validates any function-call arguments against JSON
Schema, checks permissions, dispatches tools, records results, and continues
until a final response or a configured limit. Built-in tools cover confined
workspace file access, restricted read-only terminal/git commands, approved
Python subprocesses, allowlisted HTTPS fetch/API calls, and configured stdio
MCP servers. Custom tools can be registered through the runtime's Python
`ToolRegistry` interface.

Tools are not executed directly by model output. Reads are approved by default;
write, network, terminal, Python, and MCP operations wait for an explicit
approval. The approval request is emitted as an SSE event and can be resolved
with `POST /api/runtime/executions/{execution_id}/tools/{tool_call_id}/approval`.
Replacing an existing workspace file through the agent also requires the
current file's SHA-256, preventing a stale proposal from silently overwriting
newer content. The runtime does not execute generated code or manage Git
branches and commits as an autonomous self-modification workflow; see the
[controlled code-change boundary](docs/agent/SELF_EVOLUTION.md).
Python execution runs in a separate interpreter process but is **not** an OS
sandbox; only grant approval in a trusted, private deployment. Network tools
require an explicit `outbound_allowed_hosts` allowlist in runtime settings.
Keep the API private to trusted users.

Runtime API endpoints:

- `POST /api/runtime/chat` — agent chat; set `"stream": true` for SSE tokens,
  tool events, approval requests, and final status.
- `GET/POST /api/runtime/conversations` and
  `GET/DELETE /api/runtime/conversations/{id}` — persisted conversations.
- `GET /api/runtime/models`, `POST /api/runtime/models/load`, and
  `POST /api/runtime/models/unload` — model lifecycle and status.
- `GET /api/runtime/tools`, `GET /api/runtime/executions/{id}`, and
  `POST /api/runtime/executions/{id}/cancel` — tool discovery and run state.
- `GET /api/runtime/config` and `POST /api/runtime/memory` — effective safe
  configuration and explicit long-term memory writes.

SQLite stores conversations, messages, execution state, tool events, memory,
and audit records under `runtime/storage/` by default. Interrupted runs are
marked when the runtime restarts. Text and PNG/JPEG/WebP image attachments are
accepted; image inference requires a compatible multimodal GGUF model and CLIP
projector. Audio and video are rejected with an explicit unsupported-modality
error. The existing SD-Turbo image-generation endpoint remains a separate
local image pipeline.

## Features

- FastAPI chat and a local open-weight SD-Turbo image generator.
- Integrated GGUF/open-compatible LLM adapters and a permissioned tool-using
  agent loop.
- Persistent conversation, execution, memory, and audit storage.
- The original DeepSeek message-encoding implementation remains in
  `core/encoding/`.

See [docs/SOURCES.md](./docs/SOURCES.md) for upstream model, runtime, and
framework references.

## Statistics

<p align="center">
  <img src="docs/architecture/assets/statistics.svg" alt="Repository statistics generated from git and GitHub API data" />
</p>

The snapshot uses local git history and source-analysis counts. Stars and forks
are refreshed from the GitHub API when available; the generated image and JSON
remain in the repository so the README does not rely on a remote stats image
service.

## Contributors

Want to contribute? See the [contribution guide](./CONTRIBUTING.md), open an
[issue](https://github.com/TheWildKaden/ArdvarkFood/issues), or submit a pull request. Contributor cards
use repository-local SVG avatars. GitHub usernames and contribution totals are
read from the contributors API when available; otherwise local commit author
names are used without publishing email addresses.

<table>
<tr><td align="center"><img src="docs/architecture/assets/contributors/86b346e793a6.svg" width="72" height="72" alt="Tide Sync Bot avatar" /><br /><sub>Tide Sync Bot<br />63 contributions</sub></td><td align="center"><img src="docs/architecture/assets/contributors/ce889fc0a8a6.svg" width="72" height="72" alt="Vlint avatar" /><br /><sub>Vlint<br />7 contributions</sub></td><td align="center"><img src="docs/architecture/assets/contributors/a3e534c0d6da.svg" width="72" height="72" alt="AcHamm avatar" /><br /><sub>AcHamm<br />1 contributions</sub></td></tr>
</table>

---

<p align="center">
  <sub>Built by <a href="https://github.com/TheWildKaden">TheWildKaden</a></sub>
</p>
