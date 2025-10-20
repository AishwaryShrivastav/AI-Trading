"""Abstract base class for broker integrations."""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime


class BrokerBase(ABC):
    """Abstract base class for broker API integrations."""
    
    def __init__(self, api_key: str, api_secret: str, redirect_uri: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_uri = redirect_uri
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
    
    @abstractmethod
    async def authenticate(self, auth_code: str) -> Dict[str, Any]:
        """
        Authenticate using OAuth authorization code.
        
        Args:
            auth_code: Authorization code from OAuth callback
            
        Returns:
            Dict containing access_token, refresh_token, expires_in
        """
        pass
    
    @abstractmethod
    async def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh the access token using refresh token.
        
        Returns:
            Dict containing new access_token and expires_in
        """
        pass
    
    @abstractmethod
    async def get_ltp(self, symbol: str, exchange: str = "NSE") -> float:
        """
        Get Last Traded Price for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange code (NSE, BSE, etc.)
            
        Returns:
            Current LTP as float
        """
        pass
    
    @abstractmethod
    async def get_ohlcv(
        self, 
        symbol: str, 
        interval: str = "1D",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        exchange: str = "NSE"
    ) -> List[Dict[str, Any]]:
        """
        Get OHLCV historical data.
        
        Args:
            symbol: Trading symbol
            interval: Time interval (1D, 1H, 15M, etc.)
            from_date: Start date
            to_date: End date
            exchange: Exchange code
            
        Returns:
            List of OHLCV candles
        """
        pass
    
    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        transaction_type: str,  # BUY or SELL
        quantity: int,
        order_type: str = "MARKET",  # MARKET, LIMIT, SL, SL-M
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        exchange: str = "NSE",
        product: str = "D"  # D=Delivery, I=Intraday, M=Margin
    ) -> Dict[str, Any]:
        """
        Place an order with the broker.
        
        Args:
            symbol: Trading symbol
            transaction_type: BUY or SELL
            quantity: Number of shares
            order_type: MARKET, LIMIT, SL, SL-M
            price: Limit price (for LIMIT/SL orders)
            trigger_price: Trigger price (for SL/SL-M orders)
            exchange: Exchange code
            product: Product type
            
        Returns:
            Dict with order_id and status
        """
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Get status of a specific order.
        
        Args:
            order_id: Broker order ID
            
        Returns:
            Dict with order details and status
        """
        pass
    
    @abstractmethod
    async def get_order_history(self) -> List[Dict[str, Any]]:
        """
        Get history of all orders.
        
        Returns:
            List of order dictionaries
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel a pending order.
        
        Args:
            order_id: Broker order ID
            
        Returns:
            Dict with cancellation status
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Returns:
            List of position dictionaries
        """
        pass
    
    @abstractmethod
    async def get_funds(self) -> Dict[str, Any]:
        """
        Get account funds and margin information.
        
        Returns:
            Dict with available funds, used margin, etc.
        """
        pass
    
    @abstractmethod
    async def get_holdings(self) -> List[Dict[str, Any]]:
        """
        Get long-term holdings.
        
        Returns:
            List of holding dictionaries
        """
        pass
    
    def is_token_valid(self) -> bool:
        """Check if access token is valid and not expired."""
        if not self.access_token:
            return False
        if not self.token_expiry:
            return True
        return datetime.utcnow() < self.token_expiry
    
    async def ensure_authenticated(self):
        """Ensure we have a valid access token, refresh if needed."""
        if not self.is_token_valid():
            if self.refresh_token:
                await self.refresh_access_token()
            else:
                raise Exception("No valid authentication. Please re-authenticate.")

