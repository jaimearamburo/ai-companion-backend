-- Development seed data: two clearly marked placeholder bots, so a call can run
-- before the real roster exists. Replace them with real characters (and their
-- own voices) before anyone else uses the app.
--
-- Safe to run more than once: existing rows are left alone. Apply by hand in the
-- Supabase SQL editor after the migrations, like a migration.

BEGIN;

INSERT INTO public.bots (slug, display_name, ui_description)
VALUES
    ('placeholder-a', 'Placeholder A', 'Development placeholder; not a real character yet.'),
    ('placeholder-b', 'Placeholder B', 'Development placeholder; not a real character yet.')
ON CONFLICT (slug) DO NOTHING;

-- Both use the default voice of LiveKit's Fish Audio plugin until real voices
-- are chosen in the voice listening test.
INSERT INTO public.bot_versions (bot_id, version, persona_prompt, voices, allowed_tools)
SELECT b.id, 1, p.persona, '{"fish_s21_hosted": "933563129e564b19a115bedd57b7406a"}'::jsonb,
       ARRAY['recall_memory', 'list_memories', 'forget_memory']
FROM public.bots b
JOIN (VALUES
    ('placeholder-a', 'A friendly, upbeat companion who enjoys everyday conversation. Placeholder persona for development.'),
    ('placeholder-b', 'A calm, thoughtful companion who asks good follow-up questions. Placeholder persona for development.')
) AS p (slug, persona) ON p.slug = b.slug
ON CONFLICT (bot_id, version) DO NOTHING;

COMMIT;
