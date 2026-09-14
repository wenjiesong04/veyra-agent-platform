from __future__ import annotations

import httpx
import pytest

from veyra_agent_platform.community.storage.s3_storage import (
    S3AvatarStorage,
    S3PackageStorage,
    S3StorageConfig,
    S3StorageError,
)


def _config() -> S3StorageConfig:
    return S3StorageConfig(
        endpoint_url="http://minio.example:9000",
        bucket="veyra-community",
        region="us-east-1",
        access_key_id="test-access",
        secret_access_key="test-secret",
        key_prefix="packages",
    )


def test_s3_package_storage_signs_path_style_requests_and_verifies_content_hash() -> (
    None
):
    content = b"package-bytes"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "PUT":
            return httpx.Response(200, request=request)
        return httpx.Response(200, content=content, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    storage = S3PackageStorage(_config(), http_client=client)

    storage_id = storage.put(content)
    assert storage.get(storage_id) == content
    assert [request.method for request in requests] == ["PUT", "GET"]
    assert requests[0].url.path == f"/veyra-community/packages/{storage_id}"
    authorization = requests[0].headers["authorization"]
    assert authorization.startswith("AWS4-HMAC-SHA256 Credential=test-access/")
    assert "test-secret" not in authorization


def test_s3_package_storage_rejects_corrupt_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"different", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    storage = S3PackageStorage(_config(), http_client=client)
    storage_id = storage.put(b"package")

    with pytest.raises(S3StorageError, match="hash verification") as error:
        storage.get(storage_id)

    assert error.value.code == "object_storage_corrupt"


def test_s3_package_storage_check_ready_probes_the_bucket_without_a_prefix() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    storage = S3PackageStorage(_config(), http_client=client)

    assert storage.check_ready() is True
    assert [request.method for request in requests] == ["HEAD"]
    assert requests[0].url.path == "/veyra-community"
    assert "packages" not in requests[0].url.path


@pytest.mark.parametrize("status_code", [403, 404, 500])
def test_s3_storage_check_ready_rejects_non_success_bucket_responses(
    status_code: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    storage = S3AvatarStorage(_config(), http_client=client)

    assert storage.check_ready() is False


def test_s3_storage_check_ready_rejects_transport_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("storage offline", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    storage = S3PackageStorage(_config(), http_client=client)

    assert storage.check_ready() is False
