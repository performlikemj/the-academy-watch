-- =============================================================================
-- Recurring purge of expired API-Football cache (api_cache) via pg_cron
-- =============================================================================
-- Applied to PROD (Supabase project snqwamzutbcbjgusubsa) on 2026-06-22.
--
-- WHY: api_cache is a DB-backed TTL cache for API-Football responses. Nothing
-- was ever deleting expired rows, so it grew to ~200 MB (92.5k rows, ~65% of
-- them already expired) — the single biggest table in the DB and ~half of total
-- DB size. This schedules a daily purge so the cache stays at a bounded
-- steady-state instead of growing forever. Mirrors APICache.cleanup_expired()
-- in src/models/api_cache.py.
--
-- This is OUT-OF-BAND maintenance, intentionally NOT an Alembic migration:
--   * pg_cron setup needs the postgres superuser; running CREATE EXTENSION over
--     the app's deploy connection risks breaking `flask db upgrade`.
--   * It is infra/scheduling, not application schema.
-- It is idempotent and re-runnable. If the database is ever rebuilt/migrated to
-- a new project, re-run this file (psql / Supabase SQL editor) to restore the job.
--
-- Verify:    select jobid, jobname, schedule, active, command from cron.job;
-- Run log:   select * from cron.job_run_details order by start_time desc limit 10;
-- Unschedule: select cron.unschedule('purge-expired-api-cache');
-- =============================================================================

create extension if not exists pg_cron;

-- Named job => cron.schedule upserts by name, so re-running this is safe.
select cron.schedule(
  'purge-expired-api-cache',
  '30 3 * * *',                                            -- daily, 03:30 UTC (off-peak)
  $$delete from public.api_cache where expires_at < now()$$
);

-- One-time disk reclaim (NOT run automatically): the daily DELETE bounds growth,
-- but to shrink the already-allocated ~200 MB back to disk, run a one-off during
-- a maintenance window (briefly ACCESS EXCLUSIVE locks api_cache — safe because
-- it is only read on API-Football cache lookups, not on normal page loads):
--     vacuum (full, analyze) public.api_cache;
