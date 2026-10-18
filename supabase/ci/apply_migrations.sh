#!/usr/bin/env bash
# Applies every migration, in filename (= timestamp) order, then runs the schema
# checks. Stops at the first error.
#
# Connects using the standard Postgres environment variables (PGHOST, PGUSER,
# PGPASSWORD, PGDATABASE). Meant for CI's throwaway database only — never point
# it at the real Supabase project, where migrations are applied by hand.
set -euo pipefail

cd "$(dirname "$0")/.."

# ON_ERROR_STOP makes psql exit with an error on the first failing statement.
psql -v ON_ERROR_STOP=1 --quiet --file ci/bootstrap.sql

for file in migrations/*.sql; do
    echo "Applying $file"
    psql -v ON_ERROR_STOP=1 --quiet --file "$file"
done

# The seed must apply cleanly, and applying it twice must change nothing.
echo "Applying seed.sql (twice)"
psql -v ON_ERROR_STOP=1 --quiet --file seed.sql
psql -v ON_ERROR_STOP=1 --quiet --file seed.sql
if [ "$(psql --tuples-only --no-align -c "SELECT count(*) FROM public.bot_versions")" != "2" ]; then
    echo "seed.sql is not idempotent" >&2
    exit 1
fi

echo "Running schema checks"
psql -v ON_ERROR_STOP=1 --quiet --file ci/checks.sql
echo "All migrations applied and all checks passed"
