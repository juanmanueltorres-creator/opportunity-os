"""Public source text only; never mix candidate facts into vacancy exports."""
from html.parser import HTMLParser


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif not self.hidden:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden:
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def public_requirements(description: str) -> dict:
    parser = _Text()
    parser.feed(description or '')
    text = ' '.join(''.join(parser.parts).split())
    return {
        'description': text or 'No verificado',
        'experience_required': 'No verificado',
        'technologies_required': 'No verificado',
        'last_verified_at': 'No verificado',
    }
