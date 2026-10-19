# Creation-of-soc

Copies every `.com` file from a folder named `singlet` into its own
sub-folder inside a new folder named `soc`, ready for SOC calculations:

```
scan/singlet/g1.com    ->   soc/g1.com/g1.com
scan/singlet/g2.com    ->   soc/g2.com/g2.com
...                         (one sub-folder per .com file)
```

Only `.com` files are copied. Other files (`.log`, `.chk`, ...) and other
folders (for example `triplet`) are ignored.

## How to run (Ubuntu terminal)

```bash
python3 creation_of_soc.py
```

The program first asks two questions:

1. **Path to singlet** – the folder that *contains* `singlet`
   (e.g. `jana/pp/opt/b3lyp/scan`) or the `singlet` folder itself.
   If `singlet` is not directly inside, sub-folders are searched.
2. **Path for soc** – the folder in which `soc` should be created
   (e.g. `jana/pp/opt/b3lyp/scan`). If the path already ends in `/soc`,
   that folder is used.

Type paths the same way as in the terminal: relative
(`jana/pp/opt/b3lyp/scan`), absolute (`/home/jana/...`), with `~` or
`$HOME`, with quotes or `\ ` for spaces. **Tab** completes folder names.

It then shows a summary and copies only after you type `y`.

## Safety

- Files in `singlet` are only read, never changed or moved.
- Nothing is created or copied before you confirm the summary.
- Files already in `soc` are never replaced without asking.
- If something is in the way (for example a file with a sub-folder's
  name), nothing is copied and the problem is shown.
- Every copy is compared byte by byte with the original, and the whole
  `soc` folder is checked again at the end.
- Running it again is safe: files already copied correctly are skipped.

Needs Python 3 (already installed on Ubuntu). Tested with Python 3.8–3.13.
