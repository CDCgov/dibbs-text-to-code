#!/bin/bash

# Use this script to initialize the development environment.
#
# Usage: source bootstrap.sh
# Requires: python3

cd "$(dirname "$0")/.." || exit

# Detect platform (mingw = Git Bash, cygwin = WSL, linux = native Linux/macOS)
unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)     platform=linux;;
    Darwin*)    platform=mac;;
    CYGWIN*)    platform=windows;;
    MINGW*)     platform=windows;;
    MSYS*)      platform=windows;;
    *)          platform="unknown"
esac

echo "Detected platform: $platform"

# Select python executable
if [ "$platform" = "windows" ]; then
    python_cmd=python
else
    python_cmd=python3
fi

# Create a default .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating a default .env file..."
    echo "" > .env
else
    echo "Default .env file already exists."
fi

# Create a virtual environment if it doesn't exist
if [ ! -d .venv ]; then
    echo "Creating a virtual environment..."
    $python_cmd -m venv .venv
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
if [ "$platform" = "windows" ]; then
    source .venv/Scripts/activate
else
    source .venv/bin/activate
fi

# Install the development requirements
echo "Installing development requirements..."
$python_cmd -m pip install --upgrade pip > /dev/null
pip install '.[dev]' > /dev/null

# Install pre-commit hooks
echo "Installing pre-commit hooks..."
pre-commit install
