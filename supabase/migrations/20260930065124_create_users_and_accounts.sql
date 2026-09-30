-- Users and their linked OAuth accounts, used by Auth.js in the frontend through
-- a custom adapter (see ARCHITECTURE.md → Database schema → Auth tables).
--
-- Apply manually in the Supabase SQL editor (see supabase/README.md). The whole
-- file runs in one transaction: if any statement fails, nothing is applied.

BEGIN;

-- What a user is allowed to do. 'admin' can put any number of bots in a call
-- (testing); 'user' is limited to two.
CREATE TYPE public.user_role AS ENUM ('admin', 'user');

CREATE TABLE public.users (
    id             uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Nullable: not every OAuth profile provides a name.
    name           text,
    email          text             NOT NULL UNIQUE,
    -- Set by Auth.js when an OAuth provider confirms the email.
    email_verified timestamptz,
    image          text,
    -- Null for accounts that only sign in with Google.
    password_hash  text,
    role           public.user_role NOT NULL DEFAULT 'user',
    created_at     timestamptz      NOT NULL DEFAULT now(),
    -- Kept current by the users_set_updated_at trigger below.
    updated_at     timestamptz      NOT NULL DEFAULT now(),
    -- Emails are stored lowercase only, so a plain UNIQUE makes them unique
    -- regardless of capitals and lookups are simple equality. The frontend
    -- adapter lowercases before every insert and lookup.
    CONSTRAINT users_email_lowercase CHECK (email = lower(email)),
    CONSTRAINT users_email_not_blank CHECK (btrim(email) <> '')
);

-- Trigger function shared by every table with an updated_at column: sets it to
-- the current time whenever a row is updated. search_path is fixed to empty so
-- the function can't be redirected to objects in another schema.
CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = ''
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- One row per OAuth provider login linked to a user (e.g. their Google account).
-- Token columns mirror the OAuth fields Auth.js passes through.
CREATE TABLE public.accounts (
    id                  uuid   PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid   NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    type                text   NOT NULL,
    provider            text   NOT NULL,
    provider_account_id text   NOT NULL,
    refresh_token       text,
    access_token        text,
    expires_at          bigint,
    token_type          text,
    scope               text,
    id_token            text,
    session_state       text,
    -- A given provider login belongs to exactly one user.
    CONSTRAINT accounts_provider_account_key UNIQUE (provider, provider_account_id)
);

-- Postgres doesn't index foreign keys automatically; this makes "all accounts
-- for a user" (and cascading deletes) fast.
CREATE INDEX accounts_user_id_idx ON public.accounts (user_id);

-- Row-level security: with RLS on and no policies, the API roles can read or
-- write nothing. Server-side access (the frontend's service-role key, the
-- backend's direct Postgres connection) bypasses RLS.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY;

-- Supabase grants its browser-facing API roles access to new public tables by
-- default; remove that too, so a policy added by mistake still grants nothing.
REVOKE ALL ON public.users, public.accounts FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.set_updated_at() FROM PUBLIC, anon, authenticated;

-- Record this migration in the table the Supabase CLI uses to track applied
-- migrations, so switching to the CLI later won't try to apply it again.
CREATE SCHEMA IF NOT EXISTS supabase_migrations;
CREATE TABLE IF NOT EXISTS supabase_migrations.schema_migrations (
    version    text PRIMARY KEY,
    statements text[],
    name       text
);
INSERT INTO supabase_migrations.schema_migrations (version, name)
VALUES ('20260930065124', 'create_users_and_accounts');

COMMIT;
