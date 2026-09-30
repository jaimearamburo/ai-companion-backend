-- Prepares a plain Postgres database to behave like a fresh Supabase project for
-- the parts our migrations touch. Used only by CI's throwaway database.

-- Stand-ins for the API roles Supabase creates in every project.
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;

-- Supabase grants these roles access to new tables in the public schema by
-- default; mirror that, so migrations' REVOKE statements are actually tested.
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;
