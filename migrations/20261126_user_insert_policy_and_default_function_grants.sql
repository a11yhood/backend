-- Follow-up to 20261116_users_banned_and_rpc_hardening.sql. Safe to re-run.

-- 1) A signed-in client may only create its own row, and only with the base role.
-- The backend uses the service role, which bypasses RLS.
DROP POLICY IF EXISTS users_insert_authenticated ON public.users;
CREATE POLICY users_insert_authenticated
  ON public.users FOR INSERT
  TO authenticated
  WITH CHECK ((select auth.uid()) = id AND role = 'user');

-- 2) New functions get no implicit EXECUTE. The default grant to PUBLIC is global,
-- so it can only be revoked without IN SCHEMA (the per-schema form has no effect on it).
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO service_role;
