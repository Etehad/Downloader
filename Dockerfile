FROM python:3.11-slim

# نصب ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 2
