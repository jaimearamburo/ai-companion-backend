# `pipeline/` — Pipeline

The only place modules are connected together. For each call it reads the validated dispatch metadata, resolves providers, and assembles the LiveKit `AgentSession` with the scriptwriter, safety gate, turn-taking, memory and audio router.

**Rule:** other modules don't import each other's internals; they are wired here. This is what keeps each module testable on its own.

**Spec:** ARCHITECTURE.md → "Sequence diagram".

**Status:** not yet implemented.
