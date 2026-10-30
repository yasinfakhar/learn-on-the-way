import contextlib, contextvars, json, os, time
from collections import defaultdict, deque
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from mcp.server.fastmcp import FastMCP
from mcp import types
from mcp.server.transport_security import TransportSecuritySettings
from urllib.parse import urlsplit
from jsonschema import validate, ValidationError
from .db import Base, engine
from .auth import router, authenticate, BASE
from .learning import TOOLS, execute
from .courses import catalog

current_user = contextvars.ContextVar('user',default=None)
mcp = FastMCP('Learn on the Way', stateless_http=True, json_response=True,
 transport_security=TransportSecuritySettings(allowed_hosts=[urlsplit(BASE).netloc,'127.0.0.1:*','localhost:*'], allowed_origins=[BASE]),
 instructions='Teach one short step at a time. Use course material to answer questions. Ask one quiz question, wait for the actual answer, then record it. Never fabricate progress. Voice is provided by the host client; tool availability in voice mode depends on that client. Pause whenever the learner needs to focus on driving.')

def schema(tool): return {'type':'object','properties':tool['properties'],'required':tool.get('required',[]),'additionalProperties':False}
@mcp._mcp_server.list_tools()
async def list_tools():
    return [types.Tool(name=name,description=t['description'],inputSchema=schema(t),annotations=types.ToolAnnotations(readOnlyHint=name in ('list_micro_courses','search_micro_courses','open_step','get_my_learning'),destructiveHint=False,idempotentHint=name!='record_answer',openWorldHint=False)) for name,t in TOOLS.items()]
@mcp._mcp_server.call_tool()
async def call_tool(name, arguments):
    try:
        if not current_user.get(): raise ValueError('Authentication required')
        if name not in TOOLS: raise ValueError('Unknown tool')
        validate(arguments,schema(TOOLS[name]))
        result = execute(current_user.get(),name,arguments)
        return [types.TextContent(type='text',text=json.dumps(result))]
    except (ValueError,ValidationError) as error:
        raise ValueError(str(error).split('\n')[0])

mcp_app = mcp.streamable_http_app()
@contextlib.asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    catalog()  # Validate all course files before serving traffic.
    async with mcp.session_manager.run(): yield
app = FastAPI(title='Learn on the Way',lifespan=lifespan)
app.add_middleware(SessionMiddleware,secret_key=os.environ['SESSION_SECRET'],https_only=BASE.startswith('https://'),same_site='lax',max_age=600)
app.include_router(router)

# One process: bounded per-IP throttling, using the socket peer (never an untrusted forwarded header).
visits = defaultdict(deque)
@app.middleware('http')
async def security(request:Request, call_next):
    path = request.url.path
    if path.startswith('/oauth/') and request.method=='POST':
        ip = request.client.host if request.client else 'unknown'
        key=(ip,path); now=time.monotonic(); queue=visits[key]
        while queue and queue[0]<now-60: queue.popleft()
        if len(queue)>=20: return JSONResponse({'detail':'Too many requests. Retry in one minute.'},429,headers={'Retry-After':'60'})
        queue.append(now)
        if len(visits)>10000:
            for k in list(visits):
                if not visits[k] or visits[k][-1]<now-60: del visits[k]
    marker=None
    if path.startswith('/mcp') or path.startswith('/api/'):
        auth=request.headers.get('authorization','')
        user = authenticate(auth[7:]) if auth.startswith('Bearer ') else None
        if not user:
            return JSONResponse({'detail':'Sign in to Learn on the Way'},401,headers={'WWW-Authenticate':f'Bearer resource_metadata="{BASE}/.well-known/oauth-protected-resource"'})
        marker=current_user.set(user)
    try:
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        return response
    finally:
        if marker is not None: current_user.reset(marker)

@app.get('/health')
def health():
    from sqlalchemy import text
    with engine.connect() as conn: conn.execute(text('SELECT 1'))
    return {'status':'ok'}
@app.get('/', response_class=HTMLResponse)
def home(): return '<h1>Learn on the Way</h1><p>Short audio-friendly courses, quizzes and private progress.</p><p>Connect your MCP client to '+BASE+'/mcp</p><a href="/privacy">Privacy</a>'
@app.get('/privacy', response_class=HTMLResponse)
def privacy(): return '<h1>Learn on the Way privacy</h1><p>This server stores your email, hashed password, authorization credentials, course progress, quiz answers and ratings. Your connected AI provider also processes the material and conversation under its own terms. Credentials are stored as hashes. Data is not sold. Ask the server operator to delete your account and learning records. This app supplies text and tools; your AI client supplies speech. Configure while parked and pause learning when traffic requires attention.</p>'
@app.post('/api/tools/{name}')
async def rest(name:str, request:Request):
    if name not in TOOLS: raise HTTPException(404,'Unknown tool')
    args=await request.json()
    try:
        validate(args,schema(TOOLS[name]))
        return execute(current_user.get(),name,args)
    except (ValueError,ValidationError) as e: raise HTTPException(422,str(e).split('\n')[0])
app.mount('/',mcp_app)
