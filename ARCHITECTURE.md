# Voice Companion Architecture v2 — Full Pipeline

Sep 22, 2026 · @Someone — revised Sep 24, 2026

## Bottom line

The v2 architecture — with the safety guardrail and tiered memory added — still clears both targets, with the same caveat as before: **cost has real margin (\~1.2¢/min, well under 3¢), latency does not.** Sub-300ms is achievable on *first audible bot sound* only if the safety check runs genuinely in parallel with a speculative script draft that starts before turn-detection commits, and only with the cached-filler technique still doing the heavy lifting. Long-term memory is kept **off the critical path** entirely: a profile cheat sheet is preloaded at call start, and anything beyond it is fetched on demand by the scriptwriter through a tool call (see Memory). Four specific numbers in the original brief — <15ms for the safety pass, sub-30ms LiveKit edge transit, <50ms Groq inference under a 1,500-token budget, and a speculative bet firing \~130ms *before* the user stops speaking — are optimistic as stated; see Engineering flags for the corrected versions. None of these are fatal, but the brief's own numbers would fail if taken literally.

**Group size:** the user picks 1 or 2 bots from a predefined roster via a room-setup UI before starting the call — group size is user-chosen, not fixed. A user + 1 bot (1-to-1) is a supported, intentional mode; 2 bots is the max for regular users. **Admin users (developers) may add any number of bots for testing.** The pipeline is written generically over N bots — nothing is hardcoded to 2. Room size barely changes cost: the scriptwriter only ever has 1 bot speak per turn (2 during a banter interruption), so TTS, output tokens, parallel TTS streams and LiveKit usage (all bots are tracks on one agent participant) don't grow with N. What does grow is the scriptwriter's **input prompt** — every bot's persona and per-bot cheat sheet go into every call — adding input tokens and prefill time per extra bot, and giving the LLM more personas to juggle. Token budgets in this doc are sized for 2 bots; N > 2 (admin testing) will run slightly over them. The 2-bot limit for regular users is enforced in the frontend (UI and server-side before dispatch) and re-checked by the backend at session start against the user's role.

## Full stack

| # | Layer | Pick | Role |
| --- | --- | --- | --- |
| 1 | Frontend | Next.js on Vercel Free/Hobby | Login + room-setup UI + server-side dispatch call; drops out once WebRTC connects — zero cost, not on the latency path |
| 2 | Transport + VAD | LiveKit Cloud, Australia-pinned | WebRTC media routing; region-pinning keeps audio transit in-country |
| 3 | Orchestration | Self-hosted LiveKit Agents (Python) on a persistent server in AWS ap-southeast-2 (Sydney) | Runs the whole turn loop next to the media edge — no trans-Pacific hop for orchestration logic |
| 4 | STT | Inworld STT (`inworld-stt-1`), voice profiling enabled — **provisional, under test** | Streaming transcription + acoustic voice-profile (emotion/accent/age/pitch). Transcription only — turn detection is layer 5. No confirmed AU/APAC endpoint — falls back to Deepgram Nova-3 (AU endpoint, confirmed) if the latency test in Engineering flags fails |
| 5 | Turn detection | LiveKit Turn Detector v1 (default), selectable per call | Decides when the user's turn has actually ended (turn commit). Audio-based model; see Turn-taking |
| 6 | Safety guardrail | GPT-OSS-Safeguard-20B on Groq | Policy classifier on the live transcript; intercepts self-harm/medical-advice requests before they reach TTS |
| 7 | Memory — Tier 1 (hot) | Redis (Upstash/Aiven), Sydney-pinned | Session state, room boundaries, the **profile cheat sheet** loaded at call start; read every turn |
| 8 | Memory — Tier 2 (long-term) | Supabase Postgres + pgvector, Sydney | Atomic core facts + session summaries; searched on demand via the scriptwriter's `recall_memory` tool — never on every turn |
| 9 | Memory — Tier 3 (rolling) | In-payload short-term buffer, 10–15 messages | Injected directly into the prompt, pruned to protect the token ceiling |
| 10 | Scriptwriter LLM | GPT-OSS-20B on Groq, Harmony format, low reasoning effort | Single pass: decides which bot(s) speak (the "conductor" role — originally planned as a separate LLM, merged into this one), writes dialogue + non-verbal tags, holds every persona at once; may call `recall_memory` |
| 11 | TTS | Inworld TTS-2 Flash | Streaming synthesis, one stream per speaking bot with that bot's voice; non-verbal tags (`[sigh]`, `[laugh]`, `[chuckle]`) render on Flash — confirmed compatible, see Engineering flags |
| 12 | Embedding model | Self-hosted Hugging Face sentence-embedding model on the orchestration server — **specific model TBD after a CPU latency test** | Turns text into vectors for pgvector, both when storing memories and when searching them. No network hop, nothing leaves Australia |
| 13 | Memory extraction LLM | Cheap LLM, **model TBD** | Post-call job: extracts atomic core facts + a session summary from each call's transcript. Off the hot path |

One structural note carried over from the sub-400ms design and still true here: **STT and turn-detection are continuous streams, not a step that starts after the user stops talking** — everything downstream reacts to those streams, it doesn't wait for a full transcript to be handed over.

## Design requirement: pluggable providers

Every external endpoint in this stack — STT, TTS, LLM (including the safety model), plus the turn detector and the speculative-trigger strategy — must be swappable without a code rewrite. Testing provider combinations (like the Deepgram/Inworld STT comparison above) is an ongoing part of building this, not a one-time choice made once and hardcoded.

Concretely: a config-driven provider registry maps preset names (e.g. `deepgram_au`, `inworld_flash`, `groq_gptoss20b`) to the actual LiveKit plugin instantiation (auth, model, region params). A Next.js test UI exposes this as dropdowns, resolved server-side (API keys never reach the browser) into preset names, sent to the LiveKit agent worker via **agent-dispatch metadata** at session start (LiveKit's `createDispatch(...)`, read back via `ctx.job.metadata` in the Python entrypoint). This is per-session, not mid-call: picking a combo starts a new test call, it doesn't hot-swap providers inside one already running.

**Per-call selectable presets:**

| Dropdown | Presets | Default |
| --- | --- | --- |
| STT | e.g. `inworld_stt1`, `deepgram_nova3_au`, `deepgram_flux` | `inworld_stt1` |
| TTS | e.g. `inworld_flash` | `inworld_flash` |
| LLM (scriptwriter) | e.g. `groq_gptoss20b` | `groq_gptoss20b` |
| Turn detector | `livekit_v1`, `livekit_v1_mini`, `stt_native` | `livekit_v1` |
| Speculative trigger | `auto`, `livekit_preemptive`, `transcript_rules`, `transcript_debounce_only`, `vad_silence` | `auto` |

Preset names are provisional until the registry is implemented; the registry is the source of truth for the final list.

**Compatibility rules** (the backend rejects an invalid combination at session start with a clear error; the frontend greys out invalid options):
- `stt_native` turn detection is only valid with an STT that reports end-of-turn itself (Inworld, Deepgram Flux — not Deepgram Nova-3).
- `auto` speculative trigger resolves by STT: `livekit_preemptive` for STTs whose LiveKit plugin emits *preflight* transcripts (Deepgram, AssemblyAI, Soniox, Cartesia), `transcript_rules` otherwise (Inworld). See Turn-taking for why.

**Config-only, not per-call:**
- **Embedding model.** Vectors from different models aren't comparable, so every stored memory must be embedded with the same model that searches it. Changing it means re-embedding the whole memory table — a deliberate migration, never a dropdown.
- **Memory extraction LLM.** Runs after the call, not selectable from the test UI.

This is also why the implementation-language split matters: the agent worker (Python, where the plugin ecosystem for these vendors is most complete) owns the registry and the actual provider instantiation; Next.js (TypeScript) owns the dropdown UI, auth-gated, and the dispatch call. No custom RPC between them — LiveKit's own dispatch/room APIs are the only channel. The exact dispatch-metadata shape is in Frontend contract.

## Turn-taking: turn detection vs speculative bets

Two separate mechanisms with two different jobs:

| | Speculative trigger ("the bet") | Turn detection ("the commit") |
| --- | --- | --- |
| Job | Start the safety check and script draft early | Decide the user has really finished; release audio |
| Cost of being wrong | A wasted, discarded Groq call | A bot talks over the user |
| Tuned for | Speed; allowed to be wrong | Accuracy |

### Turn detection

Selectable per call (`turn_detector` preset):

- **`livekit_v1` (default)** — LiveKit's audio-based turn detector. It takes raw audio as input, not a transcript: a neural network trained on finished vs. unfinished speech, with a semantic branch (learned to follow word content directly from sound) and an acoustic branch (intonation, rhythm), fused into one end-of-turn probability. It runs once VAD sees ≥0.25s of silence; per-language thresholds turn the probability into a commit. It only uses the STT's detected language to pick the threshold, so it works identically whichever STT is chosen. Served on LiveKit Inference. Supports 14 languages including English, Chinese and Spanish. LiveKit's published benchmark: 9.9% false cutoffs at a 300ms latency budget (Deepgram Flux 12.9%), 4.5% at 600ms (Flux 9.9%) — vendor's own benchmark, not independent.
- **`livekit_v1_mini`** — quantized/pruned v1 running locally on the orchestration server's CPU: no network hop, "most of v1's accuracy" (no separate figures published). Needs compute-optimized instances (AWS c6i/c7i) to avoid timeouts.
- **`stt_native`** — use the STT's own end-of-turn signal (LiveKit `turn_detection="stt"`). Inworld's plugin exposes `min_end_of_turn_silence_when_confident` (default 200ms) and `end_of_turn_confidence_threshold`; no published accuracy figures.

Defaults with the audio model: minimum endpointing delay 0.3s, maximum 2.5s — tunable, and worth tuning on real users' speech — some users pause mid-sentence for longer than average.

### Speculative trigger

**Every bet fires on an event** — a transcript update or a silence event — never on a timer, and never as a prediction of the future. Streaming STT sends its current best guess of the sentence several times a second and revises it as it hears more; each trigger strategy is just a rule for which of those updates is worth betting on. When a bet turns out wrong (the user keeps talking), it's cancelled and a new one may fire at the next plausible ending.

Selectable per call (`speculative_trigger` preset):

1. **`vad_silence`** — bet on whatever the transcript says after a fixed silence (e.g. 150ms). Fewest wasted bets, slowest; ignores the words entirely. Kept as a comparison baseline.
2. **`transcript_debounce_only`** — bet when the transcript stops changing for a short window (e.g. 100ms) and the STT's predicted punctuation looks terminal (`.` `?` `!`).
3. **`transcript_rules`** — #2 plus an instant word-rule check first (table below). Blacklist hit: block the bet. Whitelist hit: fire immediately without waiting for the debounce window. Everything else falls through to #2.
4. **`livekit_preemptive`** — LiveKit's built-in `preemptive_generation`. It doesn't inspect words or silence itself; it fires on the STT's events: every *final* transcript segment (any STT), and additionally on *preflight* transcripts (an early "this looks finished" message that only some STT plugins emit — Deepgram, AssemblyAI, Soniox, Cartesia). Built-in cancel/re-bet, capped by `max_retries` (default 3) and `max_speech_duration` (default 10s).
5. **`auto` (default)** — `livekit_preemptive` with preflight-capable STTs, `transcript_rules` with Inworld. Reason: the Inworld plugin emits no preflight transcripts, and emits its *final* transcript at the same moment it declares end-of-speech (after its own ≥200ms silence rule). With Inworld, `livekit_preemptive` would therefore fire later than our own trigger, which reads Inworld's in-progress interim text.

**`transcript_rules` step by step**, e.g. *"I was just thinking about my sister's coming to visit this weekend, … isn't that nice."* (brief pause after "weekend"):

1. Interim text streams in; each update restarts the stabilization timer.
2. Each update's last word is checked against the rule lists: blacklist → no bet; whitelist → fire now; otherwise → step 3.
3. Text unchanged for the debounce window + terminal punctuation → **fire a bet**.
4. A bet = **safety check + scriptwriter draft, in parallel**, on that exact text. The draft is buffered, never played. (The scriptwriter already has the profile cheat sheet in its prompt; if it calls `recall_memory`, that happens inside the bet — see Memory.)
5. They pause after "weekend" → bet #1 fires. "isn't that nice" arrives → text changed → bet #1 is **cancelled immediately** (Groq stream stopped, so output tokens stop being billed) and the bet counter goes to 1.
6. "…isn't that nice." settles → bet #2 fires. They stay silent.
7. Turn detector commits. If the bet's text matches the final transcript, its draft is used; otherwise it's discarded and a fresh generation starts. Then the safety gate (see sequence diagram).

**Rules for all trigger strategies:**
- **Only one bet in flight.** A new bet always cancels the previous one first.
- **Bet cap: 3 per user turn, plus a 10-second speech cut-off** (both tunable). The counter resets at turn commit. After the cap, no further bets that turn; the reply is generated at turn commit (slower by roughly one LLM first-clause time, covered by the filler).
- **The commit can win the race.** If turn detection commits before any bet has fired (e.g. the STT is slow to deliver the last words), the commit itself triggers generation. No head start that turn; nothing breaks.
- **Metrics per turn**, logged with session/turn id and active presets: bets fired, bets wasted, and time between the used bet firing and turn commit. Defaults get chosen from this data, not guessed.

**Why the cap and rules matter at scale:** a wasted bet costs one scriptwriter call + one safety call (\~$0.00013 for the scriptwriter at the cost model's rates). At \~3 user turns/min and up to 3 wasted bets per turn, that's up to \~0.12¢/min — up to \~10% of the \~1.2¢/min total in the worst case. The goal is the earliest bet with the fewest misses, not the most bets.

| Language | Blacklist (blocks the bet) | Whitelist (fires immediately) |
| --- | --- | --- |
| English | `the`, `a`, `an`, `and`, `but`, `or`, `my`, `your`, `because`, `uh`, `um` — **not** trailing prepositions (`to`, `for`, `with`, `at`, `on`): these are common, grammatical sentence endings in spoken English ("Who's that for?"), blacklisting them would slow down normal speech | Starts with `How`/`What`/`Who`/`Why`/`Are you`/`Can you` + a verb phrase; or ends on a temporal anchor (`today`, `yesterday`, `right now`) or a name (`Paul`, `Gary`) |
| Mandarin | Trailing `的` (de), `和` (he, "and"), `因为` (yinwei, "because") — unfinished connectors/particles | Ends on a sentence-final particle: `了` (le), `吗` (ma), `呢` (ne), `吧` (ba) — these grammatically sit almost exclusively at true clause boundaries, arguably a stronger signal than any English rule |
| Spanish | Trailing bare article (`el`, `la`, `los`, `las`, `un`, `una`); trailing `y` (and), `pero` (but), `porque` (because) | Starts with `¿Qué`, `¿Cómo`, `¿Quién`, `¿Por qué`, or inverted-question form |

**Be honest about what the rule layer buys you:** it only resolves the clear-cut edges of the distribution — obviously-unfinished trailing tokens, and short obviously-complete utterances (greetings, simple questions). Most real conversational sentences are neither blacklisted nor whitelisted and still fall through to the debounce+punctuation baseline, which stays the primary mechanism, not a rare fallback. Treat the rule layer as a cheap accelerant that reduces wasted/wrong bets on the edges, not a replacement for the baseline. The stabilization thresholds were originally reasoned about against Deepgram's interim-result behaviour and must be re-validated against Inworld's actual output.

## Sequence diagram

The safety check runs **alongside** the speculative script draft, not in front of it. Long-term memory is not in the parallel block: the cheat sheet is already in the prompt, and a Tier 2 lookup only happens if the scriptwriter asks for one. If safety trips, the `alt` branch swaps in a pre-cached disclaimer instead of the real script.

```mermaid
sequenceDiagram
    participant Usr as User
    participant STT as Inworld STT
    participant TD as Turn detector (LiveKit v1)
    participant Bet as Speculative trigger
    participant Safe as Groq Safeguard-20B
    participant LLM as Groq GPT-OSS-20B (scriptwriter)
    participant Mem as recall_memory (embed + pgvector)
    participant Fill as Filler/disclaimer cache
    participant TTS as Inworld TTS Flash (per bot)
    participant Out as Per-bot audio router

    Usr->>STT: audio (continuous)
    Usr->>TD: audio (continuous)
    STT-->>Bet: interim transcripts
    Bet-->>Bet: rules + stabilization → fire bet
    par Safety check
        Bet->>Safe: transcript
        Safe-->>Safe: policy classify
    and Script draft
        Bet->>LLM: transcript + cheat sheet + rolling buffer
        opt Scriptwriter needs older memory
            LLM->>Mem: recall_memory(query)
            Mem-->>LLM: matching core facts
            LLM-->>LLM: second request with facts (automatic)
        end
        LLM-->>LLM: draft script, buffered
    end
    TD-->>Bet: turn committed
    alt Safety clear, bet matches final transcript
        par Filler track
            Fill-->>Usr: cached filler audio
        and Real response track
            LLM->>TTS: release buffered per-bot segments
            TTS->>Out: audio frames tagged with bot_id
            Out-->>Usr: one track per bot
        end
    else Safety tripped, errored or timed out
        Fill-->>Usr: pre-cached disclaimer, real script discarded
    else No usable bet (stale or none fired)
        Bet->>LLM: generate fresh from final transcript (then as above)
    end
```

Reading it: the bet starts safety and the script draft the moment the transcript settles, and neither waits for the other. Turn-detection commits on its own clock in parallel. Only once it commits does the `alt` gate fire: safety's verdict decides whether the buffered script or the disclaimer gets released to audio. The safety gate fails closed — an error, timeout or unparseable verdict is treated as "unclear" and plays the disclaimer.

## Latency budget — concrete example

User says: *"Oh you know, I was just thinking about my sister's coming to visit this weekend, isn't that nice."* `T=0` = the user stops speaking.

| Time | Event |
| --- | --- |
| before the call's first turn | Profile cheat sheet loaded from Supabase into Redis/prompt at session start — not per turn |
| throughout utterance | Inworld STT streams interim transcripts (interim cadence not yet validated — see Engineering flags); a bet may fire and be cancelled at the pause after "weekend" |
| T ≈ 0 to +100ms | Last words land in the transcript (depends on STT interim latency); text settles → bet fires: safety + script draft in parallel |
| T ≈ bet + low tens of ms | Safety verdict lands (Groq API round-trip, realistically low tens of ms, not <15ms) |
| T ≈ bet + TTFT + \~1ms/token | Script draft's first clause buffered |
| T ≈ +300ms or later | Turn detector commits (v1: ≥0.25s VAD silence, default minimum endpointing delay 0.3s, tunable) |
| T ≈ turn-commit | Safety verdict already sitting there → `alt` gate fires immediately; cached filler dispatched (0ms compute) **and** buffered script released to Inworld TTS Flash, same instant |
| T ≈ turn-commit +20–80ms | Filler audio reaches the user — first-audible-sound, comfortably inside 300ms from turn-commit |
| T ≈ turn-commit +80–150ms | Inworld TTS Flash TTFB lands, real audio streams in behind the filler |

The earlier version of this table had the bet firing at T ≈ −130ms, i.e. before the user stopped speaking. That isn't achievable: a bet can only contain words the STT has already transcribed, and transcription always trails speech. The head start that matters is bet-to-commit (here roughly 200ms), not bet-to-end-of-speech.

The load-bearing assumption: **the bet fires and the safety verdict lands before turn-detection commits**, so they're free by the time you need them. If the bet is late, the commit triggers generation itself and that turn loses its head start. Turns where the scriptwriter calls `recall_memory` pay extra (one embedding + one pgvector query + a second LLM request, roughly +150–300ms, estimate); if that's still pending at commit, the "thinking" filler covers it (see Memory).

## Memory

### Reading memory during a call

- **Tier 1 — profile cheat sheet (preloaded).** At session start, the backend builds a cheat sheet from Supabase and holds it in Redis for the call: the highest-importance core facts plus the most recent session summaries, filtered per bot to what that bot witnessed (see sharing rules below). It goes into every scriptwriter prompt. Well-engineered, this covers most turns without any lookup.
- **Tier 2 — `recall_memory` tool (on demand).** The scriptwriter is given a `recall_memory(query, other_bot=None)` tool and calls it only when the cheat sheet and rolling buffer don't answer the turn. LiveKit Agents runs the tool and makes the second LLM request automatically; `max_tool_steps=1` limits it to one lookup per turn. The prompt must be firm that the tool is for gaps only; tool-call rate is logged per session so over-calling can be measured and tuned.
  - Lookup = embed the query with the self-hosted embedding model → exact vector search over that user's core facts that the calling bot witnessed (see Database schema).
  - The safety verdict from the first request carries over; safety is not re-run for the tool's second request (the user's words haven't changed).
  - **"Thinking" filler:** if a lookup is still pending at turn commit, a thinking filler plays instead of the normal one ("Hmm, let me think…"). A lookup that finishes inside the bet, before commit, is inaudible.
- **Tier 3 — rolling buffer.** Last 10–15 messages of the current call, injected directly into the prompt.

### Sharing memory between bots

Memories belong to the user but are **scoped to the bots that witnessed them** (were in the room when it was said).

- A bot's cheat sheet and default `recall_memory` searches only include memories that bot witnessed.
- If the user asks a bot about something they only told a different bot, the bot says it doesn't recall and **offers to ask the other bot**: *"I don't recall you mentioning it, but I can ask Jason if you like?"*
- Only after the user agrees does the bot call `recall_memory(query, other_bot="jason")`, and it answers with attribution: *"Jason says it was Luigi's on Crown Street!"* A bot never volunteers another bot's memories unprompted.
- If the other bot is in the same room, the scriptwriter can simply have that bot answer.

### Writing memory: post-call extraction

When a call ends, an async job processes that call's transcript (per session, not per 24 hours — so memories are available minutes later, and every extracted fact inherits the session's set of bots as its witnesses):

1. Load the session's messages and the user's existing related core facts.
2. A cheap LLM extracts **atomic core facts** — standalone sentences about the user (preferences, people, places, health, emotional triggers), including entities mentioned only once — and a **session summary**.
3. Rules for extraction: only facts the **user** stated or confirmed (never bot-invented content); relative dates resolved to absolute dates (`occurred_at`); an **importance** score per fact (drives the cheat sheet); structured JSON output validated against a typed schema, rejected and retried if malformed.
4. For each candidate fact the LLM returns **ADD** (new), **UPDATE** (changes an existing fact — the old one gets `superseded_by`), or **SKIP** (already known), to prevent nightly-style duplication and contradictions.
5. Embed new/updated facts and write them with their witness rows.

The job is idempotent per session id, so a failed run can be retried safely. Where it runs (end-of-call hook in the agent worker vs. a separate job queue) is an implementation choice, to be decided when it's built.

### Embeddings

pgvector stores vectors and finds the nearest ones; it does not create them. The self-hosted embedding model (stack layer 12) turns text into vectors both at write time (extraction job) and at read time (`recall_memory`). One model for all stored vectors; its dimension fixes the column size; each row records which model produced it.

## Database schema (owned by the backend repo)

**Ownership, now that this is split into a frontend and backend repo:** the actual Supabase Postgres schema and its migrations live in and are applied from the **backend** repo (`supabase/migrations/`), even though both repos read/write this database — backend for memory and transcripts, frontend for user accounts, room/session history, and anything else user-facing. One schema, one place migrations are written and applied, so two independently-edited repos don't drift apart on what the tables actually look like.

The frontend repo consumes the schema through Supabase's generated TypeScript types (`supabase gen types typescript`), regenerated after any schema change — never hand-typed to match an assumption about what a table looks like. If frontend work surfaces a need for a new table or column, the shape gets drafted and added as a migration in the backend repo, then frontend's types get regenerated from the live schema.

### Naming convention

**Every table and column is snake_case**, with no exceptions for third-party libraries. Application code may use other conventions (e.g. camelCase in TypeScript) only through its own mapping layer.

**Names are product-neutral:** tables, columns, enum values and seed data describe the generic product (the person in a call is a `user`), never a specific audience.

### Auth tables — custom Auth.js adapter

Login is handled by **Auth.js in the frontend** (a JavaScript library; the Python backend never uses it — it receives the user's `user_id` in dispatch metadata). Providers: Google + email/password (Credentials), with **JWT sessions** — the same setup as the sports-finder-app.

Auth.js never touches the database itself; it passes camelCase JavaScript objects (`emailVerified`, `providerAccountId`, …) to a **database adapter**. The off-the-shelf adapters (`@auth/pg-adapter`, `@auth/supabase-adapter`) hard-code camelCase column names, and the ORM-based ones (Prisma, Drizzle) would add a second database library to the frontend whose table definitions must be hand-synced with the migrations here. Neither is acceptable, so **the frontend implements a small custom adapter** on `supabase-js`, typed from the generated Supabase types, that maps Auth.js's objects onto these snake_case tables. With JWT sessions and no email-verification flow, it only needs the user and account methods (roughly `createUser`, `getUser`, `getUserByEmail`, `getUserByAccount`, `updateUser`, `linkAccount`); session methods are never called.

Draft (not yet a migration):

```sql
CREATE TYPE user_role AS ENUM ('admin', 'user');

CREATE TABLE users (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text,                          -- nullable: not every OAuth profile provides one
    email          text        NOT NULL,
    email_verified timestamptz,                   -- set by Auth.js for OAuth sign-ins
    image          text,
    password_hash  text,                          -- null for Google-only accounts
    role           user_role   NOT NULL DEFAULT 'user',  -- admin: unlimited bots per call (testing)
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()    -- maintained by a trigger
);
CREATE UNIQUE INDEX users_email_key ON users (lower(email));

-- One row per OAuth provider login linked to a user (e.g. their Google account).
-- Token columns mirror the OAuth fields Auth.js passes through.
CREATE TABLE accounts (
    id                  uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid    NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    type                text    NOT NULL,
    provider            text    NOT NULL,
    provider_account_id text    NOT NULL,
    refresh_token       text,
    access_token        text,
    expires_at          bigint,
    token_type          text,
    scope               text,
    id_token            text,
    session_state       text,
    UNIQUE (provider, provider_account_id)
);
CREATE INDEX accounts_user_id_idx ON accounts (user_id);
```

- **No `sessions` table** — JWT sessions never use it. Add one only if the app moves to database sessions.
- **No `verification_tokens` table** — only needed for email verification or magic-link sign-in; add it with that feature.
- `user_id` is always the end user (the person talking to the bots); every other table's `user_id` references `users (id)`.

**RLS is mandatory:** Supabase exposes `public` tables through its API, so every table — especially `users` with `password_hash` — has RLS enabled. With Auth.js (not Supabase Auth), Supabase's `auth.uid()` doesn't work out of the box; until user-facing policies are designed, tables are accessed only server-side (frontend with the service-role key, backend over a direct Postgres connection) and RLS denies everything else.

### Draft — memory tables (not yet a migration)

`user_id` is always the end user (the person talking to the bots) and references `users (id)`. Referenced tables marked TBD (sessions, bots) aren't designed yet.

```sql
CREATE TYPE memory_type AS ENUM ('core_fact', 'session_summary');

CREATE TABLE memories (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL,              -- the end user; FK TBD
    session_id      uuid,                              -- call it came from; FK to sessions TBD
    type            memory_type NOT NULL,
    memory_text     text        NOT NULL,
    importance      smallint    CHECK (importance BETWEEN 1 AND 10),  -- core facts; drives the cheat sheet
    embedding       halfvec(768),                      -- dimension fixed by the chosen embedding model
    embedding_model text,
    occurred_at     timestamptz,                       -- when the event happened, not when stored
    created_at      timestamptz NOT NULL DEFAULT now(),
    superseded_by   uuid,                              -- set when a later fact replaces this one
    PRIMARY KEY (user_id, id),                         -- partition key must be part of the PK
    CHECK (type <> 'core_fact' OR embedding IS NOT NULL)
) PARTITION BY HASH (user_id);

-- Which bots were present when a memory was said (the sharing rule).
-- A join table rather than an array column so bot_id can be a real foreign key.
CREATE TABLE memory_witnesses (
    user_id   uuid NOT NULL,
    memory_id uuid NOT NULL,
    bot_id    uuid NOT NULL,                           -- FK to bots TBD
    PRIMARY KEY (user_id, memory_id, bot_id),
    FOREIGN KEY (user_id, memory_id) REFERENCES memories (user_id, id) ON DELETE CASCADE
);

-- recall_memory: exact search, scoped to one user + one bot
SELECT m.memory_text, m.occurred_at
FROM memories m
JOIN memory_witnesses w ON w.user_id = m.user_id AND w.memory_id = m.id
WHERE m.user_id = $1 AND w.bot_id = $2
  AND m.type = 'core_fact' AND m.superseded_by IS NULL
ORDER BY m.embedding <=> $3
LIMIT 5;
```

A `messages` (transcript) table is also needed — session, speaker (the user or which bot), text, timestamp, same `user_id` hash partitioning. For bot turns it stores what was actually **heard** (LiveKit reports the synchronized transcript when speech is interrupted), not the full generated script. **Raw transcripts are kept indefinitely for now.**

**Indexing and performance decisions:**
- **Exact vector search per user, no HNSW (for now).** pgvector applies `WHERE` filters *after* an HNSW index scan (default `hnsw.ef_search` = 40 candidates), so an HNSW index shared by many users would, for one user, return few or no rows. A single user's history is thousands of rows, not millions, so the primary key's `user_id` prefix narrows to that user's rows and Postgres computes exact distances on them — 100% recall, expected low-single-digit ms (to be benchmarked). HNSW (with pgvector ≥0.8 iterative scans) is only worth revisiting if individual histories grow very large.
- **Hash partitioning by `user_id`** — for maintenance (smaller per-partition indexes, faster vacuum) and cache locality, not for vector-search correctness. Cheap to set up now, expensive to retrofit onto a large live table. Partition count TBD.
- **`halfvec`** — half-precision storage halves table and index size with negligible recall loss.
- **Persistent connection pool** from the Sydney orchestration server to Supabase (Sydney), so no lookup pays connection setup.

**Also needed, not yet drafted:** bots (the roster), sessions (bots present, presets used, start/end). RLS policies TBD — memories and transcripts hold sensitive personal and health information and must not be freely readable from the browser.

**Future, not now:** delegated access to a user's memories (e.g. by a family member) — an additive access table linking another account to that user; no change to the memory tables.

Once finalized, the schema itself stays documented here, so both repos' copies of this doc stay in sync when it changes.

## Multi-bot audio output

One LLM writes the script for all bots; the backend splits it into per-bot segments, synthesizes each bot's segments with that bot's voice (parallel Inworld TTS streams), and publishes each bot on its own audio track. The browser plays all tracks; overlaps blend naturally.

**Design (pending prototype):** one `AgentSession`, one agent participant, **one audio track per bot**, named `bot:<bot_id>`.

- `AgentSession` keeps the input side and the machinery it provides: STT, turn detection, speculative/preemptive generation, the automatic tool loop, barge-in handling, and fillers. Our scriptwriter replaces its LLM step (`llm_node`).
- Its audio output (`session.output.audio`) is a documented, replaceable component. We replace the default single-track output with a **per-bot router**: our TTS step tags every audio frame with its `bot_id` in the frame's `userdata`, and the router pushes each frame onto that bot's track.
- **Barge-in:** when the user interrupts, the router's clear/stop empties **all** bot tracks at once — including during a banter overlap.
- **Speaking indicator:** LiveKit's built-in active-speaker detection is per *participant*, so it can't tell bots on one participant apart. The router knows exactly when it starts and stops each bot's audio and sends `bot_speaking` data messages (see Frontend contract).
- **Captions (optional):** LiveKit Agents' transcript stream is synchronized to audio playback and can be attributed to a specific track — per-bot captions, useful for accessibility (users with hearing difficulties).
- **Unverified, first thing the prototype checks:** that the `userdata` tag survives every pipeline stage from the TTS step to the output. LiveKit's own source relies on the same mechanism to carry transcript timing, which strongly suggests it does.

This replaces the earlier recommendation of one LiveKit participant per bot: per-bot track names make each bot addressable for the fade and the speaking indicator without a second room connection per bot.

## Bot-to-bot interruption (banter)

Requested: bots should be able to cut each other off mid-sentence the way people do — Gary bragging about tomatoes, Paul barging in with "Hold your horses, young man..." — with both voices audibly overlapping for a beat before Gary's line fades out.

**Correction to the proposed mechanism:** LiveKit's SFU does not mix audio server-side — it "forwards a copy of each track to each subscriber without manipulating the underlying packets." There is no LiveKit "mixer channel" to route into. Two bot tracks subscribed and unmuted at the same time already blend automatically in the listener's browser, for free — that part needs no engineering. What has to be built is everything that controls *when* the overlap starts and *how it ends*.

**The real difficulty is playback-timing sync, not prompt engineering.** The scriptwriter LLM generates text far faster than TTS audio is actually heard (clause-level streaming means the LLM may already be writing clause 3 while the user is still hearing clause 1). An `[INTERRUPT: BOT_NAME]` tag firing at LLM-token time would cut Paul in far too early relative to what's actually audible. The trigger has to be anchored to Gary's **audio playback position**, not his text-generation position.

Three separate layers, only one of which is prompting:

1. **LLM (prompt engineering).** The scriptwriter writes structured per-speaker segments and, for banter, tags where the interrupter cuts in — then simply stops writing the rest of the interrupted bot's line. "How much of Gary's sentence gets said" falls out of content generation for free; no extra tagging of duration needed.
2. **Backend scheduling (new work), and the part that actually owns timing.** Generate both segments' audio essentially immediately in parallel — Gary's segment streams to TTS as normal, and the interrupting bot's line is fully synthesized right away too, then held in a buffer rather than generated cold at the interrupt moment. That decouples TTS-generation speed from the trigger: the only thing that has to happen precisely on time is starting playback of audio that already exists. The backend tracks Gary's actual dispatched-audio duration in real time and, at the computed offset, pushes the buffered interrupt audio directly onto the interrupting bot's track (alongside the per-bot router, which is still streaming Gary). LiveKit itself never decides any of this — it's a blind router that forwards whatever frames it's given, the instant they're pushed, with no awareness that an interruption is happening; all the timing intelligence lives in this backend logic.
3. **The 350ms fade (new work, not a LiveKit feature).** With no server-side mixer, this has to happen client-side: the agent sends a `bot_fade` data message the instant it starts the interrupting bot's audio, and the frontend runs a Web Audio `GainNode` ramp on the interrupted bot's track (`bot:<bot_id>`) down over the fade window. Doing sample-level gain processing inside the Python agent would add real CPU work to the hot path for no benefit over doing it in the browser.

The browser never decides *when* an interruption happens — it only executes the fade the instant it's told to, on a cue the backend sends. All timing intelligence — both segments' pre-generated audio, the trigger moment, and the fade cue — lives in one place: the backend.

**Previously open questions, now resolved:**

- **Barge-in during an overlap.** The per-bot router's stop clears every bot track, so an overlap ducks/stops the same way a single bot does (see Multi-bot audio output).
- **Bot track identity.** One agent participant with one named track per bot (see Multi-bot audio output), pending prototype.

**N > 2 bots (admin testing only):** the scheduler handles one interruption at a time between any two bots; no additional mechanism for larger groups.

**350ms is a starting default, not a validated number.** It should be a tunable parameter, confirmed by ear once real TTS latency and real playback are in the loop — not treated as a spec to hit exactly.

## Frontend contract

Everything the frontend repo must implement to match this backend. Field and message names are provisional until the first backend prototype confirms them; changes are made here first.

**Dispatch metadata** (JSON string in `createDispatch(...)`'s `metadata`, created server-side only):

```json
{
  "user_id": "<user's id>",
  "bots": ["<bot_id>", "<bot_id>"],
  "presets": {
    "stt": "inworld_stt1",
    "tts": "inworld_flash",
    "llm": "groq_gptoss20b",
    "turn_detector": "livekit_v1",
    "speculative_trigger": "auto"
  }
}
```

**Room setup:**
- Dropdowns for all five presets (see Design requirement: pluggable providers), with the compatibility rules applied: grey out `stt_native` for STTs without end-of-turn support; show `auto` as the recommended trigger.
- Bot selection: max 2 for regular users, unlimited for admins; enforced in the UI and in the server-side dispatch code. The backend re-checks against the user's role and rejects the session if violated.

**In the call:**
- Bot audio arrives from the single agent participant as **one audio track per bot**, track name `bot:<bot_id>`.
- Data messages from the agent (topic `bot_events`):
  - `{"type": "bot_speaking", "bot": "<bot_id>", "speaking": true | false}` — drives the "who's talking" highlight. LiveKit's built-in active-speaker events can't be used for this: they're per participant, and all bots share one participant.
  - `{"type": "bot_fade", "bot": "<bot_id>", "duration_ms": 350}` — run a Web Audio `GainNode` ramp to silence on that bot's track over `duration_ms`.
- Optional: per-bot captions from LiveKit's synchronized transcript stream.

**Database:**
- Regenerate Supabase types after every backend migration.
- Auth.js uses a **custom adapter** on `supabase-js` mapping its objects onto the snake_case `users` / `accounts` tables (see Database schema → Auth tables). No ORM in the frontend.

## Cost model — worked example

Same assumptions as before, updated for the max room size: user + 2 bots: 1 minute of active session, bots collectively speaking \~40% of wall-clock time, on-demand pricing, no volume discounts.

| Line item | Basis | Cost/min |
| --- | --- | --- |
| Frontend (Vercel) | Free tier, not per-minute | $0.0000 |
| LiveKit Cloud (transport) | \~2 participant-minutes × $0.0005 | $0.0010 |
| Orchestration server (Sydney) | Small always-on instance, amortized across concurrent calls — **implementation-dependent estimate**, not a vendor quote | \~$0.0015 |
| Inworld STT (`inworld-stt-1`) | $0.10–0.15/hr (paid/on-demand) → $0.0017–0.0025/min; conservative on-demand figure used | $0.0025 |
| Groq Safeguard-20B (safety) | \~3–5 short calls/min, negligible token volume | \~$0.0002 |
| Groq GPT-OSS-20B (scriptwriter) | \~3 calls/min, \~800 in / \~80 out tokens | \~$0.0004 |
| Redis (Tier 1) | Low/free tier until scale, amortized fixed fee | \~$0.0005 |
| Supabase + pgvector (Tier 2) | Free tier until scale, amortized fixed fee — **must move to paid before launch, see Engineering flags** | \~$0.0005 |
| Inworld TTS-2 Flash | 40% × 930 chars/min × $15/1M chars | $0.0056 |
| **Total** |  | **\~$0.0122/min (≈1.2¢)** |

Still roughly 59% under the 3¢ ceiling — more margin than before, since Inworld's STT pricing is lower per minute than Deepgram's despite adding voice-profiling. The two database lines (Redis, Supabase) are the only structurally different cost shape here — they're flat/tiered vendor fees, not per-minute usage APIs, so the $/min figures above are your amortization, not a quote; they'll actually get *cheaper* per minute as concurrent usage grows, unlike the STT/TTS lines which scale linearly with usage.

**Not yet in the table (to be measured, not guessed):**
- **Wasted speculative bets** — up to \~0.12¢/min worst case (see Turn-taking); the bet cap and rules exist to keep it well below that.
- **`recall_memory` turns** — a second scriptwriter request on the turns that use it.
- **Post-call extraction** — one cheap-LLM pass per call over its transcript; small, off the hot path.
- **Self-hosted embedding model and `livekit_v1_mini`** — CPU on the orchestration server; may require a larger or compute-optimized instance (c6i/c7i) than the "small instance" assumed above.

## Engineering flags — corrections before you build

- **"<15ms for the safety pass" isn't realistic for a network call to Groq, but the fix is architectural, not a vendor swap.** Even at Groq's speeds, an API round-trip (TLS, serialization, queueing) plus inference realistically lands in the low tens of ms, not single digits. The fix: run the safety check **in parallel with the speculative scriptwriter draft**, not serially in front of it (see the sequence diagram). The real constraint isn't "under 15ms" — it's "finishes before turn-detection commits."
- **"Under 50ms Groq inference" holds only for short outputs.** GPT-OSS-20B runs at \~1,000 tok/s on Groq — that's 1ms/token. 50ms of *generation* time caps you at roughly 50 output tokens (about two short bot lines with tags), before TTFT/prefill is even counted. If the scriptwriter needs to write full lines for 2 bots with tags in one pass, budget closer to 100–150ms of generation alone. Doesn't break the design, but the 1,500-token ceiling in the brief is really an *input* budget — the output budget needs its own, tighter cap.
- **The speculative bet cannot fire before the user stops speaking** (the brief's T ≈ −130ms). A bet only contains transcribed words, and transcription trails speech. Realistically it fires at T ≈ 0 to +100ms, still well ahead of turn commit (≥ +300ms with default settings). See Latency budget.
- **"Tier 2 recall (if ready in time)" in the original sequence diagram can't work.** An LLM request can't accept new input once started, so a lookup running in parallel with the scriptwriter would always arrive too late. Replaced by the preloaded cheat sheet + `recall_memory` tool (see Memory).
- **Supabase free tier is a real reliability risk for anything past prototype.** Free-tier Postgres projects have historically paused after a period of inactivity and sit on shared infrastructure with less predictable latency. Tier 2 is now off the per-turn critical path, but the cheat-sheet load at session start and `recall_memory` turns still depend on it. Fine to build on for now; budget for the paid tier before any real user is talking to this.
- **"Sub-30ms LiveKit edge transit" is stated as a target, not a sourced figure.** LiveKit Cloud does have an Australia region (confirmed), but no published number for edge transit time specifically — treat this as something to measure once you have a test room running, not a given.
- **Regulatory line (Privacy Act ADM updates, Digital Duty of Care) — flagging, not advising.** This is outside what I can responsibly confirm as current or complete, and it's a compliance question, not an infrastructure one. Get this in front of an actual Australian privacy lawyer before launch rather than building against my or any AI's summary of it. Note that the memory extraction job deliberately stores health information (allergies) and emotional triggers, and raw transcripts are kept indefinitely — both are squarely in scope for that review.
- **One thing that checks out cleanly:** the non-verbal tags named in the brief (`[sigh]`, `[laugh]`, `[chuckle]`) match what Inworld TTS-2 Flash actually supports — Flash renders non-verbal tags but not the broader emotional-steering tags (`[say excitedly]`, etc.). The brief is already scoped correctly here; no change needed.
- **STT is currently Inworld (`inworld-stt-1`), swapped in for its acoustic voice-profiling — this is provisional, not settled.** No confirmed Australia/APAC endpoint exists for Inworld, unlike Deepgram's confirmed `api.au.deepgram.com`. Test real round-trip latency from Sydney before building further on it; revert to Deepgram Nova-3 if it comes back materially worse. Inworld *does* expose end-of-turn settings through its LiveKit plugin, but it emits no preflight transcripts, and its semantic VAD (Silero + Smart Turn) is documented only for its Realtime API, not standalone STT.
- **The swap invalidates prior timing assumptions, not just infrastructure.** The debounce/punctuation-based stabilization trigger was reasoned about around Deepgram's interim-result and predicted-punctuation behaviour. Inworld's interim-result cadence is now the number that most decides how early a bet can fire, and must be measured.
- **Unverified, to check during implementation:**
  - Whether LiveKit Turn Detector v1 (served on LiveKit Inference) is free for a self-hosted agent connected to LiveKit Cloud, and its round-trip time from Sydney. `livekit_v1_mini` avoids both questions.
  - LiveKit's turn-detection benchmarks are the vendor's own, not independent.
  - That audio-frame `userdata` tags survive the whole `AgentSession` output path (first prototype check — see Multi-bot audio output).
  - Groq: whether tool calls stream for `gpt-oss-20b` (tool use is supported, parallel tool calls are not), whether prompt caching applies to it (would shrink the `recall_memory` second request), and account rate limits under speculative-bet load.
  - Embedding model CPU latency on the target instance type.
  - Exact-search latency for a realistic per-user history size (benchmark before relying on "low-single-digit ms").

## Sources

- [LiveKit — solving end-of-turn detection (Turn Detector v1)](https://livekit.com/blog/solving-end-of-turn-detection)
- [LiveKit — turn-detector docs (v1 vs v1-mini)](https://docs.livekit.io/agents/logic/turns/turn-detector/)
- [LiveKit — turns overview](https://docs.livekit.io/agents/logic/turns/)
- [LiveKit — configuring turn detection and interruptions](https://livekit.com/blog/turn-detection-and-interruption-handling)
- [LiveKit — Inworld STT plugin](https://docs.livekit.io/agents/models/stt/inworld/)
- [LiveKit Agents source (preemptive generation, AudioOutput, Inworld plugin)](https://github.com/livekit/agents)
- [LiveKit — Cloud pricing](https://livekit.com/pricing)
- [LiveKit — regions and endpoints](https://docs.livekit.io/deploy/admin/regions/endpoints/)
- [Groq — tool use](https://console.groq.com/docs/tool-use)
- [Groq — pricing overview](https://www.eesel.ai/blog/groq-pricing)
- [Groq — Asia-Pacific/Sydney data center announcement](https://groq.com/newsroom/groq-expands-to-asia-pacific-with-sydney-data-center-to-power-the-next-generation-of-ai-inference)
- [pgvector — README (filtering, iterative scans, halfvec)](https://github.com/pgvector/pgvector)
- [Deepgram — Australia endpoint GA](https://deepgram.com/learn/deepgram-australia-endpoint-now-generally-available)
- [Deepgram Flux vs Nova-3 semantic endpointing](https://www.autointerviewai.com/blog/deepgram-flux-semantic-end-of-turn-stt-review-2026)
- [Inworld — what is semantic VAD](https://inworld.ai/resources/what-is-semantic-vad)
- [Inworld — TTS-2 tag support docs](https://docs.inworld.ai/tts/best-practices/prompting-for-tts-2)
- [Inworld — voice agent cost-per-minute model](https://inworld.ai/resources/voice-agent-cost-per-minute-2026)
