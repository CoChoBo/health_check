FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000
ENV DB_PATH=/data/health_check.sqlite3

WORKDIR /app

COPY admin.html import_csv.py server.py README.md ./

RUN mkdir -p /data

EXPOSE 8000

CMD ["python", "server.py"]
