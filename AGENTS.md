# AGENTS.md

**See [CLAUDE.md](CLAUDE.md).** It is the single source of truth for this
repository: build and run commands, the admin CLI surface, backend and iOS
architecture, the design system, deployment, and the checklist for adding a new
agent tool.

This file used to be a full copy of CLAUDE.md that differed only in the word
"Codex", and the copy drifted out of date. There are no Codex-specific rules —
everything in CLAUDE.md applies verbatim.

Two repo-wide notes worth repeating here, because they are the easy ones to get
wrong:

- **Codex CLI config lives in `.codex/` and is gitignored** — it contains API
  keys. Never commit it, and never read secrets out of it into a file that is
  tracked.
- **`ios-app/` is gitignored** and not part of the public repository. Backend
  changes that alter the SSE contract or a card payload still need the iOS side
  updated in the private checkout; say so rather than assuming it is done.
