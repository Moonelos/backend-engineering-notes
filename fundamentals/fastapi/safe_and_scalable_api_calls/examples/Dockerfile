FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY bounded_calls.py safe_call_app.py ./
RUN useradd --uid 10001 --no-create-home appuser
USER 10001
EXPOSE 8000
CMD ["uvicorn", "safe_call_app:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "100", "--timeout-graceful-shutdown", "20"]
