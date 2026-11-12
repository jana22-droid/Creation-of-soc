#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run init.py  (run PySOC in every sub-folder of soc_singlet, one after another)
=============================================================================

init.py is the settings file of PySOC; it is used by running PySOC in the
folder where it is. This program does that in every sub-folder of
soc_singlet, one after another, in the order g1.com, g2.com, ... g41.com,
exactly as PySOC's own pysoc.py does it:

    cd soc_singlet/g1.com  ;  python2 soc.py   (reads init.py, gaussian.log, gaussian.rwf)
                              soc_td           (writes soc_out.dat)
    cd soc_singlet/g2.com  ;  ...

A sub-folder counts as done only when its soc_out.dat has been written by
this run and holds every <S|Hso|T> line init.py asks for. The output of
PySOC for each sub-folder is kept in pysoc.log in that sub-folder.
Only soc_singlet is run. soc_triplet is not touched.

HOW TO RUN (Ubuntu terminal, the same terminal where g16 normally works)
    python3 run_init.py

The program asks where soc_singlet is (soc_singlet itself, or the folder
that contains it) and which PySOC folder to use, shows a summary, and after
you type y runs IN THE BACKGROUND: you can close the terminal or log out.

WHILE IT RUNS
    Watch progress :  tail -f .../soc_singlet/run_init.log
                      (Ctrl+C only stops the watching, not the run)
    Stop after the folder that is running now :  touch .../soc_singlet/STOP
    Stop at once   :  the exact kill command is printed when the run starts
    Check later    :  run this program again; it shows how far it is

BEFORE THE FIRST RUN
    * The Gaussian jobs (submit_soc_singlet.py) must have finished.
    * init.py must have this computer's paths (replace.py).

SAFETY
    * Nothing starts until you confirm the summary.
    * Sub-folders whose soc_out.dat is complete and newer than init.py,
      gaussian.log and gaussian.rwf are skipped, so running again is safe.
    * No file is ever deleted. Before a sub-folder is run AGAIN, the result
      files of the last run (soc_out.dat, pysoc.log and the five rwfdump files
      MO_energy, MOA_coeffs, MOB_coeffs, XY_coeffs, AO_overlap) are kept with
      .old added to their names; on a first run nothing is renamed.
    * After soc.py, every file PySOC needs is checked to have been written by
      THIS run, so files left from an earlier run can never be taken as new
      results.
    * Nothing starts while Gaussian jobs are still running on this soc_singlet.
    * If 3 sub-folders fail one after another, the run stops.
    * PySOC's own files (soc.py, soc_td, MolSOC) are never changed. If
      PySOC's soc.py looks for Gaussian 09 but this computer has Gaussian 16,
      the program offers to run a copy of soc.py that uses g16 (kept in
      soc_singlet/pysoc_g16/); you are asked first.
"""
from __future__ import print_function

import sys

# Stop early, with a clear message, if started with the old Python 2.
if sys.version_info[0] < 3:
    sys.stderr.write(
        "\nThis program needs Python 3 (PySOC itself runs with Python 2).\n"
        "Please run it like this:\n\n"
        "    python3 run_init.py\n\n")
    sys.exit(1)

import ast
import glob
import os
import re
import shlex
import shutil
import signal
import subprocess
import textwrap
import time

# ---------------------------------------------------------------------------
# Settings (normally nothing needs to be changed here)
# ---------------------------------------------------------------------------
PYSOC_BIN = "/home/vsrgroup3/softwares/pySOC/pysoc-master/pysoc/bin"  # soc.py and soc_td
PYTHON2_NAMES = ("python2", "python2.7")   # PySOC's soc.py is written in Python 2
INIT_NAME = "init.py"
SOC_OUT = "soc_out.dat"          # written by soc_td: the result
JOB_LOG = "pysoc.log"            # what soc.py and soc_td print, in each sub-folder
QM_LOG = "gaussian.log"          # PySOC reads these two (names fixed inside soc.py)
QM_RWF = "gaussian.rwf"
TD_INPUT = "soc_td_input.dat"    # written by soc.py at its very end, read by soc_td
# Files each step must write in the sub-folder during the run (checked by time):
RWFDUMP_FILES = ("MO_energy", "MOA_coeffs", "MOB_coeffs", "XY_coeffs", "AO_overlap")
MOLSOC_FILES = ("soint", "molsoc_overlap.dat")
MOLSOC_IF_PRESENT = ("molsoc_dipole.dat",)
SOC_PY_FILES = ("ao_basis.dat", "molsoc.inp", "molsoc_basis", "mo_ene.dat", "mo_coeff.dat",
                "ao_overlap.dat", "ci_coeff.dat", "soc_ao.dat", "s_matr.dat", "dip_ao.dat",
                TD_INPUT)
RUN_LOG = "run_init.log"         # progress of the whole run, inside soc_singlet
LOCK_NAME = ".run_init.lock"
SUBMIT_LOCK = ".submit_soc_singlet.lock"   # lock of a running submit_soc_singlet.py
STOP_NAME = "STOP"               # touch soc_singlet/STOP to stop after the current folder
G16_COPY_FOLDER = "pysoc_g16"    # inside soc_singlet: copy of soc.py that uses g16
MAX_FAILS_IN_A_ROW = 3           # stop the run after this many failures in a row
MIN_FREE_GB = 1.0                # do not start a folder with less free disk space than this
GAUSSIAN = ("g16", "g09")
SOC_FOLDER = "soc_singlet"       # the only folder that is run
OTHER_SOC_FOLDER = "soc_triplet"  # never touched
ORIGINAL_FOLDERS = ("singlet", "triplet")
SUBFOLDER_EXTENSION = ".com"     # sub-folders are named g1.com, g2.com, ...
MAX_SEARCH_DEPTH = 10

LINE = "=" * 70

# Status of each sub-folder before starting
NEW = "new"              # never run -> will run
AGAIN = "again"          # soc_out.dat there but old or incomplete -> will run again
DONE = "done"            # complete soc_out.dat, newer than its inputs -> skipped
NOT_READY = "not ready"  # Gaussian output missing or not finished -> skipped
BLOCKED = "blocked"      # something is wrong -> nothing at all is started


class UserQuit(Exception):
    """The user pressed Ctrl+D at a question."""


# ---------------------------------------------------------------------------
# Talking to the user
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


def warn(text):
    say("  [!] " + text)


def ask(prompt):
    try:
        return input(safe(prompt))
    except EOFError:
        say("")
        raise UserQuit()


def ask_yes_no(question):
    while True:
        answer = ask(question + " [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        warn("Please type y (yes) or n (no).")


def ask_choice(question, options):
    """Show a numbered list and return the index (0-based) of the chosen option."""
    say(question)
    for number, option in enumerate(options, 1):
        say("    {0}) {1}".format(number, option))
    while True:
        answer = ask("  Type a number (1-{0}): ".format(len(options))).strip()
        if re.match(r"^[0-9]+$", answer) and 1 <= int(answer) <= len(options):
            return int(answer) - 1
        warn("Please type one of the numbers shown.")


def show_wrapped(names):
    for row in textwrap.wrap(", ".join(names), width=64,
                             break_long_words=False, break_on_hyphens=False):
        say("      " + row)


def natural_key(text):
    """Sort key that puts g2 before g10 (normal sorting would not)."""
    parts = re.split(r"(\d+)", text)
    return [int(part) if index % 2 else part.lower()
            for index, part in enumerate(parts)]


def natural_sorted(items):
    return sorted(items, key=lambda item: (natural_key(item), item))


def current_folder():
    try:
        return os.getcwd()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Tab completion of paths (like in the terminal)
# ---------------------------------------------------------------------------
def path_completions(text):
    """All paths that start with what has been typed so far."""
    quote = ""
    body = text
    if body[:1] in ("'", '"'):
        quote, body = body[0], body[1:]
    expanded = os.path.expanduser(body)
    home_from, home_to = "", ""
    if body.startswith("~"):
        tilde_part = body.split("/", 1)[0]
        home = os.path.expanduser(tilde_part)
        if home != tilde_part:
            home_from, home_to = home, tilde_part
    results = []
    for match in natural_sorted(glob.glob(glob.escape(expanded) + "*")):
        if os.path.isdir(match):
            match += "/"
        if home_from and match.startswith(home_from):
            match = home_to + match[len(home_from):]
        results.append(quote + match)
    return results


def enable_tab_completion():
    try:
        import readline
    except ImportError:
        return  # works fine without it, just no Tab completion
    matches = []

    def complete(text, state):
        try:
            if state == 0:
                matches[:] = path_completions(text)
            return matches[state] if state < len(matches) else None
        except Exception:
            return None

    try:
        readline.set_completer_delims("\t\n")
        readline.set_completer(complete)
        if "libedit" in (readline.__doc__ or ""):
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Understanding a typed path
# ---------------------------------------------------------------------------
def readings_of(raw):
    """Every sensible way to read a typed path, best first."""
    text = raw.strip()
    if text.startswith("file://"):
        from urllib.parse import unquote
        text = unquote(text[len("file://"):])
    readings = []

    def add(candidate):
        candidate = candidate.strip()
        if candidate and "\0" not in candidate and candidate not in readings:
            readings.append(candidate)

    try:
        # Like the shell: handles 'quotes', "quotes" and escaped\ spaces.
        words = shlex.split(text)
        if len(words) == 1:
            add(words[0])
    except ValueError:  # e.g. a quote that was opened but never closed
        pass
    add(text)  # exactly as typed
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        add(text[1:-1])  # only the outer quotes removed
    return [os.path.expandvars(os.path.expanduser(r)) for r in readings]


def find_path(raw):
    """
    Return (existing_path, best_guess, suggestions).
    existing_path is None when nothing exists at the typed path. Then
    suggestions lists existing folders the user may have meant (the same
    relative path seen from the home folder, from / or from /home).
    """
    readings = readings_of(raw)
    if not readings:
        return None, raw.strip(), []
    for reading in readings:
        full = os.path.abspath(reading)
        if os.path.exists(full):
            return full, full, []
    suggestions = []
    for reading in readings:
        if os.path.isabs(reading) or reading.startswith("."):
            continue
        for base in (os.path.expanduser("~"), os.sep, "/home"):
            full = os.path.abspath(os.path.join(base, reading))
            if os.path.exists(full) and full not in suggestions:
                suggestions.append(full)
    return None, os.path.abspath(readings[0]), suggestions


def pick_suggestion(suggestions):
    if not suggestions:
        return None
    if len(suggestions) == 1:
        if ask_yes_no("  Did you mean  " + suggestions[0] + "  ?"):
            return suggestions[0]
        return None
    choice = ask_choice("  Did you mean one of these?", suggestions + ["None of these"])
    return suggestions[choice] if choice < len(suggestions) else None


def existing_path_from(raw, what):
    """Turn typed text into an existing path, or None (after explaining why)."""
    found, guess, suggestions = find_path(raw)
    if found is not None:
        return found
    warn("{0} not found:  {1}".format(what, guess))
    picked = pick_suggestion(suggestions)
    if picked is None:
        warn("Please check the spelling and type the path again.")
    return picked


def is_inside(path, folder):
    path = os.path.realpath(path)
    folder = os.path.realpath(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


# ---------------------------------------------------------------------------
# Step 1: find soc_singlet and its sub-folders
# ---------------------------------------------------------------------------
def same_name(name, wanted):
    return name.lower() == wanted.lower()


def is_soc_folder_name(name):
    return same_name(name, SOC_FOLDER) or same_name(name, OTHER_SOC_FOLDER)


def subfolder_kind(parent, name):
    """
    'ok' for a sub-folder made by creation_of_soc.py (g1.com, or g1 with g1.com
    inside), 'link' if such a sub-folder is a link, else None (not one of them).
    """
    if name.startswith("."):
        return None
    path = os.path.join(parent, name)
    if not os.path.isdir(path):
        return None
    extension = SUBFOLDER_EXTENSION.lower()
    named_like_file = name.lower().endswith(extension) and len(name) > len(extension)
    if not named_like_file and not os.path.isfile(os.path.join(path, name + SUBFOLDER_EXTENSION)):
        return None
    return "link" if os.path.islink(path) else "ok"


def list_subfolders(soc_dir):
    """Return (sorted sub-folder names, linked sub-folder names, number of other items)."""
    try:
        names = os.listdir(soc_dir)
    except OSError as err:
        warn("Cannot open this folder ({0}):  {1}".format(err.strerror or err, soc_dir))
        return None, [], 0
    good, links = [], []
    for name in names:
        kind = subfolder_kind(soc_dir, name)
        if kind == "ok":
            good.append(name)
        elif kind == "link":
            links.append(name)
    others = len(names) - len(good) - len(links)
    return natural_sorted(good), natural_sorted(links), others


def search_soc_singlet(top):
    """Look for folders named soc_singlet anywhere below top."""
    found = []
    top_depth = top.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, _ in os.walk(top):
        depth = dirpath.rstrip(os.sep).count(os.sep) - top_depth
        keep = []
        for name in dirnames:
            if same_name(name, SOC_FOLDER):
                found.append(os.path.join(dirpath, name))
            elif (not is_soc_folder_name(name) and not name.startswith(".")
                  and depth < MAX_SEARCH_DEPTH):
                keep.append(name)  # soc folders are not searched inside
        dirnames[:] = keep
    return natural_sorted(found)


def locate_soc_singlet(folder):
    """
    Work out which soc_singlet folder is meant by the folder the user typed.
    Returns the soc_singlet path, or None if there is none.
    """
    name = os.path.basename(folder)
    parent = os.path.dirname(folder)

    # (a) The path of soc_singlet itself.
    if same_name(name, SOC_FOLDER):
        say("  This is the soc_singlet folder itself.")
        return folder

    # (b) One sub-folder of soc_singlet (for example soc_singlet/g7.com).
    if same_name(os.path.basename(parent), SOC_FOLDER) and subfolder_kind(parent, name):
        say("  This is one sub-folder of soc_singlet ({0}), so the soc_singlet".format(name))
        say("  folder above it is used:  " + parent)
        return parent

    # (c) soc_triplet, singlet or triplet: soc_singlet is normally next to them.
    if same_name(name, OTHER_SOC_FOLDER) or any(same_name(name, n) for n in ORIGINAL_FOLDERS):
        say("  This is the '{0}' folder. Only soc_singlet is run, so".format(name))
        say("  soc_singlet is looked for in the folder above it:  " + parent)
        folder = parent

    # (d) The folder that contains soc_singlet (directly, or deeper inside).
    try:
        names = os.listdir(folder)
    except OSError as err:
        warn("Cannot open this folder ({0}):  {1}".format(err.strerror or err, folder))
        return None
    direct = natural_sorted(
        os.path.join(folder, n) for n in names
        if same_name(n, SOC_FOLDER) and os.path.isdir(os.path.join(folder, n)))
    if len(direct) == 1:
        say("  soc_singlet found inside this folder.")
        return direct[0]
    if len(direct) > 1:
        return direct[ask_choice(
            "  More than one 'soc_singlet' folder is here. Which one?", direct)]

    say("  No 'soc_singlet' folder directly inside, searching the sub-folders ...")
    found = search_soc_singlet(folder)
    if len(found) == 1:
        say("  Found:  " + found[0])
        if ask_yes_no("  Use this as the soc_singlet folder?"):
            return found[0]
        return None
    if len(found) > 1:
        choice = ask_choice("  Several 'soc_singlet' folders were found. Which one?",
                            found + ["None of these"])
        return found[choice] if choice < len(found) else None

    # (e) No folder called soc_singlet, but this folder holds g1.com, g2.com, ...
    subs, _, _ = list_subfolders(folder)
    if subs:
        say("  No folder named 'soc_singlet' was found, but this folder itself has")
        say("  {0} sub-folder(s) like {1}.".format(len(subs), subs[0]))
        if ask_yes_no("  Use this folder as the soc_singlet folder?"):
            return folder
    return None


def ask_for_soc_singlet():
    """Returns (soc_singlet path, sub-folder names, linked sub-folder names)."""
    say("")
    say(LINE)
    say("Where is the 'soc_singlet' folder?")
    say("  Type the path of soc_singlet itself, or of the folder that contains it")
    say("  (for example:  jana/pp/opt/b3lyp/scan/soc_singlet")
    say("            or:  jana/pp/opt/b3lyp/scan ).  Both work.")
    say("  Tab completes folder names. You are now in:  "
        + (current_folder() or "(unknown)"))
    say(LINE)
    while True:
        raw = ask("Path to soc_singlet: ")
        if not raw.strip():
            warn("Please type a path (or press Ctrl+C to stop).")
            continue
        folder = existing_path_from(raw, "Folder")
        if folder is None:
            continue
        if not os.path.isdir(folder):
            warn("This is a file, not a folder:  " + folder)
            continue
        soc_dir = locate_soc_singlet(folder)
        if soc_dir is None:
            say("")
            warn("No 'soc_singlet' folder was found in:  " + folder)
            warn("Please type another path.")
            continue
        subs, links, others = list_subfolders(soc_dir)
        if subs is None:
            continue
        if not subs and not links:
            warn("This soc_singlet has no sub-folders like g1.com:  " + soc_dir)
            warn("Please run creation_of_soc.py first, or type another path.")
            continue
        say("  OK, soc_singlet folder:  " + soc_dir)
        say("  {0} sub-folder(s) found:".format(len(subs) + len(links)))
        show_wrapped(natural_sorted(subs + links))
        if others:
            say("  ({0} other item(s) in soc_singlet are not g*.com sub-folders and are ignored.)"
                .format(others))
        return soc_dir, subs, links


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(text):
    say(stamp() + "  " + text)


def duration(seconds):
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "{0} h {1:02d} min".format(hours, minutes)
    if minutes:
        return "{0} min {1:02d} s".format(minutes, secs)
    return "{0} s".format(secs)


def quoted(path):
    return "'" + path + "'"


def read_text(path, limit=4 * 1024 * 1024):
    try:
        with open(path, "rb") as handle:
            return handle.read(limit).decode("utf-8", "replace")
    except (IOError, OSError):
        return None


def setting_value(text, name):
    """The value of  name = '...'  in init.py text (the last line that sets it)."""
    value = None
    for line in text.splitlines():
        match = re.match(r"\s*" + name + r"\s*=\s*(['\"])(.*?)\1", line)
        if match:
            value = match.group(2)
    return value


def setting_literal(text, name):
    """The value of  name = [ ... ]  in init.py text, or None if it is not a plain list."""
    value = None
    for line in text.splitlines():
        match = re.match(r"\s*" + name + r"\s*=\s*(.*)$", line)
        if match:
            expression = match.group(1).split("#")[0].strip()
            try:
                value = ast.literal_eval(expression)
            except (ValueError, SyntaxError):
                value = None
    return value


def expected_lines(init_text):
    """How many 'sum_soc' lines soc_td writes for this init.py (None if it cannot be told)."""
    n_s = setting_literal(init_text, "n_s")
    n_t = setting_literal(init_text, "n_t")
    n_g = setting_literal(init_text, "n_g")
    if not isinstance(n_s, list) or not isinstance(n_t, list) or not isinstance(n_g, list):
        return None
    with_ground = bool(n_g) and n_g[0] == "True"   # soc_td compares with 'True' exactly
    return (len(n_s) + (1 if with_ground else 0)) * len(n_t)


def shebang_program(path):
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
    if shutil.which("ldd") is None:
        return []
    try:
        result = subprocess.run(["ldd", path], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.split("=>")[0].strip() for line in result.stdout.splitlines() if "not found" in line]


def free_gb(folder):
    try:
        info = os.statvfs(folder)
        return info.f_bavail * info.f_frsize / (1024.0 ** 3)
    except (OSError, AttributeError):
        return None


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Gaussian output and running Gaussian programs
# ---------------------------------------------------------------------------
def log_state(path):
    """None (no file), 'normal', 'error' or 'incomplete'."""
    if not os.path.isfile(path):
        return None
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            handle.seek(max(0, size - 16384))
            tail = handle.read()
    except (IOError, OSError):
        return "incomplete"
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    if lines and b"Normal termination" in lines[-1]:
        return "normal"
    if b"Error termination" in tail:
        return "error"
    return "incomplete"


def is_gaussian_process(name):
    return name in GAUSSIAN or name.startswith("g16") or name.startswith("g09") or bool(
        re.match(r"^l\d+\.exe$", name))


def gaussian_processes():
    """{working folder (real path): [(pid, name), ...]} for every running Gaussian program."""
    busy = {}
    try:
        pids = [pid for pid in os.listdir("/proc") if pid.isdigit()]
    except OSError:
        return busy
    for pid in pids:
        try:
            with open("/proc/{0}/comm".format(pid)) as handle:
                name = handle.read().strip()
            if not is_gaussian_process(name):
                continue
            folder = os.path.realpath(os.readlink("/proc/{0}/cwd".format(pid)))
        except (IOError, OSError):
            continue
        busy.setdefault(folder, []).append((int(pid), name))
    return busy


def running_pid(soc_dir, lock_name, marker):
    """PID of a running program that holds this lock in soc_singlet, or None."""
    try:
        with open(os.path.join(soc_dir, lock_name)) as handle:
            pid = int(handle.read().strip() or "0")
    except (IOError, OSError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        with open("/proc/{0}/cmdline".format(pid), "rb") as handle:
            command = handle.read()
    except (IOError, OSError):
        return None
    return pid if marker.encode() in command else None


def remove_stale_lock(soc_dir):
    lock = os.path.join(soc_dir, LOCK_NAME)
    if os.path.lexists(lock) and running_pid(soc_dir, LOCK_NAME, "run_init") is None:
        try:
            os.remove(lock)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# soc_out.dat: is it there and complete?
# ---------------------------------------------------------------------------
def soc_out_state(folder, expected):
    """(True, number of lines) when complete, else (False, reason)."""
    path = os.path.join(folder, SOC_OUT)
    if not os.path.isfile(path):
        return False, "no " + SOC_OUT
    text = read_text(path) or ""
    lines = [line for line in text.splitlines() if line.startswith("sum_soc")]
    if not lines:
        return False, SOC_OUT + " has no sum_soc lines"
    broken = [line for line in lines
              if "nan" in line.lower() or "*" in line.split(":", 1)[-1]]
    if broken:
        return False, "{0} has {1} line(s) with NaN or ***** values".format(SOC_OUT, len(broken))
    if expected is not None and len(lines) != expected:
        return False, "{0} has {1} of the {2} sum_soc lines init.py asks for".format(
            SOC_OUT, len(lines), expected)
    return True, len(lines)


def last_error(path):
    """The last line of pysoc.log that says what went wrong (or '')."""
    text = read_text(path) or ""
    pattern = re.compile(r"error|traceback|not exist|no such file|cannot|permission denied|"
                         r"not found|severe|forrtl|segmentation", re.IGNORECASE)
    found = [line.strip() for line in text.splitlines()
             if pattern.search(line) and ".profile" not in line]   # soc.py runs the profile: harmless
    return found[-1][:160] if found else ""


# ---------------------------------------------------------------------------
# Python 2, PySOC and the soc.py that will be used
# ---------------------------------------------------------------------------
def find_python2():
    for name in PYTHON2_NAMES:
        program = shutil.which(name)
        if not program:
            continue
        try:
            result = subprocess.run([program, "--version"], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            continue
        match = re.search(r"Python (2\.\d+[\.\d]*)", result.stdout)
        if match:
            return os.path.abspath(program), match.group(1)
    return None, None


def python2_can_read(python2, path):
    """True if Python 2 can read soc.py (only checks the syntax; nothing is run)."""
    code = "import sys; compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')"
    try:
        result = subprocess.run([python2, "-c", code, path], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


class Pysoc(object):
    def __init__(self, folder):
        self.folder = folder
        self.soc_py = os.path.join(folder, "soc.py")
        self.soc_td = os.path.join(folder, "soc_td")


def pysoc_problems(pysoc):
    problems = []
    text = read_text(pysoc.soc_py) if os.path.isfile(pysoc.soc_py) else None
    if text is None:
        problems.append("there is no soc.py in it")
    elif "from init import" not in text:
        problems.append("its soc.py is not the PySOC soc.py that reads init.py")
    if not os.path.isfile(pysoc.soc_td):
        problems.append("there is no soc_td in it")
    elif not os.access(pysoc.soc_td, os.X_OK):
        problems.append("soc_td is not executable (chmod +x {0})".format(pysoc.soc_td))
    else:
        missing = missing_libraries(pysoc.soc_td)
        if missing:
            problems.append("soc_td needs libraries this computer lacks: " + ", ".join(missing))
    for name in ("init.py", "init.pyc", "init"):
        if os.path.exists(os.path.join(pysoc.folder, name)):
            problems.append("it contains '{0}': Python would read that one instead of the "
                            "init.py of each sub-folder; please move it away".format(name))
    return problems


def ask_for_pysoc():
    """Returns a Pysoc whose folder holds the PySOC soc.py and soc_td."""
    say("")
    say(LINE)
    say("The PySOC folder (the one with soc.py and soc_td)")
    say(LINE)
    folder = os.path.abspath(PYSOC_BIN)
    while True:
        pysoc = Pysoc(folder)
        problems = pysoc_problems(pysoc)
        say("  PySOC folder:  " + folder)
        if not problems:
            say("  OK, soc.py and soc_td found.")
            if ask_yes_no("  Use this PySOC folder?"):
                return pysoc
        else:
            for problem in problems:
                warn(problem)
        say("  Type the PySOC folder (the one with soc.py and soc_td), or the path of soc.py.")
        while True:
            raw = ask("PySOC folder: ")
            if not raw.strip():
                warn("Please type a path (or press Ctrl+C to stop).")
                continue
            path = existing_path_from(raw, "Folder")
            if path is None:
                continue
            folder = os.path.dirname(path) if os.path.isfile(path) else path
            break


def rwfdump_part(soc_text):
    """The part soc.py adds to g09root to call rwfdump, e.g. '/g09/rwfdump'."""
    match = re.search(r"g09root\s*\+\s*(['\"])(/[^'\"]*?rwfdump)", soc_text)
    return match.group(2) if match else None


def g16_version_of(soc_text):
    """soc.py with g16 instead of g09 on the lines that build the Gaussian paths."""
    changed = []
    lines = soc_text.splitlines(True)
    for index, line in enumerate(lines):
        if "g09root" in line and "/g09/" in line and not line.lstrip().startswith("#"):
            lines[index] = line.replace("/g09/", "/g16/").replace("g09.profile", "g16.profile")
            changed.append((index + 1, line.rstrip("\r\n"), lines[index].rstrip("\r\n")))
    return "".join(lines), changed


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------
class Job(object):
    def __init__(self, soc_dir, sub_name):
        self.sub_name = sub_name
        self.folder = os.path.join(soc_dir, sub_name)
        self.init = os.path.join(self.folder, INIT_NAME)
        self.status = NEW
        self.reason = ""
        self.g09root = None
        self.molsoc = None
        self.expected = None


def plan(soc_dir, subs, links):
    busy = gaussian_processes()
    jobs = []
    for name in natural_sorted(subs + links):
        job = Job(soc_dir, name)
        jobs.append(job)
        if name in links:
            job.status, job.reason = BLOCKED, "the sub-folder is a link, not a normal folder"
            continue
        text = read_text(job.init, 1024 * 1024) if os.path.isfile(job.init) else None
        if text is None:
            job.status, job.reason = BLOCKED, "no init.py in it (run copy_init.py first)"
            continue
        if not re.search(r"^\s*QM_code\s*=", text, re.MULTILINE):
            job.status, job.reason = BLOCKED, "its init.py is not a PySOC init.py"
            continue
        if setting_value(text, "QM_code") != "gauss_tddft":
            job.status, job.reason = BLOCKED, "init.py has QM_code = {0}, not 'gauss_tddft'".format(
                setting_value(text, "QM_code"))
            continue
        job.g09root = setting_value(text, "g09root")
        molsoc = job.molsoc = setting_value(text, "molsoc_path")
        wrong = []
        if not job.g09root or not os.path.isdir(job.g09root):
            wrong.append("g09root = {0}".format(quoted(job.g09root or "")))
        if not molsoc or not os.path.isfile(molsoc):
            wrong.append("molsoc_path = {0}".format(quoted(molsoc or "")))
        if wrong:
            job.status = BLOCKED
            job.reason = ("init.py has paths that are not on this computer ({0}); "
                          "run replace.py first".format("; ".join(wrong)))
            continue
        if not os.access(molsoc, os.X_OK):
            job.status, job.reason = BLOCKED, "MolSOC in init.py is not executable: " + molsoc
            continue
        if not os.access(job.folder, os.W_OK | os.X_OK):
            job.status, job.reason = BLOCKED, "no permission to write in this sub-folder"
            continue
        job.expected = expected_lines(text)
        if os.path.realpath(job.folder) in busy:
            job.status, job.reason = NOT_READY, "Gaussian is running in it right now"
            continue
        state = log_state(os.path.join(job.folder, QM_LOG))
        if state is None:
            job.status, job.reason = NOT_READY, "no gaussian.log (Gaussian has not run here)"
            continue
        if state != "normal":
            job.status, job.reason = NOT_READY, "gaussian.log does not end with Normal termination"
            continue
        rwf = os.path.join(job.folder, QM_RWF)
        if not os.path.isfile(rwf) or os.path.getsize(rwf) == 0:
            job.status, job.reason = NOT_READY, "no gaussian.rwf (needs %rwf=gaussian.rwf in gaussian.com)"
            continue
        complete, detail = soc_out_state(job.folder, job.expected)
        out_time = mtime(os.path.join(job.folder, SOC_OUT))
        if complete:
            newest_input = max(mtime(job.init) or 0, mtime(os.path.join(job.folder, QM_LOG)) or 0,
                               mtime(rwf) or 0)
            if out_time is not None and out_time >= newest_input:
                job.status = DONE
            else:
                job.status, job.reason = AGAIN, "soc_out.dat is older than init.py or the Gaussian files"
        elif os.path.lexists(os.path.join(job.folder, SOC_OUT)):
            job.status, job.reason = AGAIN, detail
    return jobs


def count(jobs, status):
    return sum(1 for job in jobs if job.status == status)


def show_summary(soc_dir, jobs, python2, version, pysoc, soc_py_used, rwfdump):
    say("")
    say(LINE)
    say("SUMMARY - please check. Nothing has been started yet.")
    say(LINE)
    say("  soc_singlet   :  " + soc_dir)
    say("  Sub-folders   :  {0}  ({1}{2})".format(
        len(jobs), jobs[0].sub_name, " ... " + jobs[-1].sub_name if len(jobs) > 1 else ""))
    say("  Python 2      :  {0}  (Python {1})".format(python2, version))
    say("  soc.py        :  " + soc_py_used)
    say("  soc_td        :  " + pysoc.soc_td)
    if rwfdump:
        say("  rwfdump       :  " + rwfdump)
    say("  Each folder   :  cd soc_singlet/<sub-folder>  then  python2 soc.py ; soc_td")
    say("                   result: {0}, PySOC output: {1}".format(SOC_OUT, JOB_LOG))
    say("  Order         :  one folder at a time; the next starts only after the")
    say("                   previous one has completely finished")
    say("  Will run (never run before)                 :  {0}".format(count(jobs, NEW)))
    if count(jobs, AGAIN):
        say("  Will run AGAIN                              :  {0}".format(count(jobs, AGAIN)))
        for job in jobs:
            if job.status == AGAIN:
                say("      {0}  ({1}; old files kept as .old)".format(job.sub_name, job.reason))
    if count(jobs, DONE):
        say("  Already have a complete soc_out.dat         :  {0}".format(count(jobs, DONE)))
    if count(jobs, NOT_READY):
        say("  NOT READY (Gaussian output missing), skipped:  {0}".format(count(jobs, NOT_READY)))
        for job in jobs:
            if job.status == NOT_READY:
                say("      {0}  ({1})".format(job.sub_name, job.reason))
    if count(jobs, BLOCKED):
        say("  Cannot be run                               :  {0}".format(count(jobs, BLOCKED)))
    expected = sorted(set(job.expected for job in jobs if job.expected is not None))
    if expected:
        say("  Expected in each soc_out.dat:  {0} sum_soc line(s) (from n_s, n_t, n_g in init.py)"
            .format(" or ".join(str(e) for e in expected)))
    say("  soc_triplet   :  not touched")
    say(LINE)


class CannotRun(Exception):
    """Something stops the run; the reason has already been shown."""


class Declined(Exception):
    """The user answered n; nothing is started."""


def choose_soc_py(jobs, pysoc):
    """
    Decide which soc.py to run. Returns (soc_py_to_use, g16_text_or_None, rwfdump_path).
    Raises CannotRun (after explaining why) or Declined.
    """
    roots = sorted(set(job.g09root for job in jobs if job.g09root))
    if len(roots) > 1:
        say("")
        warn("The init.py files have different g09root values:")
        for root in roots:
            say("      " + quoted(root))
        warn("Please run replace.py so that all of them have the same paths.")
        raise CannotRun()
    if not roots:
        return pysoc.soc_py, None, None
    root = roots[0]
    soc_text = read_text(pysoc.soc_py) or ""
    part = rwfdump_part(soc_text)
    if part is None:
        say("")
        warn("Could not find in soc.py where it calls Gaussian's rwfdump; this does not")
        warn("look like the PySOC 2016 soc.py:  " + pysoc.soc_py)
        raise CannotRun()
    rwfdump = root.rstrip(os.sep) + part
    if os.path.isfile(rwfdump):
        return pysoc.soc_py, None, rwfdump
    g16_rwfdump = root.rstrip(os.sep) + part.replace("/g09/", "/g16/")
    if "/g09/" in part and os.path.isfile(g16_rwfdump):
        new_text, changed = g16_version_of(soc_text)
        say("")
        say(LINE)
        say("  soc.py runs Gaussian's rwfdump as  g09root + '{0}', that is".format(part))
        say("      " + rwfdump)
        say("  which does not exist. This computer has Gaussian 16:")
        say("      " + g16_rwfdump)
        say("  PySOC can be run with a COPY of soc.py in which these line(s) say g16:")
        for number, old, new in changed:
            say("    line {0}:  {1}".format(number, old.strip()))
            say("         ->  {0}".format(new.strip()))
        say("  The copy is kept in soc_singlet/{0}/soc.py. PySOC's own soc.py is not"
            .format(G16_COPY_FOLDER))
        say("  changed; nothing else in the copy is different.")
        say(LINE)
        if not ask_yes_no("  Run PySOC with this g16 copy of soc.py?"):
            raise Declined()
        return None, new_text, g16_rwfdump
    say("")
    warn("Gaussian's rwfdump was not found where soc.py looks for it:")
    say("      " + rwfdump)
    if "/g09/" in part:
        say("      (and not in " + g16_rwfdump + " either)")
    warn("Check g09root in init.py (search.py shows the right value).")
    raise CannotRun()


def write_g16_copy(soc_dir, text, python2):
    folder = os.path.join(soc_dir, G16_COPY_FOLDER)
    path = os.path.join(folder, "soc.py")
    if os.path.lexists(folder) and (os.path.islink(folder) or not os.path.isdir(folder)):
        raise IOError("something that is not a folder is called " + folder)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    for name in os.listdir(folder):
        if name not in ("soc.py",):
            raise IOError("{0} holds other files ({1}); please empty it".format(folder, name))
    with open(path, "w") as handle:
        handle.write(text)
    os.chmod(path, 0o755)
    if read_text(path) != text:
        raise IOError("the g16 copy of soc.py could not be written correctly")
    if not python2_can_read(python2, path):
        raise IOError("Python 2 cannot read the g16 copy of soc.py")
    return path


# ---------------------------------------------------------------------------
# The background run (started by the program itself; you never type this)
# ---------------------------------------------------------------------------
CURRENT = {"child": None, "stop": ""}


def on_stop_signal(signum, frame):
    CURRENT["stop"] = "stopped by a kill/terminate signal"
    child = CURRENT["child"]
    if child is not None and child.returncode is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)  # soc.py / soc_td and everything they started
        except OSError:
            pass


def child_environment(folder):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"   # no init.pyc: always read the current init.py
    env["PYTHONPATH"] = folder             # the sub-folder's own init.py is found first
    return env


def run_step(command, folder, log_handle):
    """Run one program inside the folder; returns its exit code (None if it could not start)."""
    try:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log_handle,
                                 stderr=subprocess.STDOUT, cwd=folder, env=child_environment(folder),
                                 start_new_session=True)
    except OSError as err:
        log_handle.write("could not start {0}: {1}\n".format(command[0], err).encode())
        return None
    CURRENT["child"] = child
    try:
        return child.wait()
    finally:
        CURRENT["child"] = None


def keep_old(path):
    if os.path.lexists(path):
        os.replace(path, path + ".old")


def not_written(folder, since):
    """The first file this run should have written but did not (None if all are fine)."""
    def fresh(name):
        when = mtime(os.path.join(folder, name))
        return when is not None and when >= since
    for name in RWFDUMP_FILES:
        if not fresh(name):
            return "Gaussian's rwfdump did not write {0} in this run".format(name)
        dumps = (read_text(os.path.join(folder, name)) or "").count("Dump of file")
        if dumps != 1:
            return "{0} holds {1} dumps instead of 1".format(name, dumps)
    for name in MOLSOC_FILES:
        if not fresh(name):
            return "MolSOC did not write {0} in this run".format(name)
    for name in MOLSOC_IF_PRESENT:
        if os.path.exists(os.path.join(folder, name)) and not fresh(name):
            return "MolSOC did not write {0} in this run".format(name)
    for name in SOC_PY_FILES:
        if not fresh(name):
            return "soc.py did not write {0} in this run".format(name)
    return None


def run_one(job, python2, soc_py, soc_td):
    """Run PySOC in one sub-folder. Returns (ok, message, seconds)."""
    folder = job.folder
    log_path = os.path.join(folder, JOB_LOG)
    started = time.time()
    try:
        # Results of an earlier run are kept as *.old (nothing is deleted).
        for name in (SOC_OUT, JOB_LOG) + RWFDUMP_FILES:
            keep_old(os.path.join(folder, name))
    except OSError as err:
        return False, "cannot prepare the folder ({0})".format(err.strerror or err), 0
    try:
        handle = open(log_path, "wb")
        since = os.stat(log_path).st_mtime   # the folder's own clock: files newer than this are new
    except (IOError, OSError) as err:
        return False, "cannot write {0} ({1})".format(JOB_LOG, err.strerror or err), 0
    with handle:
        handle.write("==== {0}  python2 {1}\n".format(stamp(), soc_py).encode())
        handle.flush()
        code = run_step([python2, soc_py], folder, handle)
        if CURRENT["stop"]:
            return False, "stopped", time.time() - started
        missing = not_written(folder, since)
        if missing:
            why = last_error(log_path)
            return False, "{0} (soc.py exit code {1}){2}".format(
                missing, code, ": " + why if why else ""), time.time() - started
        handle.write("==== {0}  {1}\n".format(stamp(), soc_td).encode())
        handle.flush()
        code = run_step([soc_td], folder, handle)
        if CURRENT["stop"]:
            return False, "stopped", time.time() - started
    complete, detail = soc_out_state(folder, job.expected)
    took = time.time() - started
    if complete and (mtime(os.path.join(folder, SOC_OUT)) or 0) < since:
        complete, detail = False, "soc_td did not write soc_out.dat in this run"
    if complete:
        return True, "{0} sum_soc lines".format(detail), took
    why = last_error(log_path)
    return False, "{0} (soc_td exit code {1}){2}".format(detail, code, ": " + why if why else ""), took


def worker(soc_dir, python2, soc_py, soc_td, names):
    me = os.getpid()
    lock = os.path.join(soc_dir, LOCK_NAME)
    stop_file = os.path.join(soc_dir, STOP_NAME)
    signal.signal(signal.SIGTERM, on_stop_signal)
    signal.signal(signal.SIGINT, on_stop_signal)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)  # logging out must not stop the run

    jobs = [Job(soc_dir, name) for name in names]
    for job in jobs:
        job.expected = expected_lines(read_text(job.init) or "")
    ok, failed, skipped, interrupted = [], [], [], []
    fails_in_a_row = 0
    total = len(jobs)
    width = len(str(total))
    log("RUN STARTED  (process {0})  {1} folder(s), one after another, in:".format(me, total))
    log("    " + soc_dir)
    log("    soc.py: " + soc_py)
    stop_reason = ""
    try:
        for number, job in enumerate(jobs, 1):
            tag = "[{0:>{2}}/{1}] {3}".format(number, total, width, job.sub_name)
            if CURRENT["stop"]:
                stop_reason = CURRENT["stop"]
                break
            if os.path.exists(stop_file):
                stop_reason = "the STOP file was found, so no new folder was started"
                try:
                    os.remove(stop_file)
                except OSError:
                    pass
                break
            space = free_gb(soc_dir)
            if space is not None and space < MIN_FREE_GB:
                stop_reason = "only {0:.1f} GB disk space is free".format(space)
                break
            if log_state(os.path.join(job.folder, QM_LOG)) != "normal" or \
                    not os.path.isfile(os.path.join(job.folder, QM_RWF)):
                log(tag + "  FAILED  (gaussian.log / gaussian.rwf not ready)")
                failed.append(job)
                continue
            log(tag + "  running PySOC (soc.py, soc_td) ...")
            success, message, took = run_one(job, python2, soc_py, soc_td)
            if CURRENT["stop"] and not success:
                interrupted.append(job)
                log(tag + "  STOPPED while running (it will run again next time)")
                stop_reason = CURRENT["stop"]
                break
            if success:
                fails_in_a_row = 0
                ok.append(job)
                log(tag + "  OK  soc_out.dat written, {0}  ({1})".format(message, duration(took)))
            else:
                fails_in_a_row += 1
                failed.append(job)
                log(tag + "  FAILED  " + message)
                log("    details:  " + os.path.join(job.folder, JOB_LOG))
                if fails_in_a_row >= MAX_FAILS_IN_A_ROW:
                    stop_reason = "{0} folders failed one after another".format(fails_in_a_row)
                    break
    finally:
        if CURRENT["stop"] and not stop_reason:
            stop_reason = CURRENT["stop"]
        done_names = set(j.sub_name for j in ok + skipped + interrupted)
        failed_names = set(j.sub_name for j in failed)
        not_run = [j.sub_name for j in jobs
                   if j.sub_name not in done_names and j.sub_name not in failed_names]
        say("")
        if stop_reason:
            log("RUN STOPPED: " + stop_reason + ".")
        else:
            log("RUN FINISHED.")
        log("    soc_out.dat OK  : {0}".format(len(ok)))
        log("    FAILED          : {0}{1}".format(
            len(failed), "  (" + ", ".join(j.sub_name for j in failed) + ")" if failed else ""))
        if interrupted:
            log("    STOPPED midway  : {0}".format(", ".join(j.sub_name for j in interrupted)))
        if not_run:
            log("    not run         : {0}  ({1})".format(len(not_run), ", ".join(not_run)))
        if failed or not_run or interrupted:
            log("    Run the program again to do the failed / not-run ones; finished")
            log("    folders are skipped.")
        try:
            with open(lock) as handle:
                if handle.read().strip() == str(me):
                    os.remove(lock)
        except (IOError, OSError):
            pass
    return 0 if not failed and not stop_reason else 1


# ---------------------------------------------------------------------------
# Starting the background run
# ---------------------------------------------------------------------------
def start_background(soc_dir, python2, soc_py, soc_td, jobs):
    lock = os.path.join(soc_dir, LOCK_NAME)
    run_log = os.path.join(soc_dir, RUN_LOG)
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.close(handle)
    except OSError:
        warn("Another run on this soc_singlet started a moment ago. Nothing was started.")
        return 1
    names = [job.sub_name for job in jobs if job.status in (NEW, AGAIN)]
    try:
        with open(run_log, "a") as out:
            out.write("\n" + "=" * 70 + "\n")
        out = open(run_log, "a")
        child = subprocess.Popen(
            [sys.executable, os.path.realpath(__file__), "--worker", soc_dir, python2, soc_py,
             soc_td] + names,
            stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
            cwd=soc_dir, start_new_session=True, close_fds=True)
        out.close()
        with open(lock, "w") as handle:
            handle.write(str(child.pid))
    except Exception as err:
        try:
            os.remove(lock)
        except OSError:
            pass
        warn("Could not start the run: {0}".format(err))
        return 1
    time.sleep(1.0)
    if child.poll() is not None:
        # Already over: a quick run, or one that stopped at once. Show its report.
        text = read_text(run_log) or ""
        last = text.split("=" * 70)[-1].strip("\n")
        say("")
        say(LINE)
        if "RUN FINISHED" in last or "RUN STOPPED" in last:
            say("The run is already over (it took less than a second). Its report:")
            say("")
            for line in last.splitlines():
                say(line)
        else:
            warn("The run stopped straight away. Its messages are in:  " + run_log)
        say(LINE)
        return 0 if child.returncode == 0 else 1
    say("")
    say(LINE)
    say("STARTED in the background (process {0}): {1} folder(s), one after another.".format(
        child.pid, len(names)))
    say("You can now close this terminal or log out; the run keeps going.")
    say("")
    say("  Watch progress (Ctrl+C stops only the watching):")
    say("      tail -f " + shlex.quote(run_log))
    say("  Stop after the folder that is running now:")
    say("      touch " + shlex.quote(os.path.join(soc_dir, STOP_NAME)))
    say("  Stop at once (also stops the PySOC step that is running):")
    say("      kill {0}".format(child.pid))
    say("  Check later how far it is: run this program again.")
    say(LINE)
    return 0


def show_running(soc_dir, pid, subs, links):
    jobs = plan(soc_dir, subs, links)
    say("")
    say(LINE)
    say("A run is already going on this soc_singlet (process {0}).".format(pid))
    say("  soc_out.dat complete so far : {0} of {1}".format(count(jobs, DONE), len(jobs)))
    say("  Watch progress  :  tail -f " + shlex.quote(os.path.join(soc_dir, RUN_LOG)))
    say("  Stop after the current folder:  touch " + shlex.quote(os.path.join(soc_dir, STOP_NAME)))
    say("  Stop at once    :  kill {0}".format(pid))
    say("Nothing new was started.")
    say(LINE)


def main():
    if sys.argv[1:2] == ["--worker"]:
        return worker(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6:])
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        say(__doc__)
        return 0

    say(LINE)
    say("  RUN init.py  (PySOC in every sub-folder of soc_singlet, one after another)")
    say("  In each sub-folder:  python2 soc.py ; soc_td   ->  soc_out.dat")
    say("      soc_singlet/g1.com, then soc_singlet/g2.com, ...")
    say("  Only soc_singlet is run. soc_triplet is not touched.")
    say("  Press Ctrl+C at any time to stop (before the run starts).")
    say(LINE)
    if sys.argv[1:]:
        say("  Note: the program asks for the paths itself; the words typed after")
        say("  the command are ignored.")

    python2, version = find_python2()
    if python2 is None:
        say("")
        warn("Python 2 was not found in this terminal (tried: {0}).".format(", ".join(PYTHON2_NAMES)))
        warn("PySOC's soc.py is written in Python 2, so it cannot run without it.")
        warn("Install it (Ubuntu 18.04: sudo apt install python-minimal) and run this again.")
        return 1
    enable_tab_completion()

    soc_dir, subs, links = ask_for_soc_singlet()
    pid = running_pid(soc_dir, LOCK_NAME, "run_init")
    if pid is not None:
        show_running(soc_dir, pid, subs, links)
        return 0
    remove_stale_lock(soc_dir)
    submit = running_pid(soc_dir, SUBMIT_LOCK, "submit_soc_singlet")
    if submit is not None:
        say("")
        warn("Gaussian jobs are still running on this soc_singlet (submit_soc_singlet.py,")
        warn("process {0}). Start run_init.py after they have finished.".format(submit))
        warn("Nothing has been started.")
        return 1

    pysoc = ask_for_pysoc()
    if not python2_can_read(python2, pysoc.soc_py):
        warn("{0} (Python {1}) cannot read {2}.".format(python2, version, pysoc.soc_py))
        warn("Nothing has been started.")
        return 1

    jobs = plan(soc_dir, subs, links)
    for molsoc in sorted(set(job.molsoc for job in jobs if job.molsoc)):
        missing = missing_libraries(molsoc)
        if missing:
            for job in jobs:
                if job.molsoc == molsoc and job.status != BLOCKED:
                    job.status = BLOCKED
                    job.reason = "MolSOC needs libraries this computer lacks: " + ", ".join(missing)
    blocked = [job for job in jobs if job.status == BLOCKED]
    if blocked:
        show_summary(soc_dir, jobs, python2, version, pysoc, pysoc.soc_py, None)
        say("")
        warn("PySOC cannot be run in these sub-folder(s):")
        for job in blocked:
            say("      {0}:  {1}".format(job.sub_name, job.reason))
        say("")
        say("  Nothing has been started (in any sub-folder).")
        say("  Please fix the item(s) above, then run the program again.")
        return 1

    try:
        soc_py, g16_text, rwfdump = choose_soc_py(jobs, pysoc)
    except CannotRun:
        warn("Nothing has been started.")
        return 1
    except Declined:
        say("  Nothing has been started.")
        return 0
    soc_py_shown = soc_py or os.path.join(soc_dir, G16_COPY_FOLDER, "soc.py") + "  (g16 copy)"
    if rwfdump:
        needs = shebang_program(rwfdump)
        if not program_available(needs):
            say("")
            warn("Gaussian's rwfdump needs '{0}', which is not installed.".format(
                os.path.basename(needs)))
            if os.path.basename(needs) in ("csh", "tcsh"):
                warn("Install it with:  sudo apt install csh")
            warn("Nothing has been started.")
            return 1
        if not os.access(rwfdump, os.X_OK):
            warn("Gaussian's rwfdump is not executable: " + rwfdump)
            warn("Nothing has been started.")
            return 1
    if not (shutil.which("g16") or shutil.which("g09") or os.environ.get("GAUSS_EXEDIR")):
        say("")
        warn("Gaussian is not set up in this terminal (no g16 command, no GAUSS_EXEDIR).")
        warn("rwfdump (used by PySOC) normally needs it. Best: open the terminal where")
        warn("g16 works and start this program there.")
        if not ask_yes_no("  Start anyway?"):
            say("  Nothing has been started.")
            return 0

    show_summary(soc_dir, jobs, python2, version, pysoc, soc_py_shown, rwfdump)
    ready = count(jobs, NEW) + count(jobs, AGAIN)
    if ready == 0:
        say("")
        if count(jobs, DONE) == len(jobs):
            say("  All {0} sub-folders already have a complete soc_out.dat.".format(len(jobs)))
        else:
            say("  No sub-folder is ready to run (see NOT READY above).")
        say("  Nothing needs to be run.")
        return 0
    if count(jobs, NOT_READY):
        say("")
        say("  {0} sub-folder(s) are NOT READY (listed above) and will be skipped.".format(
            count(jobs, NOT_READY)))
        if not ask_yes_no("  Run PySOC in the {0} ready sub-folder(s) anyway?".format(ready)):
            say("  Nothing has been started.")
            return 0

    stop_file = os.path.join(soc_dir, STOP_NAME)
    if os.path.exists(stop_file):
        say("")
        say("  A STOP file from an earlier run is in soc_singlet. It must be removed,")
        say("  or the run would stop at once.")
        if not ask_yes_no("  Remove it?"):
            say("  Nothing has been started.")
            return 0
        try:
            os.remove(stop_file)
        except OSError as err:
            warn("Could not remove it ({0}). Nothing has been started.".format(err.strerror or err))
            return 1

    say("")
    if not ask_yes_no("Start PySOC in {0} sub-folder(s) now, one after another, in the background?"
                      .format(ready)):
        say("  Cancelled. Nothing has been started.")
        return 0
    if g16_text is not None:
        try:
            soc_py = write_g16_copy(soc_dir, g16_text, python2)
            say("  g16 copy of soc.py written:  " + soc_py)
        except (IOError, OSError) as err:
            warn("Could not write the g16 copy of soc.py: {0}".format(err))
            warn("Nothing has been started.")
            return 1
    return start_background(soc_dir, python2, soc_py, pysoc.soc_td, jobs)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, UserQuit):
        say("")
        say("")
        say("Stopped by you. Nothing has been started.")
        sys.exit(130)
