#!/bin/bash

# Test DNS configuration in Docker build
echo "🧪 Testing Docker DNS configuration..."

# Test with a minimal Python container
cat > /tmp/test-dockerfile << 'EOF'
FROM python:3.12-slim

ARG DNS_SERVER=8.8.8.8
RUN echo "nameserver $DNS_SERVER" > /etc/resolv.conf && \
    echo "nameserver 8.8.4.4" >> /etc/resolv.conf

# Install system dependencies for DNS resolution
RUN apt-get update && apt-get install -y \
    dnsutils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Test DNS resolution
RUN nslookup pypi.org || true
RUN curl -I https://pypi.org/ || true

# Test pip install with DNS-friendly configuration
ENV PIP_DEFAULT_TIMEOUT=100
ENV PIP_RETRIES=3
ENV PIP_TIMEOUT=100
ENV PIP_TRUSTED_HOST=pypi.org
ENV PIP_TRUSTED_HOST=pypi.python.org
ENV PIP_TRUSTED_HOST=files.pythonhosted.org

# Install a simple package to test connectivity
RUN pip install --no-cache-dir requests

CMD ["python", "-c", "import requests; print('✅ DNS and pip working!')"]
EOF

echo "🐳 Building test container..."
docker build -t dns-test --build-arg DNS_SERVER=8.8.8.8 -f /tmp/test-dockerfile .

if [ $? -eq 0 ]; then
    echo "✅ DNS test build successful!"
    echo "🏃 Running test container..."
    docker run --rm --dns=8.8.8.8 --dns=8.8.4.4 dns-test
    
    if [ $? -eq 0 ]; then
        echo "✅ DNS configuration working correctly!"
    else
        echo "❌ DNS test failed during runtime"
        exit 1
    fi
else
    echo "❌ DNS test build failed"
    exit 1
fi

echo "🧹 Cleaning up..."
docker rmi dns-test 2>/dev/null || true
rm -f /tmp/test-dockerfile

echo "✅ DNS test completed successfully!"