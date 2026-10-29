import pytest
from app.application.selected_job import select_job


def test_selection_requires_exact_unique_id():
    row = {'id': 'real:1', 'title': 'Analista'}
    assert select_job({'atlas': [row]}, 'real:1') == row
    with pytest.raises(ValueError):
        select_job({'atlas': [row]}, 'missing')
    with pytest.raises(ValueError):
        select_job({'atlas': [row, row]}, 'real:1')
