"""Authentication router for broker OAuth."""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import logging

from ..database import get_db, Setting
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
        
        # Store tokens in database
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
        
        db.commit()
        
        logger.info("Successfully authenticated with Upstox")
        
        # Redirect to frontend dashboard
        return RedirectResponse(url="/?auth=success")
        
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


@router.get("/status")
async def auth_status(db: Session = Depends(get_db)):
    """Check authentication status."""
    access_token = db.query(Setting).filter(
        Setting.key == "upstox_access_token"
    ).first()
    
    return {
        "authenticated": access_token is not None and access_token.value is not None,
        "broker": "upstox"
    }

