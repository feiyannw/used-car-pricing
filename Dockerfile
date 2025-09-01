FROM python:3.11-slim

# Faster, cleaner installs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional but common)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

# MODEL_TABLE must be provided at deploy time
# ENV MODEL_TABLE=used-car-pricing.used_car_dataset.used_car_model_automl

EXPOSE 8080
CMD exec gunicorn --bind :8080 --workers 1 --threads 8 app:app
