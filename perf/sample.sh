#!/usr/bin/env bash
# Samples API/worker/Postgres CPU and memory plus DB connections every 5 s.
# Usage: perf/sample.sh <seconds> <outfile> [dbname]
set -u
secs=$1; out=$2; db=${3:-steward_perf}
echo "ts,api_cpu_pct,api_rss_mb,workers_cpu_pct,pg_cpu_pct,pg_rss_mb,db_connections,load1" > "$out"
end=$((SECONDS+secs))
while [ $SECONDS -lt $end ]; do
  read -r acpu arss < <(ps -eo pcpu,rss,args | awk '/[u]vicorn app.main:app.*8100|multiprocessing.spawn/ {c+=$1; r+=$2} END {printf "%.1f %.0f\n", c, r/1024}')
  wcpu=$(ps -eo pcpu,args | awk '/[a]pp.workers/ {c+=$1} END {printf "%.1f", c}')
  read -r pcpu prss < <(ps -eo pcpu,rss,comm | awk '$3 ~ /postgres/ {c+=$1; r+=$2} END {printf "%.1f %.0f\n", c, r/1024}')
  conns=$(PGPASSWORD=devowner psql -h 127.0.0.1 -U steward_owner -d postgres -Atc "select count(*) from pg_stat_activity where datname='$db'")
  echo "$(date +%s),$acpu,$arss,$wcpu,$pcpu,$prss,$conns,$(cut -d' ' -f1 /proc/loadavg)" >> "$out"
  sleep 5
done
