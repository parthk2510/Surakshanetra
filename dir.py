import os
import fnmatch

# Root directory of the repo
ROOT_DIR = "."

# Output file
OUTPUT_FILE = "repo_structure.txt"

# Ignore patterns (from your gitignore)
IGNORE_PATTERNS = [
    ".DS_Store","Thumbs.db","*~","*.tmp","*.log",
    "temp","tmp",".git",".gitignore",".gitmodules",".github","docs","tests","test","*.md",

    "__pycache__","*.py[cod]","*$py.class","*.pyo","*.pyd",
    ".pytest_cache",".mypy_cache",".ruff_cache",".coverage","htmlcov",

    "venv","env",".venv",".env",

    "build","dist","*.egg-info",".eggs","pip-wheel-metadata",

    "node_modules","npm-debug.log*","yarn-debug.log*","yarn-error.log*",".pnp",".pnp.js",
    "coverage",

    ".env",".env.*","config/local.json","config/secrets.json",
    "secrets","keys","*.pem","*.key",

    ".vscode",".idea","*.iml",".cursorignore",

    "*.sqlite","*.sqlite3","*.db",
    "uploads","data","cache",

    "chain_data","node_data","node_dat","indexes","snapshots",

    "*.class","*.jar","target","out","test-output","pids",
    "*.pid","*.seed","*.pid.lock",

    "reports","exports",

    "*.txt","*.md"
]

def is_ignored(name):
    for pattern in IGNORE_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def build_tree(start_path, prefix=""):
    entries = []
    try:
        items = sorted(os.listdir(start_path))
    except PermissionError:
        return entries

    items = [i for i in items if not is_ignored(i)]

    for index, item in enumerate(items):
        path = os.path.join(start_path, item)
        connector = "└── " if index == len(items) - 1 else "├── "

        entries.append(prefix + connector + item)

        if os.path.isdir(path):
            extension = "    " if index == len(items) - 1 else "│   "
            entries.extend(build_tree(path, prefix + extension))

    return entries


tree = build_tree(ROOT_DIR)

with open(OUTPUT_FILE, "w",encoding="utf-8") as f:
    f.write("\n".join(tree))

print(f"Directory structure saved to {OUTPUT_FILE}")