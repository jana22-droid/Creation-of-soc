# Creation-of-soc

Four programs that prepare and run Gaussian SOC calculations. Run them one after
the other in an Ubuntu terminal:

| Step | Command | What it does |
|------|---------|--------------|
| 1 | `python3 creation_of_soc.py` | Copies `singlet/g1.com` → `soc_singlet/g1.com/g1.com` (and the same for triplet) |
| 2 | `python3 creation_of_gaussian_com.py` | In every sub-folder, makes `gaussian.com` from `g1.com` with the new first lines |
| 3 | `python3 copy_init.py` | Copies the PySOC `init.py` into every sub-folder of `soc_singlet` |
| 4 | `python3 submit_soc_singlet.py` | Runs `g16 < gaussian.com > gaussian.log` in every `soc_singlet` sub-folder, one job after another |

All four programs show a summary and change nothing until you type `y`.
Type paths the same way as in the terminal: relative
(`jana/pp/opt/b3lyp/scan`), absolute (`/home/jana/...`), with `~` or
`$HOME`, with quotes or `\ ` for spaces. **Tab** completes folder names.

## Step 1: `creation_of_soc.py`

Copies every `.com` file from the `singlet` and `triplet` folders into its
own sub-folder inside `soc_singlet` and `soc_triplet`. Singlet first, then
triplet:

```
scan/singlet/g1.com    ->   soc_singlet/g1.com/g1.com
scan/singlet/g2.com    ->   soc_singlet/g2.com/g2.com
scan/triplet/g1.com    ->   soc_triplet/g1.com/g1.com
...                         (one sub-folder per .com file)
```

It asks two questions:

1. **Path to singlet/triplet**: the folder that *contains* `singlet` and
   `triplet` (e.g. `jana/pp/opt/b3lyp/scan`). Both are found
   automatically, also when they are deeper inside. If only one of them
   exists, only that one is done.
2. **Path for soc folders**: the folder in which `soc_singlet` and
   `soc_triplet` should be created (e.g. `jana/pp/opt/b3lyp/scan`).

Only `.com` files are copied. Other files (`.log`, `.chk`, ...) are ignored.

## Step 2: `creation_of_gaussian_com.py`

Goes into every sub-folder of `soc_singlet` (then `soc_triplet`), opens
the `.com` file there, replaces its first lines (the `%` lines and the
`#` route line) with the lines below, and saves the result as a **new**
file `gaussian.com` in the same sub-folder:

```
soc_singlet/g1.com/g1.com   ->   soc_singlet/g1.com/gaussian.com
soc_singlet/g2.com/g2.com   ->   soc_singlet/g2.com/gaussian.com
soc_triplet/g1.com/g1.com   ->   soc_triplet/g1.com/gaussian.com
...
```

New first lines (set in `NEW_HEADER` at the top of the program):

```
%rwf=gaussian.rwf
%nprocshared=6
%mem=3GB
%chk=gaussian.chk
# td=(50-50,nstates=4) b3lyp/6-311g(d,p) nosymm geom=connectivity gfinput
10f 6d
```

Everything after them (blank line, title, charge/multiplicity,
coordinates, connectivity) stays exactly as it is in each `g*.com`.

It asks one question: the path of `soc_singlet`/`soc_triplet`. Type the
folder that *contains* them (e.g. `jana/pp/opt/b3lyp/scan`) or the path
of `soc_singlet` or `soc_triplet` itself; both are found automatically.

The summary also shows the charge/multiplicity of the files and warns if
a file has no connectivity section (needed by `geom=connectivity`).

## Step 3: `copy_init.py`

Copies the PySOC settings file `init.py` into every sub-folder of
`soc_singlet`. Only `soc_singlet` is done; `soc_triplet` is not touched.

```
init.py   ->   soc_singlet/g1.com/init.py
init.py   ->   soc_singlet/g2.com/init.py
...            (one copy in every sub-folder, g1.com ... g41.com)
```

It asks two questions:

1. **Path to soc_singlet**: type either `soc_singlet` itself
   (e.g. `jana/pp/opt/b3lyp/scan/soc_singlet`) or the folder that contains
   it (e.g. `jana/pp/opt/b3lyp/scan`). The program tells the two apart. It
   also understands a path to `soc_triplet`, `singlet`, `triplet` or one
   sub-folder such as `soc_singlet/g7.com`, and searches deeper folders.
2. **Which init.py**: if `init.py` is next to the program, in the folder you
   are in, or next to `soc_singlet`, it is found and you only confirm it.
   Otherwise type its path or its folder. A file with another name (for
   example a download called `8c06abfb-init.py`) is accepted, but every
   copy is named `init.py`, because that is the name PySOC looks for.

Before copying, it checks that the file looks like the PySOC `init.py`
(it contains `QM_code`, `qm_out` and `molsoc_path`, and Python can read
it). The summary also notes settings that will need changing before PySOC
can run: `QM_code` other than `gauss_tddft`, and `g09root` or
`molsoc_path` pointing to a place that does not exist on this computer.
These notes do not stop the copying.

After you edit `init.py`, run the program again: it shows which copies
are different and replaces them only if you type `y`.

Tested with Python 3.6 (Ubuntu 18.04), 3.8 and 3.13.

## Step 4: `submit_soc_singlet.py`

Runs Gaussian 16 on the `gaussian.com` in every sub-folder of
`soc_singlet`, **one job at a time**, in the order g1.com, g2.com, ...
g41.com. Only `gaussian.com` is run; the `g1.com`, `g2.com`, ... files next
to it are never used. `soc_triplet` is not touched.

```
cd soc_singlet/g1.com   ;   g16 < gaussian.com > gaussian.log
   ... waits until that g16 has completely finished ...
cd soc_singlet/g2.com   ;   g16 < gaussian.com > gaussian.log
...
```

Each job runs inside its own sub-folder, so `gaussian.log`,
`gaussian.rwf` and `gaussian.chk` are written next to `gaussian.com` and
`init.py`, where PySOC needs them. A job counts as done only when the last
line of its `gaussian.log` says `Normal termination`. After each job the
program also checks that no Gaussian program is still working in that
sub-folder before the next job starts, and notes it if `gaussian.rwf` is
missing.

Start it from the terminal where `g16` normally works (it checks this).
It asks one question, the path of `soc_singlet` or of the folder that
contains it, shows a summary, and after `y` runs **in the background**:
you can close the terminal or log out of SSH.

| What | How |
|------|-----|
| Watch progress | `tail -f .../soc_singlet/submit_soc_singlet.log` (Ctrl+C only stops watching) |
| Stop after the job that is running now | `touch .../soc_singlet/STOP` |
| Stop at once (also stops the running g16) | `kill <number>` (the exact command is printed at the start) |
| See how far it is | run the program again |

- Jobs that already ended with `Normal termination` are skipped, so
  running it again is always safe.
- A job that failed or was stopped runs again next time; its old log is
  kept as `gaussian.log.old`.
- A failed job is reported (with Gaussian's `Error termination` line) and
  the next job starts once the failed one has completely ended. If 3 jobs
  fail one after another, the run stops.
- Nothing starts if a `gaussian.com` is missing, if a Gaussian job is
  already running in one of the sub-folders, or if a run is already going
  on this `soc_singlet`.
- No new job starts with less than 2 GB of free disk space.

Tested with Python 3.6 (Ubuntu 18.04), 3.8 and 3.13, using a stand-in for
g16 that writes its files like Gaussian does.

## Safety (all programs)

- Original files are only read, never changed or moved.
  (`copy_init.py` only adds `init.py` to each `soc_singlet` sub-folder;
  `submit_soc_singlet.py` only adds Gaussian's own output files.)
- Nothing is created or written before you confirm the summary.
- Existing files are never replaced without asking.
- If anything looks wrong (for example a file in the way, or a `.com`
  file without a route line), nothing at all is done and the problem is
  shown.
- Every file written is read back and compared with what it should be.
- Running a program again is safe: files that are already correct are
  skipped.

Needs Python 3 (already installed on Ubuntu). Tested with Python 3.8–3.13.
