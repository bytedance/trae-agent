#!/bin/bash

# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# Trae Agent Installation Script for Unix-like systems (Mac/Linux)
# This script provides an out-of-the-box installation experience for all users

set -e  # Exit on any error

# Color definitions for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_header() {
    echo -e "${BOLD}${BLUE}$1${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to compare version numbers
version_ge() {
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

# Function to get Python version
get_python_version() {
    if command_exists python3; then
        python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
    elif command_exists python; then
        python -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
    else
        echo "0.0"
    fi
}

# Main installation function
main() {
    log_header "🚀 Trae Agent Installation Script"
    echo
    log_info "This script will install Trae Agent and its dependencies."
    log_info "Requirements: Python 3.12+, UV package manager"
    echo

    # Check if we're in the correct directory
    if [[ ! -f "pyproject.toml" ]] || [[ ! -f "README.md" ]]; then
        log_error "This script must be run from the trae-agent project root directory."
        log_error "Please navigate to the project directory and run: ./install.sh"
        exit 1
    fi

    # Step 1: Check and install UV if needed
    log_header "📦 Checking UV installation..."
    if command_exists uv; then
        UV_VERSION=$(uv --version | cut -d' ' -f2)
        log_success "UV is already installed (version: $UV_VERSION)"
    else
        log_info "UV not found. Installing UV..."
        if command_exists curl; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
            # Source the shell profile to make uv available in current session
            if [[ -f "$HOME/.cargo/env" ]]; then
                source "$HOME/.cargo/env"
            fi
            export PATH="$HOME/.cargo/bin:$PATH"
            
            if command_exists uv; then
                log_success "UV installed successfully!"
            else
                log_error "UV installation failed. Please install UV manually from https://docs.astral.sh/uv/"
                exit 1
            fi
        else
            log_error "curl is required to install UV. Please install curl first or install UV manually from https://docs.astral.sh/uv/"
            exit 1
        fi
    fi

    # Step 2: Check Python version
    log_header "🐍 Checking Python version..."
    PYTHON_VERSION=$(get_python_version)
    if [[ "$PYTHON_VERSION" == "0.0" ]]; then
        log_error "Python is not installed or not found in PATH."
        log_error "Please install Python 3.12+ from https://www.python.org/downloads/"
        exit 1
    fi

    if version_ge "$PYTHON_VERSION" "3.12"; then
        log_success "Python $PYTHON_VERSION is compatible (requires 3.12+)"
    else
        log_error "Python $PYTHON_VERSION is not compatible. Trae Agent requires Python 3.12+"
        log_error "Please install Python 3.12+ from https://www.python.org/downloads/"
        exit 1
    fi

    # Step 3: Create virtual environment and install dependencies
    log_header "🔧 Setting up virtual environment and dependencies..."
    
    # Check if virtual environment already exists
    if [[ -d ".venv" ]]; then
        log_warning "Virtual environment already exists. Updating dependencies..."
    else
        log_info "Creating virtual environment..."
        uv venv
    fi

    log_info "Installing dependencies (this may take a few minutes)..."
    uv sync --all-extras

    if [[ $? -eq 0 ]]; then
        log_success "Dependencies installed successfully!"
    else
        log_error "Failed to install dependencies. Please check the error messages above."
        exit 1
    fi

    # Step 4: Set up configuration file
    log_header "⚙️  Setting up configuration..."
    if [[ ! -f "trae_config.yaml" ]]; then
        if [[ -f "trae_config.yaml.example" ]]; then
            cp trae_config.yaml.example trae_config.yaml
            log_success "Configuration file created from example template."
            log_warning "Please edit trae_config.yaml to add your API keys before using Trae Agent."
        else
            log_warning "Example configuration file not found. You'll need to create trae_config.yaml manually."
        fi
    else
        log_info "Configuration file already exists."
    fi

    # Step 5: Verify installation
    log_header "✅ Verifying installation..."
    if source .venv/bin/activate && command_exists trae-cli; then
        log_success "Trae Agent CLI is available!"
        
        # Test the CLI
        if .venv/bin/trae-cli --help >/dev/null 2>&1; then
            log_success "Installation verification passed!"
        else
            log_warning "CLI installed but may have issues. Try running 'trae-cli --help' after activation."
        fi
    else
        log_warning "CLI verification failed. You may need to activate the virtual environment first."
    fi

    # Step 6: Show next steps
    log_header "🎉 Installation Complete!"
    echo
    log_info "To get started with Trae Agent:"
    echo
    echo -e "  ${BOLD}1. Activate the virtual environment:${NC}"
    echo -e "     ${GREEN}source .venv/bin/activate${NC}"
    echo
    echo -e "  ${BOLD}2. Configure your API keys in trae_config.yaml${NC}"
    echo -e "     Edit the file and add your API keys for your chosen provider(s):"
    echo -e "     - OpenAI, Anthropic, Google Gemini, OpenRouter, Doubao, etc."
    echo
    echo -e "  ${BOLD}3. Test the installation:${NC}"
    echo -e "     ${GREEN}trae-cli show-config${NC}"
    echo
    echo -e "  ${BOLD}4. Run your first task:${NC}"
    echo -e "     ${GREEN}trae-cli run \"Create a hello world Python script\"${NC}"
    echo
    echo -e "  ${BOLD}5. For interactive mode:${NC}"
    echo -e "     ${GREEN}trae-cli interactive${NC}"
    echo
    log_info "For more information, see the README.md file or visit:"
    log_info "https://github.com/bytedance/trae-agent"
    echo
    log_success "Happy coding with Trae Agent! 🤖"
}

# Run the main function
main "$@"