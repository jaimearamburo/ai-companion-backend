# `turn_taking/` — Turn taking

Decides when to fire a speculative bet (start safety + script draft early) and manages bets through a user's turn.

**Owns:** the trigger strategies (`transcript_rules`, `transcript_debounce_only`, `vad_silence`, `livekit_preemptive` integration), the per-language word rule tables, one-bet-in-flight cancellation, the bet cap (3 per turn + 10s cut-off), and per-turn bet metrics.

**Does not own:** turn detection itself (a provider preset in `providers/`), or what a bet does once fired (`pipeline/` wires safety + scriptwriter).

**Spec:** ARCHITECTURE.md → "Turn-taking: turn detection vs speculative bets".

**Status:** not yet implemented.
