import tkinter as tk
from tkinter import scrolledtext
import threading
import subprocess
import requests
import zipfile
import os
import shutil
import time
import sys

# ── colours ──────────────────────────────────────────────────────────────────
BG       = "#0a0a0f"
PANEL    = "#11111a"
BORDER   = "#1e1e30"
GREEN    = "#00ff88"
GREEN2   = "#00cc66"
CYAN     = "#00e5ff"
DIM      = "#334455"
TEXT     = "#c8d8e8"
MUTED    = "#445566"
RED      = "#ff3355"

OPENMSX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openMSX")
OPENMSX_EXE = os.path.join(OPENMSX_DIR, "openmsx.exe")


def is_installed():
    return os.path.isfile(OPENMSX_EXE)


# ── install logic (runs in thread) ───────────────────────────────────────────
def run_install(log):
    try:
        log("◈ Fetching latest openMSX release…")
        response = requests.get("https://api.github.com/repos/openMSX/openMSX/releases/latest")
        data = response.json()

        zip_url = zip_name = None
        for asset in data["assets"]:
            if asset["name"].endswith("windows-vc-x64-bin.zip"):
                zip_url  = asset["browser_download_url"]
                zip_name = asset["name"]
                break

        if not zip_url:
            log("✗ Could not find Windows build in latest release.", RED)
            return

        log(f"◈ Downloading {zip_name}…")
        r = requests.get(zip_url, stream=True)
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(zip_name, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    log(f"  {pct}%", overwrite=True)

        log("◈ Extracting…")
        os.makedirs(OPENMSX_DIR, exist_ok=True)
        with zipfile.ZipFile(zip_name, "r") as z:
            z.extractall(OPENMSX_DIR)
        os.remove(zip_name)

        # Launch briefly to generate folder structure
        log("◈ Generating config structure…")
        proc = subprocess.Popen(OPENMSX_EXE)
        time.sleep(3)
        proc.terminate()

        machines_dir   = os.path.join(OPENMSX_DIR, "share", "machines")
        extensions_dir = os.path.join(OPENMSX_DIR, "share", "extensions")
        os.makedirs(machines_dir,   exist_ok=True)
        os.makedirs(extensions_dir, exist_ok=True)

        rom_urls = [
            "https://download.file-hunter.com/System%20ROMs/machines/panasonic/FS-A1GT_U20.bin",
            "https://download.file-hunter.com/System%20ROMs/machines/panasonic/fs-a1gt_firmware.rom",
            "https://download.file-hunter.com/System%20ROMs/machines/panasonic/fs-a1gt_kanjifont.rom",
        ]
        log("◈ Downloading machine ROMs…")
        for url in rom_urls:
            fname = url.split("/")[-1]
            log(f"  ↓ {fname}")
            r = requests.get(url, stream=True, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            with open(os.path.join(machines_dir, fname), "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)

        # Nextor ROM
        log("◈ Downloading Nextor ROM…")
        nextor_url  = "https://download.file-hunter.com/System%20ROMs/extensions/Nextor-2.1.1.SunriseIDE.ROM"
        nextor_name = "Nextor-2.1.1.SunriseIDE.ROM"
        r = requests.get(nextor_url, stream=True, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(os.path.join(extensions_dir, nextor_name), "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)

        # SunriseIDE XML
        xml = """<?xml version="1.0" ?>
<!DOCTYPE msxconfig SYSTEM 'msxconfig2.dtd'>
<msxconfig>
  <info>
    <name>Sunrise ATA-IDE</name>
    <manufacturer>Sunrise</manufacturer>
    <code/>
    <release_year>1995</release_year>
    <description>ATA-IDE interface with hard disk and Nextor ROM.</description>
    <type>external hard disk</type>
  </info>
  <devices>
    <primary slot="any">
      <secondary slot="any">
        <SunriseIDE id="Sunrise IDE">
          <mem base="0x0000" size="0x10000"/>
          <rom>
            <filename>Nextor-2.1.1.SunriseIDE.ROM</filename>
            <sha1>dca824d7b0ddf25c6e87a8098e97ab7489725f57</sha1>
            <sha1>d3a4375ff5f58cf59cc609dd41c90af285f033c2</sha1>
            <sha1>61cba1680ac6cb448dc3e8c710a43f4e7ab49457</sha1>
          </rom>
          <master>
            <type>IDEHD</type>
            <filename>boot.dsk</filename>
            <size>100</size>
          </master>
        </SunriseIDE>
      </secondary>
    </primary>
  </devices>
</msxconfig>"""
        with open(os.path.join(extensions_dir, "SunriseIDE_Nextor.xml"), "w") as f:
            f.write(xml)
        log("  ✓ SunriseIDE_Nextor.xml written")

        # Copy floppy.dsk
        floppy_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "floppy.dsk")
        floppy_dst = os.path.join(OPENMSX_DIR, "floppy.dsk")
        if os.path.isfile(floppy_src):
            shutil.copy2(floppy_src, floppy_dst)
            log("  ✓ floppy.dsk copied")
        else:
            log("  ⚠ floppy.dsk not found next to launcher — skipping", CYAN)

        # Brief launch to create persistent dir
        log("◈ Creating persistent storage folders…")
        proc = subprocess.Popen([OPENMSX_EXE, "-machine", "Panasonic_FS-A1GT", "-ext", "SunriseIDE_Nextor"])
        time.sleep(3)
        proc.terminate()

        # Download boot.dsk
        log("◈ Downloading boot.dsk (MSX-DOS 2.3)…")
        boot_url = "https://download.file-hunter.com/OS/MSXDOS2/MSXDOS23.DSK"
        boot_dir = os.path.join(
            os.environ.get("USERPROFILE", os.path.expanduser("~")),
            "Documents", "openMSX", "persistent", "SunriseIDE_Nextor", "untitled1"
        )
        os.makedirs(boot_dir, exist_ok=True)
        r = requests.get(boot_url, stream=True, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(os.path.join(boot_dir, "boot.dsk"), "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        log("  ✓ boot.dsk downloaded")

        log("", GREEN)
        log("✔ Installation complete!", GREEN)

    except Exception as e:
        log(f"✗ Error: {e}", RED)


# ── GUI ───────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("openMSX Toolbox")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._last_was_overwrite = False
        self._build_ui()
        self._refresh_state()

    def _build_ui(self):
        W = 620

        # ── scanline canvas header ──────────────────────────────────────────
        hdr = tk.Canvas(self, width=W, height=100, bg=BG, highlightthickness=0)
        hdr.pack(fill="x")
        # subtle scanlines
        for y in range(0, 100, 3):
            hdr.create_line(0, y, W, y, fill="#111118")
        # title text
        hdr.create_text(W//2, 38, text="openMSX TOOLBOX",
                        font=("Courier", 28, "bold"), fill=GREEN)
        hdr.create_text(W//2, 65, text="Panasonic FS-A1GT  ·  SunriseIDE  ·  Nextor",
                        font=("Courier", 11), fill=MUTED)
        hdr.create_line(20, 82, W-20, 82, fill=BORDER, width=1)

        # ── status indicator ───────────────────────────────────────────────
        status_frame = tk.Frame(self, bg=BG)
        status_frame.pack(fill="x", padx=24, pady=(10, 0))

        tk.Label(status_frame, text="STATUS", font=("Courier", 9, "bold"),
                 fg=MUTED, bg=BG).pack(side="left")

        self._status_dot = tk.Label(status_frame, text="  ●  ", font=("Courier", 14),
                                    fg=DIM, bg=BG)
        self._status_dot.pack(side="left")

        self._status_lbl = tk.Label(status_frame, text="Checking…",
                                    font=("Courier", 11), fg=TEXT, bg=BG)
        self._status_lbl.pack(side="left")

        # ── divider ────────────────────────────────────────────────────────
        tk.Canvas(self, height=1, bg=BORDER, highlightthickness=0).pack(
            fill="x", padx=24, pady=10)

        # ── buttons ────────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=24, pady=4)

        self._install_btn = self._make_btn(btn_frame, "⬇  INSTALL", GREEN,  self._on_install)
        self._install_btn.pack(side="left", padx=(0, 12))

        self._run_btn = self._make_btn(btn_frame, "▶  RUN",     CYAN,  self._on_run)
        self._run_btn.pack(side="left")

        # ── log area ───────────────────────────────────────────────────────
        log_outer = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        log_outer.pack(fill="both", expand=True, padx=24, pady=(12, 20))

        log_inner = tk.Frame(log_outer, bg=PANEL)
        log_inner.pack(fill="both", expand=True)

        self._log = scrolledtext.ScrolledText(
            log_inner, width=72, height=16,
            bg=PANEL, fg=TEXT, insertbackground=GREEN,
            font=("Courier", 10), bd=0, highlightthickness=0,
            relief="flat", state="disabled"
        )
        self._log.pack(fill="both", expand=True, padx=8, pady=8)

        # colour tags
        self._log.tag_config("green", foreground=GREEN)
        self._log.tag_config("red",   foreground=RED)
        self._log.tag_config("cyan",  foreground=CYAN)
        self._log.tag_config("dim",   foreground=MUTED)

        self._log_line("openMSX Toolbox ready.\n", "dim")

    # ── helpers ───────────────────────────────────────────────────────────────
    def _make_btn(self, parent, label, colour, cmd):
        btn = tk.Button(
            parent, text=label,
            font=("Courier", 12, "bold"),
            fg=colour, bg=PANEL,
            activeforeground=BG, activebackground=colour,
            relief="flat", bd=0, padx=18, pady=10,
            cursor="hand2", command=cmd,
            highlightthickness=1, highlightbackground=colour,
            highlightcolor=colour
        )
        btn.bind("<Enter>", lambda e, b=btn, c=colour: b.configure(bg=c, fg=BG))
        btn.bind("<Leave>", lambda e, b=btn, c=colour: b.configure(bg=PANEL, fg=c))
        return btn

    def _refresh_state(self):
        if is_installed():
            self._status_dot.configure(fg=GREEN)
            self._status_lbl.configure(text="openMSX installed")
            self._install_btn.configure(state="normal")
            self._run_btn.configure(state="normal")
        else:
            self._status_dot.configure(fg=RED)
            self._status_lbl.configure(text="Not installed")
            self._install_btn.configure(state="normal")
            self._run_btn.configure(state="disabled")

    def _log_line(self, msg, tag=""):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")
        self._last_was_overwrite = False

    def _log_overwrite(self, msg, tag=""):
        """Replace the last line (for progress %)."""
        self._log.configure(state="normal")
        if self._last_was_overwrite:
            self._log.delete("end-2l", "end-1c")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")
        self._last_was_overwrite = True

    def _safe_log(self, msg, colour=None, overwrite=False):
        tag = {GREEN: "green", RED: "red", CYAN: "cyan"}.get(colour, "")
        if overwrite:
            self.after(0, self._log_overwrite, msg, tag)
        else:
            self.after(0, self._log_line, msg, tag)

    # ── button actions ────────────────────────────────────────────────────────
    def _on_install(self):
        self._install_btn.configure(state="disabled")
        self._run_btn.configure(state="disabled")
        self._status_dot.configure(fg=CYAN)
        self._status_lbl.configure(text="Installing…")

        def worker():
            run_install(self._safe_log)
            self.after(0, self._refresh_state)
            self.after(0, self._install_btn.configure, {"state": "normal"})

        threading.Thread(target=worker, daemon=True).start()

    def _on_run(self):
        floppy = os.path.join(OPENMSX_DIR, "floppy.dsk")
        cmd = [
            OPENMSX_EXE,
            "-machine", "Panasonic_FS-A1GT",
            "-ext",     "SunriseIDE_Nextor",
            "-ext",     "scc+",
            "-diska",   floppy,
        ]
        self._safe_log("◈ Launching openMSX…", CYAN)
        self._safe_log("  " + " ".join(os.path.basename(c) if c == OPENMSX_EXE else c for c in cmd), CYAN)
        try:
            subprocess.Popen(cmd)
        except Exception as e:
            self._safe_log(f"✗ {e}", RED)


if __name__ == "__main__":
    app = App()
    app.mainloop()
