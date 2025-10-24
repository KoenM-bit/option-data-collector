# Professional Docker configuration for option-data-collector
FROM python:3.12-slim

# DNS configuration for Synology compatibility
ARG DNS_SERVER=8.8.8.8
RUN echo "nameserver $DNS_SERVER" > /etc/resolv.conf

# Set working directory
WORKDIR /app

# Install system dependencies and configure DNS
RUN apt-get update && apt-get install -y \
    dnsutils \
    iputils-ping \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Configure pip for better reliability on Synology
ENV PIP_DEFAULT_TIMEOUT=100
ENV PIP_RETRIES=10
ENV PIP_TRUSTED_HOST=pypi.org,pypi.python.org,files.pythonhosted.org

# Install dependencies with retry logic
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --timeout 300 -r requirements.txt

# Verify installation
RUN pip list

# Copy source code
COPY . .

# Set Python path to include src directory
ENV PYTHONPATH=/app:$PYTHONPATH

# Default command (can be overridden in docker-compose)
CMD ["python", "beursduivel.py"]