import os
import re
import time
import logging
import traceback
from typing import Any, Dict

from flask import Flask, request, jsonify, Response
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPIError, BadRequest
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)

# ---------------- Prometheus metrics ----------------
REQUEST_COUNTER = Counter(
    "request_count", "Total request count partitioned by HTTP status class", ["status_class", "route"]
)
REQUEST_LATENCY = Histogram(
    "request_latency_seconds", "Request latency in seconds", buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 5)
)

# ---------------- Flask app & config ----------------
app = Flask(__name__)
app.logger.setLevel(logging.INFO)

MODEL_TABLE = os.environ.get("MODEL_TABLE")  # e.g. used-car-pricing.used_car_dataset.used_car_model_automl
if not MODEL_TABLE:
    raise RuntimeError("Missing env var MODEL_TABLE, e.g. used-car-pricing.used_car_dataset.used_car_model_automl")

bq_client = bigquery.Client()

def _status_class(code: int) -> str:
    return f"{code // 100}xx"

def _get_any(payload: Dict[str, Any], *keys: str, required: bool = True, default=None):
    for k in keys:
        if k in payload and payload[k] is not None:
            return payload[k]
    if required:
        raise KeyError(f"Missing required field: one of {keys}")
    return default

def _norm_str(v: Any) -> str:
    return str(v).strip().lower()

def _norm_cyl(v: Any) -> str:
    if v is None:
        return "unknown"
    s = str(v).strip().lower()
    if isinstance(v, (int, float)) or re.fullmatch(r"\d+", s):
        return f"{int(float(v))} cylinders"
    m = re.match(r"(\d+)", s)
    if m:
        return f"{int(m.group(1))} cylinders"
    return s

# --------- Global error handler: return JSON & log traceback ---------
@app.errorhandler(Exception)
def handle_all_errors(e):
    app.logger.error("UNCAUGHT ERROR: %s\n%s", e, traceback.format_exc())
    REQUEST_COUNTER.labels(_status_class(500), "uncaught").inc()
    return jsonify({"error": "Internal error", "detail": str(e)}), 500

# ---------------- Routes ----------------
@app.route("/health", methods=["GET"])
def health():
    start = time.time()
    status = 200
    resp = jsonify({"ok": True, "model": MODEL_TABLE})
    REQUEST_COUNTER.labels(_status_class(status), "/health").inc()
    REQUEST_LATENCY.observe(time.time() - start)
    return resp, status

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True, "message": "pong"}), 200

@app.route("/bq_test", methods=["GET"])
def bq_test():
    """Minimal BQ check: verifies permission & connectivity quickly."""
    try:
        app.logger.info("Running BQ self-test SELECT 1")
        rows = list(bq_client.query("SELECT 1 AS ok").result())
        return jsonify({"ok": True, "row": dict(rows[0])}), 200
    except GoogleAPIError as e:
        app.logger.error("BQ TEST ERROR: %s\n%s", e, traceback.format_exc())
        return jsonify({"ok": False, "where": "bq_test", "detail": str(e)}), 500

@app.route("/predict", methods=["POST"])
def predict():
    start = time.time()
    route = "/predict"
    try:
        payload = request.get_json(force=True) or {}
        year = int(_get_any(payload, "year"))
        odometer = float(_get_any(payload, "odometer"))
        manufacturer = _norm_str(_get_any(payload, "manufacturer", "make"))
        model = _norm_str(_get_any(payload, "model"))
        condition = _norm_str(_get_any(payload, "condition"))
        cylinders = _norm_cyl(_get_any(payload, "cylinders", required=False))
        transmission = _norm_str(_get_any(payload, "transmission"))

        app.logger.info("Predict payload: %s", {
            "year": year, "manufacturer": manufacturer, "model": model,
            "condition": condition, "cylinders": cylinders,
            "odometer": odometer, "transmission": transmission
        })

    except Exception as e:
        status = 400
        REQUEST_COUNTER.labels(_status_class(status), route).inc()
        REQUEST_LATENCY.observe(time.time() - start)
        return jsonify({"error": "Invalid input", "detail": str(e)}), status

    query = f"""
    SELECT *
    FROM ML.PREDICT(
      MODEL `{MODEL_TABLE}`,
      (SELECT
        @year AS year,
        @manufacturer AS manufacturer,
        @model AS model,
        @condition AS condition,
        @cylinders AS cylinders,
        @odometer AS odometer,
        @transmission AS transmission
      )
    )
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("year", "INT64", year),
        bigquery.ScalarQueryParameter("manufacturer", "STRING", manufacturer),
        bigquery.ScalarQueryParameter("model", "STRING", model),
        bigquery.ScalarQueryParameter("condition", "STRING", condition),
        bigquery.ScalarQueryParameter("cylinders", "STRING", cylinders),
        bigquery.ScalarQueryParameter("odometer", "FLOAT64", odometer),
        bigquery.ScalarQueryParameter("transmission", "STRING", transmission),
    ])

    try:
        app.logger.info("Calling ML.PREDICT on model: %s", MODEL_TABLE)
        rows = list(bq_client.query(query, job_config=job_config).result())
        if not rows:
            raise RuntimeError("No rows returned from ML.PREDICT")

        row = dict(rows[0])
        pred = row.get("predicted_price") or row.get("predicted_value") or row.get("price")
        if pred is None:
            for v in row.values():
                try:
                    pred = float(v); break
                except Exception:
                    continue
        if pred is None:
            raise RuntimeError(f"Prediction column not found. keys={list(row.keys())}")

        status = 200
        resp = jsonify({
            "predicted_price": float(pred),
            "inputs": {
                "year": year, "manufacturer": manufacturer, "model": model,
                "condition": condition, "cylinders": cylinders,
                "odometer": odometer, "transmission": transmission
            },
            "raw": row
        })
    except BadRequest as e:
        app.logger.error("BQ BadRequest: %s\n%s", e, traceback.format_exc())
        status = 500
        resp = jsonify({"error": "BQ BadRequest", "detail": str(e)})
    except GoogleAPIError as e:
        app.logger.error("BQ GoogleAPIError: %s\n%s", e, traceback.format_exc())
        status = 500
        resp = jsonify({"error": "BQ GoogleAPIError", "detail": str(e)})
    except Exception as e:
        app.logger.error("Predict ERROR: %s\n%s", e, traceback.format_exc())
        status = 500
        resp = jsonify({"error": "Prediction failed", "detail": str(e)})

    REQUEST_COUNTER.labels(_status_class(status), route).inc()
    REQUEST_LATENCY.observe(time.time() - start)
    return resp, status

@app.route("/metrics", methods=["GET"])
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
