#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copy init.py  (into every sub-folder of soc_singlet)
====================================================

Copies the PySOC settings file init.py into every sub-folder of
soc_singlet (the sub-folders made by creation_of_soc.py):

    init.py   -->   .../soc_singlet/g1.com/init.py
    init.py   -->   .../soc_singlet/g2.com/init.py
    ...             one copy in every sub-folder (g1.com ... g41.com)

Only soc_singlet is done. soc_triplet is not touched.

HOW TO RUN (Ubuntu terminal)
    python3 copy_init.py

At the start the program asks two things:
    1. Where soc_singlet is. Type EITHER the path of soc_singlet itself
       (for example jana/pp/opt/b3lyp/scan/soc_singlet) OR the path of the
       folder that contains it (for example jana/pp/opt/b3lyp/scan). The
       program tells the two apart by itself. If soc_singlet is deeper
       inside, the sub-folders are searched.
    2. Which init.py to copy. If init.py is in the same folder as this
       program, in the folder you are in, or next to soc_singlet, it is
       found automatically and you only confirm it. Otherwise type its
       path (or the folder it is in).

Type paths the same way as in the terminal, for example:
    jana/pp/opt/b3lyp/scan          (from the folder you are in now)
    /home/jana/pp/opt/b3lyp/scan    (full path)
    ~/pp/opt/b3lyp/scan             (from your home folder)
The Tab key completes folder names, like in the terminal.

SAFETY
    * init.py and everything in soc_singlet are only read, never changed or
      moved. The only thing added is one init.py in each sub-folder.
    * Nothing is copied until you confirm the summary.
    * An init.py already in a sub-folder is never replaced without asking you.
    * If anything is in the way, nothing at all is copied and the problem is shown.
    * Every copy is read back and compared byte by byte with init.py.
    * Running the program again is safe: correct copies are skipped. If you
      edit init.py later, run the program again and answer y to replace the
      old copies.
"""
from __future__ import print_function

import sys

# Stop early, with a clear message, if started with the old Python 2.
if sys.version_info[0] < 3:
    sys.stderr.write(
        "\nThis program needs Python 3. Please run it like this:\n\n"
        "    python3 copy_init.py\n\n")
    sys.exit(1)

import glob
import os
import re
import shlex
import textwrap
import time

# ---------------------------------------------------------------------------
# Settings (normally nothing needs to be changed here)
# ---------------------------------------------------------------------------
INIT_NAME = "init.py"            # name of every copy (PySOC looks for this name)
SOC_FOLDER = "soc_singlet"       # the only folder that is done
OTHER_SOC_FOLDER = "soc_triplet"  # never touched
ORIGINAL_FOLDERS = ("singlet", "triplet")  # the folders the .com files came from
SUBFOLDER_EXTENSION = ".com"     # sub-folders are named g1.com, g2.com, ...
GAUSSIAN_INPUT = "gaussian.com"  # made by creation_of_gaussian_com.py (only checked)
MAX_SEARCH_DEPTH = 10            # how many levels deep to search
MAX_INIT_SIZE = 1024 * 1024      # init.py is a few kB; anything over 1 MB is not it
PYSOC_WORDS = ("QM_code", "qm_out", "molsoc_path")  # words every PySOC init.py has

LINE = "=" * 70

# Status of each sub-folder before copying
NEW = "new"              # no init.py there yet -> will be copied
SAME = "same"            # init.py there and identical -> skipped
DIFFERENT = "different"  # init.py there but different -> asks before replacing
BLOCKED = "blocked"      # something is in the way -> nothing at all is copied


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


def describe(path, data):
    """Size and time of last change, so the right version of a file is easy to spot."""
    size = "{0} bytes".format(len(data)) if data is not None else "cannot be read"
    try:
        changed = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
        return "{0}, last changed {1}".format(size, changed)
    except (OSError, ValueError, OverflowError):
        return size


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
        say("  This is the '{0}' folder. init.py goes only into soc_singlet,".format(name))
        say("  so soc_singlet is looked for in the folder above it:  " + parent)
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
    """STEP 1. Returns (soc_singlet path, sub-folder names, linked sub-folder names)."""
    say("")
    say(LINE)
    say("STEP 1 of 2:  Where is the 'soc_singlet' folder?")
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
# Step 2: find init.py and check that it is the PySOC init.py
# ---------------------------------------------------------------------------
class InitFile(object):
    def __init__(self, path, data):
        self.path = path
        self.data = data          # the exact bytes that will be copied
        self.info = describe(path, data)
        self.text = data.decode("utf-8", "replace")


def read_init(path):
    """Read a candidate init.py. Returns its bytes, or None after explaining why not."""
    if not os.path.isfile(path):
        warn("This is not a file:  " + path)
        return None
    try:
        size = os.path.getsize(path)
        if size == 0:
            warn("This file is empty:  " + path)
            return None
        if size > MAX_INIT_SIZE:
            warn("This file is far too big to be init.py ({0} bytes):  {1}".format(size, path))
            return None
        with open(path, "rb") as handle:
            return handle.read()
    except (IOError, OSError) as err:
        warn("Cannot read this file ({0}):  {1}".format(err.strerror or err, path))
        return None


def content_problems(path, data):
    """Reasons to doubt that this is the right init.py (empty list if it looks fine)."""
    problems = []
    text = data.decode("utf-8", "replace")
    missing = [word for word in PYSOC_WORDS if not re.search(r"\b" + word + r"\b", text)]
    if missing:
        problems.append("It does not look like the PySOC init.py ({0} not found in it)."
                        .format(", ".join(missing)))
    try:
        compile(data, path, "exec")  # only checks the syntax; nothing is run
    except SyntaxError as err:
        problems.append("Python reports a mistake in it at line {0}: {1}".format(
            err.lineno, err.msg))
    except Exception as err:
        problems.append("Python cannot read it ({0}).".format(err))
    return problems


def accept_init(path):
    """Read and check one init.py. Returns an InitFile, or None if not usable/refused."""
    data = read_init(path)
    if data is None:
        return None
    problems = content_problems(path, data)
    if problems:
        say("")
        warn("Please check this file:  " + path)
        for problem in problems:
            warn(problem)
        if not ask_yes_no("  Copy it anyway?"):
            return None
    init = InitFile(path, data)
    say("  OK, init.py to copy:  {0}  ({1})".format(path, init.info))
    if os.path.basename(path) != INIT_NAME:
        say("  Note: this file is called '{0}'. Every copy will be named '{1}',".format(
            os.path.basename(path), INIT_NAME))
        say("  because that is the name PySOC looks for.")
    return init


def init_candidates(soc_dir):
    """init.py files found automatically (outside soc_singlet), best first."""
    places = []
    try:
        places.append(os.path.dirname(os.path.realpath(__file__)))  # next to this program
    except NameError:
        pass
    here = current_folder()
    if here:
        places.append(here)                                          # where you are now
    places.append(os.path.dirname(soc_dir))                          # next to soc_singlet
    found, seen = [], set()
    for place in places:
        candidate = os.path.join(place, INIT_NAME)
        real = os.path.realpath(candidate)
        if real in seen or not os.path.isfile(candidate) or is_inside(candidate, soc_dir):
            continue
        seen.add(real)
        found.append(os.path.abspath(candidate))
    return found


def read_quietly(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(MAX_INIT_SIZE + 1)
    except (IOError, OSError):
        return None


def ask_for_init(soc_dir):
    """STEP 2. Returns an InitFile."""
    say("")
    say(LINE)
    say("STEP 2 of 2:  Which init.py should be copied?")
    say(LINE)

    candidates = init_candidates(soc_dir)
    # Files with exactly the same content count as one.
    distinct, contents = [], []
    for path in candidates:
        data = read_quietly(path)
        if data not in contents:
            contents.append(data)
            distinct.append(path)

    if len(distinct) == 1:
        data = contents[0]
        say("  Found:  {0}  ({1})".format(distinct[0], describe(distinct[0], data)))
        if ask_yes_no("  Copy this init.py into every sub-folder of soc_singlet?"):
            init = accept_init(distinct[0])
            if init is not None:
                return init
    elif len(distinct) > 1:
        labels = ["{0}  ({1})".format(path, describe(path, data))
                  for path, data in zip(distinct, contents)]
        choice = ask_choice("  Different init.py files were found. Which one should be copied?",
                            labels + ["Another one - let me type its path"])
        if choice < len(distinct):
            init = accept_init(distinct[choice])
            if init is not None:
                return init
    else:
        say("  No init.py was found next to this program, in the folder you are in,")
        say("  or next to soc_singlet.")

    say("")
    say("  Type the path of init.py, or of the folder it is in")
    say("  (for example:  ~/Downloads/init.py   or   ~/Downloads ).")
    while True:
        raw = ask("Path to init.py: ")
        if not raw.strip():
            warn("Please type a path (or press Ctrl+C to stop).")
            continue
        path = existing_path_from(raw, "File or folder")
        if path is None:
            continue
        if os.path.isdir(path):
            folder = path
            path = os.path.join(folder, INIT_NAME)
            if not os.path.isfile(path):
                warn("There is no '{0}' in this folder:  {1}".format(INIT_NAME, folder))
                try:
                    similar = natural_sorted(n for n in os.listdir(folder)
                                             if n.lower().endswith("init.py")
                                             and os.path.isfile(os.path.join(folder, n)))
                except OSError:
                    similar = []
                if similar:
                    say("  Files with a similar name in it:  " + ", ".join(similar))
                    say("  To use one of them, type its full path.")
                continue
        init = accept_init(path)
        if init is not None:
            return init


def init_notes(init):
    """Things worth knowing about init.py's settings (they do not stop the copying)."""
    notes = []

    def setting(name):
        value = None
        for line in init.text.splitlines():
            match = re.match(r"\s*" + name + r"\s*=\s*(['\"])(.*?)\1", line)
            if match:
                value = match.group(2)  # the last uncommented line wins, as in Python
        return value

    qm_code = setting("QM_code")
    if qm_code is not None and qm_code != "gauss_tddft":
        notes.append("QM_code is '{0}'; for Gaussian TD-DFT it should be 'gauss_tddft'."
                     .format(qm_code))
    g09root = setting("g09root")
    if g09root is not None and not os.path.isdir(g09root):
        notes.append("g09root = '{0}' does not exist on this computer.".format(g09root))
    molsoc = setting("molsoc_path")
    if molsoc is not None and not os.path.isfile(molsoc):
        notes.append("molsoc_path = '{0}' does not exist on this computer.".format(molsoc))
    return notes


# ---------------------------------------------------------------------------
# Planning, copying and checking
# ---------------------------------------------------------------------------
class Job(object):
    """One sub-folder of soc_singlet: where init.py goes."""

    def __init__(self, soc_dir, sub_name):
        self.sub_name = sub_name
        self.folder = os.path.join(soc_dir, sub_name)
        self.dst = os.path.join(self.folder, INIT_NAME)
        self.label = os.path.join(os.path.basename(soc_dir), sub_name, INIT_NAME)
        self.status = NEW
        self.reason = ""
        self.copy = False     # will be copied in this run


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def check_job(job, init):
    """Decide what has to happen in one sub-folder. Nothing is changed here."""
    status = NEW
    if os.path.lexists(job.dst):
        if os.path.islink(job.dst):
            return BLOCKED, "{0} is a link, not a normal file".format(job.label)
        if not os.path.isfile(job.dst):
            return BLOCKED, "a FOLDER called {0} is in the way: {1}".format(INIT_NAME, job.dst)
        try:
            status = SAME if read_bytes(job.dst) == init.data else DIFFERENT
        except (IOError, OSError) as err:
            return BLOCKED, "cannot read {0} ({1})".format(job.label, err.strerror or err)
        if status == DIFFERENT and not os.access(job.dst, os.W_OK):
            return BLOCKED, "the existing {0} is read-only".format(job.label)
    if status == NEW and not os.access(job.folder, os.W_OK | os.X_OK):
        return BLOCKED, "no permission to write in the folder " + job.folder
    return status, ""


def make_plan(soc_dir, subs, links, init):
    jobs = []
    for name in natural_sorted(subs + links):
        job = Job(soc_dir, name)
        if name in links:
            job.status = BLOCKED
            job.reason = "the sub-folder {0} is a link, not a normal folder".format(name)
        else:
            job.status, job.reason = check_job(job, init)
        jobs.append(job)
    return jobs


def show_summary(soc_dir, jobs, init, notes):
    count = lambda status: sum(1 for job in jobs if job.status == status)
    no_gaussian = [job.sub_name for job in jobs
                   if not os.path.isfile(os.path.join(job.folder, GAUSSIAN_INPUT))]
    say("")
    say(LINE)
    say("SUMMARY - please check. Nothing has been copied yet.")
    say(LINE)
    say("  init.py       :  {0}  ({1})".format(init.path, init.info))
    say("  soc_singlet   :  " + soc_dir)
    say("  Sub-folders   :  {0}  ({1}{2})".format(
        len(jobs), jobs[0].sub_name, " ... " + jobs[-1].sub_name if len(jobs) > 1 else ""))
    say("  Layout        :  " + jobs[0].label
        + ("  ...  " + jobs[-1].label if len(jobs) > 1 else ""))
    say("  New, will be copied                       :  {0}".format(count(NEW)))
    if count(SAME):
        say("  Already there and identical (skipped)     :  {0}".format(count(SAME)))
    if count(DIFFERENT):
        say("  Already there but DIFFERENT from init.py  :  {0}".format(count(DIFFERENT)))
    if count(BLOCKED):
        say("  Cannot be copied                          :  {0}".format(count(BLOCKED)))
    say("  soc_triplet   :  not touched")
    if no_gaussian:
        say("")
        say("  Note: {0} sub-folder(s) have no {1} yet (run creation_of_gaussian_com.py".format(
            len(no_gaussian), GAUSSIAN_INPUT))
        say("  for them). init.py is copied there anyway:")
        show_wrapped(no_gaussian)
    if notes:
        say("")
        say("  Note about the settings inside init.py (copying is not affected,")
        say("  but PySOC will need these fixed before it can run):")
        for note in notes:
            say("    - " + note)
        say("  You can edit init.py later and run this program again; it will")
        say("  offer to replace the old copies.")
    say(LINE)


def copy_files(jobs, init):
    to_copy = [job for job in jobs if job.copy]
    say("")
    say("Copying init.py ...")
    width = len(str(len(to_copy)))
    for number, job in enumerate(to_copy, 1):
        counter = "[{0:>{2}}/{1}]".format(number, len(to_copy), width)
        try:
            with open(job.dst, "wb") as handle:
                handle.write(init.data)
            if read_bytes(job.dst) != init.data:
                raise IOError("the copy is not identical to init.py")
            say("  {0} OK      {1}".format(counter, job.label))
        except Exception as err:
            job.reason = str(getattr(err, "strerror", None) or err)
            say("  {0} FAILED  {1}  ({2})".format(counter, job.label, job.reason))


def final_check(soc_dir, jobs, init):
    """Look at every sub-folder again and confirm init.py is there and identical."""
    say("")
    say("Final check: comparing every init.py in soc_singlet with the original ...")
    say("")
    say(LINE)
    good, bad, kept = [], [], []
    for job in jobs:
        if job.status == DIFFERENT and not job.copy:
            kept.append(job)  # the user chose to keep the old version
            continue
        try:
            ok = (not os.path.islink(job.dst) and os.path.isfile(job.dst)
                  and read_bytes(job.dst) == init.data)
        except (IOError, OSError):
            ok = False
        (good if ok else bad).append(job)

    if not bad:
        say("SOC_SINGLET:  {0} of {1} sub-folder(s) have init.py, identical to".format(
            len(good), len(jobs)))
        say("              " + init.path)
    else:
        say("SOC_SINGLET:  PROBLEM - init.py is missing or not identical in {0} sub-folder(s):"
            .format(len(bad)))
        for job in bad:
            say("      " + job.label + ("   (" + job.reason + ")" if job.reason else ""))
        say("              The other {0} sub-folder(s) are fine.".format(len(good)))
    if kept:
        say("              Left unchanged on your request (different from init.py): {0}"
            .format(len(kept)))
        for job in kept:
            say("                  " + job.label)
    say("              Folder:  " + soc_dir)
    say("SOC_TRIPLET:  not touched.")
    say("")
    if not bad:
        say("DONE. Everything is in place.")
    else:
        say("Please fix the problem(s) above and run the program again:")
        say("sub-folders that are already fine will be skipped.")
    say(LINE)
    return 0 if not bad else 1


def main():
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        say(__doc__)
        return 0

    say(LINE)
    say("  COPY init.py")
    say("  Copies init.py into every sub-folder of soc_singlet:")
    say("      init.py  ->  soc_singlet/g1.com/init.py,  soc_singlet/g2.com/init.py, ...")
    say("  Only soc_singlet is done; soc_triplet is not touched.")
    say("  Press Ctrl+C at any time to stop.")
    say(LINE)
    if sys.argv[1:]:
        say("  Note: the program asks for the paths itself; the words typed after")
        say("  the command are ignored.")
    enable_tab_completion()

    soc_dir, subs, links = ask_for_soc_singlet()
    init = ask_for_init(soc_dir)
    jobs = make_plan(soc_dir, subs, links, init)
    show_summary(soc_dir, jobs, init, init_notes(init))

    blocked = [job for job in jobs if job.status == BLOCKED]
    if blocked:
        say("")
        warn("init.py cannot be copied here:")
        for job in blocked:
            say("      {0}:  {1}".format(job.sub_name, job.reason))
        say("")
        say("  Nothing has been copied (into any sub-folder).")
        say("  Please move or rename the item(s) above, then run the program again.")
        return 1

    for job in jobs:
        job.copy = job.status == NEW

    different = [job for job in jobs if job.status == DIFFERENT]
    if different:
        say("")
        say("  These sub-folder(s) already have an init.py that is DIFFERENT")
        say("  from the one you chose:")
        show_wrapped([job.sub_name for job in different])
        if ask_yes_no("  Replace them with the init.py you chose?"):
            for job in different:
                job.copy = True
        else:
            say("  OK, they will be left unchanged.")

    to_copy = sum(1 for job in jobs if job.copy)
    if to_copy == 0:
        say("")
        say("  Nothing needs to be copied.")
        return final_check(soc_dir, jobs, init)

    say("")
    if not ask_yes_no("Start copying init.py into {0} sub-folder(s) now?".format(to_copy)):
        say("  Cancelled. Nothing has been copied.")
        return 0

    copy_files(jobs, init)
    return final_check(soc_dir, jobs, init)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, UserQuit):
        say("")
        say("")
        say("Stopped by you. If copying had already started, simply run the")
        say("program again: sub-folders that already have the right init.py are skipped.")
        sys.exit(130)
