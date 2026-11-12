#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search.py  -  find on THIS computer the paths that PySOC's init.py needs
=======================================================================

init.py (the PySOC settings file) still contains paths from another computer:

    g09root        = '/home/serb/software'
    molsoc_path    = '/home/serb/software/pysoc-master/molsoc/molsoc_modified/molsoc0.1/bin/molsoc0.1.exe'
    dir_para_basis = '/fsnfs/users/xinggao/work/.../tddftb/sto2gto/mio-1-1'

This program searches this computer and shows the right value for each of
them, ready to copy. It also checks the other things PySOC needs to run
with init.py: Gaussian's rwfdump, the PySOC scripts (soc.py, soc_td,
pysoc.py) and Python 2. And it lists the init.py copies already on this
computer, with the paths they contain now.

HOW TO RUN
    python3 search.py                      searches the whole computer
    python3 search.py ~/software /opt      searches only these folders (faster)

Run it from the terminal where g16 normally works.
Press Ctrl+C during the search to stop early; what was found so far is shown.

The results are printed between two lines (COPY FROM HERE / COPY UP TO HERE)
and are also saved in the file search_results.txt in the folder you are in.

Nothing on the computer is changed; the only file written is search_results.txt.
"""
from __future__ import print_function

import sys

# Stop early, with a clear message, if started with the old Python 2.
if sys.version_info[0] < 3:
    sys.stderr.write(
        "\nThis program needs Python 3. Please run it like this:\n\n"
        "    python3 search.py\n\n")
    sys.exit(1)

import getpass
import hashlib
import os
import re
import shutil
import socket
import subprocess
import time

# ---------------------------------------------------------------------------
# What is searched for
# ---------------------------------------------------------------------------
GAUSSIAN_VERSIONS = ("g16", "g09", "g03")
MOLSOC_NAME = "molsoc0.1.exe"
RESULTS_NAME = "search_results.txt"
RESULTS_HEADER = "search.py results"

# Folders never searched: they hold no installed programs, only system data,
# and some of them never finish (/proc, /sys).
SKIP_FOLDERS = ("/proc", "/sys", "/dev", "/run", "/snap", "/var/lib/docker",
                "/var/lib/containers", "/var/lib/snapd", "/var/cache", "/lost+found")
SKIP_NAMES = (".git", "__pycache__", "node_modules", ".cache")

# Files of the PySOC releases, recognised by their exact content (SHA-256).
MOLSOC_KNOWN = {
    "da3880756d5d1997418e854ab0b9e20a167544246a29d4011e0a6e477be2531d":
        ("modified", "the MODIFIED MolSOC from the PySOC 2016 release (the one init.py needs)"),
    "61990c1ed95f530d15e3d31b1de1a4c3dae032013e9180f043103d0c47b31e96":
        ("newer", "MolSOC from the newer PySOC (2020 and later)"),
    "a72020ef5f63fec8e202c2a0cb81eea40bb1faeb3bf8a5fca203da9da1294239":
        ("original", "the ORIGINAL, unmodified MolSOC (NOT the one PySOC needs)"),
}
SOC_PY_KNOWN = {
    "d473776765bf67d86942287ecb4132273396fff54e7378eebf17c57d29fa92bd":
        "PySOC 2016 release (Python 2), made for this init.py",
}
SOC_TD_KNOWN = {
    "8c5abcf68508f93543b740cf54022fb380d9ecf8b6a01fcb6b2e8b011b508a72":
        "PySOC 2016 release, made for this init.py",
    "3f3ac36ab05cbabace611efb374bf0aa1c4b4981ae75f18f414a7d952ffb6ce8":
        "from the newer PySOC (2020 and later); with soc.py/init.py use the 2016 one",
}

# Where the PySOC 2016 release (the version that uses init.py) can be downloaded.
RELEASE = "https://raw.githubusercontent.com/gaox-qd/pysoc/6ad12eaa85fe1c56250d91686be34bdc496f5793/"
PYSOC_URL = RELEASE + "pysoc.tar.gz"
MOLSOC_URL = RELEASE + "molsoc.tar.gz"

MAX_READ = 1024 * 1024          # read at most 1 MB of a text file
MAX_HASH = 200 * 1024 * 1024    # do not fingerprint files bigger than 200 MB
LINE = "=" * 72


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def safe(text):
    """Return text that can always be printed (unprintable characters become '?')."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        return text.encode(encoding, "replace").decode(encoding)
    except LookupError:
        return text


def say(text=""):
    print(safe(text))
    sys.stdout.flush()


def quoted(path):
    """A path written the way it goes into init.py."""
    return "'" + path + "'" if "'" not in path else '"' + path + '"'


def read_text(path, limit=MAX_READ):
    try:
        with open(path, "rb") as handle:
            return handle.read(limit).decode("utf-8", "replace")
    except (IOError, OSError):
        return None


def sha256(path):
    try:
        if os.path.getsize(path) > MAX_HASH:
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except (IOError, OSError):
        return None


def is_executable_file(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def natural_key(text):
    parts = re.split(r"(\d+)", text)
    return [int(part) if index % 2 else part.lower() for index, part in enumerate(parts)]


def natural_sorted(items):
    return sorted(items, key=lambda item: (natural_key(item), item))


def run_quietly(command, timeout=10):
    """Run a command; return its output (stdout and stderr together), or None."""
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True,
                                timeout=timeout)
        return result.stdout
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def setting_value(text, name):
    """The value of  name = '...'  in init.py / pysoc.py text (last uncommented one)."""
    value = None
    for line in text.splitlines():
        match = re.match(r"\s*" + name + r"\s*=\s*(['\"])(.*?)\1", line)
        if match:
            value = match.group(2)
    return value


def shebang_program(path):
    """For '#!/usr/bin/env python2' -> 'python2'; for '#!/bin/csh -f' -> '/bin/csh'."""
    text = read_text(path, 256)
    if not text or not text.startswith("#!"):
        return None
    words = text[2:].splitlines()[0].split()
    if not words:
        return None
    if os.path.basename(words[0]) == "env" and len(words) > 1:
        return words[1]
    return words[0]


def program_available(program):
    if program is None:
        return True
    if os.sep in program:
        return os.path.isfile(program) and os.access(program, os.X_OK)
    return shutil.which(program) is not None


def missing_libraries(path):
    """Shared libraries a program needs that this computer does not have."""
    if shutil.which("ldd") is None:
        return []
    output = run_quietly(["ldd", path]) or ""
    return [line.split("=>")[0].strip() for line in output.splitlines() if "not found" in line]


def os_release():
    text = read_text("/etc/os-release", 8192) or ""
    found = re.search(r'^VERSION_ID="?([^"\n]*)"?', text, re.MULTILINE)
    name = re.search(r'^ID="?([^"\n]*)"?', text, re.MULTILINE)
    return (name.group(1) if name else ""), (found.group(1) if found else "")


def python2_install_hint():
    distro, version = os_release()
    if distro == "ubuntu" and version.startswith("18."):
        return "sudo apt install python-minimal      (Ubuntu 18.04)"
    if distro == "ubuntu" and (version.startswith("20.") or version.startswith("22.")):
        return "sudo apt install python2"
    return "install Python 2.7 (ask your system admin), e.g. with conda: conda create -n py27 python=2.7"


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------
class Found(object):
    def __init__(self):
        self.gaussian = {}       # real path of g16/g09 folder -> set of "how found"
        self.rwfdump = set()
        self.molsoc = set()
        self.basis = set()       # folders like mio-1-1 holding *.basis files
        self.soc_py = set()      # PySOC soc.py (the one that reads init.py)
        self.soc_td = set()
        self.pysoc_py = set()
        self.archives = set()    # pysoc.tar.gz, molsoc.tar.gz, pysoc-master.zip ...
        self.init_py = set()     # PySOC init.py files (any copy)
        self.newer_pysoc = set()  # folders of the 2020+ PySOC (does not use init.py)
        self.folders = 0
        self.unreadable = 0
        self.stopped = False
        self.seconds = 0.0

    def add_gaussian(self, folder, how):
        folder = os.path.realpath(folder)
        if os.path.basename(folder) in GAUSSIAN_VERSIONS and os.path.isdir(folder):
            self.gaussian.setdefault(folder, set()).add(how)


PYSOC_INIT_SETTINGS = ("QM_code", "molsoc_path", "n_s")  # every PySOC init.py sets these
INIT_PATH_SETTINGS = ("g09root", "molsoc_path", "dir_para_basis")  # the paths shown


def is_pysoc_init(path):
    """True only for a real PySOC init.py (it sets QM_code, molsoc_path and n_s)."""
    try:
        if os.path.getsize(path) > 65536:
            return False
    except OSError:
        return False
    text = read_text(path, 65536) or ""
    return all(re.search(r"^\s*" + name + r"\s*=", text, re.MULTILINE)
               for name in PYSOC_INIT_SETTINGS)


def is_pysoc_soc_py(path):
    text = read_text(path) or ""
    return "from init import" in text


ARCHIVE = re.compile(r"^(py|mol)soc[\w.-]*\.(zip|tar\.gz|tgz|tar)$", re.IGNORECASE)


def look_at_folder(found, folder, files):
    """Check the files of one folder (only names first; contents only for a few)."""
    name = os.path.basename(folder)
    names = set(files)
    if name in GAUSSIAN_VERSIONS and name in names:
        found.add_gaussian(folder, "found by the search")
    if name.lower().startswith("mio") and any(f.endswith(".basis") for f in files):
        found.basis.add(os.path.realpath(folder))
    if name == "program" and "main.py" in names and os.path.basename(
            os.path.dirname(folder)) == "pysoc":
        found.newer_pysoc.add(os.path.realpath(os.path.dirname(os.path.dirname(folder))))
    for file_name in files:
        path = os.path.join(folder, file_name)
        if file_name == MOLSOC_NAME or (file_name == "molsoc" and folder.endswith("data/bin")):
            if os.path.isfile(path):
                found.molsoc.add(os.path.realpath(path))
        elif file_name == "rwfdump":
            if os.path.isfile(path):
                found.rwfdump.add(os.path.realpath(path))
        elif file_name == "soc.py":
            if is_pysoc_soc_py(path):
                found.soc_py.add(os.path.realpath(path))
        elif file_name == "soc_td":
            if os.path.isfile(path):
                found.soc_td.add(os.path.realpath(path))
        elif file_name == "pysoc.py":
            if os.path.isfile(path):
                found.pysoc_py.add(os.path.realpath(path))
        elif ARCHIVE.match(file_name):
            if os.path.isfile(path):
                found.archives.add(os.path.realpath(path))
        elif file_name.endswith("init.py") and "__init" not in file_name:
            if os.path.isfile(path) and is_pysoc_init(path):
                found.init_py.add(os.path.abspath(path))


def quick_checks(found):
    """Places that are known without searching: the g16 command, Gaussian variables."""
    for version in GAUSSIAN_VERSIONS:
        program = shutil.which(version)
        if program:
            found.add_gaussian(os.path.dirname(os.path.realpath(program)),
                               "the '{0}' command in this terminal".format(version))
    for variable in ("g16root", "g09root", "g03root"):
        value = os.environ.get(variable)
        if value:
            found.add_gaussian(os.path.join(value, variable[:3]),
                               "the {0} variable of this terminal".format(variable))
    for entry in os.environ.get("GAUSS_EXEDIR", "").split(":"):
        if entry:
            found.add_gaussian(entry, "the GAUSS_EXEDIR variable of this terminal")
    for folder in found.gaussian:
        if os.path.isfile(os.path.join(folder, "rwfdump")):
            found.rwfdump.add(os.path.realpath(os.path.join(folder, "rwfdump")))
    for name, store in ((MOLSOC_NAME, found.molsoc), ("soc_td", found.soc_td),
                        ("pysoc.py", found.pysoc_py)):
        program = shutil.which(name)
        if program:
            store.add(os.path.realpath(program))
    program = shutil.which("soc.py")
    if program and is_pysoc_soc_py(program):
        found.soc_py.add(os.path.realpath(program))


def search_roots(args):
    if not args:
        return [os.sep], "the whole computer"
    roots = []
    for arg in args:
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(arg)))
        if not os.path.isdir(path):
            say("  [!] Not a folder, skipped:  " + path)
            continue
        roots.append(path)
    roots = natural_sorted(set(roots))
    kept = [r for r in roots
            if not any(r != o and r.startswith(o.rstrip(os.sep) + os.sep) for o in roots)]
    return kept, ", ".join(kept)


def walk(found, roots):
    show_progress = sys.stderr.isatty()
    width = shutil.get_terminal_size((80, 20)).columns
    last = 0.0
    started = time.time()

    def unreadable(error):
        found.unreadable += 1

    try:
        for root in roots:
            for folder, dirnames, files in os.walk(root, onerror=unreadable):
                found.folders += 1
                dirnames[:] = [d for d in dirnames if d not in SKIP_NAMES
                               and os.path.join(folder, d) not in SKIP_FOLDERS]
                look_at_folder(found, folder, files)
                if show_progress and time.time() - last > 0.3:
                    last = time.time()
                    text = "  searching ... {0:,} folders   {1}".format(found.folders, folder)
                    sys.stderr.write("\r" + safe(text[:width - 1]).ljust(width - 1))
                    sys.stderr.flush()
    except KeyboardInterrupt:
        found.stopped = True
    if show_progress:
        sys.stderr.write("\r" + " " * (width - 1) + "\r")
        sys.stderr.flush()
    found.seconds = time.time() - started


# ---------------------------------------------------------------------------
# Making sense of what was found
# ---------------------------------------------------------------------------
def gaussian_details(found):
    """One dict per Gaussian folder, best first."""
    for path in found.rwfdump:  # a rwfdump inside a g16/g09 folder points to it too
        found.add_gaussian(os.path.dirname(path), "found by the search")
    from_terminal = set()
    for version in GAUSSIAN_VERSIONS:
        program = shutil.which(version)
        if program:
            from_terminal.add(os.path.dirname(os.path.realpath(program)))
    details = []
    for folder, how in found.gaussian.items():
        version = os.path.basename(folder)
        rwfdump = os.path.join(folder, "rwfdump")
        profile = os.path.join(folder, "bsd", version + ".profile")
        info = {
            "folder": folder, "version": version, "root": os.path.dirname(folder),
            "how": sorted(how), "program": os.path.join(folder, version),
            "has_program": is_executable_file(os.path.join(folder, version)),
            "rwfdump": rwfdump if os.path.isfile(rwfdump) else None,
            "profile": profile if os.path.isfile(profile) else None,
            "in_terminal": folder in from_terminal,
        }
        if info["rwfdump"]:
            info["rwfdump_runs"] = os.access(rwfdump, os.X_OK)
            info["rwfdump_needs"] = shebang_program(rwfdump)
            info["rwfdump_needs_ok"] = program_available(info["rwfdump_needs"])
        details.append(info)
    details.sort(key=lambda d: (not d["in_terminal"], not d["has_program"],
                                not d["rwfdump"], GAUSSIAN_VERSIONS.index(d["version"]),
                                natural_key(d["folder"])))
    return details


def molsoc_details(found):
    details = []
    for path in found.molsoc:
        kind, text = MOLSOC_KNOWN.get(sha256(path) or "", ("unknown", ""))
        if kind == "unknown":
            if "molsoc_modified" in path:
                kind, text = "modified-folder", "in a molsoc_modified folder (modified MolSOC)"
            else:
                text = "a MolSOC of unknown version - check it is the MODIFIED one"
        details.append({"path": path, "kind": kind, "text": text,
                        "runs": os.access(path, os.X_OK), "missing": missing_libraries(path)})
    order = ("modified", "modified-folder", "newer", "unknown", "original")
    details.sort(key=lambda d: (order.index(d["kind"]), bool(d["missing"]), natural_key(d["path"])))
    return details


def g09_lines(soc_py):
    """Line numbers and text of the soc.py lines that contain '/g09/'."""
    text = read_text(soc_py) or ""
    return [(number, line.rstrip()) for number, line in enumerate(text.splitlines(), 1)
            if "/g09/" in line and not line.strip().startswith("#")]


def pysoc_details(found):
    """One dict per folder that holds a PySOC soc.py, best first."""
    folders = {}
    for path in found.soc_py:
        folders.setdefault(os.path.dirname(path), {})["soc_py"] = path
    for path in found.soc_td:
        if os.path.dirname(path) in folders:
            folders[os.path.dirname(path)]["soc_td"] = path
    for path in found.pysoc_py:
        if os.path.dirname(path) in folders:
            folders[os.path.dirname(path)]["pysoc_py"] = path
    details = []
    for folder, files in folders.items():
        soc_py = files["soc_py"]
        info = {"folder": folder, "soc_py": soc_py,
                "soc_py_text": SOC_PY_KNOWN.get(sha256(soc_py) or "", "unknown version"),
                "soc_py_needs": shebang_program(soc_py),
                "soc_py_runs": os.access(soc_py, os.X_OK),
                "g09_lines": g09_lines(soc_py),
                "soc_td": files.get("soc_td"), "pysoc_py": files.get("pysoc_py")}
        if info["soc_td"]:
            info["soc_td_text"] = SOC_TD_KNOWN.get(sha256(info["soc_td"]) or "", "unknown version")
            info["soc_td_runs"] = os.access(info["soc_td"], os.X_OK)
            info["soc_td_missing"] = missing_libraries(info["soc_td"])
        if info["pysoc_py"]:
            info["scrip_soc"] = setting_value(read_text(info["pysoc_py"]) or "", "scrip_soc")
            info["scrip_ok"] = (info["scrip_soc"] is not None and
                                os.path.realpath(info["scrip_soc"]) == folder)
            info["pysoc_runs"] = os.access(info["pysoc_py"], os.X_OK)
        details.append(info)
    details.sort(key=lambda d: (not (d["soc_td"] and d["pysoc_py"]),
                                d["soc_py_text"] == "unknown version", natural_key(d["folder"])))
    return details


def python2_details():
    for name in ("python2", "python2.7", "python"):
        program = shutil.which(name)
        if not program:
            continue
        output = run_quietly([program, "--version"]) or ""
        match = re.search(r"Python (2\.\d+[\.\d]*)", output)
        if match:
            return {"name": name, "path": program, "version": match.group(1)}
    return None


def init_groups(found):
    """init.py copies grouped by the folder above their folder (e.g. soc_singlet)."""
    groups = {}
    for path in found.init_py:
        folder = os.path.dirname(path)
        parent = os.path.dirname(folder)
        if os.path.basename(path) == "init.py" and re.match(r"^g\d+", os.path.basename(folder)):
            key = parent                    # soc_singlet/g1.com/init.py -> soc_singlet
        else:
            key = folder
        groups.setdefault(key, []).append(path)
    # Files that contain the same paths count as one set (other lines may differ).
    versions = {}
    for path in found.init_py:
        text = read_text(path, 65536) or ""
        values = tuple(setting_value(text, name) for name in INIT_PATH_SETTINGS)
        versions.setdefault(values, []).append(path)
    return groups, [{"values": values, "paths": paths} for values, paths in versions.items()]


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def report(found, searched):
    out = []
    todo = []
    add = out.append
    gauss = gaussian_details(found)
    molsoc = molsoc_details(found)
    pysoc = pysoc_details(found)
    py2 = python2_details()
    basis = natural_sorted(found.basis)
    groups, versions = init_groups(found)

    add(LINE)
    add(" {0}   (computer: {1}, user: {2}, {3})".format(
        RESULTS_HEADER, socket.gethostname(), getpass.getuser(), time.strftime("%Y-%m-%d %H:%M")))
    add(" Searched: {0}  ({1:,} folders, {2:.0f} s)".format(searched, found.folders, found.seconds))
    if found.stopped:
        add(" [!] The search was stopped early with Ctrl+C, so something may be missing.")
    add("=" * 24 + " COPY FROM HERE " + "=" * 32)
    add("")

    # ---- 1. the init.py values -------------------------------------------
    add("1) PATHS FOR init.py ON THIS COMPUTER")
    if gauss:
        add("   g09root        = " + quoted(gauss[0]["root"]))
    else:
        add("   g09root        = NOT FOUND  (no Gaussian folder found)")
    usable = [m for m in molsoc if m["kind"] != "original"]
    if usable:
        add("   molsoc_path    = " + quoted(usable[0]["path"]))
    else:
        add("   molsoc_path    = NOT FOUND  (no modified MolSOC found)")
    if basis:
        add("   dir_para_basis = " + quoted(basis[0]) + "   (only used for TD-DFTB)")
    else:
        add("   dir_para_basis = not found; only used for TD-DFTB, so for Gaussian it can stay")
    if pysoc:
        add("   PySOC folder   = " + quoted(pysoc[0]["folder"])
            + "   (soc.py, soc_td, pysoc.py; goes into pysoc.py as scrip_soc)")
    else:
        add("   PySOC folder   = NOT FOUND  (soc.py / soc_td / pysoc.py)")
    add("")

    # ---- 2. details ---------------------------------------------------------
    add("2) DETAILS")
    add("   Gaussian  (g09root = the folder that CONTAINS the g16 or g09 folder)")
    if not gauss:
        add("     none found")
        todo.append("Gaussian not found. Run this program in the terminal where g16 works, "
                    "or give the folder that holds Gaussian:  python3 search.py /that/folder")
    for number, g in enumerate(gauss):
        add("     {0} {1}   (Gaussian {2}; {3})".format(
            "[best]" if number == 0 else "[also]", g["folder"], g["version"][1:], "; ".join(g["how"])))
        add("            {0:<9}: {1}{2}".format(g["version"], g["program"],
                                                "" if g["has_program"] else "   (NOT FOUND)"))
        if g["rwfdump"]:
            note = []
            if not g["rwfdump_runs"]:
                note.append("not executable")
            if g["rwfdump_needs"]:
                note.append("needs {0}: {1}".format(
                    g["rwfdump_needs"], "installed" if g["rwfdump_needs_ok"] else "NOT INSTALLED"))
            add("            rwfdump  : {0}{1}".format(g["rwfdump"],
                                                        "   (" + "; ".join(note) + ")" if note else ""))
        else:
            add("            rwfdump  : NOT FOUND in this folder")
        add("            profile  : {0}".format(g["profile"] or "not found"))
    if gauss:
        best = gauss[0]
        if not best["rwfdump"]:
            todo.append("rwfdump (Gaussian utility that PySOC uses) is not in " + best["folder"])
        else:
            if not best["rwfdump_needs_ok"]:
                needs = os.path.basename(best["rwfdump_needs"])
                hint = "sudo apt install csh" if needs in ("csh", "tcsh") else "install " + needs
                todo.append("rwfdump needs '{0}', which is not installed:  {1}".format(needs, hint))
            if not best["rwfdump_runs"]:
                todo.append("rwfdump is not executable:  chmod +x " + best["rwfdump"])
        if best["version"] != "g09":
            lines = pysoc[0]["g09_lines"] if pysoc else []
            where = ("lines " + ", ".join(str(n) for n, _ in lines)) if lines else "two lines"
            todo.append("soc.py looks for g09root + '/g09/rwfdump'. This computer has Gaussian {0}, "
                        "so in soc.py {1} must say {2} instead of g09.".format(
                            best["version"][1:], where, best["version"]))

    add("   MolSOC  (molsoc_path = the file molsoc0.1.exe)")
    if not molsoc:
        add("     none found")
    for number, m in enumerate(molsoc):
        add("     {0} {1}".format("[best]" if number == 0 and m["kind"] != "original" else "[also]",
                                  m["path"]))
        state = "runs: OK" if m["runs"] and not m["missing"] else (
            "NOT executable" if not m["runs"] else "MISSING libraries: " + ", ".join(m["missing"]))
        add("            {0}; {1}".format(m["text"], state))
    if not usable:
        if any(m["kind"] == "original" for m in molsoc):
            todo.append("Only the ORIGINAL MolSOC was found; PySOC needs the modified one.")
        todo.append("Get the modified MolSOC (it is ready to use, no compiling):  wget {0}  "
                    "then  tar xzf molsoc.tar.gz   ->  molsoc/molsoc_modified/molsoc0.1/bin/"
                    "molsoc0.1.exe".format(MOLSOC_URL))
    else:
        if not usable[0]["runs"]:
            todo.append("MolSOC is not executable:  chmod +x " + usable[0]["path"])
        if usable[0]["missing"]:
            todo.append("MolSOC needs libraries this computer lacks: " + ", ".join(usable[0]["missing"]))

    add("   PySOC scripts  (the programs that read init.py)")
    if not pysoc:
        add("     none found")
        todo.append("PySOC (soc.py, soc_td, pysoc.py) not found. Get the 2016 release that uses "
                    "init.py:  wget {0}  then  tar xzf pysoc.tar.gz   ->  pysoc/bin/".format(PYSOC_URL))
    for number, p in enumerate(pysoc):
        add("     {0} {1}".format("[best]" if number == 0 else "[also]", p["folder"]))
        add("            soc.py   : {0}{1}".format(p["soc_py_text"],
                                                    "" if p["soc_py_runs"] else "; NOT executable"))
        if p["soc_td"]:
            state = "" if p["soc_td_runs"] else "; NOT executable"
            if p["soc_td_missing"]:
                state += "; MISSING libraries: " + ", ".join(p["soc_td_missing"])
            add("            soc_td   : {0}{1}".format(p["soc_td_text"], state))
        else:
            add("            soc_td   : NOT FOUND in this folder")
        if p["pysoc_py"]:
            add("            pysoc.py : scrip_soc = {0}{1}".format(
                quoted(p["scrip_soc"]) if p["scrip_soc"] is not None else "(not set)",
                "" if p["scrip_ok"] else "   -> must become " + quoted(p["folder"])))
        else:
            add("            pysoc.py : NOT FOUND in this folder")
    if pysoc:
        best = pysoc[0]
        if not best["soc_td"]:
            todo.append("soc_td is missing next to soc.py in " + best["folder"])
        if not best["pysoc_py"]:
            todo.append("pysoc.py is missing next to soc.py in " + best["folder"])
        elif not best["scrip_ok"]:
            todo.append("In pysoc.py set  scrip_soc = " + quoted(best["folder"]))
        not_runnable = [f for f, ok in ((best["soc_py"], best["soc_py_runs"]),
                                        (best["soc_td"], best.get("soc_td_runs", True)),
                                        (best["pysoc_py"], best.get("pysoc_runs", True))) if f and not ok]
        if not_runnable:
            todo.append("Not executable:  chmod +x " + " ".join(not_runnable))
        if best.get("soc_td_missing"):
            todo.append("soc_td needs libraries this computer lacks: " + ", ".join(best["soc_td_missing"]))
    for folder in natural_sorted(found.newer_pysoc):
        add("     [note] newer PySOC (2020 and later) in {0} - it does not use init.py".format(folder))
    archives = natural_sorted(found.archives)
    if archives:
        add("     downloaded archives:")
        for path in archives:
            add("            " + path)
        if not pysoc or not usable:
            todo.append("PySOC/MolSOC archives are on this computer (listed above); unpack them "
                        "with  tar xzf <file>  in the folder where they are.")

    add("   Python 2  (soc.py and pysoc.py are written in Python 2)")
    if py2:
        add("            {0}   (Python {1})".format(py2["path"], py2["version"]))
        if py2["name"] != "python2" and pysoc and pysoc[0]["soc_py_needs"] == "python2":
            todo.append("soc.py starts with '#!/usr/bin/env python2', but only '{0}' exists; "
                        "run it as  {0} soc.py  or ask for a python2 link.".format(py2["name"]))
    else:
        add("            NOT FOUND")
        todo.append("Python 2 is not installed:  " + python2_install_hint())

    add("   init.py copies on this computer: {0}".format(len(found.init_py)))
    for key in natural_sorted(groups):
        paths = groups[key]
        if all(os.path.dirname(os.path.dirname(p)) == key for p in paths):
            names = natural_sorted(os.path.basename(os.path.dirname(p)) + "/" + os.path.basename(p)
                                   for p in paths)
        else:
            names = natural_sorted(os.path.basename(p) for p in paths)
        shown = names[0] + (" ... " + names[-1] if len(names) > 2 else
                            ", " + names[-1] if len(names) == 2 else "")
        add("            {0:>3} in {1}   ({2})".format(len(paths), key, shown))
    if versions:
        add("            Paths written in them now ({0} different set(s)):".format(len(versions)))
        for number, version in enumerate(sorted(versions, key=lambda v: -len(v["paths"])), 1):
            add("            set {0}  ({1} file(s)):".format(number, len(version["paths"])))
            for name, value in zip(INIT_PATH_SETTINGS, version["values"]):
                if value is None:
                    continue
                exists = os.path.exists(value)
                add("              {0:<14} = {1}   {2}".format(
                    name, quoted(value), "(exists here)" if exists else "(NOT on this computer)"))
    add("")

    # ---- 3. to do -------------------------------------------------------------
    add("3) STILL MISSING / TO DO")
    if found.stopped:
        todo.insert(0, "The search was stopped early. Run it again and let it finish, or give "
                       "folders:  python3 search.py ~/ /opt")
    if not todo:
        add("   nothing - everything PySOC needs was found")
    for item in todo:
        add("   - " + item)
    add("")
    add("=" * 24 + " COPY UP TO HERE " + "=" * 31)
    if found.unreadable:
        add(" ({0:,} folder(s) could not be opened - no permission. That is normal for a".format(
            found.unreadable))
        add("  normal user; if something is NOT FOUND, it may be in one of them.)")
    return out


def results_file():
    """Where to save the results: this folder, or the home folder if that is not possible."""
    for folder in (os.getcwd(), os.path.expanduser("~")):
        for number in range(0, 100):
            name = RESULTS_NAME if number == 0 else "search_results_{0}.txt".format(number)
            path = os.path.join(folder, name)
            if os.path.exists(path):
                first = read_text(path, 512) or ""
                if RESULTS_HEADER not in first:
                    continue  # someone else's file with this name: never overwrite it
            if os.access(folder, os.W_OK):
                return path
            break
    return None


def main():
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        say(__doc__)
        return 0
    say(LINE)
    say("  SEARCH: finding on this computer what PySOC's init.py needs")
    say("  (Gaussian / rwfdump, modified MolSOC, PySOC scripts, Python 2, init.py copies)")
    say("  Nothing is changed. Press Ctrl+C to stop the search early.")
    say(LINE)
    roots, searched = search_roots(sys.argv[1:])
    if not roots:
        say("  [!] None of the folders given exists. Nothing was searched.")
        return 1
    found = Found()
    quick_checks(found)
    say("  Searching " + searched + " ... (this can take a few minutes)")
    walk(found, roots)
    if found.stopped:
        say("  Stopped by you. Showing what was found so far.")
    lines = report(found, searched)
    say("")
    for line in lines:
        say(line)
    path = results_file()
    if path:
        try:
            with open(path, "w") as handle:
                handle.write("\n".join(lines) + "\n")
            say("")
            say("Saved to:  " + path)
            say("Upload that file, or copy everything between the two COPY lines.")
        except (IOError, OSError) as err:
            say("")
            say("[!] Could not save {0} ({1}); copy the lines above instead.".format(
                path, err.strerror or err))
    else:
        say("")
        say("[!] Could not save the results to a file; copy the lines above instead.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("")
        say("Stopped by you.")
        sys.exit(130)
