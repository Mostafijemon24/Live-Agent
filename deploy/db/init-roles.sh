#!/usr/bin/env bash
# Creates the two database roles and the application database.
# Run once as a PostgreSQL superuser (the official postgres image runs this
# automatically from /docker-entrypoint-initdb.d on first start).
#
#   steward_owner  owns the schema, runs migrations (no superuser, CREATEDB only for the test DB)
#   steward_app    used by the running API: no DDL, no DELETE (grants are applied by the migrations)
set -euo pipefail

: "${STEWARD_DB_NAME:=steward}"
: "${STEWARD_OWNER_PASSWORD:?set STEWARD_OWNER_PASSWORD}"
: "${STEWARD_APP_PASSWORD:?set STEWARD_APP_PASSWORD}"

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname postgres \
  -v db="$STEWARD_DB_NAME" -v owner_pw="$STEWARD_OWNER_PASSWORD" -v app_pw="$STEWARD_APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE steward_owner LOGIN CREATEDB NOSUPERUSER NOCREATEROLE PASSWORD %L', :'owner_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'steward_owner') \gexec
SELECT format('CREATE ROLE steward_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'steward_app') \gexec
SELECT format('CREATE DATABASE %I OWNER steward_owner', :'db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO steward_app', :'db') \gexec
SQL

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname "$STEWARD_DB_NAME" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO steward_owner;
GRANT USAGE ON SCHEMA public TO steward_app;
SQL
echo "steward roles and database ready"
