FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .

COPY configs ./configs
COPY data/corpus ./data/corpus

RUN useradd --create-home copilot && chown -R copilot /app
USER copilot

ENV COPILOT_SETTINGS=/app/configs/settings.yaml
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "copilot.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
