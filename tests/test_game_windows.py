import unittest
from sirosix.game_windows import find_game_window


class WindowsFixture:
    def __init__(self, windows):
        self.windows = windows
    def EnumWindows(self, fn, data):
        for handle in self.windows:
            fn(handle, data)
    def IsWindowVisible(self, handle):
        return True
    def GetWindowText(self, handle):
        return self.windows[handle][0]
    def GetWindowThreadProcessId(self, handle):
        return 1, self.windows[handle][2]
    def GetClassName(self, handle):
        return self.windows[handle][1]
    def GetWindowRect(self, handle):
        return 0, 0, 1920, 1080
    def IsIconic(self, handle):
        return False


class GameWindowTests(unittest.TestCase):
    def test_sirosix_player_name_remains_a_valid_game_window(self):
        gui = WindowsFixture({1: ("SiroSix Verzum Bot", "TkTopLevel", 2),
                              2: ("Verzum - SiroSix", "SDL_app", 3),
                              3: ("Verzum Forum", "Chrome_WidgetWin_1", 4)})
        self.assertEqual(find_game_window("Verzum", gui, gui, 2)[0], 2)

    def test_rubinum_bot_and_browser_are_never_chosen_as_game(self):
        gui = WindowsFixture({1: ("SiroSix Rubinum Bot", "TkTopLevel", 2),
                              2: ("Rubinum - Spieler", "YmirClient", 3),
                              3: ("Rubinum Browser", "Chrome_WidgetWin_1", 4)})
        self.assertEqual(find_game_window("Rubinum", gui, gui, 2)[0], 2)
        del gui.windows[2]
        self.assertIsNone(find_game_window("Rubinum", gui, gui, 2))
