import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app as module
from renewal import renewal_occurrences


class RenewalScheduleTest(unittest.TestCase):
    def test_korea_time_and_overnight_maintenance_gap(self):
        card = {'eo': 0, 'min': 10, 'sec': 0}
        # 02:30 KST: the next even renewal is 08:10, skipping maintenance hours.
        now = datetime(2026, 9, 29, 17, 30, tzinfo=timezone.utc)
        previous, upcoming = renewal_occurrences(card, now)
        self.assertEqual(previous, datetime(2026, 9, 29, 17, 10, tzinfo=timezone.utc))
        self.assertEqual(upcoming, datetime(2026, 9, 29, 23, 10, tzinfo=timezone.utc))

    def test_exact_second_is_previous_and_next_day_is_supported(self):
        now = datetime(2026, 9, 30, 14, 49, 40, tzinfo=timezone.utc)
        previous, upcoming = renewal_occurrences({'eo': 1, 'min': 49, 'sec': 40}, now)
        self.assertEqual(previous, now)
        self.assertEqual(upcoming - previous, timedelta(hours=2))


class AdminWorkspaceRenewalTest(unittest.TestCase):
    def setUp(self):
        if not os.environ.get('FIMOBOOK_DATABASE_PATH', '').startswith('/tmp/fimobook-workspace-test'):
            self.skipTest('Run against an isolated /tmp/fimobook-workspace-test database')
        self.old_csrf = module.app.config['WTF_CSRF_ENABLED']
        module.app.config['WTF_CSRF_ENABLED'] = False
        self.client = module.app.test_client()
        with module.app.app_context():
            module.db.create_all()
            token = uuid.uuid4().hex
            user = module.User(username='workspace-' + token, email=token + '@example.test', is_admin=True,
                               email_verified=True)
            module.db.session.add(user); module.db.session.commit(); self.uid = user.id
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.uid); session['_fresh'] = True

    def tearDown(self):
        if hasattr(self, 'uid'):
            with module.app.app_context():
                module.RenewalInterest.query.filter_by(user_id=self.uid).delete()
                module.Notification.query.filter_by(user_id=self.uid).delete()
                module.db.session.delete(module.db.session.get(module.User, self.uid)); module.db.session.commit()
            module.app.config['WTF_CSRF_ENABLED'] = self.old_csrf

    def test_admin_login_unlocks_both_workspaces(self):
        self.assertEqual(self.client.get('/admin').status_code, 200)
        response = self.client.get('/secret/player-review-summary')
        self.assertIn('요약 리뷰 빠른 등록', response.text)
        self.assertNotIn('id="admin-password"', response.text)
        self.assertEqual(self.client.get('/admin/points').status_code, 200)

    def test_real_password_login_reaches_admin_workspace(self):
        with module.app.app_context():
            user = module.db.session.get(module.User, self.uid)
            user.set_password('workspace-login-test'); email = user.email
            module.db.session.commit()
        client = module.app.test_client()
        response = client.post('/login?next=/admin', data={'email':email, 'password':'workspace-login-test'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/admin'))
        self.assertEqual(client.get('/admin').status_code, 200)

    def test_plain_summary_and_empty_protection(self):
        player = {'cid': 22901978, 'playerKor': '테스트 선수'}
        with patch.object(module, '_resolve_admin_summary_player', return_value=player), patch.object(module, '_store_player_review_summary') as store:
            response = self.client.post('/secret/player-review-summary', data={'action':'quick_save', 'player_reference':'22901978', 'summary':'추천합니다', 'strengths':'속도'})
            self.assertEqual(response.status_code, 302)
            store.assert_called_once_with(player, summary_text='추천합니다', strengths='속도', weaknesses='')
            store.reset_mock()
            self.client.post('/secret/player-review-summary', data={'action':'quick_save', 'player_reference':'22901978'})
            store.assert_not_called()

    def test_quick_save_persists_real_summary_without_mocking_store(self):
        path = '/tmp/fimobook-workspace-test-summary-' + uuid.uuid4().hex + '.json'
        try:
            with patch.object(module, 'PLAYER_REVIEW_SUMMARY_PATH', path):
                response = self.client.post('/secret/player-review-summary', data={
                    'action':'quick_save', 'player_reference':'22901950', 'summary':'실제 저장 검증', 'strengths':'속도'})
                self.assertEqual(response.status_code, 302)
                self.assertIn('draft_saved=1', response.headers['Location'])
                self.assertEqual(module._get_player_review_summary(22901950)['summary'], '실제 저장 검증')
                response = self.client.post('/secret/player-review-summary', data={
                    'action':'quick_save', 'player_reference':'22901950',
                    'review_summary_json':'{"pros":["체감"],"cons":["수비"],"final_verdict":"JSON 실제 저장"}'})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(module._get_player_review_summary(22901950)['summary'], 'JSON 실제 저장')
        finally:
            if os.path.exists(path): os.unlink(path)

    def test_interest_is_account_scoped_and_repeatable(self):
        card = next(c for c in module._load_renewal_cards() if c.get('available'))
        for _ in range(2):
            response = self.client.post('/api/renewal-interests', json={'name':card['name'], 'enabled':True})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['names'], [card['name']])
        with self.client.session_transaction() as session: session['_user_id'] = '99999999'
        self.assertEqual(self.client.get('/api/renewal-interests').status_code, 302)
        with self.client.session_transaction() as session: session['_user_id'] = str(self.uid)
        self.assertEqual(self.client.post('/api/renewal-interests', json={'name':'fake', 'enabled':True}).status_code, 400)
        self.assertEqual(self.client.post('/api/renewal-interests', json={'name':card['name'], 'enabled':False}).json['names'], [])

    def test_due_alert_is_generated_once_and_uses_server_schedule(self):
        card = next(c for c in module._load_renewal_cards() if c.get('available'))
        previous, _ = renewal_occurrences(card)
        with module.app.app_context():
            module.db.session.add(module.RenewalInterest(user_id=self.uid, card_name=card['name'],
                                  subscribed_at=previous.replace(tzinfo=None) - timedelta(minutes=2)))
            module.db.session.commit()
        with patch.object(module,'datetime') as clock:
            clock.now.return_value=previous-timedelta(seconds=30)
            first = self.client.post('/api/renewal-alerts/check', json={})
            second = self.client.post('/api/renewal-alerts/check', json={})
        self.assertEqual(len(first.json['alerts']), 1)
        self.assertEqual(second.json['alerts'], [])
        with module.app.app_context():
            self.assertEqual(module.Notification.query.filter_by(user_id=self.uid, kind='renewal').count(), 1)

    def test_regular_member_cannot_enter_admin_or_write_summary(self):
        with module.app.app_context():
            user = module.db.session.get(module.User, self.uid); user.is_admin = False; module.db.session.commit()
        self.assertEqual(self.client.get('/admin').status_code, 403)
        response = self.client.get('/secret/player-review-summary')
        self.assertIn('id="admin-password"', response.text)

    def test_member_management_paginates_and_searches(self):
        marker = 'pagination-' + uuid.uuid4().hex
        ids = []
        try:
            with module.app.app_context():
                users = [module.User(username=f'{marker}-{n}', email=f'{marker}-{n}@example.test') for n in range(35)]
                module.db.session.add_all(users); module.db.session.commit(); ids = [u.id for u in users]
            first = self.client.get('/admin/points', query_string={'q':marker})
            second = self.client.get('/admin/points', query_string={'q':marker, 'page':2})
            self.assertEqual(first.text.count('class="user-row"'), 30)
            self.assertEqual(second.text.count('class="user-row"'), 5)
            self.assertIn('검색 결과 35명', first.text)
        finally:
            with module.app.app_context():
                module.User.query.filter(module.User.id.in_(ids)).delete(synchronize_session=False)
                module.db.session.commit()

    def test_new_interest_does_not_generate_old_alert(self):
        card = next(c for c in module._load_renewal_cards() if c.get('available'))
        self.client.post('/api/renewal-interests', json={'name':card['name'], 'enabled':True})
        self.assertEqual(self.client.post('/api/renewal-alerts/check', json={}).json['alerts'], [])

    def test_post_requires_csrf_token(self):
        module.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post('/api/renewal-interests', json={'name':'fake', 'enabled':True}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
