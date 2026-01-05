from aiohttp import web
import secrets
import random

routes = web.RouteTableDef()

game_sessions = {}

def generate_memo():
    return secrets.token_hex(8)

def create_deck():
    suits = ['♠', '♥', '♦', '♣']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    deck = [{'rank': rank, 'suit': suit} for suit in suits for rank in ranks]
    random.shuffle(deck)
    return deck

def hand_value(hand):
    total = 0
    aces = 0
    
    for card in hand:
        if card['rank'] == 'A':
            aces += 1
            total += 11
        elif card['rank'] in ['J', 'Q', 'K']:
            total += 10
        else:
            total += int(card['rank'])
    
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    
    return total

@routes.get("/")
async def index(request: web.Request) -> web.StreamResponse:
    memo = generate_memo()
    
    deck = create_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    
    game_sessions[memo] = {
        'deck': deck,
        'player_hand': player_hand,
        'dealer_hand': dealer_hand,
        'paid': False,
        'game_over': False,
        'result': None
    }
    
    with open('index.html', 'r') as f:
        html = f.read()
    
    html = html.replace('MEMO_PLACEHOLDER', memo)
    html = html.replace('BOOTH_PLACEHOLDER', USER)
    
    return web.Response(content_type="text/html", text=html)

@routes.post("/verify_payment")
async def verify_payment(request: web.Request) -> web.StreamResponse:
    data = await request.json()
    block_hash = data.get('block_hash')
    memo = data.get('memo')
    
    if not block_hash or not memo:
        return web.json_response({'error': 'Missing block_hash or memo'}, status=400)
    
    if memo not in game_sessions:
        return web.json_response({'error': 'Invalid game session'}, status=400)
    
    try:
        async with request.app['client'].post(f'/getlive', data=str(block_hash)) as resp:
            if resp.status != 200:
                return web.json_response({'error': 'Block not found or not live'}, status=400)
            
            block = await resp.json()
            
            change = block.get('change', {})
            if (change.get('dst') != USER or 
                change.get('memo') != memo or 
                change.get('n') < 1):
                return web.json_response({'error': 'Invalid payment block'}, status=400)
            
            src_user = change.get('src')
            try:
                async with request.app['client'].get('/balances') as balance_resp:
                    if balance_resp.status == 200:
                        balances = await balance_resp.json()
                        player_balance = balances.get(src_user, 20)
                        if player_balance < 0:
                            return web.json_response({'error': 'Insufficient tickets - you have negative balance'}, status=400)
            except Exception as e:
                print(f"Balance check failed: {e}")
            
            session = game_sessions[memo]
            session['paid'] = True
            session['player'] = change.get('src')
            session['bet_amount'] = change.get('n')
            
            player_value = hand_value(session['player_hand'])
            
            return web.json_response({
                'success': True,
                'player_hand': session['player_hand'],
                'dealer_hand': [session['dealer_hand'][0]],
                'player_value': player_value,
                'can_hit': player_value < 21,
                'message': 'Payment verified! Your turn to play.'
            })
            
    except Exception as e:
        return web.json_response({'error': f'Verification failed: {str(e)}'}, status=500)

@routes.post("/hit")
async def hit(request: web.Request) -> web.StreamResponse:
    data = await request.json()
    memo = data.get('memo')
    
    if not memo:
        return web.json_response({'error': 'Missing memo'}, status=400)
    
    if memo not in game_sessions:
        return web.json_response({'error': 'Invalid game session'}, status=400)
    
    session = game_sessions[memo]
    
    if not session['paid']:
        return web.json_response({'error': 'Must pay to play!'}, status=400)
    
    if session['game_over']:
        return web.json_response({'error': 'Game already over'}, status=400)
    
    if len(session['deck']) == 0:
        return web.json_response({'error': 'No more cards in deck'}, status=400)
    
    new_card = session['deck'].pop()
    session['player_hand'].append(new_card)
    player_value = hand_value(session['player_hand'])
    
    if player_value > 21:
        session['game_over'] = True
        session['result'] = 'bust'
        return web.json_response({
            'player_hand': session['player_hand'],
            'player_value': player_value,
            'dealer_hand': session['dealer_hand'],
            'dealer_value': hand_value(session['dealer_hand']),
            'result': 'bust',
            'message': 'Bust! You lose.',
            'game_over': True
        })
    
    return web.json_response({
        'player_hand': session['player_hand'],
        'player_value': player_value,
        'can_hit': True,
        'message': 'Card drawn. Hit or stand?'
    })

@routes.post("/stand")
async def stand(request: web.Request) -> web.StreamResponse:
    data = await request.json()
    memo = data.get('memo')
    
    if not memo:
        return web.json_response({'error': 'Missing memo'}, status=400)
    
    if memo not in game_sessions:
        return web.json_response({'error': 'Invalid game session'}, status=400)
    
    session = game_sessions[memo]
    
    if not session['paid']:
        return web.json_response({'error': 'Must pay to play!'}, status=400)
    
    if session['game_over']:
        return web.json_response({'error': 'Game already over'}, status=400)
    
    dealer_value = hand_value(session['dealer_hand'])
    while dealer_value < 17:
        if len(session['deck']) == 0:
            break
        session['dealer_hand'].append(session['deck'].pop())
        dealer_value = hand_value(session['dealer_hand'])
    
    player_value = hand_value(session['player_hand'])
    
    if dealer_value > 21:
        result = 'win'
        message = 'Dealer busts! You win!'
        tickets = session['bet_amount'] * 2 
    elif player_value > dealer_value:
        result = 'win'
        message = 'You win!'
        tickets = session['bet_amount'] * 2
    elif player_value == dealer_value:
        result = 'push'
        message = 'Push! It\'s a tie.'
        tickets = session['bet_amount']  
    else:
        result = 'lose'
        message = 'Dealer wins.'
        tickets = 0
    
    session['game_over'] = True
    session['result'] = result
    
    if tickets > -1:
        try:
            async with request.app['client'].post('/transfer', 
                json={
                    'dst': session['player'],
                    'n': tickets,
                    'memo': secrets.token_hex(4) 
                }
            ) as resp:
                if resp.status == 200:
                    transfer_result = await resp.json()
                    if 'error' in transfer_result:
                        print(f"Transfer error: {transfer_result['error']}")
                else:
                    error_text = await resp.text()
                    print(f"Transfer failed with status {resp.status}: {error_text}")
        except Exception as e:
            print(f"Transfer failed: {str(e)}")
    
    return web.json_response({
        'player_hand': session['player_hand'],
        'player_value': player_value,
        'dealer_hand': session['dealer_hand'],
        'dealer_value': dealer_value,
        'result': result,
        'message': message,
        'tickets_won': tickets,
        'game_over': True
    })

@routes.get("/game_state")
async def game_state(request: web.Request) -> web.StreamResponse:
    memo = request.query.get('memo')
    
    if not memo or memo not in game_sessions:
        return web.json_response({'error': 'Invalid game session'}, status=400)
    
    session = game_sessions[memo]
    
    if not session['paid']:
        return web.json_response({
            'paid': False,
            'message': 'Waiting for payment...'
        })
    
    return web.json_response({
        'paid': True,
        'player_hand': session['player_hand'],
        'dealer_hand': [session['dealer_hand'][0]] if not session['game_over'] else session['dealer_hand'],
        'player_value': hand_value(session['player_hand']),
        'dealer_value': hand_value(session['dealer_hand']) if session['game_over'] else None,
        'game_over': session['game_over'],
        'result': session['result']
    })


# The code below should connect your code to bc_agent correctly without needing student edits (written by cs340 staff)

async def asyncstartup(app: web.Application) -> None:
    """Run after the app exists and the asyncio system is functional"""
    import aiohttp
    auth = aiohttp.BasicAuth(login=USER, password=PASS)
    app['client'] = aiohttp.ClientSession(f'http://localhost:{PORT}', auth=auth)

async def asyncshutdown(app):
    """Cleanup and prepare to exit."""
    await app['client'].close()


if __name__ == '__main__': 
    # parse command-line arguments
    import argparse, pathlib, json
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=pathlib.Path, help="the private config file used by bc_agent.py on the same server")
    args = parser.parse_args()
    
    # load the blockchain contact info
    try:
        with open(args.config) as src:
            pconf = json.load(src)
        PORT = pconf['port']
        USER = None
        for u,p in pconf['passcodes'].items():
            if u.endswith('_b'):
                if USER is None:
                    USER, PASS = u, p
                else:
                    raise LookupError('Config file ambiguous with multiple booths')
    except BaseException as ex:
        print('ERROR: Invalid config file')
        print(ex)
        quit(1)
        
    # create the app
    app = web.Application()
    app.on_startup.append(asyncstartup)
    app.on_shutdown.append(asyncshutdown)
    app.add_routes(routes)
    
    web.run_app(app, host="0.0.0.0", port=20258) # this function never returns