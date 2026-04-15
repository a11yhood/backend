#!/usr/bin/env python3
"""
Unified scraper script for running scrapers on the backend
Usage: python scraper.py <platform> [--mode {test|full}]

Examples:
  python scraper.py github --mode test      # Test mode (5 products)
  python scraper.py github --mode full      # Full scrape
  python scraper.py ravelry --mode test
  python scraper.py thingiverse --mode test

Requires environment variables:
  SUPABASE_URL: Supabase project URL
  SUPABASE_KEY: Supabase service role key
"""

import argparse
import asyncio
import os
import sys

from supabase import create_client


async def main():
    parser = argparse.ArgumentParser(description="Run scrapers on the backend")
    parser.add_argument(
        "platform", choices=["github", "ravelry", "thingiverse"], help="Which platform to scrape"
    )
    parser.add_argument(
        "--mode",
        choices=["test", "full"],
        default="test",
        help="Test mode (5 products) or full scrape (default: test)",
    )

    args = parser.parse_args()
    platform = args.platform
    test_mode = args.mode == "test"
    test_limit = 5

    # Get Supabase credentials from environment
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print("❌ ERROR: SUPABASE_URL and SUPABASE_KEY environment variables are required")
        print("Set them in your .env file or shell environment")
        sys.exit(1)

    # Create Supabase client
    supabase = create_client(supabase_url, supabase_key)

    # Load appropriate scraper based on platform
    if platform == "github":
        from scrapers.github import GitHubScraper

        # Get GitHub token from oauth_configs or environment
        token: str | None = None
        try:
            config_response = (
                supabase.table("oauth_configs")
                .select("access_token")
                .eq("platform", "github")
                .execute()
            )
            token = (
                (config_response.data or [{}])[0].get("access_token")
                if config_response.data
                else None
            )
        except Exception:
            pass

        if not token:
            token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_ACCESS_TOKEN")

        if token:
            print(f"✓ Using GitHub token: {token[:20]}...")
        else:
            print("⚠️  No GitHub token configured (will be rate-limited to 60 requests/hour)")

        scraper = GitHubScraper(supabase, access_token=token)

    elif platform == "ravelry":
        from scrapers.ravelry import RavelryScraper

        # Get Ravelry token from oauth_configs
        try:
            config_response = (
                supabase.table("oauth_configs")
                .select("access_token")
                .eq("platform", "ravelry")
                .execute()
            )
            token = (
                (config_response.data or [{}])[0].get("access_token")
                if config_response.data
                else None
            )
        except Exception as e:
            print(f"❌ ERROR: Failed to load Ravelry token: {e}")
            sys.exit(1)

        if not token:
            print("❌ ERROR: No Ravelry OAuth token found in oauth_configs table")
            print("Please configure Ravelry OAuth in the admin panel first")
            sys.exit(1)

        print(f"✓ Using Ravelry token: {token[:20]}...")
        scraper = RavelryScraper(supabase, token)

    elif platform == "thingiverse":
        from scrapers.thingiverse import ThingiverseScraper

        # Get Thingiverse token from oauth_configs
        try:
            config_response = (
                supabase.table("oauth_configs")
                .select("access_token")
                .eq("platform", "thingiverse")
                .execute()
            )
            token = (
                (config_response.data or [{}])[0].get("access_token")
                if config_response.data
                else None
            )
        except Exception as e:
            print(f"❌ ERROR: Failed to load Thingiverse token: {e}")
            sys.exit(1)

        if not token:
            print("❌ ERROR: No Thingiverse OAuth token found in oauth_configs table")
            print("Please configure Thingiverse OAuth in the admin panel first")
            sys.exit(1)

        print(f"✓ Using Thingiverse token: {token[:20]}...")
        scraper = ThingiverseScraper(supabase, token)

    # Run scraper
    try:
        mode_str = "test (5 products)" if test_mode else "full"
        print(f"\nStarting {platform} scraper ({mode_str})...")
        print("-" * 60)

        result = await scraper.scrape(test_mode=test_mode, test_limit=test_limit)

        print("\n=== Scraping Results ===")
        print(f"Source:           {result['source']}")
        print(f"Products found:   {result['products_found']}")
        print(f"Products added:   {result['products_added']}")
        print(f"Products updated: {result['products_updated']}")
        print(f"Duration:         {result['duration_seconds']:.2f}s")
        print(f"Status:           {result.get('status', 'success')}")

        if result.get("error_message"):
            print(f"Error:            {result['error_message']}")

        # Check database
        print("\n=== Database Check ===")
        products = supabase.table("products").select("id").eq("source", platform).execute()
        total_count = len(products.data)
        print(f"Total {platform} products in database: {total_count}")

        # Show sample products
        if total_count > 0:
            sample_products = (
                supabase.table("products")
                .select("name, url")
                .eq("source", platform)
                .limit(3)
                .execute()
            )
            if sample_products.data:
                print("\nSample products:")
                for p in sample_products.data:
                    print(f"  - {p['name']}: {p['url']}")

        print("\n✅ Scraping completed successfully!")
        return 0

    except Exception as e:
        print(f"\n❌ ERROR during scraping: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        await scraper.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
