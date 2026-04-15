-- Deprecate integer/bigint storage for blog post timestamps.
-- Convert legacy epoch columns to TIMESTAMPTZ when needed.
--
-- Columns handled: published_at, publish_date, created_at, updated_at
--
-- Production hardening:
-- - Supports epoch milliseconds and epoch seconds values.
-- - Fails fast on invalid/out-of-range values to avoid silent data corruption.

DO $$
DECLARE
  col_name text;
  col_data_type text;
  invalid_count bigint;
  target_cols text[] := ARRAY['published_at', 'publish_date', 'created_at', 'updated_at'];
BEGIN
  FOREACH col_name IN ARRAY target_cols
  LOOP
    SELECT data_type
    INTO col_data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'blog_posts'
      AND column_name = col_name;

    IF col_data_type IN ('bigint', 'integer', 'smallint') THEN
      EXECUTE format(
        'SELECT COUNT(*) FROM public.blog_posts
         WHERE %1$I IS NOT NULL
           AND (
             %1$I < 0
             OR %1$I > 32503680000000
             OR (%1$I > 0 AND %1$I < 1000000000)
           )',
        col_name
      )
      INTO invalid_count;

      IF invalid_count > 0 THEN
        RAISE EXCEPTION USING
          MESSAGE = format('Cannot migrate blog_posts.%s: found invalid epoch values', col_name),
          DETAIL = format('Invalid rows in %s: %s', col_name, invalid_count),
          HINT = 'Normalize invalid timestamps before rerunning this migration.';
      END IF;

      EXECUTE format(
        'ALTER TABLE public.blog_posts
           ALTER COLUMN %1$I TYPE timestamptz
           USING (
             CASE
               WHEN %1$I IS NULL THEN NULL
               WHEN %1$I >= 100000000000
                 THEN to_timestamp((%1$I::double precision) / 1000.0)
               ELSE
                 to_timestamp(%1$I::double precision)
             END
           )',
        col_name
      );
    END IF;
  END LOOP;
END $$;
