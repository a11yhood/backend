-- Phase 3 of #270: drop products.type now that product types live in tags.
--
-- RUN ORDER: apply 20261010_move_product_types_to_tags.sql FIRST. That migration
-- reads products.type to create the tags; this one destroys the column.
-- Deploy the backend/frontend that no longer reference `type` before applying.
--
-- Idempotent: safe to re-run.

BEGIN;

DROP INDEX IF EXISTS idx_products_type;
DROP INDEX IF EXISTS idx_products_filter_composite;

-- Replacement for the composite index, without the type column.
CREATE INDEX IF NOT EXISTS idx_products_source_banned ON products(source, banned);

DROP FUNCTION IF EXISTS get_product_types();

-- Remove the old signature (with p_types) so the new one is not an ambiguous overload.
DROP FUNCTION IF EXISTS get_product_tags_filtered(TEXT[], TEXT[], TEXT, TEXT, UUID, TIMESTAMPTZ, BOOLEAN, INT);

CREATE OR REPLACE FUNCTION get_product_tags_filtered(
  p_sources TEXT[] DEFAULT NULL,
  p_name_search TEXT DEFAULT NULL,
  p_tag_search TEXT DEFAULT NULL,
  p_created_by UUID DEFAULT NULL,
  p_updated_since TIMESTAMPTZ DEFAULT NULL,
  p_include_banned BOOLEAN DEFAULT FALSE,
  p_limit INT DEFAULT NULL
)
RETURNS TABLE(tag_name TEXT)
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  WITH matching_products AS (
    SELECT p.id
    FROM products p
    WHERE (p_sources IS NULL OR p.source = ANY(p_sources))
      AND (p_name_search IS NULL OR p.name ILIKE '%' || p_name_search || '%')
      AND (p_created_by IS NULL OR p.created_by = p_created_by)
      AND (p_updated_since IS NULL OR p.source_last_updated >= p_updated_since)
      AND (p_include_banned = TRUE OR p.banned = FALSE)
  ),
  matching_tag_ids AS (
    SELECT DISTINCT pt.tag_id
    FROM product_tags pt
    INNER JOIN matching_products mp ON pt.product_id = mp.id
  )
  SELECT t.name as tag_name
  FROM tags t
  INNER JOIN matching_tag_ids mti ON t.id = mti.tag_id
  WHERE (p_tag_search IS NULL OR t.name ILIKE '%' || p_tag_search || '%')
  ORDER BY t.name
  LIMIT COALESCE(p_limit, 1000000);
$$;

GRANT EXECUTE ON FUNCTION get_product_tags_filtered(TEXT[], TEXT, TEXT, UUID, TIMESTAMPTZ, BOOLEAN, INT) TO authenticated, anon;

ALTER TABLE products DROP COLUMN IF EXISTS type;

COMMIT;
