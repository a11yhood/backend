-- DEV/TEST ONLY: atomic truncate function for database reset.
-- This function must ONLY be applied to the test Supabase project.
-- Never apply to production.
--
-- Called by POST /api/dev/reset via db.rpc("dev_truncate_all_tables").
-- Using TRUNCATE ... CASCADE lets Postgres resolve FK ordering automatically.
-- Returns a JSON summary of tables cleared.

CREATE OR REPLACE FUNCTION dev_truncate_all_tables()
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  tables text[] := ARRAY[
    'product_tags', 'product_editors', 'product_urls',
    'scraping_logs', 'discussions', 'ratings',
    'blog_posts', 'user_activities', 'user_requests',
    'collection_products', 'collections',
    'products', 'tags', 'oauth_configs', 'users'
  ];
  counts jsonb := '{}'::jsonb;
  t text;
  n int;
BEGIN
  -- Collect row counts before truncating
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('SELECT COUNT(*) FROM %I', t) INTO n;
    counts := counts || jsonb_build_object(t, n);
  END LOOP;

  TRUNCATE
    product_tags, product_editors, product_urls,
    scraping_logs, discussions, ratings,
    blog_posts, user_activities, user_requests,
    collection_products, collections,
    products, tags, oauth_configs, users
  CASCADE;

  RETURN json_build_object(
    'status', 'reset',
    'cleared_tables', counts,
    'total_rows_deleted', (
      SELECT SUM(value::int) FROM jsonb_each_text(counts)
    )
  );
END;
$$;

-- Only the service_role (backend) can call this — never anon or authenticated users.
REVOKE ALL ON FUNCTION dev_truncate_all_tables() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION dev_truncate_all_tables() TO service_role;
