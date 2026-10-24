#!/usr/bin/env bash
# Creates the database roles and the application database.
# Run once as a PostgreSQL superuser (the official postgres image runs this
# automatically from /docker-entrypoint-initdb.d on first start).
#
#   steward_owner  owns the schema, runs migrations (no superuser, CREATEDB only for the test DB)
#   steward_app       used by the running API: no DDL, no DELETE
#   steward_worker    background workers (orchestrator, tools, scheduler): no DELETE, no secrets
#   steward_deleter   deletion service: the only role that can soft-delete a file
#   steward_readonly  reporting/support: SELECT only, no secrets
# All table grants are applied by the migrations, not here. Safe to re-run: existing
# roles are left as they are, so it also adds the Phase 3 roles to an existing database.
set -euo pipefail

: "${STEWARD_DB_NAME:=steward}"
: "${STEWARD_OWNER_PASSWORD:?set STEWARD_OWNER_PASSWORD}"
: "${STEWARD_APP_PASSWORD:?set STEWARD_APP_PASSWORD}"
: "${STEWARD_WORKER_PASSWORD:?set STEWARD_WORKER_PASSWORD}"
: "${STEWARD_DELETER_PASSWORD:?set STEWARD_DELETER_PASSWORD}"
: "${STEWARD_READONLY_PASSWORD:?set STEWARD_READONLY_PASSWORD}"

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname postgres \
  -v db="$STEWARD_DB_NAME" -v owner_pw="$STEWARD_OWNER_PASSWORD" -v app_pw="$STEWARD_APP_PASSWORD" \
  -v worker_pw="$STEWARD_WORKER_PASSWORD" -v deleter_pw="$STEWARD_DELETER_PASSWORD" \
  -v readonly_pw="$STEWARD_READONLY_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE steward_owner LOGIN CREATEDB NOSUPERUSER NOCREATEROLE PASSWORD %L', :'owner_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'steward_owner') \gexec
SELECT format('CREATE ROLE steward_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'steward_app') \gexec
SELECT format('CREATE ROLE steward_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'worker_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'steward_worker') \gexec
SELECT format('CREATE ROLE steward_deleter LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'deleter_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'steward_deleter') \gexec
SELECT format('CREATE ROLE steward_readonly LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'readonly_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'steward_readonly') \gexec
SELECT format('CREATE DATABASE %I OWNER steward_owner', :'db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO steward_app, steward_worker, steward_deleter, steward_readonly', :'db') \gexec
SQL

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname "$STEWARD_DB_NAME" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO steward_owner;
GRANT USAGE ON SCHEMA public TO steward_app, steward_worker, steward_deleter, steward_readonly;
SQL
echo "steward roles and database ready"
