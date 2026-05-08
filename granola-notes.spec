# PyInstaller spec for the Granola Notes GUI exporter (Windows .exe).
# Build with: pyinstaller granola-notes.spec
# Output:    dist/Granola Notes.exe
#
# Strategy: --onefile --windowed, with explicit excludes to keep the binary
# minimal. The GUI subtree only needs auth, api, exporter, converters/prosemirror.

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ["src/granola_sync/gui/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[
        "win32crypt",
        "win32timezone",
        "cryptography.hazmat.primitives.ciphers.aead",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Markdown / Obsidian path — not needed for .txt export
        "granola_sync.converters.template",
        "granola_sync.sync",
        "granola_sync.sync.engine",
        "granola_sync.sync.dedup",
        "granola_sync.sync.vault",
        # AI enrichment
        "granola_sync.enrichment",
        "anthropic",
        # CLI / config (the GUI bypasses YAML config entirely)
        "granola_sync.cli",
        "granola_sync.config",
        "yaml",
        "thefuzz",
        "rapidfuzz",
        "rich",
        # Test / dev
        "pytest",
        "respx",
        "freezegun",
        # Heavy stdlib modules we don't use
        "pandas",
        "numpy",
        "matplotlib",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Granola Notes",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=None,
    icon=None,
)
