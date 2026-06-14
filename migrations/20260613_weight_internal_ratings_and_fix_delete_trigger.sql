-- Blend internal (A11yhood) and external source ratings for computed display score.
-- Internal ratings are weighted by their count; external contributes one blended vote.
-- Also fix rating trigger updates so DELETE operations recompute computed_rating safely.

CREATE OR REPLACE FUNCTION public.compute_product_rating(product_id_param UUID)
  RETURNS NUMERIC(3,2)
  LANGUAGE plpgsql
  SET search_path = public
AS $$
DECLARE
  user_avg NUMERIC;
  user_count INTEGER;
  source_rating_val NUMERIC;
  source_stars NUMERIC;
  display_rating NUMERIC;
BEGIN
  SELECT AVG(rating)::NUMERIC, COUNT(*)::INTEGER
    INTO user_avg, user_count
  FROM ratings
  WHERE product_id = product_id_param;

  SELECT source_rating::NUMERIC
    INTO source_rating_val
  FROM products
  WHERE id = product_id_param;

  -- source_rating is already normalized by adapters; clamp to star range defensively
  source_stars := CASE
    WHEN source_rating_val IS NULL THEN NULL
    ELSE ROUND(LEAST(GREATEST(source_rating_val, 0), 5), 2)
  END;

  IF user_count > 0 AND source_stars IS NOT NULL THEN
    display_rating := ROUND(((user_avg * user_count) + source_stars) / (user_count + 1), 2);
  ELSIF user_count > 0 THEN
    display_rating := ROUND(user_avg, 2);
  ELSIF source_stars IS NOT NULL THEN
    display_rating := source_stars;
  ELSE
    display_rating := NULL;
  END IF;

  RETURN display_rating::NUMERIC(3,2);
END;
$$;

CREATE OR REPLACE FUNCTION public.update_product_computed_rating()
  RETURNS trigger
  LANGUAGE plpgsql
  SET search_path = public
AS $$
DECLARE
  target_product_id UUID;
BEGIN
  target_product_id := CASE
    WHEN TG_OP = 'DELETE' THEN OLD.product_id
    ELSE NEW.product_id
  END;

  IF target_product_id IS NOT NULL THEN
    UPDATE products
    SET computed_rating = compute_product_rating(target_product_id)
    WHERE id = target_product_id;
  END IF;

  RETURN COALESCE(NEW, OLD);
END;
$$;

-- Ensure existing rows reflect the updated weighting model.
UPDATE products
SET computed_rating = compute_product_rating(id);
