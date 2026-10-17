# 0005. The agent runtime runs the tool loop; tools live on an MCP server

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** MT-05, MT-06, MT-07, MT-10, MT-11, EV-10, VO-08
- **Plan decisions:** D3, D4, D33

## Context

LiveKit Agents can run an LLM's tool calls itself. The design needs the same agent behaviour to run in voice calls and in text-only evals, needs limits and user scoping enforced in code the project tests, and needs tools to survive a change of LLM provider.

## Decision

The agent runtime (package `companion/agent/`, class `CompanionAgent`) is plain Python with no LiveKit imports. It builds the prompt, calls the LLM, runs the tool loop with a per-turn limit and per-call timeouts, and streams the reply. In a call, `LiveKitBridge` connects LiveKit Agents to it in the same process; evals call it directly. Tools are served by a standalone MCP server that works out whose data a request may see from a signed session token, never from model-supplied IDs. The server runs as one long-running process beside the database, reached over Streamable HTTP; stdio is used only in development. The official MCP Python SDK is the planned library, to be confirmed by a short spike.

## Alternatives considered

- **LiveKit's built-in tool loop with its MCP toolset.** Rejected: less code, but limits and scoping would live in framework behaviour, and evals would need a voice session.
- **Tools as in-process functions.** Rejected: ties tools to one LLM provider's format and puts data access inside the call process.
- **One MCP server process per call over stdio.** Rejected: each call would start its own server and load the embedding model.

## Consequences

The network calls are the same as with LiveKit's loop; the runtime's own overhead has a tested budget of 10ms per turn (VO-08). The runtime must implement streaming, cancellation and the tool-call limit itself. A test must prove voice and text use the same runtime.
