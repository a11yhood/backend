-- Issues #65 / #47: make computed_rating maintenance cheap.
--
-- Problems with the previous setup:
--   1. trg_rating_update_computed_rating was FOR EACH ROW: a bulk insert/update/delete of N
--      ratings ran N sequential UPDATEs on products (each calling compute_product_rating,
--      which itself re-queried ratings AND products), queueing row locks on hot products.
--   2. The BEFORE INSERT/UPDATE OF source_rating trigger on products computed the rating by
--      re-reading the products row. On INSERT the row does not exist yet, and on UPDATE the
--      table still holds the OLD source_rating, so computed_rating used a NULL/stale value.
--   3. Every rating write rewrote the product row even when computed_rating did not change.
--
-- Changes:
--   * compute_display_rating(): pure blend function (no queries), shared by every caller.
--     Argument order (user_avg, source_rating, user_count) matches services/ratings.py.
--   * compute_product_rating(): kept for backfills/manual use; now delegates to the above.
--   * update_own_computed_rating(): uses NEW.source_rating directly; skips the ratings lookup
--     on INSERT (a brand-new product cannot have ratings).
--   * ratings trigger: three statement-level triggers using transition tables. One statement
--     now costs a single set-based UPDATE no matter how many ratings it touches, products
--     are locked in id order (no lock-order deadlocks), and unchanged values are not written.
--   * idx_ratings_created_at: backs the unfiltered GET /api/ratings ordering.
--
-- computed_rating semantics are unchanged from 20260613 (internal ratings weighted by count,
-- external source rating contributes one blended vote).

CREATE OR REPLACE FUNCTION public.compute_display_rating(
  user_avg NUMERIC,
  source_rating_val NUMERIC,
  user_count INTEGER
)
  RETURNS NUMERIC(3,2)
  LANGUAGE plpgsql
  IMMUTABLE
  SET search_path = public
AS $$
DECLARE
  source_stars NUMERIC;
  display_rating NUMERIC;
BEGIN
  -- source_rating is already normalized by adapters; clamp to star range defensively
  source_stars := CASE
    WHEN source_rating_val IS NULL THEN NULL
    ELSE ROUND(LEAST(GREATEST(source_rating_val, 0), 5), 2)
  END;

  IF COALESCE(user_count, 0) > 0 AND source_stars IS NOT NULL THEN
    display_rating := ROUND(((user_avg * user_count) + source_stars) / (user_count + 1), 2);
  ELSIF COALESCE(user_count, 0) > 0 THEN
    display_rating := ROUND(user_avg, 2);
  ELSIF source_stars IS NOT NULL THEN
    display_rating := source_stars;
  ELSE
    display_rating := NULL;
  END IF;

  RETURN display_rating::NUMERIC(3,2);
END;
$$;

CREATE OR REPLACE FUNCTION public.compute_product_rating(product_id_param UUID)
  RETURNS NUMERIC(3,2)
  LANGUAGE plpgsql
  STABLE
  SET search_path = public
AS $$
DECLARE
  user_avg NUMERIC;
  user_count INTEGER;
  source_rating_val NUMERIC;
BEGIN
  SELECT AVG(rating)::NUMERIC, COUNT(*)::INTEGER
    INTO user_avg, user_count
  FROM ratings
  WHERE product_id = product_id_param;

  SELECT source_rating::NUMERIC
    INTO source_rating_val
  FROM products
  WHERE id = product_id_param;

  RETURN compute_display_rating(user_avg, source_rating_val, user_count);
END;
$$;

-- BEFORE INSERT OR UPDATE OF source_rating ON products (trigger itself is unchanged).
CREATE OR REPLACE FUNCTION public.update_own_computed_rating()
  RETURNS trigger
  LANGUAGE plpgsql
  SET search_path = public
AS $$
DECLARE
  user_avg NUMERIC := NULL;
  user_count INTEGER := 0;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    SELECT AVG(rating)::NUMERIC, COUNT(*)::INTEGER
      INTO user_avg, user_count
    FROM ratings
    WHERE product_id = NEW.id;
  END IF;

  NEW.computed_rating := compute_display_rating(user_avg, NEW.source_rating::NUMERIC, user_count);
  RETURN NEW;
END;
$$;

-- Recompute computed_rating for a set of products in one statement.
CREATE OR REPLACE FUNCTION public.refresh_product_computed_ratings(product_ids UUID[])
  RETURNS void
  LANGUAGE plpgsql
  SET search_path = public
AS $$
BEGIN
  IF product_ids IS NULL OR cardinality(product_ids) = 0 THEN
    RETURN;
  END IF;

  WITH locked AS (
    -- Lock in a stable order so concurrent multi-product statements cannot deadlock.
    SELECT p.id, p.source_rating
    FROM products p
    WHERE p.id = ANY(product_ids)
    ORDER BY p.id
    FOR UPDATE
  ),
  agg AS (
    SELECT l.id,
           AVG(r.rating)::NUMERIC AS user_avg,
           COUNT(r.rating)::INTEGER AS user_count,
           l.source_rating
    FROM locked l
    LEFT JOIN ratings r ON r.product_id = l.id
    GROUP BY l.id, l.source_rating
  ),
  calc AS (
    SELECT id,
           compute_display_rating(user_avg, source_rating::NUMERIC, user_count) AS new_rating
    FROM agg
  )
  UPDATE products p
  SET computed_rating = calc.new_rating
  FROM calc
  WHERE p.id = calc.id
    AND p.computed_rating IS DISTINCT FROM calc.new_rating;
END;
$$;

CREATE OR REPLACE FUNCTION public.ratings_after_insert_refresh()
  RETURNS trigger
  LANGUAGE plpgsql
  SET search_path = public
AS $$
BEGIN
  PERFORM refresh_product_computed_ratings(
    ARRAY(SELECT DISTINCT product_id FROM new_rows WHERE product_id IS NOT NULL)
  );
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.ratings_after_update_refresh()
  RETURNS trigger
  LANGUAGE plpgsql
  SET search_path = public
AS $$
BEGIN
  -- Include OLD product ids so a rating moved between products refreshes both.
  PERFORM refresh_product_computed_ratings(
    ARRAY(
      SELECT product_id FROM new_rows WHERE product_id IS NOT NULL
      UNION
      SELECT product_id FROM old_rows WHERE product_id IS NOT NULL
    )
  );
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.ratings_after_delete_refresh()
  RETURNS trigger
  LANGUAGE plpgsql
  SET search_path = public
AS $$
BEGIN
  PERFORM refresh_product_computed_ratings(
    ARRAY(SELECT DISTINCT product_id FROM old_rows WHERE product_id IS NOT NULL)
  );
  RETURN NULL;
END;
$$;

-- Replace the row-level trigger. Transition tables cannot be combined across events,
-- so there is one statement-level trigger per operation.
DROP TRIGGER IF EXISTS trg_rating_update_computed_rating ON ratings;
DROP TRIGGER IF EXISTS trg_ratings_computed_rating_insert ON ratings;
DROP TRIGGER IF EXISTS trg_ratings_computed_rating_update ON ratings;
DROP TRIGGER IF EXISTS trg_ratings_computed_rating_delete ON ratings;

CREATE TRIGGER trg_ratings_computed_rating_insert
AFTER INSERT ON ratings
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION public.ratings_after_insert_refresh();

CREATE TRIGGER trg_ratings_computed_rating_update
AFTER UPDATE ON ratings
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION public.ratings_after_update_refresh();

CREATE TRIGGER trg_ratings_computed_rating_delete
AFTER DELETE ON ratings
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION public.ratings_after_delete_refresh();

-- The row-level trigger function is no longer referenced by any trigger.
DROP FUNCTION IF EXISTS public.update_product_computed_rating();

CREATE INDEX IF NOT EXISTS idx_ratings_created_at ON ratings(created_at DESC);
