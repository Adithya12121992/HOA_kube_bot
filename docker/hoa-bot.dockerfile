FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/services/chatbot/ ./src/services/chatbot/
COPY src/rag/ ./src/rag/
COPY src/config/ ./src/config/

EXPOSE 8000

CMD ["uvicorn", "src.services.chatbot.service:app", "--host", "0.0.0.0", "--port", "8000"]
