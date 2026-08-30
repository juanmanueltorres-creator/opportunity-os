from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.cv.models import CVDocumentModel
from app.cv.recruiter_models import RecruiterDocumentModel, RecruiterRenderResult
from app.cv.recruiter_policy import RecruiterPolicy


class RecruiterRenderer(Protocol):
    renderer_version: str

    def render(
        self,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        output_path: str | Path,
        policy: RecruiterPolicy,
    ) -> RecruiterRenderResult: ...
