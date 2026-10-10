-- Issue #270: product types are being retired in favor of tags.
--
-- Phase 1 (this migration): convert the three recoverable types into tags.
-- Other types (Software, Hardware, Assistive Tech, App or Website, Other) were
-- not accurate enough to carry over and are intentionally dropped.
-- The products.type column is left in place; it is dropped in a later migration
-- once the frontend no longer sends it.
--
-- Idempotent: safe to run more than once.

INSERT INTO tags (name)
VALUES ('knitting'), ('crochet'), ('fabrication')
ON CONFLICT (name) DO NOTHING;

INSERT INTO product_tags (product_id, tag_id)
SELECT p.id, t.id
FROM products p
JOIN tags t ON t.name = lower(btrim(p.type))
WHERE lower(btrim(p.type)) IN ('knitting', 'crochet', 'fabrication')
ON CONFLICT (product_id, tag_id) DO NOTHING;
