import os
import json
import logging
from datetime import datetime, timezone
import requests
import azure.functions as func
from azure.storage.blob import BlobServiceClient

app = func.FunctionApp()

API_BASE_URL = os.getenv(
    "API_BASE_URL", "https://upload-data-hotel.duckdns.org"
).rstrip("/")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "").strip()
STORAGE_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "hotel-reviews-ingested"


def get_auth_headers() -> dict:
    if not API_AUTH_TOKEN:
        return {}
    return {
        "Authorization": f"Bearer {API_AUTH_TOKEN}",
        "X-API-Key": API_AUTH_TOKEN,
    }


def run_ingestion_pipeline() -> dict:
    """Tarik dataset dari FastAPI MinIO VPS ke Azure Blob Storage."""
    if not STORAGE_CONN_STR:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING belum diatur.")

    headers = get_auth_headers()
    response = requests.get(
        f"{API_BASE_URL}/api/uploads", headers=headers, timeout=30
    )
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, list):
        uploads = payload
    elif isinstance(payload, dict):
        uploads = (
            payload.get("items")
            or payload.get("uploads")
            or payload.get("data")
            or payload.get("results")
        )
    else:
        raise ValueError("Format respons daftar upload tidak didukung.")

    if uploads is None:
        raise ValueError("Respons API tidak berisi daftar upload.")
    if not isinstance(uploads, list):
        raise ValueError("Daftar upload dari API harus berupa array.")

    blob_service = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
    container_client = blob_service.get_container_client(CONTAINER_NAME)
    if not container_client.exists():
        container_client.create_container()

    batch_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ingested_files = []

    for idx, item in enumerate(uploads):
        if not isinstance(item, dict):
            raise ValueError(f"Metadata upload ke-{idx} harus berupa object.")
        upload_id = next(
            (
                item[key]
                for key in ("id", "upload_id", "file_id")
                if item.get(key) is not None
            ),
            None,
        )
        filename = (
            item.get("filename")
            or item.get("file_name")
            or item.get("name")
            or f"dataset_{upload_id or idx}.csv"
        )

        if upload_id is None:
            raise KeyError(
                f"Key ID tidak ditemukan di JSON: {list(item.keys())}"
            )

        download_url = f"{API_BASE_URL}/api/uploads/{upload_id}/download"
        file_resp = requests.get(
            download_url, headers=headers, timeout=60
        )
        file_resp.raise_for_status()

        blob_path = f"batch_{batch_ts}/{filename}"
        blob_client = container_client.get_blob_client(blob_path)
        blob_client.upload_blob(file_resp.content, overwrite=True)
        ingested_files.append(blob_path)

    return {
        "status": "success",
        "total_files": len(ingested_files),
        "files": ingested_files,
    }


@app.timer_trigger(
    schedule="0 0 */6 * * *", arg_name="myTimer", run_on_startup=False
)
def hotel_reviews_scheduler(myTimer: func.TimerRequest) -> None:
    logging.info("Memulai pipeline ingestion data Hotel Reviews...")
    result = run_ingestion_pipeline()
    logging.info(f"Ingestion selesai: {result}")


@app.route(route="trigger-ingestion", auth_level=func.AuthLevel.FUNCTION)
def manual_trigger_ingestion(req: func.HttpRequest) -> func.HttpResponse:
    try:
        result = run_ingestion_pipeline()
        return func.HttpResponse(
            json.dumps(result, indent=2),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logging.error(f"Pipeline ingestion gagal: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "detail": str(e)}, indent=2),
            mimetype="application/json",
            status_code=500,
        )