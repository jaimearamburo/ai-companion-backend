-- Behavioural checks run after all migrations are applied in CI. Each check
-- raises an exception (failing CI) if the schema doesn't enforce its rule.
-- Runs against CI's throwaway database only; it inserts test rows.
--
-- Pattern used below: a nested BEGIN ... EXCEPTION WHEN <error> block runs a
-- statement that must be rejected. If it succeeds instead, the RAISE right after
-- it fails the check; if it's rejected with the expected error, the handler
-- swallows the error and the checks carry on.

-- --- users / accounts (20260930065124) --------------------------------------------
DO $$
DECLARE
    test_user_id uuid;
    stamp timestamptz;
BEGIN
    -- Emails must be stored lowercase.
    BEGIN
        INSERT INTO public.users (email) VALUES ('Mixed.Case@example.com');
        RAISE EXCEPTION 'check failed: an email with capitals was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Emails must be unique.
    INSERT INTO public.users (email) VALUES ('someone@example.com') RETURNING id INTO test_user_id;
    BEGIN
        INSERT INTO public.users (email) VALUES ('someone@example.com');
        RAISE EXCEPTION 'check failed: a duplicate email was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    -- New users default to the 'user' role.
    IF (SELECT role FROM public.users WHERE id = test_user_id) <> 'user' THEN
        RAISE EXCEPTION 'check failed: new users should default to role "user"';
    END IF;

    -- updated_at changes on update. (now() is fixed within a transaction, so set a
    -- distinctive past value first and check the trigger replaced it.)
    UPDATE public.users SET updated_at = '2000-01-01' WHERE id = test_user_id;
    SELECT updated_at INTO stamp FROM public.users WHERE id = test_user_id;
    IF stamp = '2000-01-01'::timestamptz THEN
        RAISE EXCEPTION 'check failed: updated_at trigger did not run';
    END IF;

    -- Deleting a user deletes their linked accounts.
    INSERT INTO public.accounts (user_id, type, provider, provider_account_id)
    VALUES (test_user_id, 'oauth', 'google', 'google-123');
    DELETE FROM public.users WHERE id = test_user_id;
    IF EXISTS (SELECT 1 FROM public.accounts WHERE provider_account_id = 'google-123') THEN
        RAISE EXCEPTION 'check failed: accounts were not deleted with their user';
    END IF;
END;
$$;

-- --- bots / sessions / session_bots / messages / relationships (20260930073542) ------
DO $$
DECLARE
    alice uuid;
    bob uuid;
    gary uuid;
    paul uuid;
    gary_v1 uuid;
    paul_v1 uuid;
    call_id uuid;
    partition_count integer;
BEGIN
    INSERT INTO public.users (email) VALUES ('alice@example.com') RETURNING id INTO alice;
    INSERT INTO public.users (email) VALUES ('bob@example.com') RETURNING id INTO bob;
    INSERT INTO public.bots (slug, display_name) VALUES ('gary', 'Gary') RETURNING id INTO gary;
    INSERT INTO public.bots (slug, display_name) VALUES ('paul', 'Paul') RETURNING id INTO paul;
    INSERT INTO public.bot_versions (bot_id, version, persona_prompt, voices)
    VALUES (gary, 1, 'Warm retired builder.', '{"fish_s21_hosted": "voice-gary"}')
    RETURNING id INTO gary_v1;
    INSERT INTO public.bot_versions (bot_id, version, persona_prompt, voices)
    VALUES (paul, 1, 'Gentle former teacher.', '{"fish_s21_hosted": "voice-paul"}')
    RETURNING id INTO paul_v1;

    -- Bot slugs are lowercase words joined by hyphens.
    BEGIN
        INSERT INTO public.bots (slug, display_name) VALUES ('Gary Two', 'Gary 2');
        RAISE EXCEPTION 'check failed: an invalid bot slug was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Avatars are served over HTTPS only.
    BEGIN
        INSERT INTO public.bots (slug, display_name, avatar_url)
        VALUES ('anne', 'Anne', 'http://example.com/anne.png');
        RAISE EXCEPTION 'check failed: a non-HTTPS avatar URL was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- A version needs at least one voice, and version numbers start at 1 and
    -- don't repeat for a bot.
    BEGIN
        INSERT INTO public.bot_versions (bot_id, version, persona_prompt, voices)
        VALUES (gary, 2, 'x', '{}');
        RAISE EXCEPTION 'check failed: a version without voices was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.bot_versions (bot_id, version, persona_prompt, voices)
        VALUES (gary, 0, 'x', '{"fish_s21_hosted": "v"}');
        RAISE EXCEPTION 'check failed: version 0 was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.bot_versions (bot_id, version, persona_prompt, voices)
        VALUES (gary, 1, 'x', '{"fish_s21_hosted": "v"}');
        RAISE EXCEPTION 'check failed: a duplicate version number was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    -- Versions are append-only: they can't be edited or deleted.
    BEGIN
        UPDATE public.bot_versions SET persona_prompt = 'Changed.' WHERE id = gary_v1;
        RAISE EXCEPTION 'check failed: a bot version was edited';
    EXCEPTION WHEN restrict_violation THEN NULL;
    END;
    BEGIN
        DELETE FROM public.bot_versions WHERE id = gary_v1;
        RAISE EXCEPTION 'check failed: a bot version was deleted';
    EXCEPTION WHEN restrict_violation THEN NULL;
    END;

    INSERT INTO public.sessions (user_id, livekit_room_name, region, stt_preset, tts_preset,
                                 llm_preset, safety_preset, turn_detector_preset, trigger_preset)
    VALUES (alice, 'room-1', 'au', 'deepgram_nova3_au', 'fish_s21_hosted', 'groq_gptoss120b',
            'groq_safeguard20b', 'livekit_v1_mini', 'auto')
    RETURNING id INTO call_id;
    INSERT INTO public.session_bots (session_id, bot_id, bot_version_id)
    VALUES (call_id, gary, gary_v1), (call_id, paul, paul_v1);

    -- A new session defaults to memory deletion switched off.
    IF (SELECT memory_deletion_enabled FROM public.sessions WHERE id = call_id) THEN
        RAISE EXCEPTION 'check failed: memory deletion was on by default';
    END IF;

    -- Only known regions are accepted.
    BEGIN
        INSERT INTO public.sessions (user_id, livekit_room_name, region, stt_preset, tts_preset,
                                     llm_preset, safety_preset, turn_detector_preset, trigger_preset)
        VALUES (alice, 'room-eu', 'eu', 'a', 'b', 'c', 'd', 'e', 'f');
        RAISE EXCEPTION 'check failed: an unknown region was accepted';
    EXCEPTION WHEN invalid_text_representation THEN NULL;
    END;

    -- A call can't record another bot's version for a bot.
    BEGIN
        UPDATE public.session_bots SET bot_version_id = paul_v1
        WHERE session_id = call_id AND bot_id = gary;
        RAISE EXCEPTION 'check failed: a call recorded another bot''s version';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    -- A session's status and end time must agree.
    BEGIN
        UPDATE public.sessions SET ended_at = now() WHERE id = call_id;  -- still 'active'
        RAISE EXCEPTION 'check failed: an active session was given an end time';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Transcript lines: user lines have no bot, bot lines must name the bot.
    INSERT INTO public.messages (user_id, session_id, seq, speaker, text)
    VALUES (alice, call_id, 0, 'user', 'Hello!');
    INSERT INTO public.messages (user_id, session_id, seq, speaker, bot_id, text, interrupted)
    VALUES (alice, call_id, 1, 'bot', gary, 'G''day, how are you', true);
    BEGIN
        INSERT INTO public.messages (user_id, session_id, seq, speaker, text)
        VALUES (alice, call_id, 2, 'bot', 'A bot line without a bot');
        RAISE EXCEPTION 'check failed: a bot line without bot_id was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.messages (user_id, session_id, seq, speaker, bot_id, text)
        VALUES (alice, call_id, 2, 'user', gary, 'A user line with a bot');
        RAISE EXCEPTION 'check failed: a user line with bot_id was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.messages (user_id, session_id, seq, speaker, text, interrupted)
        VALUES (alice, call_id, 2, 'user', 'Interrupted user line', true);
        RAISE EXCEPTION 'check failed: a user line was marked interrupted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Two lines can't share a position in the same call.
    BEGIN
        INSERT INTO public.messages (user_id, session_id, seq, speaker, text)
        VALUES (alice, call_id, 0, 'user', 'Duplicate position');
        RAISE EXCEPTION 'check failed: a duplicate message seq was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    -- A message can't be attached to another user's session.
    BEGIN
        INSERT INTO public.messages (user_id, session_id, seq, speaker, text)
        VALUES (bob, call_id, 0, 'user', 'Wrong user');
        RAISE EXCEPTION 'check failed: a message was attached to another user''s session';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    -- messages is split into 16 partitions.
    SELECT count(*) INTO partition_count FROM pg_inherits
    WHERE inhparent = 'public.messages'::regclass;
    IF partition_count <> 16 THEN
        RAISE EXCEPTION 'check failed: messages has % partitions, expected 16', partition_count;
    END IF;

    -- Relationship rapport stays within 1-10.
    INSERT INTO public.user_bot_relationships (user_id, bot_id) VALUES (alice, gary);
    BEGIN
        UPDATE public.user_bot_relationships SET rapport_level = 11 WHERE user_id = alice;
        RAISE EXCEPTION 'check failed: rapport_level 11 was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- A bot with history can't be deleted (retire it with is_active instead).
    BEGIN
        DELETE FROM public.bots WHERE id = gary;
        RAISE EXCEPTION 'check failed: a bot with history was deleted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    -- Deleting a user deletes their sessions, transcripts and relationships.
    DELETE FROM public.users WHERE id = alice;
    IF EXISTS (SELECT 1 FROM public.sessions WHERE id = call_id)
       OR EXISTS (SELECT 1 FROM public.session_bots WHERE session_id = call_id)
       OR EXISTS (SELECT 1 FROM public.messages WHERE session_id = call_id)
       OR EXISTS (SELECT 1 FROM public.user_bot_relationships WHERE user_id = alice) THEN
        RAISE EXCEPTION 'check failed: a user''s calls were not deleted with them';
    END IF;
END;
$$;

-- --- Rules for every table, whichever migration created it --------------------------
DO $$
BEGIN
    -- Row-level security is on for every table in the public schema, including
    -- partitioned tables ('p') and their partitions ('r').
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity
    ) THEN
        RAISE EXCEPTION 'check failed: a public table has row-level security disabled';
    END IF;

    -- The browser-facing API roles have no privileges on any public table.
    IF EXISTS (
        SELECT 1 FROM pg_tables t, (VALUES ('anon'), ('authenticated')) AS r(role_name)
        WHERE t.schemaname = 'public'
          AND has_table_privilege(r.role_name, format('public.%I', t.tablename),
                                  'SELECT,INSERT,UPDATE,DELETE')
    ) THEN
        RAISE EXCEPTION 'check failed: anon or authenticated can access a public table';
    END IF;

    -- Every migration file recorded itself.
    IF (SELECT count(*) FROM supabase_migrations.schema_migrations
        WHERE version IN ('20260930065124', '20260930073542')) <> 2 THEN
        RAISE EXCEPTION 'check failed: not every migration recorded itself';
    END IF;
END;
$$;
