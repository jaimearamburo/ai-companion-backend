# `supabase/` — Database schema

The single source of truth for the Supabase Postgres schema shared by the backend and the frontend. Never change the schema from anywhere else (including the frontend repo or the dashboard's table editor).

## Workflow

1. **Design first:** a schema change is drafted in ARCHITECTURE.md → Database schema.
2. **Migration file:** it becomes a file in `migrations/`, named `YYYYMMDDHHMMSS_description.sql` (UTC timestamp), which fixes the order migrations apply in.
3. **CI check:** on every push, CI applies all migrations, in order, to a throwaway Postgres (see `ci/`). A migration that fails there never reaches the real database.
4. **Apply manually:** paste the file into the Supabase dashboard's **SQL editor** and run it — one file at a time, in filename order, never skipping one.
5. **Frontend types:** after applying, the frontend regenerates its types (`supabase gen types typescript`).

## Rules for migration files

- **One transaction per file** (`BEGIN; … COMMIT;`): if any statement fails, nothing is applied.
- **Never edit a migration after it has been applied** — write a new one instead.
- **snake_case** names; **product-neutral** naming (see ARCHITECTURE.md → Naming convention).
- **Every new table:** enable RLS, and revoke the default grants to `anon` and `authenticated`.
- **Each file records itself** in `supabase_migrations.schema_migrations` (the Supabase CLI's tracking table), so the CLI would recognise it as applied if it's adopted later.

## Checking what's applied

In the SQL editor:

```sql
SELECT version, name FROM supabase_migrations.schema_migrations ORDER BY version;
```

## Migrations

| File | What it does |
|---|---|
| `20260930065124_create_users_and_accounts.sql` | `users` and `accounts` for Auth.js (custom adapter): lowercase-only emails, `updated_at` trigger, RLS on, API-role grants revoked |
