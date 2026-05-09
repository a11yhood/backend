-- Hotfix: Repair images schema/data for payload storage + compact dedupe keys
-- Date: 2026-05-08
--
-- Purpose:
--  1) Ensure uploaded image payloads are stored in image_data_base64 (not canonical_url).
--  2) Replace canonical_url uniqueness with canonical_key uniqueness.
--  3) Safely dedupe existing images rows and repair FK references.
--  4) Backfill products.image_id and blog_posts.header_image_id.
--
-- This script is idempotent and safe for partially applied migration states.

CREATE TABLE IF NOT EXISTS public.images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_url TEXT,
    canonical_key TEXT,
    image_data_base64 TEXT,
    source_kind TEXT NOT NULL DEFAULT 'external' CHECK (source_kind IN ('external', 'uploaded')),
    mime_type TEXT,
    byte_size INTEGER,
    width INTEGER,
    height INTEGER,
    default_alt TEXT,
    created_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.images
  ADD COLUMN IF NOT EXISTS canonical_url TEXT,
  ADD COLUMN IF NOT EXISTS canonical_key TEXT,
  ADD COLUMN IF NOT EXISTS image_data_base64 TEXT,
  ADD COLUMN IF NOT EXISTS source_kind TEXT,
  ADD COLUMN IF NOT EXISTS mime_type TEXT;

ALTER TABLE IF EXISTS public.images
  ALTER COLUMN canonical_url DROP NOT NULL;

ALTER TABLE IF EXISTS public.images
  ALTER COLUMN source_kind SET DEFAULT 'external';

UPDATE public.images
SET source_kind = 'external'
WHERE source_kind IS NULL;

-- Drop legacy unique constraints/indexes on canonical_url if present.
DO $$
DECLARE
  c RECORD;
BEGIN
  FOR c IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'public.images'::regclass
      AND contype = 'u'
      AND conname IN ('images_canonical_url_key')
  LOOP
    EXECUTE format('ALTER TABLE public.images DROP CONSTRAINT %I', c.conname);
  END LOOP;
END;
$$;

DROP INDEX IF EXISTS public.images_canonical_url_key;
DROP INDEX IF EXISTS public.idx_images_canonical_url_unique;

-- Normalize existing uploaded rows that still have full data URLs in canonical_url.
UPDATE public.images
SET
  image_data_base64 = COALESCE(
    image_data_base64,
    NULLIF(split_part(canonical_url, ',', 2), '')
  ),
  mime_type = COALESCE(
    mime_type,
    NULLIF(split_part(split_part(canonical_url, ';', 1), ':', 2), '')
  ),
  canonical_url = CASE
    WHEN canonical_url ILIKE 'data:%' THEN NULL
    ELSE canonical_url
  END,
  source_kind = CASE
    WHEN canonical_url ILIKE 'data:%' THEN 'uploaded'
    ELSE COALESCE(source_kind, 'external')
  END
WHERE canonical_url ILIKE 'data:%';

-- Ensure canonical_key exists for every row.
UPDATE public.images
SET canonical_key = CASE
  WHEN source_kind = 'uploaded' THEN
    'uploaded:' || md5(COALESCE(image_data_base64, ''))
  ELSE
    'external:' || md5(COALESCE(canonical_url, ''))
END
WHERE canonical_key IS NULL;

UPDATE public.images
SET canonical_key = 'legacy:' || md5(id::text)
WHERE canonical_key IS NULL;

-- Dedupe by canonical_key while preserving existing references.
DROP TABLE IF EXISTS _images_keep_map;
DROP TABLE IF EXISTS _images_drop_map;

CREATE TEMP TABLE _images_keep_map AS
SELECT DISTINCT ON (canonical_key)
  canonical_key,
  id AS keep_id
FROM public.images
ORDER BY canonical_key, id;

CREATE TEMP TABLE _images_drop_map AS
SELECT i.id AS drop_id, k.keep_id
FROM public.images i
JOIN _images_keep_map k ON k.canonical_key = i.canonical_key
WHERE i.id <> k.keep_id;

UPDATE public.products p
SET image_id = m.keep_id
FROM _images_drop_map m
WHERE p.image_id = m.drop_id;

UPDATE public.blog_posts b
SET header_image_id = m.keep_id
FROM _images_drop_map m
WHERE b.header_image_id = m.drop_id;

DELETE FROM public.images i
USING _images_drop_map m
WHERE i.id = m.drop_id;

ALTER TABLE IF EXISTS public.images
  ALTER COLUMN canonical_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_images_canonical_key_unique
  ON public.images(canonical_key);

ALTER TABLE IF EXISTS public.images ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS images_select_all ON public.images;
CREATE POLICY images_select_all
ON public.images FOR SELECT
TO authenticated, anon
USING (true);

DROP POLICY IF EXISTS images_admin_write ON public.images;
CREATE POLICY images_admin_write
ON public.images FOR ALL
TO authenticated
USING (public.is_admin())
WITH CHECK (public.is_admin());

CREATE INDEX IF NOT EXISTS idx_images_source_kind ON public.images(source_kind);

ALTER TABLE public.products
  ADD COLUMN IF NOT EXISTS image_id UUID REFERENCES public.images(id) ON DELETE SET NULL;

ALTER TABLE public.blog_posts
  ADD COLUMN IF NOT EXISTS header_image_id UUID REFERENCES public.images(id) ON DELETE SET NULL;

-- Backfill product image references.
INSERT INTO public.images (
  id,
  canonical_key,
  canonical_url,
  image_data_base64,
  source_kind,
  mime_type
)
SELECT
  gen_random_uuid(),
  CASE
    WHEN p.image ILIKE 'data:%' THEN
      'uploaded:' || md5(COALESCE(NULLIF(split_part(p.image, ',', 2), ''), p.image))
    ELSE
      'external:' || md5(p.image)
  END,
  CASE
    WHEN p.image ILIKE 'data:%' THEN NULL
    ELSE p.image
  END,
  CASE
    WHEN p.image ILIKE 'data:%' THEN NULLIF(split_part(p.image, ',', 2), '')
    ELSE NULL
  END,
  CASE
    WHEN p.image ILIKE 'data:%' THEN 'uploaded'
    ELSE 'external'
  END,
  CASE
    WHEN p.image ILIKE 'data:%' THEN NULLIF(split_part(split_part(p.image, ';', 1), ':', 2), '')
    ELSE NULL
  END
FROM public.products p
WHERE p.image IS NOT NULL
  AND btrim(p.image) <> ''
ON CONFLICT (canonical_key) DO NOTHING;

UPDATE public.products p
SET image_id = i.id
FROM public.images i
WHERE p.image_id IS NULL
  AND p.image IS NOT NULL
  AND btrim(p.image) <> ''
  AND i.canonical_key = CASE
    WHEN p.image ILIKE 'data:%' THEN
      'uploaded:' || md5(COALESCE(NULLIF(split_part(p.image, ',', 2), ''), p.image))
    ELSE
      'external:' || md5(p.image)
  END;

-- Backfill blog post header image references.
INSERT INTO public.images (
  id,
  canonical_key,
  canonical_url,
  image_data_base64,
  source_kind,
  mime_type
)
SELECT
  gen_random_uuid(),
  CASE
    WHEN b.header_image ILIKE 'data:%' THEN
      'uploaded:' || md5(COALESCE(NULLIF(split_part(b.header_image, ',', 2), ''), b.header_image))
    ELSE
      'external:' || md5(b.header_image)
  END,
  CASE
    WHEN b.header_image ILIKE 'data:%' THEN NULL
    ELSE b.header_image
  END,
  CASE
    WHEN b.header_image ILIKE 'data:%' THEN NULLIF(split_part(b.header_image, ',', 2), '')
    ELSE NULL
  END,
  CASE
    WHEN b.header_image ILIKE 'data:%' THEN 'uploaded'
    ELSE 'external'
  END,
  CASE
    WHEN b.header_image ILIKE 'data:%' THEN NULLIF(split_part(split_part(b.header_image, ';', 1), ':', 2), '')
    ELSE NULL
  END
FROM public.blog_posts b
WHERE b.header_image IS NOT NULL
  AND btrim(b.header_image) <> ''
ON CONFLICT (canonical_key) DO NOTHING;

UPDATE public.blog_posts b
SET header_image_id = i.id
FROM public.images i
WHERE b.header_image_id IS NULL
  AND b.header_image IS NOT NULL
  AND btrim(b.header_image) <> ''
  AND i.canonical_key = CASE
    WHEN b.header_image ILIKE 'data:%' THEN
      'uploaded:' || md5(COALESCE(NULLIF(split_part(b.header_image, ',', 2), ''), b.header_image))
    ELSE
      'external:' || md5(b.header_image)
  END;

CREATE INDEX IF NOT EXISTS idx_products_image_id ON public.products(image_id);
CREATE INDEX IF NOT EXISTS idx_blog_posts_header_image_id ON public.blog_posts(header_image_id);
