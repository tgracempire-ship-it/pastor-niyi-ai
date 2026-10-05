"""Fetch the public Chroma database during Render's build when configured."""
import os
import shutil
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DB_DIR = Path(os.getenv("SERMON_DB_DIR", str(APP_DIR / "sermon_vector_db"))).resolve()
DRIVE_URL = os.getenv("SERMON_DB_URL", "").strip() or os.getenv("GDRIVE_DB_URL", "").strip()


def main():
    if (DB_DIR / "chroma.sqlite3").is_file():
        print("Sermon database already present in build context.")
        return
    if not DRIVE_URL or "/drive/folders/" not in DRIVE_URL:
        print("No Google Drive folder URL available at build; app startup will fetch it.")
        return

    import gdown

    DB_DIR.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sermon-db-build-", dir=DB_DIR.parent) as temp:
        download_dir = Path(temp) / "download"
        result = gdown.download_folder(url=DRIVE_URL, output=str(download_dir), quiet=False)
        sqlite_files = list(download_dir.rglob("chroma.sqlite3"))
        if not result or not sqlite_files:
            raise RuntimeError("The shared Google Drive folder did not contain chroma.sqlite3.")
        shutil.copytree(sqlite_files[0].parent, DB_DIR, dirs_exist_ok=True)
    print(f"Sermon database included in build image at {DB_DIR}.")


if __name__ == "__main__":
    main()
