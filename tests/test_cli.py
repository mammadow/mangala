"""Unit tests for the CLI interface (cli.py)."""
from unittest.mock import patch

from mangala.cli import (
    _ai_move,
    _play_turn,
    _prompt_human_side,
    _prompt_level,
    _prompt_move,
)
from mangala.engine import initial_state, legal_moves


def test_prompt_level() -> None:
    with patch("mangala.cli._read_line", side_effect=["easy"]):
        assert _prompt_level() == "easy"

    with patch("mangala.cli._read_line", side_effect=["2"]):  # "medium" is 2nd in LEVELS
        assert _prompt_level() == "medium"

    with patch("mangala.cli._read_line", side_effect=["invalid", ""]):
        assert _prompt_level(default="hard") == "hard"


def test_prompt_human_side() -> None:
    with patch("mangala.cli._read_line", side_effect=["1"]):
        assert _prompt_human_side() == 0

    with patch("mangala.cli._read_line", side_effect=["2"]):
        assert _prompt_human_side() == 1

    with patch("mangala.cli._read_line", side_effect=["q"]):
        assert _prompt_human_side() == -1


def test_prompt_move() -> None:
    moves = [1, 2, 3]
    with patch("mangala.cli._read_line", side_effect=["2"]):
        assert _prompt_move(0, moves) == 2

    with patch("mangala.cli._read_line", side_effect=["9", "1"]):  # 9 invalid, then 1
        assert _prompt_move(0, moves) == 1

    with patch("mangala.cli._read_line", side_effect=["quit"]):
        assert _prompt_move(0, moves) == -1


def test_ai_move() -> None:
    s = initial_state()
    pit = _ai_move(s, "easy")
    assert pit in legal_moves(s)


def test_play_turn_ai() -> None:
    s = initial_state()
    players = ["ai", "human"]
    new_s, aborted = _play_turn(s, players, "easy")
    assert not aborted
    assert new_s != s


def test_play_turn_human_abort() -> None:
    s = initial_state()
    players = ["human", "ai"]
    with patch("mangala.cli._prompt_move", return_value=-1):
        _new_s, aborted = _play_turn(s, players, "easy")
        assert aborted


def test_game_loop_aborts_cleanly() -> None:
    from mangala.cli import _game_loop
    with patch("mangala.cli._play_turn", return_value=(initial_state(), True)):
        _game_loop(["human", "human"], "easy", False)


def test_game_loop_runs_to_completion() -> None:
    from mangala.cli import _game_loop
    from mangala.engine import GameState
    term = GameState(pits=[0]*14, current_player=0, game_over=True, winner=0)
    with patch("mangala.cli.initial_state", return_value=term):
        _game_loop(["ai", "ai"], "easy", False)


def test_cli_main_quit() -> None:
    from mangala.cli import main
    with patch("mangala.cli._prompt_mode", return_value=0):
        main()


def test_cli_main_human_vs_ai() -> None:
    from mangala.cli import main
    with (
        patch("mangala.cli._prompt_mode", return_value=2),
        patch("mangala.cli._prompt_human_side", return_value=0),
        patch("mangala.cli._prompt_level", return_value="easy"),
        patch("mangala.cli._game_loop") as mock_loop,
    ):
        main()
        assert mock_loop.called


def test_read_line_exceptions() -> None:
    from mangala.cli import _read_line
    with patch("builtins.input", side_effect=EOFError):
        assert _read_line("prompt: ") == ""
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        assert _read_line("prompt: ") == ""


def test_prompt_mode_branches() -> None:
    from mangala.cli import _prompt_mode
    # Invalid input then valid
    with patch("mangala.cli._read_line", side_effect=["bad", "1"]):
        assert _prompt_mode() == 1
    # Mode 3
    with patch("mangala.cli._read_line", side_effect=["3"]):
        assert _prompt_mode() == 3
    # Quit
    with patch("mangala.cli._read_line", side_effect=["q"]):
        assert _prompt_mode() == 0


def test_prompt_human_side_invalid_then_valid() -> None:
    with patch("mangala.cli._read_line", side_effect=["invalid", "2"]):
        assert _prompt_human_side() == 1


def test_prompt_move_invalid_non_int() -> None:
    moves = [1, 2]
    with patch("mangala.cli._read_line", side_effect=["not-a-number", "2"]):
        assert _prompt_move(0, moves) == 2


def test_play_turn_with_capture_and_extra_turn() -> None:
    s = initial_state()
    # Mock apply_move returning capture > 0 and extra_turn = True
    fake_events = {"capture": 4, "extra_turn": True}
    with (
        patch("mangala.cli._ai_move", return_value=0),
        patch("mangala.cli.apply_move", return_value=(s, fake_events)),
    ):
        _new_s, aborted = _play_turn(s, ["ai", "human"], "easy")
        assert not aborted


def test_game_loop_tie_ending() -> None:
    from mangala.cli import _game_loop
    from mangala.engine import GameState
    tie_state = GameState(pits=[0]*14, current_player=0, game_over=True, winner=-1)
    tie_state.pits[6] = 24
    tie_state.pits[13] = 24
    with patch("mangala.cli.initial_state", return_value=tie_state):
        _game_loop(["ai", "ai"], "easy", False)


def test_cli_main_human_vs_human() -> None:
    from mangala.cli import main
    with patch("mangala.cli._prompt_mode", return_value=1), patch("mangala.cli._game_loop") as mock_loop:
        main()
        assert mock_loop.called


def test_cli_main_human_vs_ai_aborted_at_side() -> None:
    from mangala.cli import main
    with (
        patch("mangala.cli._prompt_mode", return_value=2),
        patch("mangala.cli._prompt_human_side", return_value=-1),
        patch("mangala.cli._game_loop") as mock_loop,
    ):
        main()
        assert not mock_loop.called


def test_cli_main_ai_vs_ai_and_keyboard_interrupt() -> None:
    from mangala.cli import main
    with (
        patch("mangala.cli._prompt_mode", return_value=3),
        patch("mangala.cli._prompt_level", return_value="easy"),
        patch("mangala.cli._game_loop", side_effect=KeyboardInterrupt),
    ):
        main()


def test_game_loop_watch_mode_sleep() -> None:
    from mangala.cli import _game_loop
    from mangala.engine import GameState

    term = GameState(pits=[0] * 14, current_player=0, game_over=True, winner=0)
    with (
        patch("mangala.cli._play_turn", side_effect=[(term, False)]),
        patch("time.sleep") as mock_sleep,
    ):
        _game_loop(["ai", "ai"], "easy", watch_mode=True)
        assert mock_sleep.called


def test_run_mui_protocol_full() -> None:
    import io

    from mangala.cli import run_mui_protocol

    # Feed sequence of standard protocol commands
    commands = "\n".join([
        "",  # empty line
        "mui",
        "uci",
        "isready",
        "muinewgame",
        "ucinewgame",
        "position startpos",
        "eval",
        "go depth 1",
        "position startpos moves 0 7 1",
        "go depth 1 movetime 50",
        "quit",
    ]) + "\n"

    in_stream = io.StringIO(commands)
    out_stream = io.StringIO()

    run_mui_protocol(in_stream=in_stream, out_stream=out_stream)
    output = out_stream.getvalue()

    assert "id name Turkish Mangala" in output
    assert "id author mammadow" in output
    assert "muiok" in output
    assert "uciok" in output
    assert "readyok" in output
    assert "eval " in output
    assert "bestmove " in output


def test_run_mui_protocol_terminal_state() -> None:
    import io

    from mangala.cli import run_mui_protocol

    # Test go on a terminal position where all pits are empty
    in_stream = io.StringIO("go\nquit\n")
    out_stream = io.StringIO()

    from mangala.engine import GameState
    term = GameState(pits=[0] * 14, current_player=0, game_over=True, winner=0)
    term.pits[6] = 25
    term.pits[13] = 23

    with patch("mangala.cli.initial_state", return_value=term):
        run_mui_protocol(in_stream=in_stream, out_stream=out_stream)
        output = out_stream.getvalue()
        assert "bestmove none" in output


def test_cli_main_mui_flags() -> None:
    from mangala.cli import main

    with patch("sys.argv", ["mangala", "--mui"]), patch("mangala.cli.run_mui_protocol") as mock_mui:
        main()
        assert mock_mui.called

    with patch("sys.argv", ["mangala", "-u"]), patch("mangala.cli.run_mui_protocol") as mock_mui:
        main()
        assert mock_mui.called

