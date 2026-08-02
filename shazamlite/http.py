import csv
import io
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from .constants import EXTENSION_UA
from .errors import FailedDecodeJson, HTTPStatusError, MaxRetriesExceeded

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

DEFAULT_HEADERS = {
    "User-Agent": EXTENSION_UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
RETRYABLE_ERRORS = (urllib.error.URLError, ConnectionError, TimeoutError)


@dataclass
class Response:
    status_code: int
    body: bytes
    url: str

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            raise FailedDecodeJson(self.status_code, self.text, self.url)

    def csv(self) -> list:
        try:
            rows = list(
                csv.reader(io.StringIO(self.text), delimiter=",", skipinitialspace=True)
            )
        except Exception:
            raise FailedDecodeJson(self.status_code, self.text, self.url)
        rows = [row for row in rows if row and row[0].strip() != ""]
        return rows


def _build_url(url: str, params: Optional[Dict[str, Any]]) -> str:
    if not params:
        return url
    query = urllib.parse.urlencode(params)
    separator = "&" if "?" in url else "?"
    return url + separator + query


class HTTPClient:
    def __init__(
        self,
        timeout: float = 15.0,
        retries: int = 3,
        impersonate: bool = True,
        use_curl_cffi: Optional[bool] = None,
    ):
        self.timeout = timeout
        self.retries = max(1, retries)
        self.impersonate = impersonate
        self.use_curl_cffi = (
            bool(cffi_requests is not None) if use_curl_cffi is None else use_curl_cffi
        )
        self._session = None

    def _request_once(self, method, url, headers, data, json_body, timeout):
        if self.use_curl_cffi and cffi_requests is not None:
            if self._session is None:
                self._session = cffi_requests.Session(impersonate="chrome")
            request_headers = dict(headers)
            kwargs = dict(timeout=timeout, headers=request_headers)
            if json_body is not None:
                kwargs["json"] = json_body
            if data is not None:
                kwargs["data"] = data
            if self.impersonate:
                kwargs["impersonate"] = "chrome"
            response = self._session.request(method, url, **kwargs)
            return Response(response.status_code, response.content, url)

        request_headers = dict(headers)
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif data is not None:
            body = data if isinstance(data, bytes) else str(data).encode("utf-8")

        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return Response(response.status, response.read(), url)
        except urllib.error.HTTPError as error:
            return Response(error.code, error.read(), url)

    def request(
        self,
        method: str = "GET",
        url: str = "",
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data=None,
        json_body=None,
        response_format: str = "json",
        timeout: Optional[float] = None,
    ) -> Union[Response, Any]:
        full_url = _build_url(url, params)
        merged_headers = dict(DEFAULT_HEADERS)
        merged_headers.update(headers or {})

        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._request_once(
                    method, full_url, merged_headers, data, json_body, timeout or self.timeout
                )
                if response.status_code in RETRYABLE_STATUSES:
                    if attempt < self.retries:
                        self._backoff(attempt)
                        continue
                    raise HTTPStatusError(
                        response.status_code, response.text, response.url
                    )
                if not (200 <= response.status_code < 300):
                    raise HTTPStatusError(
                        response.status_code, response.text, response.url
                    )
                if response_format == "json":
                    return response.json()
                if response_format == "csv":
                    return response.csv()
                if response_format == "text":
                    if response.status_code < 200 or response.status_code >= 300:
                        raise HTTPStatusError(
                            response.status_code, response.text, response.url
                        )
                    return response.text
                return response
            except (FailedDecodeJson, HTTPStatusError):
                raise
            except RETRYABLE_ERRORS:
                if attempt >= self.retries:
                    raise MaxRetriesExceeded("all %d attempts failed for %s" % (self.retries, full_url))
                self._backoff(attempt)

        raise MaxRetriesExceeded("all %d attempts failed for %s" % (self.retries, full_url))

    def _backoff(self, attempt: int):
        delay = (0.5 * (2 ** (attempt - 1))) + random.uniform(0.0, 0.5)
        time.sleep(delay)


def fetch(**kwargs):
    return HTTPClient().request(**kwargs)
