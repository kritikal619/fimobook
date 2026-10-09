import unittest
import uuid
import os
import base64
from renewal_webpush import ensure_key, public_key, send_push
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from types import SimpleNamespace
from tests import test_admin_workspace_renewal as workspace_tests
import app as m
from jobs.renewal_push_job import queue_due, deliver_pending, run
from renewal import renewal_occurrences, renewal_is_quiet, KST


class RenewalPushTest(unittest.TestCase):
    def setUp(self):
        workspace_tests.AdminWorkspaceRenewalTest.setUp(self)
        self.key_path='/tmp/renewal-push-test-'+uuid.uuid4().hex+'.pem'
        ensure_key(self.key_path)
        self.path_patch=patch.object(m,'_renewal_vapid_path',return_value=self.key_path)
        self.path_patch.start()
        receiver=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        b64=lambda value:base64.urlsafe_b64encode(value).rstrip(b'=').decode()
        self.endpoint='https://fcm.googleapis.com/fcm/send/'+uuid.uuid4().hex
        self.subscription={'endpoint':self.endpoint,'keys':{'p256dh':b64(receiver),'auth':b64(os.urandom(16))}}
        self.card=next(c for c in m._load_renewal_cards() if c.get('available'))
        previous,_=renewal_occurrences(self.card)
        self.occurrence=previous.replace(tzinfo=None)
        self.now=self.occurrence-timedelta(seconds=30)

    def tearDown(self):
        if hasattr(self,'key_path'):
            with m.app.app_context():
                m.RenewalPushDelivery.query.filter_by(user_id=self.uid).delete()
                m.RenewalPushDevice.query.filter_by(user_id=self.uid).delete()
                m.RenewalQuietHours.query.filter_by(user_id=self.uid).delete()
                m.db.session.commit()
            self.path_patch.stop()
            os.unlink(self.key_path)
        workspace_tests.AdminWorkspaceRenewalTest.tearDown(self)

    def enable(self):
        response=self.client.post('/api/renewal-push',json={'subscription':self.subscription,'action':'enable'})
        self.assertEqual(response.status_code,200)
        return response

    def interest(self):
        with m.app.app_context():
            row=m.RenewalInterest(user_id=self.uid,card_name=self.card['name'],subscribed_at=self.occurrence-timedelta(seconds=90))
            m.db.session.add(row);m.db.session.commit();return row.id

    def test_binding_is_account_scoped_and_preserves_coupon_preferences(self):
        self.enable()
        response=self.client.get('/api/renewal-push',headers={'X-Fimo-Push-Endpoint':self.endpoint})
        self.assertTrue(response.json['enabled'])
        self.assertEqual(response.json['vapid'],public_key(self.key_path))
        self.client.post('/api/renewal-push',json={'endpoint':self.endpoint,'action':'disable'})
        self.assertFalse(self.client.get('/api/renewal-push',headers={'X-Fimo-Push-Endpoint':self.endpoint}).json['enabled'])

    def test_untrusted_endpoints_cannot_bind_and_csrf_is_required(self):
        for endpoint in ['http://127.0.0.1:8000','https://127.0.0.1/','https://example.com/','https://fcm.googleapis.com:8443/']:
            value={**self.subscription,'endpoint':endpoint}
            self.assertEqual(self.client.post('/api/renewal-push',json={'subscription':value,'action':'enable'}).status_code,400)
        m.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.post('/api/renewal-push',json={'subscription':self.subscription,'action':'enable'}).status_code,400)

    def test_other_account_cannot_disable_or_test_the_device(self):
        self.enable()
        with m.app.app_context():
            user=m.User(username=uuid.uuid4().hex,email=uuid.uuid4().hex+'@example.test')
            m.db.session.add(user);m.db.session.commit();other_id=user.id
        try:
            with self.client.session_transaction() as session:session['_user_id']=str(other_id)
            for action in ('disable','test','heartbeat'):
                self.assertEqual(self.client.post('/api/renewal-push',json={'endpoint':self.endpoint,'action':action}).status_code,404)
            self.assertFalse(self.client.get('/api/renewal-push',headers={'X-Fimo-Push-Endpoint':self.endpoint}).json['enabled'])
        finally:
            with m.app.app_context():m.db.session.delete(m.db.session.get(m.User,other_id));m.db.session.commit()

    def test_logout_detaches_this_sessions_push(self):
        self.enable();self.client.get('/logout')
        with m.app.app_context():self.assertFalse(m.RenewalPushDevice.query.filter_by(endpoint=self.endpoint).one().enabled)

    def test_job_sends_with_closed_browser_once_and_creates_inbox_item(self):
        self.enable();self.interest();sent=[]
        with m.app.app_context():
            result=run(now=self.now,send=lambda subscription,payload:sent.append(payload))
            self.assertEqual(result['sent'],1)
            self.assertEqual(sent[0]['kind'],'renewal')
            self.assertEqual(sent[0]['title'],self.card['name']+' 1분 후 갱신')
            self.assertEqual(sent[0]['renewal_at'],self.occurrence.replace(tzinfo=timezone.utc).isoformat())
            self.assertEqual(m.Notification.query.filter_by(user_id=self.uid,kind='renewal').count(),1)
            run(now=self.now+timedelta(seconds=15),send=lambda subscription,payload:sent.append(payload))
            self.assertEqual(len(sent),1)
            self.assertEqual(m.RenewalPushDelivery.query.filter_by(status='sent',user_id=self.uid).count(),1)

    def test_transient_failure_retries_and_disabled_interest_cancels_pending(self):
        self.enable();interest_id=self.interest()
        def fail(subscription,payload):raise RuntimeError('transient')
        with m.app.app_context():
            self.assertEqual(run(now=self.now,send=fail)['retry'],1)
            self.assertEqual(deliver_pending(self.now+timedelta(seconds=3),send=lambda *args:None)['sent'],0)
            m.RenewalInterest.query.filter_by(id=interest_id).delete();m.db.session.commit()
            self.assertEqual(deliver_pending(self.now+timedelta(seconds=15),send=lambda *args:self.fail('cancelled push was sent'))['expired'],1)

    def test_retry_survives_job_restart(self):
        self.enable();self.interest()
        def fail(subscription,payload):raise RuntimeError('transient')
        with m.app.app_context():
            run(now=self.now,send=fail);m.db.session.remove()
            sent=[]
            self.assertEqual(run(now=self.now+timedelta(seconds=10),send=lambda subscription,payload:sent.append(payload))['sent'],1)
            self.assertEqual(len(sent),1)

    def test_expired_renewal_is_not_sent_late(self):
        self.enable();self.interest()
        with m.app.app_context():
            queue_due(self.now)
            self.assertEqual(deliver_pending(self.occurrence+timedelta(seconds=301),send=lambda *args:self.fail('expired push was sent'))['expired'],1)

    def test_test_notification_is_only_sent_on_explicit_request_and_throttled(self):
        self.enable()
        with patch.object(m,'send_renewal_push',return_value='ok') as send:
            response=self.client.post('/api/renewal-push',json={'endpoint':self.endpoint,'action':'test'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(send.call_args.args[1]['kind'],'renewal_test')
            self.assertTrue(send.call_args.args[1]['tag'].startswith('renewal-test-'))
            self.assertEqual(self.client.post('/api/renewal-push',json={'endpoint':self.endpoint,'action':'test'}).status_code,429)
            send.assert_called_once()

    def test_web_push_encrypts_and_signs_without_exposing_plaintext(self):
        response=SimpleNamespace(status_code=201,text='')
        with patch('pywebpush.requests.post',return_value=response) as post:
            send_push(self.subscription,{'kind':'renewal','title':'암호화 확인'},self.key_path)
        kwargs=post.call_args.kwargs
        self.assertNotIn('암호화 확인'.encode(),kwargs['data'])
        self.assertEqual(kwargs['headers']['content-encoding'],'aes128gcm')
        self.assertTrue(kwargs['headers']['Authorization'].startswith('vapid '))
        self.assertEqual(kwargs['timeout'],10)

    def test_key_is_stable_and_private(self):
        before=public_key(self.key_path);ensure_key(self.key_path)
        self.assertEqual(public_key(self.key_path),before)
        self.assertEqual(os.stat(self.key_path).st_mode & 0o777,0o600)

    def quiet_around_now(self):
        minute = self.now.replace(tzinfo=timezone.utc).astimezone(KST).hour * 60 + self.now.minute
        with m.app.app_context():
            m.db.session.add(m.RenewalQuietHours(user_id=self.uid, enabled=True,
                                                start_minute=(minute-1)%1440, end_minute=(minute+5)%1440))
            m.db.session.commit()

    def test_quiet_settings_persist_and_reject_invalid_ranges(self):
        self.assertEqual(self.client.get('/api/renewal-quiet-hours').json,
                         {'enabled':False, 'start':'00:00', 'end':'07:00'})
        value={'enabled':True, 'start':'23:00', 'end':'07:00'}
        self.assertEqual(self.client.post('/api/renewal-quiet-hours',json=value).json,value)
        self.assertEqual(self.client.get('/api/renewal-quiet-hours').json,value)
        for invalid in [None, [], {**value,'enabled':'true'}, {**value,'start':'24:00'},
                        {**value,'end':'07:60'}, {**value,'end':'23:00'}]:
            self.assertEqual(self.client.post('/api/renewal-quiet-hours',json=invalid).status_code,400)
        self.assertEqual(self.client.get('/api/renewal-quiet-hours').json,value)
        with patch.object(m,'send_renewal_push') as send:
            m.app.config['WTF_CSRF_ENABLED']=True
            self.assertEqual(self.client.post('/api/renewal-quiet-hours',json=value).status_code,400)
            send.assert_not_called()

    def test_quiet_job_skips_all_devices_and_inbox(self):
        self.enable();self.interest();self.quiet_around_now()
        with m.app.app_context():
            result=run(now=self.now,send=lambda *args:self.fail('quiet push sent'))
            self.assertEqual(result['sent'],0)
            self.assertEqual(m.RenewalPushDelivery.query.filter_by(user_id=self.uid).count(),0)
            self.assertEqual(m.Notification.query.filter_by(user_id=self.uid,kind='renewal').count(),0)

    def test_quiet_change_cancels_previously_queued_retry(self):
        self.enable();self.interest()
        with m.app.app_context():queue_due(self.now)
        self.quiet_around_now()
        with m.app.app_context():
            self.assertEqual(deliver_pending(self.now,send=lambda *args:self.fail('quiet retry sent'))['expired'],1)

    def test_quiet_settings_are_account_scoped_without_a_push_device(self):
        value={'enabled':True,'start':'23:00','end':'07:00'}
        self.client.post('/api/renewal-quiet-hours',json=value)
        with m.app.app_context():
            other=m.User(username=uuid.uuid4().hex,email=uuid.uuid4().hex+'@example.test')
            m.db.session.add(other);m.db.session.commit();other_id=other.id
        try:
            client=m.app.test_client()
            with client.session_transaction() as session:session['_user_id']=str(other_id)
            self.assertFalse(client.get('/api/renewal-quiet-hours').json['enabled'])
            self.assertEqual(client.post('/api/renewal-quiet-hours',json={**value,'start':'22:00'}).status_code,200)
            self.assertEqual(self.client.get('/api/renewal-quiet-hours').json,value)
        finally:
            with m.app.app_context():
                m.RenewalQuietHours.query.filter_by(user_id=other_id).delete()
                m.db.session.delete(m.db.session.get(m.User,other_id));m.db.session.commit()

    def test_night_push_is_not_retried_at_end_of_quiet_hours(self):
        self.enable();interest_id=self.interest()
        occurrence=datetime(2026,9,29,21,59,50)  # 06:59:50 KST
        with m.app.app_context():
            m.db.session.get(m.RenewalInterest,interest_id).subscribed_at=occurrence-timedelta(seconds=30)
            device=m.RenewalPushDevice.query.filter_by(user_id=self.uid).one()
            m.db.session.add(m.RenewalPushDelivery(user_id=self.uid,interest_id=interest_id,device_id=device.id,occurrence=occurrence))
            m.db.session.commit()
        self.client.post('/api/renewal-quiet-hours',json={'enabled':True,'start':'00:00','end':'07:00'})
        with m.app.app_context():
            result=deliver_pending(occurrence+timedelta(seconds=30),send=lambda *args:self.fail('night push replayed'))
            self.assertEqual(result['expired'],1)

    def test_foreground_does_not_replay_night_renewals_in_morning(self):
        self.interest()
        self.client.post('/api/renewal-quiet-hours',json={'enabled':True,'start':'23:00','end':'07:00'})
        card={**self.card,'eo':0,'min':0,'sec':0}
        with m.app.app_context():
            interest=m.RenewalInterest.query.filter_by(user_id=self.uid).one()
            interest.subscribed_at=datetime(2026,9,29,14);m.db.session.commit()
        with patch.object(m,'_load_renewal_cards',return_value=[card]),patch.object(m,'datetime') as clock:
            clock.now.return_value=datetime(2026,9,29,22,0,tzinfo=timezone.utc)
            self.assertEqual(self.client.post('/api/renewal-alerts/check',json={}).json['alerts'],[])
            clock.now.return_value=datetime(2026,9,29,22,59,15,tzinfo=timezone.utc)
            self.assertEqual(len(self.client.post('/api/renewal-alerts/check',json={}).json['alerts']),1)

    def test_one_minute_window_does_not_send_early_or_after_renewal(self):
        self.enable();self.interest()
        with m.app.app_context():
            sent=[]
            self.assertEqual(run(now=self.occurrence-timedelta(seconds=61),send=lambda *args:sent.append(args))['sent'],0)
            self.assertEqual(run(now=self.occurrence-timedelta(seconds=60),send=lambda *args:sent.append(args))['sent'],1)
            self.assertEqual(run(now=self.occurrence,send=lambda *args:sent.append(args))['sent'],0)
            self.assertEqual(len(sent),1)

    def test_pending_reminder_expires_at_the_renewal_second(self):
        self.enable();self.interest()
        with m.app.app_context():
            queue_due(self.now)
            self.assertEqual(deliver_pending(self.occurrence,send=lambda *args:self.fail('late reminder sent'))['expired'],1)


class QuietBoundaryTest(unittest.TestCase):
    def test_overnight_and_daytime_boundaries_in_korea_time(self):
        pref=SimpleNamespace(enabled=True,start_minute=23*60,end_minute=7*60)
        for hour,minute,expected in [(22,59,False),(23,0,True),(0,0,True),(6,59,True),(7,0,False)]:
            local=datetime(2026,9,30,hour,minute,tzinfo=KST)
            self.assertEqual(renewal_is_quiet(pref,local.astimezone(timezone.utc)),expected)
            self.assertEqual(renewal_is_quiet(pref,local.astimezone(timezone.utc).replace(tzinfo=None)),expected)
        pref.start_minute=12*60;pref.end_minute=13*60
        self.assertTrue(renewal_is_quiet(pref,datetime(2026,9,30,12,tzinfo=KST)))
        self.assertFalse(renewal_is_quiet(pref,datetime(2026,9,30,13,tzinfo=KST)))
        pref.enabled=False
        self.assertFalse(renewal_is_quiet(pref,datetime(2026,9,30,12,tzinfo=KST)))

if __name__=='__main__':unittest.main()
