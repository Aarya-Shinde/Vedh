import os
import sys
import time
import shutil
import zipfile
from pathlib import Path

def main():
    # Give the main app time to shut down completely
    time.sleep(2.0)

    if len(sys.argv) < 3:
        print("Usage: updater.exe <install_dir> <zip_path>")
        sys.exit(1)

    install_dir = Path(sys.argv[1]).resolve()
    zip_path = Path(sys.argv[2]).resolve()

    print(f"Starting update...")
    print(f"Target Directory: {install_dir}")
    print(f"Update Package: {zip_path}")

    # 1. Extract zip to a temporary swap folder
    temp_extract = install_dir / "_update_temp"
    try:
        if temp_extract.exists():
            shutil.rmtree(temp_extract)
        temp_extract.mkdir()

        print("Extracting update package...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract)
    except Exception as e:
        print(f"Extraction failed: {e}")
        sys.exit(1)

    # 2. Perform Clean Swap: Delete all files in install dir except updater.exe and _update_temp
    print("Removing old application files...")
    for item in install_dir.iterdir():
        # Do not delete the updater itself or the temp extraction folder
        if item.name in ("_update_temp", "updater.exe"):
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            print(f"Failed to delete {item.name}: {e}")

    # 3. Copy files from temp_extract directly into install_dir
    print("Installing new version files...")
    try:
        for item in temp_extract.iterdir():
            target = install_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
    except Exception as e:
        print(f"Copying files failed: {e}")
        sys.exit(1)

    # 4. Clean up temp folder
    try:
        shutil.rmtree(temp_extract)
    except Exception:
        pass

    # 5. Launch the updated application
    exe_path = install_dir / "Vedh.exe"
    print("Launching updated application...")
    if exe_path.exists():
        try:
            os.startfile(exe_path)
        except Exception as e:
            print(f"Failed to start Vedh.exe: {e}")
    else:
        print(f"Error: {exe_path} not found.")

    sys.exit(0)

if __name__ == "__main__":
    main()
