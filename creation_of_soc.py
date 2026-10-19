#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Creation of SOC
===============

Copies every ".com" file found in a folder named "singlet" into its own
sub-folder inside a folder named "soc":

    .../scan/singlet/g1.com   -->   .../soc/g1.com/g1.com
    .../scan/singlet/g2.com   -->   .../soc/g2.com/g2.com
    ... one sub-folder for every .com file in singlet.

HOW TO RUN (Ubuntu terminal)
    python3 creation_of_soc.py

At the start the program asks two things:
    1. The path of the folder that contains "singlet"
       (or the path of the singlet folder itself).
    2. The path of the folder in which "soc" should be created
       (if that path already ends in "soc", that folder is used).

Type paths the same way as in the terminal, for example:
    jana/pp/opt/b3lyp/scan          (from the folder you are in now)
    /home/jana/pp/opt/b3lyp/scan    (full path)
    ~/pp/opt/b3lyp/scan             (from your home folder)
The Tab key completes folder names, like in the terminal.

SAFETY
    * Files in "singlet" are only read. They are never changed or moved.
    * Nothing is created or copied until you confirm the summary.
    * Files already in soc are never replaced without asking you.
    * Every copy is compared byte by byte with the original.
    * Running the program again is safe: files already copied are skipped.
"""
from __future__ import print_function

import sys

# Stop early, with a clear message, if started with the old Python 2.
if sys.version_info[0] < 3:
    sys.stderr.write(
        "\nThis program needs Python 3. Please run it like this:\n\n"
        "    python3 creation_of_soc.py\n\n")
    sys.exit(1)

import glob
import os
import re
import shlex
import shutil
import textwrap

# ---------------------------------------------------------------------------
# Settings (normally nothing needs to be changed here)
# ---------------------------------------------------------------------------
SINGLET_FOLDER_NAME = "singlet"  # folder to look for (Singlet / SINGLET also accepted)
SOC_FOLDER_NAME = "soc"          # folder that is created
FILE_EXTENSION = ".com"          # files that are copied (.COM also accepted)
# True  -> soc/g1.com/g1.com   (sub-folder named exactly like the file)
# False -> soc/g1/g1.com       (sub-folder named without ".com")
KEEP_EXTENSION_IN_FOLDER_NAME = True
MAX_SEARCH_DEPTH = 10            # how many levels deep to search for "singlet"

LINE = "=" * 70

# Status of each file before copying
NEW = "new"              # not in soc yet -> will be copied
SAME = "same"            # already in soc and identical -> skipped
DIFFERENT = "different"  # already in soc but different -> asks before replacing
BLOCKED = "blocked"      # something in soc is in the way -> nothing is copied


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


def is_inside(path, folder):
    path = os.path.realpath(path)
    folder = os.path.realpath(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


# ---------------------------------------------------------------------------
# Step 1: the singlet folder
# ---------------------------------------------------------------------------
def is_singlet_name(name):
    return name.lower() == SINGLET_FOLDER_NAME.lower()


def search_for_singlet(top):
    """Look for folders named singlet anywhere below top."""
    found = []
    top_depth = top.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, _ in os.walk(top):
        depth = dirpath.rstrip(os.sep).count(os.sep) - top_depth
        keep = []
        for name in dirnames:
            if is_singlet_name(name):
                found.append(os.path.join(dirpath, name))  # not searched inside
            elif not name.startswith(".") and depth < MAX_SEARCH_DEPTH:
                keep.append(name)
        dirnames[:] = keep
    return natural_sorted(found)


def locate_singlet(folder):
    """Find the singlet folder at or below the given folder, or None."""
    if is_singlet_name(os.path.basename(folder)):
        return folder
    try:
        names = os.listdir(folder)
    except OSError as err:
        warn("Cannot open this folder ({0}):  {1}".format(err.strerror or err, folder))
        return None
    direct = natural_sorted(
        os.path.join(folder, name) for name in names
        if is_singlet_name(name) and os.path.isdir(os.path.join(folder, name)))
    if len(direct) == 1:
        return direct[0]
    if len(direct) > 1:
        return direct[ask_choice(
            "  More than one '{0}' folder is here. Which one?".format(SINGLET_FOLDER_NAME),
            direct)]

    say("  There is no '{0}' folder directly inside  {1}".format(SINGLET_FOLDER_NAME, folder))
    say("  Searching the sub-folders ...")
    found = search_for_singlet(folder)
    if not found:
        warn("No folder named '{0}' was found inside:  {1}".format(SINGLET_FOLDER_NAME, folder))
        return None
    if len(found) == 1:
        say("  Found:  " + found[0])
        return found[0] if ask_yes_no("  Use this folder?") else None
    choice = ask_choice(
        "  Several '{0}' folders were found. Which one?".format(SINGLET_FOLDER_NAME),
        found + ["None of these"])
    return found[choice] if choice < len(found) else None


def list_com_files(folder):
    """Return (sorted .com file names, number of other items), or (None, 0) on error."""
    try:
        names = os.listdir(folder)
    except OSError as err:
        warn("Cannot open this folder ({0}):  {1}".format(err.strerror or err, folder))
        return None, 0
    extension = FILE_EXTENSION.lower()
    wanted = []
    for name in names:
        if (name.lower().endswith(extension)
                and len(name) > len(extension)
                and not name.startswith(".")  # hidden / junk files such as ._g1.com
                and os.path.isfile(os.path.join(folder, name))):
            wanted.append(name)
    return natural_sorted(wanted), len(names) - len(wanted)


def ask_for_singlet():
    say("")
    say(LINE)
    say("STEP 1 of 2:  Where is the '{0}' folder?".format(SINGLET_FOLDER_NAME))
    say("  Type the path of the folder that CONTAINS '{0}'".format(SINGLET_FOLDER_NAME))
    say("  (for example:  jana/pp/opt/b3lyp/scan )")
    say("  or the path of the '{0}' folder itself.".format(SINGLET_FOLDER_NAME))
    say("  Tab completes folder names. You are now in:  " + current_folder())
    say(LINE)
    while True:
        raw = ask("Path to {0}: ".format(SINGLET_FOLDER_NAME))
        if not raw.strip():
            warn("Please type a path (or press Ctrl+C to stop).")
            continue
        folder = existing_folder_from(raw)
        if folder is None:
            continue
        singlet = locate_singlet(folder)
        if singlet is None:
            continue
        com_files, others = list_com_files(singlet)
        if com_files is None:
            continue
        if not com_files:
            warn("There are no '{0}' files in:  {1}".format(FILE_EXTENSION, singlet))
            warn("Please type another path.")
            continue
        say("")
        say("  OK, singlet folder:  " + singlet)
        say("  {0} '{1}' file(s) found:".format(len(com_files), FILE_EXTENSION))
        for row in textwrap.wrap(", ".join(com_files), width=64,
                                 break_long_words=False, break_on_hyphens=False):
            say("      " + row)
        if others:
            say("  ({0} other item(s) in this folder are not '{1}' files and are ignored.)"
                .format(others, FILE_EXTENSION))
        return singlet, com_files


# ---------------------------------------------------------------------------
# Step 2: where to create soc
# ---------------------------------------------------------------------------
def soc_location_problem(soc_dir):
    """Return a message if soc cannot be created/used at soc_dir, else None."""
    if os.path.lexists(soc_dir) and not os.path.isdir(soc_dir):
        return "Something that is not a folder is already called '{0}':  {1}".format(
            os.path.basename(soc_dir), soc_dir)
    existing = soc_dir
    while not os.path.exists(existing):  # nearest folder that already exists
        parent = os.path.dirname(existing)
        if parent == existing:
            break
        existing = parent
    if not os.path.isdir(existing):
        return "Cannot create a folder inside a file:  " + existing
    if not os.access(existing, os.W_OK | os.X_OK):
        return "You do not have permission to write in:  " + existing
    return None


def ask_for_soc_location(singlet):
    say("")
    say(LINE)
    say("STEP 2 of 2:  Where should the '{0}' folder be created?".format(SOC_FOLDER_NAME))
    say("  Type the path of the folder in which '{0}' should be made".format(SOC_FOLDER_NAME))
    say("  (for example:  jana/pp/opt/b3lyp/scan ).")
    say("  If the path already ends in '/{0}', that folder itself is used.".format(SOC_FOLDER_NAME))
    say(LINE)
    while True:
        raw = ask("Path for {0}: ".format(SOC_FOLDER_NAME))
        if not raw.strip():
            warn("Please type a path (or press Ctrl+C to stop).")
            continue
        found, guess, suggestions = find_path(raw)
        if found is not None:
            if not os.path.isdir(found):
                warn("This is a file, not a folder:  " + found)
                continue
            base = found
        else:
            say("  This folder does not exist yet:  " + guess)
            if suggestions:
                options = suggestions + ["No - create the new folder  " + guess,
                                         "No - let me type the path again"]
                choice = ask_choice("  Did you mean an existing folder?", options)
                if choice < len(suggestions):
                    base = suggestions[choice]
                elif choice == len(suggestions):
                    base = guess
                else:
                    continue
            elif ask_yes_no("  Should it be created?"):
                base = guess
            else:
                warn("Please type the path again.")
                continue

        if os.path.basename(base).lower() == SOC_FOLDER_NAME.lower():
            soc_dir = base
        else:
            soc_dir = os.path.join(base, SOC_FOLDER_NAME)

        problem = soc_location_problem(soc_dir)
        if problem:
            warn(problem)
            warn("Please type another path.")
            continue
        if is_inside(soc_dir, singlet):
            say("  Note: this puts '{0}' INSIDE the '{1}' folder:  {2}".format(
                SOC_FOLDER_NAME, SINGLET_FOLDER_NAME, soc_dir))
            if not ask_yes_no("  Is that really what you want?"):
                continue
        say("")
        say("  OK, soc folder:  " + soc_dir)
        return soc_dir


# ---------------------------------------------------------------------------
# Planning, copying and checking
# ---------------------------------------------------------------------------
class Job(object):
    """One .com file: where it comes from and where it goes."""

    def __init__(self, name, singlet, soc_dir):
        self.name = name
        self.src = os.path.join(singlet, name)
        if KEEP_EXTENSION_IN_FOLDER_NAME:
            folder_name = name
        else:
            folder_name = name[:-len(FILE_EXTENSION)]
        self.folder = os.path.join(soc_dir, folder_name)
        self.dst = os.path.join(self.folder, name)
        self.status = NEW
        self.reason = ""
        self.copy = False    # will be copied in this run
        self.copied = False  # was copied and checked in this run


def same_content(path_a, path_b):
    """True if both files have exactly the same bytes."""
    if os.path.getsize(path_a) != os.path.getsize(path_b):
        return False
    with open(path_a, "rb") as file_a, open(path_b, "rb") as file_b:
        while True:
            block_a = file_a.read(1024 * 1024)
            block_b = file_b.read(1024 * 1024)
            if block_a != block_b:
                return False
            if not block_a:
                return True


def check_job(job):
    """Decide what has to happen with one file. Nothing is changed here."""
    if not os.access(job.src, os.R_OK):
        return BLOCKED, "cannot read the original file " + job.src
    if os.path.lexists(job.folder):
        if os.path.islink(job.folder):
            return BLOCKED, "this is a link, not a normal folder: " + job.folder
        if not os.path.isdir(job.folder):
            return BLOCKED, "a FILE with the sub-folder's name is in the way: " + job.folder
    if os.path.lexists(job.dst):
        if os.path.islink(job.dst):
            return BLOCKED, "this is a link, not a normal file: " + job.dst
        if not os.path.isfile(job.dst):
            return BLOCKED, "a FOLDER with the file's name is in the way: " + job.dst
        try:
            if same_content(job.src, job.dst):
                return SAME, ""
        except (IOError, OSError) as err:
            return BLOCKED, "cannot read {0} ({1})".format(job.dst, err.strerror or err)
        return DIFFERENT, ""
    return NEW, ""


def make_plan(singlet, com_files, soc_dir):
    jobs = [Job(name, singlet, soc_dir) for name in com_files]
    for job in jobs:
        job.status, job.reason = check_job(job)
    # Two files must never end up in the same sub-folder.
    by_folder = {}
    for job in jobs:
        by_folder.setdefault(job.folder, []).append(job)
    for group in by_folder.values():
        if len(group) > 1:
            for job in group:
                job.status = BLOCKED
                job.reason = "would share the sub-folder {0} with {1}".format(
                    job.folder, ", ".join(j.name for j in group if j is not job))
    return jobs


def short(path, soc_dir):
    """soc/g1.com/g1.com instead of the full path."""
    return os.path.relpath(path, os.path.dirname(soc_dir))


def show_summary(singlet, soc_dir, jobs):
    count = lambda status: sum(1 for job in jobs if job.status == status)
    say("")
    say(LINE)
    say("SUMMARY - please check. Nothing has been created or copied yet.")
    say(LINE)
    say("  From (singlet)  :  " + singlet)
    say("  To   (soc)      :  " + soc_dir
        + ("" if os.path.isdir(soc_dir) else "   <- will be created"))
    say("  .com files      :  {0}  (one sub-folder each)".format(len(jobs)))
    say("  Layout          :  " + short(jobs[0].dst, soc_dir)
        + ("  ...  " + short(jobs[-1].dst, soc_dir) if len(jobs) > 1 else ""))
    say("")
    say("  New, will be copied                 :  {0}".format(count(NEW)))
    if count(SAME):
        say("  Already in soc and identical (skip) :  {0}".format(count(SAME)))
    if count(DIFFERENT):
        say("  Already in soc but DIFFERENT        :  {0}".format(count(DIFFERENT)))
    if count(BLOCKED):
        say("  Cannot be copied                    :  {0}".format(count(BLOCKED)))
    say(LINE)


def copy_files(soc_dir, jobs):
    to_copy = [job for job in jobs if job.copy]
    say("")
    say("Copying ...")
    try:
        if not os.path.isdir(soc_dir):
            os.makedirs(soc_dir)
    except OSError as err:
        warn("Could not create the soc folder ({0}):  {1}".format(err.strerror or err, soc_dir))
        for job in to_copy:
            job.reason = "soc folder could not be created"
        return
    width = len(str(len(to_copy)))
    for number, job in enumerate(to_copy, 1):
        counter = "[{0:>{2}}/{1}]".format(number, len(to_copy), width)
        try:
            if not os.path.isdir(job.folder):
                os.makedirs(job.folder)
            shutil.copyfile(job.src, job.dst)
            try:
                shutil.copystat(job.src, job.dst)  # keep the file date (not essential)
            except OSError:
                pass
            if not same_content(job.src, job.dst):
                raise IOError("the copy is not identical to the original")
            job.copied = True
            say("  {0} OK      {1}  ->  {2}".format(counter, job.name, short(job.dst, soc_dir)))
        except Exception as err:
            job.reason = str(getattr(err, "strerror", None) or err)
            say("  {0} FAILED  {1}  ({2})".format(counter, job.name, job.reason))


def final_check(soc_dir, jobs):
    """Look at soc again and confirm every file is there and identical."""
    say("")
    say("Final check: comparing every file in soc with the original ...")
    good, bad, kept = [], [], []
    for job in jobs:
        if job.status == DIFFERENT and not job.copy:
            kept.append(job)  # the user chose to keep the old version
            continue
        try:
            ok = (os.path.isdir(job.folder) and not os.path.islink(job.dst)
                  and os.path.isfile(job.dst) and same_content(job.src, job.dst))
        except (IOError, OSError):
            ok = False
        (good if ok else bad).append(job)

    say("")
    say(LINE)
    if not bad:
        say("DONE.  {0} of {1} '{2}' file(s) are in soc, each in its own sub-folder,"
            .format(len(good), len(jobs), FILE_EXTENSION))
        say("       and identical to the originals in singlet.")
    else:
        say("PROBLEM:  {0} file(s) are missing or not identical in soc:".format(len(bad)))
        for job in bad:
            say("      " + job.name + ("   (" + job.reason + ")" if job.reason else ""))
        say("  The other {0} file(s) are fine. Fix the problem above and run the".format(len(good)))
        say("  program again: files that are already fine will be skipped.")
    if kept:
        say("  Left unchanged on your request (different from singlet): {0}".format(len(kept)))
        for job in kept:
            say("      " + short(job.dst, soc_dir))
    say("  soc folder:  " + soc_dir)
    say(LINE)
    return 0 if not bad else 1


def main():
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        say(__doc__)
        return 0

    say(LINE)
    say("  CREATION OF SOC")
    say("  Copies every '{0}' file from the '{1}' folder into its own".format(
        FILE_EXTENSION, SINGLET_FOLDER_NAME))
    say("  sub-folder of '{0}':   {1}/g1{2}  ->  {0}/g1{2}/g1{2}".format(
        SOC_FOLDER_NAME, SINGLET_FOLDER_NAME, FILE_EXTENSION))
    say("  Press Ctrl+C at any time to stop.")
    say(LINE)
    if sys.argv[1:]:
        say("  Note: the program asks for the paths itself; the words typed after")
        say("  the command are ignored.")
    enable_tab_completion()

    singlet, com_files = ask_for_singlet()
    soc_dir = ask_for_soc_location(singlet)

    jobs = make_plan(singlet, com_files, soc_dir)
    show_summary(singlet, soc_dir, jobs)

    blocked = [job for job in jobs if job.status == BLOCKED]
    if blocked:
        say("")
        warn("These file(s) cannot be copied:")
        for job in blocked:
            say("      {0}:  {1}".format(job.name, job.reason))
        say("")
        say("  Nothing has been created or copied. Please move or rename the")
        say("  item(s) above, then run the program again.")
        return 1

    for job in jobs:
        job.copy = job.status == NEW

    different = [job for job in jobs if job.status == DIFFERENT]
    if different:
        say("")
        say("  These file(s) are already in soc but are DIFFERENT from singlet:")
        for job in different:
            say("      " + short(job.dst, soc_dir))
        if ask_yes_no("  Replace them with the version from singlet?"):
            for job in different:
                job.copy = True
        else:
            say("  OK, they will be left unchanged.")

    to_copy = sum(1 for job in jobs if job.copy)
    if to_copy == 0:
        say("")
        say("  Nothing needs to be copied.")
        return final_check(soc_dir, jobs)

    say("")
    if not ask_yes_no("Start copying {0} file(s) now?".format(to_copy)):
        say("  Cancelled. Nothing has been created or copied.")
        return 0

    copy_files(soc_dir, jobs)
    return final_check(soc_dir, jobs)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, UserQuit):
        say("")
        say("")
        say("Stopped by you. If copying had already started, simply run the")
        say("program again: files that are already copied correctly are skipped.")
        sys.exit(130)
