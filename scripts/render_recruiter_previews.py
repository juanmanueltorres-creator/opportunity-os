from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.cv.models import CVDocumentModel
from app.cv.recruiter_models import RecruiterDocumentModel
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.recruiter_qa import RecruiterQualityQA
from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer

_FIXTURES = ("recruiter_software", "recruiter_tech_operations")


def _load_fixture(name: str) -> tuple[RecruiterDocumentModel, CVDocumentModel]:
    path = Path("tests/fixtures") / f"{name}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (
        RecruiterDocumentModel.model_validate(payload["recruiter_document"]),
        CVDocumentModel.model_validate(payload["source_document"]),
    )


def render_previews(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = load_recruiter_policy("config/recruiter_policy.yaml")
    renderer = RenderCVTypstRenderer()
    qa = RecruiterQualityQA()
    outputs: list[Path] = []

    for fixture_name in _FIXTURES:
        recruiter_document, source_document = _load_fixture(fixture_name)
        output_path = output_dir / f"{fixture_name}.pdf"
        render_result = renderer.render(
            recruiter_document=recruiter_document,
            source_document=source_document,
            output_path=output_path,
            policy=policy,
        )
        qa_result = qa.evaluate(
            render_result=render_result,
            recruiter_document=recruiter_document,
            source_document=source_document,
            policy=policy,
        )
        if not qa_result.valid:
            codes = ", ".join(issue.code for issue in qa_result.errors)
            raise RuntimeError(
                f"Recruiter preview {fixture_name} failed QA: {codes or 'unknown_error'}"
            )
        outputs.append(output_path)

    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render fictional recruiter PDFs for human visual inspection."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/ci/recruiter-preview"),
    )
    args = parser.parse_args()

    outputs = render_previews(args.output_dir)
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
