# Armani

GitHub: [@acunningham-ship-it](https://github.com/acunningham-ship-it)

## Focus

A small model that punches above its weight. Not the frontier-lab play of
scaling parameters until competence appears — the leverage is in the loop
around the model: context that earns every token, tools whose failures are loud
instead of silent, and evals that catch the agent claiming it did something it
didn't.

That's the target here: keep the runtime small enough to run locally on modest
hardware and make it strong through tight feedback rather than raw parameters.

## What I'm working on

Repository hygiene first, because a clean tree is cheaper to reason about than
a clever one:

- Dropped the vendored `llama/extracted/` DLL dump (~60 MB). The runtime loads
  inference through the `llama_cpp` Python package, so those binaries were
  dead weight — and a per-machine Windows artifact that should never have been
  in version control.
- `.gitignore` now covers model weights, virtualenvs, local secrets and runtime
  state, so the next `add -A` can't vacuum up a GGUF or a sqlite file.
- Removed a scratch file and a redundant note; moved `SOURES.TXT` to
  `docs/SOURCES.md`, since that file is real attribution for the SD-Turbo pipeline
  and shouldn't be misspelled.

## Next

- Model selection and a repeatable eval harness, so "strong" is measured rather
  than assumed.
- Keep the agent runtime and the image generator cleanly separated — they share
  a process today, not a purpose.

## Notes

`portfolios/` collects these per-contributor notes — one file per contributor.

Kaden's original note, kept verbatim: *"rlly cool AI Guy"*. This file is the same
entry as `AcHamm.md` (`AcHamm` is the GitHub display name for this account), so
it absorbs that file rather than leaving two entries for one person.
