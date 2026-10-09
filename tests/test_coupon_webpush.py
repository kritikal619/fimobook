import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import app as m
from tests import test_renewal_push as renewal_tests
from jobs.coupon_webpush_job import run, deliver_pending


class CouponWebPushTest(unittest.TestCase):
    setUp = renewal_tests.RenewalPushTest.setUp
    def tearDown(self):
        if hasattr(self, 'uid'):
            with m.app.app_context():
                m.CouponPushDelivery.query.filter_by(user_id=self.uid).delete()
                m.CouponPushRelease.query.filter(m.CouponPushRelease.code.like(self.prefix+'%')).delete(synchronize_session=False)
                m.db.session.commit()
        renewal_tests.RenewalPushTest.tearDown(self)

    def enable(self, topic='coupon'):
        response=self.client.post('/api/renewal-push',json={'action':'enable','topic':topic,'subscription':self.subscription})
        self.assertEqual(response.status_code,200)
        return response.json

    @property
    def prefix(self):
        return 'TEST'+str(self.uid)+'-'

    def coupon(self, suffix='NEW', expired=False):
        return {'code':self.prefix+suffix,'boolExpires':expired}

    def test_independent_preferences_restore_and_logout(self):
        state=self.enable();self.assertTrue(state['coupons_enabled']);self.assertFalse(state['enabled'])
        self.enable('renewal')
        state=self.client.post('/api/renewal-push',json={'action':'disable','topic':'coupon','endpoint':self.endpoint}).json
        self.assertTrue(state['enabled']);self.assertFalse(state['coupons_enabled'])
        self.enable()
        state=self.client.post('/api/renewal-push',json={'action':'disable','endpoint':self.endpoint}).json
        self.assertFalse(state['enabled']);self.assertTrue(state['coupons_enabled'])
        state=self.client.get('/api/renewal-push',headers={'X-Fimo-Push-Endpoint':self.endpoint}).json
        self.assertTrue(state['coupons_enabled'])
        self.client.get('/logout')
        with m.app.app_context():
            device=m.RenewalPushDevice.query.filter_by(endpoint=self.endpoint).one()
            self.assertFalse(device.enabled);self.assertFalse(device.coupons_enabled)

    def test_coupon_test_uses_coupon_payload_and_rate_limit(self):
        self.enable()
        with patch.object(m,'send_renewal_push') as send:
            result=self.client.post('/api/renewal-push',json={'action':'test','topic':'coupon','endpoint':self.endpoint})
            self.assertEqual(result.status_code,200)
            payload=send.call_args.args[1];self.assertEqual(payload['kind'],'coupon_test');self.assertEqual(payload['url'],'/coupons/')
            self.assertEqual(self.client.post('/api/renewal-push',json={'action':'test','topic':'coupon','endpoint':self.endpoint}).status_code,429)

    def seed(self):
        with m.app.app_context():
            m.CouponPushRelease.query.delete();m.CouponPushState.query.delete();m.db.session.commit()
            return run(coupons=[self.coupon('OLD')],send=lambda *args:self.fail('historical coupon sent'))

    def test_seed_is_quiet_new_coupon_sends_once_and_one_inbox_per_account(self):
        self.enable();self.seed()
        sent=[]
        with m.app.app_context():
            now=datetime.utcnow()+timedelta(seconds=1)
            other=m.RenewalPushDevice(user_id=self.uid,endpoint='https://fcm.googleapis.com/fcm/send/'+uuid.uuid4().hex,
                 subscription_json='{}',enabled=False,coupons_enabled=True,coupons_subscribed_at=now-timedelta(seconds=1))
            m.db.session.add(other);m.db.session.commit()
            result=run(coupons=[self.coupon()],now=now,send=lambda sub,payload:sent.append(payload))
            self.assertEqual(result['sent'],2)
            self.assertTrue(all(payload['kind']=='coupon' for payload in sent))
            self.assertEqual(m.Notification.query.filter_by(user_id=self.uid,kind='coupon').count(),1)
            run(coupons=[self.coupon()],now=now+timedelta(minutes=1),send=lambda *args:self.fail('duplicate sent'))
            self.assertEqual(m.CouponPushDelivery.query.filter_by(user_id=self.uid).count(),2)

    def test_failure_persists_for_retry_and_disabled_coupon_cancels(self):
        self.enable();self.seed()
        with m.app.app_context():
            now=datetime.utcnow()+timedelta(seconds=1)
            def fail(*args):raise RuntimeError('transport unavailable')
            self.assertEqual(run(coupons=[self.coupon()],now=now,send=fail)['retry'],1)
            m.db.session.remove()
            self.assertEqual(deliver_pending([self.coupon()],now+timedelta(seconds=61),send=lambda *args:None)['sent'],1)
            run(coupons=[self.coupon('NEXT')],now=now+timedelta(seconds=62),send=fail)
            device=m.RenewalPushDevice.query.filter_by(endpoint=self.endpoint).one();device.coupons_enabled=False;m.db.session.commit()
            self.assertEqual(deliver_pending([self.coupon('NEXT')],now+timedelta(minutes=3),send=lambda *args:self.fail('disabled push sent'))['expired'],1)

    def test_source_failure_never_consumes_new_codes_and_expired_not_sent(self):
        self.enable();self.seed()
        with m.app.app_context():
            with patch('jobs.coupon_webpush_job._fetch_coupon_raw',side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError):run()
            self.assertIsNone(m.db.session.get(m.CouponPushRelease,self.coupon()['code']))
            self.assertEqual(run(coupons=[self.coupon(expired=True)],send=lambda *args:self.fail('expired push sent'))['sent'],0)

    def test_rebinding_account_does_not_transfer_old_topics(self):
        self.enable();self.enable('renewal')
        with m.app.app_context():
            user=m.User(username=uuid.uuid4().hex,email=uuid.uuid4().hex+'@example.test');m.db.session.add(user);m.db.session.commit();other=user.id
        try:
            with self.client.session_transaction() as session:session['_user_id']=str(other)
            response=self.client.post('/api/renewal-push',json={'action':'enable','topic':'coupon','subscription':self.subscription})
            self.assertFalse(response.json['enabled']);self.assertTrue(response.json['coupons_enabled'])
            with self.client.session_transaction() as session:session['_user_id']=str(self.uid)
            self.assertEqual(self.client.post('/api/renewal-push',json={'action':'disable','topic':'coupon','endpoint':self.endpoint}).status_code,404)
        finally:
            with m.app.app_context():
                m.RenewalPushDevice.query.filter_by(user_id=other).delete();m.db.session.delete(m.db.session.get(m.User,other));m.db.session.commit()

    def test_empty_initial_feed_does_not_hide_first_future_coupon(self):
        self.enable()
        with m.app.app_context():
            m.CouponPushRelease.query.delete();m.CouponPushState.query.delete();m.db.session.commit()
            now=datetime.utcnow()+timedelta(seconds=1)
            run(coupons=[],now=now,send=lambda *args:self.fail('empty feed sent'))
            self.assertEqual(run(coupons=[self.coupon()],now=now+timedelta(minutes=1),send=lambda *args:None)['sent'],1)

    def test_guest_has_login_link_and_coupon_markup_is_server_rendered(self):
        client=m.app.test_client()
        with patch.object(m,'get_coupons',return_value=[{**self.coupon(),'items':['코인 100만','선수팩 1개'],'manualStatus':'auto'}]):
            response=client.get('/coupons/')
            self.assertEqual(response.status_code,200);self.assertIn('로그인',response.text)
            self.assertIn(self.coupon()['code'],response.text);self.assertIn('쿠폰 등록 방법',response.text)
            self.assertNotIn('·',response.text.split('<div class="coupon-page-outer">')[1].split('</div>\n\n<script')[0])

if __name__=='__main__':unittest.main()
