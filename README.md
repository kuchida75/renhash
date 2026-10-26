# renhash

RenHASH v1.8.0 is a Bash CLI for renaming regular files in the **current folder**:

```text
<prefix>_<index>_<RANDOM6>[.<extension>]
flower_001_8A9F02.png
flower_002_B1C3D4.png
```

Choose filename order, filesystem creation/birth order, or modification-time order.
Numbering is deterministic for a fixed set of names and timestamps; six-character
uppercase hexadecimal suffixes are fresh random values on every invocation.
Extensions are preserved, and files without an extension remain extensionless.

## Requirements and installation

Linux/Ubuntu, Bash 4.4+, GNU-compatible `find`, `sort`, `stat`, `od`, `tr`, `fold`,
`xargs`, `mv`, `mktemp`, `cmp`, `cp`, and `rm`, plus standard `cat`.
Ubuntu supplies these through Bash, coreutils and findutils. `getconf` is used
when available to check the filesystem's filename-length limit (otherwise 255
bytes). Python 3 is needed **only for tests**; GNU Parallel and OpenSSL are not
needed. `curl`, `readlink`, and `chmod` are used by the optional self-updater.

```bash
install -Dm755 renhash "$HOME/.local/bin/renhash"
# Ensure ~/.local/bin is on your PATH, then enter the folder to rename:
cd /path/to/images
renhash --help
```

## Chronological numbering

Preview the oldest-created files first, preserving the existing prefix and padding
settings you choose:

```bash
renhash --sort-by birth --prefix flower --digits 4 \
  --dry-run --sort new --limit 20
```

`--sort-by` controls **number assignment**:

| Value | Numbering order | With `--reverse` |
| --- | --- | --- |
| `name` (default) | Filename ascending, using C-locale byte order | Filename descending |
| `birth` | Filesystem birth time, oldest first | Newest first |
| `mtime` | Last data modification time, oldest first | Newest first |

For time ordering, equal timestamps always use filename **ascending** as the
secondary key, even with `--reverse`. Subsecond precision reported by `stat` is
retained. Sorting uses UTC timestamps and numeric epoch seconds, including dates
before 1970, so the user's locale and timezone do not affect numbering.

Birth time is a filesystem property, **not** EXIF capture time, a date encoded in
the filename, or Unix `ctime` (which records metadata changes). Copying a file can
change its birth time. Some filesystems, kernels and mounts do not expose birth
time. If **any eligible input** reports an unknown birth time, the default is to
stop before saving a plan or renaming anything. To deliberately fall back:

```bash
renhash --sort-by birth --birth-fallback mtime --dry-run --sort new
```

This prints a warning and orders the **entire selected batch** by mtime, rather
than mixing birth and modification timestamps. Other metadata-read errors still
stop the run. The GNU `stat` [timestamp fields](https://www.gnu.org/software/coreutils/manual/html_node/stat-invocation.html)
define unknown birth time as `%w` equal to `-`; epoch zero itself is a valid time.

To use modification times directly, or put the newest-created file first:

```bash
renhash --sort-by mtime --dry-run --sort new
renhash --sort-by birth --reverse --dry-run --sort new
```

## Preview, rename, and undo

The terminal PLAN colors sources blue and destinations magenta. Redirected output
and `--no-color` omit colors and icons. Names are shell-escaped for display so a
filename containing a newline or terminal control character cannot corrupt the
preview. These display strings are not the plan's storage format.

For example, with `z-old.png` created before `a-new.png`:

```text
$ renhash --sort-by birth --dry-run --sort new
z-old.png -> flower_001_8A9F02.png
a-new.png -> flower_002_B1C3D4.png
```

`--sort old|new` is retained from v1.7.1: it controls **only preview display order**.
It defaults to `old` (source filename). Use `--sort new` to see the numbering
sequence when ordering by time. The full `--plan` file always uses numbering order.
`--limit N` limits preview rows only; it does not limit selection, renaming, or the
saved plan. Large previews finish successfully without truncating the plan.

After reviewing a preview, perform a real run and save its mapping for undo:

```bash
# Each --plan path must be new. Keep plans outside the inputs when using '*'.
renhash --sort-by birth --prefix flower --digits 4 --dry-run \
  --sort new --plan ../flower-preview.tsv

renhash --sort-by birth --prefix flower --digits 4 --jobs 8 \
  --plan ../flower-renamed.tsv

# Run undo inside the same folder as the renamed files:
renhash --undo ../flower-renamed.tsv --dry-run --sort new
renhash --undo ../flower-renamed.tsv --jobs 8
```

**A dry run does not freeze a future run's mapping.** Each invocation generates
new random suffixes and rereads the files and timestamps. Undo the **real run's**
plan, not the preview's. `--plan` saves a mapping; it is not an apply-plan command.
No eligible files means a successful no-op without creating a plan.

## Resume and numbering

```bash
# Existing flower_0148_ABCDEF.png remains unchanged; new inputs start at 149:
renhash --prefix flower --resume --sort-by birth --dry-run --sort new

# Explicit start wins over --resume and --start, regardless of argument order:
renhash --prefix flower --resume --resume-from 250 --sort-by mtime --dry-run
```

Both `--resume` and `--resume-from` exclude files already matching the **literal
current prefix**, a decimal index and a six-character hexadecimal suffix, with
or without an extension. Prefixes may contain underscores and glob characters.

Automatic resume scans all regular files in the folder, across all extensions,
independently of `--pattern`. Mixed padding widths and leading zeros are read in
base 10. For example, `flower_0148_ABCDEF.png` and `flower_150_AAAAAA.jpg` make the
next index 151. Files under another prefix remain eligible if they match the
input pattern. With neither resume option, already-renamed files can be renumbered.

`--digits` is a **minimum width** and expands for the final index: 1,205 inputs
starting at 1 get four digits throughout. A collision triggers a new random
suffix for the same index, so it does not introduce a numbering gap.
`--start` and `--resume-from` accept positive decimal integers with up to 18
significant digits. A batch whose final index would exceed that limit is refused.
Padding accepts 1–255; the generated filename must also fit the filesystem limit.

## Scope and safety

- `--pattern GLOB` defaults to `*.png`. Quote patterns to prevent the calling shell
  from expanding them. It matches basenames only. Dotfiles require a pattern
  beginning with a literal dot, such as `--pattern ".*.png"`. No recursion,
  directory paths, brace expansion or shell evaluation is performed.
- Only regular files are selected. Directories, FIFOs and symlinks, including
  dangling symlinks, are excluded. Prefixes cannot contain `/`.
- Spaces, tabs, newlines, backslashes, quotes, Unicode, non-UTF-8 filename bytes,
  leading dashes and shell metacharacters survive rename/undo. Internal records
  are NUL-delimited. Parallel workers receive positional arguments, never shell
  commands assembled from filenames or TSV data.
- Targets are checked during planning and before execution. GNU `mv -nT` prevents
  overwriting or accidentally moving a source inside an existing target directory;
  skipped moves are detected and reported as failures even on older GNU `mv`.
  Existing files, directories and dangling symlinks reserve their names.
- `--plan` refuses to replace an existing path, including a source file or symlink.
  Plans are created with private permissions. Keep the saved plan until undo is
  no longer needed.
- `--jobs N` uses up to N workers (default: `nproc`; accepted range 1–1024). A single
  worker is supported with `--jobs 1`; assignment of numbers happens before any
  parallel moves, so worker completion order does not affect the mapping.
- The whole batch is checked before movement, but a rename run is not an atomic
  transaction. A late conflict or I/O error can leave a partial batch. The command
  exits nonzero, and successful moves can be reversed with the saved plan.
  Without `--plan`, a recovery plan is retained in a private temporary directory
  and its path is printed. Otherwise temporary files are removed on exit.
- Undo validates the complete plan before movement, rejects duplicate/overlapping
  names and paths outside the current folder, and refuses overwrite conflicts.
  Missing undo inputs are warned about and skipped, allowing recovery of a
  partially completed run and repeated undo. Undo does not verify file contents
  or restore timestamps or file metadata changed after renaming.

Keep the folder stable while planning and renaming; concurrent writers or another
renamer can change the snapshot. All filenames in a plan are relative to the
folder, so use undo there. An unrelated file later created under a saved target
name cannot be distinguished from the original by this mapping alone.

## Plan format and compatibility

New plans are escaped TSV retaining the original filename bytes, with a version header:

```text
# renhash-plan-v2
source.png<TAB>flower_001_ABCDEF.png
line\nbreak.png<TAB>flower_002_123456.png
```

`<TAB>` above represents one actual separator byte. Each data row has exactly two
fields, source then destination. Within each field, `\\` represents a backslash,
`\t` a tab, `\n` a newline and `\r` a carriage return. Decoding is literal and never
uses `eval`. NUL bytes, unknown escapes, malformed rows, self-mappings, duplicate
names, chains/cycles, and absolute or directory-containing paths are rejected.

`--undo` also accepts headerless v1.7.1 `src<TAB>dst` plans for ordinary filenames;
backslashes in those legacy files are literal, not escape codes. A leading `./`
is accepted for compatibility. Old raw TSV cannot reliably represent names that
contain tabs or newlines; use v2 plans for those files. This is a deliberate format
change to prevent corrupted plans and unsafe filename interpretation.

## Options

```text
--prefix NAME              Default: flower
--start N                  Default: 1
--digits N                 Default: 3, auto-expands
--pattern GLOB             Default: *.png, current-folder basenames only
--jobs N                   Default: nproc, maximum: 1024
--sort-by name|mtime|birth  Default: name
--reverse                  Descending names, or newest timestamps first
--birth-fallback error|mtime
                           Default: error; mtime fallback applies to entire batch
--resume                   Continue after the largest current-prefix index
--resume-from N            Explicit continuation start; overrides --resume/--start
--dry-run                  Preview only
--limit N                  Maximum preview rows (0 = all)
--sort old|new             Preview display order only (default: old)
--plan FILE                Save complete new escaped TSV mapping
--undo FILE                Reverse a saved plan in this folder
--no-color                 Disable colors and icons
--version, -v              Version
--update                   Self-update from GitHub; curl required
--help, -h                 Help
```

The v1.7.1 README previously described options the executable never implemented,
such as `--pad`, `--step`, `--copy`, `--suffix`, and a positional path. Those are not
supported. Use `--digits`, `--pattern GLOB` and `cd` as shown above. The existing
`--sort old|new` option remains a display setting; use the new `--sort-by` option
to change numbering.

The optional updater still reads `kuchida75/renhash` on GitHub, even when cloned
from Forgejo. It validates a completed download before replacing the local script.
Private GitHub repositories require `GITHUB_TOKEN`. Updating installs the remote
version, which can be older than a local development version.

## Development and verification

```bash
bash -n renhash
python3 -m unittest discover -s tests -v
```

The end-to-end suite uses disposable folders. It covers real and simulated birth
times, unsupported birth times and whole-batch fallback, subsecond ties, reverse
ordering, pre-1970 mtimes, resume precedence and mixed padding, display colors,
limits over 1,000 inputs, filename and pattern injection attempts, escaped and
legacy plans, malformed plans, serial/parallel undo, collision retries, late
file/directory/symlink collisions and recovery after a worker failure. The large
roundtrip previews, renames, verifies contents, and undoes **1,205 files** starting
at index 1,000. Test shims exercise unavailable metadata and race conditions
without changing the host's filesystems. CI runs the same suite on Ubuntu 22.04
and 24.04.
