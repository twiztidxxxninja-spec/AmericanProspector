"""
Wait and sleep mechanics. Space key opens a prompt for how long to wait/rest.
"""

import tcod
import tcod.event
import tcod.console
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.player import Player
    from src.survival import SurvivalStats

WHITE  = (255, 255, 255)
YELLOW = (255, 220,  60)
CYAN   = ( 80, 200, 200)
GREEN  = ( 80, 180,  80)
RED    = (220,  50,  50)
GREY   = (120, 120, 120)
DGREY  = ( 60,  60,  60)
BLACK  = (  0,   0,   0)
BG     = ( 15,  15,  30)


def wait_menu(con: tcod.console.Console, ctx, player: "Player",
              time_obj) -> Optional[int]:
    """
    Prompt: wait how long?
    Returns minutes to advance, or None if cancelled.
    """
    OPTIONS = [
        ("1 minute",   1),
        ("10 minutes", 10),
        ("1 hour",     60),
        ("Until dawn", -1),   # special: advance to next dawn
        ("Until dusk", -2),
        ("Sleep (8 hours)", -3),
        ("Custom...",  -99),
    ]

    W, H = 36, len(OPTIONS) + 7
    X = (con.width  - W) // 2
    Y = (con.height - H) // 2
    selected = 0
    custom_mode = False
    custom_text = ""

    from src.menus import draw_box

    while True:
        draw_box(con, X, Y, W, H, "Wait / Rest")
        con.print(X + 2, Y + 1,
                  f"{time_obj.time_string}  {time_obj.date_string}",
                  fg=GREY, bg=BG)
        con.print(X + 2, Y + 2,
                  f"Fatigue: {player.survival.bar('fatigue', 10)}",
                  fg=WHITE, bg=BG)

        from src.menus import BG2
        for i, (label, _) in enumerate(OPTIONS):
            row = Y + 4 + i
            is_sel = i == selected
            color  = CYAN if is_sel else WHITE
            bgc    = BG2  if is_sel else BG
            prefix = ">" if is_sel else " "
            con.print(X + 2, row, f"{prefix} {label}", fg=color, bg=bgc)

        if custom_mode:
            cursor = "_"
            con.print(X + 2, Y + H - 3,
                      f"Minutes: {custom_text}{cursor}"[:W - 4],
                      fg=YELLOW, bg=BG)
        con.print(X + 2, Y + H - 2,
                  "↑↓ select   Enter confirm   Esc cancel",
                  fg=GREY, bg=BG)

        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.TextInput) and custom_mode:
                if event.text.isdigit():
                    custom_text += event.text
                continue
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K   = tcod.event.KeySym

                if custom_mode:
                    if sym == K.ESCAPE:
                        custom_mode = False
                        custom_text = ""
                    elif sym == K.BACKSPACE and custom_text:
                        custom_text = custom_text[:-1]
                    elif sym in (K.RETURN, K.KP_ENTER) and custom_text:
                        return int(custom_text)
                    continue

                if sym == K.ESCAPE:
                    return None
                if sym in (K.UP, K.KP_8):
                    selected = max(0, selected - 1)
                if sym in (K.DOWN, K.KP_2):
                    selected = min(len(OPTIONS) - 1, selected + 1)
                if sym in (K.RETURN, K.KP_ENTER):
                    _, minutes = OPTIONS[selected]
                    if minutes == -99:
                        custom_mode = True
                        custom_text = ""
                    elif minutes == -1:
                        # Advance to next dawn
                        h = time_obj.hour
                        if h < 5:
                            return (5 - h) * 60 - time_obj.minute
                        else:
                            return (29 - h) * 60 - time_obj.minute  # next day 5am
                    elif minutes == -2:
                        # Advance to dusk
                        h = time_obj.hour
                        if h < 18:
                            return (18 - h) * 60 - time_obj.minute
                        else:
                            return (42 - h) * 60 - time_obj.minute
                    elif minutes == -3:
                        return 480   # 8 hours
                    else:
                        return minutes


def resolve_sleep(player: "Player", minutes: int, sheltered: bool = False,
                  bedroll: bool = False) -> dict:
    """
    Resolve a rest period. Returns a summary dict.
    """
    warmth_bonus = 20 if bedroll else 0
    if sheltered:
        warmth_bonus += 15

    fatigue_before = player.survival.fatigue
    player.survival.rest(minutes)
    if warmth_bonus:
        player.survival.warmth = min(100.0,
                                     player.survival.warmth + warmth_bonus * (minutes / 480))

    fatigue_after = player.survival.fatigue
    quality = "restful" if minutes >= 420 else \
              "adequate" if minutes >= 240 else "light"

    return {
        "minutes":  minutes,
        "quality":  quality,
        "fatigue_gained": fatigue_after - fatigue_before,
        "sheltered": sheltered,
    }
