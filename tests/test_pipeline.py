from types import SimpleNamespace

import pytest

import function_app


class FakeResponse:
    def __init__(self, payload=None, content=b""):
        self.payload = payload
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_run_ingestion_pipeline_uploads_downloaded_csv(monkeypatch):
    requests = SimpleNamespace(
        get=lambda url, headers, timeout: (
            FakeResponse({"items": [{"id": 7, "filename": "reviews.csv"}]})
            if url.endswith("/api/uploads")
            else FakeResponse(content=b"hotel,reviews\nA,Great")
        )
    )
    uploaded_blobs = []
    blob_client = SimpleNamespace(
        upload_blob=lambda data, overwrite: uploaded_blobs.append(
            (data, overwrite)
        )
    )
    container_client = SimpleNamespace(
        exists=lambda: True,
        get_blob_client=lambda name: (
            uploaded_blobs.append(("name", name)) or blob_client
        ),
    )
    blob_service = SimpleNamespace(
        get_container_client=lambda name: container_client
    )
    monkeypatch.setattr(function_app, "requests", requests)
    monkeypatch.setattr(
        function_app.BlobServiceClient,
        "from_connection_string",
        lambda connection_string: blob_service,
    )
    monkeypatch.setattr(function_app, "API_BASE_URL", "https://example.test")
    monkeypatch.setattr(function_app, "API_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(function_app, "STORAGE_CONN_STR", "test-connection")

    result = function_app.run_ingestion_pipeline()

    assert result["status"] == "success"
    assert result["total_files"] == 1
    assert result["files"][0].endswith("/reviews.csv")
    assert uploaded_blobs == [
        ("name", result["files"][0]),
        (b"hotel,reviews\nA,Great", True),
    ]


def test_run_ingestion_pipeline_requires_storage_connection(monkeypatch):
    monkeypatch.setattr(function_app, "STORAGE_CONN_STR", None)

    with pytest.raises(ValueError, match="AZURE_STORAGE_CONNECTION_STRING"):
        function_app.run_ingestion_pipeline()


@pytest.mark.parametrize(
    ("payload", "error_message"),
    [
        ({"unexpected": []}, "Respons API tidak berisi daftar upload"),
        ("not-an-object", "Format respons daftar upload"),
    ],
)
def test_run_ingestion_pipeline_rejects_unsupported_api_response(
    monkeypatch, payload, error_message
):
    monkeypatch.setattr(function_app, "STORAGE_CONN_STR", "test-connection")
    monkeypatch.setattr(
        function_app,
        "requests",
        SimpleNamespace(
            get=lambda *args, **kwargs: FakeResponse(payload=payload)
        ),
    )

    with pytest.raises(ValueError, match=error_message):
        function_app.run_ingestion_pipeline()