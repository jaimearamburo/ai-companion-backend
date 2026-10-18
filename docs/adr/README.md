# Architecture decision records

One short record per significant decision: the context, what was decided, the options rejected, and the consequences. Records are never rewritten once accepted; a later record supersedes an earlier one. New records start from [the template](0000-template.md).

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-choose-vendors-by-measured-latency.md) | Choose each vendor by measured latency, per layer and region | Accepted |
| [0003](0003-pay-only-for-live-call-latency.md) | Pay only for live-call latency; run everything else on demand in Sydney | Accepted |
| [0004](0004-screen-input-in-parallel-and-fail-closed.md) | Screen user input in parallel with the draft, and fail closed | Accepted |
| [0005](0005-agent-runtime-owns-the-tool-loop.md) | The agent runtime runs the tool loop; tools live on an MCP server | Accepted |
| [0006](0006-pgvector-exact-search-per-user.md) | Store memories in Postgres with pgvector and search each user's memories exactly | Accepted |
| [0007](0007-bots-are-versioned-database-rows.md) | Bot definitions are validated database rows with immutable versions | Accepted, amended by 0008 |
| [0008](0008-models-per-role-belong-to-the-region-profile.md) | Models per role belong to the region profile; bots have a voice per TTS preset | Accepted |
| [0009](0009-no-partitioning-until-volume-needs-it.md) | Don't partition tables until volume needs it | Accepted |
