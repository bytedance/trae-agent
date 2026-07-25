#!/usr/bin/env bash
# trae-agent one-shot installer
# Inspired by https://opencode.ai/install and OpenClaw's install flow.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/1982167424-art/trae-agent/main/install.sh | bash
#   ./install.sh                  # install to ~/.local/bin
#   ./install.sh --system         # install to /usr/local/bin (requires sudo)
#   ./install.sh --uninstall      # remove the installed binary

set -euo pipefail

REPO_URL="https://github.com/1982167424-art/trae-agent.git"
PACKAGE_NAME="trae-agent"
USE_SYSTEM=0
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --system)    USE_SYSTEM=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --help|-h)
            echo "trae-agent installer"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --system      Install to /usr/local/bin instead of ~/.local/bin"
            echo "  --uninstall   Remove the existing installation"
            echo "  --help, -h    Show this help"
            exit 0
            ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

# --- Pick install path ---------------------------------------------------------
if [ "$USE_SYSTEM" -eq 1 ]; then
    INSTALL_BIN="/usr/local/bin/trae"
else
    # XDG-style: ~/.local/bin if it exists or can be created, else fall back.
    INSTALL_BIN="$HOME/.local/bin/trae"
    mkdir -p "$(dirname "$INSTALL_BIN")"
fi

if [ "$UNINSTALL" -eq 1 ]; then
    echo "Uninstalling trae-agent..."

    # P1-4 修复:完整删除所有安装产物,避免遗留文件。
    # uv tool 装到自己的隔离 venv,需要 `uv tool uninstall` 删包 + 删可执行文件;
    # 我们额外手工删自己创建的 ~/.local/bin/trae 别名链接。
    if command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then
        UV_BIN=$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")
        "$UV_BIN" tool uninstall trae-agent 2>&1 | tail -3 || true
    fi
    if command -v pipx >/dev/null 2>&1; then
        pipx uninstall trae-agent 2>&1 | tail -3 || true
    fi

    # 删别名/可执行文件(P1-4)
    for target in \
        "$HOME/.local/bin/trae" \
        "$HOME/.local/bin/trae-cli" \
        "/usr/local/bin/trae" \
        "/usr/local/bin/trae-cli"; do
        if [ -e "$target" ]; then
            if [ -w "$(dirname "$target")" ]; then
                rm -f "$target" && echo "Removed: $target"
            else
                sudo rm -f "$target" 2>/dev/null && echo "Removed (sudo): $target"
            fi
        fi
    done

    # 清理 ~/.local/share/uv/tools/trae-agent 残留(uv tool uninstall 通常
    # 会处理,但兜底以防失败)
    if [ -d "$HOME/.local/share/uv/tools/trae-agent" ]; then
        rm -rf "$HOME/.local/share/uv/tools/trae-agent"
        echo "Removed: $HOME/.local/share/uv/tools/trae-agent"
    fi

    echo "Uninstall complete."
    exit 0
fi

# --- Preflight ----------------------------------------------------------------
echo "▸ Checking Python..."
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "✗ Python 3.10+ is required but not installed." >&2
    echo "  Install it from https://www.python.org/" >&2
    exit 1
fi

PY_VERSION=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$("$PY" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PY" -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "✗ Python 3.10+ required, found $PY_VERSION" >&2
    exit 1
fi
echo "  ✓ Python $PY_VERSION"

# --- Locate or install uv -----------------------------------------------------
echo "▸ Checking uv..."
if command -v uv >/dev/null 2>&1; then
    UV=uv
elif [ -x "$HOME/.local/bin/uv" ]; then
    UV="$HOME/.local/bin/uv"
elif command -v pipx >/dev/null 2>&1; then
    echo "  → uv not found, falling back to pipx"
    UV=""  # use pipx path below
else
    echo "  → uv not found, installing via pip"
    "$PY" -m pip install --user uv >/dev/null 2>&1 || {
        echo "✗ Failed to install uv automatically." >&2
        echo "  Please install it: https://docs.astral.sh/uv/" >&2
        exit 1
    }
    UV="$HOME/.local/bin/uv"
fi
echo "  ✓ uv: $(command -v "$UV" 2>/dev/null || echo 'via pipx/pip')"

# --- Install the package ------------------------------------------------------
echo "▸ Installing trae-agent to $INSTALL_BIN..."

if [ -n "$UV" ]; then
    # uv tool install — sandboxed, isolated env, exposes entry points.
    # The entry-point name in pyproject.toml is `trae-cli` (not `trae`),
    # so uv creates ~/.local/bin/trae-cli. We create a `trae` alias below.
    #
    # NOTE: trae-agent's CLI does `import docker` at module-import time
    # (docker_manager.py is unconditionally imported by base_agent.py),
    # so we MUST install the `evaluation` extra (which provides docker,
    # pexpect, unidiff). Otherwise the first `trae` invocation crashes
    # with ModuleNotFoundError before any command runs.
    #
    # Issue 6: --with "pkg[extras]" --from "git+URL" syntax requires
    # uv >= 0.5.0. Older versions silently ignore --with or error out.
    # Check the version and fall back to pipx if uv is too old.
    UV_VERSION=$("$UV" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)
    UV_MAJOR=$(echo "$UV_VERSION" | cut -d. -f1)
    UV_MINOR=$(echo "$UV_VERSION" | cut -d. -f2)
    UV_TOO_OLD=0
    if [ -z "$UV_MAJOR" ] || [ "$UV_MAJOR" -lt 0 ] 2>/dev/null; then
        UV_TOO_OLD=1
    elif [ "$UV_MAJOR" -eq 0 ] && { [ -z "$UV_MINOR" ] || [ "$UV_MINOR" -lt 5 ]; } 2>/dev/null; then
        UV_TOO_OLD=1
    fi

    if [ "$UV_TOO_OLD" -eq 1 ]; then
        echo "  → uv $UV_VERSION is too old for --with extras (need >= 0.5.0), trying pipx..." >&2
        if command -v pipx >/dev/null 2>&1; then
            pipx install "trae-agent[evaluation] @ git+${REPO_URL}" 2>&1 | tail -5
        else
            echo "✗ uv too old and pipx not found. Please upgrade uv: uv self update" >&2
            exit 1
        fi
    else
        "$UV" tool install --with "trae-agent[evaluation]" --from "git+${REPO_URL}" trae-agent --force 2>&1 | tail -5 || {
            echo "✗ uv tool install failed. Trying alternative..." >&2
            if command -v pipx >/dev/null 2>&1; then
                pipx install "trae-agent[evaluation] @ git+${REPO_URL}" 2>&1 | tail -5
            else
                "$UV" pip install --system "trae-agent[evaluation] @ git+${REPO_URL}" 2>&1 | tail -5
            fi
        }
    fi
    TOOL_BIN="$HOME/.local/bin/trae-cli"
    if [ -e "$TOOL_BIN" ]; then
        # User-wide alias — creates `trae` regardless of $INSTALL_BIN.
        ln -sf "$TOOL_BIN" "$HOME/.local/bin/trae"
        # $INSTALL_BIN alias — the user might have requested --system.
        if [ "$USE_SYSTEM" -eq 1 ] && [ "$INSTALL_BIN" != "$HOME/.local/bin/trae" ]; then
            # P1-5 修复:/usr/local/bin 通常需要 sudo,普通用户裸 ln 会失败,
            # 旧脚本只打 ⚠ 然后继续,会让用户误以为安装成功。这里明确报错并 exit。
            if [ -w "$(dirname "$INSTALL_BIN")" ]; then
                ln -sf "$TOOL_BIN" "$INSTALL_BIN"
            else
                echo "  ✗ --system requested but $(dirname "$INSTALL_BIN") is not writable." >&2
                echo "    Re-run with sudo, or omit --system to use ~/.local/bin." >&2
                echo "    (trae is already available at $HOME/.local/bin/trae)" >&2
                exit 1
            fi
        fi
    fi
else
    # pipx fallback. pipx also uses the entry-point name from pyproject.toml.
    pipx install "trae-agent[evaluation] @ git+${REPO_URL}" 2>&1 | tail -5
    TOOL_BIN="$HOME/.local/bin/trae-cli"
    [ -e "$TOOL_BIN" ] && ln -sf "$TOOL_BIN" "$HOME/.local/bin/trae"
fi

# --- Check Ollama (optional) --------------------------------------------------
echo "▸ Checking Ollama (optional)..."
if command -v ollama >/dev/null 2>&1; then
    echo "  ✓ ollama installed"
else
    echo "  → ollama not installed (only needed for local models)"
    echo "    install: https://ollama.com/download"
fi

# --- Verify -------------------------------------------------------------------
echo ""
echo "─────────────────────────────────────────────────────"
# uv tool installs as `trae-cli` (entry-point name); we also create a `trae` alias.
# Check for either.
if command -v trae >/dev/null 2>&1 || command -v trae-cli >/dev/null 2>&1; then
    echo "✓ trae-agent installed successfully!"
    echo ""
    echo "Both commands are available:"
    echo "  trae        (alias)"
    echo "  trae-cli    (canonical entry point)"
    echo ""
    echo "Quick start:"
    echo "  trae version                    # banner"
    echo "  trae skills list                # list available skills"
    echo "  trae plan \"add tests for utils\" # read-only plan first"
    echo "  trae run \"fix the bug in auth\"  # then build & execute"
else
    echo "⚠ Installation finished, but neither 'trae' nor 'trae-cli' is on PATH."
    echo "  Add this to your shell rc file (~/.zshrc or ~/.bashrc):"
    echo "    export PATH=\"$(dirname "$INSTALL_BIN"):\$PATH\""
    echo "  Then 'source' the rc file or open a new terminal."
fi
