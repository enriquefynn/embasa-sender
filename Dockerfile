FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DB_PATH=/data/embasa.db
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sender ./sender

VOLUME /data
ENTRYPOINT ["python", "-m", "sender"]
CMD ["serve"]
