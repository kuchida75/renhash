# renhash

![version](https://img.shields.io/github/v/release/kuchida75/renhash?label=version)
![license](https://img.shields.io/github/license/kuchida75/renhash)
[![lint](https://github.com/kuchida75/renhash/actions/workflows/lint.yml/badge.svg)](https://github.com/kuchida75/renhash/actions/workflows/lint.yml)

Batch renamer for large folders that gives every file a **stable, ordered name**
(e.g. `0001.jpg`, `0002.jpg` …) while preserving extensions and optionally adding
prefixes/suffixes.  
Designed for big photo/video sets and AI datasets where you need **deterministic** names
and **resumable** runs.

> TL;DR:  
> `renhash --dry-run --pad 4 --start 1 --prefix IMG_ .`  
> then run without `--dry-run` when happy.

---

## ✨ Features

- **Deterministic ordering** (by name, mtime, or hash)
- **Safe dry-run** mode that prints exactly what would change
- **Resume mid-batch** (`--resume`, `--resume-from N`)
- **Custom numbering** (`--start`, `--pad`, `--step`)
- **Prefix/Suffix & case tools** (`--prefix`, `--suffix`, `--lower`, `--upper`)
- **Copy or move** semantics (`--copy` vs default move)
- **Glob filters** (include/exclude by extension or pattern)
- **No clobber:** never overwrites existing files unless you ask for it

---

## 🧠 Usage

```bash
# Preview what would happen
renhash --dry-run --pad 4 --prefix IMG_ .

# Execute renaming for real
renhash --pad 4 --prefix IMG_ .

renhash [OPTIONS] [PATH]

Core:
  --dry-run                 Show planned renames only
  --copy                    Copy files instead of moving
  --overwrite               Allow overwriting if the target exists

Indexing:
  --start N                 First index (default: 1)
  --resume                  Continue from highest existing index
  --resume-from N           Continue from specific index N
  --pad N                   Zero-pad width (e.g., 4 → 0001)
  --step N                  Increment step (default: 1)

Naming:
  --prefix STR              Add prefix before number
  --suffix STR              Add suffix before extension
  --lower | --upper         Force case

Ordering:
  --sort name|mtime|hash    Sort input (default: name)
  --reverse                 Reverse sort order

Scope:
  --ext "jpg,png,mp4"       Only these extensions
  --exclude "tmp,txt"       Exclude these extensions
  --depth N                 Max directory depth
  --hidden                  Include dotfiles

Layout:
  --dir DIR                 Output directory (default: in-place)
  --pattern "{n}.{ext}"     Custom pattern; tokens: {n},{name},{base},{ext}

Utilities:
  --undo-file FILE          Use file of “old → new” pairs to undo
  --log FILE                Write operations to FILE
  -h, --help                Show help
  -V, --version             Show version
