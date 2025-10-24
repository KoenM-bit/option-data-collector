# Option Data Collector

Professional options data collection system for **Ahold Delhaize (AD.AS)** running on Synology NAS with Docker.

## 🎯 Overview

This project collects and analyzes options data from multiple Dutch financial sources:
- **Beursduivel.be**: Detailed options chain data with live pricing
- **FD.nl**: Market overview and individual option contracts  
- **Yahoo Finance**: Analyst sentiment and recommendations

## 📁 Project Structure

```
option-data-collector/
├── src/
│   ├── config/           # Environment & database configuration
│   ├── scrapers/         # Web scraping modules
│   ├── services/         # Business logic & data processing
│   └── utils/           # Helper functions & utilities
├── docker/              # Docker configurations
├── scripts/             # Development & deployment scripts
├── tests/              # Unit tests
├── .github/workflows/   # CI/CD pipeline
├── beursduivel.py      # Original scraper (maintained for compatibility)
├── sentiment_tracker.py # Original sentiment tracker (maintained)
├── new_beursduivel.py  # New structured entry point
└── new_sentiment_tracker.py # New structured entry point
```

## 🚀 Quick Start

### Local Development

1. **Start development environment:**
   ```bash
   ./scripts/dev.sh
   ```

2. **Test functionality:**
   ```bash
   ./scripts/test.sh
   ```

3. **View logs:**
   ```bash
   docker-compose -f docker/docker-compose.dev.yml logs -f
   ```

### Production Deployment

Your current Portainer setup works unchanged:

```yaml
# Your existing docker-compose.yml works as-is
# OR use the new structured version:

services:
  option-scraper:
    command: python new_beursduivel.py  # Uses new structure
    # OR: python beursduivel.py        # Uses original files
```

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `production` | Environment (development/production) |
| `DB_HOST` | `192.168.1.200` | Database host |
| `DB_USER` | `remoteuser` | Database user |
| `DB_PASS` | - | Database password |
| `SCRAPE_INTERVAL` | `3600` | Scraping interval (seconds) |
| `MARKET_OPEN` | `9` | Market open hour |
| `MARKET_CLOSE` | `17` | Market close hour |

### Development vs Production

**Development** (5-minute intervals, local MySQL):
```bash
ENV=development
DB_HOST=localhost
SCRAPE_INTERVAL=300
```

**Production** (1-hour intervals, your Synology MySQL):
```bash
ENV=production
DB_HOST=192.168.1.200
SCRAPE_INTERVAL=3600
```

## 📊 Data Sources & Services

### Option Scraper Service
- **Source**: Beursduivel.be
- **Data**: Options chain, strikes, expiries, bid/ask prices
- **Frequency**: Every hour during market hours (9:00-17:00 Amsterdam)
- **Tables**: `option_prices`

### Sentiment Tracker Service  
- **Source**: Yahoo Finance API
- **Data**: Analyst recommendations, price targets, sentiment scores
- **Frequency**: Once daily
- **Tables**: `sentiment_data`

## 🐳 Docker Services

### Current Setup (Unchanged)
Your existing Portainer configuration continues to work:

```yaml
option-scraper:
  command: python beursduivel.py     # Original implementation
  
sentiment-tracker:  
  command: python sentiment_tracker.py # Original implementation
```

### New Structured Setup (Optional)
```yaml
option-scraper:
  command: python new_beursduivel.py     # New structured implementation

sentiment-tracker:
  command: python new_sentiment_tracker.py # New structured implementation  
```

## 🔄 CI/CD Pipeline

### Automated Deployment

1. **Push to GitHub** triggers automated testing
2. **Tests pass** → builds Docker image  
3. **Deploys to Synology** via SSH
4. **Health checks** ensure successful deployment
5. **Automatic rollback** if deployment fails

### Manual Deployment
```bash
# Test locally first
./scripts/test.sh

# Deploy to Synology  
./scripts/deploy.sh
```

## 📈 Database Schema

### option_prices
```sql
CREATE TABLE option_prices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    issue_id VARCHAR(32),
    expiry VARCHAR(64), 
    type VARCHAR(10),        -- 'Call' or 'Put'
    strike VARCHAR(10),
    price DECIMAL(10,3),
    source VARCHAR(20),      -- 'LIVE', 'beursduivel'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### sentiment_data  
```sql
CREATE TABLE sentiment_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(32),
    rating_avg FLOAT,
    rating_label VARCHAR(32),
    target_avg FLOAT,
    target_high FLOAT, 
    target_low FLOAT,
    sentiment_score FLOAT,
    buy_count INT,
    hold_count INT,
    sell_count INT,
    months_considered INT,
    trend_json JSON,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 🛡️ Compatibility Promise

**✅ Zero Breaking Changes**: Your existing setup continues to work unchanged

- Original files (`beursduivel.py`, `sentiment_tracker.py`) preserved
- Same database connections and queries
- Identical Docker behavior and timing  
- Same Portainer configuration

**✅ Progressive Migration**: Use new features when ready

- Switch containers individually: `python new_beursduivel.py`
- Test locally first with development environment
- Rollback instantly if needed

## 🔧 Troubleshooting

### Development Issues
```bash
# Check container status
docker-compose -f docker/docker-compose.dev.yml ps

# View logs
docker-compose -f docker/docker-compose.dev.yml logs option-scraper

# Restart services
docker-compose -f docker/docker-compose.dev.yml restart
```

### Production Issues  
```bash
# SSH to Synology
ssh your-synology-ip

# Check containers
cd /volume1/docker/option-api
docker-compose ps

# View logs  
docker-compose logs --tail=50 option-scraper
```

## 📝 Migration Path

1. **Phase 1**: Keep existing setup running (zero risk)
2. **Phase 2**: Test new structure locally with `./scripts/dev.sh`
3. **Phase 3**: Gradually switch containers to use `new_*.py` files
4. **Phase 4**: Enable CI/CD pipeline for automated deployments

Your **current working system remains untouched** while you gain access to professional DevOps practices.

## 🤝 Support

- **Original functionality**: Preserved exactly as-is
- **New features**: Professional structure + CI/CD 
- **Migration**: Risk-free, reversible, gradual