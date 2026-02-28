import tkinter as tk
from tkinter import scrolledtext, filedialog
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

# ── default install dir (next to exe/script) ─────────────────────────────────
# ── base dir: works both as .py and compiled .exe ────────────────────────────
def _base_dir():
    """Return the folder containing the running exe (or script during dev)."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller exe
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _base_dir()

DEFAULT_INSTALL_DIR = os.path.join(BASE_DIR, "openMSX")

# ── persistent config file to remember chosen dir ────────────────────────────
CONFIG_FILE = os.path.join(BASE_DIR, "openmsx_path.cfg")


def load_install_dir():
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                p = f.read().strip()
            if p:
                return p
        except Exception:
            pass
    return DEFAULT_INSTALL_DIR


def save_install_dir(path):
    try:
        with open(CONFIG_FILE, "w") as f:
            f.write(path)
    except Exception:
        pass


def get_exe(install_dir):
    return os.path.join(install_dir, "openmsx.exe")


def is_installed(install_dir):
    return os.path.isfile(get_exe(install_dir))


# ── install logic (runs in thread) ───────────────────────────────────────────
def run_install(log, install_dir):
    openmsx_exe = get_exe(install_dir)
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
        zip_path = os.path.join(install_dir, zip_name)
        os.makedirs(install_dir, exist_ok=True)
        r = requests.get(zip_url, stream=True)
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    log(f"  {pct}%", overwrite=True)

        log("◈ Extracting…")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(install_dir)
        os.remove(zip_path)

        # Launch briefly to generate folder structure
        log("◈ Generating config structure…")
        proc = subprocess.Popen(openmsx_exe)
        time.sleep(3)
        proc.terminate()

        machines_dir   = os.path.join(install_dir, "share", "machines")
        extensions_dir = os.path.join(install_dir, "share", "extensions")
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
        floppy_src = os.path.join(BASE_DIR, "floppy.dsk")
        floppy_dst = os.path.join(install_dir, "floppy.dsk")
        if os.path.isfile(floppy_src):
            shutil.copy2(floppy_src, floppy_dst)
            log("  ✓ floppy.dsk copied")
        else:
            log("  ⚠ floppy.dsk not found next to launcher — skipping", CYAN)

        # Brief launch to create persistent dir  (Documents/openMSX stays fixed — openMSX decides this)
        log("◈ Creating persistent storage folders…")
        proc = subprocess.Popen([openmsx_exe, "-machine", "Panasonic_FS-A1GT", "-ext", "SunriseIDE_Nextor"])
        time.sleep(3)
        proc.terminate()

        # Download boot.dsk — always goes to Documents/openMSX (openMSX controls this path)
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
        log(f"  Installed to: {install_dir}", GREEN)

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
        self._install_dir = load_install_dir()
        self._build_ui()
        self._refresh_state()

    def _build_ui(self):
        W = 620

        # ── scanline canvas header ──────────────────────────────────────────
        hdr = tk.Canvas(self, width=W, height=100, bg=BG, highlightthickness=0)
        hdr.pack(fill="x")
        for y in range(0, 100, 3):
            hdr.create_line(0, y, W, y, fill="#111118")
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

        # ── install directory picker ───────────────────────────────────────
        dir_frame = tk.Frame(self, bg=BG)
        dir_frame.pack(fill="x", padx=24, pady=(0, 8))

        tk.Label(dir_frame, text="INSTALL DIR", font=("Courier", 9, "bold"),
                 fg=MUTED, bg=BG).pack(side="left")

        self._dir_var = tk.StringVar(value=self._install_dir)
        dir_entry = tk.Entry(
            dir_frame, textvariable=self._dir_var,
            font=("Courier", 9), bg=PANEL, fg=TEXT,
            insertbackground=GREEN, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=GREEN, width=42
        )
        dir_entry.pack(side="left", padx=(10, 6), ipady=4)

        browse_btn = tk.Button(
            dir_frame, text="…",
            font=("Courier", 10, "bold"),
            fg=CYAN, bg=PANEL,
            activeforeground=BG, activebackground=CYAN,
            relief="flat", bd=0, padx=10, pady=4,
            cursor="hand2", command=self._on_browse,
            highlightthickness=1, highlightbackground=CYAN,
            highlightcolor=CYAN
        )
        browse_btn.bind("<Enter>", lambda e: browse_btn.configure(bg=CYAN, fg=BG))
        browse_btn.bind("<Leave>", lambda e: browse_btn.configure(bg=PANEL, fg=CYAN))
        browse_btn.pack(side="left")

        # ── buttons ────────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=24, pady=4)

        self._install_btn = self._make_btn(btn_frame, "⬇  INSTALL", GREEN, self._on_install)
        self._install_btn.pack(side="left", padx=(0, 12))

        self._run_btn = self._make_btn(btn_frame, "▶  RUN", CYAN, self._on_run)
        self._run_btn.pack(side="left")

        # ── log area ───────────────────────────────────────────────────────
        log_outer = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        log_outer.pack(fill="both", expand=True, padx=24, pady=(12, 20))

        log_inner = tk.Frame(log_outer, bg=PANEL)
        log_inner.pack(fill="both", expand=True)

        self._log = scrolledtext.ScrolledText(
            log_inner, width=72, height=14,
            bg=PANEL, fg=TEXT, insertbackground=GREEN,
            font=("Courier", 10), bd=0, highlightthickness=0,
            relief="flat", state="disabled"
        )
        self._log.pack(fill="both", expand=True, padx=8, pady=8)

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
        d = self._dir_var.get().strip() if hasattr(self, '_dir_var') else self._install_dir
        if is_installed(d):
            self._status_dot.configure(fg=GREEN)
            self._status_lbl.configure(text="openMSX installed")
            self._run_btn.configure(state="normal")
        else:
            self._status_dot.configure(fg=RED)
            self._status_lbl.configure(text="Not installed")
            self._run_btn.configure(state="disabled")
        self._install_btn.configure(state="normal")

    def _log_line(self, msg, tag=""):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")
        self._last_was_overwrite = False

    def _log_overwrite(self, msg, tag=""):
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
    def _on_browse(self):
        chosen = filedialog.askdirectory(
            title="Choose openMSX install folder",
            initialdir=self._dir_var.get()
        )
        if chosen:
            # Append "openMSX" subfolder so it's tidy
            chosen = os.path.join(chosen, "openMSX")
            self._dir_var.set(chosen)
            self._install_dir = chosen
            save_install_dir(chosen)
            self._refresh_state()

    def _on_install(self):
        install_dir = self._dir_var.get().strip()
        if not install_dir:
            self._safe_log("✗ No install directory set.", RED)
            return

        self._install_dir = install_dir
        save_install_dir(install_dir)

        self._install_btn.configure(state="disabled")
        self._run_btn.configure(state="disabled")
        self._status_dot.configure(fg=CYAN)
        self._status_lbl.configure(text="Installing…")
        self._safe_log(f"◈ Install path: {install_dir}", CYAN)

        def worker():
            run_install(self._safe_log, install_dir)
            self.after(0, self._refresh_state)

        threading.Thread(target=worker, daemon=True).start()

    def _on_run(self):
        install_dir = self._dir_var.get().strip()
        openmsx_exe = get_exe(install_dir)
        floppy = os.path.join(install_dir, "floppy.dsk")
        cmd = [
            openmsx_exe,
            "-machine", "Panasonic_FS-A1GT",
            "-ext",     "SunriseIDE_Nextor",
            "-ext",     "scc+",
            "-diska",   floppy,
        ]
        self._safe_log("◈ Launching openMSX…", CYAN)
        self._safe_log("  " + " ".join(
            os.path.basename(c) if c == openmsx_exe else c for c in cmd
        ), CYAN)
        try:
            subprocess.Popen(cmd)
        except Exception as e:
            self._safe_log(f"✗ {e}", RED)


if __name__ == "__main__":
    app = App()
    app.mainloop()
