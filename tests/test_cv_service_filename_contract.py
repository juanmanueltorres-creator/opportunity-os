from __future__ import annotations

import inspect

from app.cv.service import CVPreparationService


def test_cv_preparation_service_uses_filename_builder_instead_of_generic_cv_pdf() -> None:
    source = inspect.getsource(CVPreparationService.prepare)

    assert "build_cv_filename" in source
    assert ' / "cv.pdf"' not in source
