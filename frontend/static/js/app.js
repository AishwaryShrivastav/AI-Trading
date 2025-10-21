// Main Application Logic

class TradingApp {
    constructor() {
        this.currentTab = 'pending';
        this.tradeCards = [];
        this.positions = [];
        this.orders = [];
        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.checkAuthStatus();
        await this.loadInitialData();
        
        // Check for auth success redirect
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('auth') === 'success') {
            this.showToast('Successfully authenticated with Upstox!', 'success');
            window.history.replaceState({}, document.title, '/');
        }
    }

    setupEventListeners() {
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });

        // Auth button
        document.getElementById('authBtn').addEventListener('click', () => {
            api.initiateUpstoxLogin();
        });

        // Refresh button
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.loadCurrentTabData();
        });

        // Generate signals button
        document.getElementById('generateSignalsBtn').addEventListener('click', () => {
            this.generateSignals();
        });

        // Options chain load
        const loadChainBtn = document.getElementById('loadChainBtn');
        if (loadChainBtn) {
            loadChainBtn.addEventListener('click', async () => {
                const sym = document.getElementById('opt-symbol').value.trim();
                const expiry = document.getElementById('opt-expiry').value.trim();
                await this.loadOptionChain(sym, expiry || null);
            });
        }

        // Modal close
        document.querySelector('.modal-close').addEventListener('click', () => {
            this.closeModal();
        });

        // Close modal on outside click
        document.getElementById('trade-card-modal').addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                this.closeModal();
            }
        });
    }

    async checkAuthStatus() {
        try {
            const status = await api.getAuthStatus();
            const authBtn = document.getElementById('authBtn');
            if (status.authenticated) {
                authBtn.textContent = '✓ Authenticated';
                authBtn.classList.remove('btn-secondary');
                authBtn.classList.add('btn-success');
                authBtn.disabled = true;
            }
        } catch (error) {
            console.error('Auth status check failed:', error);
        }
    }

    async loadInitialData() {
        await this.loadCurrentTabData();
    }

    async loadCurrentTabData() {
        this.showLoading(true);
        try {
            switch (this.currentTab) {
                case 'pending':
                    await this.loadPendingTradeCards();
                    break;
                case 'positions':
                    await this.loadPositions();
                    break;
                case 'orders':
                    await this.loadOrders();
                    break;
                case 'reports':
                    await this.loadReports();
                    break;
            case 'options':
                // No auto load; user can load
                break;
            }
        } catch (error) {
            this.showToast('Failed to load data: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    async loadOptionChain(symbol, expiry) {
        this.showLoading(true);
        try {
            const params = new URLSearchParams({ symbol });
            if (expiry) params.append('expiry', expiry);
            const res = await api.request(`/api/options/chain?${params.toString()}`);
            const container = document.getElementById('option-chain');
            const data = res.data || {};
            const strikes = data.strikes || [];
            if (!strikes.length) {
                container.innerHTML = '<div class="empty-state"><p>No chain data available.</p></div>';
                return;
            }
            // Render simple table view
            const rows = strikes.slice(0, 50).map(s => `
                <tr>
                    <td>${s.strike}</td>
                    <td>${(s.call && s.call.ltp) || ''}</td>
                    <td>${(s.call && s.call.oi) || ''}</td>
                    <td>${(s.put && s.put.ltp) || ''}</td>
                    <td>${(s.put && s.put.oi) || ''}</td>
                </tr>
            `).join('');

            container.innerHTML = `
                <table>
                    <thead>
                        <tr>
                            <th>Strike</th>
                            <th>CE LTP</th>
                            <th>CE OI</th>
                            <th>PE LTP</th>
                            <th>PE OI</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
        } catch (e) {
            this.showToast('Failed to load option chain', 'error');
        } finally {
            this.showLoading(false);
        }
    }

    switchTab(tabName) {
        this.currentTab = tabName;

        // Update tab buttons
        document.querySelectorAll('.tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`${tabName}-tab`).classList.add('active');

        this.loadCurrentTabData();
    }

    async loadPendingTradeCards() {
        try {
            this.tradeCards = await api.getPendingTradeCards();
            this.renderTradeCards();
        } catch (error) {
            console.error('Failed to load trade cards:', error);
            throw error;
        }
    }

    renderTradeCards() {
        const grid = document.getElementById('trade-cards-grid');
        const noTrades = document.getElementById('no-trades');
        const countBadge = document.getElementById('pending-count');

        if (this.tradeCards.length === 0) {
            grid.innerHTML = '';
            noTrades.style.display = 'block';
            countBadge.textContent = '0';
            return;
        }

        noTrades.style.display = 'none';
        countBadge.textContent = this.tradeCards.length;

        grid.innerHTML = this.tradeCards.map(card => this.createTradeCardHTML(card)).join('');

        // Add event listeners
        this.tradeCards.forEach(card => {
            document.getElementById(`approve-${card.id}`).addEventListener('click', () => {
                this.approveTradeCard(card.id);
            });

            document.getElementById(`reject-${card.id}`).addEventListener('click', () => {
                this.rejectTradeCard(card.id);
            });

            const explainBtn = document.querySelector(`.guardrail-explain-btn[data-card-id="${card.id}"]`);
            if (explainBtn) {
                explainBtn.addEventListener('click', async () => {
                    try {
                        const data = await api.guardrailsExplain(card.id);
                        alert(`Guardrails for ${data.symbol}:\n` + JSON.stringify(data, null, 2));
                    } catch (e) {
                        alert('Failed to load guardrail details');
                    }
                });
            }
        });
    }

    createTradeCardHTML(card) {
        const confidence = (card.confidence * 100).toFixed(0);
        const riskReward = ((card.take_profit - card.entry_price) / (card.entry_price - card.stop_loss)).toFixed(2);
        
        const guardrails = [
            {name: 'Liquidity', passed: card.liquidity_check, icon: '💧'},
            {name: 'Position Size', passed: card.position_size_check, icon: '📊'},
            {name: 'Exposure', passed: card.exposure_check, icon: '🎯'},
            {name: 'Event Window', passed: card.event_window_check, icon: '📅'},
            {name: 'Regime', passed: card.regime_check, icon: '🌡️'},
            {name: 'Catalyst', passed: card.catalyst_freshness_check, icon: '⚡'}
        ];
        const guardrailsHtml = `
            <div class="guardrails-section">
                <div class="guardrails-title">Guardrails</div>
                ${guardrails.map(g => `
                    <span class="guardrail ${g.passed ? 'pass' : 'fail'}">
                        ${g.icon} ${g.name} ${g.passed ? '✓' : '✗'}
                    </span>
                `).join('')}
                ${card.risk_warnings && card.risk_warnings.length ? `
                    <button class="guardrail-explain-btn" data-card-id="${card.id}">Explain (${card.risk_warnings.length})</button>
                ` : ''}
            </div>
        `;

        return `
            <div class="trade-card">
                <div class="trade-card-header">
                    <span class="symbol">${card.symbol}</span>
                    <span class="trade-type ${card.trade_type.toLowerCase()}">${card.trade_type}</span>
                </div>
                <div class="trade-card-body">
                    <div class="trade-detail">
                        <span class="trade-detail-label">Entry</span>
                        <span class="trade-detail-value">₹${card.entry_price.toFixed(2)}</span>
                    </div>
                    <div class="trade-detail">
                        <span class="trade-detail-label">Quantity</span>
                        <span class="trade-detail-value">${card.quantity}</span>
                    </div>
                    <div class="trade-detail">
                        <span class="trade-detail-label">Stop Loss</span>
                        <span class="trade-detail-value">₹${card.stop_loss.toFixed(2)}</span>
                    </div>
                    <div class="trade-detail">
                        <span class="trade-detail-label">Take Profit</span>
                        <span class="trade-detail-value">₹${card.take_profit.toFixed(2)}</span>
                    </div>
                    <div class="trade-detail">
                        <span class="trade-detail-label">Risk:Reward</span>
                        <span class="trade-detail-value">1:${riskReward}</span>
                    </div>
                    <div class="trade-detail">
                        <span class="trade-detail-label">Strategy</span>
                        <span class="trade-detail-value">${card.strategy || 'N/A'}</span>
                    </div>
                    <div class="confidence-bar">
                        <div class="confidence-bar-label">Confidence: ${confidence}%</div>
                        <div class="confidence-bar-track">
                            <div class="confidence-bar-fill" style="width: ${confidence}%"></div>
                        </div>
                    </div>
                    ${card.evidence ? `<div class="evidence">${this.truncate(card.evidence, 150)}</div>` : ''}
                    ${guardrailsHtml}
                </div>
                <div class="trade-card-actions">
                    <button id="reject-${card.id}" class="btn btn-danger">Reject</button>
                    <button id="approve-${card.id}" class="btn btn-success">Approve</button>
                </div>
            </div>
        `;
    }

    truncate(text, length) {
        if (text.length <= length) return text;
        return text.substring(0, length) + '...';
    }

    async approveTradeCard(id) {
        if (!confirm('Approve this trade and place order?')) {
            return;
        }

        this.showLoading(true);
        try {
            const result = await api.approveTradeCard(id);
            this.showToast('Trade approved and order placed!', 'success');
            await this.loadPendingTradeCards();
        } catch (error) {
            this.showToast('Failed to approve trade: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    async rejectTradeCard(id) {
        const reason = prompt('Reason for rejection:');
        if (!reason) return;

        this.showLoading(true);
        try {
            await api.rejectTradeCard(id, reason);
            this.showToast('Trade rejected', 'success');
            await this.loadPendingTradeCards();
        } catch (error) {
            this.showToast('Failed to reject trade: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    async loadPositions() {
        try {
            this.positions = await api.getPositions();
            this.renderPositions();
        } catch (error) {
            console.error('Failed to load positions:', error);
            throw error;
        }
    }

    renderPositions() {
        const container = document.getElementById('positions-list');
        
        if (this.positions.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No open positions</p></div>';
            return;
        }

        const html = `
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Avg Price</th>
                        <th>Current Price</th>
                        <th>P&L</th>
                        <th>Opened At</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.positions.map(pos => `
                        <tr>
                            <td><strong>${pos.symbol}</strong></td>
                            <td>${pos.quantity}</td>
                            <td>₹${pos.average_price.toFixed(2)}</td>
                            <td>₹${pos.current_price ? pos.current_price.toFixed(2) : 'N/A'}</td>
                            <td class="${(pos.unrealized_pnl || 0) >= 0 ? 'positive' : 'negative'}">
                                ₹${(pos.unrealized_pnl || 0).toFixed(2)}
                            </td>
                            <td>${new Date(pos.opened_at).toLocaleString()}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        
        container.innerHTML = html;
    }

    async loadOrders() {
        try {
            this.orders = await api.getOrders();
            this.renderOrders();
        } catch (error) {
            console.error('Failed to load orders:', error);
            throw error;
        }
    }

    renderOrders() {
        const container = document.getElementById('orders-list');
        
        if (this.orders.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No orders</p></div>';
            return;
        }

        const html = `
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Type</th>
                        <th>Quantity</th>
                        <th>Price</th>
                        <th>Status</th>
                        <th>Placed At</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.orders.map(order => `
                        <tr>
                            <td><strong>${order.symbol}</strong></td>
                            <td>${order.transaction_type}</td>
                            <td>${order.quantity}</td>
                            <td>₹${order.price ? order.price.toFixed(2) : 'Market'}</td>
                            <td><span class="badge">${order.status}</span></td>
                            <td>${new Date(order.placed_at).toLocaleString()}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        
        container.innerHTML = html;
    }

    async loadReports() {
        try {
            const [eodReport, monthlyReport] = await Promise.all([
                api.getEODReport(),
                api.getMonthlyReport()
            ]);
            this.renderReports(eodReport, monthlyReport);
        } catch (error) {
            console.error('Failed to load reports:', error);
            throw error;
        }
    }

    renderReports(eodReport, monthlyReport) {
        // EOD Report
        const eodContainer = document.getElementById('eod-report');
        eodContainer.innerHTML = `
            <div class="metric">
                <span class="metric-label">Total Trades</span>
                <span class="metric-value">${eodReport.total_trades}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Open Positions</span>
                <span class="metric-value">${eodReport.open_positions}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Closed Positions</span>
                <span class="metric-value">${eodReport.closed_positions}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Realized P&L</span>
                <span class="metric-value ${eodReport.realized_pnl >= 0 ? 'positive' : 'negative'}">
                    ₹${eodReport.realized_pnl.toFixed(2)}
                </span>
            </div>
            <div class="metric">
                <span class="metric-label">Unrealized P&L</span>
                <span class="metric-value ${eodReport.unrealized_pnl >= 0 ? 'positive' : 'negative'}">
                    ₹${eodReport.unrealized_pnl.toFixed(2)}
                </span>
            </div>
            <div class="metric">
                <span class="metric-label">Total P&L</span>
                <span class="metric-value ${eodReport.total_pnl >= 0 ? 'positive' : 'negative'}">
                    ₹${eodReport.total_pnl.toFixed(2)}
                </span>
            </div>
            <div class="metric">
                <span class="metric-label">Win Rate</span>
                <span class="metric-value">${eodReport.win_rate.toFixed(1)}%</span>
            </div>
        `;

        // Monthly Report
        const monthlyContainer = document.getElementById('monthly-report');
        monthlyContainer.innerHTML = `
            <div class="metric">
                <span class="metric-label">Total Trades</span>
                <span class="metric-value">${monthlyReport.total_trades}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Win Rate</span>
                <span class="metric-value">${monthlyReport.win_rate.toFixed(1)}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Total P&L</span>
                <span class="metric-value ${monthlyReport.total_pnl >= 0 ? 'positive' : 'negative'}">
                    ₹${monthlyReport.total_pnl.toFixed(2)}
                </span>
            </div>
            <div class="metric">
                <span class="metric-label">Max Drawdown</span>
                <span class="metric-value negative">₹${monthlyReport.max_drawdown.toFixed(2)}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Winning Trades</span>
                <span class="metric-value positive">${monthlyReport.winning_trades}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Losing Trades</span>
                <span class="metric-value negative">${monthlyReport.losing_trades}</span>
            </div>
        `;
    }

    async generateSignals() {
        if (!confirm('Generate new trading signals? This may take a few minutes.')) {
            return;
        }

        this.showLoading(true);
        try {
            const result = await api.runSignalGeneration();
            this.showToast(
                `Generated ${result.candidates_found} signals, created ${result.trade_cards_created} trade cards`,
                'success'
            );
            if (this.currentTab === 'pending') {
                await this.loadPendingTradeCards();
            }
        } catch (error) {
            this.showToast('Signal generation failed: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    showLoading(show) {
        document.getElementById('loading-overlay').style.display = show ? 'flex' : 'none';
    }

    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type} show`;

        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }

    closeModal() {
        document.getElementById('trade-card-modal').classList.remove('show');
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new TradingApp();
});

