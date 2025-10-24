# Portainer Deployment Guide for Synology

## 🐳 Deploying via Portainer Web UI

### Method 1: Import Docker Compose Stack

1. **Open Portainer** (usually at `http://your-synology-ip:9000`)

2. **Go to Stacks** → **Add Stack**

3. **Name your stack**: `option-data-collector`

4. **Choose deployment method**:

#### Option A: Git Repository (Recommended)
```
Repository URL: https://github.com/KoenM-bit/option-data-collector
Compose path: docker/docker-compose.dns-fix.yml
```

#### Option B: Upload/Paste Compose File
Copy the contents of `docker/docker-compose.dns-fix.yml` into the web editor.

### Method 2: Manual Container Creation

If stack deployment fails, create containers individually:

1. **Go to Containers** → **Add Container**

2. **Use these settings for each service**:

#### Option API Container:
```
Name: option-api
Image: Build from: /volume1/docker/option-data-collector/docker/Dockerfile.dns-fix
Network: host
Volumes:
  - /volume1/docker/option-data-collector:/app
Environment:
  - Copy from your .env file
Command: python app.py
Restart Policy: Unless stopped
```

## 🔧 Portainer-Specific Fixes

### DNS Configuration in Portainer:
1. **Container Settings** → **Network** → **DNS**
   - Primary DNS: `8.8.8.8`
   - Secondary DNS: `8.8.4.4`

2. **Extra Hosts** (Advanced):
   ```
   pypi.org:151.101.1.63
   pypi.python.org:151.101.1.63
   files.pythonhosted.org:151.101.1.63
   ```

### Build Context Issues:
- Portainer may have issues with build context paths
- If build fails, use pre-built images or SSH method instead

## 🚀 Quick Portainer Stack Template

Create a new stack with this compose content:

```yaml
version: '3.8'

services:
  option-api:
    build:
      context: .
      dockerfile: docker/Dockerfile.dns-fix
    container_name: option-api-portainer
    network_mode: host
    volumes:
      - /volume1/docker/option-data-collector:/app
    working_dir: /app
    dns:
      - 8.8.8.8
      - 8.8.4.4
    extra_hosts:
      - "pypi.org:151.101.1.63"
    command: python app.py
    restart: unless-stopped
    environment:
      - DB_HOST=${DB_HOST:-192.168.1.200}
      - DB_PORT=${DB_PORT:-3306}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_NAME=${DB_NAME:-options_db}

  option-scraper:
    build:
      context: .
      dockerfile: docker/Dockerfile.dns-fix
    container_name: option-scraper-portainer
    network_mode: host
    volumes:
      - /volume1/docker/option-data-collector:/app
    working_dir: /app
    dns:
      - 8.8.8.8
      - 8.8.4.4
    command: >
      sh -c "while true; do python options_collector.py; sleep ${SCRAPE_INTERVAL:-3600}; done"
    restart: unless-stopped
    environment:
      - DB_HOST=${DB_HOST:-192.168.1.200}
      - DB_PORT=${DB_PORT:-3306}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_NAME=${DB_NAME:-options_db}
      - SCRAPE_INTERVAL=${SCRAPE_INTERVAL:-3600}

  sentiment-tracker:
    build:
      context: .
      dockerfile: docker/Dockerfile.dns-fix
    container_name: sentiment-tracker-portainer
    network_mode: host
    volumes:
      - /volume1/docker/option-data-collector:/app
    working_dir: /app
    dns:
      - 8.8.8.8
      - 8.8.4.4
    command: python sentiment_analyzer.py
    restart: unless-stopped
    environment:
      - DB_HOST=${DB_HOST:-192.168.1.200}
      - DB_PORT=${DB_PORT:-3306}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_NAME=${DB_NAME:-options_db}

  daily-etl:
    build:
      context: .
      dockerfile: docker/Dockerfile.dns-fix
    container_name: daily-etl-portainer
    network_mode: host
    volumes:
      - /volume1/docker/option-data-collector:/app
    working_dir: /app
    dns:
      - 8.8.8.8
      - 8.8.4.4
    command: python daily_pipeline.py
    restart: unless-stopped
    environment:
      - DB_HOST=${DB_HOST:-192.168.1.200}
      - DB_PORT=${DB_PORT:-3306}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_NAME=${DB_NAME:-options_db}
```

## 🎯 Environment Variables in Portainer

Since Portainer doesn't always read `.env` files properly, set these manually:

```
DB_HOST=192.168.1.200
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=options_db
SCRAPE_INTERVAL=3600
ENVIRONMENT=production
```

## ⚠️ Common Portainer Issues

1. **Build Context**: Portainer may not find the Dockerfile correctly
   - Solution: Use SSH method for initial build, then manage via Portainer

2. **Volume Paths**: May need absolute paths
   - Use: `/volume1/docker/option-data-collector:/app`

3. **Network Issues**: Portainer's networking can differ from CLI
   - Use `network_mode: host` for simplicity

4. **Environment Files**: `.env` files may not be loaded
   - Set environment variables manually in Portainer UI

## 🔄 Recommended Hybrid Approach

1. **Initial deployment**: Use SSH + emergency-deploy.sh
2. **Management**: Use Portainer for start/stop/logs
3. **Updates**: Use SSH for builds, Portainer for operations

This gives you the best of both worlds! 🚀