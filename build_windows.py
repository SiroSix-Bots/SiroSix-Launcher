"""Nuitka-Build des Launchers. Keine Veröffentlichung oder Anmeldung."""
from pathlib import Path
import subprocess
import sys
import os

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("SIROSIX_BUILD_DIR", ROOT.parent / "builds"))
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    from sirosix import VERSION
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    icon = assets / "sirosix.ico"
    if not icon.exists():
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new("RGBA", (256, 256), "#101925")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((10, 10, 246, 246), radius=55, fill="#5679f8")
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 112)
        draw.text((128, 119), "S6", anchor="mm", font=font, fill="#ffffff")
        image.save(icon, sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
    subprocess.run([
        sys.executable, "-m", "nuitka", "--mode=onefile", "--mingw64", "--assume-yes-for-downloads",
        "--jobs=" + str(os.cpu_count() or 2), "--lto=no", "--nofollow-import-to=win32com.test,win32com.demos",
        "--enable-plugin=tk-inter", "--include-package-data=customtkinter", "--include-package=sirosix",
        "--include-package=win32com.client", "--include-module=win32timezone", "--windows-console-mode=disable",
        "--windows-icon-from-ico=" + str(icon), "--output-filename=SiroSix-Launcher.exe",
        "--include-data-files=" + str(icon) + "=assets/sirosix.ico",
        "--company-name=SiroSix", "--product-name=SiroSix Launcher", "--file-version=" + VERSION + ".0",
        "--output-dir=" + str(OUT / "launcher"), "--report=" + str(OUT / "launcher-report.xml"),
        str(ROOT / "main.py"),
    ], cwd=ROOT, check=True)
