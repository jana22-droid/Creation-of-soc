#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replace paths in init.py  (in every sub-folder of soc_singlet)
==============================================================

The init.py files in soc_singlet still contain paths from another computer.
This program puts the paths of THIS computer into the init.py of every
sub-folder of soc_singlet (g1.com, g2.com, ... g41.com), one after another:

    g09root        = '<new path>'
    molsoc_path    = '<new path>'
    dir_para_basis = '<new path>'

Only these three values are changed. Every other line of init.py stays
exactly as it is, and no other file is touched (gaussian.com, g1.com,
gaussian.log ... and soc_triplet are left alone).

HOW TO RUN (Ubuntu terminal)
    python3 replace.py

The program asks two things:
    1. Where soc_singlet is. Type EITHER the path of soc_singlet itself
       (for example jana/pp/opt/b3lyp/scan/soc_singlet) OR the folder that
       contains it (for example jana/pp/opt/b3lyp/scan).
    2. Whether the new paths shown are right (they come from search.py on
       the lab computer). Answer n to type other paths.

SAFETY
    * Nothing is changed until you confirm the summary.
    * If any sub-folder has a problem (no init.py, a setting missing, no
      permission), nothing at all is changed and the problem is shown.
    * Each init.py is written in one step (never half-written), then read
      back and checked: the three values are the new ones and every other
      line is identical to before.
    * Running the program again is safe: init.py files that already have
      the new paths are skipped.
"""
from __future__ import print_function

import sys

# Stop early, with a clear message, if started with the old Python 2.
if sys.version_info[0] < 3:
    sys.stderr.write(
        "\nThis program needs Python 3. Please run it like this:\n\n"
        "    python3 replace.py\n\n")
    sys.exit(1)

import glob
import os
import re
import shlex
import shutil
import textwrap

# ---------------------------------------------------------------------------
# Settings: the new paths (from search.py on the lab computer)
# ---------------------------------------------------------------------------
NEW_PATHS = (
    ("g09root", "/home/vsrgroup3/softwares"),
    ("molsoc_path", "/home/vsrgroup3/softwares/pySOC/pysoc-master/molsoc/"
                    "molsoc_modified/molsoc0.1/bin/molsoc0.1.exe"),
    ("dir_para_basis", "/home/vsrgroup3/softwares/pySOC/pysoc-master/pysoc/"
                       "parameters/mio-1-1-fit"),
)
WHAT_IT_IS = {
    "g09root": "folder that contains the g16 (or g09) folder",
    "molsoc_path": "the modified MolSOC program",
    "dir_para_basis": "basis folder, only used for TD-DFTB",
}

INIT_NAME = "init.py"
TEMP_NAME = ".init.py.replace-tmp"   # written first, then renamed to init.py
SOC_FOLDER = "soc_singlet"           # the only folder that is changed
OTHER_SOC_FOLDER = "soc_triplet"     # never touched
ORIGINAL_FOLDERS = ("singlet", "triplet")
SUBFOLDER_EXTENSION = ".com"         # sub-folders are named g1.com, g2.com, ...
MAX_SEARCH_DEPTH = 10
MAX_INIT_SIZE = 1024 * 1024          # init.py is a few kB; anything over 1 MB is not it
PYSOC_SETTINGS = ("QM_code", "n_s")  # every PySOC init.py sets these

LINE = "=" * 70

# Status of each sub-folder before changing
UPDATE = "update"     # init.py has old paths -> will be changed
SAME = "same"         # init.py already has the new paths -> skipped
BLOCKED = "blocked"   # something is wrong -> nothing at all is changed


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
        say("  This is the '{0}' folder. Only soc_singlet is changed, so".format(name))
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
# Step 2: the new paths
# ---------------------------------------------------------------------------
def path_problems(name, value):
    """Reasons why a new path looks wrong on this computer (empty list = fine)."""
    if name == "g09root":
        if not os.path.isdir(value):
            return ["this folder does not exist on this computer"]
        if not any(os.path.isdir(os.path.join(value, v)) for v in ("g16", "g09")):
            return ["there is no g16 or g09 folder inside it"]
    elif name == "molsoc_path":
        if not os.path.isfile(value):
            return ["this file does not exist on this computer"]
        if not os.access(value, os.X_OK):
            return ["this file is not executable (chmod +x it)"]
    elif name == "dir_para_basis":
        if not os.path.isdir(value):
            return ["this folder does not exist (it is only used for TD-DFTB)"]
    return []


def gaussian_inside(folder):
    found = [v for v in ("g16", "g09") if os.path.isdir(os.path.join(folder, v))]
    return ", ".join("{0}/{1}".format(folder.rstrip(os.sep), v) for v in found)


def show_paths(paths):
    for name, value in paths:
        say("    {0:<14} = {1}".format(name, quoted(value)))
        say("    {0:<14}   ({1})".format("", WHAT_IT_IS[name]))
        problems = path_problems(name, value)
        if problems:
            for problem in problems:
                warn("{0}: {1}".format(name, problem))
        elif name == "g09root":
            say("    {0:<14}   OK, found {1}".format("", gaussian_inside(value)))
        else:
            say("    {0:<14}   OK, exists on this computer".format(""))


def quoted(path):
    return "'" + path + "'"


def bad_characters(value):
    for character in ("'", '"', "\\", "\n", "\r", "\0"):
        if character in value:
            return character
    return None


def ask_new_value(name, current):
    while True:
        raw = ask("  New {0} (Enter = keep {1}): ".format(name, quoted(current))).strip()
        if not raw:
            return current
        words = readings_of(raw)
        value = os.path.abspath(words[0]) if words else ""
        if not value:
            continue
        bad = bad_characters(value)
        if bad:
            warn("A path with the character {0!r} cannot be used here.".format(bad))
            continue
        return value


def ask_for_paths():
    """STEP 2. Returns the list of (name, new value) to write."""
    say("")
    say(LINE)
    say("STEP 2 of 2:  The new paths for init.py")
    say(LINE)
    paths = list(NEW_PATHS)
    while True:
        show_paths(paths)
        if ask_yes_no("  Are these the right new paths?"):
            break
        say("  Type each new path, or press Enter to keep the one shown.")
        paths = [(name, ask_new_value(name, value)) for name, value in paths]
        say("")
    serious = [(name, problem) for name, value in paths if name != "dir_para_basis"
               for problem in path_problems(name, value)]
    if serious:
        say("")
        warn("Some paths do not look right on this computer (see above).")
        warn("PySOC will not work with them.")
        if not ask_yes_no("  Write them into init.py anyway?"):
            raise UserQuit()
    return paths


# ---------------------------------------------------------------------------
# Changing one init.py (planned first, written only after you confirm)
# ---------------------------------------------------------------------------
ASSIGNMENT = r"^(\s*{0}\s*=\s*)(['\"])(.*?)\2(.*)$"


def split_lines(text):
    """Lines with their own line ending kept (so CRLF files stay CRLF)."""
    lines = []
    for line in text.splitlines(True):
        body = line.rstrip("\r\n")
        lines.append((body, line[len(body):]))
    return lines


def plan_changes(text, paths):
    """
    Return (new_text, old_values, problem). old_values maps name -> list of
    the values found now. problem is a sentence when the file cannot be changed.
    """
    for name in PYSOC_SETTINGS:
        if not re.search(r"^\s*" + name + r"\s*=", text, re.MULTILINE):
            return None, {}, "this is not a PySOC init.py ({0} is not set in it)".format(name)
    lines = split_lines(text)
    old_values = dict((name, []) for name, _ in paths)
    new_lines = []
    for body, ending in lines:
        for name, value in paths:
            match = re.match(ASSIGNMENT.format(name), body)
            if match:
                prefix, quote, old, rest = match.groups()
                old_values[name].append(old)
                body = prefix + quote + value + quote + rest
                break
        new_lines.append(body + ending)
    missing = [name for name, _ in paths if not old_values[name]]
    if missing:
        return None, old_values, "{0} is not set in this init.py".format(" and ".join(missing))
    return "".join(new_lines), old_values, ""


def changed_only_settings(old_text, new_text, paths):
    """True when every line that differs is one of the setting lines, and nothing else moved."""
    old_lines, new_lines = split_lines(old_text), split_lines(new_text)
    if len(old_lines) != len(new_lines):
        return False
    for (old_body, old_end), (new_body, new_end) in zip(old_lines, new_lines):
        if old_end != new_end:
            return False
        if old_body == new_body:
            continue
        if not any(re.match(ASSIGNMENT.format(name), old_body) and
                   re.match(ASSIGNMENT.format(name), new_body) for name, _ in paths):
            return False
    return True


def values_now(text, paths):
    """name -> list of values in the text (every assignment line)."""
    values = {}
    for name, _ in paths:
        values[name] = [m.group(3) for m in
                        (re.match(ASSIGNMENT.format(name), body) for body, _ in split_lines(text))
                        if m]
    return values


def decode(data):
    return data.decode("utf-8", "surrogateescape")


def encode(text):
    return text.encode("utf-8", "surrogateescape")


class Job(object):
    def __init__(self, soc_dir, sub_name):
        self.sub_name = sub_name
        self.folder = os.path.join(soc_dir, sub_name)
        self.path = os.path.join(self.folder, INIT_NAME)
        self.label = os.path.join(os.path.basename(soc_dir), sub_name, INIT_NAME)
        self.status = UPDATE
        self.reason = ""
        self.old_data = None
        self.new_data = None
        self.old_values = {}


def plan_job(job, paths):
    if os.path.islink(job.folder):
        return BLOCKED, "the sub-folder is a link, not a normal folder"
    if not os.path.lexists(job.path):
        return BLOCKED, "there is no init.py in it (run copy_init.py first)"
    if os.path.islink(job.path) or not os.path.isfile(job.path):
        return BLOCKED, "init.py in it is not a normal file"
    try:
        if os.path.getsize(job.path) > MAX_INIT_SIZE:
            return BLOCKED, "init.py in it is far too big to be the PySOC init.py"
        with open(job.path, "rb") as handle:
            job.old_data = handle.read()
    except (IOError, OSError) as err:
        return BLOCKED, "cannot read init.py ({0})".format(err.strerror or err)
    old_text = decode(job.old_data)
    new_text, job.old_values, problem = plan_changes(old_text, paths)
    if problem:
        return BLOCKED, problem
    if not changed_only_settings(old_text, new_text, paths):
        return BLOCKED, "internal check failed: more than the three settings would change"
    job.new_data = encode(new_text)
    if job.new_data == job.old_data:
        return SAME, ""
    if not os.access(job.path, os.W_OK):
        return BLOCKED, "init.py is read-only"
    if not os.access(job.folder, os.W_OK | os.X_OK):
        return BLOCKED, "no permission to write in this sub-folder"
    if os.path.lexists(os.path.join(job.folder, TEMP_NAME)):
        leftover = os.path.join(job.folder, TEMP_NAME)
        if os.path.islink(leftover) or not os.path.isfile(leftover):
            return BLOCKED, "something called {0} is in the way".format(TEMP_NAME)
    return UPDATE, ""


def make_plan(soc_dir, subs, links, paths):
    jobs = []
    for name in natural_sorted(subs + links):
        job = Job(soc_dir, name)
        if name in links:
            job.status, job.reason = BLOCKED, "the sub-folder is a link, not a normal folder"
        else:
            job.status, job.reason = plan_job(job, paths)
        jobs.append(job)
    return jobs


def show_summary(soc_dir, jobs, paths):
    count = lambda status: sum(1 for job in jobs if job.status == status)
    say("")
    say(LINE)
    say("SUMMARY - please check. Nothing has been changed yet.")
    say(LINE)
    say("  soc_singlet   :  " + soc_dir)
    say("  Sub-folders   :  {0}  ({1}{2})".format(
        len(jobs), jobs[0].sub_name, " ... " + jobs[-1].sub_name if len(jobs) > 1 else ""))
    say("  File changed  :  init.py in each sub-folder (nothing else)")
    say("  Will be changed                         :  {0}".format(count(UPDATE)))
    if count(SAME):
        say("  Already have the new paths (skipped)    :  {0}".format(count(SAME)))
    if count(BLOCKED):
        say("  Cannot be changed                       :  {0}".format(count(BLOCKED)))
    updating = [job for job in jobs if job.status == UPDATE]
    if updating:
        say("")
        say("  Changes in init.py:")
        for name, value in paths:
            olds = []
            for job in updating:
                for old in job.old_values.get(name, []):
                    if old not in olds:
                        olds.append(old)
            for old in olds:
                if old == value:
                    continue
                say("    {0:<14}  {1}".format(name, quoted(old)))
                say("    {0:<14}  -> {1}".format("", quoted(value)))
        twice = [name for name, _ in paths
                 if any(len(job.old_values.get(name, [])) > 1 for job in updating)]
        if twice:
            say("    (" + ", ".join(twice) + " is set on more than one line; every such line is changed)")
    say("  soc_triplet   :  not touched")
    say(LINE)


def write_job(job):
    """Write the new init.py in one step: temporary file first, then rename."""
    temp = os.path.join(job.folder, TEMP_NAME)
    try:
        with open(temp, "wb") as handle:
            handle.write(job.new_data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            shutil.copymode(job.path, temp)
        except OSError:
            pass
        os.replace(temp, job.path)
    except Exception:
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except OSError:
            pass
        raise
    with open(job.path, "rb") as handle:
        if handle.read() != job.new_data:
            raise IOError("init.py read back is not what was written")


def final_check(soc_dir, jobs, paths):
    say("")
    say("Final check: reading every init.py in soc_singlet again ...")
    say("")
    say(LINE)
    good, bad = [], []
    for job in jobs:
        try:
            with open(job.path, "rb") as handle:
                text = decode(handle.read())
            values = values_now(text, paths)
            ok = all(values[name] and all(v == value for v in values[name]) for name, value in paths)
            if ok and job.old_data is not None:
                ok = changed_only_settings(decode(job.old_data), text, paths)
        except (IOError, OSError):
            ok = False
        (good if ok else bad).append(job)
    if not bad:
        say("SOC_SINGLET:  all {0} init.py file(s) have the new paths;".format(len(good)))
        say("              every other line is unchanged.")
    else:
        say("SOC_SINGLET:  PROBLEM - {0} init.py file(s) do not have the new paths:".format(len(bad)))
        for job in bad:
            say("      " + job.label + ("   (" + job.reason + ")" if job.reason else ""))
        say("              The other {0} are fine.".format(len(good)))
    for name, value in paths:
        say("              {0:<14} = {1}".format(name, quoted(value)))
    say("              Folder:  " + soc_dir)
    say("SOC_TRIPLET:  not touched.")
    say("")
    if not bad:
        say("DONE. Everything is in place.")
    else:
        say("Please fix the problem(s) above and run the program again:")
        say("init.py files that already have the new paths will be skipped.")
    say(LINE)
    return 0 if not bad else 1


def main():
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        say(__doc__)
        return 0

    say(LINE)
    say("  REPLACE PATHS IN init.py")
    say("  Puts this computer's paths into init.py in every sub-folder of soc_singlet:")
    say("      g09root, molsoc_path, dir_para_basis  (nothing else is changed)")
    say("  Only soc_singlet is done; soc_triplet is not touched.")
    say("  Press Ctrl+C at any time to stop.")
    say(LINE)
    if sys.argv[1:]:
        say("  Note: the program asks for the paths itself; the words typed after")
        say("  the command are ignored.")
    enable_tab_completion()

    soc_dir, subs, links = ask_for_soc_singlet()
    paths = ask_for_paths()
    jobs = make_plan(soc_dir, subs, links, paths)
    show_summary(soc_dir, jobs, paths)

    blocked = [job for job in jobs if job.status == BLOCKED]
    if blocked:
        say("")
        warn("init.py cannot be changed here:")
        for job in blocked:
            say("      {0}:  {1}".format(job.sub_name, job.reason))
        say("")
        say("  Nothing has been changed (in any sub-folder).")
        say("  Please fix the item(s) above, then run the program again.")
        return 1

    to_change = [job for job in jobs if job.status == UPDATE]
    if not to_change:
        say("")
        say("  All init.py files already have these paths. Nothing needs to be changed.")
        return final_check(soc_dir, jobs, paths)

    say("")
    if not ask_yes_no("Change init.py in {0} sub-folder(s) now?".format(len(to_change))):
        say("  Cancelled. Nothing has been changed.")
        return 0

    say("")
    say("Changing init.py ...")
    width = len(str(len(to_change)))
    for number, job in enumerate(to_change, 1):
        counter = "[{0:>{2}}/{1}]".format(number, len(to_change), width)
        try:
            write_job(job)
            say("  {0} OK      {1}".format(counter, job.label))
        except Exception as err:
            job.reason = str(getattr(err, "strerror", None) or err)
            say("  {0} FAILED  {1}  ({2})".format(counter, job.label, job.reason))
    return final_check(soc_dir, jobs, paths)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, UserQuit):
        say("")
        say("")
        say("Stopped by you. Nothing more has been changed. Files already changed")
        say("have the new paths; running the program again skips them.")
        sys.exit(130)
