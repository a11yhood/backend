-- Follow-up fix for 20260927_data_integrity_rls_and_scraper_lock.sql's
-- scraper_locks table (already applied, so fixed up here rather than edited
-- in place):
--
-- 1. Add lock_token so a run that reclaims a stale lock (see
--    services/scrapers.py's _try_acquire_scrape_lock) gets a fresh token, and
--    the original owner's eventual release only deletes the row when its
--    token still matches. Without this: run A (running long) has its lock
--    reclaimed as "stale" by run B; A finishes and deletes what it thinks is
--    its own row, but that row is now B's, so a third run can start while B
--    is still going.
-- 2. Grant service_role explicit access. Some environments rely on
--    ALTER DEFAULT PRIVILEGES set up elsewhere (see
--    migrations/test_only/20260308_service_role_public_schema_grants.sql)
--    rather than a global default, so a newly created table isn't guaranteed
--    to be reachable by service_role without this.

ALTER TABLE public.scraper_locks
    ADD COLUMN IF NOT EXISTS lock_token UUID NOT NULL DEFAULT gen_random_uuid();

GRANT ALL ON public.scraper_locks TO service_role;
