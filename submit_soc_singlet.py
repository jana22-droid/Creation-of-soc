#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Submit soc_singlet  (run g16 in every sub-folder, one after another)
====================================================================

Runs Gaussian 16 on the gaussian.com file in every sub-folder of
soc_singlet, one job after another, in the order g1.com, g2.com, ... g41.com:

    cd soc_singlet/g1.com  ;  g16 < gaussian.com > gaussian.log
    cd soc_singlet/g2.com  ;  g16 < gaussian.com > gaussian.log
    ...

Each job runs INSIDE its own sub-folder, so gaussian.log, gaussian.rwf and
gaussian.chk end up next to gaussian.com and init.py, where PySOC needs them.
Only soc_singlet is run. soc_triplet is not touched.

HOW TO RUN (Ubuntu terminal, the same terminal where g16 normally works)
    python3 submit_soc_singlet.py

The program asks one thing: where soc_singlet is. Type EITHER the path of
soc_singlet itself (for example jana/pp/opt/b3lyp/scan/soc_singlet) OR the
folder that contains it (for example jana/pp/opt/b3lyp/scan). It shows a
summary, and after you type y the jobs start IN THE BACKGROUND: you can
close the terminal or log out of SSH and they keep running.

WHILE IT RUNS
    Watch progress :  tail -f .../soc_singlet/submit_soc_singlet.log
                      (Ctrl+C only stops the watching, not the jobs)
    Stop after the job that is running now :  touch .../soc_singlet/STOP
    Stop at once   :  the exact kill command is printed when the run starts
    Check later    :  run this program again; it shows how far it is

SAFETY
    * gaussian.com and every other file in soc_singlet are only read.
    * Nothing starts until you confirm the summary.
    * Jobs whose gaussian.log already ends with "Normal termination" are
      skipped, so running the program again is safe.
    * A job that failed or was stopped is run again; its old gaussian.log is
      kept as gaussian.log.old.
    * If anything is wrong (a gaussian.com missing, a job already running in
      a sub-folder, a run already going), nothing at all is started.
    * Two runs on the same soc_singlet can never go at the same time.
    * If 3 jobs fail one after another, the run stops (something is wrong
      with all of them, for example g16 itself), instead of failing 41 times.
"""
from __future__ import print_function

import sys

# Stop early, with a clear message, if started with the old Python 2.
if sys.version_info[0] < 3:
    sys.stderr.write(
        "\nThis program needs Python 3. Please run it like this:\n\n"
        "    python3 submit_soc_singlet.py\n\n")
    sys.exit(1)

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
GAUSSIAN = "g16"                 # the command that runs Gaussian
INPUT_NAME = "gaussian.com"      # input in every sub-folder (creation_of_gaussian_com.py)
OUTPUT_NAME = "gaussian.log"     # output written next to it
RWF_NAME = "gaussian.rwf"        # needed later by PySOC (only checked, from %rwf=)
RUN_LOG = "submit_soc_singlet.log"   # progress of the whole run, inside soc_singlet
LOCK_NAME = ".submit_soc_singlet.lock"
STOP_NAME = "STOP"               # touch soc_singlet/STOP to stop after the current job
MAX_FAILS_IN_A_ROW = 3           # stop the run after this many failures in a row
MIN_FREE_GB = 2.0                # do not start a job with less free disk space than this
WARN_FREE_GB = 20.0              # mention it in the summary below this
SOC_FOLDER = "soc_singlet"       # the only folder that is run
OTHER_SOC_FOLDER = "soc_triplet"  # never touched
ORIGINAL_FOLDERS = ("singlet", "triplet")
SUBFOLDER_EXTENSION = ".com"     # sub-folders are named g1.com, g2.com, ...
MAX_SEARCH_DEPTH = 10            # how many levels deep to search for soc_singlet

LINE = "=" * 70

# Status of each sub-folder before starting
NEW = "new"              # never run -> will run
AGAIN = "again"          # gaussian.log there but not finished -> will run again
DONE = "done"            # gaussian.log ends with Normal termination -> skipped
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
# Gaussian: what state a sub-folder is in
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


def log_state(path):
    """
    None          no gaussian.log
    'normal'      the last line says Normal termination  (job finished well)
    'error'       Gaussian stopped with Error termination
    'incomplete'  the job stopped before the end (killed, crashed or still running)
    """
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


def error_line(path):
    """The 'Error termination ...' line of a gaussian.log, to show why a job failed."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            handle.seek(max(0, size - 16384))
            tail = handle.read().decode("utf-8", "replace")
    except (IOError, OSError):
        return ""
    found = [line.strip() for line in tail.splitlines() if "Error termination" in line]
    return found[-1] if found else ""


def rwf_name(input_path):
    """File named in the %rwf= line of gaussian.com (None if there is no such line)."""
    try:
        with open(input_path, "rb") as handle:
            text = handle.read(65536).decode("utf-8", "replace")
    except (IOError, OSError):
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            break  # the % lines come before the route line
        match = re.match(r"%rwf\s*=\s*(\S+)", stripped, re.IGNORECASE)
        if match:
            return match.group(1).split(",")[0]
    return None


def is_gaussian_process(name):
    return name == GAUSSIAN or name.startswith(GAUSSIAN) or bool(re.match(r"^l\d+\.exe$", name))


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


def free_gb(folder):
    try:
        info = os.statvfs(folder)
        return info.f_bavail * info.f_frsize / (1024.0 ** 3)
    except (OSError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# A run already going? (lock file inside soc_singlet)
# ---------------------------------------------------------------------------
def running_pid(soc_dir):
    """PID of a run that is going on this soc_singlet right now, or None."""
    lock = os.path.join(soc_dir, LOCK_NAME)
    try:
        with open(lock) as handle:
            pid = int(handle.read().strip() or "0")
    except (IOError, OSError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        with open("/proc/{0}/cmdline".format(pid), "rb") as handle:
            command = handle.read()
    except (IOError, OSError):
        return None  # that process is gone: the lock is left over
    if b"submit_soc_singlet" not in command:
        return None  # the number now belongs to another program
    return pid


def remove_stale_lock(soc_dir):
    lock = os.path.join(soc_dir, LOCK_NAME)
    if os.path.lexists(lock) and running_pid(soc_dir) is None:
        try:
            os.remove(lock)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------
class Job(object):
    """One sub-folder of soc_singlet: gaussian.com in, gaussian.log out."""

    def __init__(self, soc_dir, sub_name):
        self.sub_name = sub_name
        self.folder = os.path.join(soc_dir, sub_name)
        self.input = os.path.join(self.folder, INPUT_NAME)
        self.output = os.path.join(self.folder, OUTPUT_NAME)
        self.status = NEW
        self.reason = ""


def plan(soc_dir, subs, links):
    busy = gaussian_processes()
    jobs = []
    for name in natural_sorted(subs + links):
        job = Job(soc_dir, name)
        jobs.append(job)
        if name in links:
            job.status, job.reason = BLOCKED, "the sub-folder is a link, not a normal folder"
            continue
        if not os.path.isfile(job.input):
            job.status, job.reason = BLOCKED, "no {0} in it (run creation_of_gaussian_com.py)".format(
                INPUT_NAME)
            continue
        if not os.access(job.input, os.R_OK):
            job.status, job.reason = BLOCKED, "cannot read its " + INPUT_NAME
            continue
        if os.path.realpath(job.folder) in busy:
            pids = ", ".join("{0} ({1})".format(p, n) for p, n in busy[os.path.realpath(job.folder)])
            job.status, job.reason = BLOCKED, "a Gaussian job is running in it right now: " + pids
            continue
        if os.path.lexists(job.output) and not os.path.isfile(job.output):
            job.status, job.reason = BLOCKED, "something that is not a file is called " + OUTPUT_NAME
            continue
        state = log_state(job.output)
        if state == "normal":
            job.status = DONE
        elif state is not None:
            job.status = AGAIN
            job.reason = {"error": "Error termination last time",
                          "incomplete": "stopped before the end last time"}[state]
        if job.status != DONE and not os.access(job.folder, os.W_OK | os.X_OK):
            job.status, job.reason = BLOCKED, "no permission to write in this sub-folder"
    return jobs


def count(jobs, status):
    return sum(1 for job in jobs if job.status == status)


def show_summary(soc_dir, jobs, g16_path):
    to_run = [job for job in jobs if job.status in (NEW, AGAIN)]
    no_rwf = [job.sub_name for job in jobs
              if job.status in (NEW, AGAIN) and rwf_name(job.input) is None]
    elsewhere = [(folder, procs) for folder, procs in gaussian_processes().items()
                 if not is_inside(folder, soc_dir)]
    space = free_gb(soc_dir)
    say("")
    say(LINE)
    say("SUMMARY - please check. Nothing has been started yet.")
    say(LINE)
    say("  Gaussian      :  " + g16_path)
    say("  soc_singlet   :  " + soc_dir)
    say("  Sub-folders   :  {0}  ({1}{2})".format(
        len(jobs), jobs[0].sub_name, " ... " + jobs[-1].sub_name if len(jobs) > 1 else ""))
    say("  Each job      :  cd soc_singlet/<sub-folder>  then  {0} < {1} > {2}".format(
        GAUSSIAN, INPUT_NAME, OUTPUT_NAME))
    say("                   (only {0} is run; g1.com, g2.com ... are never used)".format(INPUT_NAME))
    say("  Order         :  one job at a time; the next starts only after the")
    say("                   previous one has completely finished")
    say("  Will run (never run before)                 :  {0}".format(count(jobs, NEW)))
    if count(jobs, AGAIN):
        say("  Will run AGAIN (did not finish last time)   :  {0}".format(count(jobs, AGAIN)))
        for job in jobs:
            if job.status == AGAIN:
                say("      {0}  ({1}; old log kept as {2}.old)".format(
                    job.sub_name, job.reason, OUTPUT_NAME))
    if count(jobs, DONE):
        say("  Already finished, skipped                   :  {0}".format(count(jobs, DONE)))
    if count(jobs, BLOCKED):
        say("  Cannot be run                               :  {0}".format(count(jobs, BLOCKED)))
    if to_run:
        say("  First job     :  " + to_run[0].sub_name + "/" + INPUT_NAME)
    if space is not None:
        say("  Free disk     :  {0:.1f} GB".format(space))
        if space < WARN_FREE_GB:
            say("  [!] Little free disk space. Each job writes a {0} file; the run".format(RWF_NAME))
            say("      stops before a job if less than {0:.0f} GB is free.".format(MIN_FREE_GB))
    if no_rwf:
        say("")
        say("  Note: {0} has no %rwf= line in these sub-folder(s), so no {1}".format(
            INPUT_NAME, RWF_NAME))
        say("  will be kept for PySOC:")
        show_wrapped(no_rwf)
    if elsewhere:
        say("")
        say("  Note: Gaussian is already running elsewhere on this computer; it will")
        say("  share the CPU cores with this run:")
        for folder, procs in elsewhere:
            say("      {0}  ({1})".format(folder, ", ".join(n for _, n in procs)))
    say(LINE)


# ---------------------------------------------------------------------------
# The background run (started by the program itself; you never type this)
# ---------------------------------------------------------------------------
# What the background run is doing right now. A stop signal (kill) only sets
# "stop" and passes the signal on to the running g16; the run then stops cleanly
# once g16 has exited, and never starts another job.
CURRENT = {"child": None, "stop": ""}


def on_stop_signal(signum, frame):
    CURRENT["stop"] = "stopped by a kill/terminate signal"
    child = CURRENT["child"]
    if child is not None and child.returncode is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)  # g16 and all its l*.exe programs
        except OSError:
            pass  # g16 has already ended


def wait_until_folder_is_free(folder):
    """After g16 has exited, make sure no Gaussian program is still working in folder."""
    real = os.path.realpath(folder)
    waited = 0
    while real in gaussian_processes() and not CURRENT["stop"]:
        if waited == 0:
            log("    waiting: a Gaussian program is still working in this sub-folder ...")
        time.sleep(5)
        waited += 5
    if waited and not CURRENT["stop"]:
        log("    sub-folder is free again (waited {0}).".format(duration(waited)))


def run_one(job, g16_path):
    """Run g16 on gaussian.com inside the sub-folder. Returns (ok, message, seconds)."""
    state = log_state(job.output)
    if state is not None:
        try:
            os.replace(job.output, job.output + ".old")  # keep the unfinished log
        except OSError as err:
            return False, "cannot rename the old {0} ({1})".format(
                OUTPUT_NAME, err.strerror or err), 0
    started = time.time()
    try:
        source = open(job.input, "rb")
    except (IOError, OSError) as err:
        return False, "cannot read {0} ({1})".format(INPUT_NAME, err.strerror or err), 0
    try:
        try:
            output = open(job.output, "wb")
        except (IOError, OSError) as err:
            return False, "cannot write {0} ({1})".format(OUTPUT_NAME, err.strerror or err), 0
        try:
            try:
                # Own process group, so a stop reaches g16 and every l*.exe it starts.
                child = subprocess.Popen([g16_path], stdin=source, stdout=output,
                                         stderr=subprocess.STDOUT, cwd=job.folder,
                                         start_new_session=True)
            except OSError as err:
                return False, "could not start {0} ({1})".format(
                    g16_path, err.strerror or err), 0
            CURRENT["child"] = child
            code = child.wait()  # waits until g16 has completely finished
        finally:
            CURRENT["child"] = None
            output.close()
    finally:
        source.close()
    took = time.time() - started
    wait_until_folder_is_free(job.folder)
    state = log_state(job.output)
    if state == "normal":
        return True, "", took
    if state == "error":
        why = error_line(job.output) or "Error termination"
    else:
        why = "gaussian.log does not end with Normal termination"
    return False, "{0} (g16 exit code {1})".format(why, code), took


def worker(soc_dir, g16_path, names):
    me = os.getpid()
    lock = os.path.join(soc_dir, LOCK_NAME)
    stop_file = os.path.join(soc_dir, STOP_NAME)

    signal.signal(signal.SIGTERM, on_stop_signal)
    signal.signal(signal.SIGINT, on_stop_signal)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)  # logging out must not stop the run

    jobs = [Job(soc_dir, name) for name in names]
    ok, failed, skipped, warnings, interrupted = [], [], [], [], []
    fails_in_a_row = 0
    total = len(jobs)
    width = len(str(total))
    log("RUN STARTED  (process {0})  {1} job(s), one after another, in:".format(me, total))
    log("    " + soc_dir)
    stop_reason = ""
    try:
        for number, job in enumerate(jobs, 1):
            tag = "[{0:>{2}}/{1}] {3}".format(number, total, width, job.sub_name)
            if CURRENT["stop"]:
                stop_reason = CURRENT["stop"]
                break
            if os.path.exists(stop_file):
                stop_reason = "the STOP file was found, so no new job was started"
                try:
                    os.remove(stop_file)
                except OSError:
                    pass
                break
            if log_state(job.output) == "normal":
                log(tag + "  already finished, skipped")
                skipped.append(job)
                continue
            if not os.path.isfile(job.input):
                log(tag + "  FAILED  ({0} is missing)".format(INPUT_NAME))
                failed.append(job)
                continue
            space = free_gb(soc_dir)
            if space is not None and space < MIN_FREE_GB:
                stop_reason = "only {0:.1f} GB disk space is free".format(space)
                break
            log(tag + "  running  {0} < {1}  ...".format(GAUSSIAN, INPUT_NAME))
            success, message, took = run_one(job, g16_path)
            if CURRENT["stop"] and not success:
                interrupted.append(job)
                log(tag + "  STOPPED while running (it will run again next time)")
                stop_reason = CURRENT["stop"]
                break
            if success:
                fails_in_a_row = 0
                ok.append(job)
                rwf = rwf_name(job.input)
                note = ""
                if rwf and not os.path.isfile(os.path.join(job.folder, rwf)):
                    note = "   [!] but {0} was not found".format(rwf)
                    warnings.append(job.sub_name)
                log(tag + "  OK  Normal termination  ({0}){1}".format(duration(took), note))
            else:
                fails_in_a_row += 1
                failed.append(job)
                log(tag + "  FAILED  " + message)
                if fails_in_a_row >= MAX_FAILS_IN_A_ROW:
                    stop_reason = "{0} jobs failed one after another".format(fails_in_a_row)
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
        log("    finished OK now : {0}".format(len(ok)))
        if skipped:
            log("    already done    : {0}".format(len(skipped)))
        log("    FAILED          : {0}{1}".format(
            len(failed), "  (" + ", ".join(j.sub_name for j in failed) + ")" if failed else ""))
        if interrupted:
            log("    STOPPED midway  : {0}".format(", ".join(j.sub_name for j in interrupted)))
        if not_run:
            log("    not run         : {0}  ({1})".format(len(not_run), ", ".join(not_run)))
        if warnings:
            log("    finished but no {0}: {1}".format(RWF_NAME, ", ".join(warnings)))
        if failed or not_run or interrupted:
            log("    Run the program again to do the failed / not-run ones; finished")
            log("    jobs are skipped.")
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
def start_background(soc_dir, g16_path, jobs):
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
            [sys.executable, os.path.realpath(__file__), "--worker", soc_dir, g16_path] + names,
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
        warn("The run stopped straight away. Its messages are in:  " + run_log)
        return 1
    stop_file = os.path.join(soc_dir, STOP_NAME)
    say("")
    say(LINE)
    say("STARTED in the background (process {0}): {1} job(s), one after another.".format(
        child.pid, len(names)))
    say("You can now close this terminal or log out; the jobs keep running.")
    say("")
    say("  Watch progress (Ctrl+C stops only the watching):")
    say("      tail -f " + shlex.quote(run_log))
    say("  Stop after the job that is running now:")
    say("      touch " + shlex.quote(stop_file))
    say("  Stop at once (also stops the g16 job that is running):")
    say("      kill {0}".format(child.pid))
    say("  Check later how far it is: run this program again.")
    say(LINE)
    return 0


def show_running(soc_dir, pid, subs, links):
    jobs = plan(soc_dir, subs, links)
    say("")
    say(LINE)
    say("A run is already going on this soc_singlet (process {0}).".format(pid))
    say("  Finished so far : {0} of {1}".format(count(jobs, DONE), len(jobs)))
    busy = gaussian_processes()
    for job in jobs:
        if os.path.realpath(job.folder) in busy:
            say("  Running now     : " + job.sub_name)
    say("  Watch progress  :  tail -f " + shlex.quote(os.path.join(soc_dir, RUN_LOG)))
    say("  Stop after the current job:  touch "
        + shlex.quote(os.path.join(soc_dir, STOP_NAME)))
    say("  Stop at once    :  kill {0}".format(pid))
    say("Nothing new was started.")
    say(LINE)


def main():
    if sys.argv[1:2] == ["--worker"]:
        return worker(sys.argv[2], sys.argv[3], sys.argv[4:])
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        say(__doc__)
        return 0

    say(LINE)
    say("  SUBMIT soc_singlet  (g16, one job after another)")
    say("  Runs  {0} < {1} > {2}  inside every sub-folder of soc_singlet:".format(
        GAUSSIAN, INPUT_NAME, OUTPUT_NAME))
    say("      soc_singlet/g1.com/{0}, then soc_singlet/g2.com/{0}, ...".format(INPUT_NAME))
    say("  Only {0} is run (never g1.com, g2.com ...). soc_triplet is not touched.".format(
        INPUT_NAME))
    say("  Press Ctrl+C at any time to stop (before the run starts).")
    say(LINE)
    if sys.argv[1:]:
        say("  Note: the program asks for the path itself; the words typed after")
        say("  the command are ignored.")

    g16_path = shutil.which(GAUSSIAN)
    if g16_path is None:
        say("")
        warn("'{0}' was not found in this terminal, so nothing can be run.".format(GAUSSIAN))
        warn("Start this program from the terminal where '{0}' normally works".format(GAUSSIAN))
        warn("(check with:  which {0} ).".format(GAUSSIAN))
        return 1
    g16_path = os.path.abspath(g16_path)
    enable_tab_completion()

    soc_dir, subs, links = ask_for_soc_singlet()
    pid = running_pid(soc_dir)
    if pid is not None:
        show_running(soc_dir, pid, subs, links)
        return 0
    remove_stale_lock(soc_dir)

    jobs = plan(soc_dir, subs, links)
    show_summary(soc_dir, jobs, g16_path)

    blocked = [job for job in jobs if job.status == BLOCKED]
    if blocked:
        say("")
        warn("These sub-folder(s) cannot be run:")
        for job in blocked:
            say("      {0}:  {1}".format(job.sub_name, job.reason))
        say("")
        say("  Nothing has been started (no job at all).")
        say("  Please fix the item(s) above, then run the program again.")
        return 1

    to_run = count(jobs, NEW) + count(jobs, AGAIN)
    if to_run == 0:
        say("")
        say("  All {0} jobs have already finished with Normal termination.".format(len(jobs)))
        say("  Nothing needs to be run.")
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
    if not ask_yes_no("Start {0} job(s) now, one after another, in the background?".format(to_run)):
        say("  Cancelled. Nothing has been started.")
        return 0
    return start_background(soc_dir, g16_path, jobs)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, UserQuit):
        say("")
        say("")
        say("Stopped by you. Nothing has been started.")
        sys.exit(130)
