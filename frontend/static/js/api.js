// API Client for AI Trading System

const API_BASE_URL = '';  // Same origin

class APIClient {
    constructor() {
        this.baseUrl = API_BASE_URL;
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        };

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API Request failed:', error);
            throw error;
        }
    }

    // Auth endpoints
    async getAuthStatus() {
        return this.request('/api/auth/status');
    }

    initiateUpstoxLogin() {
        window.location.href = '/api/auth/upstox/login';
    }

    // Trade Cards endpoints
    async getPendingTradeCards() {
        return this.request('/api/trade-cards/pending');
    }

    async getTradeCard(id) {
        return this.request(`/api/trade-cards/${id}`);
    }

    async approveTradeCard(id, userId = 'default_user', notes = null) {
        return this.request(`/api/trade-cards/${id}/approve`, {
            method: 'POST',
            body: JSON.stringify({
                trade_card_id: id,
                user_id: userId,
                notes: notes
            }),
        });
    }

    async rejectTradeCard(id, reason, userId = 'default_user') {
        return this.request(`/api/trade-cards/${id}/reject`, {
            method: 'POST',
            body: JSON.stringify({
                trade_card_id: id,
                reason: reason,
                user_id: userId
            }),
        });
    }

    async getRiskSummary(id) {
        return this.request(`/api/trade-cards/${id}/risk-summary`);
    }

    // Guardrails endpoints
    async guardrailsCheck(payload) {
        return this.request('/api/guardrails/check', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    async guardrailsExplain(cardId) {
        return this.request(`/api/guardrails/explain?card_id=${cardId}`);
    }

    // Options strategy endpoints
    async generateOptionStrategy(symbol, expiry, accountId, strategyType = 'IRON_CONDOR', maxRisk = 50000) {
        return this.request('/api/options/strategy/generate', {
            method: 'POST',
            body: JSON.stringify({ symbol, expiry, account_id: accountId, strategy_type: strategyType, max_risk: maxRisk })
        });
    }

    async executeOptionStrategy(strategyId) {
        return this.request('/api/options/strategy/execute', {
            method: 'POST',
            body: JSON.stringify({ strategy_id: strategyId })
        });
    }

    // Positions endpoints
    async getPositions() {
        return this.request('/api/positions');
    }

    async getFunds() {
        return this.request('/api/funds');
    }

    // Orders endpoints
    async getOrders() {
        return this.request('/api/orders');
    }

    async getOrder(id) {
        return this.request(`/api/orders/${id}`);
    }

    async refreshOrderStatus(id) {
        return this.request(`/api/orders/${id}/refresh`, {
            method: 'POST',
        });
    }

    // Signals endpoints
    async runSignalGeneration(strategies = null, symbols = null) {
        return this.request('/api/signals/run', {
            method: 'POST',
            body: JSON.stringify({
                strategies: strategies,
                symbols: symbols,
                force_refresh: false
            }),
        });
    }

    async getStrategies() {
        return this.request('/api/signals/strategies');
    }

    // Reports endpoints
    async getEODReport(date = null) {
        const params = date ? `?date=${date}` : '';
        return this.request(`/api/reports/eod${params}`);
    }

    async getMonthlyReport(month = null) {
        const params = month ? `?month=${month}` : '';
        return this.request(`/api/reports/monthly${params}`);
    }

    // Health check
    async healthCheck() {
        return this.request('/health');
    }
}

// Export singleton instance
const api = new APIClient();

