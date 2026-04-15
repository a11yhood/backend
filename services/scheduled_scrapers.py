"""
Scheduled scraper service - runs scrapers on a schedule
"""

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scrapers import ScraperUtilities
from services.scrapers import ScraperService
from supabase import Client

logger = logging.getLogger(__name__)


class ScheduledScraperService:
    """Manages scheduled scraping tasks"""

    def __init__(self):
        self.scheduler: AsyncIOScheduler | None = None

    def initialize(self, supabase_client: Client):
        """Initialize the scheduler with configured jobs

        Args:
            supabase_client: Supabase client for scraping operations
        """
        if self.scheduler is not None:
            logger.warning("Scheduler already initialized")
            return

        self.scheduler = AsyncIOScheduler()
        self.supabase = supabase_client

        # Schedule daily scraping at 2 AM UTC
        # Customize these times as needed
        self.scheduler.add_job(
            self._run_github_scrape,
            CronTrigger(hour=2, minute=0, timezone="UTC"),
            id="github_daily",
            name="Daily GitHub scraping at 2 AM UTC",
            replace_existing=True,
            misfire_grace_time=600,  # Allow 10 minutes grace period
        )

        self.scheduler.add_job(
            self._run_thingiverse_scrape,
            CronTrigger(hour=2, minute=30, timezone="UTC"),
            id="thingiverse_daily",
            name="Daily Thingiverse scraping at 2:30 AM UTC",
            replace_existing=True,
            misfire_grace_time=600,
        )

        self.scheduler.add_job(
            self._run_ravelry_scrape,
            CronTrigger(hour=3, minute=0, timezone="UTC"),
            id="ravelry_daily",
            name="Daily Ravelry scraping at 3 AM UTC",
            replace_existing=True,
            misfire_grace_time=600,
        )

        logger.info("Scheduled scraper service initialized:")
        logger.info("  - GitHub: Daily at 2:00 AM UTC")
        logger.info("  - Thingiverse: Daily at 2:30 AM UTC")
        logger.info("  - Ravelry: Daily at 3:00 AM UTC")

    async def _run_github_scrape(self):
        """Run GitHub scraper"""
        await self._run_scraper("github")

    async def _run_thingiverse_scrape(self):
        """Run Thingiverse scraper"""
        await self._run_scraper("thingiverse")

    async def _run_ravelry_scrape(self):
        """Run Ravelry scraper"""
        await self._run_scraper("ravelry")

    async def _run_scraper(self, platform: str):
        """Run a scraper and log results

        Args:
            platform: Platform name (github, thingiverse, or ravelry)
        """
        try:
            logger.info(
                f"[{platform}] Starting scheduled scrape at {datetime.now(UTC).isoformat()}..."
            )

            scraper_service = ScraperService(self.supabase)

            # Run the appropriate scraper
            if platform == "github":
                result = await scraper_service.scrape_github()
            elif platform == "thingiverse":
                # Get token from oauth_configs if available
                token = None
                try:
                    config_response = (
                        self.supabase.table("oauth_configs")
                        .select("access_token")
                        .eq("platform", "thingiverse")
                        .execute()
                    )
                    token = (
                        (config_response.data or [{}])[0].get("access_token")
                        if config_response.data
                        else None
                    )
                except Exception:
                    pass
                result = await scraper_service.scrape_thingiverse(access_token=token)
            elif platform == "ravelry":
                # Get token from oauth_configs if available
                token = None
                try:
                    config_response = (
                        self.supabase.table("oauth_configs")
                        .select("access_token")
                        .eq("platform", "ravelry")
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
                    logger.warning(f"[{platform}] No OAuth token configured, skipping")
                    return

                result = await scraper_service.scrape_ravelry(access_token=token)
            else:
                logger.error(f"Unknown platform: {platform}")
                return

            # Log results
            logger.info(
                f"[{platform}] Scheduled scrape completed: "
                f"found={result['products_found']}, "
                f"added={result['products_added']}, "
                f"updated={result['products_updated']}, "
                f"duration={result['duration_seconds']:.2f}s"
            )

            # Record in scraping logs via ScraperUtilities
            try:
                ScraperUtilities.set_last_scrape_time(
                    self.supabase,
                    platform,
                    result,
                    user_id="scheduled",  # Mark as scheduled job, not user-triggered
                )
            except Exception as e:
                logger.warning(f"[{platform}] Failed to record scraping log: {e}")

        except Exception as e:
            logger.error(f"[{platform}] Scheduled scrape failed: {e}", exc_info=True)

            # Log the error
            try:
                error_result = {
                    "source": platform,
                    "products_found": 0,
                    "products_added": 0,
                    "products_updated": 0,
                    "duration_seconds": 0,
                    "status": "error",
                    "error_message": str(e),
                }
                ScraperUtilities.set_last_scrape_time(
                    self.supabase, platform, error_result, user_id="scheduled"
                )
            except Exception as log_error:
                logger.error(f"[{platform}] Failed to log error: {log_error}")

    def start(self):
        """Start the scheduler"""
        if self.scheduler is None:
            logger.error("Scheduler not initialized")
            return

        if self.scheduler.running:
            logger.warning("Scheduler already running")
            return

        self.scheduler.start()
        logger.info("Scheduled scraper service started")

    def stop(self):
        """Stop the scheduler"""
        if self.scheduler is None:
            return

        if not self.scheduler.running:
            logger.warning("Scheduler not running")
            return

        self.scheduler.shutdown()
        logger.info("Scheduled scraper service stopped")

    async def get_jobs(self) -> list:
        """Get list of scheduled jobs"""
        if self.scheduler is None:
            return []

        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in self.scheduler.get_jobs()
        ]


# Global instance
_scheduled_scraper_service: ScheduledScraperService | None = None


def get_scheduled_scraper_service() -> ScheduledScraperService:
    """Get or create the global scheduled scraper service"""
    global _scheduled_scraper_service
    if _scheduled_scraper_service is None:
        _scheduled_scraper_service = ScheduledScraperService()
    return _scheduled_scraper_service
