FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# CPU-only torch first, so sentence-transformers' dependency resolution sees
# it already satisfied and doesn't pull the default CUDA-enabled build
# (which drags in nvidia-* packages we never use - no GPU in this container -
# and inflates the image from ~1-2GB to ~9GB).
RUN pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/services/chatbot/ ./src/services/chatbot/
COPY src/rag/ ./src/rag/
COPY src/config/ ./src/config/

EXPOSE 8000

CMD ["uvicorn", "src.services.chatbot.service:app", "--host", "0.0.0.0", "--port", "8000"]
