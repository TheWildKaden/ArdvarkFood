# Monorepo architecture

ArdvarkFood keeps the web application, command-line entry point, agent, and
model/tool runtime in one repository while preserving explicit module
boundaries. Python packages are imported from the repository root; the
application is not currently published as independently installable wheels.

## Request and startup flow

```text
cli/ ──starts──> app.py ──creates──> services/api/
                                     ├── serves website/
                                     ├── mounts /api/chat and /api/images/*
                                     └── mounts runtime/api/ at /api/runtime/*

runtime/api/ ──creates──> agent/ ──uses──> runtime/models, runtime/tools,
                                           runtime/storage
```

- `app.py` is the stable ASGI import target (`app:app`) and delegates
  application construction to `services/api/app_factory.py`.
- `cli/` provides the Textual workbench (`python -m cli tui`) and the
  `python -m cli serve` command. Invoking `python -m cli` without a subcommand
  continues to open the workbench.
- `services/api/` serves the browser UI from `website/` and exposes the
  existing chat and local image-generation endpoints.
- `runtime/api/server.py` mounts the agent API into that FastAPI app. The
  runtime does not replace the existing `/api/chat` or image endpoints.

## Component ownership

| Directory | Owns | Depends on |
| --- | --- | --- |
| `website/` | Ardvark HTML, browser assets, and the separately retained Stock Watch source | HTTP API contract |
| `cli/` | Textual terminal workbench, CLI parsing, and local server command | `app:app` target; optional Textual dependency |
| `services/api/` | FastAPI routes, request schemas, and app factory | `packages/`, `runtime/api/`, `website/` |
| `agent/` | Agent loop, context, planning, memory, and multimodal input routing | `runtime/` contracts |
| `runtime/` | Model adapters, inference, tool registry/execution, permissions, config, persistence, and runtime routes | `agent/`, Python dependencies |
| `core/` | Message encoding and foundational algorithms | Small focused dependencies |
| `packages/` | Reusable integrations such as local image generation | Shared Python interfaces |
| `infrastructure/` | Static-site, container, and architecture tooling | Build tools and CI environment |
| `tests/` | Cross-component and package tests | Application/runtime dependencies |

The image-generation integration is injected through the `ImageGenerator`
protocol, allowing the API to be tested with a fake implementation without
loading model weights. Agent and runtime components are similarly exercised
with fake model adapters and temporary storage.

## State and deployment

- Runtime configuration is loaded from `runtime/config/settings.json` and
  `AI_RUNTIME_*` environment variables.
- Runtime SQLite state defaults to `runtime/storage/runtime.sqlite3`;
  generated images default to `.generated/`. Both locations are local,
  ignored state rather than source-controlled data.
- The root `requirements.txt` installs API, runtime, core, and test
  dependencies. Large local image-generation dependencies are optional and
  installed separately from `requirements-image-generator.txt`.
- `npm run build:pages` publishes only `docs/` into `dist/`. GitHub Pages and
  Cloudflare Pages therefore host the static project site, not the FastAPI
  application or model runtime.
- The source and checked-in bundle under `website/stock-watch/` are retained
  as a separate project, but are not currently a supported build target: the
  source imports local logger/monitoring packages that are absent from this
  repository, and the directory has no application dependency manifest.

## Validation

Run the application, agent, runtime, core, CLI, and architecture tests with:

```bash
python -m pytest -q
```

Build and validate the static project site with `npm run build:pages`.
Architecture source and diagrams are generated and validated through the
commands in `docs/architecture/README.md`.
