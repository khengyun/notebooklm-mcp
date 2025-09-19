from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from notebooklm_mcp.monitoring import metrics_collector
from notebooklm_mcp.security import APIKeyMiddleware


async def _ok_endpoint(_request):
    return JSONResponse({"status": "ok"})


def _build_app(**middleware_options):
    return Starlette(
        routes=[Route("/", _ok_endpoint)],
        middleware=[Middleware(APIKeyMiddleware, **middleware_options)],
    )


def test_api_key_middleware_rejects_missing_key():
    app = _build_app(api_keys={"secret"}, header="x-api-key", allow_bearer=True)
    client = TestClient(app)

    baseline_failures = metrics_collector.metrics.authentication_failures
    response = client.get("/")

    assert response.status_code == 401
    assert metrics_collector.metrics.authentication_failures == baseline_failures + 1

    metrics_collector.metrics.authentication_failures = baseline_failures


def test_api_key_middleware_accepts_header():
    app = _build_app(api_keys={"secret"}, header="x-api-key", allow_bearer=False)
    client = TestClient(app)

    response = client.get("/", headers={"x-api-key": "secret"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_key_middleware_accepts_bearer_token():
    app = _build_app(api_keys={"secret"}, header="x-api-key", allow_bearer=True)
    client = TestClient(app)

    response = client.get("/", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
