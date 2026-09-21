# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

from pathlib import Path

datas = [
    ("config/symbols.yaml", "config"),
    ("config/trading_rules.yaml", "config"),
    (".env.example", "."),
]
if Path(".env").exists():
    datas.append((".env", "."))
binaries = []
hiddenimports = [
    "app",
    "app.gui",
    "app.gui.app",
    "app.gui.theme",
    "customtkinter",
    "darkdetect",
    "MetaTrader5",
    "telethon",
    "telegram",
    "pydantic",
    "pydantic_settings",
    "yaml",
    "sqlalchemy",
    "sqlite3",
    "tzdata",
    "dotenv",
    "httpx",
]

for package in ("customtkinter", "telethon", "telegram", "tzdata", "MetaTrader5"):
    collected_datas, collected_binaries, collected_hidden = collect_all(package)
    datas += collected_datas
    binaries += collected_binaries
    hiddenimports += collected_hidden

a = Analysis(
    ["run_gui.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytest_asyncio"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TelegramMT5",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TelegramMT5",
)
