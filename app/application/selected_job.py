"""Local radar inspection and guarded handoff to the existing CV pipeline.

No network requests, public exports, uploads or automatic submissions.
An existing private assessment is required; discovery scores are not CV evidence.
"""
import argparse
import json
from pathlib import Path

from app.application.prepare import _load_assessment, main as prepare


def select_job(feed: dict, job_id: str) -> dict:
    rows = [row for row in feed.get('atlas', []) if row.get('id') == job_id]
    if len(rows) != 1:
        raise ValueError('Expected exactly one matching radar job')
    return rows[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--assessment')
    parser.add_argument('--master-facts')
    parser.add_argument('--evidence-catalog')
    parser.add_argument('--output-root', default='artifacts/applications')
    args = parser.parse_args(argv)
    row = select_job(json.loads(Path(args.feed).read_text(encoding='utf-8')), args.job_id)
    fields = ('id', 'company', 'title', 'description', 'published_at',
              'last_verified_at', 'experience_required', 'technologies_required',
              'work_language', 'location', 'remote_mode', 'source_url', 'category')
    report = {
        key: ('No verificado' if row.get(key) in (None, '', 'UNKNOWN') else row[key])
        for key in fields
    }
    report['link_verification'] = 'No verificado'
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if not args.assessment:
        return 0
    if not args.master_facts or not args.evidence_catalog:
        parser.error('Generation requires private master facts and evidence catalog')
    assessment = _load_assessment(args.assessment)
    if (assessment.opportunity.id != row['id']
            or str(assessment.opportunity.source_url) != row.get('source_url')):
        parser.error('Assessment does not match selected radar job and source URL')
    output = Path(args.output_root).resolve()
    private_root = Path('artifacts/applications').resolve()
    if not output.is_relative_to(private_root):
        parser.error('CV output must remain under ignored artifacts/applications')
    return prepare([
        '--opportunity', args.assessment, '--master-facts', args.master_facts,
        '--evidence-catalog', args.evidence_catalog,
        '--recruiter-policy', 'config/recruiter_policy.yaml',
        '--output-root', str(output), '--language', 'es',
    ])


if __name__ == '__main__':
    raise SystemExit(main())
