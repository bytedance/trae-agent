# -*- mode: python ; coding: utf-8 -*-

analysis = Analysis(
    [
        'trae_agent/tools/edit_tool_cli.py',
        'trae_agent/tools/json_edit_tool_cli.py'
    ],
    pathex=['.'],
    datas=[], # codespell:ignore
    hiddenimports=[
        'jsonpath_ng',
    ],
    hookspath=[],
    binaries=[],
    runtime_hooks=[],
    excludes=[
        'trae_agent.tools.ckg_tool',
        'trae_agent.tools.ckg',
        'tree_sitter',
        'tree_sitter_languages',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=None)

# 1. edit_tool
exe_edit_tool = EXE(
    pyz,
    analysis.scripts[0:1],
    [],
    exclude_binaries=True,
    name='edit_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True
)

# 2. json_edit_tool
exe_json_edit_tool = EXE(
    pyz,
    analysis.scripts[1:2],
    [],
    exclude_binaries=True,
    name='json_edit_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True
)

coll = COLLECT(
    exe_edit_tool, exe_json_edit_tool, analysis.binaries, analysis.zipfiles, analysis.datas, # codespell:ignore
    strip=False, upx=True, upx_exclude=[], name='dist_tools'
)
