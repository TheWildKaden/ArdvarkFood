# Models

## The position: small model, strong loop

We are not chasing "bigger model = better model." A model that needs a frontier
budget and a 200k context window to behave is not strong; it is expensive and
still unverified.

The bet here is the opposite: a **small, local, quantized model** whose
competence comes from the machinery around it — a context budget it actually
respects, a small set of tools it can call correctly, memory it retrieves
instead of carrying, and evals that fail loudly when it claims work it did not
do.

"Strong" is a measured property, not a parameter count. Until there is a
harness producing numbers, treat any strength claim here as unproven.

## What the runtime already assumes

The code is built for the small end, not retrofitted to it:

| Assumption | Where it lives |
| --- | --- |
| 4096-token default context | `config/settings.json` → `model.context_size` |
| CPU-first, no GPU required | `model.gpu_layers: 0` |
| No weights in the repo | `model.model_path` is empty; GGUF is supplied locally |
| 512-token default output | `model.default_max_tokens` |
| Local GGUF via `llama-cpp-python` | `models/adapters/llama_cpp.py` |
| Any OpenAI-compatible endpoint, for comparison | `models/adapters/openai_compatible.py` |
| No vendor assumption in the core | `ModelAdapter` protocol in `models/inference.py` |

`ModelAdapter` is the only seam the engine knows about: `load`, `unload`,
`tokenize`, `generate`, `stream`, plus a `ModelMetadata`. Nothing above it
assumes a specific vendor, file format, or checkpoint.

## The context budget is the feature

`InferenceEngine.fit_context()` treats the window as a budget, not a bag:

1. Reserve the output allowance — `max_tokens`, or `min(1024, context // 4)`.
2. Count the **tool schemas** and subtract them. Tools are a recurring tax paid
   on every single request, not a one-off cost.
3. Hold back a 128-token reserve.
4. Whatever remains is the input budget. Over it, drop the oldest conversation
   turns — and if the current message alone still will not fit, raise
   `ContextWindowExceeded` rather than silently truncating.

That ordering is the whole design argument. A small window makes waste visible;
a huge one hides it until the bill arrives.

## Design rules that follow

- **Keep the toolset small.** Every registered tool is paid for on every turn.
  Ten mediocre tools cost more than three good ones.
- **Keep the system prompt lean.** It is subtracted before any user content.
- **Put durable state in memory/storage, not the transcript.** Eviction is
  oldest-turn-first, so anything that must survive belongs outside the window.
- **Retrieval has to earn its tokens.** Injecting a document that does not
  change the answer is a net loss at this scale.
- **Do not paper over failures with a bigger checkpoint.** If the agent
  misbehaves, the first suspect is context management, not model capacity.

## Anti-goals

- Scaling parameters to compensate for a loop nobody measured.
- Depending on huge context windows to avoid deciding what matters.
- Locking the runtime to one provider's API shape.

## Open questions

- Which small GGUF checkpoints clear the bar on tool-calling accuracy at 4096
  tokens, and at what quantisation before accuracy degrades.
- What the eval harness measures first — tool-call correctness, instruction
  retention across eviction, or groundedness. Pick one before adding the rest.

## Evidence

The measured backing for every claim above — effect sizes, citations, and an
explicit list of what could **not** be verified — is in
[`RESEARCH.md`](RESEARCH.md). Read it before citing a number from this file.
