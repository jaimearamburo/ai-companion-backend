# `contracts/` — Boundary models

Strict, immutable Pydantic v2 models for everything that crosses a boundary: dispatch metadata from the frontend, bot definitions from the database, the scriptwriter's output, memory records, tool inputs and outputs, safety verdicts, and eval scenarios and results.

**Rules shared by every model** (`Contract` in `_base.py`):

- **Strict types.** A value must already have the declared type: `"3"` is not an int and `"true"` is not a bool. JSON input still reads IDs and timestamps from strings.
- **Unknown fields are rejected.** A tool input carrying a model-supplied `user_id` fails instead of being ignored.
- **Immutable.** Instances can't be changed after validation.
- **Sequences accept lists.** Database rows and YAML supply lists; items stay strict.

**Owns:** the shapes and the rules that need no outside context (e.g. a core fact needs a kind and an importance; a line can't interrupt its own speaker).

**Does not own:** rules that need the call or the database, such as the per-role bot limit or whether a speaker is in the room; those live where the context is.

**Spec:** ARCHITECTURE.md → "Frontend contract", "Database schema", "Memory", "Safety gate", "Evaluation, observability and releases".

**Status:** implemented (S1.1).
