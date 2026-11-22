-- The login role of the database dumps (ADR 0012): `pg_dump` reads every row, and the
-- role can write to no table. Its password is never in git: the local seed sets a dev
-- one; production gets it from Bitwarden, as the `backup` environment's
-- BACKUP_DB_PASSWORD.
--
-- BYPASSRLS because pg_dump turns row security off and fails on any table whose policies
-- would hide a row. pg_read_all_data gives SELECT on every table and sequence and USAGE
-- on every schema, and nothing else: the role owns nothing and holds no other grant, so
-- every write to a table or schema is refused by privileges. The read-only default is
-- only a second belt, since a session can lift it.
create role twochi_backup login bypassrls;
grant pg_read_all_data to twochi_backup;
alter role twochi_backup set default_transaction_read_only = on;
