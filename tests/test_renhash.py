#!/usr/bin/env python3
"""End-to-end tests; all file operations run in disposable directories."""
import errno
import json
import os
from pathlib import Path
import pty
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'renhash'
REAL_STAT = shutil.which('stat')
REAL_MV = shutil.which('mv')


def decode_field(value):
    result = []
    pos = 0
    escapes = {'\\': '\\', 't': '\t', 'n': '\n', 'r': '\r'}
    while pos < len(value):
        if value[pos] == '\\':
            pos += 1
            result.append(escapes[value[pos]])
        else:
            result.append(value[pos])
        pos += 1
    return ''.join(result)


def read_plan(path):
    # Split only LF, preserving filenames containing CR and non-UTF-8 bytes.
    lines = os.fsdecode(path.read_bytes()).split('\n')
    assert lines[0] == '# renhash-plan-v2'
    return [tuple(decode_field(field) for field in line.split('\t'))
            for line in lines[1:] if line]


class RenhashTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='renhash-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        self.temp = self.root / 'temporary'
        self.temp.mkdir()
        self.env = {**os.environ, 'TMPDIR': str(self.temp), 'TZ': 'Pacific/Honolulu',
                    'PATH': str(self.tools) + os.pathsep + os.environ['PATH']}

    def run_cli(self, *args, success=True):
        result = subprocess.run([str(SCRIPT), '--no-color', *map(str, args)],
                                cwd=self.root, env=self.env, capture_output=True,
                                text=True, timeout=90)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('\x1b', result.stdout + result.stderr)
        return result

    def make(self, names):
        for name in names:
            (self.root / name).write_bytes(os.fsencode(name))

    def preview(self, *args, filename='preview.tsv'):
        result = self.run_cli('--dry-run', '--plan', filename, *args)
        return read_plan(self.root / filename), result

    def assert_indices(self, plan, start, width=3, prefix='flower'):
        for offset, (_, target) in enumerate(plan):
            self.assertRegex(target, '^' + re.escape(prefix) + '_' +
                             f'{start + offset:0{width}d}' + r'_[0-9A-F]{6}(\..*)?$')

    def shim(self, command, body):
        path = self.tools / command
        path.write_text('#!' + sys.executable + '\n' + body)
        path.chmod(0o755)

    def birth_shim(self, times):
        data = self.root / 'birth-times.json'
        data.write_text(json.dumps(times))
        self.shim('stat', f'''import json, os, sys
if '%W' not in ' '.join(sys.argv):
    os.execv({REAL_STAT!r}, [{REAL_STAT!r}, *sys.argv[1:]])
assert os.environ['TZ'] == 'UTC0'
times = json.load(open({str(data)!r}))
for name in sys.argv[sys.argv.index('--') + 1:]:
    seconds, stamp = times[name]
    sys.stdout.buffer.write(os.fsencode(str(seconds) + '\\t' + stamp + '\\t' + name) + b'\\0')
''')

    def test_default_name_order_and_padded_decimal_options(self):
        self.make(['z.png', 'a.png', 'M.png', '.hidden.png'])
        plan, result = self.preview('--start', '0008', '--digits', '0003', '--jobs', '0001')
        self.assertEqual([p[0] for p in plan], ['M.png', 'a.png', 'z.png'])
        self.assert_indices(plan, 8)
        self.assertEqual(len(result.stdout.splitlines()), 3)
        self.assertEqual((self.root / 'a.png').read_bytes(), b'a.png')
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_reverse_name(self):
        self.make(['b.png', 'a.png', 'c.png'])
        plan, _ = self.preview('--reverse')
        self.assertEqual([p[0] for p in plan], ['c.png', 'b.png', 'a.png'])

    def test_mtime_nanoseconds_ties_and_pre_epoch(self):
        self.make(['later.png', 'z.png', 'a.png', 'negative.png'])
        values = {'later.png': 1_700_000_000_900_000_000, 'z.png': 1_700_000_000_100_000_000,
                  'a.png': 1_700_000_000_100_000_000, 'negative.png': -900_000_000}
        for name, value in values.items():
            os.utime(self.root / name, ns=(value, value))
        plan, _ = self.preview('--sort-by', 'mtime')
        self.assertEqual([p[0] for p in plan], ['negative.png', 'a.png', 'z.png', 'later.png'])
        plan, _ = self.preview('--sort-by', 'mtime', '--reverse', filename='reverse.tsv')
        self.assertEqual([p[0] for p in plan], ['later.png', 'a.png', 'z.png', 'negative.png'])

    def test_birth_order_precision_and_ties_with_newest(self):
        self.make(['a.png', 'z.png', 'older.png', 'newer.png'])
        self.birth_shim({'older.png': [100, '1970-01-01 00:01:40.000000001 +0000'],
                         'a.png': [101, '1970-01-01 00:01:41.000000100 +0000'],
                         'z.png': [101, '1970-01-01 00:01:41.000000100 +0000'],
                         'newer.png': [101, '1970-01-01 00:01:41.000000900 +0000']})
        plan, _ = self.preview('--sort-by', 'birth')
        self.assertEqual([p[0] for p in plan], ['older.png', 'a.png', 'z.png', 'newer.png'])
        plan, _ = self.preview('--sort-by', 'birth', '--reverse', filename='reverse.tsv')
        self.assertEqual([p[0] for p in plan], ['newer.png', 'a.png', 'z.png', 'older.png'])

    def test_birth_on_real_filesystem_independent_of_mtime(self):
        names = ['z.png', 'middle.png', 'a.png']
        for index, name in enumerate(names):
            self.make([name])
            os.utime(self.root / name, (100 - index, 100 - index))
            time.sleep(0.015)
        birth = subprocess.check_output([REAL_STAT, '--printf=%w', '--', str(self.root / names[0])])
        if birth == b'-':
            result = self.run_cli('--sort-by', 'birth', '--dry-run', success=False)
            self.assertIn('Birth time unavailable', result.stderr)
        else:
            plan, _ = self.preview('--sort-by', 'birth')
            self.assertEqual([p[0] for p in plan], names)

    def test_unknown_birth_errors_before_plan_or_changes(self):
        self.make(['known.png', 'missing.png'])
        self.birth_shim({'known.png': [100, '1970-01-01 00:01:40.000000000 +0000'],
                         'missing.png': [0, '-']})
        result = self.run_cli('--sort-by', 'birth', '--plan', 'bad.tsv', success=False)
        self.assertIn('Birth time unavailable', result.stderr)
        self.assertFalse((self.root / 'bad.tsv').exists())
        self.assertTrue((self.root / 'known.png').exists())
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_birth_fallback_uses_mtime_for_entire_batch(self):
        self.make(['known.png', 'missing.png'])
        self.birth_shim({'known.png': [1, '1970-01-01 00:00:01.000000000 +0000'],
                         'missing.png': [0, '-']})
        os.utime(self.root / 'known.png', (200, 200))
        os.utime(self.root / 'missing.png', (100, 100))
        plan, result = self.preview('--sort-by', 'birth', '--birth-fallback', 'mtime')
        self.assertEqual([p[0] for p in plan], ['missing.png', 'known.png'])
        self.assertIn('ENTIRE batch by mtime', result.stderr)

    def test_known_epoch_zero_is_valid_birth_time(self):
        self.make(['epoch.png'])
        self.birth_shim({'epoch.png': [0, '1970-01-01 00:00:00.000000000 +0000']})
        plan, _ = self.preview('--sort-by', 'birth')
        self.assertEqual(plan[0][0], 'epoch.png')

    def test_resume_prefix_globs_underscores_mixed_widths_all_extensions(self):
        prefix = 'my_set_[x]*'
        existing = [prefix + '_0148_ABCDEF.png', prefix + '_000150_A1B2C3.jpg',
                    prefix + '_0149_FF0000', prefix + '_9999_NOTHEX.png',
                    'other_9999_AAAAAA.png', 'incoming.png']
        self.make(existing)
        plan, result = self.preview('--prefix', prefix, '--resume')
        self.assertEqual([p[0] for p in plan], ['incoming.png', prefix + '_9999_NOTHEX.png', 'other_9999_AAAAAA.png'])
        self.assert_indices(plan, 151, prefix=prefix)
        self.assertIn('max existing index 150', result.stderr)

    def test_resume_from_precedence_and_skip(self):
        self.make(['flower_0148_ABCDEF.png', 'b.png', 'a.png'])
        plan, _ = self.preview('--resume', '--start', '90', '--resume-from', '0008')
        self.assertEqual([p[0] for p in plan], ['a.png', 'b.png'])
        self.assert_indices(plan, 8)

    def test_resume_all_existing_is_noop_and_default_can_renumber(self):
        self.make(['flower_0148_ABCDEF.png'])
        result = self.run_cli('--resume', '--dry-run')
        self.assertIn('No eligible', result.stderr)
        plan, _ = self.preview()
        self.assert_indices(plan, 1)

    def test_preview_display_order_does_not_change_numbering(self):
        self.make(['z.png', 'a.png'])
        os.utime(self.root / 'a.png', (200, 200))
        os.utime(self.root / 'z.png', (100, 100))
        plan, result = self.preview('--sort-by', 'mtime', '--sort', 'old')
        self.assertEqual([p[0] for p in plan], ['z.png', 'a.png'])
        self.assertTrue(result.stdout.startswith('a.png -> flower_002_'))
        plan, result = self.preview('--sort-by', 'mtime', '--sort', 'new', filename='new.tsv')
        self.assertTrue(result.stdout.startswith('z.png -> flower_001_'))

    def test_hostile_filenames_and_prefix_roundtrip_serial_and_parallel(self):
        names = ['space name.png', "single'quote.png", 'double"quote.png', 'back\\slash.png',
                 '$(touch PWNED).png', '`touch PWNED`.png', '-n.png', 'tab\tfile.png',
                 'line\nfile.png', 'carriage\rreturn.png', 'escape\x1b[31m.png',
                 '$(touch PWNED2)\t\n.png', 'x[$(touch PWNED3)].png', 'unicodé-日本.png', os.fsdecode(b'bad-\xff.png')]
        self.make(names)
        prefix = "my_set_[x]_'$()\\\t\n"
        for jobs in ('1', '4'):
            planfile = 'run-' + jobs + '.tsv'
            self.run_cli('--prefix', prefix, '--jobs', jobs, '--plan', planfile)
            plan = read_plan(self.root / planfile)
            self.assertEqual(len(plan), len(names))
            for source, destination in plan:
                self.assertEqual((self.root / destination).read_bytes(), os.fsencode(source))
            self.run_cli('--undo', planfile, '--jobs', jobs)
            for name in names:
                self.assertEqual((self.root / name).read_bytes(), os.fsencode(name))
            self.assertFalse((self.root / 'PWNED').exists())
            self.assertFalse((self.root / 'PWNED2').exists())
            self.assertFalse((self.root / 'PWNED3').exists())

    def test_pattern_is_data_not_shell(self):
        self.make(['$(touch PWNED)-a.png', 'ordinary.png'])
        plan, _ = self.preview('--pattern', '$(touch PWNED)*.png')
        self.assertEqual([p[0] for p in plan], ['$(touch PWNED)-a.png'])
        self.assertFalse((self.root / 'PWNED').exists())

    def test_extensions_and_nonregular_inputs(self):
        self.make(['noext', '.hidden', '.multi.ext', 'image.tar.gz', 'trailing.'])
        (self.root / 'directory.png').mkdir()
        (self.root / 'link.png').symlink_to('noext')
        (self.root / 'broken.png').symlink_to('missing')
        os.mkfifo(self.root / 'fifo.png')
        plan, _ = self.preview('--pattern', '*')
        expected = {'image.tar.gz': '.gz', 'noext': '', 'trailing.': '.'}
        self.assertEqual(set(p[0] for p in plan), set(expected))
        hidden, _ = self.preview('--pattern', '.*', filename='hidden.tsv')
        self.assertEqual([p[0] for p in hidden], ['.hidden', '.multi.ext'])
        self.assertRegex(hidden[0][1], r'^flower_[0-9]+_[0-9A-F]{6}$')
        self.assertTrue(hidden[1][1].endswith('.ext'))
        for source, target in plan:
            self.assertRegex(target, r'^flower_[0-9]+_[0-9A-F]{6}' + re.escape(expected[source]) + '$')

    def test_mtime_sort_ties_with_tabs_and_newlines(self):
        names = ['z\tlast.png', 'a\t1.png', 'a\t0.png', 'a\n0.png']
        self.make(names)
        for name in names:
            os.utime(self.root / name, ns=(1_000_000_123, 1_000_000_123))
        plan, _ = self.preview('--sort-by', 'mtime', '--reverse')
        self.assertEqual([p[0] for p in plan], sorted(names, key=os.fsencode))

    def test_1205_files_resume_dryrun_parallel_rename_and_undo(self):
        count = 1205
        names = [f'source_{i:04}.png' for i in range(count)]
        existing = ['set_[x]_0148_ABCDEF.png', 'set_[x]_999_AAAAAA.jpg']
        self.make(names + existing)
        for index, name in enumerate(names):
            stamp = 1_700_000_000_000_000_000 + (count - index) * 10_000_000
            os.utime(self.root / name, ns=(stamp, stamp))
        options = ['--prefix', 'set_[x]', '--resume', '--sort-by', 'mtime', '--digits', '3', '--jobs', '4']
        plan, preview = self.preview(*options, '--limit', '5', '--sort', 'new')
        self.assertEqual(len(plan), count)
        self.assertEqual(len(preview.stdout.splitlines()), 5)
        self.assertEqual([p[0] for p in plan], list(reversed(names)))
        self.assert_indices(plan, 1000, width=4, prefix='set_[x]')
        self.assertIn('Padding expanded to 4', preview.stderr)
        self.assertTrue(all((self.root / name).exists() for name in names + existing))
        self.run_cli(*options, '--plan', 'real.tsv')
        actual = read_plan(self.root / 'real.tsv')
        self.assertEqual([p[0] for p in actual], [p[0] for p in plan])
        self.assert_indices(actual, 1000, width=4, prefix='set_[x]')
        for source, target in actual:
            self.assertFalse((self.root / source).exists())
            self.assertEqual((self.root / target).read_bytes(), os.fsencode(source))
        self.assertTrue(all((self.root / name).exists() for name in existing))
        self.run_cli('--undo', 'real.tsv', '--jobs', '4')
        for name in names + existing:
            self.assertEqual((self.root / name).read_bytes(), os.fsencode(name))
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_plan_cannot_overwrite_source_symlink_or_existing_file(self):
        self.make(['a.png', 'existing.tsv'])
        (self.root / 'dangling.tsv').symlink_to('missing')
        for filename in ['a.png', 'existing.tsv', 'dangling.tsv']:
            with self.subTest(filename=filename):
                self.run_cli('--plan', filename, success=False)
                self.assertEqual((self.root / 'a.png').read_bytes(), b'a.png')
        self.assertTrue((self.root / 'dangling.tsv').is_symlink())

    def test_invalid_options_never_rename(self):
        self.make(['a.png'])
        for options in [('--start', '0'), ('--start', '-1'), ('--start', '8+2'),
                        ('--start', '9999999999999999999'), ('--digits', '0'),
                        ('--digits', '256'), ('--jobs', '0'), ('--jobs', '1025'),
                        ('--limit', '-1'), ('--sort-by', 'ctime'), ('--sort', 'mtime'),
                        ('--birth-fallback', 'ctime'), ('--prefix', '../escape'),
                        ('--pattern', '../*.png'), ('--resume-from', '0'),
                        ('--prefix',), ('--wat',)]:
            with self.subTest(options=options):
                self.run_cli(*options, success=False)
                self.assertTrue((self.root / 'a.png').exists())

    def test_long_names_overflow_and_huge_resume_are_rejected(self):
        self.make(['a.png'])
        self.run_cli('--prefix', 'x' * 250, success=False)
        self.run_cli('--start', '999999999999999999', '--digits', '255', success=False)
        self.make(['b.png'])
        self.run_cli('--start', '999999999999999999', success=False)
        self.make(['flower_99999999999999999999_ABCDEF.png'])
        self.run_cli('--resume', success=False)
        self.assertTrue((self.root / 'a.png').exists())

    def test_legacy_undo_is_safe_and_dry_run_is_read_only(self):
        names = ["single'quote.png", '$(touch PWNED).png', 'back\\slash.png']
        targets = ['renamed1.png', 'renamed2.png', 'renamed3.png']
        self.make(targets)
        plan = self.root / 'legacy.tsv'
        plan.write_text(''.join(f'{source}\t{target}\n' for source, target in zip(names, targets)))
        result = self.run_cli('--undo', plan, '--dry-run', '--limit', '1')
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertTrue(all((self.root / name).exists() for name in targets))
        self.run_cli('--undo', plan, '--jobs', '4')
        self.assertTrue(all((self.root / name).exists() for name in names))
        self.assertFalse((self.root / 'PWNED').exists())
        self.run_cli('--undo', plan)  # Idempotent recovery; restored inputs are missing.

    def test_malformed_undo_rejected_before_any_moves(self):
        self.make(['dest.png', 'other.png'])
        examples = [b'../outside\tdest.png\n', b'/absolute\tdest.png\n', b'a/b\tdest.png\n',
                    b'\tdest.png\n', b'old.png\tdest.png\textra\n', b'no-tab\n',
                    b'old.png\tdest.png\0\n', b'old.png\tdest.png\nold.png\tother.png\n',
                    b'old.png\tdest.png\nother.png\tdest.png\n',
                    b'old.png\tdest.png\ndest.png\tother.png\n',
                    b'old.png\tdest.png\ndest.png\told.png\n', b'dest.png\tdest.png\n',
                    b'# renhash-plan-v2\nold\\q.png\tdest.png\n', b'# renhash-plan-v2\n', b'']
        for index, contents in enumerate(examples):
            with self.subTest(contents=contents):
                plan = self.root / f'invalid-{index}.tsv'
                plan.write_bytes(contents)
                self.run_cli('--undo', plan, success=False)
                self.assertEqual((self.root / 'dest.png').read_bytes(), b'dest.png')
                self.assertEqual((self.root / 'other.png').read_bytes(), b'other.png')

    def test_undo_conflict_preflights_entire_batch(self):
        self.make(['target1.png', 'target2.png', 'original2.png'])
        (self.root / 'undo.tsv').write_text('original1.png\ttarget1.png\noriginal2.png\ttarget2.png\n')
        self.run_cli('--undo', 'undo.tsv', success=False)
        self.assertTrue((self.root / 'target1.png').exists())
        self.assertFalse((self.root / 'original1.png').exists())

    def test_late_target_races_never_clobber_or_move_into_directories(self):
        self.make(['source.png'])
        for kind in ['file', 'directory', 'symlink']:
            with self.subTest(kind=kind):
                self.shim('mv', f'''import os, sys
from pathlib import Path
target = Path(sys.argv[-1])
kind = {kind!r}
if kind == 'file': target.write_bytes(b'keep-existing')
elif kind == 'directory': target.mkdir()
else: target.symlink_to('missing-file')
os.execv({REAL_MV!r}, [{REAL_MV!r}, *sys.argv[1:]])
''')
                filename = f'{kind}.tsv'
                result = self.run_cli('--plan', filename, '--jobs', '1', success=False)
                target = self.root / read_plan(self.root / filename)[0][1]
                self.assertIn('failed or skipped', result.stderr)
                self.assertEqual((self.root / 'source.png').read_bytes(), b'source.png')
                if kind == 'file': self.assertEqual(target.read_bytes(), b'keep-existing')
                elif kind == 'directory': self.assertEqual(list(target.iterdir()), [])
                else: self.assertEqual(os.readlink(target), 'missing-file')
                if kind == 'directory': target.rmdir()
                else: target.unlink()

    def test_planning_collision_rerolls_hash_without_skipping_index(self):
        self.make(['source.png', 'flower_001_000000.png'])
        # Exclude the collision sentinel from the selected pattern; first RNG
        # batch gives 000000, retry gives 010101. Index must remain 001.
        self.shim('od', '''import sys
if '-v' in sys.argv: print('00 00 00')
else: print('01 01 01')
''')
        plan, _ = self.preview('--pattern', 'source.png')
        self.assertEqual(plan, [('source.png', 'flower_001_010101.png')])
        self.assertEqual((self.root / 'flower_001_000000.png').read_bytes(), b'flower_001_000000.png')

    def test_worker_failure_keeps_recovery_plan_without_explicit_plan(self):
        self.make(['a.png', 'b.png'])
        self.shim('mv', f'''import os, sys
if sys.argv[-2] == 'b.png': sys.exit(1)
os.execv({REAL_MV!r}, [{REAL_MV!r}, *sys.argv[1:]])
''')
        result = self.run_cli('--jobs', '1', success=False)
        self.assertIn('recovery plan retained', result.stderr)
        plans = list(self.temp.glob('renhash.*/plan.tsv'))
        self.assertEqual(len(plans), 1)
        self.assertEqual(len(read_plan(plans[0])), 2)
        (self.tools / 'mv').unlink()
        self.run_cli('--undo', plans[0])
        self.assertEqual((self.root / 'a.png').read_bytes(), b'a.png')
        self.assertEqual((self.root / 'b.png').read_bytes(), b'b.png')

    def test_timestamp_failure_is_not_silently_ignored(self):
        self.make(['a.png'])
        self.shim('stat', 'import sys\nsys.exit(7)\n')
        self.run_cli('--sort-by', 'mtime', '--plan', 'must-not-exist.tsv', success=False)
        self.assertFalse((self.root / 'must-not-exist.tsv').exists())
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_limited_preview_is_successful_for_large_output(self):
        self.make([f'{index:04}.png' for index in range(1001)])
        plan, result = self.preview('--limit', '1')
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(len(plan), 1001)

    def test_colored_source_and_destination_preview_in_terminal(self):
        self.make(['a.png'])
        master, slave = pty.openpty()
        try:
            result = subprocess.run([str(SCRIPT), '--dry-run'], cwd=self.root,
                                    env=self.env, stdout=slave, stderr=subprocess.PIPE, timeout=10)
        finally:
            os.close(slave)
        output = b''
        try:
            while True:
                try:
                    chunk = os.read(master, 4096)
                except OSError as error:
                    if error.errno == errno.EIO: break
                    raise
                if not chunk: break
                output += chunk
        finally:
            os.close(master)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'\x1b[38;5;39m', output)
        self.assertIn(b'\x1b[38;5;199m', output)

    def test_resume_excludes_old_files_before_reading_birth_times(self):
        self.make(['flower_0148_ABCDEF.png', 'incoming.png'])
        self.birth_shim({'incoming.png': [100, '1970-01-01 00:01:40.000000000 +0000']})
        plan, _ = self.preview('--resume', '--sort-by', 'birth')
        self.assertEqual([p[0] for p in plan], ['incoming.png'])
        self.assert_indices(plan, 149)

    def test_selection_failure_is_not_treated_as_empty_folder(self):
        self.make(['a.png'])
        self.shim('find', 'import sys\nsys.exit(9)\n')
        self.run_cli('--plan', 'must-not-exist.tsv', success=False)
        self.assertFalse((self.root / 'must-not-exist.tsv').exists())
        self.assertTrue((self.root / 'a.png').exists())

    def test_self_update_stages_download_and_preserves_script_on_error(self):
        executable = self.root / 'renhash-copy'
        original = SCRIPT.read_bytes()
        for kind in ['download-failure', 'invalid-bash', 'success']:
            with self.subTest(kind=kind):
                executable.write_bytes(original)
                executable.chmod(0o755)
                self.shim('curl', f'''import sys
from pathlib import Path
kind = {kind!r}
output = Path(sys.argv[sys.argv.index('-o') + 1])
if kind == 'download-failure':
    output.write_bytes(b'partial')
    sys.exit(22)
if kind == 'invalid-bash': output.write_bytes(b'if then')
else: output.write_bytes(b'#!/usr/bin/env bash' + bytes([10]) + b'printf updated' + bytes([10]))
''')
                result = subprocess.run([str(executable), '--update', '--no-color'],
                                        cwd=self.root, env=self.env, capture_output=True, timeout=10)
                if kind == 'success':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotEqual(executable.read_bytes(), original)
                    self.assertTrue(os.access(executable, os.X_OK))
                    self.assertEqual(subprocess.check_output([str(executable)], timeout=5), b'updated')
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(executable.read_bytes(), original)
                self.assertEqual(list(self.temp.iterdir()), [])

    def test_help_version_and_empty_folder(self):
        result = self.run_cli('--help')
        self.assertIn('--sort-by name|mtime|birth', result.stdout)
        self.assertIn('v1.8.0', self.run_cli('--version').stdout)
        self.assertIn('No eligible', self.run_cli('--dry-run').stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
