#!/usr/bin/env python3
"""Translate an authenticated, current-commit Codex verdict into a required check."""
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

BOT = 'chatgpt-codex-connector[bot]'


def evaluate(head, reviews, comments, summaries=()):
    candidates = [r for r in reviews if r.get('user', {}).get('login') == BOT
                  and r.get('user', {}).get('type') == 'Bot'
                  and r.get('commit_id') == head]
    if candidates:
        latest = max(candidates, key=lambda review: review['id'])
        if latest.get('state') not in ('APPROVED', 'COMMENTED'):
            return False, 'Latest Codex review does not approve this commit.'
        if any(comment.get('pull_request_review_id') == latest['id'] for comment in comments):
            return False, 'Latest Codex review contains inline findings.'
        marker = re.search(r'^MuseStack-Review: APPROVE ([0-9a-f]{40})\s*$', latest.get('body') or '', re.M)
        if latest.get('state') == 'APPROVED' or (marker and marker.group(1) == head):
            return True, 'Official Codex explicitly approves the current commit.'
    # Native Codex posts a machine-readable summary even when it submits no
    # formal GitHub review. Accept its exact, completed no-findings verdict.
    native = [c for c in summaries if c.get('user', {}).get('login') == BOT
              and c.get('user', {}).get('type') == 'Bot'
              and '<!-- codex-pull-request-review-summary -->' in (c.get('body') or '')]
    if native:
        body = max(native, key=lambda comment: comment['id']).get('body') or ''
        marker = re.search(r'<!-- codex-review-state:v1 (.*?) -->', body, re.S)
        try:
            verdict = json.loads(marker.group(1))['code_review'] if marker else {}
        except (ValueError, KeyError, TypeError):
            verdict = {}
        if (isinstance(verdict, dict) and verdict.get('commit_sha') == head
                and verdict.get('status') == 'completed'
                and verdict.get('has_any_findings') is False
                and verdict.get('has_unresolved_findings') is False):
            return True, 'Official Codex completed review of this commit with no findings.'
    return False, 'Codex has not supplied an explicit current-commit approval.'


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid repository')
        self.root = 'https://api.github.com/repos/' + repository
        self.token = token

    def request(self, path, data=None, method=None):
        request = urllib.request.Request(self.root + path,
            data=None if data is None else json.dumps(data).encode(), method=method,
            headers={'Authorization': 'Bearer ' + self.token,
                     'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def pages(self, path):
        result = []
        for page in range(1, 11):
            items = self.request(path + f'?per_page=100&page={page}')
            result.extend(items)
            if len(items) < 100:
                return result
        raise ValueError('Review history exceeds the audited pagination limit')


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    number = (event.get('pull_request') or event.get('issue') or {}).get('number')
    if number is None:
        number = int(event.get('inputs', {}).get('pull_request', '0'))
    if type(number) is not int or number < 1:
        raise ValueError('A pull request number is required')
    repository = os.environ['GITHUB_REPOSITORY']
    api = GitHub(repository, os.environ['GH_TOKEN'])
    pr = api.request(f'/pulls/{number}')
    head = pr['head']['sha']
    check = api.request('/check-runs', {'name': 'OpenAI review gate', 'head_sha': head,
        'status': 'in_progress', 'output': {'title': 'Checking official Codex verdict',
        'summary': 'Only a fresh, explicit verdict from the official bot is accepted.'}})
    try:
        if pr['base']['ref'] != 'main' or pr['base']['repo']['full_name'] != repository:
            raise ValueError('Only pull requests into this repository main are supported')
        if pr['head']['repo']['full_name'] != repository:
            raise ValueError('Fork submissions require a maintainer branch before this gate can approve')
        reviews = api.pages(f'/pulls/{number}/reviews')
        comments = api.pages(f'/pulls/{number}/comments')
        summaries = api.pages(f'/issues/{number}/comments')
        approved, summary = evaluate(head, reviews, comments, summaries)
        if api.request(f'/pulls/{number}')['head']['sha'] != head:
            approved, summary = False, 'Head changed while reviewing; a new review is required.'
        api.request('/check-runs/' + str(check['id']), {'status': 'completed',
            'conclusion': 'success' if approved else 'action_required',
            'output': {'title': 'Codex approved' if approved else 'Codex approval required',
                       'summary': summary}}, method='PATCH')
        print(summary)
        return 0 if approved else 1
    except Exception:
        api.request('/check-runs/' + str(check['id']), {'status': 'completed',
            'conclusion': 'failure', 'output': {'title': 'Review verification failed',
            'summary': 'Unable to verify an explicit official review; merging remains blocked.'}}, method='PATCH')
        raise


if __name__ == '__main__':
    sys.exit(main())
