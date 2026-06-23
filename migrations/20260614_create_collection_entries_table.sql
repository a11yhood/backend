-- Create typed collection entries to support nested collections and query/blog references.
-- Backward compatibility: product entries are backfilled from collection_products.

CREATE TABLE IF NOT EXISTS collection_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('product', 'collection', 'blogPost', 'query')),
    position INTEGER NOT NULL DEFAULT 0,
    label TEXT,
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    collection_ref_id UUID REFERENCES collections(id) ON DELETE CASCADE,
    blog_post_id UUID REFERENCES blog_posts(id) ON DELETE CASCADE,
    query_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT collection_entries_target_required CHECK (
        (kind = 'product' AND product_id IS NOT NULL AND collection_ref_id IS NULL AND blog_post_id IS NULL AND query_json IS NULL)
        OR (kind = 'collection' AND collection_ref_id IS NOT NULL AND product_id IS NULL AND blog_post_id IS NULL AND query_json IS NULL)
        OR (kind = 'blogPost' AND blog_post_id IS NOT NULL AND product_id IS NULL AND collection_ref_id IS NULL AND query_json IS NULL)
        OR (kind = 'query' AND query_json IS NOT NULL AND product_id IS NULL AND collection_ref_id IS NULL AND blog_post_id IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_entries_collection_position
ON collection_entries(collection_id, position);

CREATE INDEX IF NOT EXISTS idx_collection_entries_kind
ON collection_entries(kind);

CREATE INDEX IF NOT EXISTS idx_collection_entries_product_id
ON collection_entries(product_id);

CREATE INDEX IF NOT EXISTS idx_collection_entries_collection_ref_id
ON collection_entries(collection_ref_id);

CREATE INDEX IF NOT EXISTS idx_collection_entries_blog_post_id
ON collection_entries(blog_post_id);

INSERT INTO collection_entries (collection_id, kind, position, product_id)
SELECT cp.collection_id, 'product', COALESCE(cp.position, 0), cp.product_id
FROM collection_products cp
LEFT JOIN collection_entries ce
  ON ce.collection_id = cp.collection_id
 AND ce.kind = 'product'
 AND ce.product_id = cp.product_id
WHERE ce.id IS NULL;
