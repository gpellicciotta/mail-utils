import shutil
import zipfile
from pathlib import Path

from .tree import ThunderbirdFolder, clean_folder_path

IGNORED_EXTENSIONS = {
    ".msf",
    ".dat",
    ".html",
    ".htm",
    ".rdf",
    ".sqlite",
    ".sqlite-journal",
    ".mab",
    ".json",
    ".js",
    ".txt",
    ".db",
    ".xml",
    ".csv",
    ".jar",
    ".xul",
    ".xpt",
    ".ico",
    ".png",
    ".xpm",
    ".dtd",
    ".ini",
}


def is_mail_store_file(relative_path: str | Path, file_size: int = 0) -> bool:
    """Determine whether a given file path is likely a Thunderbird Mbox mail store."""
    path_obj = Path(relative_path)
    ext = path_obj.suffix.lower()
    if ext in IGNORED_EXTENSIONS:
        return False
    return not path_obj.name.startswith(".")


def walk_folders(source_path: Path) -> list[ThunderbirdFolder]:
    """Discover all Mbox mail stores within a .pcv/.zip archive, profile directory, or single file."""
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Thunderbird source path not found: {source_path}")

    folders = []

    if source_path.is_file():
        if zipfile.is_zipfile(source_path):
            with zipfile.ZipFile(source_path, "r") as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    norm_name = info.filename.replace("\\", "/")
                    if norm_name.startswith(("Mail/", "ImapMail/")) and is_mail_store_file(norm_name, info.file_size):
                        cleaned = clean_folder_path(norm_name)
                        if cleaned:
                            folders.append(
                                ThunderbirdFolder(path=cleaned, source_identifier=info.filename, file_size=info.file_size)
                            )
        else:
            # Single standalone mbox file
            folders.append(
                ThunderbirdFolder(
                    path=source_path.stem,
                    source_identifier=str(source_path),
                    file_size=source_path.stat().st_size,
                )
            )
        return folders

    if source_path.is_dir():
        for file_path in source_path.rglob("*"):
            if file_path.is_file() and is_mail_store_file(file_path, file_path.stat().st_size):
                rel = file_path.relative_to(source_path)
                norm_name = str(rel).replace("\\", "/")
                cleaned = clean_folder_path(norm_name)
                if cleaned:
                    folders.append(
                        ThunderbirdFolder(
                            path=cleaned,
                            source_identifier=str(file_path),
                            file_size=file_path.stat().st_size,
                        )
                    )
        return folders

    return folders


def extract_mbox_to_file(source_path: Path, folder: ThunderbirdFolder, target_path: Path) -> None:
    """Extract an Mbox store from an archive or copy it from the filesystem to `target_path`."""
    source_path = Path(source_path)
    if source_path.is_file() and zipfile.is_zipfile(source_path):
        with (
            zipfile.ZipFile(source_path, "r") as z,
            z.open(folder.source_identifier) as src,
            open(target_path, "wb") as dst,
        ):
            shutil.copyfileobj(src, dst)
    else:
        src_file = Path(folder.source_identifier)
        if not src_file.is_absolute() and not src_file.exists():
            src_file = source_path / folder.source_identifier
        shutil.copy2(src_file, target_path)
