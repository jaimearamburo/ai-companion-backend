-- The bot roster and its immutable versions, calls (sessions) and which bot
-- versions were in them, call transcripts (messages), and each user's
-- relationship with each bot.
-- See ARCHITECTURE.md → Database schema → Calls, bots and transcripts.
--
-- Apply manually in the Supabase SQL editor (see supabase/README.md). The whole
-- file runs in one transaction: if any statement fails, nothing is applied.

BEGIN;

-- --- Bots: the roster of companion characters --------------------------------
-- A reference table: other tables point to it. Bots are never deleted (their
-- history refers to them); retire one with is_active = false. This table holds
-- what the room-setup screen shows; what the bot says and how it behaves lives
-- in bot_versions.
CREATE TABLE public.bots (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Short fixed identifier used in code and logs, e.g. 'gary'.
    slug           text        NOT NULL UNIQUE,
    display_name   text        NOT NULL,
    -- Short bio shown on the room-setup screen.
    ui_description text        NOT NULL DEFAULT '',
    avatar_url     text,
    is_active      boolean     NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bots_slug_format CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    CONSTRAINT bots_display_name_not_blank CHECK (btrim(display_name) <> ''),
    CONSTRAINT bots_avatar_url_https CHECK (avatar_url IS NULL OR avatar_url ~ '^https://\S+$')
);

CREATE TRIGGER bots_set_updated_at
    BEFORE UPDATE ON public.bots
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- --- Bot versions: what each bot says and how it behaves ---------------------------
-- Append-only: editing a bot means inserting its next version. A release pins
-- version IDs, so rolling back restores exactly the persona it shipped with,
-- and session_bots records which version took part in each call.
CREATE TABLE public.bot_versions (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id         uuid        NOT NULL REFERENCES public.bots (id) ON DELETE RESTRICT,
    version        integer     NOT NULL,
    -- The personality text the scriptwriter reads for this bot.
    persona_prompt text        NOT NULL,
    -- Voice per TTS preset, e.g. {"fish_s21_hosted": "<voice id>"}: each TTS
    -- vendor has its own voice IDs, and the vendor is chosen per region.
    voices         jsonb       NOT NULL,
    -- Tool names the bot may call; validated against the known tools on load.
    allowed_tools  text[]      NOT NULL DEFAULT '{}',
    -- Settings objects; missing keys take the defaults in the bot model.
    memory_policy  jsonb       NOT NULL DEFAULT '{}',
    safety_rules   jsonb       NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bot_versions_bot_version_key UNIQUE (bot_id, version),
    -- Lets session_bots reference (bot_id, id) together, which guarantees the
    -- recorded version belongs to the recorded bot.
    CONSTRAINT bot_versions_bot_id_id_key UNIQUE (bot_id, id),
    CONSTRAINT bot_versions_version_positive CHECK (version >= 1),
    CONSTRAINT bot_versions_persona_not_blank CHECK (btrim(persona_prompt) <> ''),
    CONSTRAINT bot_versions_voices_not_empty CHECK (jsonb_typeof(voices) = 'object' AND voices <> '{}'::jsonb),
    CONSTRAINT bot_versions_memory_policy_object CHECK (jsonb_typeof(memory_policy) = 'object'),
    CONSTRAINT bot_versions_safety_rules_object CHECK (jsonb_typeof(safety_rules) = 'object')
);

-- Rejects any change to a row of an append-only table. Uses its own error code
-- (restrict_violation) so callers can tell it apart from other failures.
CREATE FUNCTION public.reject_row_change() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER bot_versions_append_only
    BEFORE UPDATE OR DELETE ON public.bot_versions
    FOR EACH ROW EXECUTE FUNCTION public.reject_row_change();

-- --- Sessions: one row per call ------------------------------------------------
CREATE TYPE public.session_status AS ENUM ('active', 'ended', 'failed');
-- Which regional infrastructure served the call (ARCHITECTURE.md → Regions).
CREATE TYPE public.region AS ENUM ('au', 'us');

CREATE TABLE public.sessions (
    id                   uuid                  PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Deleting a user deletes their calls (and, through them, the transcripts).
    user_id              uuid                  NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    livekit_room_name    text                  NOT NULL UNIQUE,
    region               public.region         NOT NULL,
    -- The user's room-setup choice: may bots forget specific memories when asked?
    memory_deletion_enabled boolean            NOT NULL DEFAULT false,
    status               public.session_status NOT NULL DEFAULT 'active',
    -- Why the call ended, e.g. 'user_hung_up', 'error' (free text, for logs).
    end_reason           text,
    -- The provider presets chosen for this call (see ARCHITECTURE.md → presets).
    stt_preset           text                  NOT NULL,
    tts_preset           text                  NOT NULL,
    llm_preset           text                  NOT NULL,
    safety_preset        text                  NOT NULL,
    turn_detector_preset text                  NOT NULL,
    trigger_preset       text                  NOT NULL,
    started_at           timestamptz           NOT NULL DEFAULT now(),
    ended_at             timestamptz,
    CONSTRAINT sessions_ended_after_start CHECK (ended_at IS NULL OR ended_at >= started_at),
    -- An ended or failed call has an end time; an active one doesn't.
    CONSTRAINT sessions_end_matches_status CHECK ((status = 'active') = (ended_at IS NULL)),
    -- Lets child tables reference (user_id, id) together, which guarantees a
    -- child row belongs to the same user as its session.
    CONSTRAINT sessions_user_id_id_key UNIQUE (user_id, id)
);

-- "A user's calls, newest first" (call history).
CREATE INDEX sessions_user_started_idx ON public.sessions (user_id, started_at DESC);

-- --- Session bots: which bots were in each call ---------------------------------
-- Junction table for the many-to-many between sessions and bots. The source of
-- truth for "who was in the room", later copied into memory witnesses.
CREATE TABLE public.session_bots (
    session_id     uuid NOT NULL REFERENCES public.sessions (id) ON DELETE CASCADE,
    bot_id         uuid NOT NULL REFERENCES public.bots (id) ON DELETE RESTRICT,
    -- The exact version that took part, so the call can be reproduced later.
    bot_version_id uuid NOT NULL,
    PRIMARY KEY (session_id, bot_id),
    FOREIGN KEY (bot_id, bot_version_id) REFERENCES public.bot_versions (bot_id, id) ON DELETE RESTRICT
);

-- "Which calls was this bot in" (the primary key only covers session-first lookups).
CREATE INDEX session_bots_bot_idx ON public.session_bots (bot_id);

-- --- Messages: call transcripts ----------------------------------------------------
-- One row per spoken line. For bots, the text is what was actually heard: if the
-- user interrupted, only the part that played is stored (interrupted = true).
CREATE TYPE public.speaker_type AS ENUM ('user', 'bot');

-- Hash-partitioned by user_id: the table is split into 16 sub-tables, and each
-- user's rows always live in the same one. Queries for one user touch one
-- partition; maintenance runs per partition. Postgres requires the partition
-- key (user_id) to be part of the primary key and of any unique constraint.
CREATE TABLE public.messages (
    id         uuid                NOT NULL DEFAULT gen_random_uuid(),
    user_id    uuid                NOT NULL,
    session_id uuid                NOT NULL,
    -- Order of the line within its call (0, 1, 2, ...).
    seq        integer             NOT NULL,
    speaker    public.speaker_type NOT NULL,
    -- Which bot spoke; null when the user spoke.
    bot_id     uuid                REFERENCES public.bots (id) ON DELETE RESTRICT,
    text       text                NOT NULL,
    interrupted boolean            NOT NULL DEFAULT false,
    spoken_at  timestamptz         NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, id),
    -- The message's session must belong to the same user (composite reference).
    FOREIGN KEY (user_id, session_id) REFERENCES public.sessions (user_id, id) ON DELETE CASCADE,
    CONSTRAINT messages_session_seq_key UNIQUE (user_id, session_id, seq),
    CONSTRAINT messages_seq_non_negative CHECK (seq >= 0),
    -- bot_id is set exactly when a bot is speaking.
    CONSTRAINT messages_bot_matches_speaker CHECK ((speaker = 'bot') = (bot_id IS NOT NULL)),
    -- Only bot lines can be cut off by the user.
    CONSTRAINT messages_only_bots_interrupted CHECK (NOT interrupted OR speaker = 'bot')
) PARTITION BY HASH (user_id);

-- The 16 partitions (each gets its share of users by hash of user_id).
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE TABLE public.messages_p%s PARTITION OF public.messages '
            'FOR VALUES WITH (MODULUS 16, REMAINDER %s)', i, i);
    END LOOP;
END;
$$;

-- --- User–bot relationships: how well each bot knows each user --------------------
-- One row per (user, bot) pair that has talked. Updated by the post-call job;
-- read by the scriptwriter so a bot behaves like an old friend or a new
-- acquaintance as appropriate.
CREATE TABLE public.user_bot_relationships (
    user_id       uuid        NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    bot_id        uuid        NOT NULL REFERENCES public.bots (id) ON DELETE RESTRICT,
    first_met_at  timestamptz NOT NULL DEFAULT now(),
    last_call_at  timestamptz NOT NULL DEFAULT now(),
    call_count    integer     NOT NULL DEFAULT 0,
    -- 1 (just met) to 10 (close friend); set by the post-call job.
    rapport_level smallint    NOT NULL DEFAULT 1,
    -- A short summary of the relationship so far, written by the post-call job.
    rapport_notes text        NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, bot_id),
    CONSTRAINT user_bot_relationships_call_count_non_negative CHECK (call_count >= 0),
    CONSTRAINT user_bot_relationships_rapport_range CHECK (rapport_level BETWEEN 1 AND 10),
    CONSTRAINT user_bot_relationships_last_after_first CHECK (last_call_at >= first_met_at)
);

-- "Which users has this bot met" (the primary key covers user-first lookups).
CREATE INDEX user_bot_relationships_bot_idx ON public.user_bot_relationships (bot_id);

CREATE TRIGGER user_bot_relationships_set_updated_at
    BEFORE UPDATE ON public.user_bot_relationships
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- --- Access control ----------------------------------------------------------------
-- RLS on with no policies: the browser-facing API roles can do nothing.
-- Server-side access (service-role key, direct Postgres connection) bypasses RLS.
-- Each messages partition is a table of its own, so each needs RLS too.
DO $$
DECLARE
    table_name text;
BEGIN
    FOR table_name IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename IN ('bots', 'bot_versions', 'sessions', 'session_bots', 'messages', 'user_bot_relationships')
           OR (schemaname = 'public' AND tablename LIKE 'messages\_p%')
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', table_name);
    END LOOP;
END;
$$;

INSERT INTO supabase_migrations.schema_migrations (version, name)
VALUES ('20260930073542', 'create_bots_sessions_messages');

COMMIT;
