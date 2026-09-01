from __future__ import annotations

from typing import Protocol

from app.process_email.models import ProcessClassification


class ProcessClassifier(Protocol):
    def classify(self, text: str) -> ProcessClassification: ...
