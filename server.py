import asyncio, json, random, string, os, time
from aiohttp import web, WSMsgType

ROOT=os.path.dirname(__file__)
rooms={}
WORDS=set('''apple ant art arm age air ask act add ape ace able about above after again age ago also any are area arm around as at ate aunt away baby back bad bag ball banana bank bark base bat bath be bear beat bed bee been beer begin bell best better big bird bite black blue boat body book boot born both box boy bread break bring brother brown build bus busy but buy cake call came can car card care case cat catch cause cell chain chair chance change check child city class clean clear close cloud coat cold come cook cool copy corn cost could country course cover cow create cup cut dance dark date day deal dear deep desk did die different dinner do dog door down draw dream drink drive drop dry duck each ear early earth east easy eat egg end enjoy enough enter equal even ever every eye face fact fall family far fast father fear feel feet few field find fine fire fish fit five flat fly food foot for form found four free friend from front fruit fun game garden gas gave get girl give glad go gold good got great green ground group grow guess had hair half hand happen happy hard has hat have he head hear heart help her here high him his history hit hold home hope horse hot hour house how human hundred hungry idea if important in in side into iron is island it its job join jump just keep key kind king kitchen knew know land large last late laugh learn leave left leg less let letter life light like line list little live long look lost love low made make man many map mark match matter may me meal mean meet men middle might milk mind minute miss money month moon more morning mother mountain move much music must name near need never new next nice night no not note now number of off often old on once one only open or other our out over own page paper part party pass past people person pick place plan play point power pretty problem put question quick quiet race rain ran random read ready real red remember right ring road room round run sad safe same saw say school sea seat second see seem sentence set she ship short should show side simple since sing sister sit six sky sleep small smile snow so some something son soon sound south space speak spell spend sport stand star start stay still stop story street strong study such summer sun sure table take talk tall team tell ten test than that the their them then there these they thing think this three time to today together told too top town tree try turn two under until up us use used very voice wait walk want warm was watch water way we well went were what when where which while white who why wide will win wind window with word work world would write wrong year yellow yes you young'''.split())

def code():
    while True:
        c=''.join(random.choices(string.ascii_uppercase+string.digits,k=5))
        if c not in rooms: return c

def public_state(r):
    state={k:r[k] for k in ['code','host','mode','status','words','current_word','turn_index','turn_deadline','round_deadline','min_length','max_strikes','turn_seconds','winner','message']}
    state['players']={pid:{k:v for k,v in p.items() if k!='ws'} for pid,p in r['players'].items()}
    return state

def send(ws, obj):
    return ws.send_str(json.dumps(obj))

async def broadcast(r):
    data=json.dumps({'type':'state','state':public_state(r)})
    dead=[]
    for pid,p in r['players'].items():
        ws=p.get('ws')
        if ws and not ws.closed:
            try: await ws.send_str(data)
            except: dead.append(pid)
    for pid in dead: r['players'][pid]['ws']=None

def active(r): return [p for p in r['players'].values() if p['alive']]
def next_turn(r, from_index=None):
    alive=active(r)
    if len(alive)<=1:
        r['status']='finished'; r['winner']=alive[0]['name'] if alive else 'No winner'; return
    ids=list(r['players'].keys())
    start=(r['turn_index']+1) % max(1,len(ids)) if from_index is None else from_index
    for n in range(len(ids)):
        idx=(start+n)%len(ids); pid=ids[idx]
        if r['players'][pid]['alive']:
            r['turn_index']=idx; r['turn_deadline']=time.time()+r['turn_seconds']; return

def strike(r,pid,reason):
    p=r['players'][pid]; p['strikes']+=1
    r['message']=f"{p['name']} {reason} (strike {p['strikes']}/{r['max_strikes']})"
    if p['strikes']>=r['max_strikes']:
        p['alive']=False; r['message']=f"{p['name']} is out!"
    next_turn(r)

async def timer_loop(r):
    while r['status']=='playing':
        await asyncio.sleep(.25)
        now=time.time()
        if r['mode']=='timed' and now>=r['round_deadline']:
            r['status']='finished'; best=max(r['players'].values(),key=lambda p:p['score']); r['winner']=best['name']; r['message']='Time is up!'; await broadcast(r); break
        if r['status']=='playing' and now>=r['turn_deadline']:
            ids=list(r['players']); pid=ids[r['turn_index']]
            if r['players'][pid]['alive']:
                strike(r,pid,'ran out of time')
            await broadcast(r)
        elif r['status']=='playing': await broadcast(r)

async def ws_handler(request):
    ws=web.WebSocketResponse(heartbeat=20); await ws.prepare(request)
    pid=None; room=None
    async for msg in ws:
        if msg.type!=WSMsgType.TEXT: continue
        try: d=json.loads(msg.data)
        except: continue
        act=d.get('action')
        if act=='create':
            pid=d.get('playerId') or ''.join(random.choices(string.ascii_lowercase+string.digits,k=9))
            name=(d.get('name') or 'Player').strip()[:18] or 'Player'; c=code()
            room={'code':c,'host':pid,'mode':d.get('mode','survival'),'status':'lobby','players':{pid:{'id':pid,'name':name,'score':0,'strikes':0,'alive':True,'ws':ws}},'words':[],'current_word':'COMPUTER','turn_index':0,'turn_deadline':0,'round_deadline':0,'min_length':3,'max_strikes':3,'turn_seconds':10,'winner':None,'message':'Waiting for players to join…','timer_task':None}
            rooms[c]=room; await send(ws,{'type':'joined','playerId':pid,'code':c}); await broadcast(room)
        elif act=='join':
            c=(d.get('code') or '').upper().strip(); room=rooms.get(c)
            if not room: await send(ws,{'type':'error','message':'Room not found. Check the code and try again.'}); continue
            if room['status']!='lobby': await send(ws,{'type':'error','message':'This game has already started.'}); continue
            if len(room['players'])>=8: await send(ws,{'type':'error','message':'This room is full (8 players).'}); continue
            pid=d.get('playerId') or ''.join(random.choices(string.ascii_lowercase+string.digits,k=9)); name=(d.get('name') or 'Player').strip()[:18] or 'Player'
            room['players'][pid]={'id':pid,'name':name,'score':0,'strikes':0,'alive':True,'ws':ws}; await send(ws,{'type':'joined','playerId':pid,'code':c}); await broadcast(room)
        elif act=='start' and room and pid==room['host']:
            if len(room['players'])<2: await send(ws,{'type':'error','message':'You need at least 2 players to start.'}); continue
            room['status']='playing'; room['turn_index']=0; room['turn_deadline']=time.time()+10
            if room['mode']=='timed': room['round_deadline']=time.time()+180
            room['message']='Game on! Start with a word ending in R.'
            room['timer_task']=asyncio.create_task(timer_loop(room)); await broadcast(room)
        elif act=='play' and room and room['status']=='playing':
            ids=list(room['players']); current=ids[room['turn_index']]
            if pid!=current: await send(ws,{'type':'error','message':'It is not your turn yet.'}); continue
            p=room['players'][pid]; word=(d.get('word') or '').strip().lower()
            if time.time()>room['turn_deadline']: strike(room,pid,'ran out of time')
            elif not word.isalpha() or len(word)<room['min_length'] or word not in WORDS:
                strike(room,pid,'used an invalid or unknown word')
            elif word in [x['word'] for x in room['words']]: strike(room,pid,'repeated a word')
            elif word[0].upper()!=room['current_word'][-1].upper(): strike(room,pid,f"must start with {room['current_word'][-1].upper()}")
            else:
                elapsed=10-(room['turn_deadline']-time.time()); bonus=max(0,min(5,int((5-elapsed)/1.5)))
                p['score']+=10+bonus; room['words'].append({'word':word.upper(),'player':p['name'],'points':10+bonus}); room['current_word']=word.upper(); room['message']=f"{p['name']} played {word.upper()} (+{10+bonus})"; next_turn(room)
            await broadcast(room)
        elif act=='leave' and room and pid in room['players']:
            room['players'][pid]['ws']=None
    if room and pid in room['players']: room['players'][pid]['ws']=None
    return ws

async def index(request): return web.FileResponse(os.path.join(ROOT,'index.html'))
app=web.Application(); app.router.add_get('/',index); app.router.add_get('/ws',ws_handler)
if __name__=='__main__': web.run_app(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
