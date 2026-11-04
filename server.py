import asyncio
import json
import os
import random
import string
import time

from aiohttp import web, WSMsgType

ROOT = os.path.dirname(__file__)
rooms = {}

# English word bank. This can be expanded in future versions.
WORDS = set("""
apple ant art arm age air ask act add ape ace able about above after again ago
also any area around aunt away baby back bad bag ball banana bank bark base bat
bath beach bear beat bed bee begin bell best better big bird bite black blue
boat body book boot born box boy bread break bring brother brown build bus busy
buy cake call came can car card care case cat catch cause cell chain chair
chance change check child city class clean clear close cloud coat cold come
cook cool copy corn cost could country course cover cow create cup cut dance
dark date day deal dear deep desk did different dinner dog door down draw dream
drink drive drop dry duck each ear early earth east easy eat egg end enjoy
enough enter equal even ever every eye face fact fall family far fast father
fear feel feet few field find fine fire fish fit five flat fly food foot form
found four free friend from front fruit fun game garden gas gave get girl give
glad go goal gold good got great green ground group grow guess hair half hand
happy hard hat have head hear heart help here high history hit hold home hope
horse hot hour house how human hungry idea important inside iron island job
join jump just keep key kind king kitchen know land large last late laugh
learn leave left leg less let letter life light like line list little live
long look lost love low made man many map mark match matter may meal mean meet
middle might milk mind minute miss money month moon more morning mother
mountain move much music must name near need never new next nice night note
number off often old once one only open other our out over own page paper part
party pass past people person pick place plan play point power pretty problem
put question quick quiet race rain ran random read ready real red remember
right ring road room round run sad safe same saw say school sea seat second see
seem sentence set she ship short should show side simple since sing sister sit
six sky sleep small smile snow some son soon sound south space speak spell
spend sport stand star start stay still stop story street strong study summer
sun sure table take talk tall team tell ten test than that their them then
there these they thing think this three time today together told too top town
tree try turn two under until us use used very voice wait walk want warm was
watch water way well went were what when where which while white who why wide
will win wind window with word work world would write wrong year yellow yes
young ability absence academy account achieve action active actor actual adapt
address admire advance advice airport alarm album alert alive allow almost
amount ancient animal announce answer anxiety anyone anyway apart appeal appear
apply approve arch argue arise artist aspect assist assume athlete attack
attempt attend author autumn average avoid awake award aware balance balloon
bamboo banner bargain basic basket battle beauty become bedroom behave belief
belong below benefit bicycle birthday blanket blossom board border bottle
bottom branch brave breeze bridge bright brilliant broken budget button cabin
camera candle captain carpet carry cartoon castle casual celebrate century
certain challenge champion chapter charge charity charm chase cheer chemical
choice circle citizen classic clever climate climb clock collect college color
comfort command comment common company compare compete complete complex concept
concern confirm connect consider contact control conversation corner correct
courage cousin credit crystal culture curious custom damage danger daring
daughter debate decide declare decorate decrease defend define degree delay
deliver demand depend describe desert design desire detail develop device
diamond digital direct discover discuss distance divide doctor dolphin double
dragon drawer driver eager eagle easily economy educate effort electric
element elevator emerge emotion employ empty energy engine enhance ensure
entire entry escape essay evening example excited exercise expand expect
explain explore express extra fabric factor factory failure famous fantasy
farmer fashion feather feature fellow female festival figure final finance
finish flight flower focus forest forget formal forward freedom frequent
fresh future galaxy garage gather general gentle genuine giant ginger glass
global glory golden graceful grammar grand grant grass grateful gravity
grocery growth guard guitar habit hammer handle happen harvest health heaven
helpful hidden holiday honest honey honor horizon hospital host hotel hundred
hunter identify ignore imagine impact improve include income increase indeed
indoor industry inform initial injury insect inspire instant instead interest
invent invite jacket journey judge jungle junior justice kettle keyboard
kingdom knowledge ladder language laptop leader leather lecture legend lemon
length lesson library license lightning limit listen lively locate lonely
lovely loyal lucky luggage machine magazine magic magnet maintain major manage
manner manual market master material maximum measure medical memory mention
message metal method million mirror mobile modern moment monitor monkey
monster monthly motion motor movement multiply museum musical mystery narrow
nation native nature nearby nearly necklace negative network neutral nephew
nervous normal notice object observe obtain obvious ocean office official
onward opinion opposite orange orchard ordinary organize origin original
outdoor outline outside package paddle palace panel panic parent parking
partner passion patient pattern payment peace pencil perfect perform perhaps
period phone photo phrase physical picture pillow planet plastic platform
pleasant plenty pocket poetry police popular portion position positive
possible potato pottery poverty powerful practice prepare present prevent
primary printer private process produce product profile program project
promise promote protect proud provide public purpose puzzle quality quantity
quarter rabbit radar rather reach react reason receive record recover recycle
reduce region regular reject relate release relief remain remind remove repair
repeat replace reply report request require rescue research respect respond
result return reveal review reward rhythm ribbon river robot rocket routine
safety salary sample satisfy science screen search season secret section
secure select senior series service settle shadow shelter shining shoulder
signal silent silver singer single skill slender smart smooth social society
solution source special speech speed spirit split spoken spread spring square
stable stadium station steady stone storage strange strategy strength student
studio subject success sudden suggest support suppose surprise survey switch
symbol system tablet talent target teacher teamwork technology telephone temple
tender tennis terrible theater theory thermal thunder ticket timber tiny
tomorrow tonight topic total tourist tower traffic training travel treasure
triangle tropical trouble tunnel typical umbrella unable uncover understand
unique universe unknown unlock update upgrade useful vacation valley valuable
vanish variety vehicle version victory video village violin visible visitor
visual vitamin volcano volume volunteer voyage wallet wander warning warrior
wealth weather website welcome western whisper wildlife winner winter wisdom
wonderful wooden worker workshop worried worth writer writing yesterday
yourself
""".split())

MISSIONS = [
    {
        "id": "long",
        "title": "Word Explorer",
        "description": "Play a word with at least 7 letters.",
        "bonus": 20
    },
    {
        "id": "short",
        "title": "Quick Thinker",
        "description": "Play a word with exactly 3 letters.",
        "bonus": 15
    },
    {
        "id": "vowel",
        "title": "Vowel Master",
        "description": "Play a word beginning with a vowel.",
        "bonus": 15
    },
    {
        "id": "double",
        "title": "Double Letter",
        "description": "Play a word containing two consecutive identical letters.",
        "bonus": 20
    }
]

CHAOS_EVENTS = [
    {
        "id": "long_words",
        "title": "LONG WORDS",
        "description": "Words must contain at least 5 letters.",
        "min_length": 5,
        "turn_seconds": 10
    },
    {
        "id": "rush",
        "title": "SUDDEN RUSH",
        "description": "You have only 7 seconds per turn.",
        "min_length": 3,
        "turn_seconds": 7
    },
    {
        "id": "bonus",
        "title": "DOUBLE POINTS",
        "description": "Earn double points during this event.",
        "min_length": 3,
        "turn_seconds": 10
    }
]


def make_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=9))


def make_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if code not in rooms:
            return code


def new_mission():
    return dict(random.choice(MISSIONS))


def base_min_length(room):
    return 6 if room["boss_active"] else 3


def public_state(room, viewer_id=None):
    players = {}

    for pid, player in room["players"].items():
        players[pid] = {
            "id": pid,
            "name": player["name"],
            "score": player["score"],
            "strikes": player["strikes"],
            "alive": player["alive"],
            "powerup_count": len(player["powerups"])
        }

    state = {
        "code": room["code"],
        "host": room["host"],
        "mode": room["mode"],
        "status": room["status"],
        "words": room["words"],
        "current_word": room["current_word"],
        "turn_index": room["turn_index"],
        "turn_deadline": room["turn_deadline"],
        "round_deadline": room["round_deadline"],
        "min_length": room["min_length"],
        "max_strikes": room["max_strikes"],
        "turn_seconds": room["turn_seconds"],
        "winner": room["winner"],
        "message": room["message"],
        "players": players,
        "chaos_event": room["chaos_event"],
        "boss_active": room["boss_active"],
        "boss_progress": room["boss_progress"],
        "boss_goal": room["boss_goal"],
        "championship": room["championship"]
    }

    # Secret information is sent only to its owner.
    if viewer_id in room["players"]:
        player = room["players"][viewer_id]
        state["my_mission"] = player["mission"]
        state["my_powerups"] = list(player["powerups"])
        state["shield_active"] = player["shield_active"]
    else:
        state["my_mission"] = None
        state["my_powerups"] = []
        state["shield_active"] = False

    return state


async def send(ws, data):
    if ws and not ws.closed:
        await ws.send_str(json.dumps(data))


async def broadcast(room):
    for pid, player in room["players"].items():
        ws = player["ws"]

        if ws and not ws.closed:
            try:
                await send(ws, {
                    "type": "state",
                    "state": public_state(room, pid)
                })
            except Exception:
                player["ws"] = None


def active_players(room):
    return [
        player for player in room["players"].values()
        if player["alive"]
    ]


def finish_game(room, message):
    room["status"] = "finished"

    ranked = sorted(
        room["players"].values(),
        key=lambda p: (p["score"], p["boss_wins"]),
        reverse=True
    )

    room["championship"] = [
        {
            "rank": index + 1,
            "name": player["name"],
            "score": player["score"]
        }
        for index, player in enumerate(ranked)
    ]

    room["winner"] = ranked[0]["name"] if ranked else "No winner"
    room["message"] = message


def next_turn(room):
    alive = active_players(room)

    if not alive:
        finish_game(room, "All players have been eliminated!")
        return

    if len(alive) == 1 and not room["boss_active"]:
        survivor = alive[0]
        finish_game(room, "The last player standing wins!")
        room["winner"] = survivor["name"]
        return

    ids = list(room["players"].keys())

    for step in range(1, len(ids) + 1):
        index = (room["turn_index"] + step) % len(ids)

        if room["players"][ids[index]]["alive"]:
            room["turn_index"] = index
            room["turn_deadline"] = time.time() + room["turn_seconds"]
            return


def apply_strike(room, pid, reason):
    player = room["players"][pid]

    if player["shield_active"]:
        player["shield_active"] = False
        room["message"] = (
            f"{player['name']} used a Shield and avoided a strike!"
        )
        next_turn(room)
        return

    player["strikes"] += 1

    room["message"] = (
        f"{player['name']} {reason} "
        f"({player['strikes']}/{room['max_strikes']} strikes)"
    )

    if player["strikes"] >= room["max_strikes"]:
        player["alive"] = False
        room["message"] = f"{player['name']} has been eliminated!"

    next_turn(room)


def mission_completed(mission, word):
    if mission["id"] == "long":
        return len(word) >= 7

    if mission["id"] == "short":
        return len(word) == 3

    if mission["id"] == "vowel":
        return word[0] in "aeiou"

    if mission["id"] == "double":
        return any(
            word[i] == word[i + 1]
            for i in range(len(word) - 1)
        )

    return False


def activate_chaos(room):
    event = dict(random.choice(CHAOS_EVENTS))

    room["chaos_event"] = event
    room["chaos_remaining"] = 2
    room["min_length"] = max(
        base_min_length(room),
        event["min_length"]
    )
    room["turn_seconds"] = event["turn_seconds"]

    room["message"] = (
        f"CHAOS EVENT: {event['title']}! {event['description']}"
    )


def clear_chaos(room):
    room["chaos_event"] = None
    room["chaos_remaining"] = 0
    room["min_length"] = base_min_length(room)
    room["turn_seconds"] = 10


def after_valid_word(room):
    if room["chaos_event"]:
        room["chaos_remaining"] -= 1
        if room["chaos_remaining"] <= 0:
            clear_chaos(room)

    # Start a new event only when no event is already active.
    if not room["chaos_event"] and len(room["words"]) % 4 == 0:
        activate_chaos(room)

    if len(room["words"]) >= 12 and not room["boss_active"]:
        room["boss_active"] = True
        room["boss_progress"] = 0
        room["boss_goal"] = 5
        room["min_length"] = 6
        room["message"] = (
            "FINAL BOSS CHALLENGE! Complete five valid words "
            "of at least six letters!"
        )


def create_player(pid, name, ws):
    return {
        "id": pid,
        "name": name,
        "score": 0,
        "strikes": 0,
        "alive": True,
        "ws": ws,
        "mission": new_mission(),
        "powerups": [],
        "shield_active": False,
        "double_points": 0,
        "boss_wins": 0
    }


def create_room(pid, name, mode, ws):
    return {
        "code": make_code(),
        "host": pid,
        "mode": mode if mode in ("survival", "timed") else "survival",
        "status": "lobby",
        "players": {
            pid: create_player(pid, name, ws)
        },
        "words": [],
        "current_word": "COMPUTER",
        "turn_index": 0,
        "turn_deadline": 0,
        "round_deadline": 0,
        "min_length": 3,
        "max_strikes": 3,
        "turn_seconds": 10,
        "winner": None,
        "message": "Waiting for players to join...",
        "timer_task": None,
        "chaos_event": None,
        "chaos_remaining": 0,
        "boss_active": False,
        "boss_progress": 0,
        "boss_goal": 5,
        "championship": []
    }


async def timer_loop(room):
    while room["status"] == "playing":
        await asyncio.sleep(0.5)
        now = time.time()

        if (
            room["mode"] == "timed"
            and now >= room["round_deadline"]
        ):
            finish_game(
                room,
                "Time is up! Championship scores are final."
            )
            await broadcast(room)
            break

        if room["status"] != "playing":
            break

        if now >= room["turn_deadline"]:
            ids = list(room["players"].keys())

            if ids:
                pid = ids[room["turn_index"]]

                if room["players"][pid]["alive"]:
                    apply_strike(room, pid, "ran out of time")

                if room["status"] == "playing":
                    await broadcast(room)
                else:
                    await broadcast(room)
                    break


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    pid = None
    room = None

    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            continue

        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError):
            continue

        action = data.get("action")

        if action == "create":
            pid = data.get("playerId") or make_id()
            name = (data.get("name") or "Player").strip()[:18] or "Player"

            room = create_room(
                pid,
                name,
                data.get("mode", "survival"),
                ws
            )

            rooms[room["code"]] = room

            await send(ws, {
                "type": "joined",
                "playerId": pid,
                "code": room["code"]
            })

            await broadcast(room)

        elif action == "join":
            code = (data.get("code") or "").upper().strip()
            room = rooms.get(code)

            if not room:
                await send(ws, {
                    "type": "error",
                    "message": "Room not found. Check the room code."
                })
                continue

            if room["status"] != "lobby":
                await send(ws, {
                    "type": "error",
                    "message": "This game has already started."
                })
                continue

            if len(room["players"]) >= 8:
                await send(ws, {
                    "type": "error",
                    "message": "This room is full. Maximum 8 players."
                })
                continue

            pid = data.get("playerId") or make_id()
            name = (data.get("name") or "Player").strip()[:18] or "Player"

            room["players"][pid] = create_player(pid, name, ws)

            await send(ws, {
                "type": "joined",
                "playerId": pid,
                "code": code
            })

            await broadcast(room)

        elif action == "start" and room and pid == room["host"]:
            if room["status"] != "lobby":
                continue

            if len(room["players"]) < 2:
                await send(ws, {
                    "type": "error",
                    "message": "At least two players are required."
                })
                continue

            room["status"] = "playing"
            room["turn_index"] = 0
            room["turn_deadline"] = time.time() + room["turn_seconds"]

            if room["mode"] == "timed":
                room["round_deadline"] = time.time() + 180

            room["message"] = (
                "Word Expedition started! The first word must begin with R."
            )

            room["timer_task"] = asyncio.create_task(timer_loop(room))
            await broadcast(room)

        elif action == "play" and room and room["status"] == "playing":
            ids = list(room["players"].keys())

            if not ids:
                continue

            current_pid = ids[room["turn_index"]]

            if pid != current_pid:
                await send(ws, {
                    "type": "error",
                    "message": "It is not your turn."
                })
                continue

            player = room["players"][pid]
            word = (data.get("word") or "").strip().lower()

            if not player["alive"]:
                await send(ws, {
                    "type": "error",
                    "message": "You have been eliminated."
                })
                continue

            if time.time() > room["turn_deadline"]:
                apply_strike(room, pid, "ran out of time")

            elif (
                not word.isalpha()
                or len(word) < room["min_length"]
                or word not in WORDS
            ):
                apply_strike(room, pid, "played an invalid word")

            elif word in [
                entry["word"].lower() for entry in room["words"]
            ]:
                apply_strike(room, pid, "repeated a word")

            elif word[0] != room["current_word"][-1].lower():
                apply_strike(
                    room,
                    pid,
                    f"must start with {room['current_word'][-1].upper()}"
                )

            else:
                elapsed = max(
                    0,
                    10 - (room["turn_deadline"] - time.time())
                )

                speed_bonus = max(
                    0,
                    min(5, int((5 - elapsed) / 1.5))
                )

                points = 10 + speed_bonus

                if player["double_points"] > 0:
                    points *= 2
                    player["double_points"] -= 1

                if (
                    room["chaos_event"]
                    and room["chaos_event"]["id"] == "bonus"
                ):
                    points *= 2

                player["score"] += points

                room["words"].append({
                    "word": word.upper(),
                    "player": player["name"],
                    "points": points
                })

                room["current_word"] = word.upper()

                room["message"] = (
                    f"{player['name']} played {word.upper()} "
                    f"and earned {points} points!"
                )

                if mission_completed(player["mission"], word):
                    bonus = player["mission"]["bonus"]
                    player["score"] += bonus

                    room["message"] += (
                        f" Secret Mission completed! +{bonus} bonus points."
                    )

                    player["mission"] = new_mission()

                if len(room["words"]) % 3 == 0:
                    earned = random.choice(["shield", "double", "time"])
                    player["powerups"].append(earned)

                    room["message"] += (
                        f" {earned.title()} power-up earned!"
                    )

                if room["boss_active"]:
                    room["boss_progress"] += 1
                    player["boss_wins"] += 1

                    if room["boss_progress"] >= room["boss_goal"]:
                        finish_game(
                            room,
                            "Final Boss defeated! Championship complete."
                        )

                else:
                    after_valid_word(room)

                if room["status"] == "playing":
                    next_turn(room)

            await broadcast(room)

        elif action == "powerup" and room and room["status"] == "playing":
            if pid not in room["players"]:
                continue

            player = room["players"][pid]
            power = data.get("power")

            if power not in player["powerups"]:
                await send(ws, {
                    "type": "error",
                    "message": "You do not have that power-up."
                })
                continue

            if power == "time" and (
                pid != list(room["players"])[room["turn_index"]]
            ):
                await send(ws, {
                    "type": "error",
                    "message": "Time Boost can only be used on your turn."
                })
                continue

            player["powerups"].remove(power)

            if power == "shield":
                player["shield_active"] = True
                room["message"] = (
                    f"{player['name']} activated a Shield!"
                )

            elif power == "double":
                player["double_points"] += 2
                room["message"] = (
                    f"{player['name']} activated Double Points!"
                )

            elif power == "time":
                room["turn_deadline"] += 5
                room["message"] = (
                    f"{player['name']} added five seconds to the clock!"
                )

            await broadcast(room)

        elif action == "leave" and room and pid in room["players"]:
            room["players"][pid]["ws"] = None

    if room and pid in room["players"]:
        room["players"][pid]["ws"] = None

    return ws


async def index(request):
    return web.FileResponse(os.path.join(ROOT, "index.html"))


app = web.Application()
app.router.add_get("/", index)
app.router.add_get("/ws", ws_handler)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    web.run_app(app, host="0.0.0.0", port=port)
