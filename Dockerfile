FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
ENV PYTHONPATH=/app

RUN pip install --no-cache-dir 'psycopg[binary]==3.2.10'

COPY api/ ./api/
COPY fixtures/ ./fixtures/
COPY oracle/ ./oracle/
COPY seeds/ ./seeds/

EXPOSE 8000

CMD ["python", "api/server.py"]
