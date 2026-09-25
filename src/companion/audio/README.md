# `audio/` — Audio

Gets each bot's audio to the right place at the right time.

**Owns:** the per-bot audio router (a custom LiveKit audio output that publishes one track per bot, `bot:<bot_id>`), the banter scheduler (anchored to actual playback position), stopping all bot tracks on barge-in, and sending `bot_speaking` / `bot_fade` data messages to the frontend.

**Spec:** ARCHITECTURE.md → "Multi-bot audio output", "Bot-to-bot interruption (banter)", "Frontend contract".

**Status:** not yet implemented.
