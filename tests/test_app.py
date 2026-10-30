import os, hashlib, base64, secrets
os.environ['DATABASE_URL']='sqlite:////tmp/learn-test.db'
os.environ['SESSION_SECRET']='test-secret-not-for-production'
os.environ['PUBLIC_URL']='http://testserver'
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine


def connect(client,email):
    redirect='https://example.com/callback'
    client_id=client.post('/oauth/register',json={'redirect_uris':[redirect]}).json()['client_id']
    verifier=secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    page=client.get('/oauth/authorize',params={'client_id':client_id,'redirect_uri':redirect,'code_challenge':challenge,'state':'test'})
    import re
    csrf=re.search('name="csrf" value="([^"]+)"',page.text)[1]
    response=client.post('/oauth/authorize',data={'csrf':csrf,'email':email,'password':'a-test-password-123','action':'signup'},follow_redirects=False)
    from urllib.parse import urlsplit,parse_qs
    code=parse_qs(urlsplit(response.headers['location']).query)['code'][0]
    body={'grant_type':'authorization_code','client_id':client_id,'redirect_uri':redirect,'code':code,'code_verifier':verifier}
    tokens=client.post('/oauth/token',data=body)
    assert tokens.status_code==200,tokens.text
    assert client.post('/oauth/token',data=body).status_code==400
    return tokens.json(),client_id

def test_auth_progress_and_isolation():
    Base.metadata.drop_all(engine)
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
        assert client.post('/api/tools/list_micro_courses',json={}).status_code==401
        a,aid=connect(client,'alice@example.com'); b,bid=connect(client,'bob@example.com')
        def tool(name,args={},token=a['access_token']):
            return client.post('/api/tools/'+name,json=args,headers={'Authorization':'Bearer '+token})
        cid={'course_id':'learning-that-sticks'}
        assert tool('list_micro_courses').json()[0]['step_count']==4
        assert tool('search_micro_courses',{'query':'recall'}).json()
        assert tool('start_or_continue_course',cid).status_code==200
        assert tool('get_my_learning',token=b['access_token']).json()==[]
        assert tool('open_step',{**cid,'step':99}).status_code==422
        assert tool('complete_course',cid).status_code==422
        assert tool('rate_course',{**cid,'rating':5}).status_code==422
        assert tool('complete_step',{**cid,'step':3}).status_code==422
        assert tool('record_answer',{**cid,'step':3,'answered':True,'answer':'Premature answer'}).status_code==422
        for step in (1,2): assert tool('complete_step',{**cid,'step':step}).status_code==200
        assert tool('record_answer',{**cid,'step':3,'answered':True,'answer':''}).status_code==422
        assert tool('record_answer',{**cid,'step':3,'answered':True,'answer':'Recall it in my own words','correct':True}).status_code==200
        for step in range(1,5): assert tool('complete_step',{**cid,'step':step}).status_code==200
        assert tool('complete_course',cid).json()['progress']['status']=='passed'
        assert tool('rate_course',{**cid,'rating':6}).status_code==422
        assert tool('rate_course',{**cid,'rating':5}).status_code==200
        assert tool('get_my_learning',{'user_id':'alice'}).status_code==422
        body={'grant_type':'refresh_token','refresh_token':a['refresh_token'],'client_id':aid}
        assert client.post('/oauth/token',data=body).status_code==200
        assert client.post('/oauth/token',data=body).status_code==400
        # Exercise actual MCP transport, tool discovery and invocation.
        headers={'Authorization':'Bearer '+b['access_token'],'Accept':'application/json, text/event-stream'}
        init=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}})
        assert init.status_code==200,init.text
        result=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
        assert len(result.json()['result']['tools'])==9,result.text
        result=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_my_learning','arguments':{}}})
        assert result.status_code==200 and '[]' in result.text,result.text


def test_mcp_structured_workflow_includes_required_persistence():
    import importlib
    from app import main as application
    # The MCP SDK session manager is intentionally single-use per app lifetime.
    app=importlib.reload(application).app
    Base.metadata.drop_all(engine)
    with TestClient(app) as client:
        tokens,_=connect(client,'workflow@example.com')
        headers={'Authorization':'Bearer '+tokens['access_token'],'Accept':'application/json, text/event-stream'}
        def call(name,args):
            response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})
            assert response.status_code==200,response.text
            payload=response.json()['result']
            assert not payload.get('isError'),payload
            assert payload['structuredContent']==__import__('json').loads(payload['content'][0]['text'])
            assert payload['content'][1]['text'].startswith('REQUIRED NEXT ACTION:')
            return payload['structuredContent']
        cid={'course_id':'learning-that-sticks'}
        start=call('start_or_continue_course',cid)
        assert start['next_action']['after_delivery']['tool']=='complete_step'
        qa=call('complete_step',{**cid,'step':1})
        assert qa['next_action']['after_learner_done']['tool']=='complete_step'
        quiz=call('complete_step',{**cid,'step':2})
        assert quiz['next_action']['type']=='ask_authored_quiz'
        answer=call('record_answer',{**cid,'step':3,'answered':True,'answer':'Recall the lesson without looking.'})
        assert answer['next_action']['tool']=='complete_step'
        narration=call('complete_step',{**cid,'step':3})
        assert narration['next_action']['type']=='narrate'
        finish=call('complete_step',{**cid,'step':4})
        assert finish['next_action']['tool']=='complete_course'
        passed=call('complete_course',cid)
        assert passed['next_action']['type']=='request_rating'
        rated=call('rate_course',{**cid,'rating':5})
        assert rated['next_action']['type']=='end'
