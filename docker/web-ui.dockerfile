FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/services/web_ui/ ./src/services/web_ui/
COPY src/config/ ./src/config/

EXPOSE 5000

CMD ["python", "-m", "src.services.web_ui.app"]
