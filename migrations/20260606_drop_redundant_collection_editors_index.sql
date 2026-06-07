-- Drop redundant composite index duplicated by UNIQUE(collection_id, user_id).
-- The unique constraint already provides a btree index on the same column order.
DROP INDEX IF EXISTS public.idx_collection_editors_collection_user;
