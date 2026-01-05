"""
This file provides a player-oriented user interface for the blockchain.
It was written by CS 340 course staff and shouldn't require any edits by students.
"""

import asyncio
import aiohttp
import random
import typing
from aiohttp import web
import blockchain

routes = web.RouteTableDef()


# For convenience in typing, we define a type alias
type WebSocket = web.WebSocketResponse|aiohttp.ClientWebSocketResponse

class PrivateConfig(typing.TypedDict):
    port: int
    passcodes: dict[str,str]
    secret: dict[str,int]
    joined: bool


# keep trakc of open WebSockets to close when the app is closed
allws : set[WebSocket] = set()

# these key definitions help us store custom data inside the app object
k_bc = web.AppKey('bc',blockchain.BlockChain)
k_pub = web.AppKey('pub',dict[str,blockchain.UserData])
k_priv = web.AppKey('pub',PrivateConfig)
k_booths = web.AppKey('booths',set[str])
k_players = web.AppKey('players',set[str])

@routes.get('/view')
async def chain_viewer(request: web.Request) -> web.StreamResponse:
    return web.FileResponse('viewer.html')


@routes.get('/chain')
async def full_blockchain(request: web.Request) -> web.StreamResponse:
    """Return all of the blocks this agent knows about"""
    # JavaScript can't parse big integers in JSON, so we use strings instead
    def fixer(e):
        if isinstance(e, dict):
            return {fixer(k):fixer(v) for k,v in e.items()}
        if isinstance(e, int) and e > 0x7fffffff: return str(e)
        return e
    return web.json_response(fixer(request.app[k_bc].get_chain()))


@routes.get('/balances')
async def balances(request: web.Request) -> web.StreamResponse:
    """Return all account balances"""
    return web.json_response(request.app[k_bc].get_accounts())


@routes.post('/getlive')
async def get_live(request: web.Request) -> web.StreamResponse:
    """Return the block whose ID (change hash) is the body of the request
    but only if it is live (on the path from root to head)"""
    blockid = int(await request.read())
    block = request.app[k_bc].get_block(blockid)
    if block is None:
        return web.json_response({'error':'No block '+str(blockid)+' in the blockchain'}, status=400)
    if not request.app[k_bc].is_live(blockid):
        return web.json_response({'error':'Block '+str(blockid)+' is on a dead branch'}, status=400)
    return web.json_response(block)


def basicauth(request:web.Request) -> web.Response | str:
    """Implements HTTP Basic authentication, as described in
    <https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Authentication>"""
    from base64 import b64decode
    nope = web.Response(headers={'WWW-Authenticate': 'Basic realm="CS 340 Blockchain"'}, status=401)
    auth = request.headers.get('Authorization')
    if auth is None: return nope
    if not auth.startswith('Basic '): return nope
    u,p = b64decode(auth[6:]).decode('utf-8').split(':',1)
    if u not in request.app[k_priv]['passcodes']: return nope
    if p != request.app[k_priv]['passcodes'][u]: return nope
    return u

@routes.get('/')
async def get_index(request: web.Request) -> web.StreamResponse:
    """Return a user interface by *modifying* the contents of index.html"""
    user = basicauth(request)
    if isinstance(user, web.Response):
        return user
    with open('index.html','r') as src:
        txt = src.read()
    txt = txt.replace('nobody',user)
    if user.endswith('_b'):
        txt = txt.replace('nobooths', '<option value="' + '"></option><option value="'.join(sorted(request.app[k_players])) + '"></option>')
    else:
        txt = txt.replace('nobooths', '<option value="' + '"></option><option value="'.join(sorted(request.app[k_booths])) + '"></option>')
    return web.Response(content_type="text/html", text=txt)


@routes.post('/transfer')
async def new_block(request : web.Request) -> web.StreamResponse:
    """Allow authenticated users to post a new block to the blockchain.
    Spends roughly 3 seconds verifying the block was accepted before returning a success
    
    Arguments should be a JSON object with keys
    
    {"dst": the user to get the tickets
    ,"n": the number of tickets to send
    ,"memo": the memo to attach to this transaction
    }
    """
    import json, hashlib

    # log in
    user = basicauth(request)
    if isinstance(user, web.Response):
        return user
    
    # check format
    req = await request.json()
    if (not isinstance(req,dict) 
        or req.keys() != {'dst','n','memo'}
        or not isinstance(req['dst'],str)
        or not isinstance(req['n'],int)
        or not isinstance(req['memo'],str)
    ): return web.json_response({'error':"Malformed request body"}, status=400)
    
    b = request.app[k_bc].create_block(
        src=user,
        dst=req['dst'],
        n=req['n'],
        memo=req['memo'],
        privkey=request.app[k_priv]['secret'][user],
    )
    if isinstance(b, str):
        return web.json_response({'error':b}, status=400)
    h = int.from_bytes(hashlib.sha256(json.dumps(b['change'], separators=(',',':'), indent=None, sort_keys=True, ensure_ascii=False).encode('utf-8')).digest(), byteorder='big')
    
    errs = []
    async def send_json(data):
        errs.append(data)

    await request.app[k_bc].add_block(b, send_json)
    if len(errs):
        return web.json_response({'error':'BlockChain implementation error: create_block returned a block that add_block thought was missing it’s old value'},status=500)
    attempts = 1
    broadcast(b)
    
    # verify it's still on the blockchain roughly every 0.5 seconds for about 3 seconds
    for k in range(6):
        await asyncio.sleep(random.uniform(0.3, 0.7))
        if not request.app[k_bc].is_live(h):
            b = request.app[k_bc].create_block(privkey=request.app['pk'][user], **await request.json())
            if isinstance(b, str):
                return web.json_response({'error':b}, status=400)
            h = int.from_bytes(hashlib.sha256(json.dumps(b['change'], separators=(',',':'), indent=None, sort_keys=True, ensure_ascii=False).encode('utf-8')).digest(), byteorder='big')
            await request.app[k_bc].add_block(b, send_json)
            if len(errs):
                return web.json_response({'error':'BlockChain implementation error: create_block returned a block that add_block thought was missing it’s old value'}, status=500)
            attempts += 1
            broadcast(b)
    return web.json_response({'text':f'Added to {attempts} branch{"es" if attempts>1 else ""} of blockchain', 'block':str(h)}, status=200)


async def asyncstartup(app: web.Application) -> None:
    """Run after the app exists and the asyncio system is functional"""
    other_agents = [v['host'] for k,v in app[k_pub].items() if 'host' in v and k not in app[k_priv]['secret']]
    random.shuffle(other_agents)

    app['client'] = aiohttp.ClientSession()
    for url in other_agents:
        contact_in_background(app, url)


def contact_in_background(app: web.Application,  url: str) -> asyncio.Task:
    """Opens a WebSocket to a given URL in a background task."""
    session: aiohttp.ClientSession = app['client']
    
    async def helper():
        try:
            ws = await session.ws_connect('ws://'+url+'/ws')

            if not app[k_priv]['joined']: # first connection, get the chain form this agent
                app[k_priv]['joined'] = True
                async with session.get('http://'+url+'/chain') as resp:
                    async def ignore(arg):
                        pass
                    for b in (await resp.json()).values():
                        await app[k_bc].add_block(b, ignore)

            await use_ws(ws, app)
        except BaseException as ex:
            print('Server at', url, 'did not respond')
    return asyncio.create_task(helper()) # run in background so one slow server doesn't slow others


async def asyncshutdown(app):
    """Cleanup and prepare to exit."""
    await app['client'].close()
    for ws in tuple(allws):
        await ws.close()
    for task in asyncio.all_tasks():
        task.cancel()


async def use_ws(ws: WebSocket, app: web.Application):
    """Stores the socket for later publishing listens to incoming messages."""
  
    allws.add(ws) # placed here to support outgoing messages and shutdown
    try:
        async for msg in ws: # handles incoming messages
            if msg.type == aiohttp.WSMsgType.TEXT:
                
                try: data = msg.json()
                except:
                    print("ERROR: malformed websocket message", msg)
                    continue
                if not isinstance(data, dict):
                    print("ERROR: malformed websocket message", msg)
                    continue
                
                if data.keys() == {'missing'}:
                    b = app[k_bc].get_chain().get(data['missing'], None)
                    if b is not None:
                        asyncio.create_task(ws.send_json(b))
                elif data.keys() == {'change','signature'}:
                    asyncio.create_task(app[k_bc].add_block(data, ws.send_json))
                else:
                    print("ERROR: malformed websocket message", data)
                
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f'ERROR: WebSocket received exception {ws.exception()}')
    finally:
        allws.discard(ws)


@routes.get('/ws')
async def websocket_handler(request : web.Request) -> web.WebSocketResponse:
    """Accepts a WebSocket from another agent."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await use_ws(ws, request.app)
    return ws


def broadcast(data: blockchain.Block) -> None:
    """Sends same JSON data to all connected agents."""
    for ws in allws:
        asyncio.create_task(ws.send_json(data))


if __name__ == '__main__': 
    # parse command-line arguments
    import argparse, pathlib, json
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--pub', type=pathlib.Path, default="configs/pub.json", help="Path to a json file with public keys")
    parser.add_argument('-v', '--priv', type=pathlib.Path, default="configs/priv.json", help="Path to a json file with a port, secret keys, and passcodes")
    args = parser.parse_args()
    if not args.pub.exists() or not args.priv.exists():
        parser.print_help()
        quit(1)
    
    global bc, pub, priv
    bc = blockchain.BlockChain()
    with open(args.pub) as src: pub = json.load(src)
    with open(args.priv) as src: priv = json.load(src)
    priv['joined'] = False
    bc.add_users(pub)

    # create the app
    app = web.Application()
    app[k_bc] = bc
    app[k_pub] = pub
    app[k_priv] = priv
    app[k_booths] = {k for k in pub.keys() if k.endswith('_b')}
    app[k_players] = {k for k in pub.keys() if not k.endswith('_b')}
    app.on_startup.append(asyncstartup) # hook in acyn start
    app.on_shutdown.append(asyncshutdown)
    app.add_routes(routes)
    
    print("Accounts:")
    for k,v in priv["passcodes"].items():
        print("    Username:", k)
        print("    Password:", v)
        print()
    
    web.run_app(app, host="0.0.0.0", port=priv['port']) # this function never returns

