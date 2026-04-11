from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Body
from typing import Optional
from supabase import Client
import httpx
import logging
from datetime import datetime, UTC

from models.scrapers import (
    ScrapingLogResponse,
    ScraperTriggerRequest,
    OAuthConfigCreate,
    OAuthConfigUpdate,
    OAuthConfigResponse,
)
from pydantic import BaseModel
from services.database import get_db
from services.auth import get_current_user
from services.scrapers import ScraperService, ScraperOAuth
from services.sources import extract_domain, find_source_for_domain
from services.id_generator import normalize_to_snake_case
from scrapers import ScraperUtilities
from scrapers.github import GitHubScraper
from scrapers.ravelry import RavelryScraper
from scrapers.thingiverse import ThingiverseScraper
from scrapers.goat import GOATScraper
from scrapers.goat import GOATScraper
from routers.products import get_product_tag_rows, get_tags_map, set_product_tags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scrapers", tags=["scrapers"])


class LoadUrlRequest(BaseModel):
    """Request model for load-url endpoint"""
    url: str


async def _run_scraper_and_log(
    scraper_service: ScraperService,
    source: str,
    user_id: str,
    database: Client,
    access_token: Optional[str] = None,
    test_mode: bool = False,
    test_limit: int = 5,
):
    """Run a scraper and save the log to the database"""
    try:
        if source == "thingiverse":
            result = await scraper_service.scrape_thingiverse(
                access_token=access_token,
                test_mode=test_mode,
                test_limit=test_limit
            )
        elif source == "ravelry":
            result = await scraper_service.scrape_ravelry(
                access_token=access_token,
                test_mode=test_mode,
                test_limit=test_limit
            )
        elif source == "github":
            result = await scraper_service.scrape_github(
                test_mode=test_mode,
                test_limit=test_limit
            )
        elif source == "goat":
            result = await scraper_service.scrape_goat(
                access_token=access_token,
                test_mode=test_mode,
                test_limit=test_limit
            )
        else:
            result = {
                'source': source,
                'status': 'error',
                'error_message': f'Unknown source: {source}',
                'products_found': 0,
                'products_added': 0,
                'products_updated': 0,
                'duration_seconds': 0,
            }

        ScraperUtilities.set_last_scrape_time(database, result['source'], result, user_id=user_id)

    except Exception as e:
        error_result = {
            'source': source,
            'products_found': 0,
            'products_added': 0,
            'products_updated': 0,
            'duration_seconds': 0,
            'status': 'error',
            'error_message': str(e),
        }
        ScraperUtilities.set_last_scrape_time(database, source, error_result, user_id=user_id)


@router.post("/trigger", response_model=dict)
async def trigger_scraper(
    request: ScraperTriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """
    Trigger a scraping job (admin only)
    Runs in background to avoid blocking
    """
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    scraper_service = ScraperService(db)
    
    # Get OAuth token from database
    access_token = None
    if request.source.value in ["thingiverse", "ravelry", "github", "goat"]:
        config_response = db.table("oauth_configs").select("access_token").eq("platform", request.source.value).execute()
        
        if request.source.value in ["thingiverse", "ravelry", "goat"]:
            if not config_response.data:
                raise HTTPException(
                    status_code=400,
                    detail=f"OAuth not configured for {request.source.value}. Please authorize in admin settings."
                )
            
            access_token = config_response.data[0].get("access_token")
            if not access_token:
                raise HTTPException(
                    status_code=400,
                    detail=f"No access token found for {request.source.value}. Please authorize in admin settings."
                )
        else:
            # GitHub token is optional (scraper can run unauthenticated but is rate limited)
            if config_response.data:
                access_token = config_response.data[0].get("access_token") or None
    
    # Start scraping in background
    background_tasks.add_task(
        _run_scraper_and_log,
        scraper_service=scraper_service,
        source=request.source.value,
        user_id=current_user["id"],
        database=db,
        access_token=access_token,
        test_mode=request.test_mode,
        test_limit=request.test_limit,
    )
    
    return {
        "message": f"Scraping started for {request.source.value}",
        "test_mode": request.test_mode,
        "test_limit": request.test_limit if request.test_mode else None,
    }


@router.post("/load-url")
async def load_url(
    request: LoadUrlRequest,
    db = Depends(get_db),
) -> dict:
    """
    Check if a product with this URL exists in the database.
    If it exists, return it.
    If it doesn't exist, scrape it, save it to the database, and return it.
    No auth required - used by public submission form.
    Validates URL against supported sources before processing.
    """
    url = request.url
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    url = url.strip()

    # If no scheme provided, default to https:// for scraper compatibility
    if "://" not in url:
        url = f"https://{url}"
    
    # Validate URL against supported sources
    domain = extract_domain(url)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid URL format")
    
    # Get supported sources from database
    try:
        supported_sources_response = db.table("supported_sources").select("domain, name").execute()
        supported_sources = supported_sources_response.data if supported_sources_response.data else []
    except Exception as e:
        # If supported_sources table doesn't exist or query fails, block to avoid silent bypass
        print(f"Warning: Could not query supported_sources table: {e}")
        raise HTTPException(
            status_code=400,
            detail="Supported sources configuration is unavailable; cannot process URL."
        )
    
    # Check if domain is supported (block when no sources configured)
    if not supported_sources:
        raise HTTPException(
            status_code=400,
            detail="No supported sources are configured yet."
        )

    determined_source = find_source_for_domain(domain, supported_sources)
    if not determined_source:
        raise HTTPException(
            status_code=400,
            detail=f"URL domain is not supported. Supported domains are: {', '.join([s['domain'] for s in supported_sources])}"
        )
    
    def is_image_url(value: Optional[str]) -> bool:
        if not value:
            return False
        v = value.lower()
        return v.endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"))

    # First, check if product already exists in database
    existing = db.table("products").select("*").eq("url", url).limit(1).execute()
    if existing.data:
        product = existing.data[0]
        # Normalize fields for API response
        product["image_url"] = product.get("image")
        product["external_id"] = product.get("external_id")
        product["sourceUrl"] = product.get("url")
        
        # Attach tags
        pt_rows = get_product_tag_rows(db, [product["id"]])
        tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
        tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
        product["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]
        
        # Get owner IDs
        editors_response = db.table("product_editors").select("user_id").eq("product_id", product["id"]).execute()
        product["ownerIds"] = [editor["user_id"] for editor in editors_response.data] if editors_response.data else []
        
        # If the stored image is missing or not an image, attempt a light re-scrape to refresh media
        if not is_image_url(product.get("image_url")):
            refreshed = None
            try:
                # Try GitHub
                github_token = None
                try:
                    config_response = db.table("oauth_configs").select("access_token").eq("platform", "github").execute()
                    github_token = (config_response.data or [{}])[0].get("access_token") if config_response.data else None
                except Exception:
                    github_token = None
                github_scraper = GitHubScraper(db, access_token=github_token)
                if github_scraper.supports_url(url):
                    refreshed = await github_scraper.scrape_url(url)
            except Exception as e:
                print(f"GitHub scraper refresh error: {e}")

            if not refreshed:
                try:
                    config_response = db.table("oauth_configs").select("access_token").eq("platform", "ravelry").execute()
                    access_token = config_response.data[0].get("access_token") if config_response.data else None
                    ravelry_scraper = RavelryScraper(db, access_token)
                    if ravelry_scraper.supports_url(url):
                        refreshed = await ravelry_scraper.scrape_url(url)
                except Exception as e:
                    print(f"Ravelry scraper refresh error: {e}")

            if not refreshed:
                try:
                    config_response = db.table("oauth_configs").select("access_token").eq("platform", "thingiverse").execute()
                    access_token = config_response.data[0].get("access_token") if config_response.data else None
                    thingiverse_scraper = ThingiverseScraper(db, access_token)
                    if thingiverse_scraper.supports_url(url):
                        refreshed = await thingiverse_scraper.scrape_url(url)
                except Exception as e:
                    print(f"Thingiverse scraper refresh error: {e}")

            if not refreshed:
                try:
                    config_response = db.table("oauth_configs").select("access_token").eq("platform", "goat").execute()
                    access_token = config_response.data[0].get("access_token") if config_response.data else None
                    librarything_scraper = GOATScraper(db, access_token)
                    if librarything_scraper.supports_url(url):
                        refreshed = await librarything_scraper.scrape_url(url)
                except Exception as e:
                    print(f"GOAT scraper refresh error: {e}")

            if refreshed and is_image_url(refreshed.get("image") or refreshed.get("imageUrl") or refreshed.get("image_url")):
                new_image = refreshed.get("image") or refreshed.get("imageUrl") or refreshed.get("image_url")
                db.table("products").update({"image": new_image}).eq("id", product["id"]).execute()
                product["image_url"] = new_image

        return {"success": True, "product": product, "source": "database"}
    
    # Product doesn't exist - try to scrape it
    scraped_data = None
    scraper_name = None
    
    # Try each scraper to see if it supports this URL
    try:
        # Try GitHub
        github_token = None
        try:
            config_response = db.table("oauth_configs").select("access_token").eq("platform", "github").execute()
            github_token = (config_response.data or [{}])[0].get("access_token") if config_response.data else None
        except Exception:
            github_token = None
        github_scraper = GitHubScraper(db, access_token=github_token)
        if github_scraper.supports_url(url):
            scraped_data = await github_scraper.scrape_url(url)
            scraper_name = "github"
    except Exception as e:
        # Log but continue to next scraper
        print(f"GitHub scraper error: {e}")
    
    if not scraped_data:
        try:
            # Try Ravelry
            config_response = db.table("oauth_configs").select("access_token").eq("platform", "ravelry").execute()
            access_token = config_response.data[0].get("access_token") if config_response.data else None
            ravelry_scraper = RavelryScraper(db, access_token)
            if ravelry_scraper.supports_url(url):
                scraped_data = await ravelry_scraper.scrape_url(url)
                scraper_name = "ravelry"
        except Exception as e:
            # Log but continue to next scraper
            print(f"Ravelry scraper error: {e}")
    
    if not scraped_data:
        try:
            # Try Thingiverse
            config_response = db.table("oauth_configs").select("access_token").eq("platform", "thingiverse").execute()
            access_token = config_response.data[0].get("access_token") if config_response.data else None
            thingiverse_scraper = ThingiverseScraper(db, access_token)
            if thingiverse_scraper.supports_url(url):
                scraped_data = await thingiverse_scraper.scrape_url(url)
                scraper_name = "thingiverse"
        except Exception as e:
            # Log but continue
            print(f"Thingiverse scraper error: {e}")
    
    if not scraped_data:
        try:
            # Try GOAT (LibraryThing)
            config_response = db.table("oauth_configs").select("access_token").eq("platform", "goat").execute()
            access_token = config_response.data[0].get("access_token") if config_response.data else None
            librarything_scraper = GOATScraper(db, access_token)
            if librarything_scraper.supports_url(url):
                scraped_data = await librarything_scraper.scrape_url(url)
                scraper_name = "librarything"
        except Exception as e:
            # Log but continue
            print(f"GOAT scraper error: {e}")
    
    if not scraped_data:
        return {"success": False, "message": "URL not supported by any scraper or scraping failed"}
    
    # Save scraped product to database
    db_data = {
        "name": scraped_data.get("name"),
        "description": scraped_data.get("description"),
        "url": url,
        "image": scraped_data.get("image") or scraped_data.get("imageUrl") or scraped_data.get("image_url"),
        "source": scraped_data.get("source", scraper_name),
        "type": scraped_data.get("type", "Other"),
        "external_id": scraped_data.get("external_id"),
        # No created_by since this is a public scrape
    }
    
    # Remove None values
    db_insert = {k: v for k, v in db_data.items() if v is not None}
    # Ensure slug exists for Supabase; SQLite adapter also handles slugs but this keeps parity
    if "slug" not in db_insert or not db_insert.get("slug"):
        base = db_insert.get("name") or db_insert.get("url") or "product"
        db_insert["slug"] = normalize_to_snake_case(base) or "product"

    response = db.table("products").insert(db_insert).execute()
    
    if not response.data:
        return {"success": False, "message": "Failed to save scraped product to database"}
    
    # Get the saved product
    saved_product = response.data[0]
    saved_product["image_url"] = saved_product.get("image")
    saved_product["external_id"] = saved_product.get("external_id")
    saved_product["sourceUrl"] = saved_product.get("url")
    
    # Create tag relationships if provided
    if scraped_data.get("tags"):
        set_product_tags(db, saved_product["id"], scraped_data["tags"])
    
    # Attach tags for response
    pt_rows = get_product_tag_rows(db, [saved_product["id"]])
    tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
    tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
    saved_product["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]
    
    # No owners since this is a public scrape
    saved_product["ownerIds"] = []
    
    return {"success": True, "product": saved_product, "source": "scraped"}



@router.get("/logs", response_model=list[ScrapingLogResponse])
async def get_scraping_logs(
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
    db = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get scraping logs (authenticated users)"""
    query = db.table("scraping_logs").select("*")
    
    if source:
        query = query.eq("source", source)
    
    query = query.range(offset, offset + limit - 1).order("created_at", desc=True)
    
    response = query.execute()
    return response.data


@router.post("/oauth/{platform}/callback")
async def oauth_callback(
    platform: str,
    code: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """
    Handle OAuth callback for scraper platforms
    Exchanges code for access token and stores it.
    The redirect_uri used here must match what is stored in oauth_configs,
    which must be the URI registered with the OAuth provider.
    """
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get OAuth config for this platform
    config_response = db.table("oauth_configs").select("*").eq("platform", platform).execute()
    
    if not config_response.data:
        raise HTTPException(status_code=404, detail=f"OAuth config not found for {platform}")
    
    config = config_response.data[0]

    try:
        if platform == "ravelry":
            token_data = await ScraperOAuth.get_ravelry_token(
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                code=code,
                redirect_uri=config["redirect_uri"],
            )
        elif platform == "thingiverse":
            token_data = await ScraperOAuth.get_thingiverse_token(
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                code=code,
                redirect_uri=config["redirect_uri"],
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

        if not token_data.get("access_token"):
            logger.error("OAuth token exchange returned no access_token for %s", platform)
            raise HTTPException(status_code=502, detail=f"OAuth token exchange returned no access token for {platform}")

        # Store tokens securely (TODO: encrypt tokens)
        update_data = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_expires_at": token_data.get("expires_at"),
        }

        db.table("oauth_configs").update(update_data).eq("id", config["id"]).execute()

        return {"message": f"OAuth token saved for {platform}"}

    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        response_text = exc.response.text if exc.response is not None else str(exc)
        logger.error(
            "OAuth token exchange failed for %s with status %s: %s",
            platform,
            exc.response.status_code if exc.response is not None else "unknown",
            response_text,
        )
        raise HTTPException(status_code=400, detail=f"OAuth token exchange failed for {platform}: {response_text}")
    except Exception as exc:
        logger.error("Failed to persist OAuth token for %s", platform, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save OAuth token for {platform}: {str(exc)}")


@router.post("/oauth/{platform}/save-token")
async def save_oauth_token(
    platform: str,
    token_data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Save OAuth token from frontend (admin only)"""
    logger.info(f"save_oauth_token called with platform={platform}, token_data keys={list(token_data.keys())}")
    
    if not current_user.get("role") == "admin":
        logger.warning(f"Non-admin user {current_user.get('id')} attempted to save token")
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Check if config exists, create if not
        logger.debug(f"Checking if oauth_configs exists for {platform}")
        config_response = db.table("oauth_configs").select("*").eq("platform", platform).execute()
        logger.debug(f"Config response: {config_response.data}")
        
        # Build update data with all provided fields
        update_data = {}
        if "client_id" in token_data:
            update_data["client_id"] = token_data["client_id"]
        if "client_secret" in token_data:
            update_data["client_secret"] = token_data["client_secret"]
        if "redirect_uri" in token_data:
            update_data["redirect_uri"] = token_data["redirect_uri"]
        if "access_token" in token_data:
            update_data["access_token"] = token_data["access_token"]
        if "refresh_token" in token_data:
            update_data["refresh_token"] = token_data["refresh_token"]
        
        if config_response.data:
            # Update existing config with all provided fields
            logger.info(f"Updating existing config for {platform} with fields: {list(update_data.keys())}")
            db.table("oauth_configs").update(update_data).eq("platform", platform).execute()
        else:
            # Create new config with minimal data
            logger.info(f"Creating new config for {platform}")
            config_data = {
                "platform": platform,
                "client_id": token_data.get("client_id", ""),
                "client_secret": token_data.get("client_secret", ""),
                "redirect_uri": token_data.get("redirect_uri", ""),
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
            }
            logger.debug(f"Inserting config data: {config_data}")
            db.table("oauth_configs").insert(config_data).execute()
        
        logger.info(f"Successfully saved token for {platform}")
        return {"message": f"Token saved for {platform}"}
    except Exception as e:
        logger.error(f"Error saving token for {platform}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save token: {str(e)}")


@router.get("/oauth/{platform}/config")
async def get_oauth_config(
    platform: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get OAuth configuration for a specific platform (admin only)"""
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # For admin users, return all fields including access_token and app_name
    # (needed for platforms like Thingiverse that use Personal Access Tokens)
    response = db.table("oauth_configs").select("*").eq("platform", platform).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail=f"No OAuth config found for {platform}")
    
    config = response.data[0]
    
    # Add has_access_token flag for convenience
    has_token = bool(config.get("access_token"))
    
    return {
        **config,
        "has_access_token": has_token
    }


@router.get("/oauth/ravelry/debug")
async def get_ravelry_oauth_debug(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Return safe diagnostics for Ravelry OAuth state (admin only).

    This endpoint intentionally excludes secrets/tokens and only reports
    booleans/timestamps/status information to aid backend debugging.
    """
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    response = db.table("oauth_configs").select(
        "platform,client_id,client_secret,redirect_uri,access_token,refresh_token,token_expires_at,updated_at,created_at"
    ).eq("platform", "ravelry").limit(1).execute()

    if not response.data:
        return {
            "platform": "ravelry",
            "configured": False,
            "missing_fields": ["client_id", "client_secret", "redirect_uri", "access_token", "refresh_token"],
            "ready_for_api_calls": False,
            "ready_for_refresh": False,
            "token_expired": None,
            "token_expires_at": None,
            "last_scrape_log": None,
        }

    cfg = response.data[0]
    has_client_id = bool(cfg.get("client_id"))
    has_client_secret = bool(cfg.get("client_secret"))
    has_redirect_uri = bool(cfg.get("redirect_uri"))
    has_access_token = bool(cfg.get("access_token"))
    has_refresh_token = bool(cfg.get("refresh_token"))

    missing_fields = []
    if not has_client_id:
        missing_fields.append("client_id")
    if not has_client_secret:
        missing_fields.append("client_secret")
    if not has_redirect_uri:
        missing_fields.append("redirect_uri")
    if not has_access_token:
        missing_fields.append("access_token")
    if not has_refresh_token:
        missing_fields.append("refresh_token")

    token_expires_at = cfg.get("token_expires_at")
    token_expired = None
    if token_expires_at:
        try:
            expires_dt = datetime.fromisoformat(str(token_expires_at).replace("Z", "+00:00"))
            token_expired = expires_dt <= datetime.now(UTC)
        except Exception:
            token_expired = None

    last_log_response = db.table("scraping_logs").select(
        "id,created_at,source,status,products_found,products_added,products_updated,error_message,duration_seconds"
    ).eq("source", "Ravelry").order("created_at", desc=True).limit(1).execute()

    if not last_log_response.data:
        # Backward compatibility for lowercase legacy source values.
        last_log_response = db.table("scraping_logs").select(
            "id,created_at,source,status,products_found,products_added,products_updated,error_message,duration_seconds"
        ).eq("source", "ravelry").order("created_at", desc=True).limit(1).execute()

    return {
        "platform": "ravelry",
        "configured": True,
        "has_client_id": has_client_id,
        "has_client_secret": has_client_secret,
        "has_redirect_uri": has_redirect_uri,
        "has_access_token": has_access_token,
        "has_refresh_token": has_refresh_token,
        "missing_fields": missing_fields,
        "ready_for_api_calls": has_access_token,
        "ready_for_refresh": has_client_id and has_client_secret and has_refresh_token,
        "token_expires_at": token_expires_at,
        "token_expired": token_expired,
        "oauth_config_updated_at": cfg.get("updated_at"),
        "oauth_config_created_at": cfg.get("created_at"),
        "last_scrape_log": (last_log_response.data or [None])[0],
    }


@router.get("/oauth-configs", response_model=list[OAuthConfigResponse])
async def get_oauth_configs(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get OAuth configurations (admin only, without secrets)"""
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    response = db.table("oauth_configs").select("id,platform,client_id,redirect_uri,created_at,updated_at").execute()
    return response.data


@router.post("/oauth-configs", response_model=OAuthConfigResponse, status_code=201)
async def create_oauth_config(
    config: OAuthConfigCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Create OAuth configuration (admin only)"""
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    config_data = config.model_dump()
    response = db.table("oauth_configs").insert(config_data).execute()
    
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create OAuth config")
    
    return response.data[0]


@router.put("/oauth-configs/{platform}", response_model=OAuthConfigResponse)
async def update_oauth_config(
    platform: str,
    config: OAuthConfigUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Update OAuth configuration (admin only) - creates if doesn't exist"""
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check if config exists
    existing = db.table("oauth_configs").select("*").eq("platform", platform).execute()
    
    update_data = config.model_dump(exclude_unset=True)
    
    if existing.data:
        # Update existing config
        response = db.table("oauth_configs").update(update_data).eq("platform", platform).execute()
    else:
        # Create new config if it doesn't exist
        create_data = {
            "platform": platform,
            "client_id": update_data.get("client_id", ""),
            "client_secret": update_data.get("client_secret", ""),
            "redirect_uri": update_data.get("redirect_uri", ""),
            **{k: v for k, v in update_data.items() if k not in ("client_id", "client_secret", "redirect_uri")}
        }
        response = db.table("oauth_configs").insert(create_data).execute()
    
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to save OAuth config")
    
    return response.data[0]


@router.delete("/oauth/{platform}/disconnect", status_code=204)
async def disconnect_oauth(
    platform: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Clear OAuth tokens for a platform (admin only) - preserves config for reconnect"""
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check if config exists
    existing = db.table("oauth_configs").select("*").eq("platform", platform).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"No OAuth config found for {platform}")
    
    # Clear tokens but preserve config fields (client_id, client_secret, redirect_uri)
    # This allows reconnecting without re-entering credentials
    update_data = {
        "access_token": None,
        "refresh_token": None,
        "token_expires_at": None,
    }
    
    db.table("oauth_configs").update(update_data).eq("platform", platform).execute()
    
    return None


ALLOWED_SEARCH_PLATFORMS = {
    "github": "github",
    "thingiverse": "thingiverse",
    "ravelry": "ravelry_pa_categories",
}


def _load_search_terms(db, platform: str, fallback: list[str]) -> list[str]:
    """Load search terms for a platform.

    Tries JSON array column 'search_terms' first. If missing (normalized schema),
    falls back to collecting rows from 'search_term' column.
    """
    # Try single-row JSON array
    try:
        row = db.table("scraper_search_terms").select("search_terms").eq("platform", platform).limit(1).execute()
        terms = (row.data or [{}])[0].get("search_terms") if row.data else None
        if isinstance(terms, list) and terms:
            return terms
    except Exception:
        pass
    # Fallback: one row per term
    try:
        resp = db.table("scraper_search_terms").select("search_term").eq("platform", platform).execute()
        terms = [r.get("search_term") for r in (resp.data or []) if r.get("search_term")]
        if terms:
            return terms
    except Exception:
        pass
    return fallback


@router.get("/{platform}/search-terms", response_model=dict)
async def get_search_terms(
    platform: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get current scraper search terms for a platform (admin only)."""
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    key = ALLOWED_SEARCH_PLATFORMS.get(platform)
    if not key:
        raise HTTPException(status_code=404, detail="Unsupported platform")

    fallback = GitHubScraper.SEARCH_TERMS if platform == "github" else (
        ThingiverseScraper.SEARCH_TERMS if platform == "thingiverse" else RavelryScraper.PA_CATEGORIES
    )

    try:
        terms = _load_search_terms(db, key, fallback)
        return {"search_terms": terms}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load search terms: {e}")


class UpdateSearchTermsRequest(BaseModel):
    search_terms: list[str]


class AddSearchTermRequest(BaseModel):
    search_term: str


@router.post("/{platform}/search-terms", response_model=dict)
async def update_search_terms(
    platform: str,
    request: UpdateSearchTermsRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Update scraper search terms for a platform (admin only)."""
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    key = ALLOWED_SEARCH_PLATFORMS.get(platform)
    if not key:
        raise HTTPException(status_code=404, detail="Unsupported platform")

    # Validate search terms
    if not request.search_terms:
        raise HTTPException(status_code=400, detail="At least one search term is required")
    if len(request.search_terms) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 search terms allowed")
    for term in request.search_terms:
        if not term or not term.strip():
            raise HTTPException(status_code=400, detail="Search terms cannot be empty")
        if len(term) > 100:
            raise HTTPException(status_code=400, detail="Search terms must be 100 characters or less")

    sanitized = [term.strip() for term in request.search_terms]

    # Persist using JSON array if available; otherwise fall back to normalized rows
    try:
        payload = {"platform": key, "search_terms": sanitized}
        db.table("scraper_search_terms").upsert(payload).execute()
    except Exception as e:
        # Fallback: normalized schema with one row per term
        try:
            # Clear existing terms for platform
            db.table("scraper_search_terms").delete().eq("platform", key).execute()
            # Insert each term as a separate row
            rows = [{"platform": key, "search_term": term} for term in sanitized]
            if rows:
                db.table("scraper_search_terms").insert(rows).execute()
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"Failed to persist search terms: {e2}")

    # Update runtime variables for immediate effect
    if platform == "github":
        GitHubScraper.SEARCH_TERMS = sanitized
    elif platform == "thingiverse":
        ThingiverseScraper.SEARCH_TERMS = sanitized
    elif platform == "ravelry":
        RavelryScraper.PA_CATEGORIES = sanitized

    return {
        "success": True,
        "search_terms": sanitized,
        "message": f"Saved {len(sanitized)} search terms for {platform}."
    }


@router.post("/{platform}/search-terms/add", response_model=dict)
async def add_search_term(
    platform: str,
    request: AddSearchTermRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Append a single search term without replacing existing ones (admin only)."""
    if not current_user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    key = ALLOWED_SEARCH_PLATFORMS.get(platform)
    if not key:
        raise HTTPException(status_code=404, detail="Unsupported platform")

    term = request.search_term.strip() if request.search_term else ""
    if not term:
        raise HTTPException(status_code=400, detail="Search term cannot be empty")
    if len(term) > 100:
        raise HTTPException(status_code=400, detail="Search terms must be 100 characters or less")

    # Load existing terms (supports both schemas)
    existing = _load_search_terms(db, key, [])
    if term in existing:
        return {"success": True, "search_terms": existing, "message": "Term already exists"}

    new_terms = existing + [term]

    # Try array upsert first
    try:
        payload = {"platform": key, "search_terms": new_terms}
        db.table("scraper_search_terms").upsert(payload).execute()
    except Exception:
        # Fallback to normalized rows: insert only the new term
        try:
            db.table("scraper_search_terms").insert({"platform": key, "search_term": term}).execute()
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"Failed to persist search term: {e2}")

    # Update runtime variables for immediate effect
    if platform == "github":
        GitHubScraper.SEARCH_TERMS = new_terms
    elif platform == "thingiverse":
        ThingiverseScraper.SEARCH_TERMS = new_terms
    elif platform == "ravelry":
        RavelryScraper.PA_CATEGORIES = new_terms

    return {
        "success": True,
        "search_terms": new_terms,
        "message": f"Added search term to {platform}."
    }

# Backwards compatibility routes for GitHub
@router.get("/github/search-terms", response_model=dict)
async def legacy_get_github_search_terms(current_user: dict = Depends(get_current_user), db = Depends(get_db)):
    return await get_search_terms("github", current_user=current_user, db=db)


@router.post("/github/search-terms", response_model=dict)
async def legacy_update_github_search_terms(request: UpdateSearchTermsRequest, current_user: dict = Depends(get_current_user), db = Depends(get_db)):
    return await update_search_terms("github", request, current_user=current_user, db=db)
