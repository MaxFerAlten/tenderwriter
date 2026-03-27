FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download it_core_news_lg \
    && apt-get purge -y build-essential gcc \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

CMD ["python", "-m", "run"]
