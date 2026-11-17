"""Fensterauswahl ohne Verwechslung von Spielername, Browser und Bot-Fenster."""
def find_game_window(part, gui, processes, own_pid):
    candidates = []
    needle = part.casefold()
    def visit(hwnd, unused):
        if not gui.IsWindowVisible(hwnd):
            return
        title = gui.GetWindowText(hwnd)
        if not title or needle not in title.casefold():
            return
        try:
            if processes.GetWindowThreadProcessId(hwnd)[1] == own_pid:
                return
            window_class = gui.GetClassName(hwnd).casefold()
            if window_class.startswith(("tk", "chrome", "cabinetwclass", "applicationframewindow")):
                return
            if needle == "verzum" and window_class != "sdl_app":
                return
            rect = gui.GetWindowRect(hwnd)
            if gui.IsIconic(hwnd) or (rect[2] - rect[0] > 200 and rect[3] - rect[1] > 200):
                candidates.append((hwnd, title, rect))
        except Exception:
            return
    gui.EnumWindows(visit, None)
    candidates.sort(key=lambda x: (not x[1].casefold().startswith(needle),
                                   -(x[2][2] - x[2][0]) * (x[2][3] - x[2][1])))
    return candidates[0] if candidates else None
