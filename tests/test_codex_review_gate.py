import unittest
import json
from tools.codex_review_gate import BOT, evaluate

HEAD = 'a' * 40


def review(**changes):
    result = {'id': 5, 'user': {'login': BOT, 'type': 'Bot'},
              'commit_id': HEAD, 'state': 'COMMENTED',
              'body': 'MuseStack-Review: APPROVE ' + HEAD}
    result.update(changes)
    return result


class ReviewGateTests(unittest.TestCase):
    def test_native_official_summary_requires_exact_completed_clean_verdict(self):
        def summary(**changes):
            state = {'commit_sha': HEAD, 'status': 'completed',
                     'has_any_findings': False, 'has_unresolved_findings': False}
            state.update(changes)
            return {'id': 10, 'user': {'login': BOT, 'type': 'Bot'}, 'body':
                    '<!-- codex-pull-request-review-summary -->\n'
                    '<!-- codex-review-state:v1 ' + json.dumps({'code_review': state}) + ' -->'}
        self.assertTrue(evaluate(HEAD, [], [], [summary()])[0])
        for state in ({'commit_sha': 'b'*40}, {'status': 'in_progress'},
                      {'has_any_findings': True}, {'has_unresolved_findings': True},
                      {'has_any_findings': None}, {'has_any_findings': 0}):
            self.assertFalse(evaluate(HEAD, [], [], [summary(**state)])[0])
        fake = summary()
        fake['user']['login'] = 'impostor'
        self.assertFalse(evaluate(HEAD, [], [], [fake])[0])
        newer = summary(status='in_progress')
        newer['id'] = 11
        self.assertFalse(evaluate(HEAD, [], [], [summary(), newer])[0])
        self.assertFalse(evaluate(HEAD, [review(state='CHANGES_REQUESTED')], [], [summary()])[0])

    def test_explicit_current_bot_verdict_passes(self):
        self.assertTrue(evaluate(HEAD, [review()], [])[0])
        self.assertTrue(evaluate(HEAD, [review(state='APPROVED', body='')], [])[0])

    def test_stale_fake_generic_or_rejected_review_does_not_pass(self):
        for item in (review(commit_id='b'*40),
                     review(user={'login': BOT, 'type': 'User'}),
                     review(user={'login': 'someone', 'type': 'Bot'}),
                     review(body='Looks good'), review(state='CHANGES_REQUESTED'),
                     review(state='DISMISSED'),
                     review(body='MuseStack-Review: APPROVE ' + 'b'*40)):
            with self.subTest(item=item):
                self.assertFalse(evaluate(HEAD, [item], [])[0])
        self.assertFalse(evaluate(HEAD, [], [])[0])

    def test_inline_findings_and_later_rejection_block(self):
        self.assertFalse(evaluate(HEAD, [review()], [{'pull_request_review_id': 5}])[0])
        self.assertFalse(evaluate(HEAD, [review(), review(id=6, state='CHANGES_REQUESTED')], [])[0])
