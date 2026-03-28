FROM python:3.11-slim

WORKDIR /app

ARG TORCH_VERSION=2.5.1
ARG TORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

# System dependencies for WeasyPrint and unstructured
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    libglib2.0-0 \
    poppler-utils \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Preinstall CPU-only PyTorch so sentence-transformers does not pull CUDA wheels.
RUN pip install --no-cache-dir \
    --index-url ${TORCH_CPU_INDEX_URL} \
    torch==${TORCH_VERSION}+cpu

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy application code
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "if [ \"$APP_DEBUG\" = \"true\" ]; then exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug; else exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info; fi"]
