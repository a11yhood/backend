-- Deprecate BIGINT storage for user activity timestamps.
-- Convert public.user_activities.timestamp to TIMESTAMPTZ when legacy BIGINT schema is present.
--
-- Production hardening:
-- - Supports legacy epoch milliseconds and epoch seconds values.
-- - Fails fast when values are invalid/out-of-range so bad data is not silently converted.

DO $$
DECLARE
  ts_data_type text;
  invalid_count bigint;
BEGIN
  SELECT data_type
  INTO ts_data_type
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'user_activities'
    AND column_name = 'timestamp';

  IF ts_data_type = 'bigint' THEN
    -- Guardrail: ensure all values can be interpreted as epoch seconds or milliseconds.
    -- Thresholds:
    -- - >= 100000000000   => milliseconds (covers all modern ms timestamps)
    -- - >= 1000000000     => seconds (covers modern second-based epochs)
    -- Reject negative and unrealistic far-future values (> year 3000 in ms).
    SELECT COUNT(*)
    INTO invalid_count
    FROM public.user_activities
    WHERE "timestamp" < 0
       OR "timestamp" > 32503680000000
       OR ("timestamp" > 0 AND "timestamp" < 1000000000);

    IF invalid_count > 0 THEN
      RAISE EXCEPTION USING
        MESSAGE = 'Cannot migrate user_activities.timestamp: found invalid epoch values',
        DETAIL = format('Invalid rows: %s', invalid_count),
        HINT = 'Normalize invalid timestamps before rerunning this migration.';
    END IF;

    ALTER TABLE public.user_activities
      ALTER COLUMN "timestamp" TYPE timestamptz
      USING (
        CASE
          WHEN "timestamp" >= 100000000000
            THEN to_timestamp(("timestamp"::double precision) / 1000.0)
          ELSE
            to_timestamp("timestamp"::double precision)
        END
      );
  END IF;
END $$;
