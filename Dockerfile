FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV TZ=Europe/Moscow DATA_PATH=/app/data/store.json
VOLUME ["/app/data"]
CMD ["python", "main.py"]
