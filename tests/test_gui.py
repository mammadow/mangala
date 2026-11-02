"""Unit tests for mangala.gui_pygame (optional GUI)."""
import os
import pytest

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


@pytest.mark.skipif(not PYGAME_AVAILABLE, reason="pygame extra not installed")
def test_gui_constants_and_geometry() -> None:
    from mangala import gui_pygame
    assert gui_pygame.WIN_W > 0
    assert gui_pygame.WIN_H > 0
    assert len(gui_pygame.PIT_CX) == 6
    assert gui_pygame.PIT_RW > 0
    assert gui_pygame.TITLE == "Turkish Mangala"


@pytest.mark.skipif(not PYGAME_AVAILABLE, reason="pygame extra not installed")
def test_gui_headless_init() -> None:
    # Set dummy video driver for headless test environments (CI, terminals)
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    from mangala.gui_pygame import MangalaGUI, Button, pit_center, P1_TREASURY, P2_TREASURY
    gui = MangalaGUI()
    assert gui.screen is not None
    assert gui.clock is not None
    assert not gui._quit

    # Test pit centers
    p1_treas = pit_center(P1_TREASURY)
    p2_treas = pit_center(P2_TREASURY)
    assert p1_treas[0] > p2_treas[0]

    # Test Button collision
    btn = Button(10, 10, 50, 50, "Test", gui.f_small)
    assert btn.hit((20, 20))
    assert not btn.hit((100, 100))
    pygame.quit()
