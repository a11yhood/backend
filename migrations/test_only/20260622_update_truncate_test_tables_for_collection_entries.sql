-- Update truncate_test_tables to replace collection_products with collection_entries.
-- Apply after migrations/20260622_drop_collection_products.sql has been run on the test DB.
--
-- See migrations/test_only/README.md for instructions.

CREATE OR REPLACE FUNCTION truncate_test_tables()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  TRUNCATE TABLE
    -- Junction / child tables first so FK constraints are satisfied
    public.collection_entries,
    public.collection_editors,
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
    public.images,
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

GRANT EXECUTE ON FUNCTION public.truncate_test_tables() TO service_role;
