# renhash

Batch renamer for large folders that gives every file a **stable, ordered name** (e.g. `0001.jpg`, `0002.jpg` …) while preserving extensions and optionally adding prefixes/suffixes. Designed for big photo/video sets and AI datasets where you need **deterministic** names and **resumable** runs.

> TL;DR: `renhash --dry-run --pad 4 --start 1 --prefix IMG_ .`  
> then run without `--dry-run` when happy.

---

## ✨ Features

- **Deterministic ordering** (by name, mtime, or hash—whichever you choose)
- **Safe dry-run** mode that prints exactly what would change
- **Resume** mid-batch (`--resume`, `--resume-from N`)
- **Custom numbering** (`--start`, `--pad`, `--step`)
- **Prefix/Suffix** and case tools (`--prefix`, `--suffix`, `--lower`, `--upper`)
- **Copy or move** semantics (`--copy` vs default move)
- **Glob filters** (include/exclude by extension or pattern)
- **No clobber**: never overwrites existing files unless you ask for it

---

## 📦 Install

### Option A — One-liner (user local)
```bash
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/kuchida75/renhash/main/renhash -o ~/.local/bin/renhash
chmod +x ~/.local/bin/renhash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc   # or ~/.zshrc / config.fish
exec $SHELL
