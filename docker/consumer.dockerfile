FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (for OCR, PDF processing)
RUN apt-get update && apt-get install -y \
    tesseract-ocr libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/services/consumer/ ./src/services/consumer/
COPY src/rag/ ./src/rag/
COPY src/config/ ./src/config/

CMD ["python", "-m", "src.services.consumer.app"]
