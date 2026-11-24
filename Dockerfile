FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10001 studio && useradd --uid 10001 --gid 10001 --create-home studio
COPY pyproject.toml README.md ./
COPY src ./src
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN python -m pip install '.[server,capture]' && python -m playwright install --with-deps chromium && mkdir -p /data/projects && chown -R studio:studio /data /opt/playwright
COPY --from=frontend /ui/dist /app/studio-ui
ENV STUDIO_UI_DIR=/app/studio-ui
USER studio
CMD ["uvicorn", "site_transfer.server.api:app", "--host", "0.0.0.0", "--port", "8080"]
