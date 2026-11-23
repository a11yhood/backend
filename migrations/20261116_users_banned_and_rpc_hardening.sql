-- 1) Account suspension (enforced in services/auth.py get_current_user)
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS banned BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS banned_reason TEXT;

-- Only admins may change ban fields (the existing role trigger does not cover them).
-- The backend uses the service role, which has no auth.uid(), so allow that too.
CREATE OR REPLACE FUNCTION public.prevent_non_admin_ban_change()
RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
  IF (NEW.banned IS DISTINCT FROM OLD.banned
      OR NEW.banned_at IS DISTINCT FROM OLD.banned_at
      OR NEW.banned_reason IS DISTINCT FROM OLD.banned_reason)
     AND auth.uid() IS NOT NULL AND NOT public.is_admin() THEN
    RAISE EXCEPTION 'Only admins can change ban status';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_prevent_ban_change ON public.users;
CREATE TRIGGER trg_prevent_ban_change BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.prevent_non_admin_ban_change();

-- 2) RPC hardening. Postgres grants EXECUTE on new functions to PUBLIC, and Supabase
-- exposes every public-schema function at /rest/v1/rpc/*. Revoke everything, then
-- re-grant only the intentionally public read-only helpers.
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;

-- Future functions: no implicit access for API roles.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

-- Public read-only RPCs (called by the backend, but safe for anon to call directly).
DO $$
BEGIN
  IF to_regprocedure('public.get_product_source_counts()') IS NOT NULL THEN
    GRANT EXECUTE ON FUNCTION public.get_product_source_counts() TO anon, authenticated;
  END IF;
  IF to_regprocedure('public.get_product_tags_filtered(text[],text,text,uuid,timestamptz,boolean,int)') IS NOT NULL THEN
    GRANT EXECUTE ON FUNCTION public.get_product_tags_filtered(text[],text,text,uuid,timestamptz,boolean,int) TO anon, authenticated;
  END IF;
  -- RLS policies call is_admin() as the requesting role, so it must stay executable.
  IF to_regprocedure('public.is_admin()') IS NOT NULL THEN
    GRANT EXECUTE ON FUNCTION public.is_admin() TO anon, authenticated;
  END IF;
END $$;
-- Trigger functions run as the table owner/invoker without needing EXECUTE grants.
