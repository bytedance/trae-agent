# Trae Agent Installation Scripts

This directory contains automated installation scripts for Trae Agent that provide an out-of-the-box setup experience for all users.

## Available Scripts

### `install.sh` - Unix-like Systems (Mac/Linux)

A comprehensive bash script that automatically sets up Trae Agent on Mac and Linux systems.

**Features:**
- ✅ Automatic UV installation if not present
- ✅ Python version validation (requires 3.12+)
- ✅ Virtual environment creation
- ✅ Dependency installation with all extras
- ✅ Configuration file setup
- ✅ Installation verification
- ✅ Clear colored output and error handling
- ✅ Idempotent (safe to run multiple times)

**Usage:**
```bash
# Make executable and run
chmod +x install.sh
./install.sh
```

### `install.bat` - Windows Systems

A comprehensive batch script that automatically sets up Trae Agent on Windows systems.

**Features:**
- ✅ Automatic UV installation via PowerShell if not present
- ✅ Python version validation (requires 3.12+)
- ✅ Virtual environment creation
- ✅ Dependency installation with all extras
- ✅ Configuration file setup
- ✅ Installation verification
- ✅ Clear output and error handling
- ✅ Idempotent (safe to run multiple times)

**Usage:**
```cmd
# Run from Command Prompt
install.bat
```

## What the Scripts Do

1. **Environment Validation**
   - Check if running from correct directory
   - Verify Python 3.12+ is installed
   - Check for UV package manager

2. **UV Installation** (if needed)
   - **Unix:** Downloads and installs UV via `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - **Windows:** Downloads and installs UV via PowerShell

3. **Project Setup**
   - Creates virtual environment using `uv venv`
   - Installs all dependencies with `uv sync --all-extras`
   - Copies example configuration file to `trae_config.yaml`

4. **Verification**
   - Tests that `trae-cli` command is available
   - Verifies CLI functionality
   - Provides next steps and usage instructions

## User Scenarios Supported

### ✅ Mac Users
- With UV installed ✅
- Without UV installed ✅
- With Python 3.12+ ✅
- Various shell environments ✅

### ✅ Linux Users
- With UV installed ✅
- Without UV installed ✅
- With Python 3.12+ ✅
- Various distributions ✅

### ✅ Windows Users
- With UV installed ✅
- Without UV installed ✅
- With Python 3.12+ ✅
- Command Prompt and PowerShell ✅

## Error Handling

Both scripts include comprehensive error handling for common scenarios:

- **Missing Python:** Clear instructions to install Python 3.12+
- **Incompatible Python version:** Version check with helpful error messages
- **Missing curl/PowerShell:** Alternative installation instructions
- **Network issues:** Graceful failure with manual installation guidance
- **Permission issues:** Clear error messages and solutions
- **Wrong directory:** Detection and guidance to correct location

## After Installation

Once the scripts complete successfully, users need to:

1. **Activate the virtual environment:**
   - Unix: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\activate`

2. **Configure API keys** in `trae_config.yaml`

3. **Test the installation:**
   ```bash
   trae-cli show-config
   trae-cli run "Create a hello world Python script"
   ```

## Testing

The installation scripts include comprehensive testing:

- `test_install_scripts.py` - Basic functionality and content verification
- `test_install_scenarios.sh` - Edge case and scenario testing

Run tests with:
```bash
python3 test_install_scripts.py
./test_install_scenarios.sh
```

## Troubleshooting

### Common Issues

**"Command not found" after installation:**
- Ensure virtual environment is activated
- Check that UV installation completed successfully
- Restart terminal/command prompt

**Python version errors:**
- Install Python 3.12+ from https://python.org
- Ensure Python is in your PATH

**UV installation fails:**
- Install UV manually from https://docs.astral.sh/uv/
- Check network connectivity
- Ensure curl (Unix) or PowerShell (Windows) is available

**Permission denied errors:**
- On Unix: `chmod +x install.sh`
- Run with appropriate permissions
- Check directory write permissions

### Getting Help

If you encounter issues:

1. Check the error messages - they include specific guidance
2. Refer to the main README.md for manual installation steps
3. Visit https://github.com/bytedance/trae-agent for documentation
4. Check the project's issue tracker

## Contributing

To improve the installation scripts:

1. Test on different operating systems and configurations
2. Add support for additional package managers
3. Improve error messages and user guidance
4. Add more comprehensive testing scenarios

The scripts are designed to be maintainable and extensible for future requirements.
