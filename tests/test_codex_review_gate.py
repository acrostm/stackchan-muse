import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from tools.codex_review_gate import BOT, evaluate, main

HEAD = 'a' * 40


def summary(**changes):
    state = {'commit_sha': HEAD, 'status': 'completed',
             'has_any_findings': False, 'has_unresolved_findings': False}
    state.update(changes)
    return {'id': 10, 'user': {'login': BOT, 'type': 'Bot'}, 'body':
            '<!-- codex-pull-request-review-summary -->\n'
            '<!-- codex-review-state:v1 ' + json.dumps({'code_review': state}) + ' -->'}


class ReviewGateTests(unittest.TestCase):
    def test_only_exact_completed_clean_native_result_passes(self):
        self.assertTrue(evaluate(HEAD, [summary()])[0])
        for state in ({'commit_sha': 'b'*40}, {'status': 'running'},
                      {'has_any_findings': True}, {'has_unresolved_findings': True},
                      {'has_any_findings': None}, {'has_any_findings': 0}):
            self.assertFalse(evaluate(HEAD, [summary(**state)])[0])

    def test_impostors_and_generic_comments_cannot_approve(self):
        for user in ({'login': BOT, 'type': 'User'}, {'login': 'other', 'type': 'Bot'}):
            fake = summary()
            fake['user'] = user
            self.assertFalse(evaluate(HEAD, [fake])[0])
        for body in ('Looks good', 'MuseStack-Review: APPROVE ' + HEAD, 'thumbs up'):
            fake = summary()
            fake['body'] = body
            self.assertFalse(evaluate(HEAD, [fake])[0])
        self.assertFalse(evaluate(HEAD, [])[0])

    def test_formal_reviews_are_never_an_alternate_approval_source(self):
        for state in ('APPROVED', 'COMMENTED', 'CHANGES_REQUESTED', 'DISMISSED'):
            formal = {'id': 15, 'user': {'login': BOT, 'type': 'Bot'},
                      'commit_id': HEAD, 'state': state,
                      'body': 'MuseStack-Review: APPROVE ' + HEAD}
            self.assertFalse(evaluate(HEAD, [formal])[0])

    def test_latest_negative_pending_or_malformed_result_revokes_success(self):
        for state in ({'status': 'running'}, {'has_any_findings': True}):
            newer = summary(**state)
            newer['id'] = 11
            self.assertFalse(evaluate(HEAD, [summary(), newer])[0])
        malformed = summary()
        malformed['body'] = ('<!-- codex-pull-request-review-summary -->'
                             '<!-- codex-review-state:v1 INVALID -->')
        self.assertFalse(evaluate(HEAD, [malformed])[0])

    def test_api_failure_after_starting_check_cannot_publish_success(self):
        api = MagicMock()
        api.request.side_effect = [
            {'head': {'sha': HEAD, 'repo': {'full_name': 'owner/repo'}},
             'base': {'ref': 'main', 'repo': {'full_name': 'owner/repo'}}},
            {'id': 123}, {}]
        api.pages.side_effect = RuntimeError('API unavailable')
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / 'event.json'
            event.write_text(json.dumps({'issue': {'number': 3}}))
            with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event),
                                         'GITHUB_REPOSITORY': 'owner/repo', 'GH_TOKEN': 'test'}), \
                    patch('tools.codex_review_gate.GitHub', return_value=api):
                with self.assertRaises(RuntimeError):
                    main()
        self.assertEqual(api.request.call_args.args[1]['conclusion'], 'failure')
