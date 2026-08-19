# Open PowerShell in project root

# Start the project under version control if it isn't already
if (-not (Test-Path .git)) {
    git init
}

# Ensure the (gitignored) data folder exists - credentials.json/token.json/*.db/logs/ all live under it.
# Doesn't touch anything already there.
New-Item -ItemType Directory -Force data | Out-Null

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install the project in editable mode with the dev extra (pytest, ruff, build).
# Editable install is the main dev loop: code changes are picked up immediately,
# no rebuild/reinstall needed.
python -m pip install --upgrade pip
pip install -e ".[dev]"

# Lint
ruff check .
ruff format --check .

# Run unit tests (fully self-contained - no live Gmail account or credentials needed)
pytest -q

# Build sdist + wheel (optional - only needed when producing a distributable
# artifact, e.g. to hand someone a .whl or publish to a package index).
if (Test-Path ./bin) {
    Remove-Item -Recurse -Force ./bin
}
New-Item -ItemType Directory -Path ./bin/distributions -Force | Out-Null
python -m build -o ./bin/distributions
