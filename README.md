# Creation-of-soc

Two programs that prepare Gaussian SOC calculations. Run them one after
the other in an Ubuntu terminal:

| Step | Command | What it does |
|------|---------|--------------|
| 1 | `python3 creation_of_soc.py` | Copies `singlet/g1.com` → `soc_singlet/g1.com/g1.com` (and the same for triplet) |
| 2 | `python3 creation_of_gaussian_com.py` | In every sub-folder, makes `gaussian.com` from `g1.com` with the new first lines |

Both programs show a summary and change nothing until you type `y`.
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

## Safety (both programs)

- Original files are only read, never changed or moved.
- Nothing is created or written before you confirm the summary.
- Existing files are never replaced without asking.
- If anything looks wrong (for example a file in the way, or a `.com`
  file without a route line), nothing at all is done and the problem is
  shown.
- Every file written is read back and compared with what it should be.
- Running a program again is safe: files that are already correct are
  skipped.

Needs Python 3 (already installed on Ubuntu). Tested with Python 3.8–3.13.
