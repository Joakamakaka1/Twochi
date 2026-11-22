#!/usr/bin/env bash
# The three files of `supabase db dump` (roles, schema and data with COPY), as Supabase's
# restore guide expects them. Runs inside the pinned postgres image, from db_dump.py,
# with the PG* variables already set; writes to /out.
#
# Same pg_dump flags and sed filters as supabase CLI 2.122.0 (`--dry-run` prints them),
# with three differences (ADR 0012). No `--role "postgres"`: twochi_backup reads
# everything but may not become postgres. No data from Storage's vector buckets, which
# Twochi does not use: `postgres` may not insert into those two tables, so their COPY,
# even empty, aborts a restore (Supabase's restore guide skips them too). And no live
# sessions or one-time tokens from `auth`: refresh tokens are stored in clear and would
# sign in to production from a leaked dump, while a restore ends every session anyway.
# Compare with the CLI's `--dry-run` when you update the CLI.
set -euo pipefail

internal='information_schema|pg_*|_analytics|_realtime|_supavisor|auth|etl|extensions|pgbouncer|realtime|storage|supabase_functions|supabase_migrations|cron|dbdev|graphql|graphql_public|net|pgmq|pgsodium|pgsodium_masks|pgtle|repack|tiger|tiger_data|timescaledb_*|_timescaledb_*|topology|vault'
no_data='information_schema|pg_*|graphql|graphql_public|pgsodium|pgsodium_masks|pgtle|repack|tiger|tiger_data|timescaledb_*|_timescaledb_*|topology|vault|etl|extensions|pgbouncer|realtime|supabase_migrations|_analytics|_realtime|_supavisor'
reserved='anon|authenticated|authenticator|cli_login_.*|dashboard_user|pgbouncer|postgres|service_role|supabase_.*|pgsodium_keyholder|pgsodium_keyiduser|pgsodium_keymaker|pgtle_admin'

pg_dumpall --roles-only --quote-all-identifier --no-role-passwords --no-comments \
| sed -E 's/^\\(un)?restrict .*$/-- &/' \
| sed -E "s/^CREATE ROLE \"($reserved)\"/-- &/" \
| sed -E "s/^ALTER ROLE \"($reserved)\"/-- &/" \
| sed -E "s/ (NOSUPERUSER|NOREPLICATION)//g" \
| sed -E "s/^-- (.* SET \"(pgaudit.*|pgrst.*|session_replication_role|statement_timeout|track_io_timing)\" .*)/\1/" \
| sed -E "s/GRANT \".*\" TO \"($reserved)\"/-- &/" \
| sed -E "/^--/d" \
| uniq > /out/roles.sql
echo "RESET ALL;" >> /out/roles.sql

pg_dump --schema-only --quote-all-identifier --exclude-schema "$internal" \
| sed -E 's/^\\(un)?restrict .*$/-- &/' \
| sed -E 's/^CREATE SCHEMA "/CREATE SCHEMA IF NOT EXISTS "/' \
| sed -E 's/^CREATE TABLE "/CREATE TABLE IF NOT EXISTS "/' \
| sed -E 's/^CREATE SEQUENCE "/CREATE SEQUENCE IF NOT EXISTS "/' \
| sed -E 's/^CREATE VIEW "/CREATE OR REPLACE VIEW "/' \
| sed -E 's/^CREATE FUNCTION "/CREATE OR REPLACE FUNCTION "/' \
| sed -E 's/^CREATE TRIGGER "/CREATE OR REPLACE TRIGGER "/' \
| sed -E 's/^CREATE PUBLICATION "supabase_realtime/-- &/' \
| sed -E 's/^CREATE EVENT TRIGGER /-- &/' \
| sed -E 's/^         WHEN TAG IN /-- &/' \
| sed -E 's/^   EXECUTE FUNCTION /-- &/' \
| sed -E 's/^ALTER EVENT TRIGGER /-- &/' \
| sed -E 's/^ALTER PUBLICATION "supabase_realtime_/-- &/' \
| sed -E 's/^ALTER FOREIGN DATA WRAPPER (.+) OWNER TO /-- &/' \
| sed -E 's/^ALTER DEFAULT PRIVILEGES FOR ROLE "supabase_admin"/-- &/' \
| sed -E 's/^GRANT ALL ON FOREIGN DATA WRAPPER (.+) TO "postgres" WITH GRANT OPTION/-- &/' \
| sed -E "s/^GRANT (.+) ON (.+) \"($internal)\"/-- &/" \
| sed -E "s/^REVOKE (.+) ON (.+) \"($internal)\"/-- &/" \
| sed -E 's/^(CREATE EXTENSION IF NOT EXISTS "pg_tle").+/\1;/' \
| sed -E 's/^(CREATE EXTENSION IF NOT EXISTS "pgsodium").+/\1;/' \
| sed -E 's/^(CREATE EXTENSION IF NOT EXISTS "pgmq").+/\1;/' \
| sed -E 's/^COMMENT ON EXTENSION (.+)/-- &/' \
| sed -E 's/^CREATE POLICY "cron_job_/-- &/' \
| sed -E 's/^ALTER TABLE "cron"/-- &/' \
| sed -E 's/^SET transaction_timeout = 0;/-- &/' \
| sed -E "/^--/d" > /out/schema.sql

# Triggers off while restoring, so the data comes back exactly as it was dumped.
{
  echo "SET session_replication_role = replica;"
  echo
  pg_dump --data-only --quote-all-identifier --exclude-schema "$no_data" \
      --exclude-table "auth.schema_migrations" \
      --exclude-table "storage.migrations" \
      --exclude-table "supabase_functions.migrations" \
      --exclude-table "storage.buckets_vectors" \
      --exclude-table "storage.vector_indexes" \
      --exclude-table-data "auth.refresh_tokens" \
      --exclude-table-data "auth.sessions" \
      --exclude-table-data "auth.mfa_amr_claims" \
      --exclude-table-data "auth.mfa_challenges" \
      --exclude-table-data "auth.one_time_tokens" \
      --exclude-table-data "auth.flow_state" \
      --schema '*' \
  | sed -E 's/^\\(un)?restrict .*$/-- &/'
  echo "RESET ALL;"
} > /out/data.sql

# What this role may run with its owner's rights; db_dump.py fails the run on any line
# (ADR 0012). Not part of the archive. A failure here must not cost the day's dump, so
# it leaves no file and db_dump.py reports that after the upload.
if ! psql --no-psqlrc --tuples-only --no-align --command \
    "select p.oid::regprocedure || ' (owner ' || pg_get_userbyid(p.proowner) || ')' from pg_proc p where p.prosecdef and has_function_privilege(p.oid, 'execute') order by 1" \
    > /out/definer_functions.txt; then
  rm -f /out/definer_functions.txt
fi
