-- Atomically replace collection entries and product projections.
--
-- This function performs a full replacement in a single database transaction:
-- 1) replace rows in collection_entries
-- 2) resync product-only projection in collection_products

CREATE OR REPLACE FUNCTION public.replace_collection_entries(
  p_collection_id UUID,
  p_entries JSONB DEFAULT '[]'::jsonb
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_entries JSONB := COALESCE(p_entries, '[]'::jsonb);
BEGIN
  IF jsonb_typeof(v_entries) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'p_entries must be a JSON array';
  END IF;

  -- Ensure the collection exists before mutating related rows.
  IF NOT EXISTS (SELECT 1 FROM public.collections WHERE id = p_collection_id) THEN
    RAISE EXCEPTION 'Collection not found: %', p_collection_id;
  END IF;

  DELETE FROM public.collection_entries
  WHERE collection_id = p_collection_id;

  IF jsonb_array_length(v_entries) > 0 THEN
    INSERT INTO public.collection_entries (
      collection_id,
      kind,
      position,
      label,
      product_id,
      collection_ref_id,
      blog_post_id,
      query_json
    )
    SELECT
      p_collection_id,
      entry.kind,
      entry.position,
      entry.label,
      entry.product_id,
      entry.collection_ref_id,
      entry.blog_post_id,
      entry.query_json
    FROM (
      SELECT
        elem->>'kind' AS kind,
        ordinality - 1 AS position,
        elem->>'label' AS label,
        NULLIF(elem->>'product_id', '')::UUID AS product_id,
        NULLIF(elem->>'collection_id', '')::UUID AS collection_ref_id,
        NULLIF(elem->>'blog_post_id', '')::UUID AS blog_post_id,
        elem->'query' AS query_json
      FROM jsonb_array_elements(v_entries) WITH ORDINALITY AS e(elem, ordinality)
    ) AS entry;
  END IF;

  DELETE FROM public.collection_products
  WHERE collection_id = p_collection_id;

  INSERT INTO public.collection_products (collection_id, product_id, position)
  SELECT
    p_collection_id,
    ce.product_id,
    ce.position
  FROM public.collection_entries ce
  WHERE ce.collection_id = p_collection_id
    AND ce.kind = 'product'
    AND ce.product_id IS NOT NULL
  ORDER BY ce.position;
END;
$$;

REVOKE ALL ON FUNCTION public.replace_collection_entries(UUID, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.replace_collection_entries(UUID, JSONB) TO service_role;
