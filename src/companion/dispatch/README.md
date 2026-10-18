# `dispatch/` — Call-start checks

Decides whether a call may start. The frontend's dispatch metadata is parsed by `DispatchMetadata` (`contracts/`); `prepare_session` then checks it against the database: the user exists, a regular user has at most two bots (admins have no limit), and every bot exists, has a version, is active and has a valid stored definition.

**Owns:** the session-start rules and their rejection reasons (`unknown_user`, `too_many_bots`, `unknown_bot`, `inactive_bot`, `invalid_bot`), logged on every rejection.

**Does not own:** the metadata's shape (`contracts/`), loading bot rows (`bots/`), or resolving preset names into providers (`providers/`).

**Spec:** ARCHITECTURE.md → "Frontend contract", "Pluggable providers".

**Status:** implemented (S1.2).
