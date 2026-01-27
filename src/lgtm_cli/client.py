import base64
from urllib.parse import urlencode

import httpx

from .config import ServiceConfig


class LGTMClient:
    def __init__(self, config: ServiceConfig, timeout: float = 30.0):
        self.config = config
        self.base_url = config.url.rstrip("/")
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.config.username and self.config.token:
            credentials = f"{self.config.username}:{self.config.token}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        if self.config.headers:
            headers.update(self.config.headers)
        return headers

    def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, params=params, headers=self._get_headers())
            response.raise_for_status()
            return response.json()

    def post(self, path: str, data: dict | None = None, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, data=data, params=params, headers=self._get_headers())
            response.raise_for_status()
            return response.json()


class LokiClient(LGTMClient):
    def query(self, query: str, start: str, end: str, limit: int = 100, direction: str = "backward") -> dict:
        return self.get("/loki/api/v1/query_range", {
            "query": query,
            "start": start,
            "end": end,
            "limit": limit,
            "direction": direction,
        })

    def query_instant(self, query: str, time: str | None = None) -> dict:
        params = {"query": query}
        if time:
            params["time"] = time
        return self.get("/loki/api/v1/query", params)

    def labels(self, start: str | None = None, end: str | None = None) -> dict:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.get("/loki/api/v1/labels", params or None)

    def label_values(self, label: str, start: str | None = None, end: str | None = None) -> dict:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.get(f"/loki/api/v1/label/{label}/values", params or None)

    def series(self, match: list[str], start: str | None = None, end: str | None = None) -> dict:
        params = {"match[]": match}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.get("/loki/api/v1/series", params)


class PrometheusClient(LGTMClient):
    def query(self, query: str, time: str | None = None) -> dict:
        params = {"query": query}
        if time:
            params["time"] = time
        return self.get("/api/v1/query", params)

    def query_range(self, query: str, start: str, end: str, step: str = "60s") -> dict:
        return self.get("/api/v1/query_range", {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        })

    def labels(self, start: str | None = None, end: str | None = None) -> dict:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.get("/api/v1/labels", params or None)

    def label_values(self, label: str, start: str | None = None, end: str | None = None) -> dict:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.get(f"/api/v1/label/{label}/values", params or None)

    def series(self, match: list[str], start: str | None = None, end: str | None = None) -> dict:
        params = {"match[]": match}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.get("/api/v1/series", params)

    def metadata(self, metric: str | None = None) -> dict:
        params = {}
        if metric:
            params["metric"] = metric
        return self.get("/api/v1/metadata", params or None)


class TempoClient(LGTMClient):
    def trace(self, trace_id: str) -> dict:
        return self.get(f"/api/traces/{trace_id}")

    def search(
        self,
        query: str | None = None,
        start: str | None = None,
        end: str | None = None,
        min_duration: str | None = None,
        max_duration: str | None = None,
        limit: int = 20,
    ) -> dict:
        params = {"limit": limit}
        if query:
            params["q"] = query
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if min_duration:
            params["minDuration"] = min_duration
        if max_duration:
            params["maxDuration"] = max_duration
        return self.get("/api/search", params)

    def tags(self) -> dict:
        return self.get("/api/search/tags")

    def tag_values(self, tag: str) -> dict:
        return self.get(f"/api/search/tag/{tag}/values")
