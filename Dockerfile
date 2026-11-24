FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10001 studio && useradd --uid 10001 --gid 10001 --create-home studio
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install '.[server]' && mkdir -p /data/projects && chown -R studio:studio /data
USER studio
CMD ["uvicorn", "site_transfer.server.api:app", "--host", "0.0.0.0", "--port", "8080"]
