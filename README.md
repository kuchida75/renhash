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
