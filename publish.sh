#!/bin/bash
set -e

echo "=========================================="
echo "PPYDFS PyPI Publishing Script"
echo "=========================================="

# Version check
python -c "from ppydfs._version import __version__; print(f'Publishing version: {__version__}')"

# Clean previous builds
echo ""
echo "[1/4] Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info

# Install build dependencies
echo ""
echo "[2/4] Installing build dependencies..."
pip install --upgrade build twine

# Build the package
echo ""
echo "[3/4] Building package..."
python -m build

# Upload to PyPI
echo ""
echo "[4/4] Uploading to PyPI..."
echo "NOTE: Use 'twine upload --repository testpypi dist/*' for TestPyPI first"
echo "      Then use 'twine upload dist/*' for production"
read -p "Press Enter to continue with upload (or Ctrl+C to cancel)..."

twine upload dist/*

echo ""
echo "=========================================="
echo "Publishing complete!"
echo "=========================================="