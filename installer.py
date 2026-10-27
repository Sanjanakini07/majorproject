"""Standalone Windows Setup Installer for NMAMIT Campus Voice Assistant.

Installs the 100% offline desktop application on any Windows machine.
Extracts program files, data, models, and sets up Desktop & Start Menu shortcuts.
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


APP_NAME = "NMAMIT Campus Voice Assistant"
SHORTCUT_NAME = "NMAMIT Campus Voice Assistant.lnk"
EXE_NAME = "NMAMIT_Assistant.exe"


def get_default_install_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Programs" / "NMAMIT_Assistant"
    return Path.home() / "NMAMIT_Assistant"


def get_bundle_payload() -> Path:
    """Find payload.zip either in sys._MEIPASS (frozen) or adjacent directory."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    return base / "payload.zip"


def create_windows_shortcut(target_exe: Path, shortcut_path: Path, icon_path: Path | None = None) -> bool:
    """Create a Windows .lnk shortcut using VBScript."""
    try:
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        vbs_script = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{str(shortcut_path)}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{str(target_exe)}"
oLink.WorkingDirectory = "{str(target_exe.parent)}"
"""
        if icon_path and icon_path.exists():
            vbs_script += f'\noLink.IconLocation = "{str(icon_path)},0"\n'
        vbs_script += "oLink.Save\n"

        temp_vbs = shortcut_path.parent / "_temp_sc.vbs"
        temp_vbs.write_text(vbs_script, encoding="utf-8")
        subprocess.run(["cscript", "//nologo", str(temp_vbs)], check=True, creationflags=0x08000000 if os.name == "nt" else 0)
        if temp_vbs.exists():
            temp_vbs.unlink()
        return True
    except Exception as e:
        print(f"Error creating shortcut: {e}", file=sys.stderr)
        return False


def create_uninstaller(install_dir: Path, desktop_lnk: Path, start_lnk: Path) -> Path:
    """Create an uninstaller script in the install directory."""
    uninstall_bat = install_dir / "uninstall.bat"
    content = f"""@echo off
title Uninstall {APP_NAME}
echo Are you sure you want to uninstall {APP_NAME}?
echo Press any key to proceed or close this window to cancel.
pause >nul

echo Removing shortcuts...
if exist "{str(desktop_lnk)}" del /f /q "{str(desktop_lnk)}"
if exist "{str(start_lnk)}" del /f /q "{str(start_lnk)}"
if exist "{str(start_lnk.parent)}" rmdir /s /q "{str(start_lnk.parent)}"

echo Removing application files...
cd /d "%TEMP%"
start /b "" cmd /c "timeout /t 2 /nobreak >nul & rmdir /s /q \\"{str(install_dir)}\\""
echo Uninstallation completed successfully.
pause
"""
    uninstall_bat.write_text(content, encoding="utf-8")
    return uninstall_bat


class InstallerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} - Setup")
        self.root.geometry("540x420")
        self.root.resizable(False, False)

        # Style configuration
        self.primary_color = "#9b1c2c"  # NMAMIT maroon
        self.bg_color = "#f8f9fa"
        self.root.configure(bg=self.bg_color)

        self.install_dir_var = tk.StringVar(value=str(get_default_install_dir()))
        self.desktop_sc_var = tk.BooleanVar(value=True)
        self.start_sc_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)

        self.build_header()
        self.container = tk.Frame(self.root, bg=self.bg_color, padx=24, pady=16)
        self.container.pack(fill=tk.BOTH, expand=True)

        self.show_welcome_page()

    def build_header(self):
        header = tk.Frame(self.root, bg=self.primary_color, padx=20, pady=14)
        header.pack(fill=tk.X)

        title = tk.Label(header, text="NMAMIT Campus Voice Assistant", font=("Segoe UI", 15, "bold"), fg="#ffffff", bg=self.primary_color)
        title.pack(anchor="w")

        subtitle = tk.Label(header, text="100% Offline Desktop Edition · Face Auth & Local AI", font=("Segoe UI", 9), fg="#f0d5d8", bg=self.primary_color)
        subtitle.pack(anchor="w")

    def show_welcome_page(self):
        for widget in self.container.winfo_children():
            widget.destroy()

        lead = tk.Label(self.container, text="Welcome to the Setup Wizard", font=("Segoe UI", 12, "bold"), bg=self.bg_color, fg="#1a1a1a")
        lead.pack(anchor="w", pady=(0, 6))

        desc = tk.Label(self.container, text="This installer will install NMAMIT Campus Voice Assistant on your Windows device. The app operates completely offline using local face authentication and a direct SQLite database connection.",
                        font=("Segoe UI", 9), bg=self.bg_color, fg="#555555", wraplength=480, justify="left")
        desc.pack(anchor="w", pady=(0, 14))

        dest_frame = tk.LabelFrame(self.container, text=" Destination Directory ", font=("Segoe UI", 9, "bold"), bg=self.bg_color, fg="#333333", padx=10, pady=10)
        dest_frame.pack(fill=tk.X, pady=(0, 12))

        entry_frame = tk.Frame(dest_frame, bg=self.bg_color)
        entry_frame.pack(fill=tk.X)

        dest_entry = tk.Entry(entry_frame, textvariable=self.install_dir_var, font=("Segoe UI", 9))
        dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        browse_btn = tk.Button(entry_frame, text="Browse...", font=("Segoe UI", 9), command=self.browse_dir)
        browse_btn.pack(side=tk.RIGHT)

        opts_frame = tk.LabelFrame(self.container, text=" Shortcut Options ", font=("Segoe UI", 9, "bold"), bg=self.bg_color, fg="#333333", padx=10, pady=8)
        opts_frame.pack(fill=tk.X, pady=(0, 14))

        cb1 = tk.Checkbutton(opts_frame, text="Create Desktop Shortcut", variable=self.desktop_sc_var, font=("Segoe UI", 9), bg=self.bg_color, activebackground=self.bg_color)
        cb1.pack(anchor="w")

        cb2 = tk.Checkbutton(opts_frame, text="Create Start Menu Shortcut", variable=self.start_sc_var, font=("Segoe UI", 9), bg=self.bg_color, activebackground=self.bg_color)
        cb2.pack(anchor="w")

        btn_bar = tk.Frame(self.container, bg=self.bg_color)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        cancel_btn = tk.Button(btn_bar, text="Cancel", font=("Segoe UI", 9), width=10, command=self.root.quit)
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        install_btn = tk.Button(btn_bar, text="Install", font=("Segoe UI", 9, "bold"), width=12, bg=self.primary_color, fg="#ffffff", activebackground="#7e1724", activeforeground="#ffffff", relief=tk.FLAT, command=self.start_installation)
        install_btn.pack(side=tk.RIGHT)

    def browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.install_dir_var.get(), title="Select Destination Folder")
        if chosen:
            self.install_dir_var.set(chosen)

    def start_installation(self):
        for widget in self.container.winfo_children():
            widget.destroy()

        lead = tk.Label(self.container, text="Installing application files...", font=("Segoe UI", 12, "bold"), bg=self.bg_color)
        lead.pack(anchor="w", pady=(0, 10))

        self.status_label = tk.Label(self.container, text="Preparing installation...", font=("Segoe UI", 9), bg=self.bg_color, fg="#666666")
        self.status_label.pack(anchor="w", pady=(0, 12))

        self.progress = ttk.Progressbar(self.container, mode="indeterminate", length=480)
        self.progress.pack(fill=tk.X, pady=(0, 20))
        self.progress.start(10)

        threading.Thread(target=self.run_install_worker, daemon=True).start()

    def update_status(self, text: str):
        self.root.after(0, lambda: self.status_label.config(text=text))

    def run_install_worker(self):
        install_dir = Path(self.install_dir_var.get())
        try:
            self.update_status("Creating installation directory...")
            install_dir.mkdir(parents=True, exist_ok=True)

            payload_path = get_bundle_payload()
            if payload_path.exists():
                self.update_status("Extracting bundled application payload...")
                with zipfile.ZipFile(payload_path, "r") as zf:
                    total_files = len(zf.infolist())
                    for idx, member in enumerate(zf.infolist(), 1):
                        zf.extract(member, install_dir)
                        if idx % 20 == 0:
                            self.update_status(f"Extracting file {idx} of {total_files}...")
            else:
                self.update_status("Copying application files...")
                # If running directly in dev tree, copy needed folders
                base = Path(__file__).resolve().parent
                for folder in ("app", "offline_app", "data", "models"):
                    src = base / folder
                    dst = install_dir / folder
                    if src.exists() and not dst.exists():
                        shutil.copytree(src, dst)
                for f in ("desktop_client.py", ".env.example"):
                    if (base / f).exists():
                        shutil.copy2(base / f, install_dir / f)

            # Ensure .env exists in install_dir
            env_file = install_dir / ".env"
            if not env_file.exists():
                example = install_dir / ".env.example"
                if example.exists():
                    shutil.copy2(example, env_file)
                else:
                    env_file.write_text("SECRET_KEY=offline_secret_key_nmamit\n", encoding="utf-8")

            # Look for target executable or launcher
            target_exe = install_dir / EXE_NAME
            if not target_exe.exists():
                # Fallback to desktop_client.exe or python launcher
                for cand in install_dir.glob("*.exe"):
                    if "uninstall" not in cand.name.lower():
                        target_exe = cand
                        break

            # Icon path
            icon_path = install_dir / "app" / "static" / "icon.ico"
            if not icon_path.exists():
                icon_path = install_dir / "icon.ico"

            # Create Shortcuts
            user_desktop = Path(os.path.expandvars(r"%USERPROFILE%\Desktop"))
            user_start = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\NMAMIT Assistant"))

            desktop_lnk = user_desktop / SHORTCUT_NAME
            start_lnk = user_start / SHORTCUT_NAME

            if self.desktop_sc_var.get() and target_exe.exists():
                self.update_status("Creating Desktop shortcut...")
                create_windows_shortcut(target_exe, desktop_lnk, icon_path)

            if self.start_sc_var.get() and target_exe.exists():
                self.update_status("Creating Start Menu shortcut...")
                create_windows_shortcut(target_exe, start_lnk, icon_path)

            # Create uninstaller
            self.update_status("Creating uninstaller...")
            create_uninstaller(install_dir, desktop_lnk, start_lnk)

            self.root.after(0, self.show_finish_page)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Installation Error", str(e)))

    def show_finish_page(self):
        for widget in self.container.winfo_children():
            widget.destroy()

        lead = tk.Label(self.container, text="Installation Complete!", font=("Segoe UI", 13, "bold"), fg="#12804d", bg=self.bg_color)
        lead.pack(anchor="w", pady=(0, 10))

        desc = tk.Label(self.container,
                        text=f"NMAMIT Campus Voice Assistant has been successfully installed on your computer.\n\nInstallation location:\n{self.install_dir_var.get()}",
                        font=("Segoe UI", 9), bg=self.bg_color, justify="left")
        desc.pack(anchor="w", pady=(0, 20))

        cb = tk.Checkbutton(self.container, text="Launch NMAMIT Campus Voice Assistant now", variable=self.launch_var, font=("Segoe UI", 9, "bold"), bg=self.bg_color)
        cb.pack(anchor="w", pady=(0, 20))

        btn_bar = tk.Frame(self.container, bg=self.bg_color)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        finish_btn = tk.Button(btn_bar, text="Finish", font=("Segoe UI", 9, "bold"), width=12, bg=self.primary_color, fg="#ffffff", activebackground="#7e1724", activeforeground="#ffffff", relief=tk.FLAT, command=self.finish)
        finish_btn.pack(side=tk.RIGHT)

    def finish(self):
        install_dir = Path(self.install_dir_var.get())
        if self.launch_var.get():
            target_exe = install_dir / EXE_NAME
            if not target_exe.exists():
                for cand in install_dir.glob("*.exe"):
                    if "uninstall" not in cand.name.lower():
                        target_exe = cand
                        break
            if target_exe.exists():
                subprocess.Popen([str(target_exe)], cwd=str(install_dir))
            else:
                # Run launcher script
                py_script = install_dir / "desktop_client.py"
                if py_script.exists():
                    subprocess.Popen([sys.executable, str(py_script)], cwd=str(install_dir))
        self.root.destroy()


def main():
    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
