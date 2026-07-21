FROM python:3.12-slim

WORKDIR /app
COPY robotics_lab ./robotics_lab
COPY README.md ./README.md

RUN useradd --create-home appuser && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

ENV HOST=0.0.0.0 PORT=8080 DB_PATH=/app/data/fleet.db
EXPOSE 8080
VOLUME ["/app/data"]

CMD ["python", "-m", "robotics_lab.server"]
