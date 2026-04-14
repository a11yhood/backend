
  -- a11yhood Supabase Database Schema
  -- Run this in Supabase SQL Editor (Project Settings → Database → SQL Editor)

  -- Enable UUID extension
  CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

  -- Valid product categories
  CREATE TABLE valid_categories (
    category TEXT PRIMARY KEY,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- Insert valid categories
  INSERT INTO valid_categories (category, description) VALUES
    ('Fabrication', '3D printable and DIY projects'),
    ('Software', 'Assistive software and applications'),
    ('Knitting', 'Knitting patterns and projects'),
    ('Crochet', 'Crochet patterns and projects'),
    ('Other', 'Other accessibility products');

  -- Supported product sources (domains where products can be submitted from)
  CREATE TABLE supported_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- Insert supported sources
  INSERT INTO supported_sources (domain, name) VALUES
    ('ravelry.com', 'Ravelry'),
    ('github.com', 'Github'),
    ('thingiverse.com', 'Thingiverse');

  -- Scraper search terms (persisted search terms for each platform)
  CREATE TABLE scraper_search_terms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform TEXT NOT NULL UNIQUE,
    search_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  -- ============================================================================
  -- USERS TABLE
  -- ============================================================================
  CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    github_id TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    avatar_url TEXT,
    email TEXT,
    display_name TEXT,
    bio TEXT,
    location TEXT,
    website TEXT,
    role TEXT DEFAULT 'user' CHECK (role IN ('user', 'moderator', 'admin')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- Ensure fast lookups by username for public routes
  CREATE UNIQUE INDEX IF NOT EXISTS users_username_idx ON public.users (username);

  -- ==== Users table hardening: role constraints, RLS, and admin-only role change ====

  -- Ensure role is constrained and defaults to 'user'
  ALTER TABLE IF EXISTS public.users
    ALTER COLUMN role SET DEFAULT 'user';
  ALTER TABLE IF EXISTS public.users
    ALTER COLUMN role SET NOT NULL;
  ALTER TABLE IF EXISTS public.users
    DROP CONSTRAINT IF EXISTS users_role_check;
  ALTER TABLE IF EXISTS public.users
    ADD CONSTRAINT users_role_check CHECK (role IN ('user','moderator','admin'));

  -- Enable Row Level Security
  ALTER TABLE IF EXISTS public.users ENABLE ROW LEVEL SECURITY;

  -- Helper: check if current auth user is admin (must run after users table exists)
  CREATE OR REPLACE FUNCTION public.is_admin() RETURNS boolean
  LANGUAGE sql STABLE AS $$
    SELECT EXISTS(
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role = 'admin'
    );
  $$;

  -- Enforce RLS on lookup tables used by scrapers and submissions
  ALTER TABLE IF EXISTS public.valid_categories ENABLE ROW LEVEL SECURITY;
  ALTER TABLE IF EXISTS public.supported_sources ENABLE ROW LEVEL SECURITY;

  -- valid_categories policies: anyone can read; only admins manage
  DROP POLICY IF EXISTS valid_categories_select_all ON public.valid_categories;
  CREATE POLICY valid_categories_select_all
  ON public.valid_categories FOR SELECT
  TO authenticated, anon
  USING (true);

  DROP POLICY IF EXISTS valid_categories_admin_write ON public.valid_categories;
  CREATE POLICY valid_categories_admin_write
  ON public.valid_categories FOR ALL
  TO authenticated
  USING (public.is_admin())
  WITH CHECK (public.is_admin());

  -- supported_sources policies: anyone can read; only admins manage
  DROP POLICY IF EXISTS supported_sources_select_all ON public.supported_sources;
  CREATE POLICY supported_sources_select_all
  ON public.supported_sources FOR SELECT
  TO authenticated, anon
  USING (true);

  DROP POLICY IF EXISTS supported_sources_admin_write ON public.supported_sources;
  CREATE POLICY supported_sources_admin_write
  ON public.supported_sources FOR ALL
  TO authenticated
  USING (public.is_admin())
  WITH CHECK (public.is_admin());

  -- Trigger: prevent non-admins from changing the role column
  CREATE OR REPLACE FUNCTION public.prevent_non_admin_role_change()
  RETURNS trigger LANGUAGE plpgsql AS $$
  BEGIN
    IF NEW.role IS DISTINCT FROM OLD.role THEN
      IF NOT public.is_admin() THEN
        RAISE EXCEPTION 'Only admins can change roles';
      END IF;
    END IF;
    RETURN NEW;
  END;
  $$;

  DROP TRIGGER IF EXISTS trg_prevent_role_change ON public.users;
  CREATE TRIGGER trg_prevent_role_change
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.prevent_non_admin_role_change();

  -- Policies: self or admin can read/update; only admin can change role due to trigger
  DROP POLICY IF EXISTS users_select_self_or_admin ON public.users;
  CREATE POLICY users_select_self_or_admin
  ON public.users FOR SELECT
  TO authenticated
  USING (auth.uid() = id OR public.is_admin());

  DROP POLICY IF EXISTS users_update_self_or_admin ON public.users;
  CREATE POLICY users_update_self_or_admin
  ON public.users FOR UPDATE
  TO authenticated
  USING (auth.uid() = id OR public.is_admin())
  WITH CHECK (auth.uid() = id OR public.is_admin());

  DROP POLICY IF EXISTS users_insert_authenticated ON public.users;
  CREATE POLICY users_insert_authenticated
  ON public.users FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = id);

  -- Note: The trigger enforces admin-only role changes regardless of policies.

  -- ============================================================================
  -- PRODUCTS TABLE
  -- ============================================================================
  CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    type TEXT,
    source TEXT NOT NULL,
    url TEXT,
    external_id TEXT,
    external_data JSONB,
    description TEXT NOT NULL,
    image TEXT,
    image_alt TEXT,
    source_rating NUMERIC(3,2),
    source_rating_count INTEGER,
    source_last_updated TIMESTAMPTZ,
    scraped_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    banned BOOLEAN DEFAULT FALSE,
    banned_at TIMESTAMPTZ,
    banned_by UUID REFERENCES users(id) ON DELETE SET NULL,
    banned_reason TEXT,
    last_edited_at TIMESTAMPTZ,
    last_edited_by UUID REFERENCES users(id) ON DELETE SET NULL,
    editor_ids UUID[],
    matched_search_terms JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure uniqueness for scraped products
    UNIQUE(source, external_id),
    UNIQUE(url)
  );

  -- PRODUCT MANAGERS TABLE (for legacy ownership tracking)
  -- Table for product editors/managers who can modify products.
  CREATE TABLE product_editors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(product_id, user_id)
  );

  -- PRODUCT URLS TABLE (per-product external links)
  CREATE TABLE product_urls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    description TEXT,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- ============================================================================
  -- RATINGS TABLE
  -- ============================================================================
  CREATE TABLE ratings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    owned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- One rating per user per product
    UNIQUE(product_id, user_id)
  );

  CREATE TABLE discussions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username TEXT,
    content TEXT NOT NULL,
    blocked BOOLEAN NOT NULL DEFAULT FALSE,
    blocked_by UUID REFERENCES users(id) ON DELETE SET NULL,
    blocked_reason TEXT,
    blocked_at TIMESTAMPTZ,
    parent_id UUID REFERENCES discussions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- ============================================================================
  -- BLOG POSTS TABLE
  -- ============================================================================
  CREATE TABLE blog_posts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    excerpt TEXT,
    header_image TEXT,
    header_image_alt TEXT,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    author_name TEXT NOT NULL,
    author_ids UUID[],
    author_names TEXT[],
    published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    publish_date TIMESTAMPTZ,
    tags TEXT[],
    featured BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- ============================================================================
  -- COLLECTIONS TABLE
  -- ============================================================================
  CREATE TABLE collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug TEXT UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_name TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    product_ids UUID[],
    is_public BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- ============================================================================
  -- USER ACTIVITIES TABLE
  -- ============================================================================
  CREATE TABLE user_activities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('product_submit', 'rating', 'discussion', 'tag')),
    product_id UUID REFERENCES products(id) ON DELETE SET NULL,
    timestamp BIGINT NOT NULL,
    activity_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  -- ==========================================================================
  -- TAGS TABLES (normalized tags)
  -- ==========================================================================

  -- Tags master table
  CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  -- Product-to-tag relationship table
  CREATE TABLE product_tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(product_id, tag_id)
  );

  -- ============================================================================
  -- SCRAPING LOGS TABLE
  -- ============================================================================
  CREATE TABLE scraping_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('thingiverse', 'ravelry', 'github')),
    products_found INTEGER DEFAULT 0,
    products_added INTEGER DEFAULT 0,
    products_updated INTEGER DEFAULT 0,
    duration_seconds NUMERIC DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('success', 'error', 'halted')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  -- ============================================================================
  -- USER REQUESTS TABLE
  -- ============================================================================
  CREATE TABLE user_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('moderator', 'admin', 'product-ownership', 'source-domain')),
    reason TEXT,
    message TEXT,
    product_id UUID REFERENCES products(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    reviewer_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- ============================================================================
  -- OAUTH CONFIGS TABLE (for scraper platform OAuth credentials)
  -- ============================================================================
  CREATE TABLE oauth_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform TEXT NOT NULL UNIQUE CHECK (platform IN ('thingiverse', 'ravelry', 'github')),
    client_id TEXT NOT NULL,
    client_secret TEXT NOT NULL, -- TODO: Encrypt in production
    redirect_uri TEXT NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );

  -- ============================================================================
  -- INDEXES FOR PERFORMANCE
  -- ============================================================================

  -- Users
  CREATE INDEX idx_users_github_id ON users(github_id);
  CREATE INDEX idx_users_username ON users(username);

  -- Products
  CREATE INDEX idx_products_source ON products(source);
  CREATE INDEX idx_products_banned ON products(banned) WHERE banned = TRUE;
  CREATE INDEX idx_products_created_by ON products(created_by);
  CREATE INDEX idx_products_created_at ON products(created_at DESC);

  -- Tags
  CREATE INDEX idx_tags_name ON tags(name);
  CREATE INDEX idx_product_tags_product ON product_tags(product_id);
  CREATE INDEX idx_product_tags_tag ON product_tags(tag_id);

  -- Product URLs
  CREATE INDEX idx_product_urls_product ON product_urls(product_id);
  CREATE INDEX idx_product_urls_creator ON product_urls(created_by);

  -- Ratings
  CREATE INDEX idx_ratings_product ON ratings(product_id);
  CREATE INDEX idx_ratings_user ON ratings(user_id);

  -- Reviews
  CREATE INDEX idx_product_editors_product_user ON product_editors(product_id, user_id);

  -- Discussions
  CREATE INDEX idx_discussions_product ON discussions(product_id);
  CREATE INDEX idx_discussions_user ON discussions(user_id);
  CREATE INDEX idx_discussions_parent ON discussions(parent_id);

  -- Blog Posts
  CREATE INDEX idx_blog_posts_slug ON blog_posts(slug);
  CREATE INDEX idx_blog_posts_author ON blog_posts(author_id);
  CREATE INDEX idx_blog_posts_published ON blog_posts(published) WHERE published = TRUE;
  CREATE INDEX idx_blog_posts_featured ON blog_posts(featured) WHERE featured = TRUE;

  -- Collections
  CREATE INDEX idx_collections_user ON collections(user_id);
  CREATE INDEX idx_collections_public ON collections(is_public) WHERE is_public = TRUE;

  -- User Activities
  CREATE INDEX idx_activities_user ON user_activities(user_id);
  CREATE INDEX idx_activities_created ON user_activities(created_at DESC);
  CREATE INDEX idx_activities_type ON user_activities(type);

  -- User Requests
  CREATE INDEX idx_requests_user ON user_requests(user_id);
  CREATE INDEX idx_requests_status ON user_requests(status);
  CREATE INDEX idx_requests_type ON user_requests(type);

  -- ============================================================================
  -- ROW LEVEL SECURITY (RLS) POLICIES
  -- ============================================================================

  -- Enable RLS on all tables
  ALTER TABLE users ENABLE ROW LEVEL SECURITY;
  ALTER TABLE products ENABLE ROW LEVEL SECURITY;
  ALTER TABLE ratings ENABLE ROW LEVEL SECURITY;
  ALTER TABLE discussions ENABLE ROW LEVEL SECURITY;
  ALTER TABLE blog_posts ENABLE ROW LEVEL SECURITY;
  ALTER TABLE collections ENABLE ROW LEVEL SECURITY;
  ALTER TABLE user_activities ENABLE ROW LEVEL SECURITY;
  ALTER TABLE scraping_logs ENABLE ROW LEVEL SECURITY;
  ALTER TABLE user_requests ENABLE ROW LEVEL SECURITY;
  ALTER TABLE oauth_configs ENABLE ROW LEVEL SECURITY;
  ALTER TABLE tags ENABLE ROW LEVEL SECURITY;
  ALTER TABLE product_tags ENABLE ROW LEVEL SECURITY;
  ALTER TABLE product_urls ENABLE ROW LEVEL SECURITY;
  ALTER TABLE product_editors ENABLE ROW LEVEL SECURITY;
  ALTER TABLE scraper_search_terms ENABLE ROW LEVEL SECURITY;
  ALTER TABLE supported_sources ENABLE ROW LEVEL SECURITY;
  ALTER TABLE valid_categories ENABLE ROW LEVEL SECURITY;

  -- Users: Everyone can read, users can update their own profile
  CREATE POLICY "Users are viewable by everyone" 
    ON users FOR SELECT 
    USING (true);

  CREATE POLICY "Users can update own profile" 
    ON users FOR UPDATE 
    USING (auth.uid() = id);

  -- Products: Everyone can read, authenticated users can create, owners/admins can update
  CREATE POLICY "Products are viewable by everyone" 
    ON products FOR SELECT 
    USING (true);

  CREATE POLICY "Authenticated users can create products" 
    ON products FOR INSERT 
    WITH CHECK (auth.role() = 'authenticated');

  CREATE POLICY "Users can update own products or admins can update all" 
    ON products FOR UPDATE 
    USING (
      auth.uid() = created_by OR 
      auth.uid() = ANY(editor_ids) OR
      EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator'))
    );

  CREATE POLICY "Admins can delete products" 
    ON products FOR DELETE 
    USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin'));

  -- Ratings: Everyone can read, authenticated users can create/update/delete their own
  CREATE POLICY "Ratings are viewable by everyone" 
    ON ratings FOR SELECT 
    USING (true);

  CREATE POLICY "Authenticated users can create ratings" 
    ON ratings FOR INSERT 
    WITH CHECK (auth.uid() = user_id);

  CREATE POLICY "Users can update own ratings" 
    ON ratings FOR UPDATE 
    USING (auth.uid() = user_id);

  CREATE POLICY "Users can delete own ratings" 
    ON ratings FOR DELETE 
    USING (auth.uid() = user_id);

  -- Discussions: Everyone can read, authenticated users can create, authors can update/delete
  CREATE POLICY "Discussions are viewable by everyone" 
    ON discussions FOR SELECT 
    USING (true);

  CREATE POLICY "Authenticated users can create discussions" 
    ON discussions FOR INSERT 
    WITH CHECK (auth.uid() = user_id);

  CREATE POLICY "Users can update own discussions or admins/mods can moderate" 
    ON discussions FOR UPDATE 
    USING (
      auth.uid() = user_id OR 
      EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator'))
    );

  CREATE POLICY "Users can delete own discussions or admins/mods can delete any" 
    ON discussions FOR DELETE 
    USING (
      auth.uid() = user_id OR 
      EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator'))
    );

  -- Blog Posts: Everyone can read published posts, admins can manage all
  CREATE POLICY "Published blog posts are viewable by everyone" 
    ON blog_posts FOR SELECT 
    USING (published = true OR auth.uid() = author_id OR auth.uid() = ANY(author_ids));

  CREATE POLICY "Admins can create blog posts" 
    ON blog_posts FOR INSERT 
    WITH CHECK (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator')));

  CREATE POLICY "Authors and admins can update blog posts" 
    ON blog_posts FOR UPDATE 
    USING (
      auth.uid() = author_id OR 
      auth.uid() = ANY(author_ids) OR
      EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

  CREATE POLICY "Admins can delete blog posts" 
    ON blog_posts FOR DELETE 
    USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin'));

  -- Collections: Public collections viewable by all, users manage their own
  CREATE POLICY "Public collections are viewable by everyone" 
    ON collections FOR SELECT 
    USING (is_public = true OR auth.uid() = user_id);

  CREATE POLICY "Authenticated users can create collections" 
    ON collections FOR INSERT 
    WITH CHECK (auth.uid() = user_id);

  CREATE POLICY "Users can update own collections" 
    ON collections FOR UPDATE 
    USING (auth.uid() = user_id);

  CREATE POLICY "Users can delete own collections" 
    ON collections FOR DELETE 
    USING (auth.uid() = user_id);

  -- User Activities: Users can read their own, admins can read all
  CREATE POLICY "Users can view own activities" 
    ON user_activities FOR SELECT 
    USING (
      auth.uid() = user_id OR 
      EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator'))
    );

  CREATE POLICY "System can create user activities" 
    ON user_activities FOR INSERT 
    WITH CHECK (true);

  -- Scraping Logs: Admins only
  CREATE POLICY "Admins can view scraping logs" 
    ON scraping_logs FOR SELECT 
    USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator')));

  CREATE POLICY "System can create scraping logs" 
    ON scraping_logs FOR INSERT 
    WITH CHECK (true);

  -- User Requests: Users can view their own, admins can view all
  CREATE POLICY "Users can view own requests and admins can view all" 
    ON user_requests FOR SELECT 
    USING (
      auth.uid() = user_id OR 
      EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator'))
    );

  CREATE POLICY "Authenticated users can create requests" 
    ON user_requests FOR INSERT 
    WITH CHECK (auth.uid() = user_id);

  CREATE POLICY "Admins can update user requests" 
    ON user_requests FOR UPDATE 
    USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator')));

  -- Product Managers
  CREATE POLICY "Product managers are viewable by everyone"
    ON product_editors FOR SELECT
    USING (true);

  CREATE POLICY "Admins can manage product managers"
    ON product_editors FOR ALL
    USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator')))
    WITH CHECK (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator')));

  -- Product URLs: readable by all; owners can manage
  CREATE POLICY "Product URLs are viewable by everyone"
    ON product_urls FOR SELECT
    USING (true);

  CREATE POLICY "Authenticated users can create product URLs"
    ON product_urls FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

  CREATE POLICY "Creators can update their product URLs"
    ON product_urls FOR UPDATE
    USING (auth.uid() = created_by)
    WITH CHECK (auth.uid() = created_by);

  CREATE POLICY "Creators can delete their product URLs"
    ON product_urls FOR DELETE
    USING (auth.uid() = created_by);

  -- OAuth Configs
  CREATE POLICY "Admins can view oauth configs" 
    ON oauth_configs FOR SELECT 
    USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator')));

  -- Scraper Search Terms: authenticated users can read, admins can manage
  CREATE POLICY "Authenticated users can view scraper search terms"
    ON scraper_search_terms FOR SELECT
    USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');

  CREATE POLICY "Admins can manage scraper search terms"
    ON scraper_search_terms FOR ALL
    USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator')))
    WITH CHECK (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role IN ('admin', 'moderator')));

  -- Product Tags: Everyone can read, authenticated users can create, admins can delete
  CREATE POLICY "Product tags are viewable by everyone"
    ON product_tags FOR SELECT
    USING (true);

  CREATE POLICY "Authenticated users can create product tags"
    ON product_tags FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

  CREATE POLICY "Admins can delete product tags"
    ON product_tags FOR DELETE
    USING (EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin'));

  -- ============================================================================
  -- STORAGE BUCKETS FOR FILE UPLOADS
  -- ============================================================================

  -- Create storage bucket for product images
  INSERT INTO storage.buckets (id, name, public) 
  VALUES ('product-images', 'product-images', true)
  ON CONFLICT (id) DO NOTHING;

  -- Storage policies for product images
  CREATE POLICY "Product images are publicly accessible" 
    ON storage.objects FOR SELECT 
    USING (bucket_id = 'product-images');

  CREATE POLICY "Authenticated users can upload product images" 
    ON storage.objects FOR INSERT 
    WITH CHECK (bucket_id = 'product-images' AND auth.role() = 'authenticated');

  CREATE POLICY "Users can update their own images" 
    ON storage.objects FOR UPDATE 
    USING (bucket_id = 'product-images' AND auth.role() = 'authenticated');

  CREATE POLICY "Users can delete their own images" 
    ON storage.objects FOR DELETE 
    USING (bucket_id = 'product-images' AND auth.role() = 'authenticated');

  -- ============================================================================
  -- HELPER FUNCTIONS
  -- ============================================================================


  -- Function to update updated_at timestamp automatically
  CREATE OR REPLACE FUNCTION update_updated_at_column()
  RETURNS TRIGGER AS $$
  BEGIN
      NEW.updated_at = NOW();
      RETURN NEW;
  END;
  $$ language 'plpgsql';

  -- Apply the trigger to tables with updated_at column
  CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  CREATE TRIGGER update_ratings_updated_at BEFORE UPDATE ON ratings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  CREATE TRIGGER update_discussions_updated_at BEFORE UPDATE ON discussions
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  CREATE TRIGGER update_blog_posts_updated_at BEFORE UPDATE ON blog_posts
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  CREATE TRIGGER update_collections_updated_at BEFORE UPDATE ON collections
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  CREATE TRIGGER update_oauth_configs_updated_at BEFORE UPDATE ON oauth_configs
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  -- Ensure product_urls updated_at is maintained
  CREATE TRIGGER update_product_urls_updated_at BEFORE UPDATE ON product_urls
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  CREATE TRIGGER update_user_requests_updated_at BEFORE UPDATE ON user_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

  CREATE TRIGGER update_scraper_search_terms_updated_at BEFORE UPDATE ON scraper_search_terms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
