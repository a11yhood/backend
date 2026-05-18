#!/usr/bin/env python3
"""
Flexible seed runner with options for different scenarios.

Usage:
    # Run all development seeds (default)
    python run_seeds.py

    # Run specific seeds
    python run_seeds.py --include supported_sources,oauth_configs

    # Skip certain seeds
    python run_seeds.py --exclude test_product,test_collections

    # List available seeds
    python run_seeds.py --list
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Ensure project root and seed_scripts are on sys.path for imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SEED_DIR = os.path.abspath(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if SEED_DIR not in sys.path:
    sys.path.insert(0, SEED_DIR)

# Load environment variables
env_file = os.getenv("ENV_FILE", ".env.test")
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    logger.warning(f"Environment file {env_file} not found, using defaults")

# Available seed scripts
SEED_SCRIPTS = {
    "supported_sources": ("seed_supported_sources", "seed_supported_sources"),
    "oauth_configs": ("seed_oauth_configs", "seed_oauth_configs"),
    "scraper_search_terms": ("seed_scraper_search_terms", "main"),
    "test_users": ("seed_test_users", "seed_users"),
    "test_product": ("seed_test_product", "seed_product"),
    "test_image": ("seed_test_image", "seed_image"),
    "test_collections": ("seed_test_collections", "seed_collections"),
}

# Default seeds for development
DEFAULT_SEEDS = [
    "supported_sources",
    "oauth_configs",
    "scraper_search_terms",
    "test_users",
    "test_product",
    "test_image",
    "test_collections",
]


def run_seed(script_name: str, module_name: str, function_name: str = "main") -> bool:
    """Run a seed script and return success status."""
    try:
        logger.info(f"Running {script_name}...")

        # Import module and call the specified function
        module = __import__(module_name)
        if hasattr(module, function_name):
            getattr(module, function_name)()
        else:
            logger.error(f"  Function {function_name} not found in {module_name}")
            return False

        logger.info(f"✓ {script_name} completed successfully")
        return True
    except Exception as e:
        logger.error(f"✗ {script_name} failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Flexible seed runner for a11yhood database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all development seeds
  python run_seeds.py

  # Run only specific seeds
  python run_seeds.py --include supported_sources,oauth_configs

  # Run all except test data
  python run_seeds.py --exclude test_product,test_collections

  # List available seeds
  python run_seeds.py --list
        """,
    )

    parser.add_argument("--list", action="store_true", help="List available seed scripts")

    parser.add_argument(
        "--include",
        type=str,
        help="Comma-separated list of seeds to include (e.g., supported_sources,oauth_configs)",
    )

    parser.add_argument(
        "--exclude", type=str, help="Comma-separated list of seeds to exclude from default set"
    )

    parser.add_argument(
        "--no-summary", action="store_true", help="Skip printing summary at the end"
    )

    args = parser.parse_args()

    # List available seeds
    if args.list:
        print("\nAvailable seed scripts:")
        print("=" * 60)
        for name in sorted(SEED_SCRIPTS.keys()):
            print(f"  • {name}")
        print("=" * 60)
        print("\nDefault seeds (run when no options specified):")
        for name in DEFAULT_SEEDS:
            print(f"  • {name}")
        return 0

    # Determine which seeds to run
    seeds_to_run = []

    if args.include:
        # Use only specified seeds
        requested = [s.strip() for s in args.include.split(",")]
        for seed_name in requested:
            if seed_name in SEED_SCRIPTS:
                seeds_to_run.append(seed_name)
            else:
                logger.warning(f"Unknown seed: {seed_name}")
    else:
        # Use default seeds, excluding any specified
        seeds_to_run = DEFAULT_SEEDS.copy()

        if args.exclude:
            excluded = {s.strip() for s in args.exclude.split(",")}
            seeds_to_run = [s for s in seeds_to_run if s not in excluded]

    if not seeds_to_run:
        logger.error("No seeds to run. Use --list to see available options.")
        return 1

    # Run the selected seeds
    logger.info("=" * 60)
    logger.info("Starting database seeding process...")
    logger.info("=" * 60)

    results = {}
    for seed_name in seeds_to_run:
        if seed_name in SEED_SCRIPTS:
            module_name, function_name = SEED_SCRIPTS[seed_name]
            results[seed_name] = run_seed(seed_name, module_name, function_name)

    # Print summary
    if not args.no_summary:
        logger.info("=" * 60)
        logger.info("Seeding Summary:")
        logger.info("=" * 60)

        passed = sum(1 for v in results.values() if v)
        total = len(results)

        for script_name, success in results.items():
            status = "✓ PASSED" if success else "✗ FAILED"
            logger.info(f"{status}: {script_name}")

        logger.info("=" * 60)
        logger.info(f"Results: {passed}/{total} seed scripts completed successfully")
        logger.info("=" * 60)

        return 0 if passed == total else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
