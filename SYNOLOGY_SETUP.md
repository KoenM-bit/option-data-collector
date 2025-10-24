# 🚀 Synology Deployment Setup Guide

This guide helps you set up automated deployment from GitHub to your Synology NAS.

## 🔧 1. Synology SSH Setup

### Enable SSH on Synology
1. Open **Control Panel** → **Terminal & SNMP**
2. Check **Enable SSH service**
3. Set port to `22` (default) or custom port
4. Apply settings

### Create SSH Key for GitHub Actions
SSH into your Synology and create a deployment key:

```bash
# SSH into your Synology
ssh your-username@192.168.1.200

# Create SSH key for GitHub deployment
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy
cd ~/.ssh

# Add the public key to authorized_keys
cat github_deploy.pub >> authorized_keys

# Set proper permissions
chmod 600 authorized_keys github_deploy
chmod 644 github_deploy.pub

# Display the private key (copy this for GitHub secrets)
echo "=== PRIVATE KEY (copy for GitHub secrets) ==="
cat github_deploy
echo "=== END PRIVATE KEY ==="

# Display the public key (for verification)
echo "=== PUBLIC KEY (for reference) ==="
cat github_deploy.pub
echo "=== END PUBLIC KEY ==="
```

## 🔐 2. GitHub Secrets Setup

Go to your GitHub repository: **Settings** → **Secrets and variables** → **Actions**

Add these **Repository secrets**:

| Secret Name | Description | Example Value |
|------------|-------------|---------------|
| `SYNOLOGY_HOST` | Your Synology IP address | `192.168.1.200` |
| `SYNOLOGY_USER` | Your SSH username | `your-username` |
| `SYNOLOGY_SSH_KEY` | Private key from step above | `-----BEGIN OPENSSH PRIVATE KEY-----\n...` |
| `SYNOLOGY_SSH_PORT` | SSH port (optional) | `22` |

### Setting up the SSH Private Key
1. Copy the **entire** private key output from the SSH setup step
2. In GitHub Secrets, paste it exactly as-is (including the header and footer lines)
3. Make sure there are no extra spaces or line breaks

## 📁 3. Synology Directory Structure

The deployment will create this structure on your Synology:

```
/volume1/docker/option-data-collector/
├── .env                          # Production environment config
├── .git/                         # Git repository
├── backup/                       # Automatic backups
├── docker/
│   └── docker-compose.prod.yml   # Production Docker setup
├── src/                          # Application source code
├── scripts/                      # Deployment scripts
└── ...                          # All project files
```

## 🐳 4. Docker Setup on Synology

### Install Docker (if not already installed)
1. Open **Package Center**
2. Search for "Docker" 
3. Install **Docker** package
4. Install **Container Manager** (if available)

### Verify Docker is working
```bash
ssh your-username@192.168.1.200
docker --version
docker compose version
```

## ⚙️ 5. Environment Configuration

The deployment will create a `.env` file from `.env.example`. You'll need to configure it:

```bash
# SSH into your Synology after first deployment
ssh your-username@192.168.1.200
cd /volume1/docker/option-data-collector

# Edit the environment file
nano .env
```

Configure these important settings:
```bash
# Database Configuration (Your Synology MySQL/MariaDB)
DB_HOST=192.168.1.200
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_secure_password
DB_NAME=options_db

# Application Settings
ENVIRONMENT=production
FLASK_ENV=production
DEBUG=false

# Market Hours (Amsterdam timezone)
MARKET_OPEN_HOUR=9
MARKET_CLOSE_HOUR=17
SCRAPE_INTERVAL=300
```

## 🚀 6. First Deployment Test

### Manual Test (Optional)
```bash
# SSH to your Synology
ssh your-username@192.168.1.200

# Create the project directory
mkdir -p /volume1/docker/option-data-collector
cd /volume1/docker/option-data-collector

# Clone your repository
git clone https://github.com/KoenM-bit/option-data-collector.git .

# Copy environment file
cp .env.example .env
# Edit .env with your production settings
nano .env

# Test Docker build
sudo docker-compose -f docker/docker-compose.prod.yml build
sudo docker-compose -f docker/docker-compose.prod.yml up -d

# Check status
sudo docker-compose -f docker/docker-compose.prod.yml ps
```

### Trigger Automatic Deployment
1. Make any commit to the `main` branch
2. Push to GitHub
3. Check **Actions** tab in GitHub
4. Watch the CI and deployment workflows

## 📊 7. Monitoring Deployment

### GitHub Actions
- Go to **Actions** tab in your GitHub repository
- Watch both "Code Quality & Testing" and "Deploy to Synology" workflows
- Green checkmarks = successful deployment

### Synology Monitoring
```bash
# SSH to your Synology
ssh your-username@192.168.1.200
cd /volume1/docker/option-data-collector

# Check container status
sudo docker-compose -f docker/docker-compose.prod.yml ps

# View logs
sudo docker-compose -f docker/docker-compose.prod.yml logs -f

# Check recent deployments
ls -la backup*/  # View backups from deployments
```

## 🔧 8. Troubleshooting

### SSH Connection Issues
```bash
# Test SSH connection manually
ssh -i ~/.ssh/github_deploy your-username@192.168.1.200

# Check SSH service on Synology
sudo systemctl status ssh
```

### Docker Issues
```bash
# Check Docker daemon
docker info

# Restart Docker (if needed)
sudo systemctl restart docker
```

### Deployment Rollback
If deployment fails, the system automatically rolls back to the previous version:
```bash
# Manual rollback (if needed)
cd /volume1/docker/option-data-collector
sudo docker-compose -f docker/docker-compose.prod.yml down

# Restore from backup
cp -r backup/* .
sudo docker-compose -f docker/docker-compose.prod.yml up -d
```

## 🎯 9. Testing the Setup

1. **Make a small change** to your code
2. **Commit and push** to the main branch:
   ```bash
   git add .
   git commit -m "Test deployment"
   git push
   ```
3. **Watch GitHub Actions** for the deployment
4. **Verify on Synology** that the update was deployed

## ✅ 10. Success Indicators

Your setup is working correctly when:
- ✅ GitHub Actions shows green checkmarks for both CI and Deploy workflows
- ✅ SSH connection from GitHub Actions succeeds
- ✅ Docker containers are running on Synology
- ✅ Your application is accessible at `http://192.168.1.200`
- ✅ Logs show no errors in the containers

## 🔧 11. Troubleshooting Common Issues

### Docker Build Hanging on pip install
```bash
# Test DNS resolution on Synology
ssh your-user@synology-ip "docker run --rm alpine nslookup pypi.org"

# If DNS fails, update Synology network settings:
# Control Panel > Network > General > DNS Server
# Set Primary: 8.8.8.8, Secondary: 8.8.4.4
```

### "Temporary failure in name resolution" Error
```bash
# Run our DNS test script locally
./scripts/test-dns-docker.sh

# If test fails, check Synology Docker daemon DNS:
# Docker > Settings > Advanced > DNS Server: 8.8.8.8
```

### Database Connection Issues
```bash
# Test MySQL connectivity from Synology
ssh your-user@synology-ip "docker run --rm mysql:8.0 mysql -h 192.168.1.200 -u option_user -p -e 'SELECT 1'"
```

### Permission Issues with Volumes
```bash
# Fix volume permissions
ssh your-user@synology-ip "sudo chown -R 1001:1001 /volume1/docker/option-data-collector"
```

### Services Not Starting
```bash
# Check detailed logs
ssh your-user@synology-ip "cd /volume1/docker/option-data-collector && sudo docker-compose -f docker/docker-compose.prod.yml logs"
```

### DNS Configuration Checklist
- [ ] Synology Network DNS set to 8.8.8.8, 8.8.4.4
- [ ] Docker daemon DNS configured in Synology Docker app
- [ ] Docker compose files include DNS servers
- [ ] Dockerfile includes DNS build args
- [ ] Test script passes: `./scripts/test-dns-docker.sh`

## 🆘 12. Getting Help

If you still encounter issues:
1. Check the **GitHub Actions logs** for detailed error messages
2. SSH to your Synology and check **Docker logs**:
   ```bash
   sudo docker-compose -f docker/docker-compose.prod.yml logs --tail=100
   ```
3. Verify all **GitHub Secrets** are set correctly
4. Ensure **SSH key permissions** are correct (600 for private key)
5. Check **Synology firewall** settings allow SSH connections

---

🎉 **Once setup is complete, every push to the main branch will automatically deploy to your Synology!**