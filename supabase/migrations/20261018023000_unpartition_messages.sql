-- Replaces the hash-partitioned messages table with a plain table. Partitioning
-- only pays off at volumes far beyond what this app handles; ADR 0009 records
-- when it would be added back and how. Rows are copied, so this is safe on a
-- table that already holds data. The same-user guarantee stays: the
-- (user_id, session_id) reference to sessions is unchanged.
--
-- Apply manually in the Supabase SQL editor (see supabase/README.md). The whole
-- file runs in one transaction: if any statement fails, nothing is applied.

BEGIN;

-- Move the old table aside and free the index-backed constraint names, which
-- must be unique per schema.
ALTER TABLE public.messages RENAME TO messages_partitioned;
ALTER TABLE public.messages_partitioned RENAME CONSTRAINT messages_pkey TO messages_partitioned_pkey;
ALTER TABLE public.messages_partitioned
    RENAME CONSTRAINT messages_session_seq_key TO messages_partitioned_session_seq_key;

-- One row per spoken line. For bots, the text is what was actually heard: if the
-- user interrupted, only the part that played is stored (interrupted = true).
CREATE TABLE public.messages (
    id          uuid                PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid                NOT NULL,
    session_id  uuid                NOT NULL,
    -- Order of the line within its call (0, 1, 2, ...).
    seq         integer             NOT NULL,
    speaker     public.speaker_type NOT NULL,
    -- Which bot spoke; null when the user spoke.
    bot_id      uuid                REFERENCES public.bots (id) ON DELETE RESTRICT,
    text        text                NOT NULL,
    interrupted boolean             NOT NULL DEFAULT false,
    spoken_at   timestamptz         NOT NULL DEFAULT now(),
    -- The message's session must belong to the same user (composite reference).
    FOREIGN KEY (user_id, session_id) REFERENCES public.sessions (user_id, id) ON DELETE CASCADE,
    -- Also serves session lookups, including the cascade when a session is deleted.
    CONSTRAINT messages_session_seq_key UNIQUE (session_id, seq),
    CONSTRAINT messages_seq_non_negative CHECK (seq >= 0),
    -- bot_id is set exactly when a bot is speaking.
    CONSTRAINT messages_bot_matches_speaker CHECK ((speaker = 'bot') = (bot_id IS NOT NULL)),
    -- Only bot lines can be cut off by the user.
    CONSTRAINT messages_only_bots_interrupted CHECK (NOT interrupted OR speaker = 'bot')
);

INSERT INTO public.messages (id, user_id, session_id, seq, speaker, bot_id, text, interrupted, spoken_at)
SELECT id, user_id, session_id, seq, speaker, bot_id, text, interrupted, spoken_at
FROM public.messages_partitioned;

-- Dropping the partitioned parent drops its 16 partitions with it.
DROP TABLE public.messages_partitioned;

-- RLS on with no policies, and no access for the browser-facing API roles.
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.messages FROM anon, authenticated;

INSERT INTO supabase_migrations.schema_migrations (version, name)
VALUES ('20261018023000', 'unpartition_messages');

COMMIT;
