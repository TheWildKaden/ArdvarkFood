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

ArdvarkFood is a FastAPI application with Ardvark chat and a local SD-Turbo
image generator. Its existing app now also mounts a modular LLM and agent
runtime under `/api/runtime`; the runtime does not replace the original chat,
image, or encoding modules.

The static project site is published with GitHub Pages. To preview the
interactive Ardvark frontend and its API locally, run
`./scripts/start-dev-preview.sh` (or the **Start Ardvark Dev Preview** task in
VS Code), then open `http://localhost:8000`. The app serves the existing chat
and image-generator frontend at `/` and the Pages-style project overview at
`/project`. Alternatively, preview only the static Pages site with
`./scripts/preview-pages.sh` at `http://localhost:4173`.

## LLM and agent runtime

The runtime defaults to local GGUF inference through `llama.cpp`. No model
weights are bundled. Install the optional runtime dependencies and provide a
GGUF model:

```bash
pip install -r AI-Runtime/requirements.txt
export AI_RUNTIME_MODEL_PATH=/path/to/model.gguf
uvicorn app:app --host 0.0.0.0 --port 8000
```

`POST /api/runtime/models/load` loads the configured model; use
`POST /api/runtime/models/unload` to release it. Model settings can be supplied
through environment variables or `AI-Runtime/config/settings.json`. An
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
and audit records under `AI-Runtime/storage/` by default. Interrupted runs are
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
  `src/encoding/`.

See [SOURES.TXT](./SOURES.TXT) for upstream model, runtime, and framework
references.

## Statistics

<p align="center">
  <img src="https://github-readme-stats.vercel.app/api/pin/?username=TheWildKaden&repo=ArdvarkFood&theme=transparent&hide_border=true" width="100%" />
</p>

## Contributors

Want to contribute? See the [contribution guide](./CONTRIBUTING.md), open an
[issue](https://github.com/TheWildKaden/ArdvarkFood/issues), or submit a pull
request. GitHub updates this contributor graphic automatically for recognized
contributions; see [how contributor recognition works](./CONTRIBUTING.md#being-recognized-as-a-contributor).

<a href="https://github.com/TheWildKaden/ArdvarkFood/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=TheWildKaden/ArdvarkFood" />
</a>

---

<p align="center">
  <sub>Built by <a href="https://github.com/TheWildKaden">TheWildKaden</a></sub>
</p>