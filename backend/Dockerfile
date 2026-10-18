FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TESSDATA_DIR=/app/models/tessdata
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./requirements.txt
COPY requirements-local-model.txt ./requirements-local-model.txt
ARG INSTALL_LOCAL_MODEL=false
RUN python -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_LOCAL_MODEL" = "true" ]; then pip install --no-cache-dir -r requirements-local-model.txt; fi
COPY models/tessdata/eng.traineddata /app/models/tessdata/eng.traineddata
COPY app ./app
RUN mkdir -p /app/storage/medical_records && useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
