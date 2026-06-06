-- Add 'collection-ownership' support to user_requests
-- 2026-06-03: Enables collection collaborator request workflow

ALTER TABLE public.user_requests
ADD COLUMN IF NOT EXISTS collection_id UUID REFERENCES public.collections(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_user_requests_collection_id
  ON public.user_requests(collection_id);

ALTER TABLE public.user_requests
DROP CONSTRAINT IF EXISTS user_requests_type_check;

ALTER TABLE public.user_requests
ADD CONSTRAINT user_requests_type_check
CHECK (type IN ('moderator', 'admin', 'product-ownership', 'source-domain', 'collection-ownership'));