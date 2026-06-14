-- Recompute Thingiverse source ratings using the same log-based mapping as the scraper.
-- Adapter formula: round(clamp(1 + log10(makes), 1.0, 5.0), 2), with makes <= 0 => NULL.
-- In persisted rows, source_rating_count stores Thingiverse makes.
-- This migration is idempotent: only rows with changed values are updated.

WITH recalculated AS (
  SELECT
    p.id,
    CASE
      WHEN COALESCE(p.source_rating_count, 0) <= 0 THEN NULL::NUMERIC(3,2)
      ELSE ROUND(
        LEAST(
          GREATEST(1.0 + LOG(10, p.source_rating_count::NUMERIC), 1.0),
          5.0
        ),
        2
      )::NUMERIC(3,2)
    END AS new_source_rating
  FROM products p
  WHERE LOWER(p.source) = 'thingiverse'
),
changed AS (
  SELECT p.id, r.new_source_rating
  FROM products p
  JOIN recalculated r ON r.id = p.id
  WHERE p.source_rating IS DISTINCT FROM r.new_source_rating
),
updated_source AS (
  UPDATE products p
  SET source_rating = c.new_source_rating
  FROM changed c
  WHERE p.id = c.id
  RETURNING p.id
)
UPDATE products p
SET computed_rating = compute_product_rating(p.id)
WHERE p.id IN (SELECT id FROM updated_source);
