"""Small AWS Signature V4 client for private S3-compatible Community objects."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx

_STORAGE_ID = re.compile(r"^[0-9a-f]{64}$")


class S3StorageError(RuntimeError):
    """A safe object-storage failure without provider response bodies."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class S3StorageConfig:
    """Connection metadata for one private S3-compatible bucket."""

    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    key_prefix: str = ""

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint_url.rstrip("/"))
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("S3 endpoint must be a plain HTTP(S) origin")
        if not self.bucket or "/" in self.bucket or "\\" in self.bucket:
            raise ValueError("S3 bucket is invalid")
        if not self.region or not self.access_key_id or not self.secret_access_key:
            raise ValueError("S3 region and credentials are required")


class _ObjectClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        headers: dict[str, str],
    ) -> httpx.Response: ...


class _S3ObjectClient:
    """Path-style, private-bucket S3 operations used by Community storage."""

    def __init__(
        self,
        config: S3StorageConfig,
        *,
        http_client: _ObjectClient | None = None,
    ) -> None:
        self.config = config
        self.endpoint_url = config.endpoint_url.rstrip("/")
        self.http_client = http_client or httpx.Client(
            timeout=30.0, follow_redirects=False
        )

    def put(self, key: str, content: bytes, content_type: str) -> None:
        response = self._request("PUT", key, content, content_type)
        if not 200 <= response.status_code < 300:
            raise S3StorageError(
                "object_storage_write_failed", "Object storage rejected the write"
            )

    def get(self, key: str) -> bytes | None:
        response = self._request("GET", key, None, None)
        if response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            raise S3StorageError(
                "object_storage_read_failed", "Object storage rejected the read"
            )
        return response.content

    def delete(self, key: str) -> None:
        response = self._request("DELETE", key, None, None)
        if response.status_code not in {200, 202, 204, 404}:
            raise S3StorageError(
                "object_storage_delete_failed",
                "Object storage rejected the delete",
            )

    def _request(
        self,
        method: str,
        key: str,
        content: bytes | None,
        content_type: str | None,
    ) -> httpx.Response:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload = content or b""
        payload_hash = hashlib.sha256(payload).hexdigest()
        parsed = urlsplit(self.endpoint_url)
        host = parsed.netloc
        canonical_uri = "/" + quote(
            f"{self.config.bucket}/{self._key(key)}", safe="/-_.~"
        )
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type:
            headers["content-type"] = content_type
        canonical_headers = "".join(
            f"{name}:{' '.join(value.strip().split())}\n"
            for name, value in sorted(headers.items())
        )
        signed_headers = ";".join(sorted(headers))
        canonical_request = "\n".join(
            (
                method,
                canonical_uri,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            )
        )
        scope = f"{date_stamp}/{self.config.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            (
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            )
        )
        signing_key = _signing_key(
            self.config.secret_access_key, date_stamp, self.config.region
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        request_headers = {
            **headers,
            "Authorization": (
                "AWS4-HMAC-SHA256 "
                f"Credential={self.config.access_key_id}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }
        try:
            return self.http_client.request(
                method,
                f"{self.endpoint_url}{canonical_uri}",
                content=content,
                headers=request_headers,
            )
        except httpx.TimeoutException as exc:
            raise S3StorageError(
                "object_storage_timeout", "Object storage request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise S3StorageError(
                "object_storage_unavailable", "Object storage is unavailable"
            ) from exc

    def _key(self, key: str) -> str:
        clean = key.strip("/")
        if not clean or "\\" in clean or any(
            part in {"", ".", ".."} for part in clean.split("/")
        ):
            raise S3StorageError(
                "object_storage_key_invalid", "Object key is invalid"
            )
        prefix = self.config.key_prefix.strip("/")
        return f"{prefix}/{clean}" if prefix else clean


class S3PackageStorage:
    """Content-addressed package storage with corruption detection on reads."""

    def __init__(
        self, config: S3StorageConfig, *, http_client: _ObjectClient | None = None
    ) -> None:
        self._objects = _S3ObjectClient(config, http_client=http_client)

    def put(self, content: bytes) -> str:
        storage_id = hashlib.sha256(content).hexdigest()
        self._objects.put(storage_id, content, "application/zip")
        return storage_id

    def get(self, storage_id: str) -> bytes | None:
        if not _STORAGE_ID.fullmatch(storage_id):
            return None
        content = self._objects.get(storage_id)
        if content is None:
            return None
        if hashlib.sha256(content).hexdigest() != storage_id:
            raise S3StorageError(
                "object_storage_corrupt",
                "Stored package content failed hash verification",
            )
        return content


class S3AvatarStorage:
    """Private avatar storage with non-content-addressed, deletable identifiers."""

    def __init__(
        self, config: S3StorageConfig, *, http_client: _ObjectClient | None = None
    ) -> None:
        self._objects = _S3ObjectClient(config, http_client=http_client)

    def put(self, content: bytes) -> str:
        storage_id = secrets.token_hex(32)
        self._objects.put(storage_id, content, "application/octet-stream")
        return storage_id

    def get(self, storage_id: str) -> bytes | None:
        if not _STORAGE_ID.fullmatch(storage_id):
            return None
        return self._objects.get(storage_id)

    def delete(self, storage_id: str) -> None:
        if not _STORAGE_ID.fullmatch(storage_id):
            return
        self._objects.delete(storage_id)


def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    date_key = hmac.new(
        f"AWS4{secret}".encode(), date_stamp.encode(), hashlib.sha256
    ).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()
