# `safety/` — Safety

Runs the safety classifier on the transcript in parallel with the script draft, and decides at turn commit whether the real script or approved fixed text is played.

**Owns:** calling the safety model (through a provider from `providers/`), parsing its verdict, and the fail-closed rule: an error, timeout or unparseable verdict is treated as "unclear" and plays the disclaimer.

**Spec:** ARCHITECTURE.md → "Safety gate", "Sequence diagram"; REQUIREMENTS.md → "Error handling".

**Status:** not yet implemented.
