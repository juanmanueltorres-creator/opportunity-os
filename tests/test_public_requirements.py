from app.radar.public_requirements import public_requirements


def test_requirements_are_plain_text_and_unknowns_explicit():
    result = public_requirements('<p>Python required</p><script>secret()</script>')
    assert result['description'] == 'Python required'
    assert result['experience_required'] == 'No verificado'
    assert result['last_verified_at'] == 'No verificado'


def test_empty_requirements_do_not_claim_verification():
    assert public_requirements('')['description'] == 'No verificado'
