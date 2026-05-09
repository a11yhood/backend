-- Migration: Replace url column with source_url in products table
-- Date: 2026-04-18
--
-- Resolves the url/source_url divergence by:
--  1. Ensuring source_url is populated from url (backfill)
--  2. Preserving any url values that differ from source_url in product_urls
--  3. Dropping the old url column
--  4. Adding partial unique indexes for identity resolution (external_id first, source_url fallback)

-- Step 1: Ensure source_url column exists (was added in 20260307 but re-stated for safety)
ALTER TABLE public.products ADD COLUMN IF NOT EXISTS source_url TEXT;

-- Step 2: Backfill source_url from url for any remaining NULL rows
DO $$
BEGIN
        IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = 'products'
                    AND column_name = 'url'
        ) THEN
                UPDATE public.products
                SET source_url = url
                WHERE source_url IS NULL
                    AND url IS NOT NULL;
        END IF;
END;
$$;

-- Step 3: Preserve old url values in product_urls for rows where url differs from source_url.
-- Only for products where created_by is set (required FK on product_urls.created_by).
DO $$
BEGIN
        IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = 'products'
                    AND column_name = 'url'
        ) THEN
                INSERT INTO public.product_urls (id, product_id, url, created_by)
                SELECT
                        gen_random_uuid(),
                        p.id,
                        p.url,
                        p.created_by
                FROM public.products p
                WHERE p.url IS NOT NULL
                    AND p.source_url IS NOT NULL
                    AND p.url <> p.source_url
                    AND p.created_by IS NOT NULL
                ON CONFLICT DO NOTHING;
        END IF;
END;
$$;

-- Step 4: Drop old url-related indexes before removing the column
DROP INDEX IF EXISTS public.products_url_idx;
DROP INDEX IF EXISTS public.products_url_idx1;

-- Step 5: Drop old unique constraints/indexes for url/source_url.
-- In some environments, products_url_key is a UNIQUE CONSTRAINT-backed index.
-- Drop constraints first (safe no-op when absent), then stale indexes.
ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_url_key;
ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_source_url_key;
DROP INDEX IF EXISTS public.products_url_key;

-- Drop the old non-partial unique index on source_url that was added in 20260307.
-- It will be replaced by the two partial indexes below.
DROP INDEX IF EXISTS public.products_source_url_key;

-- Step 6: Drop the old unconditional UNIQUE(source, external_id) table constraint
--         (auto-named by Postgres). It will be replaced by a partial unique index below.
ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_source_external_id_key;

-- Step 7: Add partial unique indexes for identity resolution
-- Primary identity: source + external_id (when external_id is present)
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_source_external_id
    ON public.products (source, external_id)
    WHERE external_id IS NOT NULL;

-- Secondary identity: source + source_url (when external_id is absent)
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_source_source_url
    ON public.products (source, source_url)
    WHERE external_id IS NULL AND source_url IS NOT NULL;

-- General lookup index on source_url
CREATE INDEX IF NOT EXISTS idx_products_source_url_lookup
    ON public.products (source_url);

-- Step 8: Drop the old url column
ALTER TABLE public.products DROP COLUMN IF EXISTS url;
