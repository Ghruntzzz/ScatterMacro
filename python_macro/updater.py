"""Stage verified launcher releases; replace files only after the old app exits."""
import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

from python_macro.library import download_release, extract_package, library_root


def prepare_update(release):
    root = library_root().parent / "updates"
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="launcher-", dir=root))
    try:
        archive = stage / "release.zip"
        download_release(release, archive)
        extract_package(archive, stage / "package")
        package = stage / "package/ScatterLauncher"
        if not (package / "ScatterLauncher.exe").is_file():
            raise ValueError("Launcher executable missing from update")
        return package
    except Exception:
        shutil.rmtree(stage)
        raise


def replace_install(package, target):
    package, target = Path(package).resolve(), Path(target).resolve()
    if target == target.parent or target in package.parents or package in target.parents:
        raise ValueError("Unsafe update location")
    if not (target / "ScatterLauncher.exe").is_file() or not (package / "ScatterLauncher.exe").is_file():
        raise ValueError("Launcher installation not found")
    backup = target.with_name(target.name + ".backup-" + uuid.uuid4().hex[:8])
    target.rename(backup)
    try:
        shutil.copytree(package, target)
        # Preserve user-added files, but never merge stale bundled DLLs.
        for item in backup.iterdir():
            if item.name == "_internal" or (target / item.name).exists():
                continue
            if item.is_symlink():
                continue
            if item.is_dir():
                shutil.copytree(item, target / item.name)
            else:
                shutil.copy2(item, target / item.name)
    except Exception:
        if target.exists():
            shutil.rmtree(target)
        backup.rename(target)
        raise
    return backup


def wait_for_exit(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return
        raise OSError("Could not wait for the running launcher")
    try:
        if kernel.WaitForSingleObject(handle, 120000) != 0:
            raise TimeoutError("Close the old launcher before updating")
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-update", action="store_true")
    parser.add_argument("--target", required=True)
    parser.add_argument("--pid", required=True, type=int)
    args = parser.parse_args()
    try:
        wait_for_exit(args.pid)
        replace_install(Path(sys.executable).parent, args.target)
        subprocess.Popen([str(Path(args.target) / "ScatterLauncher.exe")], cwd=args.target)
        return 0
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(None, "Update could not finish. Your previous installation was preserved.\n\n" + str(error), "ScatterMacro update", 0x10)
        return 1
