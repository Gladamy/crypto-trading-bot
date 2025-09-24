# Use Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY config.example.yaml ./config.yaml

# Create data directory
RUN mkdir -p data

# Expose port for API
EXPOSE 8000

# Default command
CMD ["python", "-m", "src.main", "run"]