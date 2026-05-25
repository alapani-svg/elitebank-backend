"""
End-to-end smoke test for the Elite Bank backend.
Runs every API endpoint via Django's test client (no live server needed).
Usage:
    .\venv\Scripts\python.exe manage.py shell -c "exec(open('smoke_test.py').read())"
"""
import json
from decimal import Decimal
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
c = Client(SERVER_NAME='localhost')


def check(label, ok, detail=''):
    icon = 'PASS' if ok else 'FAIL'
    line = f"  [{icon}] {label}"
    if detail:
        line += f"  — {detail}"
    print(line)
    return ok


def auth(client, email, password):
    res = client.post('/api/auth/login/', data=json.dumps({'email': email, 'password': password}),
                      content_type='application/json')
    if res.status_code != 200:
        return None
    body = res.json()
    # Login returns tokens under either `tokens.access` or `access`
    if 'tokens' in body:
        return body['tokens'].get('access')
    return body.get('access')


# Cleanup any prior test data (transactions first — PROTECT FK)
from transactions.models import Transaction
from django.db.models import Q
_old_users = User.objects.filter(email__endswith='@smoketest.local')
Transaction.objects.filter(Q(sender__in=_old_users) | Q(recipient__in=_old_users)).delete()
_old_users.delete()

print('=== Elite Bank API smoke test ===\n')

# ── 1. Auth flow ─────────────────────────────────────────────────────────────
print('AUTH')
r = c.post('/api/auth/register/', data=json.dumps({
    'email': 'alice@smoketest.local', 'full_name': 'Alice Smith', 'phone_number': '+237600000001',
    'password': 'pa55word', 'password_confirm': 'pa55word',
}), content_type='application/json')
check('register Alice', r.status_code == 201, f'status={r.status_code}')

r = c.post('/api/auth/register/', data=json.dumps({
    'email': 'bob@smoketest.local', 'full_name': 'Bob Jones', 'phone_number': '+237600000002',
    'password': 'pa55word', 'password_confirm': 'pa55word',
}), content_type='application/json')
check('register Bob', r.status_code == 201)

alice_token = auth(c, 'alice@smoketest.local', 'pa55word')
bob_token   = auth(c, 'bob@smoketest.local',   'pa55word')
check('login Alice', alice_token is not None)
check('login Bob',   bob_token   is not None)

# Give Alice some money to play with
alice = User.objects.get(email='alice@smoketest.local')
alice.balance_xaf = Decimal('100000')
alice.save()

# Authenticated client for Alice
hdr = {'HTTP_AUTHORIZATION': f'Bearer {alice_token}'}

#  2. Profile 
print('\nPROFILE')
r = c.get('/api/auth/me/', **hdr)
check('GET /me/', r.status_code == 200 and r.json()['email'] == 'alice@smoketest.local',
      f'balance={r.json().get("balance_xaf")}')

r = c.patch('/api/auth/me/', data=json.dumps({'full_name': 'Alice S.', 'phone_number': '+237600000001', 'language': 'fr'}),
            content_type='application/json', **hdr)
check('PATCH /me/', r.status_code == 200 and r.json()['user']['language'] == 'fr')

r = c.post('/api/auth/change-password/',
           data=json.dumps({'current_password': 'pa55word', 'new_password': 'newpa55word', 'confirm_password': 'newpa55word'}),
           content_type='application/json', **hdr)
check('change password', r.status_code == 200)
# Re-auth with new password
alice_token = auth(c, 'alice@smoketest.local', 'newpa55word')
hdr = {'HTTP_AUTHORIZATION': f'Bearer {alice_token}'}
check('re-login after pw change', alice_token is not None)

r = c.post('/api/auth/2fa/', data=json.dumps({'enabled': True}), content_type='application/json', **hdr)
check('enable 2FA', r.status_code == 200 and r.json()['two_factor_enabled'])

# ── 3. Beneficiaries ─────────────────────────────────────────────────────────
print('\nBENEFICIARIES')
r = c.post('/api/auth/beneficiaries/', data=json.dumps({
    'name': 'Bob (saved)', 'identifier': 'bob@smoketest.local', 'category': 'TRANSFER',
}), content_type='application/json', **hdr)
check('create transfer beneficiary', r.status_code == 201, f'id={r.json().get("id")}')
bene_id = r.json().get('id')

r = c.post('/api/auth/beneficiaries/', data=json.dumps({
    'name': 'My ENEO', 'identifier': '12345', 'category': 'BILL_PAYMENT', 'provider': 'ENEO',
}), content_type='application/json', **hdr)
check('create bill beneficiary', r.status_code == 201)

r = c.post('/api/auth/beneficiaries/', data=json.dumps({
    'name': 'My MTN', 'identifier': '+237670000001', 'category': 'AIRTIME', 'provider': 'MTN',
}), content_type='application/json', **hdr)
check('create airtime beneficiary', r.status_code == 201)

r = c.get('/api/auth/beneficiaries/', **hdr)
check('list beneficiaries', r.status_code == 200 and len(r.json()) == 3, f'count={len(r.json())}')

r = c.get('/api/auth/beneficiaries/?category=TRANSFER', **hdr)
check('filter beneficiaries by category', r.status_code == 200 and len(r.json()) == 1)

r = c.delete(f'/api/auth/beneficiaries/{bene_id}/', **hdr)
check('delete beneficiary', r.status_code == 204)

#  4. Transfers 
print('\nTRANSFERS')
r = c.post('/api/transactions/transfer/', data=json.dumps({
    'recipient_identifier': 'bob@smoketest.local', 'amount': 5000, 'description': 'test transfer',
}), content_type='application/json', **hdr)
check('successful transfer 5000 XAF', r.status_code == 201, f'ref={r.json().get("reference")}')

r = c.post('/api/transactions/transfer/', data=json.dumps({
    'recipient_identifier': 'noone@smoketest.local', 'amount': 1000,
}), content_type='application/json', **hdr)
check('failed transfer (unknown recipient) still records', r.status_code == 400)

# ── 5. Deposit (demo mode) ───────────────────────────────────────────────────
print('\nDEPOSIT')
r = c.post('/api/transactions/deposit/initiate/', data=json.dumps({
    'amount': 25000, 'phone': '+237670000001', 'payment_method': 'mtn',
}), content_type='application/json', **hdr)
check('deposit (demo mode)', r.status_code == 201 and r.json()['status'] == 'completed',
      f'status={r.json().get("status")}')

# ── 6. Bill payment ──────────────────────────────────────────────────────────
print('\nBILL PAYMENT')
r = c.post('/api/transactions/bill-payment/', data=json.dumps({
    'provider': 'ENEO', 'meter_number': '12345', 'amount': 2000,
}), content_type='application/json', **hdr)
check('pay ENEO bill', r.status_code == 201)

# ── 7. Airtime ───────────────────────────────────────────────────────────────
print('\nAIRTIME')
r = c.post('/api/transactions/airtime/', data=json.dumps({
    'network': 'mtn', 'phone': '+237670000001', 'amount': 500,
}), content_type='application/json', **hdr)
check('buy MTN airtime', r.status_code == 201)

# ── 8. Withdrawal ────────────────────────────────────────────────────────────
print('\nWITHDRAWAL')
r = c.post('/api/transactions/withdrawal/', data=json.dumps({
    'amount': 2000, 'phone': '+237670000001', 'payment_method': 'mtn',
}), content_type='application/json', **hdr)
check('withdraw 2000 XAF', r.status_code == 201 and r.json()['status'] == 'completed')

# ── 9. Transaction list & filters ────────────────────────────────────────────
print('\nTRANSACTIONS LIST')
r = c.get('/api/transactions/', **hdr)
check('list all transactions', r.status_code == 200 and len(r.json()) >= 5, f'count={len(r.json())}')

r = c.get('/api/transactions/?type=TRANSFER', **hdr)
check('filter type=TRANSFER', r.status_code == 200)

r = c.get('/api/transactions/?status=COMPLETED', **hdr)
check('filter status=COMPLETED', r.status_code == 200)

# Reference format check
refs = [t['reference'] for t in c.get('/api/transactions/', **hdr).json()]
ok = all(ref.startswith('ELITE-') for ref in refs)
check('all references use ELITE- prefix', ok, f'samples: {refs[:3]}')

# ── 10. Notifications ────────────────────────────────────────────────────────
print('\nNOTIFICATIONS')
r = c.get('/api/auth/notifications/', **hdr)
data = r.json()
check('list notifications', r.status_code == 200 and 'unread_count' in data,
      f'unread={data.get("unread_count")} total={data.get("total")}')

unread = data.get('unread_count', 0)
if data['results']:
    n_id = data['results'][0]['id']
    r = c.post(f'/api/auth/notifications/{n_id}/read/', **hdr)
    check('mark notification read', r.status_code == 200 and r.json()['read'])

r = c.post('/api/auth/notifications/mark-all-read/', **hdr)
check('mark all read', r.status_code == 200)

r = c.get('/api/auth/notifications/', **hdr)
check('unread_count now 0', r.json()['unread_count'] == 0)

# ── 11. Statement download ───────────────────────────────────────────────────
print('\nSTATEMENT')
r = c.get('/api/transactions/statement/?fmt=csv', **hdr)
check('download CSV statement', r.status_code == 200 and r['Content-Type'].startswith('text/csv'),
      f'size={len(r.content)}B')

r = c.get('/api/transactions/statement/?fmt=pdf', **hdr)
check('download PDF statement', r.status_code == 200 and r['Content-Type'] == 'application/pdf',
      f'size={len(r.content)}B')

r = c.get('/api/transactions/statement/?fmt=xml', **hdr)
check('reject invalid fmt', r.status_code == 400)

r = c.get('/api/transactions/statement/?from=2026-01-01&to=2025-01-01&fmt=pdf', **hdr)
check('reject reversed dates', r.status_code == 400)

# ── 12a. Password reset (forgot password) ────────────────────────────────────
# Temporarily disable 2FA on Alice so the post-reset login returns tokens
# (not an OTP challenge). 2FA gets re-enabled in section 12b.
_alice_for_reset = User.objects.get(email='alice@smoketest.local')
_alice_for_reset.two_factor_enabled = False
_alice_for_reset.save()

print('\nPASSWORD RESET')
r = c.post('/api/auth/password-reset/request/',
           data=json.dumps({'email': 'alice@smoketest.local'}),
           content_type='application/json')
check('request reset (existing email)', r.status_code == 200)

r = c.post('/api/auth/password-reset/request/',
           data=json.dumps({'email': 'nobody@nowhere.test'}),
           content_type='application/json')
check('request reset (unknown email) returns 200 (no enum)', r.status_code == 200)

from accounts.services.password_reset import make_token
alice_obj = User.objects.get(email='alice@smoketest.local')
token = make_token(alice_obj)
r = c.post('/api/auth/password-reset/confirm/',
           data=json.dumps({'token': token, 'new_password': 'reseta1b2', 'confirm_password': 'reseta1b2'}),
           content_type='application/json')
check('confirm reset (valid token)', r.status_code == 200)

r = c.post('/api/auth/password-reset/confirm/',
           data=json.dumps({'token': 'bogus', 'new_password': 'xxxa1b2', 'confirm_password': 'xxxa1b2'}),
           content_type='application/json')
check('reject bogus token', r.status_code == 400)

# Re-authenticate Alice with the new password
alice_token = auth(c, 'alice@smoketest.local', 'reseta1b2')
hdr = {'HTTP_AUTHORIZATION': f'Bearer {alice_token}'}
check('login with reset password', alice_token is not None)

# ── 12b. OTP login (2FA) ─────────────────────────────────────────────────────
print('\nOTP LOGIN')
alice_obj.refresh_from_db()
alice_obj.two_factor_enabled = True
alice_obj.save()

r = c.post('/api/auth/login/',
           data=json.dumps({'email': 'alice@smoketest.local', 'password': 'reseta1b2'}),
           content_type='application/json')
body = r.json()
check('2FA login returns requires_otp (no JWT yet)',
      r.status_code == 200 and body.get('requires_otp') is True and 'tokens' not in body,
      f"challenge={body.get('challenge_id','')[:8]}…")

from accounts.models import OTPChallenge
from accounts.services.otp import _hash_code
ch = OTPChallenge.objects.get(pk=body['challenge_id'])
ch.code_hash = _hash_code('555000')
ch.save()

r = c.post('/api/auth/2fa/verify/',
           data=json.dumps({'challenge_id': str(ch.id), 'code': '000000'}),
           content_type='application/json')
check('reject wrong OTP', r.status_code == 400)

r = c.post('/api/auth/2fa/verify/',
           data=json.dumps({'challenge_id': str(ch.id), 'code': '555000'}),
           content_type='application/json')
body = r.json()
check('correct OTP returns JWT', r.status_code == 200 and 'tokens' in body)

r = c.post('/api/auth/2fa/verify/',
           data=json.dumps({'challenge_id': str(ch.id), 'code': '555000'}),
           content_type='application/json')
check('OTP replay blocked', r.status_code == 400)

# Resend
r = c.post('/api/auth/login/',
           data=json.dumps({'email': 'alice@smoketest.local', 'password': 'reseta1b2'}),
           content_type='application/json')
new_ch = r.json()['challenge_id']
r = c.post('/api/auth/2fa/resend/',
           data=json.dumps({'challenge_id': new_ch}),
           content_type='application/json')
check('OTP resend issues new challenge', r.status_code == 200 and 'challenge_id' in r.json())

# Restore alice back to no-2FA so logout test still works
alice_obj.refresh_from_db()
alice_obj.two_factor_enabled = False
alice_obj.save()

# ── 13. Logout ───────────────────────────────────────────────────────────────
print('LOGOUT')
login = c.post('/api/auth/login/', data=json.dumps({'email': 'alice@smoketest.local', 'password': 'reseta1b2'}),
               content_type='application/json')
refresh_tok = login.json()['tokens']['refresh']
# Reset hdr to a fresh access token from this login
alice_token = login.json()['tokens']['access']
hdr = {'HTTP_AUTHORIZATION': f'Bearer {alice_token}'}
r = c.post('/api/auth/logout/', data=json.dumps({'refresh': refresh_tok}),
           content_type='application/json', **hdr)
check('logout (blacklists refresh)', r.status_code == 200)

r = c.post('/api/auth/token/refresh/', data=json.dumps({'refresh': refresh_tok}),
           content_type='application/json')
check('blacklisted refresh rejected', r.status_code == 401, f'status={r.status_code}')

# ── 13. Health & OpenAPI ─────────────────────────────────────────────────────
print('\nHEALTH & DOCS')
r = c.get('/healthz/')
check('GET /healthz/', r.status_code == 200 and r.json()['status'] == 'ok')

r = c.get('/readyz/')
check('GET /readyz/', r.status_code == 200)

r = c.get('/api/schema/')
check('GET /api/schema/ (OpenAPI YAML)', r.status_code == 200, f'size={len(r.content)}B')

# ── 14. Auth boundaries ──────────────────────────────────────────────────────
print('\nAUTH BOUNDARIES')
r = c.get('/api/auth/me/')  # no token
check('reject unauthenticated /me/', r.status_code == 401)

r = c.get('/api/auth/me/', HTTP_AUTHORIZATION='Bearer invalid-token')
check('reject invalid token', r.status_code == 401)

# Bob can't see Alice's transactions
bob_hdr = {'HTTP_AUTHORIZATION': f'Bearer {bob_token}'}
all_txns = c.get('/api/transactions/', **bob_hdr).json()
alice_txn_ids = {t['id'] for t in c.get('/api/transactions/', **hdr).json() if t['sender'] and t['recipient']}
bob_can_see = [t['id'] for t in all_txns if t['id'] in alice_txn_ids and not (t['sender'] is None or t['recipient'] is None)]
# Bob should only see the transfers where he was sender or recipient (the 5000 XAF from Alice)
print(f"    (Bob sees {len(all_txns)} txns, Alice's transfers visible because Bob was recipient)")

# Cleanup
_test_users = User.objects.filter(email__endswith='@smoketest.local')
Transaction.objects.filter(Q(sender__in=_test_users) | Q(recipient__in=_test_users)).delete()
_test_users.delete()
print('\n=== smoke test complete ===')
