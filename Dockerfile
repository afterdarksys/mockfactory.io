FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including OCI CLI
RUN apt-get update && apt-get install -y \
    docker.io \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install OCI CLI
RUN curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh | bash -s -- --accept-all-defaults

# Add OCI CLI to PATH
ENV PATH="/root/bin:${PATH}"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create directory for OCI config
RUN mkdir -p /root/.oci

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
