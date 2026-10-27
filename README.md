# Creation-of-soc

Copies every `.com` file from the `singlet` and `triplet` folders into its
own sub-folder inside `soc_singlet` and `soc_triplet`, ready for SOC
calculations. Singlet is done first, then triplet:

```
scan/singlet/g1.com    ->   soc_singlet/g1.com/g1.com
scan/singlet/g2.com    ->   soc_singlet/g2.com/g2.com
scan/triplet/g1.com    ->   soc_triplet/g1.com/g1.com
scan/triplet/g2.com    ->   soc_triplet/g2.com/g2.com
...                         (one sub-folder per .com file)
```

Only `.com` files are copied. Other files (`.log`, `.chk`, ...) are ignored.

## How to run (Ubuntu terminal)

```bash
python3 creation_of_soc.py
```

The program first asks two questions:

1. **Path to singlet/triplet**: the folder that *contains* `singlet` and
   `triplet` (e.g. `jana/pp/opt/b3lyp/scan`). Both are found
   automatically. If they are not directly inside, sub-folders are
   searched. If only one of them exists, only that one is done.
2. **Path for soc folders**: the folder in which `soc_singlet` and
   `soc_triplet` should be created (e.g. `jana/pp/opt/b3lyp/scan`).

Type paths the same way as in the terminal: relative
(`jana/pp/opt/b3lyp/scan`), absolute (`/home/jana/...`), with `~` or
`$HOME`, with quotes or `\ ` for spaces. **Tab** completes folder names.

It then shows a summary for singlet and triplet and copies only after you
type `y`.

## Safety

- Files in `singlet` and `triplet` are only read, never changed or moved.
- Nothing is created or copied before you confirm the summary.
- Files already in the soc folders are never replaced without asking.
- If something is in the way (for example a file with a sub-folder's
  name), nothing is copied at all and the problem is shown.
- Every copy is compared byte by byte with the original, and both soc
  folders are checked again at the end.
- Running it again is safe: files already copied correctly are skipped.

Needs Python 3 (already installed on Ubuntu). Tested with Python 3.8–3.13.
