import sys
import os
import requests
import hashlib
import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

CURRENT_VERSION = "1.0.0"
REPO_OWNER = "Aarya-Shinde"
REPO_NAME = "Vedh"
REPO_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

class UpdateChecker:
    @staticmethod
    def check_for_updates():
        try:
            # We send a User-Agent header as required by the GitHub API
            headers = {"User-Agent": "Vedh-Reader-App"}
            response = requests.get(REPO_URL, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_tag = data.get("tag_name", "").strip().lower().replace("v", "")
                if latest_tag and latest_tag > CURRENT_VERSION:
                    assets = data.get("assets", [])
                    # Find ZIP file and checksum file
                    zip_url = next((a["browser_download_url"] for a in assets if a["name"].endswith(".zip")), None)
                    checksum_url = next((a["browser_download_url"] for a in assets if a["name"] == "checksums.txt"), None)
                    return latest_tag, zip_url, checksum_url
        except Exception as e:
            print(f"Failed to query update API: {e}")
        return None, None, None


class BackgroundDownloader(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)  # success status, error/success message

    def __init__(self, download_url, checksum_url, save_dir):
        super().__init__()
        self.download_url = download_url
        self.checksum_url = checksum_url
        self.save_dir = Path(save_dir)

    def run(self):
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            zip_path = self.save_dir / "update.zip"

            # 1. Download ZIP
            headers = {"User-Agent": "Vedh-Reader-App"}
            response = requests.get(self.download_url, headers=headers, stream=True, timeout=20)
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            self.progress.emit(int((downloaded / total_size) * 100))

            # 2. Download and Verify Checksum
            if self.checksum_url:
                c_resp = requests.get(self.checksum_url, headers=headers, timeout=10)
                if c_resp.status_code == 200:
                    lines = c_resp.text.splitlines()
                    expected_hash = None
                    for line in lines:
                        if "Vedh_Windows.zip" in line:
                            expected_hash = line.split()[0].strip().lower()
                            break
                    
                    if not expected_hash:
                        # Fallback to first word of file if it's simple
                        expected_hash = c_resp.text.split()[0].strip().lower()

                    # Calculate local hash
                    hasher = hashlib.sha256()
                    with open(zip_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher.update(chunk)
                    actual_hash = hasher.hexdigest().lower()

                    if actual_hash != expected_hash:
                        self.finished.emit(False, f"SHA-256 verification failed.\nExpected: {expected_hash}\nGot: {actual_hash}")
                        return
                else:
                    self.finished.emit(False, "Failed to download SHA-256 checksum file.")
                    return

            self.finished.emit(True, str(zip_path))
        except Exception as e:
            self.finished.emit(False, f"Download error: {e}")


def launch_updater_and_exit(zip_path_str: str):
    """
    Spawns the standalone updater.exe and shuts down the current app.
    """
    try:
        # Determine installation directory where updater.exe should be located
        if hasattr(sys, '_MEIPASS'):
            # Running inside PyInstaller compiled executable
            install_dir = Path(sys.executable).parent
        else:
            # Running in dev environment
            install_dir = Path(__file__).parent.parent

        updater_exe = install_dir / "updater.exe"
        if not updater_exe.exists():
            # If updater.exe is missing, check root project dir (for fallback in dev)
            updater_exe = Path(__file__).parent.parent / "dist" / "updater" / "updater.exe"
            if not updater_exe.exists():
                updater_exe = Path(__file__).parent.parent / "updater.py"

        # Construct arguments
        args = [str(updater_exe), str(install_dir), zip_path_str]
        
        # If it's a python script (dev fallback), run it via python
        if updater_exe.suffix == ".py":
            args.insert(0, sys.executable)

        # Launch the detached process
        if sys.platform == "win32":
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(args)
            
        # Exit current application immediately so updater can swap files
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
        sys.exit(0)
    except Exception as e:
        print(f"Failed to launch updater: {e}")
