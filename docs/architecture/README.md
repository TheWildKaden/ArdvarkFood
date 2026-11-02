# Architecture generator

The generated architecture in this folder is derived from source in the current
checkout. It is not a hand-maintained replacement for the existing app or
runtime.

## Run locally

Requirements: Python 3.10+ (standard library only), Node.js 22+, npm, and a
Chromium installation supported by Puppeteer.

```bash
npm ci
npx puppeteer browsers install chrome
npm run architecture:generate
npm run architecture:validate
```

On a minimal Debian/Ubuntu host where Chromium reports missing shared libraries,
install browser dependencies with
`sudo npx puppeteer browsers install chrome --install-deps`, then run the
non-sudo browser install command above so Puppeteer stores the browser in your
user cache. Add `--offline` to
`python3 infrastructure/scripts/generate_architecture.py` to
skip GitHub API calls and use commit authors from local git history.

`npm run architecture:generate` parses sources, writes Mermaid and JSON files,
renders SVGs to local previews, updates `README.md` from
[`templates/README.md.in`](../../infrastructure/architecture/templates/README.md.in),
and validates the result. Edit that template for README content; direct edits
to the generated `README.md` will be replaced on the next generation run.

## Analyzer boundaries

- **Dependencies** — reads root, runtime, core, and image-generation
  requirements files plus the root `package.json`. Declarations are not proof
  that a feature is installed or runnable.
- **Modules** — resolves local Python imports using Python's AST and relative
  JavaScript/TypeScript imports using Babel's parser.
- **Functions and classes** — parses Python syntax with `ast` and JavaScript,
  JSX, and TypeScript syntax with `@babel/parser`. Direct calls are included
  only when their local target resolves uniquely (same-file unqualified calls
  or typed/constructed instance calls). Dynamic dispatch and unresolved
  imports are omitted.
- **API routes** — lists literal FastAPI decorators and JavaScript HTTP-method
  calls. Dynamically assembled paths and mounted prefixes may not be visible.
- **Runtime, tools, permissions, and storage** — reports detected constructors,
  direct method calls, adapter imports, SQLite table declarations, and the
  permission gate. Narrative loop and policy labels are marked as inferred
  where they summarize control flow rather than AST-resolved edges.
- **Compiler components** — visualizes the detected encoder/parser functions.
  The current source has no standalone lexer package; the diagram explicitly
  says so rather than inventing one.
- **Build systems** — reads npm scripts, workflow command lines, and known
  generator outputs. It does not claim that a build or deployment succeeded.

`docs/architecture/architecture.json` records counts, routes, manifest
dependencies, component edges, and the interpretation rules. Each `.mmd` is
the editable Mermaid source; the corresponding `previews/*.svg` is rendered
locally by Mermaid CLI. `assets/statistics.svg` and the generated per-author
SVGs are repository-local, so README rendering does not depend on a remote
contributor-image service.

## Contributor data and automation

When a GitHub repository can be identified, the generator makes at most two
GitHub REST requests: the first 100 contributors and repository statistics.
`GH_TOKEN` or `GITHUB_TOKEN` is sent only to `api.github.com` and is never
written to generated output. HTTP 403/429 responses, exhausted rate limits,
and network failures fall back to local commit counts and author names. Local
fallback does not publish email addresses. Avatars are generated locally from
initials; they are not downloaded from contributor profiles.

`.github/workflows/update-architecture.yml` runs for every push to `main`, on
manual dispatch, and weekly. It has only `contents: write` permission, stages
only the generated README and architecture assets, and commits only when the
staged diff is non-empty. A bot-actor guard and `[skip ci]` commit message
prevent generator commits from creating an update loop.

The `.mmd` files are syntax-validated by rendering them with Mermaid CLI;
generated SVG is parsed as XML and checked for executable scripts/event
handlers; JSON assets are parsed; and local links and Markdown anchors in
`README.md` are checked before generation succeeds.
