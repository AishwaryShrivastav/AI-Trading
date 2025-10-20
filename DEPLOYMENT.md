# Deployment Guide

## Deployment Options

This guide covers deploying the AI Trading System to production environments.

## Option 1: Railway (Recommended for Quick Deploy)

### Prerequisites
- Railway account (railway.app)
- Git repository

### Steps

1. **Prepare for Railway**

Create `railway.json`:
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health"
  }
}
```

Create `Procfile`:
```
web: uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

2. **Deploy**

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Add environment variables
railway variables set UPSTOX_API_KEY=your_key
railway variables set UPSTOX_API_SECRET=your_secret
railway variables set OPENAI_API_KEY=your_key

# Deploy
railway up
```

## Option 2: Render

### Prerequisites
- Render account (render.com)

### Steps

1. **Create `render.yaml`**

```yaml
services:
  - type: web
    name: ai-trading-system
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        value: sqlite:///./trading.db
      - key: UPSTOX_API_KEY
        sync: false
      - key: UPSTOX_API_SECRET
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: ENVIRONMENT
        value: production
      - key: DEBUG
        value: false
```

2. **Deploy**
- Push code to GitHub
- Connect repository to Render
- Add environment variables in dashboard
- Deploy

## Option 3: DigitalOcean App Platform

### Steps

1. **Create `app.yaml`**

```yaml
name: ai-trading-system
services:
- name: web
  github:
    repo: your-username/AI-Investment
    branch: main
  build_command: pip install -r requirements.txt
  run_command: uvicorn backend.app.main:app --host 0.0.0.0 --port 8080
  http_port: 8080
  envs:
  - key: UPSTOX_API_KEY
    scope: RUN_TIME
  - key: UPSTOX_API_SECRET
    scope: RUN_TIME
  - key: OPENAI_API_KEY
    scope: RUN_TIME
```

2. **Deploy via CLI**

```bash
# Install doctl
# Follow: https://docs.digitalocean.com/reference/doctl/how-to/install/

# Authenticate
doctl auth init

# Create app
doctl apps create --spec app.yaml
```

## Option 4: Traditional VPS (DigitalOcean Droplet, AWS EC2, etc.)

### Prerequisites
- Ubuntu 22.04 LTS server
- Root or sudo access

### Setup Script

```bash
#!/bin/bash

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+
sudo apt install python3.10 python3.10-venv python3-pip -y

# Install nginx
sudo apt install nginx -y

# Install supervisor for process management
sudo apt install supervisor -y

# Clone repository
cd /var/www
sudo git clone https://github.com/your-username/AI-Investment.git
cd AI-Investment

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
sudo nano .env
# Add your environment variables

# Initialize database
python -c "from backend.app.database import init_db; init_db()"

# Create supervisor config
sudo cat > /etc/supervisor/conf.d/ai-trading.conf << EOF
[program:ai-trading]
directory=/var/www/AI-Investment
command=/var/www/AI-Investment/venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
autostart=true
autorestart=true
stderr_logfile=/var/log/ai-trading.err.log
stdout_logfile=/var/log/ai-trading.out.log
user=www-data
EOF

# Reload supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start ai-trading

# Configure nginx
sudo cat > /etc/nginx/sites-available/ai-trading << EOF
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/ai-trading /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Setup SSL with Let's Encrypt
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com

# Setup cron jobs for scheduled tasks
crontab -e
# Add:
# 15 9 * * 1-5 /var/www/AI-Investment/venv/bin/python /var/www/AI-Investment/scripts/signal_generator.py
# 0 16 * * 1-5 /var/www/AI-Investment/venv/bin/python /var/www/AI-Investment/scripts/eod_report.py
```

## Database Considerations

### For Production

**Option 1: PostgreSQL** (Recommended for production)

1. Update `requirements.txt`:
```
psycopg2-binary==2.9.9
```

2. Update `.env`:
```
DATABASE_URL=postgresql://user:password@localhost/trading_db
```

3. Update `backend/app/database.py`:
```python
# Remove SQLite-specific connect_args
engine = create_engine(settings.database_url)
```

**Option 2: MySQL**

1. Update `requirements.txt`:
```
pymysql==1.1.0
cryptography==41.0.7
```

2. Update `.env`:
```
DATABASE_URL=mysql+pymysql://user:password@localhost/trading_db
```

### SQLite in Production (Not Recommended)

If you must use SQLite in production:
- Enable WAL mode for better concurrency
- Use volume/persistent storage
- Regular backups with `sqlite3 trading.db .dump > backup.sql`

## Environment Variables

### Required
```bash
UPSTOX_API_KEY=your_key
UPSTOX_API_SECRET=your_secret
UPSTOX_REDIRECT_URI=https://your-domain.com/api/auth/upstox/callback
OPENAI_API_KEY=your_key
SECRET_KEY=generate-random-secret-key
```

### Optional
```bash
ENVIRONMENT=production
DEBUG=False
LOG_LEVEL=INFO
MAX_CAPITAL_RISK_PERCENT=2.0
MIN_LIQUIDITY_ADV=1000000
```

## Security Checklist

- [ ] Use HTTPS (SSL certificate)
- [ ] Set strong `SECRET_KEY`
- [ ] Enable firewall (allow only 80, 443, 22)
- [ ] Disable debug mode (`DEBUG=False`)
- [ ] Use environment variables for secrets
- [ ] Regular security updates
- [ ] Implement rate limiting
- [ ] Add user authentication for multi-user
- [ ] Regular database backups
- [ ] Monitor logs for suspicious activity

## Monitoring

### Application Monitoring

**Using Supervisor:**
```bash
# Check status
sudo supervisorctl status ai-trading

# View logs
sudo tail -f /var/log/ai-trading.out.log
sudo tail -f /var/log/ai-trading.err.log
```

**Application Logs:**
```bash
tail -f logs/trading.log
```

### Health Check Monitoring

Set up monitoring with:
- UptimeRobot (free)
- Pingdom
- StatusCake

Monitor endpoint: `https://your-domain.com/health`

## Backup Strategy

### Database Backups

**Automated backup script:**
```bash
#!/bin/bash
# backup_db.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backups/trading"

mkdir -p $BACKUP_DIR

# For SQLite
cp /var/www/AI-Investment/trading.db $BACKUP_DIR/trading_$DATE.db

# For PostgreSQL
# pg_dump trading_db > $BACKUP_DIR/trading_$DATE.sql

# Keep only last 30 days
find $BACKUP_DIR -name "trading_*.db" -mtime +30 -delete

echo "Backup completed: $DATE"
```

**Add to crontab:**
```bash
0 2 * * * /path/to/backup_db.sh
```

## Scaling Considerations

### Vertical Scaling
- Increase server resources (CPU, RAM)
- Optimize database queries
- Use connection pooling

### Horizontal Scaling
- Use PostgreSQL instead of SQLite
- Deploy multiple app instances
- Use load balancer (nginx, HAProxy)
- Shared database and Redis for state

### Background Jobs
- Use Celery with Redis for async tasks
- Separate worker processes for signal generation

## Performance Optimization

1. **Enable Gzip compression** in nginx
2. **Use CDN** for static assets
3. **Cache API responses** where appropriate
4. **Database indexing** on frequently queried fields
5. **Connection pooling** for database

## Troubleshooting

### Application won't start
```bash
# Check supervisor logs
sudo supervisorctl tail ai-trading stderr

# Check permissions
sudo chown -R www-data:www-data /var/www/AI-Investment
```

### Database locked errors (SQLite)
- Switch to PostgreSQL or MySQL
- Enable WAL mode: `PRAGMA journal_mode=WAL;`

### High memory usage
- Reduce number of workers
- Optimize signal generation (batch processing)
- Add memory limits in supervisor config

## Support

For deployment issues:
1. Check application logs: `logs/trading.log`
2. Check supervisor logs
3. Check nginx logs: `/var/log/nginx/error.log`
4. Review environment variables
5. Test health endpoint

---

**Production Checklist:**
- [ ] Environment variables configured
- [ ] HTTPS enabled
- [ ] Database production-ready
- [ ] Backups automated
- [ ] Monitoring enabled
- [ ] Logs configured
- [ ] Security hardened
- [ ] Scheduled jobs configured
- [ ] Health checks passing
- [ ] Documentation updated

