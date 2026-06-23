-- Remove the legacy collection_products junction table.
-- All product membership is now stored in collection_entries (kind = 'product').
--
-- Also updates replace_collection_entries to remove the now-deleted sync step.

-- Update the RPC to no longer sync to collection_products.
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
END;
$$;

REVOKE ALL ON FUNCTION public.replace_collection_entries(UUID, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.replace_collection_entries(UUID, JSONB) TO service_role;

-- Backfill any collection_products rows that were added after the initial
-- collection_entries migration ran but before this branch was deployed.
-- The old Python code wrote to collection_products only; rows created in that
-- window would be lost if we drop without a second backfill pass.
INSERT INTO public.collection_entries (collection_id, kind, position, product_id)
SELECT cp.collection_id, 'product', COALESCE(cp.position, 0), cp.product_id
FROM public.collection_products cp
LEFT JOIN public.collection_entries ce
    ON  ce.collection_id = cp.collection_id
    AND ce.kind          = 'product'
    AND ce.product_id    = cp.product_id
WHERE ce.id IS NULL;

-- Drop the legacy junction table (CASCADE removes RLS policies and indexes).
DROP TABLE IF EXISTS public.collection_products CASCADE;
