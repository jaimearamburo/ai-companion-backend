-- Behavioural checks run after all migrations are applied in CI. Each check
-- raises an exception (failing CI) if the schema doesn't enforce its rule.
-- Runs against CI's throwaway database only; it inserts test rows.

DO $$
DECLARE
    test_user_id uuid;
    stamp timestamptz;
BEGIN
    -- Emails must be stored lowercase.
    BEGIN
        INSERT INTO public.users (email) VALUES ('Mixed.Case@example.com');
        RAISE EXCEPTION 'check failed: an email with capitals was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL;  -- expected
    END;

    -- Emails must be unique.
    INSERT INTO public.users (email) VALUES ('someone@example.com') RETURNING id INTO test_user_id;
    BEGIN
        INSERT INTO public.users (email) VALUES ('someone@example.com');
        RAISE EXCEPTION 'check failed: a duplicate email was accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;  -- expected
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

    -- Row-level security is on for every table in the public schema.
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity
    ) THEN
        RAISE EXCEPTION 'check failed: a public table has row-level security disabled';
    END IF;

    -- The browser-facing API roles have no privileges on any public table.
    IF EXISTS (
        SELECT 1 FROM pg_tables t, (VALUES ('anon'), ('authenticated')) AS r(role_name)
        WHERE t.schemaname = 'public'
          AND has_table_privilege(r.role_name, format('public.%I', t.tablename), 'SELECT,INSERT,UPDATE,DELETE')
    ) THEN
        RAISE EXCEPTION 'check failed: anon or authenticated can access a public table';
    END IF;

    -- Every migration file recorded itself.
    IF NOT EXISTS (
        SELECT 1 FROM supabase_migrations.schema_migrations WHERE version = '20260930065124'
    ) THEN
        RAISE EXCEPTION 'check failed: migration 20260930065124 did not record itself';
    END IF;
END;
$$;
