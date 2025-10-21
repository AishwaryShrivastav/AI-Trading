"""Upstox broker integration with comprehensive API coverage."""
import httpx
import json
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime, timedelta
from .base import BrokerBase
import logging

logger = logging.getLogger(__name__)


class UpstoxBroker(BrokerBase):
    """Upstox API v2/v3 integration with full feature support."""
    
    BASE_URL = "https://api.upstox.com/v2"
    BASE_URL_V3 = "https://api.upstox.com/v3"
    AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
    
    # Instrument file URLs
    INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json"
    INSTRUMENTS_NSE_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json"
    INSTRUMENTS_BSE_URL = "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json"
    INSTRUMENTS_MCX_URL = "https://assets.upstox.com/market-quote/instruments/exchange/MCX.json"
    
    def __init__(self, api_key: str, api_secret: str, redirect_uri: str):
        super().__init__(api_key, api_secret, redirect_uri)
        self.client = httpx.AsyncClient(timeout=30.0)
        self._instruments_cache: Optional[Dict[str, Any]] = None
        self._instruments_cache_time: Optional[datetime] = None
    
    def get_auth_url(self) -> str:
        """Get OAuth authorization URL for user login."""
        return f"{self.AUTH_URL}?client_id={self.api_key}&redirect_uri={self.redirect_uri}&response_type=code"
    
    async def authenticate(self, auth_code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        try:
            payload = {
                "code": auth_code,
                "client_id": self.api_key,
                "client_secret": self.api_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code"
            }
            
            response = await self.client.post(self.TOKEN_URL, data=payload)
            response.raise_for_status()
            data = response.json()
            
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
            expires_in = data.get("expires_in", 86400)  # Default 24 hours
            self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            
            logger.info("Successfully authenticated with Upstox")
            return data
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise
    
    async def refresh_access_token(self) -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        try:
            payload = {
                "refresh_token": self.refresh_token,
                "client_id": self.api_key,
                "client_secret": self.api_secret,
                "grant_type": "refresh_token"
            }
            
            response = await self.client.post(self.TOKEN_URL, data=payload)
            response.raise_for_status()
            data = response.json()
            
            self.access_token = data.get("access_token")
            expires_in = data.get("expires_in", 86400)
            self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            
            logger.info("Successfully refreshed access token")
            return data
            
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authorization."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
    
    def _get_instrument_key(self, symbol: str, exchange: str = "NSE") -> str:
        """Convert symbol to Upstox instrument key format."""
        # Upstox format: NSE_EQ|INE123A01234 or simplified NSE_EQ:{symbol}
        return f"{exchange}_EQ|{symbol}"
    
    async def get_ltp(self, symbol: str, exchange: str = "NSE") -> float:
        """Get Last Traded Price."""
        await self.ensure_authenticated()
        
        try:
            instrument_key = self._get_instrument_key(symbol, exchange)
            url = f"{self.BASE_URL}/market-quote/ltp"
            params = {"instrument_key": instrument_key}
            
            response = await self.client.get(
                url, 
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract LTP from response
            ltp = data.get("data", {}).get(instrument_key, {}).get("last_price", 0.0)
            return float(ltp)
            
        except Exception as e:
            logger.error(f"Failed to get LTP for {symbol}: {e}")
            raise
    
    async def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1day",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        exchange: str = "NSE"
    ) -> List[Dict[str, Any]]:
        """Get historical OHLCV data."""
        await self.ensure_authenticated()
        
        try:
            instrument_key = self._get_instrument_key(symbol, exchange)
            url = f"{self.BASE_URL}/historical-candle/{instrument_key}/{interval}"
            
            # Add date parameters if provided
            if to_date:
                url += f"/{to_date.strftime('%Y-%m-%d')}"
                if from_date:
                    url += f"/{from_date.strftime('%Y-%m-%d')}"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            candles = data.get("data", {}).get("candles", [])
            
            # Convert to standardized format
            ohlcv_data = []
            for candle in candles:
                ohlcv_data.append({
                    "timestamp": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5]
                })
            
            return ohlcv_data
            
        except Exception as e:
            logger.error(f"Failed to get OHLCV for {symbol}: {e}")
            raise
    
    async def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        exchange: str = "NSE",
        product: str = "D",
        instrument_token_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Place an order."""
        await self.ensure_authenticated()
        
        try:
            instrument_key = instrument_token_override or self._get_instrument_key(symbol, exchange)
            
            payload = {
                "instrument_token": instrument_key,
                "quantity": quantity,
                "transaction_type": transaction_type.upper(),
                "order_type": order_type.upper(),
                "product": product,
                "validity": "DAY"
            }
            
            if order_type in ["LIMIT", "SL"] and price:
                payload["price"] = price
            
            if order_type in ["SL", "SL-M"] and trigger_price:
                payload["trigger_price"] = trigger_price
            
            url = f"{self.BASE_URL}/order/place"
            response = await self.client.post(
                url,
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Order placed successfully: {data}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise
    
    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get order status."""
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/order/details"
            params = {"order_id": order_id}
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", {})
            
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            raise
    
    async def get_order_history(self) -> List[Dict[str, Any]]:
        """Get all orders."""
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/order/retrieve-all"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", [])
            
        except Exception as e:
            logger.error(f"Failed to get order history: {e}")
            raise
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order."""
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/order/cancel"
            payload = {"order_id": order_id}
            
            response = await self.client.delete(
                url,
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Order cancelled: {order_id}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            raise
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/portfolio/short-term-positions"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", [])
            
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise
    
    async def get_funds(self) -> Dict[str, Any]:
        """Get account funds."""
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/user/get-funds-and-margin"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", {})
            
        except Exception as e:
            logger.error(f"Failed to get funds: {e}")
            raise
    
    async def get_holdings(self) -> List[Dict[str, Any]]:
        """Get holdings."""
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/portfolio/long-term-holdings"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", [])
            
        except Exception as e:
            logger.error(f"Failed to get holdings: {e}")
            raise
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        order_type: Optional[str] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        validity: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Modify an existing order (v3 API).
        
        Args:
            order_id: Broker order ID to modify
            quantity: New quantity
            order_type: New order type (MARKET, LIMIT, SL, SL-M)
            price: New limit price
            trigger_price: New trigger price
            validity: New validity (DAY, IOC)
            
        Returns:
            Modified order details
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL_V3}/order/modify"
            
            payload = {"order_id": order_id}
            
            if quantity is not None:
                payload["quantity"] = quantity
            if order_type is not None:
                payload["order_type"] = order_type.upper()
            if price is not None:
                payload["price"] = price
            if trigger_price is not None:
                payload["trigger_price"] = trigger_price
            if validity is not None:
                payload["validity"] = validity.upper()
            
            response = await self.client.put(
                url,
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Order modified successfully: {order_id}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
            raise
    
    async def place_multi_order(
        self,
        orders: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Place multiple orders in a single API call.
        
        Args:
            orders: List of order dictionaries, each containing:
                - symbol: Trading symbol
                - transaction_type: BUY or SELL
                - quantity: Number of shares
                - order_type: MARKET, LIMIT, SL, SL-M
                - price: Limit price (optional)
                - trigger_price: Trigger price (optional)
                - exchange: Exchange (default NSE)
                - product: Product type (default D)
                
        Returns:
            List of order responses with order_ids
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/order/multi/place"
            
            # Format orders for Upstox API
            formatted_orders = []
            for order in orders:
                formatted_order = {
                    "instrument_token": self._get_instrument_key(
                        order.get("symbol"),
                        order.get("exchange", "NSE")
                    ),
                    "quantity": order["quantity"],
                    "transaction_type": order["transaction_type"].upper(),
                    "order_type": order.get("order_type", "MARKET").upper(),
                    "product": order.get("product", "D"),
                    "validity": "DAY"
                }
                
                if order.get("price"):
                    formatted_order["price"] = order["price"]
                if order.get("trigger_price"):
                    formatted_order["trigger_price"] = order["trigger_price"]
                
                formatted_orders.append(formatted_order)
            
            response = await self.client.post(
                url,
                headers=self._get_headers(),
                json={"orders": formatted_orders}
            )
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Multi-order placed: {len(formatted_orders)} orders")
            return data.get("data", [])
            
        except Exception as e:
            logger.error(f"Failed to place multi-order: {e}")
            raise
    
    async def get_trades_by_order(self, order_id: str) -> List[Dict[str, Any]]:
        """
        Get all trades/executions for a specific order.
        
        Args:
            order_id: Broker order ID
            
        Returns:
            List of trade executions for the order
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/order/trades/get-trades-for-order"
            params = {"order_id": order_id}
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", [])
            
        except Exception as e:
            logger.error(f"Failed to get trades for order {order_id}: {e}")
            raise
    
    async def get_trade_history(
        self,
        page_number: int = 1,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """
        Get paginated trade history.
        
        Args:
            page_number: Page number (1-indexed)
            page_size: Number of trades per page (max 1000)
            
        Returns:
            Dict containing trades list and pagination info
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/charges/historical-trades"
            params = {
                "page_number": page_number,
                "page_size": min(page_size, 1000)
            }
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", {})
            
        except Exception as e:
            logger.error(f"Failed to get trade history: {e}")
            raise
    
    async def get_brokerage(
        self,
        instrument_token: str,
        quantity: int,
        transaction_type: str,
        product: str = "D"
    ) -> Dict[str, Any]:
        """
        Calculate brokerage charges for a potential trade.
        
        Args:
            instrument_token: Upstox instrument key
            quantity: Number of shares
            transaction_type: BUY or SELL
            product: Product type (D=Delivery, I=Intraday)
            
        Returns:
            Dict with brokerage breakdown (charges, taxes, etc.)
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/charges/brokerage"
            params = {
                "instrument_token": instrument_token,
                "quantity": quantity,
                "transaction_type": transaction_type.upper(),
                "product": product
            }
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", {})
            
        except Exception as e:
            logger.error(f"Failed to get brokerage: {e}")
            raise
    
    async def get_margin_required(
        self,
        instruments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate margin required for orders.
        
        Args:
            instruments: List of order details containing:
                - instrument_token: Upstox instrument key
                - quantity: Number of shares
                - transaction_type: BUY or SELL
                - product: Product type
                - order_type: Order type
                - price: Price (for LIMIT orders)
                
        Returns:
            Margin requirement details
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/charges/margin"
            
            response = await self.client.post(
                url,
                headers=self._get_headers(),
                json={"instruments": instruments}
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", {})
            
        except Exception as e:
            logger.error(f"Failed to get margin requirement: {e}")
            raise
    
    async def get_day_positions(self) -> List[Dict[str, Any]]:
        """
        Get intraday positions.
        
        Returns:
            List of day positions
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/portfolio/short-term-positions"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            positions = data.get("data", [])
            # Filter only day positions
            return [p for p in positions if p.get("day_buy_quantity", 0) > 0 or p.get("day_sell_quantity", 0) > 0]
            
        except Exception as e:
            logger.error(f"Failed to get day positions: {e}")
            raise
    
    async def get_net_positions(self) -> List[Dict[str, Any]]:
        """
        Get net positions (day + overnight combined).
        
        Returns:
            List of net positions with combined P&L
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/portfolio/short-term-positions"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", [])
            
        except Exception as e:
            logger.error(f"Failed to get net positions: {e}")
            raise
    
    async def convert_position(
        self,
        instrument_token: str,
        transaction_type: str,
        quantity: int,
        from_product: str,
        to_product: str
    ) -> Dict[str, Any]:
        """
        Convert position from one product type to another.
        (e.g., Intraday to Delivery or vice versa)
        
        Args:
            instrument_token: Upstox instrument key
            transaction_type: BUY or SELL
            quantity: Quantity to convert
            from_product: Current product (I=Intraday, D=Delivery)
            to_product: Target product
            
        Returns:
            Conversion status
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/portfolio/convert-position"
            
            payload = {
                "instrument_token": instrument_token,
                "transaction_type": transaction_type.upper(),
                "quantity": quantity,
                "from_product": from_product,
                "to_product": to_product
            }
            
            response = await self.client.put(
                url,
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Position converted: {from_product} -> {to_product}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to convert position: {e}")
            raise
    
    async def get_instruments(
        self,
        exchange: Optional[str] = None,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get instrument master data.
        Uses caching to avoid repeated downloads (refreshed daily).
        
        Args:
            exchange: Specific exchange (NSE, BSE, MCX) or None for all
            force_refresh: Force refresh cache
            
        Returns:
            List of instruments with metadata
        """
        # Check cache
        cache_valid = (
            self._instruments_cache is not None and
            self._instruments_cache_time is not None and
            (datetime.utcnow() - self._instruments_cache_time) < timedelta(hours=12) and
            not force_refresh
        )
        
        if cache_valid and exchange is None:
            return self._instruments_cache
        
        try:
            # Select URL based on exchange
            if exchange == "NSE":
                url = self.INSTRUMENTS_NSE_URL
            elif exchange == "BSE":
                url = self.INSTRUMENTS_BSE_URL
            elif exchange == "MCX":
                url = self.INSTRUMENTS_MCX_URL
            else:
                url = self.INSTRUMENTS_URL
            
            response = await self.client.get(url)
            response.raise_for_status()
            instruments = response.json()
            
            # Cache complete instruments
            if exchange is None:
                self._instruments_cache = instruments
                self._instruments_cache_time = datetime.utcnow()
            
            logger.info(f"Loaded {len(instruments)} instruments from {exchange or 'all exchanges'}")
            return instruments
            
        except Exception as e:
            logger.error(f"Failed to get instruments: {e}")
            raise
    
    async def search_instrument(
        self,
        query: str,
        instrument_type: Optional[str] = None,
        exchange: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for instruments by symbol or name.
        
        Args:
            query: Search query (symbol or name)
            instrument_type: Filter by type (EQ, FUT, OPT, etc.)
            exchange: Filter by exchange
            
        Returns:
            List of matching instruments
        """
        instruments = await self.get_instruments(exchange=exchange)
        
        query = query.upper()
        results = []
        
        for inst in instruments:
            # Match on trading symbol or name
            if (query in inst.get("trading_symbol", "").upper() or 
                query in inst.get("name", "").upper()):
                
                # Apply instrument type filter
                if instrument_type and inst.get("instrument_type") != instrument_type:
                    continue
                
                results.append(inst)
        
        return results[:50]  # Limit to 50 results
    
    async def get_profile(self) -> Dict[str, Any]:
        """
        Get user profile information.
        
        Returns:
            User profile details
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/user/profile"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", {})
            
        except Exception as e:
            logger.error(f"Failed to get profile: {e}")
            raise
    
    async def get_limits(self) -> Dict[str, Any]:
        """
        Get trading limits and available funds.
        Alias for get_funds() for better clarity.
        
        Returns:
            Account limits and funds
        """
        return await self.get_funds()
    
    async def get_market_quote_full(
        self,
        instrument_keys: List[str]
    ) -> Dict[str, Any]:
        """
        Get full market quote with depth, greeks, etc.
        
        Args:
            instrument_keys: List of instrument keys
            
        Returns:
            Detailed market data including:
            - OHLC
            - LTP
            - Depth (bid/ask)
            - Greeks (for options)
            - OI (for F&O)
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/market-quote/quotes"
            params = {"instrument_key": ",".join(instrument_keys)}
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", {})
            
        except Exception as e:
            logger.error(f"Failed to get market quote: {e}")
            raise
    
    async def get_option_chain(
        self,
        instrument_key: str,
        expiry_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get option chain for an underlying.
        
        Args:
            instrument_key: Underlying instrument key
            expiry_date: Specific expiry date (YYYY-MM-DD)
            
        Returns:
            Option chain with CE and PE data
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/option/chain"
            params = {"instrument_key": instrument_key}
            
            if expiry_date:
                params["expiry_date"] = expiry_date
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get("data", {})
            
        except Exception as e:
            logger.error(f"Failed to get option chain: {e}")
            raise
    
    async def get_intraday_candle_data(
        self,
        instrument_key: str,
        interval: Literal["1minute", "30minute"]
    ) -> List[Dict[str, Any]]:
        """
        Get intraday candle data.
        
        Args:
            instrument_key: Upstox instrument key
            interval: 1minute or 30minute
            
        Returns:
            List of intraday candles for current day
        """
        await self.ensure_authenticated()
        
        try:
            url = f"{self.BASE_URL}/historical-candle/intraday/{instrument_key}/{interval}"
            
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            candles = data.get("data", {}).get("candles", [])
            
            # Convert to standardized format
            ohlcv_data = []
            for candle in candles:
                ohlcv_data.append({
                    "timestamp": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5]
                })
            
            return ohlcv_data
            
        except Exception as e:
            logger.error(f"Failed to get intraday candles: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

