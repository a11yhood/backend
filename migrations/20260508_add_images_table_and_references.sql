-- Migration: Add canonical images table and reference columns for products/blog_posts
-- Date: 2026-05-08
--
-- Goals:
--  1. Keep existing API fields (products.image, blog_posts.header_image) as URL strings.
--  2. Add normalized image references via images.id for dedupe/reuse/metadata.
--  3. Backfill existing product/blog image URLs into images and set FK columns.

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

  -- Ensure new columns/constraints exist when table pre-exists from partial runs.
  ALTER TABLE IF EXISTS public.images
    ADD COLUMN IF NOT EXISTS canonical_key TEXT,
    ADD COLUMN IF NOT EXISTS image_data_base64 TEXT;

  ALTER TABLE IF EXISTS public.images
    ALTER COLUMN canonical_url DROP NOT NULL;

  -- Remove the problematic unique index/constraint on long canonical_url values.
  DO $$
  BEGIN
    IF EXISTS (
      SELECT 1
      FROM pg_constraint
      WHERE conname = 'images_canonical_url_key'
    ) THEN
      ALTER TABLE public.images DROP CONSTRAINT images_canonical_url_key;
    END IF;
  END;
  $$;

  DROP INDEX IF EXISTS public.images_canonical_url_key;

  -- Normalize pre-existing uploaded rows that may still store full data URLs.
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
      ELSE source_kind
    END
  WHERE canonical_url ILIKE 'data:%';

  -- Build deterministic compact dedupe keys.
  UPDATE public.images
  SET canonical_key = CASE
    WHEN source_kind = 'uploaded' THEN
      'uploaded:' || md5(COALESCE(image_data_base64, ''))
    ELSE
      'external:' || md5(COALESCE(canonical_url, ''))
  END
  WHERE canonical_key IS NULL;

  -- Backstop legacy rows with empty payload/url values.
  UPDATE public.images
  SET canonical_key = 'legacy:' || md5(id::text)
  WHERE canonical_key IS NULL;

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
