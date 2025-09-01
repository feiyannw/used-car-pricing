# Used Car Pricing – Cloud ML on GCP

A cloud-native microservice that predicts used-car prices with BigQuery ML, served via Flask on Cloud Run.

## Architecture
- **Data**: BigQuery table (cleaned vehicles dataset)
- **Model**: BigQuery ML AutoML Regressor  
  `used-car-pricing.used_car_dataset.used_car_model_automl`
- **API**: Flask (`/health`, `/bq_test`, `/predict`, `/metrics`) on Cloud Run
- **Observability**: Prometheus client metrics

## Prerequisites
- Google Cloud project: `used-car-pricing`
- BigQuery dataset/table + a trained model (see SQL below)
- gcloud CLI authenticated

## Local Build & Deploy
```bash
# In repo root (where Dockerfile and app.py live)
export IMG=gcr.io/used-car-pricing/used-car-api:v$(date +%Y%m%d-%H%M%S)
gcloud builds submit --tag $IMG .

gcloud run deploy used-car-bqml-295289023086 \
  --image $IMG \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars MODEL_TABLE=used-car-pricing.used_car_dataset.used_car_model_automl
