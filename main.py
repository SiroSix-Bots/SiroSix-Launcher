if __name__ == "__main__":
    import sys
    from pathlib import Path
    if len(sys.argv) == 5 and sys.argv[1] == "--apply-update":
        try:
            from sirosix.updates import apply_update
            apply_update(Path(sys.argv[0]), sys.argv[2], int(sys.argv[3]), sys.argv[4])
        except Exception:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, "Das Launcher-Update konnte nicht installiert werden. Die bisherige Version wurde soweit möglich wiederhergestellt.", "SiroSix Update", 0x10)
    else:
        from sirosix.gui import main
        main()
