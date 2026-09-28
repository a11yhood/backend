-- Data integrity fix:
--  1. Enable RLS on the two tables the Supabase security advisor flagged as
--     "Unrestricted" (RLS disabled, so PostgREST exposes them to any API key):
--       - public.schema_migrations: internal migration bookkeeping table
--         (scripts/apply-migrations.sh), never queried via the Supabase client
--         library. No policies are added, so it is fully closed to anon/
--         authenticated API access; direct psql access (table owner) is
--         unaffected since RLS does not restrict the owner role.
--       - public.collection_entries: user-facing table, so it gets the same
--         owner/editor/public policies that collection_products had before it
--         was replaced (see 20260602_add_collection_editors.sql).
--  2. Add public.scraper_locks, used by services/scrapers.py to stop two scrape
--     runs for the same source (manual trigger vs. cron, or a retried cron
--     invocation) from overlapping. Overlapping runs raced on the
--     check-then-insert in scrapers/base_scraper.py's _product_exists()/
--     _create_product(), tripping idx_products_source_external_id.

-- ============================================================================
-- 1a. Lock down schema_migrations
-- ============================================================================

ALTER TABLE IF EXISTS public.schema_migrations ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 1b. Enable RLS on collection_entries with the same access rules
--     collection_products used to enforce.
-- ============================================================================

ALTER TABLE public.collection_entries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public collection entries are viewable by everyone" ON public.collection_entries;
CREATE POLICY "Public collection entries are viewable by everyone"
ON public.collection_entries FOR SELECT
USING (
  EXISTS (
    SELECT 1 FROM public.collections c
    WHERE c.id = collection_entries.collection_id
      AND c.is_public = true
  )
);

DROP POLICY IF EXISTS "Users can view own collection entries" ON public.collection_entries;
CREATE POLICY "Users can view own collection entries"
ON public.collection_entries FOR SELECT
USING (
  EXISTS (
    SELECT 1 FROM public.collections c
    WHERE c.id = collection_entries.collection_id
      AND (
        c.user_id = (SELECT auth.uid())
        OR EXISTS (
          SELECT 1 FROM public.collection_editors ce
          WHERE ce.collection_id = c.id
            AND ce.user_id = (SELECT auth.uid())
        )
      )
  )
);

DROP POLICY IF EXISTS "Users can add entries to own collections" ON public.collection_entries;
CREATE POLICY "Users can add entries to own collections"
ON public.collection_entries FOR INSERT
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.collections c
    WHERE c.id = collection_entries.collection_id
      AND (
        c.user_id = (SELECT auth.uid())
        OR EXISTS (
          SELECT 1 FROM public.collection_editors ce
          WHERE ce.collection_id = c.id
            AND ce.user_id = (SELECT auth.uid())
        )
      )
  )
);

DROP POLICY IF EXISTS "Users can remove entries from own collections" ON public.collection_entries;
CREATE POLICY "Users can remove entries from own collections"
ON public.collection_entries FOR DELETE
USING (
  EXISTS (
    SELECT 1 FROM public.collections c
    WHERE c.id = collection_entries.collection_id
      AND (
        c.user_id = (SELECT auth.uid())
        OR EXISTS (
          SELECT 1 FROM public.collection_editors ce
          WHERE ce.collection_id = c.id
            AND ce.user_id = (SELECT auth.uid())
        )
      )
  )
);

-- ============================================================================
-- 2. scraper_locks: per-source advisory row preventing overlapping scrape runs
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.scraper_locks (
    source TEXT PRIMARY KEY,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.scraper_locks ENABLE ROW LEVEL SECURITY;
-- No policies: only the backend's service-role client touches this table
-- (service_role bypasses RLS), so it stays fully closed to anon/authenticated.
