from app.cv.filename import build_cv_filename


def test_filename_is_professional_and_deterministic() -> None:
    filename = build_cv_filename(
        "Juan Manuel Torres",
        "Backend Engineer – Python, AWS & GenAI",
        "Scale Up Recruiting Partners",
    )

    assert filename.endswith(".pdf")
    assert "UPDATED" not in filename.upper()
    assert "FINAL" not in filename.upper()
    assert "/" not in filename and "\\" not in filename
    assert len(filename) <= 120
    assert filename == build_cv_filename(
        "Juan Manuel Torres",
        "Backend Engineer – Python, AWS & GenAI",
        "Scale Up Recruiting Partners",
    )


def test_filename_normalizes_path_unsafe_characters() -> None:
    filename = build_cv_filename("A/B", "Dev: API", "ACME (LATAM)")

    assert filename == "A_B_Dev_API_ACME_LATAM.pdf"


def test_filename_is_bounded_without_losing_pdf_extension() -> None:
    filename = build_cv_filename("Candidate", "R" * 200, "Company")

    assert len(filename) <= 120
    assert filename.endswith(".pdf")
