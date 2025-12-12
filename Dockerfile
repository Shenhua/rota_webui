# ========================================
# Rota Optimizer - Streamlit App
# ========================================
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies for OR-Tools and PDF generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libfreetype6-dev \
    libjpeg-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY src/ ./src/

# Copy data directory (for default team files, etc.)
COPY data/ ./data/

# Set PYTHONPATH so imports work correctly
ENV PYTHONPATH="/app/src:/app"

# Expose Streamlit default port
EXPOSE 8501

# Streamlit config: disable CORS for Docker, bind to all interfaces
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "app/streamlit_app.py"]
