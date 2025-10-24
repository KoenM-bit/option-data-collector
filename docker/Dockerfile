# Professional Docker configuration for option-data-collector
FROM python:3.12-slim

# DNS configuration argument (used in docker-compose)
ARG DNS_SERVER=8.8.8.8

# Set working directory
WORKDIR /app

# Configure APT to use specific DNS and be more resilient on Synology
RUN echo "Acquire::http::Timeout \"30\";" >> /etc/apt/apt.conf.d/99timeout && \
    echo "Acquire::ftp::Timeout \"30\";" >> /etc/apt/apt.conf.d/99timeout && \
    echo "Acquire::Retries \"3\";" >> /etc/apt/apt.conf.d/99timeout

# Install system dependencies with timeout and retry for Synology compatibility
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

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