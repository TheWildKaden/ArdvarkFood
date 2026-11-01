# Controlled code-change workflow

The runtime is an assistant with approval-gated tools, not an autonomous
self-modifying system. It does not load generated native modules, evaluate
generated Lisp, run proposed source changes, create commits, or roll back Git
history automatically. Python subprocess execution is not an OS sandbox.

## Current safeguards

- Workspace reads are confined to the configured workspace.
- Every `filesystem.write` call requires explicit tool approval.
- Creating a new file is supported. Replacing an existing file also requires
  the SHA-256 of the current contents; stale or missing digests are rejected.
- Writes use a temporary file and atomic replacement so readers do not observe
  partially written content.
- Git tools exposed to the agent are read-only. Commits, branch changes, and
  rollback remain operator actions.
- Test execution and proposed changes must be reviewed by a trusted operator.

These controls reduce accidental overwrites; they do not make an untrusted
workspace or arbitrary code execution safe.

## Future integration boundaries

The repository currently implements the AI runtime in Python. It has no
checked-in Rust, C, Common Lisp, or TypeScript runtime modules. Any future
multi-language implementation should introduce each component behind a
versioned, schema-validated interface rather than loading generated code into
the server process:

| Component | Intended boundary |
| --- | --- |
| Python | Produce change proposals and coordinate explicitly approved work |
| Rust | A separately supervised runtime service with a narrow request/response contract |
| Common Lisp | A separately supervised logic service; evaluate only explicitly approved inputs |
| C | A small audited native interface with explicit ownership and error contracts |
| TypeScript | Operator dashboard using the existing HTTP and server-sent-event patterns |
| Git | Human-reviewed experiment branches and commits; never rewrite the operator's current branch |

Before any proposed change can be applied automatically, the project needs an
OS-enforced sandbox with resource and network limits, isolated experiment
worktrees, a fixed test policy, approval and audit records, and a tested
rollback procedure. Those capabilities are not provided by the current Python
subprocess helper or per-tool approval mechanism.
