#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Creation of gaussian.com  (for soc_singlet and soc_triplet)
===========================================================

Goes through the folders made by creation_of_soc.py:

    soc_singlet/g1.com/g1.com,  soc_singlet/g2.com/g2.com,  ...
    soc_triplet/g1.com/g1.com,  soc_triplet/g2.com/g2.com,  ...

In every sub-folder it opens the .com file (g1.com, g2.com, ...), replaces
its first lines (the % lines and the # route line) with the lines in
NEW_HEADER below, and saves the result as a NEW file called gaussian.com
in that same sub-folder:

    soc_singlet/g1.com/g1.com   -->   soc_singlet/g1.com/gaussian.com

Everything after the route line (blank line, title, charge and
multiplicity, coordinates, connectivity, ...) is kept exactly as it is.
The original g1.com is never changed. soc_singlet is done first, then
soc_triplet.

HOW TO RUN (Ubuntu terminal)
    python3 creation_of_gaussian_com.py

The program asks one thing: where soc_singlet / soc_triplet are. Type the
path of the folder that CONTAINS them (for example jana/pp/opt/b3lyp/scan)
or the path of soc_singlet or soc_triplet itself. Both are found
automatically. Type paths as in the terminal; Tab completes folder names.

SAFETY
    * The original g*.com files are only read, never changed.
    * Nothing is written until you confirm the summary.
    * An existing gaussian.com is never replaced without asking you.
    * If any file looks wrong, nothing at all is written and the problem is shown.
    * Every gaussian.com is read back and checked after writing.
    * Running the program again is safe: correct gaussian.com files are skipped.
"""
from __future__ import print_function

import sys

# Stop early, with a clear message, if started with the old Python 2.
if sys.version_info[0] < 3:
    sys.stderr.write(
        "\nThis program needs Python 3. Please run it like this:\n\n"
        "    python3 creation_of_gaussian_com.py\n\n")
    sys.exit(1)

import glob
import os
import re
import shlex
import textwrap

# ---------------------------------------------------------------------------
# THE NEW FIRST LINES OF EVERY gaussian.com  (exactly as in your screenshot)
# To change one, edit the text between the quotes. Keep the % lines first,
# then the # route line ("10f 6d" is the rest of the route line).
# ---------------------------------------------------------------------------
NEW_HEADER = [
    "%rwf=gaussian.rwf",
    "%nprocshared=6",
    "%mem=3GB",
    "%chk=gaussian.chk",
    "# td=(50-50,nstates=4) b3lyp/6-311g(d,p) nosymm geom=connectivity gfinput",
    "10f 6d",
]

# ---------------------------------------------------------------------------
# Other settings (normally nothing needs to be changed here)
# ---------------------------------------------------------------------------
OUTPUT_NAME = "gaussian.com"                 # new file made in every sub-folder
SOC_FOLDERS = ("soc_singlet", "soc_triplet")  # folders to look for, in this order
FILE_EXTENSION = ".com"
MAX_SEARCH_DEPTH = 10                        # how many levels deep to search
ENCODING = "latin-1"                         # reads/writes every byte unchanged

LINE = "=" * 70

# Status of each sub-folder before writing
NEW = "new"              # no gaussian.com yet -> will be written
SAME = "same"            # gaussian.com already correct -> skipped
DIFFERENT = "different"  # gaussian.com exists but differs -> asks before replacing
BLOCKED = "blocked"      # something is wrong -> nothing at all is written


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
        return "(unknown)"


def show_wrapped(items, indent="      "):
    for row in textwrap.wrap(", ".join(items), width=64,
                             break_long_words=False, break_on_hyphens=False):
        say(indent + row)


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
            if os.path.isdir(full) and full not in suggestions:
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


def existing_folder_from(raw):
    """Turn typed text into an existing folder, or None (after explaining why)."""
    found, guess, suggestions = find_path(raw)
    if found is not None:
        if os.path.isdir(found):
            return found
        warn("This is a file, not a folder:  " + found)
        return None
    warn("Folder not found:  " + guess)
    picked = pick_suggestion(suggestions)
    if picked is None:
        warn("Please check the spelling and type the path again.")
    return picked


# ---------------------------------------------------------------------------
# Reading a Gaussian input file
# ---------------------------------------------------------------------------
def read_text(path):
    with open(path, "r", encoding=ENCODING, newline="") as handle:
        return handle.read()


def split_lines(text):
    """Split into lines, each keeping its own line ending."""
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def split_input(text):
    """
    Split a Gaussian input into (old_first_lines, rest, problem).
    old_first_lines = the % lines and the # route line(s).
    rest = everything after them, starting with the blank line after the route.
    """
    lines = split_lines(text)
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1  # empty lines at the very top
    start = i
    while i < len(lines) and lines[i].lstrip()[:1] in ("%", "!"):
        i += 1  # % lines (and ! comment lines)
    if i >= len(lines) or not lines[i].lstrip().startswith("#"):
        return None, None, "no route line (a line starting with #) was found after the % lines"
    while i < len(lines) and lines[i].strip():
        i += 1  # the route line (it may go on over several lines)
    if i >= len(lines):
        return None, None, "there is no blank line after the route line"
    return lines[start:i], lines[i:], None


def looks_like_charge_mult(line):
    """True for lines like '0 1', '-1 2' or '0 1 0 1 0 1' (whole numbers in pairs)."""
    tokens = line.replace(",", " ").split()
    return (bool(tokens) and len(tokens) % 2 == 0
            and all(re.match(r"^[+-]?[0-9]+$", token) for token in tokens))


def is_connectivity(block):
    """Connectivity lines start with the atom numbers 1, 2, 3, ..."""
    return all(line.split()[0] == str(number) for number, line in enumerate(block, 1))


def check_molecule(rest):
    """
    Make sure the rest looks like a Gaussian input: title, then charge and
    multiplicity, then coordinates. Returns (charge_mult, has_connectivity, problem).
    """
    blocks, current = [], []
    for line in rest:
        if line.strip():
            current.append(line.strip())
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    if blocks and len(blocks[0]) > 1 and looks_like_charge_mult(blocks[0][0]):
        return None, None, "the title line is missing (it must come between the route line and the charge/multiplicity line)"
    if len(blocks) < 2:
        return None, None, "no title and molecule (charge/multiplicity + coordinates) after the route line"
    if not looks_like_charge_mult(blocks[1][0]):
        return None, None, "the line after the title is not 'charge multiplicity': " + blocks[1][0]
    tokens = blocks[1][0].replace(",", " ").split()
    if len(blocks[1]) < 2:
        return None, None, "no coordinates after the charge/multiplicity line"
    has_connectivity = any(is_connectivity(block) for block in blocks[2:])
    return " ".join(tokens), has_connectivity, None


def header_problem():
    """Check NEW_HEADER (in case it was edited). Returns a message or None."""
    if not NEW_HEADER:
        return "NEW_HEADER is empty."
    route_seen = False
    for line in NEW_HEADER:
        try:
            line.encode("ascii")
        except UnicodeEncodeError:
            return "Use only plain keyboard characters in NEW_HEADER: " + line
        if not line.strip() or "\n" in line or "\r" in line:
            return "NEW_HEADER must not contain empty lines."
        if line.lstrip().startswith("#"):
            route_seen = True
        elif not route_seen and not line.lstrip().startswith("%"):
            return "In NEW_HEADER the lines before the route line must start with %: " + line
    if not route_seen:
        return "NEW_HEADER needs a route line starting with #."
    return None


# ---------------------------------------------------------------------------
# Finding soc_singlet and soc_triplet
# ---------------------------------------------------------------------------
class SocFolder(object):
    """soc_singlet or soc_triplet and the work to do in it."""

    def __init__(self, name, path):
        self.name = name   # "soc_singlet" or "soc_triplet"
        self.path = path   # .../scan/soc_singlet
        self.jobs = []
        self.ignored = 0


class Job(object):
    """One sub-folder, e.g. soc_singlet/g1.com: read g1.com, write gaussian.com."""

    def __init__(self, soc, sub_name, src_name):
        self.folder = os.path.join(soc.path, sub_name)
        self.src = os.path.join(self.folder, src_name)
        self.dst = os.path.join(self.folder, OUTPUT_NAME)
        base = os.path.basename(soc.path)
        self.src_label = os.path.join(base, sub_name, src_name)   # soc_singlet/g1.com/g1.com
        self.label = os.path.join(base, sub_name, OUTPUT_NAME)    # soc_singlet/g1.com/gaussian.com
        self.sub_name = sub_name
        self.status = NEW
        self.reason = ""
        self.original = None      # text of g1.com as it was read
        self.new_text = None      # text that gaussian.com gets
        self.old_header = []
        self.charge_mult = None
        self.has_connectivity = None
        self.write = False


def soc_of(name):
    """'soc_singlet' or 'soc_triplet' if the folder name is one of them, else None."""
    for soc in SOC_FOLDERS:
        if name.lower() == soc.lower():
            return soc
    return None


def search_for(top, soc):
    """Look for folders named soc (e.g. 'soc_triplet') anywhere below top."""
    found = []
    top_depth = top.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, _ in os.walk(top):
        depth = dirpath.rstrip(os.sep).count(os.sep) - top_depth
        keep = []
        for name in dirnames:
            if soc_of(name) == soc:
                found.append(os.path.join(dirpath, name))
            elif (soc_of(name) is None and not name.startswith(".")
                  and depth < MAX_SEARCH_DEPTH):
                keep.append(name)  # soc folders are not searched inside
        dirnames[:] = keep
    return natural_sorted(found)


def locate(folder, names, soc):
    """Find one soc folder inside folder (names = its contents), or None."""
    direct = natural_sorted(
        os.path.join(folder, name) for name in names
        if soc_of(name) == soc and os.path.isdir(os.path.join(folder, name)))
    if len(direct) == 1:
        return direct[0]
    if len(direct) > 1:
        return direct[ask_choice(
            "  More than one '{0}' folder is here. Which one?".format(soc), direct)]

    say("  No '{0}' folder directly inside, searching the sub-folders ...".format(soc))
    found = search_for(folder, soc)
    if not found:
        say("  No '{0}' folder found.".format(soc))
        return None
    if len(found) == 1:
        say("  Found:  " + found[0])
        if ask_yes_no("  Use this as the '{0}' folder?".format(soc)):
            return found[0]
        return None
    choice = ask_choice(
        "  Several '{0}' folders were found. Which one?".format(soc),
        found + ["None of these (skip {0})".format(soc)])
    return found[choice] if choice < len(found) else None


def prepare(job):
    """Read g1.com and work out what gaussian.com must contain. Nothing is written."""
    if os.path.basename(job.src) == OUTPUT_NAME:
        return BLOCKED, "this original file is itself called {0}".format(OUTPUT_NAME)
    try:
        job.original = read_text(job.src)
    except (IOError, OSError) as err:
        return BLOCKED, "cannot read this file ({0})".format(err.strerror or err)
    old_header, rest, problem = split_input(job.original)
    if problem:
        return BLOCKED, problem
    job.charge_mult, job.has_connectivity, problem = check_molecule(rest)
    if problem:
        return BLOCKED, problem
    job.old_header = [line.rstrip("\r\n") for line in old_header]
    newline = "\r\n" if "\r\n" in job.original else "\n"
    job.new_text = newline.join(NEW_HEADER) + newline + "".join(rest)

    status = NEW
    if os.path.lexists(job.dst):
        if os.path.islink(job.dst):
            return BLOCKED, "{0} is a link, not a normal file".format(job.label)
        if not os.path.isfile(job.dst):
            return BLOCKED, "a FOLDER called {0} is in the way: {1}".format(job.label, job.dst)
        try:
            status = SAME if read_text(job.dst) == job.new_text else DIFFERENT
        except (IOError, OSError) as err:
            return BLOCKED, "cannot read {0} ({1})".format(job.label, err.strerror or err)
    if status != SAME and not os.access(job.folder, os.W_OK | os.X_OK):
        return BLOCKED, "no permission to write in the folder " + job.folder
    return status, ""


def collect_jobs(soc):
    """One job for every gN.com sub-folder of the soc folder."""
    try:
        names = os.listdir(soc.path)
    except OSError as err:
        warn("Cannot open this folder ({0}):  {1}".format(err.strerror or err, soc.path))
        return
    extension = FILE_EXTENSION.lower()
    for name in natural_sorted(names):
        sub = os.path.join(soc.path, name)
        if name.startswith(".") or not os.path.isdir(sub):
            soc.ignored += 1  # files and hidden folders are not used
            continue
        named_like_file = name.lower().endswith(extension) and len(name) > len(extension)
        src_name = name if named_like_file else name + FILE_EXTENSION  # g1.com/g1.com or g1/g1.com
        if not named_like_file and not os.path.isfile(os.path.join(sub, src_name)):
            soc.ignored += 1  # some other folder
            continue
        job = Job(soc, name, src_name)
        if os.path.islink(sub):
            job.status, job.reason = BLOCKED, "the sub-folder {0} is a link, not a normal folder".format(name)
        elif not os.path.isfile(job.src):
            job.status, job.reason = BLOCKED, "this file is missing (sub-folder {0} has no {1} inside)".format(
                name, src_name)
        else:
            job.status, job.reason = prepare(job)
        soc.jobs.append(job)


def find_soc_folders(folder):
    """Find soc_singlet and soc_triplet (in that order) in folder."""
    try:
        names = os.listdir(folder)
    except OSError as err:
        warn("Cannot open this folder ({0}):  {1}".format(err.strerror or err, folder))
        return []
    socs = []
    for soc_name in SOC_FOLDERS:
        say("")
        say("  --- {0} ---".format(soc_name.upper()))
        path = locate(folder, names, soc_name)
        if path is None:
            continue
        soc = SocFolder(soc_name, path)
        collect_jobs(soc)
        if not soc.jobs:
            warn("There are no g*.com sub-folders in:  " + path)
            continue
        say("  OK, {0} folder:  {1}".format(soc_name, path))
        say("  {0} sub-folder(s) found:".format(len(soc.jobs)))
        show_wrapped([job.sub_name for job in soc.jobs])
        if soc.ignored:
            say("  ({0} other item(s) in this folder are ignored.)".format(soc.ignored))
        socs.append(soc)
    return socs


def ask_for_soc_folders():
    say("")
    say(LINE)
    say("Where are the 'soc_singlet' and 'soc_triplet' folders?")
    say("  Type the path of the folder that CONTAINS them")
    say("  (for example:  jana/pp/opt/b3lyp/scan )  or the path of")
    say("  soc_singlet or soc_triplet itself. Both are found automatically.")
    say("  Tab completes folder names. You are now in:  " + current_folder())
    say(LINE)
    while True:
        raw = ask("Path to soc_singlet/soc_triplet: ")
        if not raw.strip():
            warn("Please type a path (or press Ctrl+C to stop).")
            continue
        folder = existing_folder_from(raw)
        if folder is None:
            continue
        if soc_of(os.path.basename(folder)):
            say("  This is the '{0}' folder itself, so both are looked for in the".format(
                os.path.basename(folder)))
            say("  folder above it:  " + os.path.dirname(folder))
            folder = os.path.dirname(folder)
        socs = find_soc_folders(folder)
        if not socs:
            say("")
            warn("No 'soc_singlet' or 'soc_triplet' folder with g*.com sub-folders was")
            warn("found in:  " + folder)
            warn("Please type another path.")
            continue
        found_names = [soc.name for soc in socs]
        for soc_name in SOC_FOLDERS:
            if soc_name not in found_names:
                say("")
                warn("No usable '{0}' folder was found, so only '{1}' will be done."
                     .format(soc_name, found_names[0]))
        return socs


# ---------------------------------------------------------------------------
# Summary, writing and checking (soc_singlet first, then soc_triplet)
# ---------------------------------------------------------------------------
def show_summary(socs):
    route = " ".join(NEW_HEADER).lower()
    say("")
    say(LINE)
    say("SUMMARY - please check. Nothing has been written yet.")
    say(LINE)
    say("  In every sub-folder a new file '{0}' is made from the .com file".format(OUTPUT_NAME))
    say("  there. Its first lines (the % lines and the # route line) become:")
    for line in NEW_HEADER:
        say("      " + line)
    say("  Everything below them (title, charge/multiplicity, coordinates, ...)")
    say("  stays exactly as it is. The original .com files are not changed.")
    for soc_name in SOC_FOLDERS:
        matching = [soc for soc in socs if soc.name == soc_name]
        say("")
        if not matching:
            say("  {0}:  skipped (no {1} folder with g*.com sub-folders)".format(
                soc_name.upper(), soc_name))
            continue
        soc = matching[0]
        jobs = soc.jobs
        usable = [job for job in jobs if job.status != BLOCKED]
        count = lambda status: sum(1 for job in jobs if job.status == status)
        say("  {0}".format(soc_name.upper()))
        say("    Folder        :  " + soc.path)
        say("    Sub-folders   :  {0}   (e.g. {1}  ->  {2})".format(
            len(jobs), jobs[0].src_label, jobs[0].label))
        if usable:
            say("    Lines that are replaced (as found in {0}):".format(usable[0].src_label))
            for line in usable[0].old_header:
                say("        " + line)
            versions = len(set(tuple(job.old_header) for job in usable))
            if versions > 1:
                say("    (In the other files these lines can differ a little, e.g. the")
                say("    %chk name; in every file they are replaced in the same way.)")
            values = {}
            for job in usable:
                values[job.charge_mult] = values.get(job.charge_mult, 0) + 1
            say("    Charge/multiplicity (kept as is):  " + ",  ".join(
                "'{0}' in {1} file(s)".format(value, number)
                for value, number in sorted(values.items())))
            if "50-50" in route:
                not_singlet = [job for job in usable if job.charge_mult.split()[1] != "1"]
                if not_singlet:
                    say("    Note: in Gaussian, TD=(50-50) only has an effect for closed-shell")
                    say("    molecules (multiplicity 1). {0} file(s) here have another".format(
                        len(not_singlet)))
                    say("    multiplicity. This program keeps that line exactly as it is.")
            if "connectivity" in route:
                no_connectivity = [job.sub_name for job in usable if not job.has_connectivity]
                if no_connectivity:
                    say("    Note: geom=connectivity needs a connectivity section after the")
                    say("    coordinates. It seems to be missing in {0} file(s):".format(
                        len(no_connectivity)))
                    show_wrapped(no_connectivity, indent="        ")
        say("    {0:<36}:  {1}".format("New {0} to write".format(OUTPUT_NAME), count(NEW)))
        if count(SAME):
            say("    {0:<36}:  {1}".format("Already there and correct (skip)", count(SAME)))
        if count(DIFFERENT):
            say("    {0:<36}:  {1}".format("Already there but DIFFERENT", count(DIFFERENT)))
        if count(BLOCKED):
            say("    {0:<36}:  {1}".format("Cannot be done", count(BLOCKED)))
    say("")
    say(LINE)


def write_file(path, text):
    """Write safely: first to a hidden temporary file, then rename it."""
    temporary = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".tmp")
    if os.path.lexists(temporary):
        os.remove(temporary)
    try:
        with open(temporary, "x", encoding=ENCODING, newline="") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.remove(temporary)


def write_all(soc):
    todo = [job for job in soc.jobs if job.write]
    if not todo:
        return
    say("")
    say("Writing {0} ...".format(soc.name))
    width = len(str(len(todo)))
    for number, job in enumerate(todo, 1):
        counter = "[{0:>{2}}/{1}]".format(number, len(todo), width)
        try:
            write_file(job.dst, job.new_text)
            if read_text(job.dst) != job.new_text:
                raise IOError("the written file is not as expected")
            say("  {0} OK      {1}".format(counter, job.label))
        except Exception as err:
            job.reason = str(getattr(err, "strerror", None) or err)
            say("  {0} FAILED  {1}  ({2})".format(counter, job.label, job.reason))


def final_check(socs):
    """Read every gaussian.com and every original again and compare."""
    say("")
    say("Final check: reading every {0} and every original again ...".format(OUTPUT_NAME))
    say("")
    say(LINE)
    all_ok = True
    for soc_name in SOC_FOLDERS:
        matching = [soc for soc in socs if soc.name == soc_name]
        if not matching:
            say("{0}:  skipped (no {1} folder with g*.com sub-folders)".format(
                soc_name.upper(), soc_name))
            continue
        soc = matching[0]
        good, bad, kept = [], [], []
        for job in soc.jobs:
            if job.status == DIFFERENT and not job.write:
                kept.append(job)  # the user chose to keep the old gaussian.com
                continue
            try:
                if read_text(job.src) != job.original:
                    job.reason = "the original {0} changed during the run".format(job.src_label)
                    ok = False
                else:
                    ok = (not os.path.islink(job.dst) and os.path.isfile(job.dst)
                          and read_text(job.dst) == job.new_text)
            except (IOError, OSError):
                ok = False
            (good if ok else bad).append(job)

        if not bad:
            say("{0}:  {1} of {2} sub-folder(s) have a correct {3},".format(
                soc_name.upper(), len(good), len(soc.jobs), OUTPUT_NAME))
            say("          and the original .com files are unchanged.")
        else:
            all_ok = False
            say("{0}:  PROBLEM - {1} {2} file(s) are missing or not correct:".format(
                soc_name.upper(), len(bad), OUTPUT_NAME))
            for job in bad:
                say("      " + job.label + ("   (" + job.reason + ")" if job.reason else ""))
            say("          The other {0} are fine.".format(len(good)))
        if kept:
            say("          Left unchanged on your request (different): {0}".format(len(kept)))
            for job in kept:
                say("              " + job.label)
        say("          Folder:  " + soc.path)
        say("")
    if all_ok:
        say("DONE. Everything is in place.")
    else:
        say("Please fix the problem(s) above and run the program again:")
        say("files that are already correct will be skipped.")
    say(LINE)
    return 0 if all_ok else 1


def main():
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        say(__doc__)
        return 0

    problem = header_problem()
    if problem:
        say("")
        warn(problem)
        warn("Please correct NEW_HEADER at the top of this program file.")
        return 1

    say(LINE)
    say("  CREATION OF {0}  (soc_singlet and soc_triplet)".format(OUTPUT_NAME))
    say("  In every sub-folder, e.g.  soc_singlet/g1.com/ , it reads g1.com,")
    say("  puts the new first lines on top and saves it as  {0}".format(OUTPUT_NAME))
    say("  (g1.com itself is not changed). soc_singlet first, then soc_triplet.")
    say("  Press Ctrl+C at any time to stop.")
    say(LINE)
    if sys.argv[1:]:
        say("  Note: the program asks for the path itself; the words typed after")
        say("  the command are ignored.")
    enable_tab_completion()

    socs = ask_for_soc_folders()
    show_summary(socs)

    all_jobs = [job for soc in socs for job in soc.jobs]
    blocked = [job for job in all_jobs if job.status == BLOCKED]
    if blocked:
        say("")
        warn("These file(s) cannot be done:")
        for job in blocked:
            say("      {0}:".format(job.src_label))
            say("          " + job.reason)
        say("")
        say("  Nothing has been written (neither soc_singlet nor soc_triplet).")
        say("  Please fix the item(s) above, then run the program again.")
        return 1

    for job in all_jobs:
        job.write = job.status == NEW

    different = [job for job in all_jobs if job.status == DIFFERENT]
    if different:
        say("")
        say("  These {0} file(s) already exist but are DIFFERENT from what".format(OUTPUT_NAME))
        say("  would be written now:")
        for job in different:
            say("      " + job.label)
        if ask_yes_no("  Replace them?"):
            for job in different:
                job.write = True
        else:
            say("  OK, they will be left unchanged.")

    to_write = sum(1 for job in all_jobs if job.write)
    if to_write == 0:
        say("")
        say("  Nothing needs to be written.")
        return final_check(socs)

    say("")
    if not ask_yes_no("Write {0} {1} file(s) now?".format(to_write, OUTPUT_NAME)):
        say("  Cancelled. Nothing has been written.")
        return 0

    for soc in socs:  # soc_singlet first, then soc_triplet
        write_all(soc)
    return final_check(socs)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, UserQuit):
        say("")
        say("")
        say("Stopped by you. If writing had already started, simply run the")
        say("program again: files that are already correct are skipped.")
        sys.exit(130)
