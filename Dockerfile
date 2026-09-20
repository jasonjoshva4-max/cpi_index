# Dockerfile for APIx API and Scraper services
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition & project files
COPY . /app

RUN pip install --no-cache-dir -r - <<EOF
fastapi
uvicorn
sqlalchemy
psycopg2-binary
pydantic
httpx
playwright
pytest
pytest-asyncio
requests
numpy
EOF

# Install Playwright Chromium browser
RUN python -m playwright install chromium

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
