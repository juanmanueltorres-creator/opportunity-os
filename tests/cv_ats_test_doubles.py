from __future__ import annotations

from app.cv.ats.models import ATSRoundTripQAResult, ParsedResume


class PassingATSParser:
    parser_version = "fixture-parser-v1"

    def parse(self, pdf_path):
        return ParsedResume(
            parser_version=self.parser_version,
            extracted_text="fictional ATS parser fixture",
        )


class PassingATSQA:
    def evaluate(self, *, recruiter_document, source_document, parsed_resume, policy):
        return ATSRoundTripQAResult(
            valid=True,
            parser_version=parsed_resume.parser_version,
            policy_version=policy.version,
            categories={},
            aggregate_recovery_ratio=1.0,
        )
