"""Project-scoped artifact upload and download."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Request, UploadFile, status
from fastapi.responses import Response

from veyra_agent_platform.local.api.projects.routes import _translate
from veyra_agent_platform.local.artifacts.media import MAX_ARTIFACT_UPLOAD_BYTES
from veyra_agent_platform.local.artifacts.service import ArtifactService
from veyra_agent_platform.local.projects.service import ProjectError


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects", tags=["artifacts"])

    @router.post("/{project_id}/artifacts", status_code=status.HTTP_201_CREATED)
    async def upload_artifact(
        project_id: str, request: Request, file: Annotated[UploadFile, File()]
    ) -> dict[str, Any]:
        try:
            contents = await file.read(MAX_ARTIFACT_UPLOAD_BYTES + 1)
            claimed = file.content_type
            filename = file.filename
        finally:
            await file.close()
        return _translate(
            lambda: _artifacts(request).upload(
                project_id,
                filename,
                contents,
                claimed_type=claimed,
            )
        )

    @router.get("/{project_id}/artifacts/{artifact_id}")
    def get_artifact(
        project_id: str, artifact_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _artifacts(request).get(project_id, artifact_id))

    @router.get("/{project_id}/artifacts/{artifact_id}/content")
    def download_artifact(
        project_id: str, artifact_id: str, request: Request
    ) -> Response:
        def load() -> tuple[Any, bytes]:
            return _artifacts(request).read_bytes(project_id, artifact_id)

        record, payload = _translate(load)
        filename = record.filename.replace('"', "")
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        }
        return Response(
            content=payload,
            media_type=record.media_type,
            headers=headers,
        )

    return router


def _artifacts(request: Request) -> ArtifactService:
    artifacts = getattr(request.app.state, "artifacts", None)
    if not isinstance(artifacts, ArtifactService):
        raise ProjectError("Artifact service is unavailable", "artifact_unavailable")
    return artifacts
