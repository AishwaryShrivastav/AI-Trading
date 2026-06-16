"""Authentication router for broker OAuth."""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import logging

from ..database import get_db, Setting
from datetime import datetime, timedelta
from ..config import get_settings
from ..services.broker import UpstoxBroker
from ..schemas import TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)
settings = get_settings()


def get_broker():
    """Get Upstox broker instance."""
    return UpstoxBroker(
        api_key=settings.upstox_api_key,
        api_secret=settings.upstox_api_secret,
        redirect_uri=settings.upstox_redirect_uri
    )


@router.get("/upstox/login")
async def upstox_login(broker: UpstoxBroker = Depends(get_broker)):
    """Initiate Upstox OAuth flow."""
    auth_url = broker.get_auth_url()
    logger.info("Redirecting to Upstox login")
    return RedirectResponse(url=auth_url)


@router.get("/upstox/callback")
async def upstox_callback(
    code: str = Query(..., description="Authorization code from Upstox"),
    db: Session = Depends(get_db),
    broker: UpstoxBroker = Depends(get_broker)
):
    """
    Handle Upstox OAuth callback.
    Exchange authorization code for access token.
    """
    try:
        # Authenticate with the code
        token_data = await broker.authenticate(code)
        
        # Store tokens in database (access, refresh, expiry)
        access_token_setting = db.query(Setting).filter(
            Setting.key == "upstox_access_token"
        ).first()
        
        if access_token_setting:
            access_token_setting.value = token_data.get("access_token")
        else:
            access_token_setting = Setting(
                key="upstox_access_token",
                value=token_data.get("access_token"),
                description="Upstox access token"
            )
            db.add(access_token_setting)
        
        # Store refresh token
        refresh_token_setting = db.query(Setting).filter(
            Setting.key == "upstox_refresh_token"
        ).first()
        
        if refresh_token_setting:
            refresh_token_setting.value = token_data.get("refresh_token")
        else:
            refresh_token_setting = Setting(
                key="upstox_refresh_token",
                value=token_data.get("refresh_token"),
                description="Upstox refresh token"
            )
            db.add(refresh_token_setting)

        # Persist token expiry timestamp if provided
        expires_in = token_data.get("expires_in")
        if expires_in:
            expiry_setting = db.query(Setting).filter(
                Setting.key == "upstox_token_expiry"
            ).first()
            expiry_value = (datetime.utcnow() + timedelta(seconds=int(expires_in))).isoformat()
            if expiry_setting:
                expiry_setting.value = expiry_value
            else:
                expiry_setting = Setting(
                    key="upstox_token_expiry",
                    value=expiry_value,
                    description="Upstox access token expiry (UTC ISO)"
                )
                db.add(expiry_setting)
        
        db.commit()
        
        logger.info("Successfully authenticated with Upstox")
        
        # Redirect to frontend dashboard
        return RedirectResponse(url="/?auth=success")
        
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


@router.get("/status")
async def auth_status(db: Session = Depends(get_db)):
    """Check authentication status, considering expiry; mark false if expired or missing."""
    access_token = db.query(Setting).filter(Setting.key == "upstox_access_token").first()
    expiry_setting = db.query(Setting).filter(Setting.key == "upstox_token_expiry").first()
    refresh_token = db.query(Setting).filter(Setting.key == "upstox_refresh_token").first()

    has_access = bool(access_token and access_token.value)
    has_refresh = bool(refresh_token and refresh_token.value)
    authenticated = False
    expires_at_value = None
    if expiry_setting and expiry_setting.value:
        try:
            expires_at = datetime.fromisoformat(expiry_setting.value)
            expires_at_value = expiry_setting.value
            authenticated = has_access and (datetime.utcnow() < expires_at)
        except Exception:
            # If malformed expiry, fall back to access-token presence
            authenticated = has_access
    else:
        # If expiry is not persisted yet, consider authenticated if we have an access token
        authenticated = has_access

    return {
        "authenticated": authenticated,
        "has_refresh": has_refresh,
        "expires_at": expires_at_value,
        "broker": "upstox"
    }

