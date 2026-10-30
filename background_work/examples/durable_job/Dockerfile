FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt requirements-brokers.txt ./
RUN pip install --no-cache-dir -r requirements-brokers.txt
COPY . .
CMD ["python", "main.py", "worker"]
