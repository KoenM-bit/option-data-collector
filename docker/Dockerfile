# Professional Docker configuration for option-data-collector
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Verify installation
RUN pip list

# Copy source code
COPY . .

# Set Python path to include src directory
ENV PYTHONPATH=/app:$PYTHONPATH

# Default command (can be overridden in docker-compose)
CMD ["python", "beursduivel.py"]