# Used Car Pricing – Cloud ML on GCP

A cloud-native microservice that predicts used-car prices with **BigQuery ML**, served via **Flask** on **Cloud Run**.  
This project was developed as a 10-week course capstone, covering data cleaning, model training, containerization, deployment, and reflection.

---

## Deployed Service URL
[Cloud Run Service](https://used-car-bqml-295289023086-295289023086.us-central1.run.app)
---

## Architecture
- **Data**: BigQuery table (cleaned vehicles dataset)
- **Model**: BigQuery ML AutoML Regressor  
  `used-car-pricing.used_car_dataset.used_car_model_automl`
- **API**: Flask app (`/health`, `/bq_test`, `/predict`, `/metrics`) deployed on Cloud Run
- **Observability**: Prometheus client metrics for request counts and latency

---

## Prerequisites
- Google Cloud project: `used-car-pricing`
- BigQuery dataset/table + a trained AutoML model
- `gcloud` CLI authenticated
- Cloud Run service account with roles:  
  - `roles/bigquery.user`  
  - `roles/bigquery.jobUser`  
  - `roles/bigquery.dataViewer`  

---

## Local Build & Deploy

```bash
# In repo root (where Dockerfile and app.py live)
export IMG=gcr.io/used-car-pricing/used-car-api:v$(date +%Y%m%d-%H%M%S)

# Build with Cloud Build
gcloud builds submit --tag $IMG .

# Deploy to Cloud Run
gcloud run deploy used-car-bqml-295289023086 \
  --image $IMG \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars MODEL_TABLE=used-car-pricing.used_car_dataset.used_car_model_automl
