"""
gui_pygame.py - Pygame desktop interface for Turkish Mangala (legacy UI).
Run with:  mangala-gui   (or: python -m mangala.gui_pygame)
Requires:  pip install "mangala-game[gui]"   (i.e. pygame)
"""

try:
    import pygame
except ImportError:
    print("Pygame is not installed.\nRun:  pip install pygame   (or: pip install \"mangala-game[gui]\")")
    raise SystemExit(1)

import math
import threading

from . import ai as ai_module
from .engine import (
    GameState, initial_state, legal_moves, apply_move, is_terminal, score,
    P1_PITS, P2_PITS, P1_TREASURY, P2_TREASURY,
    PLAYER_PITS, PLAYER_TREASURY, OPP_TREASURY, TOTAL,
)

# ── window & timing ───────────────────────────────────────────────────────────
WIN_W, WIN_H   = 980, 730
FPS            = 60
TITLE          = "Turkish Mangala"
STONE_DELAY    = 240     # ms between each sown stone (was 140)
CAPTURE_DELAY  = 580     # ms for capture flash (was 320)
EVENT_BANNER   = 1100    # ms to show capture / extra-turn banner
AI_PAUSE_AIAI  = 850     # ms after AI move in AI-vs-AI mode
AI_PAUSE_HUMAN = 400     # ms after AI move in Human-vs-AI mode

# ── layout ────────────────────────────────────────────────────────────────────
TITLE_H   = 56
STATUS_H  = 72
LOG_H     = 110                   # height of the move-log panel at the very bottom
BOARD_TOP = TITLE_H               # y = 56
BOARD_BOT = WIN_H - STATUS_H - LOG_H   # y = 548 (board area unchanged)
BOARD_MID = 302                   # y centre for treasuries

P2_ROW_Y  = 155    # centre-y of P2 pit row
P1_ROW_Y  = 445    # centre-y of P1 pit row

PIT_RW,   PIT_RH   = 50, 42      # regular pit semi-axes (px) – bigger than before
TREAS_RW, TREAS_RH = 54, 98      # treasury semi-axes (px)

P2_TREAS_CX = 64                        # centre-x of P2 treasury
P1_TREAS_CX = WIN_W - 64               # centre-x of P1 treasury

# 6 pit column centres, left → right (P1 pits 0-5)
_GAP    = 30                                         # gap between treasury edge and first pit edge
_PIT0   = P2_TREAS_CX + TREAS_RW + _GAP + PIT_RW   # ≈ 198
_PIT5   = P1_TREAS_CX - TREAS_RW - _GAP - PIT_RW   # ≈ 782
_STEP   = (_PIT5 - _PIT0) // 5                      # ≈ 116
PIT_CX  = [_PIT0 + i * _STEP for i in range(6)]

STONE_R = 7    # stone radius (px) – slightly bigger

# ── colours ───────────────────────────────────────────────────────────────────
C_BG         = ( 30,  18,   8)
C_BOARD      = (100,  64,  30)
C_BOARD_MID  = ( 88,  56,  24)    # centre stripe colour
C_PIT        = (190, 150, 100)
C_PIT_RIM    = ( 80,  48,  18)
C_TREAS      = (210, 180, 135)
C_TREAS_RIM  = ( 80,  48,  18)
C_STONE      = (245, 220, 175)
C_STONE_SHD  = (145, 108,  58)
C_GOLD       = (255, 218,   0)
C_GOLD_DIM   = (195, 158,   0)
C_BLUE       = ( 60, 130, 220)
C_RED        = (215,  50,  50)
C_GREEN      = ( 60, 195,  80)
C_TEXT       = (238, 228, 205)
C_TEXT_DIM   = (140, 122,  90)
C_BTN        = (135,  92,  42)
C_BTN_HOV    = (175, 130,  68)
C_BTN_TXT    = (242, 232, 210)
C_P1         = ( 75, 155, 230)
C_P2         = (225,  72,  72)
C_HINT       = (  0, 210, 200)   # cyan glow for AI hint suggestion

# ── stone offset helpers ──────────────────────────────────────────────────────

def _stone_offsets(n: int, rw: int, rh: int) -> list:
    """Return n (dx,dy) offsets packed into an ellipse of semi-axes rw × rh."""
    if n == 0:
        return []
    d    = STONE_R * 2 + 3
    cols = max(1, int(rw * 1.8 // d))
    rows = math.ceil(n / cols)
    out  = []
    for i in range(n):
        r, c     = divmod(i, cols)
        cnt_row  = min(cols, n - r * cols)
        x = (c - (cnt_row - 1) / 2.0) * d
        y = (r - (rows    - 1) / 2.0) * d * rh / max(rw, 1)
        out.append((round(x), round(y)))
    return out

_OFF_CACHE: dict = {}

def _offsets(idx: int, n: int) -> list:
    key = (idx, n)
    if key not in _OFF_CACHE:
        if idx in (P1_TREASURY, P2_TREASURY):
            _OFF_CACHE[key] = _stone_offsets(n, rw=38, rh=72)
        else:
            _OFF_CACHE[key] = _stone_offsets(n, rw=34, rh=26)
    return _OFF_CACHE[key]

# ── pit centre lookup ─────────────────────────────────────────────────────────

def pit_center(idx: int) -> tuple:
    if idx == P1_TREASURY: return (P1_TREAS_CX, BOARD_MID)
    if idx == P2_TREASURY: return (P2_TREAS_CX, BOARD_MID)
    if idx in P1_PITS:     return (PIT_CX[idx], P1_ROW_Y)
    k = idx - 7
    return (PIT_CX[5 - k], P2_ROW_Y)   # pit 7→col5, pit 12→col0

# ── Button ────────────────────────────────────────────────────────────────────

class Button:
    def __init__(self, x, y, w, h, text, font):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.font = font

    def draw(self, surf, hovered=False):
        c = C_BTN_HOV if hovered else C_BTN
        pygame.draw.rect(surf, c,         self.rect, border_radius=10)
        pygame.draw.rect(surf, C_PIT_RIM, self.rect, 2, border_radius=10)
        lbl = self.font.render(self.text, True, C_BTN_TXT)
        surf.blit(lbl, lbl.get_rect(center=self.rect.center))

    def hit(self, pos) -> bool:
        return self.rect.collidepoint(pos)

# ── main GUI ──────────────────────────────────────────────────────────────────

class MangalaGUI:

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption(TITLE)
        self.clock  = pygame.time.Clock()
        self._quit  = False

        self.f_title  = pygame.font.SysFont("Georgia",  42, bold=True)
        self.f_large  = pygame.font.SysFont("Georgia",  26, bold=True)
        self.f_mid    = pygame.font.SysFont("Verdana",  19)
        self.f_small  = pygame.font.SysFont("Verdana",  14)
        self.f_tiny   = pygame.font.SysFont("Verdana",  11)
        self.f_banner = pygame.font.SysFont("Georgia",  34, bold=True)

        self._move_log: list = []   # list of (player, text) tuples, newest last

    # ── event pump ────────────────────────────────────────────────────────────

    def _pump(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self._quit = True
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self._quit = True

    def _wait(self, ms: int):
        """Blocking wait, pumping quit events so the window stays responsive."""
        deadline = pygame.time.get_ticks() + ms
        while pygame.time.get_ticks() < deadline:
            self._pump()
            if self._quit:
                return
            pygame.time.delay(16)

    # ── drawing ───────────────────────────────────────────────────────────────

    def _draw_pit(self, idx: int, n: int, hl=None):
        """
        Draw one pit or treasury.
        hl: None | 'gold' | 'blue' | 'red' | 'green'
        """
        cx, cy   = pit_center(idx)
        is_t     = idx in (P1_TREASURY, P2_TREASURY)
        rw       = TREAS_RW if is_t else PIT_RW
        rh       = TREAS_RH if is_t else PIT_RH
        fill     = C_TREAS   if is_t else C_PIT
        rim      = C_TREAS_RIM if is_t else C_PIT_RIM
        rect     = pygame.Rect(cx - rw, cy - rh, rw * 2, rh * 2)

        # Outer glow ring
        ring_col = {'gold': C_GOLD, 'blue': C_BLUE, 'red': C_RED,
                    'green': C_GREEN, 'cyan': C_HINT}.get(hl)
        if ring_col:
            pygame.draw.ellipse(self.screen, ring_col, rect.inflate(12, 12))

        # Shadow
        shadow_rect = rect.move(3, 4)
        pygame.draw.ellipse(self.screen, (20, 12, 4), shadow_rect)

        # Pit body
        pygame.draw.ellipse(self.screen, fill, rect)
        pygame.draw.ellipse(self.screen, rim,  rect, 3)

        # Stones
        for dx, dy in _offsets(idx, n):
            sx, sy = cx + dx, cy + dy
            pygame.draw.circle(self.screen, C_STONE_SHD, (sx + 2, sy + 2), STONE_R)
            pygame.draw.circle(self.screen, C_STONE,     (sx,     sy),     STONE_R)

        # Stone count label
        cnt_lbl = self.f_small.render(str(n), True, C_PIT_RIM)
        self.screen.blit(cnt_lbl, cnt_lbl.get_rect(center=(cx, cy)))

        if is_t:
            name = "P2 Hazine" if idx == P2_TREASURY else "P1 Hazine"
            nl = self.f_tiny.render(name, True, C_TEXT_DIM)
            self.screen.blit(nl, nl.get_rect(center=(cx, cy + rh + 14)))
        else:
            in_p2 = idx in P2_PITS
            iy    = cy - rh - 13 if in_p2 else cy + rh + 13
            ic    = C_P2 if in_p2 else C_P1
            idxc = idx
            if idx < 6:
                idxc = idx + 1
            il    = self.f_tiny.render(str(idxc), True, ic)
            self.screen.blit(il, il.get_rect(center=(cx, iy)))

    def _draw_frame(self, pits: list, hl: dict = None, msg: str = "",
                    sub: str = ""):
        """Full redraw: background, board, all pits, status bar.
        sub: optional second line in status bar (shown smaller, dimmer).
        """
        if hl is None:
            hl = {}

        self.screen.fill(C_BG)

        # Title bar
        t = self.f_title.render(TITLE, True, C_TEXT)
        self.screen.blit(t, t.get_rect(center=(WIN_W // 2, TITLE_H // 2)))

        # Board panel
        board_rect = pygame.Rect(0, BOARD_TOP, WIN_W, BOARD_BOT - BOARD_TOP)
        pygame.draw.rect(self.screen, C_BOARD, board_rect)

        # Subtle centre stripe (separates the two sides)
        stripe_rect = pygame.Rect(0, BOARD_MID - 8, WIN_W, 16)
        pygame.draw.rect(self.screen, C_BOARD_MID, stripe_rect)

        # Player row labels with coloured accent
        p2_label_y = BOARD_TOP + 16
        p1_label_y = BOARD_BOT - 16
        p2l = self.f_mid.render("PLAYER  2", True, C_P2)
        self.screen.blit(p2l, p2l.get_rect(center=(WIN_W // 2, p2_label_y)))
        p1l = self.f_mid.render("PLAYER  1", True, C_P1)
        self.screen.blit(p1l, p1l.get_rect(center=(WIN_W // 2, p1_label_y)))

        # All 14 pits
        for i in range(14):
            self._draw_pit(i, pits[i], hl.get(i))

        # Score difference indicator between treasuries
        s1, s2 = pits[P1_TREASURY], pits[P2_TREASURY]
        diff = s1 - s2
        if diff != 0:
            who  = "P1" if diff > 0 else "P2"
            col  = C_P1 if diff > 0 else C_P2
            dlbl = self.f_small.render(f"{who} +{abs(diff)}", True, col)
            self.screen.blit(dlbl, dlbl.get_rect(center=(WIN_W // 2, BOARD_MID)))

        # Status bar
        status_bg = pygame.Rect(0, BOARD_BOT, WIN_W, STATUS_H)
        pygame.draw.rect(self.screen, (18, 10, 4), status_bg)
        pygame.draw.line(self.screen, C_PIT_RIM, (0, BOARD_BOT), (WIN_W, BOARD_BOT), 2)

        if msg:
            cy_msg = BOARD_BOT + (STATUS_H // 2 if not sub else STATUS_H // 3)
            sl = self.f_mid.render(msg, True, C_TEXT)
            self.screen.blit(sl, sl.get_rect(center=(WIN_W // 2, cy_msg)))
        if sub:
            sl2 = self.f_small.render(sub, True, C_TEXT_DIM)
            self.screen.blit(sl2, sl2.get_rect(center=(WIN_W // 2, BOARD_BOT + STATUS_H * 2 // 3)))

        # Move-log panel
        log_y = BOARD_BOT + STATUS_H
        pygame.draw.rect(self.screen, (12, 7, 2),
                         pygame.Rect(0, log_y, WIN_W, LOG_H))
        pygame.draw.line(self.screen, C_PIT_RIM,
                         (0, log_y), (WIN_W, log_y), 1)

        # Header
        hdr = self.f_tiny.render("LAST MOVES", True, C_TEXT_DIM)
        self.screen.blit(hdr, (14, log_y + 5))

        # Up to 5 most-recent entries, newest at the top
        LINE_H  = 18
        entries = self._move_log[-5:]   # keep last 5
        for row, (player, text) in enumerate(reversed(entries)):
            col  = C_P1 if player == 0 else C_P2
            # Dim older entries so the newest stands out
            alpha = 255 - row * 38
            r, g, b = col
            faded = (max(r * alpha // 255, 0),
                     max(g * alpha // 255, 0),
                     max(b * alpha // 255, 0))
            lbl = self.f_tiny.render(text, True, faded)
            self.screen.blit(lbl, (14, log_y + 22 + row * LINE_H))

    def _event_banner(self, pits: list, hl: dict, text: str, color,
                      ms: int):
        """Flash a large event banner over the board centre for `ms` ms."""
        overlay = pygame.Surface((WIN_W, 76), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 175))
        deadline = pygame.time.get_ticks() + ms
        while pygame.time.get_ticks() < deadline and not self._quit:
            self._draw_frame(pits, hl, "")
            self.screen.blit(overlay, (0, BOARD_MID - 38))
            lbl = self.f_banner.render(text, True, color)
            self.screen.blit(lbl, lbl.get_rect(center=(WIN_W // 2, BOARD_MID)))
            pygame.display.flip()
            self._pump()
            pygame.time.delay(16)

    # ── hit testing ───────────────────────────────────────────────────────────

    def _pit_at(self, mx: int, my: int) -> int:
        """Return pit index under (mx, my), or -1."""
        for i in range(14):
            cx, cy = pit_center(i)
            is_t   = i in (P1_TREASURY, P2_TREASURY)
            rw     = TREAS_RW if is_t else PIT_RW
            rh     = TREAS_RH if is_t else PIT_RH
            if ((mx - cx) / rw) ** 2 + ((my - cy) / rh) ** 2 <= 1.0:
                return i
        return -1

    # ── animated move ─────────────────────────────────────────────────────────

    def _animate(self, state: GameState, pit: int, msg: str) -> tuple:
        """
        Visually replay the move stone-by-stone.  Returns authoritative
        (new_state, events) from apply_move().
        """
        pits             = state.pits[:]
        player           = state.current_player
        stones           = pits[pit]
        opp_t            = OPP_TREASURY[player]
        own_t            = PLAYER_TREASURY[player]
        own_pits_s       = set(PLAYER_PITS[player])
        opp_s            = set(PLAYER_PITS[1 - player])
        # Own pits that were empty at the start of the move (for empty-hole capture)
        own_empty_before = {i for i in own_pits_s if state.pits[i] == 0}

        # 1 — lift from source pit
        if stones > 1:
            pits[pit] = 1
            to_sow = stones - 1
        else:
            pits[pit] = 0
            to_sow = 1

        self._draw_frame(pits, {pit: 'blue'}, msg,
                         sub=f"Picked up {to_sow} stone{'s' if to_sow != 1 else ''} from pit {pit}")
        pygame.display.flip()
        self._wait(STONE_DELAY + 80)

        # 2 — sow counterclockwise, one stone per frame
        idx = pit
        for sown in range(to_sow):
            if self._quit:
                break
            idx = (idx + 1) % TOTAL
            if idx == opp_t:
                idx = (idx + 1) % TOTAL
            pits[idx] += 1
            remaining = to_sow - sown - 1
            sub_msg = (f"Sowing...  {remaining} left in hand"
                       if remaining > 0 else "Last stone placed")
            self._draw_frame(pits, {pit: 'blue', idx: 'gold'}, msg,
                             sub=sub_msg)
            pygame.display.flip()
            self._wait(STONE_DELAY)

        # 3 — capture animations (mirrors game.py capture rules exactly)
        last     = idx
        opposite = 12 - last   # the pit directly across the board

        # Rule 1: regular capture — last stone on opponent's side, count now even
        if last in opp_s and pits[last] % 2 == 0 and pits[last] > 0:
            if not self._quit:
                self._draw_frame(pits, {last: 'red'}, msg,
                                 sub=f"Capturing {pits[last]} stones from pit {last}!")
                pygame.display.flip()
                self._wait(CAPTURE_DELAY)
            pits[own_t] += pits[last]
            pits[last] = 0
            if not self._quit:
                self._draw_frame(pits, {own_t: 'green'}, msg,
                                 sub="Stones added to treasury!")
                pygame.display.flip()
                self._wait(STONE_DELAY + 60)

        # Rule 2: empty-hole capture — last stone lands in own previously-empty pit
        #         AND the opposite opponent pit has stones
        elif (last in own_pits_s
              and last in own_empty_before
              and pits[last] == 1
              and pits[opposite] > 0):
            if not self._quit:
                self._draw_frame(pits, {last: 'gold', opposite: 'red'}, msg,
                                 sub=f"Empty-hole capture! Taking pit {last} + pit {opposite}")
                pygame.display.flip()
                self._wait(CAPTURE_DELAY)
            total = pits[last] + pits[opposite]
            pits[own_t] += total
            pits[last] = 0
            pits[opposite] = 0
            if not self._quit:
                self._draw_frame(pits, {own_t: 'green'}, msg,
                                 sub=f"{total} stones added to treasury!")
                pygame.display.flip()
                self._wait(STONE_DELAY + 60)

        # 4 — authoritative result
        return apply_move(state, pit)

    # ── status text ───────────────────────────────────────────────────────────

    def _status(self, state: GameState, thinking=False) -> str:
        p1, p2 = score(state)
        base = f"P1 Hazine: {p1}   |   P2 Hazine: {p2}"
        if thinking:
            return f"{base}   |   AI is thinking..."
        if state.game_over:
            return base
        return f"{base}   |   Player {state.current_player + 1}'s turn"

    # ── screens ───────────────────────────────────────────────────────────────

    def _start_screen(self) -> tuple:
        """Returns (players, coach_side) or None to quit.
        coach_side is None for normal modes, 0 or 1 for Analysis Mode.
        """
        bx, bw, bh = WIN_W // 2 - 150, 300, 52
        btns = [
            Button(bx, 185, bw, bh, "Human vs Human",  self.f_large),
            Button(bx, 255, bw, bh, "Human vs AI",     self.f_large),
            Button(bx, 325, bw, bh, "AI vs AI",        self.f_large),
            Button(bx, 395, bw, bh, "Analysis Mode",   self.f_large),
        ]

        while not self._quit:
            mx, my = pygame.mouse.get_pos()
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    return None
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    return None
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if btns[0].hit((mx, my)):
                        return (["human", "human"], None)
                    if btns[1].hit((mx, my)):
                        side = self._pick_side()
                        if side is None:
                            continue
                        players = ["ai", "ai"]
                        players[side] = "human"
                        return (players, None)
                    if btns[2].hit((mx, my)):
                        return (["ai", "ai"], None)
                    if btns[3].hit((mx, my)):
                        side = self._pick_side()
                        if side is None:
                            continue
                        return (["human", "human"], side)

            self.screen.fill(C_BG)

            t = self.f_title.render(TITLE, True, C_TEXT)
            self.screen.blit(t, t.get_rect(center=(WIN_W // 2, 95)))

            sub = self.f_mid.render("Choose a game mode", True, C_TEXT_DIM)
            self.screen.blit(sub, sub.get_rect(center=(WIN_W // 2, 148)))

            for b in btns:
                b.draw(self.screen, b.hit((mx, my)))

            # Description for Analysis Mode
            desc = self.f_tiny.render(
                "Analysis Mode: play both sides, AI hints, undo/redo/pass",
                True, C_TEXT_DIM)
            self.screen.blit(desc, desc.get_rect(center=(WIN_W // 2, 458)))

            hint = self.f_tiny.render("ESC to quit", True, C_TEXT_DIM)
            self.screen.blit(hint, hint.get_rect(center=(WIN_W // 2, 480)))

            pygame.display.flip()
            self.clock.tick(FPS)

        return None

    def _pick_side(self) -> int:
        """Returns 0 (P1), 1 (P2), or None (back)."""
        bx, bw, bh = WIN_W // 2 - 150, 300, 52
        btns = [
            Button(bx, 248, bw, bh, "Play as Player 1", self.f_large),
            Button(bx, 318, bw, bh, "Play as Player 2", self.f_large),
        ]
        while not self._quit:
            mx, my = pygame.mouse.get_pos()
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self._quit = True; return None
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    return None
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if btns[0].hit((mx, my)): return 0
                    if btns[1].hit((mx, my)): return 1

            self.screen.fill(C_BG)
            q = self.f_large.render("Which side do you want to play?", True, C_TEXT)
            self.screen.blit(q, q.get_rect(center=(WIN_W // 2, 192)))
            back = self.f_tiny.render("ESC to go back", True, C_TEXT_DIM)
            self.screen.blit(back, back.get_rect(center=(WIN_W // 2, 400)))
            for b in btns:
                b.draw(self.screen, b.hit((mx, my)))
            pygame.display.flip()
            self.clock.tick(FPS)
        return None

    def _end_screen(self, state: GameState) -> bool:
        """Shows win overlay. Returns True = play again, False = quit."""
        p1, p2 = score(state)
        if state.winner == -1:
            headline = f"It's a Tie!   ({p1} vs {p2})"
            col = C_GOLD
        else:
            headline = f"Player {state.winner + 1} Wins!   ({p1} vs {p2})"
            col = C_P1 if state.winner == 0 else C_P2

        bw, bh = 155, 52
        again_btn = Button(WIN_W // 2 - bw - 10, WIN_H // 2 + 58, bw, bh, "Play Again", self.f_large)
        quit_btn  = Button(WIN_W // 2 + 10,       WIN_H // 2 + 58, bw, bh, "Quit",       self.f_large)

        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 172))

        while not self._quit:
            mx, my = pygame.mouse.get_pos()
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: return False
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE: return False
                    if ev.key == pygame.K_r:      return True
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if again_btn.hit((mx, my)): return True
                    if quit_btn.hit((mx, my)):  return False

            self._draw_frame(state.pits, {}, "")
            self.screen.blit(overlay, (0, 0))

            wl = self.f_title.render(headline, True, col)
            self.screen.blit(wl, wl.get_rect(center=(WIN_W // 2, WIN_H // 2)))
            hint = self.f_small.render("Press R to play again or ESC to quit", True, C_TEXT_DIM)
            self.screen.blit(hint, hint.get_rect(center=(WIN_W // 2, WIN_H // 2 + 42)))
            again_btn.draw(self.screen, again_btn.hit((mx, my)))
            quit_btn.draw(self.screen, quit_btn.hit((mx, my)))
            pygame.display.flip()
            self.clock.tick(FPS)

        return False

    # ── game loop ─────────────────────────────────────────────────────────────

    def _log_move(self, player: int, pit: int, events: dict):
        """Append one entry to the move log."""
        parts = [f"P{player + 1}  pit {pit}"]
        if events['capture'] > 0:
            parts.append(f"captured {events['capture']}")
        if events['extra_turn']:
            parts.append("extra turn")
        self._move_log.append((player, "   ".join(parts)))

    def _game(self, players: list, coach_side=None) -> bool:
        """Play one full game. Returns True = play again, False = quit.

        coach_side: None = normal mode; 0 or 1 = Analysis Mode where that
        player gets AI hint highlights and undo/redo/pass buttons appear.
        """
        self._move_log = []
        state    = initial_state()
        ai_ai    = all(k == "ai" for k in players)
        invalid  : dict = {}   # pit_idx -> expiry tick (ms)
        last_hl  : dict = {}   # source pit of last move, shown in red

        # ── State history (used in Analysis Mode for undo / redo) ────────────
        # Each entry: (GameState, log_snapshot).  history[hist_idx] = current.
        history  = [(state, [])]
        hist_idx = 0

        # ── AI hint (Analysis Mode) ───────────────────────────────────────────
        # A daemon thread fills _hint[0] (pit index) and sets _hint[1] = True.
        # A fresh container is created on every new hint request; stale threads
        # write into the discarded container and are ignored automatically.
        _hint             = [None, False]   # [pit_index, ready]
        hint_for_state_id = None            # id(state) when hint was requested

        # ── In-game buttons (Analysis Mode only) ─────────────────────────────
        if coach_side is not None:
            bw, bh = 80, 36
            btn_y  = BOARD_BOT + (STATUS_H - bh) // 2
            undo_btn = Button(WIN_W - 20 - bw * 3 - 16, btn_y, bw, bh, "Undo", self.f_small)
            redo_btn = Button(WIN_W - 20 - bw * 2 -  8, btn_y, bw, bh, "Redo", self.f_small)
            pass_btn = Button(WIN_W - 20 - bw,           btn_y, bw, bh, "Pass", self.f_small)
        else:
            undo_btn = redo_btn = pass_btn = None

        # Helper: draw a button that may be active or dimmed.
        def _draw_btn(btn, active: bool, hovered: bool):
            if active:
                btn.draw(self.screen, hovered)
            else:
                pygame.draw.rect(self.screen, (55, 35, 16), btn.rect, border_radius=10)
                pygame.draw.rect(self.screen, (42, 26, 10), btn.rect, 2, border_radius=10)
                lbl = self.f_small.render(btn.text, True, (95, 72, 44))
                self.screen.blit(lbl, lbl.get_rect(center=btn.rect.center))

        # Helper: start the AI hint thread for the current state.
        def _start_hint(s):
            nonlocal _hint, hint_for_state_id
            _hint             = [None, False]
            hint_for_state_id = id(s)
            c = _hint  # thread holds this ref; after _clear_hint replaces _hint,
                       # the thread writes to the old (dead) container — ignored.
            def _worker(state_snap, container):
                container[0] = ai_module.best_move(state_snap)
                container[1] = True
            threading.Thread(target=_worker, args=(s, c), daemon=True).start()

        # Helper: invalidate any running hint (position changed).
        def _clear_hint():
            nonlocal _hint, hint_for_state_id
            _hint             = [None, False]
            hint_for_state_id = None

        while not self._quit:
            if is_terminal(state):
                return self._end_screen(state)

            player  = state.current_player
            kind    = players[player]
            mv_set  = set(legal_moves(state))
            msg     = self._status(state)

            # ── AI turn ───────────────────────────────────────────────────────
            if kind == "ai":
                self._draw_frame(state.pits, last_hl,
                                 self._status(state, thinking=True))
                pygame.display.flip()
                self._pump()

                pit = ai_module.best_move(state)
                new_state, events = self._animate(state, pit, msg)
                self._log_move(player, pit, events)
                state   = new_state
                last_hl = {pit: 'red'}

                if events['capture'] > 0 and events['extra_turn']:
                    self._event_banner(state.pits, last_hl,
                                       f"Captured {events['capture']} stones  +  Extra Turn!",
                                       C_GOLD, EVENT_BANNER)
                elif events['capture'] > 0:
                    self._event_banner(state.pits, last_hl,
                                       f"Captured {events['capture']} stone{'s' if events['capture'] != 1 else ''}!",
                                       C_RED, EVENT_BANNER)
                elif events['extra_turn']:
                    self._event_banner(state.pits, last_hl,
                                       "Extra Turn!", C_GREEN, EVENT_BANNER)

                self._draw_frame(state.pits, last_hl, self._status(state))
                pygame.display.flip()
                self._wait(AI_PAUSE_AIAI if ai_ai else AI_PAUSE_HUMAN)
                continue

            # ── Human turn ────────────────────────────────────────────────────

            # Kick off AI hint thread if it's the coach side's turn
            if coach_side is not None and player == coach_side:
                if hint_for_state_id != id(state):
                    _start_hint(state)

            now     = pygame.time.get_ticks()
            invalid = {k: v for k, v in invalid.items() if v > now}

            hl = {}
            hl.update(last_hl)
            hl.update({m: 'gold' for m in mv_set})
            hl.update({k: 'red'  for k in invalid})

            # Overlay cyan hint ring (replaces gold on the suggested pit)
            hint_sub = ""
            if coach_side is not None and player == coach_side:
                if _hint[1] and _hint[0] is not None:
                    hl[_hint[0]] = 'cyan'
                    hint_sub = f"AI suggests: pit {_hint[0]}"
                else:
                    hint_sub = "AI is thinking..."

            self._draw_frame(state.pits, hl, msg, sub=hint_sub)

            # Draw analysis buttons over the status bar
            if coach_side is not None:
                mx_now, my_now = pygame.mouse.get_pos()
                can_undo = hist_idx > 0
                can_redo = hist_idx < len(history) - 1
                _draw_btn(undo_btn, can_undo, undo_btn.hit((mx_now, my_now)))
                _draw_btn(redo_btn, can_redo, redo_btn.hit((mx_now, my_now)))
                pass_btn.draw(self.screen, pass_btn.hit((mx_now, my_now)))

            pygame.display.flip()

            chosen  = None
            do_undo = False
            do_redo = False
            do_pass = False

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self._quit = True
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        self._quit = True
                    if coach_side is not None:
                        mods = pygame.key.get_mods()
                        if ev.key == pygame.K_z and (mods & pygame.KMOD_CTRL):
                            do_undo = True
                        if ev.key == pygame.K_y and (mods & pygame.KMOD_CTRL):
                            do_redo = True
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx, my = ev.pos
                    hit = self._pit_at(mx, my)
                    if hit in mv_set:
                        chosen = hit
                    elif hit >= 0:
                        invalid[hit] = pygame.time.get_ticks() + 450
                    # Analysis buttons
                    if coach_side is not None:
                        if hist_idx > 0 and undo_btn.hit((mx, my)):
                            do_undo = True
                        elif hist_idx < len(history) - 1 and redo_btn.hit((mx, my)):
                            do_redo = True
                        elif pass_btn.hit((mx, my)):
                            do_pass = True

            # ── Process action ─────────────────────────────────────────────────
            if do_undo and hist_idx > 0:
                hist_idx -= 1
                state, log_snap = history[hist_idx]
                self._move_log   = list(log_snap)
                last_hl = {}
                _clear_hint()

            elif do_redo and hist_idx < len(history) - 1:
                hist_idx += 1
                state, log_snap = history[hist_idx]
                self._move_log   = list(log_snap)
                last_hl = {}
                _clear_hint()

            elif do_pass:
                p_pass = state.current_player
                passed_state = GameState(
                    pits=state.pits[:],
                    current_player=1 - p_pass,
                    game_over=state.game_over,
                    winner=state.winner,
                )
                self._move_log.append((p_pass, f"P{p_pass + 1}   passed"))
                state   = passed_state
                last_hl = {}
                history  = history[:hist_idx + 1]
                history.append((state, list(self._move_log)))
                hist_idx = len(history) - 1
                _clear_hint()

            elif chosen is not None:
                new_state, events = self._animate(state, chosen, msg)
                self._log_move(player, chosen, events)
                state   = new_state
                last_hl = {chosen: 'red'}
                history  = history[:hist_idx + 1]
                history.append((state, list(self._move_log)))
                hist_idx = len(history) - 1
                _clear_hint()

                if events['capture'] > 0 and events['extra_turn']:
                    self._event_banner(state.pits, last_hl,
                                       f"Captured {events['capture']} stones  +  Extra Turn!",
                                       C_GOLD, EVENT_BANNER)
                elif events['capture'] > 0:
                    self._event_banner(state.pits, last_hl,
                                       f"Captured {events['capture']} stone{'s' if events['capture'] != 1 else ''}!",
                                       C_RED, EVENT_BANNER)
                elif events['extra_turn']:
                    self._event_banner(state.pits, last_hl,
                                       "Extra Turn!", C_GREEN, EVENT_BANNER)

            self.clock.tick(FPS)

        return False

    # ── top-level run ─────────────────────────────────────────────────────────

    def run(self):
        while not self._quit:
            result = self._start_screen()
            if result is None:
                break
            players, coach_side = result
            play_again = self._game(players, coach_side)
            if not play_again:
                break
        pygame.quit()


def main() -> None:
    MangalaGUI().run()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
