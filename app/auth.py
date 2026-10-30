import base64, hashlib, hmac, html, json, os, secrets, time, uuid
from urllib.parse import urlencode, urlsplit
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import Session, User, Record

router = APIRouter()
BASE = os.environ.get('PUBLIC_URL', 'http://localhost:8790').rstrip('/')
passwords = PasswordHasher()
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def put(db, key, value, ttl=0):
    db.add(Record(key=key, value=json.dumps(value), expires=int(time.time())+ttl if ttl else 0))
def get(db, key, consume=False):
    row = db.scalar(select(Record).where(Record.key == key).with_for_update())
    if not row or (row.expires and row.expires < time.time()): raise HTTPException(400, 'Invalid or expired credential')
    value = json.loads(row.value)
    if consume: db.delete(row)
    return value

def authenticate(token):
    with Session.begin() as db:
        try: return get(db, 'access:'+digest(token))['user_id']
        except HTTPException: return None

def issue(db, user_id, client_id, resource):
    access, refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(48)
    value = {'user_id':user_id, 'client_id':client_id, 'resource':resource}
    put(db, 'access:'+digest(access), value, 3600)
    put(db, 'refresh:'+digest(refresh), value, 30*86400)
    return {'access_token':access, 'refresh_token':refresh, 'token_type':'Bearer', 'expires_in':3600, 'scope':'learn'}

@router.get('/.well-known/oauth-protected-resource')
@router.get('/.well-known/oauth-protected-resource/mcp')
def resource_metadata():
    return {'resource':BASE+'/mcp', 'authorization_servers':[BASE], 'scopes_supported':['learn'], 'bearer_methods_supported':['header']}
@router.get('/.well-known/oauth-authorization-server')
def authorization_metadata():
    return {'issuer':BASE, 'authorization_endpoint':BASE+'/oauth/authorize', 'token_endpoint':BASE+'/oauth/token',
      'registration_endpoint':BASE+'/oauth/register', 'response_types_supported':['code'],
      'grant_types_supported':['authorization_code','refresh_token'], 'code_challenge_methods_supported':['S256'],
      'token_endpoint_auth_methods_supported':['none'], 'scopes_supported':['learn']}

@router.post('/oauth/register')
async def register(request:Request):
    body = await request.json()
    redirects = body.get('redirect_uris', [])
    if not isinstance(redirects,list) or not 1 <= len(redirects) <= 10: raise HTTPException(400,'Provide redirect_uris')
    for uri in redirects:
        if not isinstance(uri,str) or len(uri)>2048: raise HTTPException(400,'Invalid redirect URI')
        parsed = urlsplit(uri)
        if parsed.fragment or parsed.username or not parsed.hostname or not (parsed.scheme == 'https' or (parsed.scheme == 'http' and parsed.hostname in ('localhost','127.0.0.1','::1'))):
            raise HTTPException(400,'HTTPS redirect required; loopback HTTP allowed')
    if body.get('token_endpoint_auth_method','none') != 'none': raise HTTPException(400,'Use public client with PKCE')
    client_id = secrets.token_urlsafe(24)
    with Session.begin() as db: put(db,'client:'+client_id,{'redirect_uris':redirects})
    return JSONResponse({'client_id':client_id,'redirect_uris':redirects,'token_endpoint_auth_method':'none','grant_types':['authorization_code','refresh_token'],'response_types':['code']}, status_code=201)

@router.get('/oauth/authorize', response_class=HTMLResponse)
def authorize(request:Request, client_id:str, redirect_uri:str, code_challenge:str, state:str='', response_type:str='code', code_challenge_method:str='S256', resource:str='', scope:str='learn'):
    with Session.begin() as db: client = get(db,'client:'+client_id)
    if redirect_uri not in client['redirect_uris']: raise HTTPException(400,'Unregistered redirect')
    if response_type != 'code' or code_challenge_method != 'S256' or not 43<=len(code_challenge)<=128: raise HTTPException(400,'Authorization code with S256 PKCE required')
    if resource and resource != BASE+'/mcp': raise HTTPException(400,'Invalid resource')
    if scope != 'learn': raise HTTPException(400,'Invalid scope')
    csrf = secrets.token_urlsafe(32)
    request.session['pending'] = {'client_id':client_id,'redirect_uri':redirect_uri,'challenge':code_challenge,'state':state,'resource':BASE+'/mcp','csrf':csrf,'expires':time.time()+600}
    return page(csrf)

def page(csrf, error=''):
    return HTMLResponse('''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>Learn on the Way — Connect</title>
<style>body{font:18px system-ui;background:#f5f5ef;color:#173d33;max-width:460px;margin:8vh auto;padding:24px}input,button{box-sizing:border-box;width:100%;padding:14px;margin:8px 0;font:inherit}button{background:#173d33;color:white;border:0;border-radius:8px}small{display:block;line-height:1.6}</style>
<h1>Learn on the Way</h1><p>Connect your private learning account</p><p>'''+html.escape(error)+'''</p><form method="post" action="/oauth/authorize"><input type="hidden" name="csrf" value="'''+html.escape(csrf)+'''">
<label>Email<input name="email" type="email" required maxlength="254" autocomplete="username"></label>
<label>Password<input name="password" type="password" required minlength="12" maxlength="128" autocomplete="current-password"></label>
<button name="action" value="login">Sign in and connect</button><button name="action" value="signup">Create account and connect</button></form>
<small>Connecting allows your AI client to read courses and manage your progress, answers and ratings. Use a password of at least 12 characters. Set up while parked. <a href="/privacy">Privacy</a></small></html>''')

@router.post('/oauth/authorize')
async def consent(request:Request):
    form = await request.form()
    pending = request.session.get('pending')
    if not pending or pending['expires']<time.time() or not hmac.compare_digest(str(form.get('csrf','')),pending['csrf']): raise HTTPException(400,'Session expired. Restart connection.')
    email = str(form.get('email','')).strip().casefold()
    password = str(form.get('password',''))
    if '@' not in email or len(email)>254 or not 12<=len(password)<=128: return page(pending['csrf'],'Enter an email and a password of 12–128 characters.')
    try:
        with Session.begin() as db:
            user = db.scalar(select(User).where(User.email==email))
            if form.get('action') == 'signup':
                if user: return page(pending['csrf'],'Unable to create account. Try signing in.')
                user = User(id=str(uuid.uuid4()), email=email, password=passwords.hash(password)); db.add(user)
            else:
                try: valid = passwords.verify(user.password if user else DUMMY_PASSWORD,password)
                except VerificationError: valid=False
                if not valid or not user: return page(pending['csrf'],'Invalid email or password.')
            code = secrets.token_urlsafe(40)
            put(db,'code:'+digest(code),{**pending,'user_id':user.id},300)
    except IntegrityError: return page(pending['csrf'],'Unable to create account. Try signing in.')
    request.session.clear()
    return RedirectResponse(pending['redirect_uri']+('&' if '?' in pending['redirect_uri'] else '?')+urlencode({'code':code,'state':pending['state']}),status_code=303)

DUMMY_PASSWORD = passwords.hash(secrets.token_urlsafe(32))
@router.post('/oauth/token')
async def token(request:Request):
    form = await request.form()
    with Session.begin() as db:
        if form.get('grant_type') == 'authorization_code':
            value = get(db,'code:'+digest(str(form.get('code',''))),consume=True)
            verifier = str(form.get('code_verifier',''))
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            if not 43<=len(verifier)<=128 or not hmac.compare_digest(challenge,value['challenge']) or form.get('redirect_uri')!=value['redirect_uri']: raise HTTPException(400,'Invalid grant')
        elif form.get('grant_type') == 'refresh_token':
            value = get(db,'refresh:'+digest(str(form.get('refresh_token',''))),consume=True)
        else: raise HTTPException(400,'Unsupported grant type')
        if form.get('client_id')!=value['client_id'] or form.get('resource',value['resource'])!=value['resource']: raise HTTPException(400,'Invalid client or resource')
        result = issue(db,value['user_id'],value['client_id'],value['resource'])
    return JSONResponse(result,headers={'Cache-Control':'no-store','Pragma':'no-cache'})

@router.post('/oauth/revoke')
async def revoke(request:Request):
    form = await request.form()
    with Session.begin() as db:
        for prefix in ('access:','refresh:'):
            row = db.get(Record,prefix+digest(str(form.get('token',''))))
            if row: db.delete(row)
    return {}
