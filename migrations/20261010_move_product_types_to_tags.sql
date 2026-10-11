-- Issue #270: product types are being retired in favor of tags.
--
-- Phase 1 (this migration): convert the three recoverable types into tags.
-- Other types (Software, Hardware, Assistive Tech, App or Website, Other) were
-- not accurate enough to carry over and are intentionally dropped.
-- The products.type column is left in place; it is dropped in a later migration
-- (run this one BEFORE that one, since it reads products.type).
--
-- Tag names are case-sensitive in the application, so an existing "Knitting" tag
-- (or similar) is reused instead of creating a second "knitting" tag.
--
-- Idempotent: safe to run more than once.

-- 1. Create any of the three tags that do not exist yet (any capitalization).
INSERT INTO tags (name)
SELECT v.name
FROM (VALUES ('knitting'), ('crochet'), ('fabrication')) AS v(name)
WHERE NOT EXISTS (SELECT 1 FROM tags t WHERE lower(t.name) = v.name);

-- 2. Link products to the matching tag. If several capitalizations exist, prefer
--    the all-lowercase one, then the alphabetically first, so each product gets
--    exactly one tag per type.
WITH canonical AS (
  SELECT DISTINCT ON (lower(name)) id, lower(name) AS key
  FROM tags
  WHERE lower(name) IN ('knitting', 'crochet', 'fabrication')
  ORDER BY lower(name), (name = lower(name)) DESC, name
)
INSERT INTO product_tags (product_id, tag_id)
SELECT p.id, c.id
FROM products p
JOIN canonical c ON c.key = lower(btrim(p.type))
ON CONFLICT (product_id, tag_id) DO NOTHING;
