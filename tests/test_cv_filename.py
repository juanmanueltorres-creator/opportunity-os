from app.cv.filename import build_cv_filename


def test_filename_is_professional_and_deterministic() -> None:
    filename = build_cv_filename(
        "Juan Manuel Torres",
        "Backend Engineer – Python, AWS & GenAI",
        "Scale Up Recruiting Partners",
    )

    assert filename.endswith(".pdf")
    assert filename.startswith("CV_Torres_Juan_Manuel_")
    assert "UPDATED" not in filename.upper()
    assert "FINAL" not in filename.upper()
    assert "/" not in filename and "\\" not in filename
    assert len(filename) <= 120
    assert filename == build_cv_filename(
        "Juan Manuel Torres",
        "Backend Engineer – Python, AWS & GenAI",
        "Scale Up Recruiting Partners",
    )


def test_filename_uses_recruiter_friendly_candidate_role_company_order() -> None:
    filename = build_cv_filename(
        "Juan Manuel Torres",
        "Backend Engineer",
        "Scale Up Recruiting Partners",
    )

    assert filename == "CV_Torres_Juan_Manuel_Backend_Engineer_Scale_Up_Recruiting_Partners.pdf"


def test_filename_normalizes_path_unsafe_characters() -> None:
    filename = build_cv_filename("A/B", "Dev: API", "ACME (LATAM)")

    assert filename == "CV_A_B_Dev_API_ACME_LATAM.pdf"


def test_filename_is_bounded_without_losing_pdf_extension() -> None:
    filename = build_cv_filename("Candidate", "R" * 200, "Company")

    assert len(filename) <= 120
    assert filename.endswith(".pdf")
