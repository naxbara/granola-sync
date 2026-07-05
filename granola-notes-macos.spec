# PyInstaller spec for the Granola Notes GUI exporter (macOS .app bundle).
# Build with: python3 -m PyInstaller granola-notes-macos.spec
# Output:    dist/Granola Notes.app
#
# Strategy: onefile EXE wrapped in a .app BUNDLE (no COLLECT step).
# macOS Keychain access uses the built-in `security` CLI — no extra dependencies.

# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["src/granola_sync/gui/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[
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
        # Windows-only
        "win32crypt",
        "win32timezone",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
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
)

app = BUNDLE(
    exe,
    name="Granola Notes.app",
    icon=None,
    bundle_identifier="com.kyonxr.granola-notes",
    info_plist={
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "LSMinimumSystemVersion": "12.0",
        "CFBundleDisplayName": "Granola Notes",
        "CFBundleShortVersionString": "1.0",
    },
)
