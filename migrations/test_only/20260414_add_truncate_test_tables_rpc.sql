-- Test-only RPC: truncate all test tables in one server-side call.
--
-- Apply this in the test Supabase SQL Editor once after creating or resetting
-- the test database.  See migrations/test_only/README.md for instructions.
--
-- This function is intentionally NOT part of the production migration chain.
-- It exists purely to collapse 18 sequential DELETE round-trips into a single
-- RPC call, which cuts per-test setup time significantly.
--
-- SECURITY DEFINER lets the service-role key invoke TRUNCATE even though TRUNCATE
-- requires table-owner-level privileges; the function runs as its owner (postgres).

CREATE OR REPLACE FUNCTION truncate_test_tables()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  TRUNCATE TABLE
    -- Junction / child tables first so FK constraints are satisfied
    public.collection_products,
    public.product_tags,
    public.product_editors,
    public.product_urls,
    public.ratings,
    public.discussions,
    public.user_activities,
    public.user_requests,
    public.scraping_logs,
    -- Parent tables
    public.tags,
    public.blog_posts,
    public.collections,
    public.products,
    public.users,
    public.oauth_configs,
    public.supported_sources,
    public.scraper_search_terms
  RESTART IDENTITY CASCADE;
END;
$$;

-- Allow the service-role key (used by DatabaseAdapter) to call this function.
GRANT EXECUTE ON FUNCTION public.truncate_test_tables() TO service_role;
