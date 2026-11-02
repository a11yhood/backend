-- Re-create get_product_source_counts() for databases where
-- 20260116_performance_optimizations.sql is recorded as applied but the
-- function was never created (production). Without it, GET /api/products/sources
-- falls back to paging through every product (1000 rows per query).
--
-- Deliberately does not touch get_product_types (dropped by 20261011) or
-- get_product_tags_filtered (re-created by 20261011 without the type filter).

CREATE OR REPLACE FUNCTION public.get_product_source_counts()
RETURNS TABLE(source TEXT, count BIGINT)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT p.source, COUNT(*) AS count
  FROM products p
  WHERE p.source IS NOT NULL
  GROUP BY p.source
  ORDER BY p.source;
$$;

GRANT EXECUTE ON FUNCTION public.get_product_source_counts() TO authenticated, anon;
