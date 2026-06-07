-- Normalize collection_editors semantics: keep owner in collections.user_id only.
-- Remove any rows where collection owner was redundantly inserted as an editor.
DELETE FROM public.collection_editors AS ce
USING public.collections AS c
WHERE ce.collection_id = c.id
  AND ce.user_id = c.user_id;
