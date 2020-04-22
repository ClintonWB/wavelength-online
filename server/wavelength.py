import asyncio
import os
import os.path

from random import randint,sample

import aiohttp.web

import json

HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 8080))

here = os.path.dirname(__file__)

game_max = 9999
game_rotator = 1234
games_started = 0
games = {}

async def index_page(request):
    return aiohttp.web.FileResponse(os.path.join(here,"../client/index.html"))

acme_challenge = {}
acme_challenge_path = os.path.join("acme_challenge.txt")
if os.path.isfile(acme_challenge_path):
    with open(acme_challenge_path) as f: 
        acme_challenge = {'path':f.readline().strip(),
                          'challenge':f.readline().strip}
async def acme_challenge(request):
    
    return aiohttp.web.Response(text=acme_challenge['challenge'])

async def websocket_handler(request):
    print('Websocket connection starting')
    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(request)
    print('Websocket connection ready')

    async for msg in ws:
        print(msg)
        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data == "__ping__":
                await ws.send_str("__pong__")
                continue
            try:
               msg_json = json.loads(msg.data)
            except json.decoder.JSONDecodeError:
                await ws.send_str("Unable to parse:"+msg.data)
                continue
            if 'action' in msg_json:
                if msg_json['action'] in player_actions:
                    success = await player_actions[msg_json['action']](ws,**msg_json.get('args',{}))
                    await ws.send_str("Performed {}: code {}".format(msg_json['action'],success))
                    if(not(success)):
                        await ws.close()
                else:
                    await ws.send_str("Unable to find function {}".format(msg_json['action']))
                
    if(hasattr(ws,'game_id')):
        await leave_game(ws)
    print('Websocket connection closed')
    return ws


# Functionality

player_actions = {}
def register_player_function(func):
    player_actions[func.__name__] = func
    return func

@register_player_function
async def create_game(ws,username,**kwargs):
    
    global games_started
    game_id = (game_rotator*games_started)%game_max
    games_started += 1
    games[game_id] = {'players':{},
                  'spinner_target':50,
                  'flipped':0,
                  'pointer':50,
                  'scores':[0,0],
                  'side':'left',
        }
    print("Created Game {}".format(game_id))
    
    await join_game(ws,username,game_id)
    
    await draw_card(ws)
    await point_pointer(ws, pointer_target=50)
    
    return True

@register_player_function
async def join_game(ws,username,game_id,**kwargs):
    if(game_id not in games):
        return False
    
    game = games[game_id]
    
    if username in game['players']:
        if not game['players'][username]['socket'].closed:
            return False
    else:
        game['players'][username]={}

    ws.username = username
    ws.game_id = game_id
       
    game['players'][username]['socket'] = ws
    
    player_list = list(game['players'].keys())
    msg = {'action':'player_list',
           'performer':username,
           'player_list':player_list
           }
    asyncio.create_task(json_blast_others(ws,msg))
    private_msg = {'action':'join_game',
           'performer':username,
           'player_list':player_list,
           'game_id':game_id,
           'card':game.get('card',["A\tB"]),
           'flipped':game.get('flipped',0),
           'scores':game.get('scores',[0,0]),
           'side':game.get('side','left'),
           'pointer':game.get('pointer',50)}
    asyncio.create_task(send_json(ws,private_msg))
    
    return True

async def leave_game(ws,**kwargs):
    game = games[ws.game_id]
    if(len(game['players']) == 1):
        del game['players']
        return True
    del game['players'][ws.username]
    
    player_list = list(game['players'].keys())
    msg = {'action':'player_list',
           'performer':ws.username,
           'player_list':player_list
           }
    asyncio.create_task(json_blast_others(ws,msg))
    
    return True    
@register_player_function
async def spin_spinner(ws):
    game_id = ws.game_id
    spinner_target = randint(0,100)
    games[game_id]['spinner_target'] = spinner_target
    msg = {'action':'spin_spinner',
           'performer':ws.username}
    asyncio.create_task(json_blast_others(ws,msg))
    
    private_msg = {'action':'spinner_secret',
                'performer':ws.username,
                'spinner_target':spinner_target,
                }
    asyncio.create_task(send_json(ws,private_msg))
    return True
    
@register_player_function
async def reveal_spinner(ws):
    game_id = ws.game_id
    spinner_target = games[game_id]['spinner_target']
    msg = {'action':'reveal_spinner',
           'spinner_target':spinner_target,
           'performer':ws.username}
    asyncio.create_task(json_blast(ws,msg))
    return True
    
@register_player_function
async def draw_card(ws):
    game_id = ws.game_id
    with open(os.path.join(here,"data/english_cards.tsv")) as f:
        lines = f.readlines()
    new_card = sample(lines,2)
    games[game_id]['card'] = new_card
    games[game_id]['flipped'] = 0
    msg = {'action':'draw_card',
           'card':new_card,
           'performer':ws.username}
    asyncio.create_task(json_blast(ws,msg))
    return True
    
@register_player_function
async def flip_card(ws):
    game_id = ws.game_id
    new_side =1-games[game_id]['flipped']
    msg = {'action':'flip_card',
           'performer':ws.username,
           'side':new_side}
    games[game_id]['flipped']=new_side
    asyncio.create_task(json_blast(ws,msg))
    return True
    
@register_player_function
async def point_pointer(ws, pointer_target):
    game_id = ws.game_id
    games[game_id]['pointer'] = pointer_target
    msg = {'action':'point_pointer',
           'pointer_target':pointer_target,
           'performer':ws.username}
    asyncio.create_task(json_blast(ws,msg))
    return True
    
@register_player_function
async def set_scores(ws, scores):
    game_id = ws.game_id
    games[game_id]['scores'] = scores
    msg = {'action':'set_scores',
           'scores':scores,
           'performer':ws.username}
    asyncio.create_task(json_blast(ws,msg))
    return True

@register_player_function    
async def set_side(ws, side):
    game_id = ws.game_id
    games[game_id]['side'] = side
    msg = {'action':'set_side',
           'side':side,
           'performer':ws.username}
    asyncio.create_task(json_blast(ws,msg))
    return True

async def json_blast(ws,msg):
    game_id = ws.game_id
    msg_str = json.dumps(msg)
    for player in games[game_id]['players'].values():
        asyncio.create_task(player['socket'].send_str(msg_str))
    return True
    
async def json_blast_others(ws,msg):
    msg_str = json.dumps(msg)
    player_dict = games[ws.game_id]['players']
    for name in player_dict:
        if name != ws.username:
            asyncio.create_task(player_dict[name]['socket'].send_str(msg_str))
    return True

async def send_json(ws,msg):
    msg_str = json.dumps(msg)
    asyncio.create_task(ws.send_str(msg_str))


app = aiohttp.web.Application()
app.router.add_route('GET', '/', index_page)
app.router.add_route('GET', '/ws', websocket_handler)
app.router.add_static('/.well-known/acme-challenge/', os.path.join(here,"../client/acme_challenge"))
app.router.add_static("/images",os.path.join(here,"../client/images"))

if __name__ == '__main__':
     aiohttp.web.run_app(app, host=HOST, port=PORT)
