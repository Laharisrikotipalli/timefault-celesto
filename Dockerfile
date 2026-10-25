FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-cloud.txt ./
RUN pip install --no-cache-dir --retries 5 --timeout 120 -r requirements-cloud.txt
COPY app.py ./
COPY agent/ ./agent/
COPY fixtures/ ./fixtures/
COPY oracle/ ./oracle/
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
