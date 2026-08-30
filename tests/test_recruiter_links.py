import pymupdf

from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.recruiter_models import RecruiterDocumentModel
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer


def _source_document() -> CVDocumentModel:
    claims = [
        CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Software Developer"),
        CVClaim(claim_id="fact:email", section="headline", kind="contact", text="alex@example.test"),
        CVClaim(claim_id="fact:github", section="links", kind="link", text="github.com/example"),
    ]
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map={
            claim.claim_id: ClaimProvenance(fact_ids=[claim.claim_id])
            for claim in claims
        },
    )


def _recruiter_document() -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email"],
        link_claim_ids=["fact:github"],
    )


def test_recruiter_pdf_contains_clickable_email_and_web_link(tmp_path):
    output = tmp_path / "clickable.pdf"
    RenderCVTypstRenderer().render(
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
        output_path=output,
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )

    document = pymupdf.open(output)
    try:
        uris = {
            link.get("uri")
            for page in document
            for link in page.get_links()
            if link.get("uri")
        }
    finally:
        document.close()

    assert "mailto:alex@example.test" in uris
    assert "https://github.com/example" in uris
