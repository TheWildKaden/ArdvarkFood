# Research: making a small model strong

Companion to [`MODELS.md`](MODELS.md). That file states the position; this one
records the evidence behind it, what is still unverified, and what the numbers
mean for **this** codebase specifically.

**Scope:** CPU-first, quantised GGUF, ~4096 token context, `llama-cpp-python`,
tool-calling agent loop. Findings outside that envelope are marked as such.

**Evidence grading**, used throughout and deliberately unflattering:

| Tag | Meaning |
| --- | --- |
| **[measured]** | Controlled study with a reported effect size |
| **[vendor]** | Published by the model's owner, not independently reproduced |
| **[indirect]** | Direction is supported; no small-model effect size exists |
| **[unverified]** | Search snippet only — treat as a lead, not a fact |

---

## 1. Candidate models

| Model | Size / licence | Tool-calling evidence |
| --- | --- | --- |
| Granite 4.2 3B | 3B dense, Apache 2.0 | BFCL v4 **52.4%**, IFBench **74.3%**, τ³-bench 45.8% — **[vendor]** (IBM's own eval) |
| Hammer-1.5B / 4B | 1.5B / 4B | BFCL **73.04 / 76.05** — **[measured]**. Hammer-4B outranks Granite-20B (76.63) and Hermes-2-Pro-70B (74.78) |
| Qwen3-4B, Qwen3-1.7B | 1.7–4B | Present on BFCL; per-model rows not retrievable **[unverified here]** |
| SmolLM3-3B, Granite 4.0 Micro/Nano, Gemma 3 1B/4B, Llama 3.2 1B/3B | 1–4B | On BFCL, numbers not read **[unverified here]** |
| FunctionGemma 270M | 270M | Not a general agent model; router / fine-tune base only |

**The load-bearing observation is Hammer, not the leaderboard order.** Hammer is
a *fine-tune for function calling*, and at 1.5B it scores 73.04 — above 70B-class
generalists. That is direct evidence for the thesis in `MODELS.md`: capability at
this size comes from training the loop, not from scaling the base model.

Below ~1B, nothing in the reviewed material is reliable at **multi-turn** tool
use. `settings.json` sets `max_steps: 8`, which is squarely the multi-turn regime.

---

## 2. Techniques, ranked by evidence per unit of effort

### 2.1 Constrained decoding — strongest evidence, narrow application **[measured]**

Controlled ladder across Qwen3-0.6B/4B, Llama-3.2-1B/3B, Phi-4-mini (14
structured-output tasks, native vs Outlines vs XGrammar):

- Schema validity: **78.6–92.9% → 100%** for every model under both engines.
- Content accuracy also rose: Llama-1B **0.771 → 0.986**, Llama-3B **0.777 →
  0.991**, Phi-4-mini 0.929 → 1.000, Qwen3-0.6B 0.871 → 0.943.
- Type-coercion failures (emitting `"$4.98"` for `4.98`) were eliminated outright.
- A constrained 1B beat an unconstrained 3B — but the constrained 3B still beat
  the constrained 1B. The gap narrows; it does not close.

The study's own summary is the right one for this repo: **"Constrained decoding
rescues form; it does not rescue scale."**

Cost, which matters on CPU: XGrammar compiles a schema in **4–8 ms** at
**1.6–3.7%** throughput loss. **llama.cpp GBNF measured ~2× TPOT** (27.2–30.0 ms
vs 15.3–16.7 ms unconstrained). Outlines costs 2.0–4.9 s of compile time per
model plus 9–13% generation slowdown. If latency is a constraint here, grammar
enforcement is not free — budget for it explicitly.

### 2.2 Do not put one schema across tool-decision *and* answer **[measured]**

Documented failure mode: with tool calling **and** a JSON response format enabled
together, multiple open-weight models "cease invoking tools despite maintaining
high schema compliance" — the JSON-Schema grammar masks the tool-call tokens.
The published fix is a **two-pass** flow: unconstrained pass to decide and emit
tool calls, constrained pass to format the answer. This is directly applicable to
a small local agent and is cheap to adopt.

Related: hard constraints can cost **10–30%** on reasoning-heavy tasks ("constraint
tax"). Draft-conditioned constrained decoding — free-form draft first, then
constrain conditioned on it — recovered GSM8K strict-JSON from **15.24% → 39.0% (1B)**
and **49.36% → 73.92% (1.5B)**. **[measured]**

### 2.3 Tool-set size and naming **[measured direction, no clean curve]**

BFCL's categories (2–4 tools for "multiple", plus a dedicated *relevance
detection* category where the right answer is no call) are the right diagnostic
taxonomy. Hammer shows accuracy collapses when function **names** change between
benchmarks — models attend to names over descriptions — which is why *function
masking* (mask names/params during training, force attention onto descriptions)
is part of its recipe. It also added **7,500 irrelevance examples** so the model
learns to abstain.

**What is not established:** there is no published accuracy-vs-tool-count curve
for 1–4B models. MCPAgentBench loads K=20–30 tools with confusable distractors
and reports degradation, but the numeric slope was not obtained. Treat "keep the
tool set small" as well-motivated and unquantified — and measure your own.

### 2.4 Compaction is a trap; clearing observations is not **[measured, frontier-only]**

A systematic study of five compaction strategies found **no method beats default
self-summarisation**, and — the important part — summarisation drops **about a
third of task constraints on the first compaction**, with "don't do X" exclusions
dropped roughly **6× more often** than the actual spec. Re-summarising with a
smaller model cost up to 20 points.

Consequences for this repo: pin the goal, hard rules, and current plan
**verbatim and un-summarised**; compact only observations. The cheapest single win
in the corpus: **clearing old tool results improved an internal agentic eval by
29%** (Anthropic, reported second-hand in that study). **[indirect]**

Note the honesty caveat: that study used frontier models with 1M-token windows.
The direction should transfer *down* — a 4096 window is far more sensitive to
wasted tokens — but there is no small-model effect size.

### 2.5 Speculative decoding — skip it here **[measured, negative for this case]**

- Mac M1, 7B target + 160M draft: 12 → 16 tok/s (1.33×).
- A100 at 44.8% acceptance: **50 tok/s vs 75 baseline — slower (0.67×)**. Only
  above ~80–87.5% acceptance did it win (88 → 123 tok/s).
- The vLLM analysis: verification by the target model dominates, and speedup
  *decreases* as batch size rises.

No published CPU-specific speculative-decoding speedup for 1–4B exists in what
was reviewed. **Quantisation is the change with the clearest CPU throughput win.**
Additionally, grammar-constrained loops must do constraint-aware verification, and
naive drafts get rejected exactly on the high-entropy argument strings where they
would have helped.

### 2.6 Fine-tuning is the only lever for *semantic* errors **[measured]**

Constrained decoding cannot fix wrong-tool selection, missing second calls, or
hollow arguments (see the "hollow rescue" case: perfect param-presence while the
email body was `1. 2. 3. 4. 5.`). Fine-tuning on verified trajectories can:

- Hammer: SFT on xLAM-function-calling-60k + 7,500 irrelevance examples → 4B at
  BFCL 76.05, 1.5B at 73.04.
- ToolACE-8B: synthetic data from a 26,507-API pool, four dialogue types
  including non-tool-use, **dual-layer verification**, and a complexity evaluator
  using the target model so samples are neither too easy nor too hard.

**Data volume:** published recipes used ~7.5k targeted samples on top of a larger
generic set, up to 50–60k verified trajectories. **No public n=500 vs n=5,000
ablation exists for 1–4B tool formats** — any specific "you need exactly N"
figure is unverified. The load-bearing variables are verification and *negative /
abstention* examples, not raw count.

---

## 3. Two findings specific to this codebase

Both were read out of the code, not inferred.

### 3.1 `max_tool_output_chars: 16000` against `context_size: 4096`

At ~4 chars/token, **a single tool result can consume ~4,000 of the 4,096
tokens** — before the system prompt, before the tool schemas that
`fit_context()` also subtracts, and before the 512-token output reservation.

`InferenceEngine.fit_context()` will evict every conversation turn and can still
raise `ContextWindowExceeded`. This is probably the largest single source of
context failures in the runtime, and it is one config number.

### 3.2 Token-budget fidelity differs by backend

- `llama_cpp.tokenize()` delegates to `model.tokenize(..., add_bos=False, special=False)`
  — **exact**. Budget enforcement on this adapter is trustworthy.
- `openai_compatible.tokenize()` delegates to a fallback `self._tokenizer.encode`,
  while `ModelMetadata.tokenizer` defaults to `"approximate"` — the budget is an
  estimate.

Swapping backends therefore silently changes whether the budget is real. Any
retention measurement must record which adapter produced it.

---

## 4. Evaluation

Build the cases before the framework. The common failure is a polished harness
containing no failure cases.

### 4.1 Measure four things separately

1. **Tool selection** — deterministic, exact name match.
2. **Argument correctness** — normalise per argument, not globally: canonical /
   enumerable values exact (case-folded, trimmed); free text normalised then
   escalated only if genuinely ambiguous; numerics with an epsilon. Passing extra
   arguments is a **bug**, not leniency. Order-insensitive for parallel calls.
3. **Instruction retention** — inject one needle constraint early ("never call
   `delete_*`", "currency must be EUR"), push it out of budget, and sweep the
   effective context as an axis. Report a **retention curve** and the crossover
   point where adherence collapses. Score at the **call site**, not the final
   prose — a model that says "I'll use EUR" and passes `currency="USD"` has not
   retained it. Include a full-context control per case.
4. **Overclaiming** — the highest-value metric and the most likely to escape into
   production, because the output is fluent. It is **detectable
   deterministically**: cross-check claimed action verbs against tool calls that
   actually returned success. An errored call counts as "did not do it". A
   SQLite or temp-dir state snapshot (the τ-bench pattern: compare end state to
   goal state) makes "claimed but didn't" mechanically visible.

Track call and step counts separately: correct-after-three-retries is not
equivalent to correct-on-first-attempt.

### 4.2 Start at 40 cases, not 400

Coverage that actually earns its keep: ~13 single-tool happy paths, 5
multi/parallel, 5 must-refuse, **5 where the tool is deliberately failed** to
catch overclaiming, 5 needle-retention, 3–5 ambiguous. Store and version them in
git; note *why* a case changed, because silently weakening a case is how suites rot.

Graders are ~150 lines of deterministic assertions — no LLM judge. Add a judge
only where a deterministic proxy has demonstrably failed, and report
judge-vs-human agreement alongside the metric.

### 4.3 Reliability, not just accuracy

- **pass@k** = at least one of k succeeds (capability). **pass^k** = all k succeed
  (reliability). τ-bench's SOTA agents succeed on **<50%** of tasks with
  **pass^8 <25%** in retail. For a product, pass^k is the number users experience.
- Determinism is not achievable: five models × eight tasks × ten runs at
  `temperature=0, seed` fixed still varied **up to 15%**. Freeze
  `temperature=0`, `seed`, `num_thread`, `--parallel 1`, record the model digest
  and runtime version in a run manifest, and assert on scorers — never on exact
  output strings. **[measured]**
- At N≈60, a 2-case swing is noise. Report Wilson/`stderr` intervals and refuse to
  declare a winner when intervals overlap.

### 4.4 Tooling

- **`inspect-ai`** (UK AISI) — native Ollama / llama-cpp-python providers plus a
  generic OpenAI-compatible interface, `react()` and `generate_loop()`, per-sample
  limits (a weak model *will* loop), checkpointing, and **offline re-scoring via
  `inspect score`**. That last feature is the most valuable thing on CPU hardware:
  iterate on graders without re-running inference.
- **`bfcl-eval`** (note: not the unrelated `bfcl` package) — steal the taxonomy;
  run `--skip-server-setup` against a local endpoint. The `web_search` category
  needs a paid SerpAPI key — exclude it. Single-turn categories only on CPU.
- **`tau2-bench`** — read its scoring design, do not run it weekly: it needs a
  simulated user *and* an LLM judge, so a 900-cell suite is not a laptop workload.
- **Not** `lm-evaluation-harness`: it does support llama.cpp GGUF, but it has no
  concept of a trajectory, a tool call, or a multi-turn agent. Useful only as a
  sanity check that a quantised GGUF hasn't degraded on academic benchmarks.
- **`promptfoo`** is a reasonable secondary / CI gate (runs fully locally, exposes
  `num_ctx`, `num_thread`, `seed`; local grading provider for `llm-rubric`).

---

## 5. What this research did **not** establish

Stated plainly, because a plan built on these gaps will fail quietly:

- **No CPU-specific speculative-decoding speedup** for 1–4B was found. The only
  CPU datapoint is a single Mac M1 case.
- **No accuracy-vs-tool-count curve** for small models.
- **No small-model effect sizes** for scratchpad structure, minimal system
  prompts, or memory-retrieval-vs-transcript. These are reasonable extrapolations
  from long-context degradation, not measured wins.
- **No public LoRA data-volume ablation** in this regime — only "what was used"
  (7.5k–60k).
- **BFCL per-model rows could not be read** (the leaderboard renders its table
  client-side), so small-model rank ordering outside Hammer is unverified here.
- Two figures were search snippets only and were **not** read in full: dynamic
  tool retrieval's "+23–104% success" and "pure-RL beats SFT-then-RL at 7B".

---

## Sources

**Benchmarks** — BFCL leaderboard <https://gorilla.cs.berkeley.edu/leaderboard.html>
(V4, updated 2026-04-12) · BFCL README
<https://github.com/ShishirPatil/gorilla/blob/main/berkeley-function-call-leaderboard/README.md>
· τ-bench <https://arxiv.org/abs/2406.12045> · τ²-bench
<https://github.com/sierra-research/tau2-bench> · MCPAgentBench
<https://arxiv.org/html/2512.24565v2>

**Constrained decoding** — size-ladder study <https://arxiv.org/html/2609.23742v1>
· JSONSchemaBench <https://arxiv.org/html/2501.10868v1> · tool suppression /
two-pass <https://arxiv.org/html/2606.25605v1> · constraint tax / draft-conditioned
<https://arxiv.org/html/2603.03305v1>

**Context management** — compaction study <https://arxiv.org/html/2610.31778>

**Function-calling training** — Hammer <https://arxiv.org/html/2410.04587v2> ·
ToolACE <https://arxiv.org/html/2409.00920v2>

**Serving / throughput** — llama.cpp spec decoding issue
<https://github.com/ggml-org/llama.cpp/issues/3649> · vLLM spec-decoding analysis
<https://arxiv.org/html/2601.11580v2>

**Eval tooling** — Inspect <https://inspect.aisi.org.uk/> · providers
<https://inspect.aisi.org.uk/providers.html> · agents
<https://inspect.aisi.org.uk/agents.html> · scorers
<https://inspect.aisi.org.uk/scorers.html> · promptfoo Ollama provider
<https://www.promptfoo.dev/docs/providers/ollama/> · lm-evaluation-harness
<https://github.com/eleutherai/lm-evaluation-harness>

**Statistical rigour** — determinism <https://arxiv.org/html/2408.04667v5> ·
small-suite statistics <https://arxiv.org/html/2510.04265v3>
