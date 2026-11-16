#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOC plot  (make soc_plot.ods: k ISC of every geometry, in the SOC-PP layout)
===========================================================================

Makes the sheet soc_plot.ods in the layout of SOC-PP.ods: one block per
geometry (g1, g2, ... g41) and, in every block, one row for each transition
you choose (for example S1-T2, S2-T3 and S3-T4):

         B      C       D       E        F           G ... K     L .. N   O
    1    g1
    2           S1      T2      E(S-T)   SOC (cm-1)  SOC (ev) ...  rho fc  K ISC
    3           S0+S1   S0+T2   =C3-D3   from        =F3/8065.73 ...      =formula
                                         soc_out.dat
    4           S2      T3
    5           S0+S2   S0+T3   ...
    ...
    8    g2
    ...

WHERE THE NUMBERS COME FROM
    S1, T2 ...   the sheet with the energies (for example plot_s_t.ods), with
                 S0 added: under the label S1 goes S0 + S1, under T2 goes
                 S0 + T2, and so on (S0 itself goes under the label S0).
    SOC (cm-1)   soc_singlet/g1.com/soc_out.dat (written by PySOC), the line
                     sum_soc, <S(1)|Hso|T(2),1,0,-1> (cm-1):   5.28630  ...
                 the FIRST number after "(cm-1):" (the total SOC, sum_soc).
    the rest     the same constants and formulas as SOC-PP.ods:
                 h = 4.136E-15 eV s, lam = 0.2 eV, kB = 8.6173E-05 eV/K,
                 T = 300 K, E = C-D, SOC (ev) = F/8065.73, ...
                 Every result cell is a formula, so the sheet recalculates
                 if you change a number.

HOW TO RUN (Ubuntu terminal)
    python3 soc_plot.py

It asks four things:
    1. Where the sheet with the energies is (.ods, .xlsx or .csv). It needs
       one row per geometry (g1.log, g2.log ... or g1, g2 ...) and columns
       named S0, S1 ... S4, T1 ... T4 and/or S0+S1 ... S0+T4. If a name is
       in two columns (for example two columns called S1), you are shown
       both and choose; a column called T4 that holds S0 + T4 is recognised.
    2. Which transitions, typed as pairs, singlet first:
           S1 T2 S2 T3 S3 T4      means   S1-T2, S2-T3, S3-T4
    3. Where soc_singlet is (soc_singlet itself, or the folder that
       contains it), as in the other programs.
    4. In which folder soc_plot.ods should be saved (Enter: next to the
       energies sheet; a new folder is made if needed).
Then it shows what it found and, after you type y, writes soc_plot.ods.
Open it in LibreOffice, or upload it to Google Drive (it opens there as a
Google Sheet).

SAFETY
    * The energies sheet and the soc_out.dat files are only read. Nothing in
      soc_singlet is changed.
    * Nothing is written before you type y.
    * If soc_plot.ods is already there, it is kept as soc_plot_old1.ods
      (then soc_plot_old2.ods, ...). No file is ever deleted or overwritten.
    * Geometries with a problem (no soc_out.dat, a transition missing in it,
      an unreadable number, no energy in the sheet) are listed, and they are
      only left out if you agree.
    * The new file is read back and checked cell by cell.
"""
from __future__ import print_function

import sys

# Stop early, with a clear message, if started with the old Python 2.
if sys.version_info[0] < 3:
    sys.stderr.write(
        "\nThis program needs Python 3.\n"
        "Please run it like this:\n\n"
        "    python3 soc_plot.py\n\n")
    sys.exit(1)

import csv
import glob
import io
import math
import os
import re
import shlex
import textwrap
import zipfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from xml.sax.saxutils import escape

# ---------------------------------------------------------------------------
# Settings (normally nothing needs to be changed here)
# ---------------------------------------------------------------------------
OUTPUT_STEM = "soc_plot"         # the new sheet is soc_plot.ods
OUTPUT_EXTENSION = ".ods"
SOC_OUT = "soc_out.dat"          # written by PySOC (soc_td) in every sub-folder
SOC_FOLDER = "soc_singlet"
OTHER_SOC_FOLDER = "soc_triplet"
ORIGINAL_FOLDERS = ("singlet", "triplet")
SUBFOLDER_EXTENSION = ".com"     # sub-folders are named g1.com, g2.com, ...
MAX_SEARCH_DEPTH = 10
RUN_INIT_LOCK = ".run_init.lock"  # lock of a running run_init.py
SHEET_EXTENSIONS = (".ods", ".fods", ".xlsx", ".xlsm", ".csv", ".tsv")
GEOMETRY_EXTENSIONS = (".com", ".gjf", ".log", ".out", ".chk", ".fchk", ".dat", ".xyz")
SUM_TOLERANCE = 6e-5             # eV: an 'S0+S1' column may differ this much from S0 + S1
S0_LIMIT = 50.0                  # eV: bigger S0 values look like Hartree, not eV
HEADER_SEARCH_ROWS = 300         # the column names must be in the first 300 used rows
MAX_REPEAT = 2048                # repeated cells/rows read at most this often

# The constants and formulas of SOC-PP.ods (one row per transition; {r} = row)
PLANCK_H = 4.136e-15             # column H, Plank h (ev)
LAMBDA = 0.2                     # column I, lam (eV)
BOLTZMANN = 0.000086173          # column J, Boltaz (Kb)(ev)
TEMPERATURE = 300                # column K, T (K)
FORMULAS = OrderedDict([
    ("E", "of:=[.C{r}]-[.D{r}]"),
    ("G", "of:=[.F{r}]/8065.73"),
    ("L", "of:=EXP(-((([.E{r}]+[.I{r}])^2)/(4*[.I{r}]*[.J{r}]*[.K{r}])))"),
    ("M", "of:=SQRT(4*3.1415*[.I{r}]*0.02585)"),
    ("N", "of:=[.L{r}]/[.M{r}]"),
    ("O", "of:=(4*3.1415*3.1415*[.N{r}]*[.G{r}]*[.G{r}])/[.H{r}]"),
])
# Column titles, exactly as in SOC-PP.ods (row 2 of Sheet1)
TITLES = OrderedDict([
    ("E", "E(S-T)"), ("F", "SOC (cm-1)"), ("G", "SOC (ev)"), ("H", "Plank h (ev)"),
    ("I", "lam (\u03bbm)ev"), ("J", "Boltaz (Kb)(ev)"), ("K", "T (K)"),
    ("N", "\u03c1fc"), ("O", "K ISC"),
])
# Column widths in pt: wide enough that no number is shown as ###
COLUMN_WIDTHS = OrderedDict([
    ("A", 64.6), ("B", 63.89), ("C", 72.0), ("D", 72.0), ("E", 72.0), ("F", 76.0),
    ("G", 76.0), ("H", 76.0), ("I", 76.0), ("J", 106.24), ("K", 64.6), ("L", 84.0),
    ("M", 84.0), ("N", 84.0), ("O", 80.0),
])
COLUMNS = "ABCDEFGHIJKLMNO"

LINE = "=" * 70


class UserQuit(Exception):
    """The user pressed Ctrl+D at a question."""


class SheetError(Exception):
    """A sheet file could not be read."""


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


def show_wrapped(names, indent="      "):
    for row in textwrap.wrap(", ".join(names), width=64,
                             break_long_words=False, break_on_hyphens=False):
        say(indent + row)


def short_list(names, limit=6):
    """g1, g2, g3, ..., g41  (not all names when there are many)."""
    names = list(names)
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:3]) + ", ... " + ", ".join(names[-2:])


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


def column_letter(index):
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def column_index(letters):
    """A -> 0, Z -> 25, AA -> 26."""
    index = 0
    for letter in letters.upper():
        index = index * 26 + (ord(letter) - 64)
    return index - 1


def read_text(path, limit=16 * 1024 * 1024):
    try:
        with open(path, "rb") as handle:
            return handle.read(limit).decode("utf-8", "replace")
    except (IOError, OSError):
        return None


def to_float(text):
    """The number in text, or None (also for NaN, Inf and Fortran's *****)."""
    if text is None:
        return None
    text = text.strip()
    if re.match(r"^[+-]?\d+,\d+$", text):          # 4,0749 (decimal comma)
        text = text.replace(",", ".")
    if not re.match(r"^[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?$", text):
        return None
    try:
        value = float(text.replace("d", "e").replace("D", "e"))
    except ValueError:
        return None
    if math.isinf(value) or math.isnan(value):
        return None
    return value


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
    suggestions lists existing paths the user may have meant (the same
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


# ---------------------------------------------------------------------------
# Reading a sheet file (.ods, .fods, .xlsx, .xlsm, .csv, .tsv)
# Every sheet becomes {(row, column): (number or None, text, formula or None)}
# with row and column counted from 0.
# ---------------------------------------------------------------------------
ODF_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
ODF_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
ODF_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def odf_text(element):
    """The text of a <text:p>, with <text:s>, <text:tab> and line breaks."""
    parts = [element.text or ""]
    for child in element:
        if child.tag == ODF_TEXT + "s":
            try:
                count = int(child.get(ODF_TEXT + "c", "1"))
            except ValueError:
                count = 1
            parts.append(" " * max(count, 1))
        elif child.tag == ODF_TEXT + "tab":
            parts.append("\t")
        elif child.tag == ODF_TEXT + "line-break":
            parts.append("\n")
        else:
            parts.append(odf_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def repeat_count(value):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return 1


def odf_cell(cell):
    """(number or None, text, formula or None) of an ODF cell, or None if it is empty."""
    value_type = cell.get(ODF_OFFICE + "value-type")
    formula = cell.get(ODF_TABLE + "formula")
    text = "\n".join(odf_text(p) for p in cell.findall(ODF_TEXT + "p"))
    number = None
    if value_type in ("float", "percentage", "currency"):
        number = to_float(cell.get(ODF_OFFICE + "value"))
    elif value_type in (None, "string"):
        number = to_float(text)
    if number is None and not text.strip() and not formula:
        return None
    return number, text, formula


def read_odf_xml(data):
    """All sheets of an ODF spreadsheet (content.xml of .ods, or a whole .fods)."""
    root = ET.fromstring(data)
    sheets = []
    for table in root.iter(ODF_TABLE + "table"):
        name = table.get(ODF_TABLE + "name") or "Sheet{0}".format(len(sheets) + 1)
        cells = {}
        row_index = 0
        for row in table.iter(ODF_TABLE + "table-row"):
            row_repeat = repeat_count(row.get(ODF_TABLE + "number-rows-repeated"))
            found = []
            column = 0
            for cell in row:
                if cell.tag not in (ODF_TABLE + "table-cell", ODF_TABLE + "covered-table-cell"):
                    continue
                column_repeat = repeat_count(cell.get(ODF_TABLE + "number-columns-repeated"))
                content = odf_cell(cell)
                if content is not None:
                    for k in range(min(column_repeat, MAX_REPEAT)):
                        found.append((column + k, content))
                column += column_repeat
            if found:
                for k in range(min(row_repeat, MAX_REPEAT)):
                    for col, content in found:
                        cells[(row_index + k, col)] = content
            row_index += row_repeat
        sheets.append((name, cells))
    return sheets


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def children_named(element, name):
    return [child for child in element if local_name(child.tag) == name]


def all_named(element, name):
    return [child for child in element.iter() if local_name(child.tag) == name]


def xlsx_part(base, target):
    """Path inside the zip of a relationship target."""
    if target.startswith("/"):
        path = target[1:]
    else:
        path = base + target
    parts = []
    for piece in path.split("/"):
        if piece == "..":
            if parts:
                parts.pop()
        elif piece and piece != ".":
            parts.append(piece)
    return "/".join(parts)


def read_xlsx(path):
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(package.read("xl/sharedStrings.xml"))
            for item in children_named(root, "si"):
                pieces = []
                for child in item:              # <t>, or rich text runs <r><t>; not <rPh>
                    if local_name(child.tag) == "t":
                        pieces.append(child.text or "")
                    elif local_name(child.tag) == "r":
                        pieces.extend(t.text or "" for t in children_named(child, "t"))
                shared.append("".join(pieces))
        workbook = ET.fromstring(package.read("xl/workbook.xml"))
        relations = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ET.fromstring(package.read("xl/_rels/workbook.xml.rels")):
                relations[rel.get("Id")] = rel.get("Target") or ""
        sheets = []
        for sheet in all_named(workbook, "sheet"):
            name = sheet.get("name") or "Sheet{0}".format(len(sheets) + 1)
            rel_id = None
            for key, value in sheet.attrib.items():
                if local_name(key) == "id":
                    rel_id = value
            target = relations.get(rel_id)
            if not target:
                continue
            part = xlsx_part("xl/", target)
            if part not in names:
                continue
            root = ET.fromstring(package.read(part))
            cells = {}
            row_number = 0
            for row in all_named(root, "row"):
                row_number = repeat_count(row.get("r")) if row.get("r") else row_number + 1
                column = -1
                for cell in children_named(row, "c"):
                    ref = cell.get("r")
                    match = re.match(r"^([A-Za-z]+)(\d+)$", ref or "")
                    column = column_index(match.group(1)) if match else column + 1
                    kind = cell.get("t")
                    value = children_named(cell, "v")
                    value = value[0].text if value else None
                    formula = children_named(cell, "f")
                    formula = (formula[0].text or "") if formula else None
                    number = None
                    if kind == "s":
                        try:
                            text = shared[int(value)]
                        except (TypeError, ValueError, IndexError):
                            text = ""
                        number = to_float(text)
                    elif kind == "inlineStr":
                        text = "".join(t.text or "" for t in all_named(cell, "t"))
                        number = to_float(text)
                    elif kind in ("str", "b", "e", "d"):
                        text = value or ""
                    else:
                        text = value or ""
                        number = to_float(value)
                    if number is None and not text.strip() and not formula:
                        continue
                    cells[(row_number - 1, column)] = (number, text, formula)
            sheets.append((name, cells))
        return sheets


def read_csv(path):
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8-sig", "replace")
    try:
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel_tab if path.lower().endswith(".tsv") else csv.excel
    cells = {}
    for row_index, row in enumerate(csv.reader(io.StringIO(text), dialect)):
        for col, value in enumerate(row):
            if value.strip():
                cells[(row_index, col)] = (to_float(value), value, None)
    return [(os.path.basename(path), cells)]


def read_workbook(path):
    """All sheets of the file as [(sheet name, cells)]. Raises SheetError."""
    lower = path.lower()
    try:
        if lower.endswith(".ods"):
            with zipfile.ZipFile(path) as package:
                return read_odf_xml(package.read("content.xml"))
        if lower.endswith(".fods"):
            with open(path, "rb") as handle:
                return read_odf_xml(handle.read())
        if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
            return read_xlsx(path)
        if lower.endswith(".csv") or lower.endswith(".tsv"):
            return read_csv(path)
    except (IOError, OSError) as err:
        raise SheetError("Cannot read this file ({0}).".format(
            getattr(err, "strerror", None) or err))
    except zipfile.BadZipfile:
        raise SheetError("This file is damaged or is not really a {0} file.".format(
            os.path.splitext(path)[1]))
    except KeyError:
        raise SheetError("This file is not a complete spreadsheet (a part is missing).")
    except ET.ParseError:
        raise SheetError("This file is damaged (its contents cannot be read).")
    except (ValueError, UnicodeError) as err:
        raise SheetError("This file cannot be read ({0}).".format(err))
    raise SheetError("Only .ods, .xlsx and .csv sheets can be read.")


# ---------------------------------------------------------------------------
# Finding the energies in a sheet
# ---------------------------------------------------------------------------
def header_label(text):
    """
    ('state', 'S1') for a column named S1 (also 's1', 'S1 (eV)'),
    ('sum', 'S1') for a column named S0+S1 (also 'S0 + S1', 'S1+S0'),
    None for anything else.
    """
    name = re.sub(r"\s+", "", text or "").upper().replace("\uff0b", "+")
    name = re.sub(r"(\(EV\)|\[EV\]|/EV|\(INEV\))$", "", name)
    while len(name) >= 2 and name[0] == "(" and name[-1] == ")":
        name = name[1:-1]
    match = re.match(r"^([ST])(\d+)$", name)
    if match:
        state = match.group(1) + str(int(match.group(2)))
        return None if state == "T0" else ("state", state)
    for pattern in (r"^S0\+([ST])(\d+)$", r"^([ST])(\d+)\+S0$"):
        match = re.match(pattern, name)
        if match:
            state = match.group(1) + str(int(match.group(2)))
            return None if state in ("S0", "T0") else ("sum", state)
    return None


def geometry_key(text):
    """'g1' for g1, g1.log, g1.com, G1.LOG, singlet/g1.log; None if it is not such a name."""
    name = (text or "").strip()
    if not name or len(name) > 200 or "\n" in name:
        return None
    name = name.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lower()
    for extension in GEOMETRY_EXTENSIONS:
        if name.endswith(extension) and len(name) > len(extension):
            name = name[:-len(extension)]
            break
    return name if re.match(r"^[a-z][a-z_\-]*\d+$", name) else None


def folder_key(name):
    """'g1' for the sub-folder g1.com (or g1)."""
    key = geometry_key(name)
    if key:
        return key
    low = name.lower()
    if low.endswith(SUBFOLDER_EXTENSION) and len(low) > len(SUBFOLDER_EXTENSION):
        low = low[:-len(SUBFOLDER_EXTENSION)]
    return low


def state_sort_key(state):
    return (0 if state[0] == "S" else 1, int(state[1:]))


class Table(object):
    """The energies table found in one sheet."""

    def __init__(self, sheet, cells):
        self.sheet = sheet
        self.cells = cells
        self.header_row = None
        self.geometry_column = None
        self.geometries = OrderedDict()   # key -> (name as written, row)
        self.state_columns = {}           # 'S1' -> column of 'S1'
        self.sum_columns = {}             # 'S1' -> column of 'S0+S1'
        self.headers = {}                 # column -> its name in the sheet
        self.ambiguous = {}               # ('state'|'sum', 'S1') -> [columns]
        self.duplicates = {}              # key -> [rows] (same geometry, different numbers)

    def number(self, column, key):
        cell = self.cells.get((self.geometries[key][1], column))
        return cell[0] if cell else None

    def can_add_s0(self, state):
        """True if S0 + state can be made (or S0 itself, for state S0)."""
        if state == "S0":
            return "S0" in self.state_columns
        return state in self.sum_columns or (
            state in self.state_columns and "S0" in self.state_columns)

    def plain_only(self, state):
        return (state != "S0" and state in self.state_columns
                and not self.can_add_s0(state))

    def column_label(self, label, col):
        """Use this column for ('state'|'sum', 'S1') from now on."""
        if label[0] == "state":
            self.state_columns[label[1]] = col
        else:
            self.sum_columns[label[1]] = col
        self.ambiguous.pop(label, None)

    def available(self):
        return sorted(set(self.state_columns) | set(self.sum_columns) | (
            {"S0"} if "S0" in self.state_columns else set()), key=state_sort_key)


def build_table(sheet, cells, by_row, header_row, labels):
    """The table under this header row, or None if it has no geometry rows with numbers."""
    rows_below = [row for row in sorted(by_row) if row > header_row]
    counts = {}
    for row in rows_below:
        for col, (number, text, _) in by_row[row].items():
            if number is None and geometry_key(text) and not header_label(text):
                counts[col] = counts.get(col, 0) + 1
    if not counts:
        return None
    geometry_column = min(counts, key=lambda col: (-counts[col], col))
    label_columns = OrderedDict()
    for col in sorted(labels):
        label_columns.setdefault(labels[col], []).append(col)
    found = OrderedDict()
    for row in rows_below:
        cell = by_row[row].get(geometry_column)
        if cell is None or cell[0] is not None or header_label(cell[1]):
            continue
        key = geometry_key(cell[1])
        if key:
            found.setdefault(key, []).append((cell[1].strip(), row))
    numbers_found = False
    for rows in found.values():
        for _, row in rows:
            for cols in label_columns.values():
                for col in cols:
                    cell = by_row[row].get(col)
                    if cell is not None and cell[0] is not None:
                        numbers_found = True
    if not numbers_found:
        return None

    def number_at(row, col):
        cell = by_row.get(row, {}).get(col)
        return cell[0] if cell else None

    table = Table(sheet, cells)
    table.header_row = header_row
    table.geometry_column = geometry_column
    for col, label in labels.items():
        table.headers[col] = by_row[header_row][col][1].strip()
    table.headers[geometry_column] = (by_row[header_row].get(geometry_column) or
                                      (None, "", None))[1].strip()
    for label, cols in label_columns.items():
        kind, state = label
        if len(cols) > 1:
            for rows in found.values():
                for _, row in rows:
                    if len(set(number_at(row, col) for col in cols)) > 1:
                        table.ambiguous[label] = cols
        if kind == "state":
            table.state_columns[state] = cols[0]
        else:
            table.sum_columns[state] = cols[0]
    all_columns = [col for cols in label_columns.values() for col in cols]
    for key, rows in found.items():
        table.geometries[key] = rows[0]
        if len(rows) > 1:
            first = [number_at(rows[0][1], col) for col in all_columns]
            if any([number_at(row, col) for col in all_columns] != first for _, row in rows[1:]):
                table.duplicates[key] = [row for _, row in rows]
    return table


def find_table(sheet, cells):
    """The energies table of one sheet, or None."""
    by_row = {}
    for (row, col), cell in cells.items():
        by_row.setdefault(row, {})[col] = cell
    candidates = []
    for row in sorted(by_row)[:HEADER_SEARCH_ROWS]:
        labels = {}
        for col, (number, text, _) in by_row[row].items():
            if number is None:
                label = header_label(text)
                if label:
                    labels[col] = label
        if labels:
            candidates.append((-len(set(labels.values())), row, labels))
    candidates.sort(key=lambda item: (item[0], item[1]))
    for _, row, labels in candidates:
        table = build_table(sheet, cells, by_row, row, labels)
        if table is not None:
            return table
    return None


def looks_like_soc_pp(sheets):
    for _, cells in sheets:
        for (_, text, _) in cells.values():
            if (text or "").strip().upper() == "K ISC":
                return True
    return False


def describe_columns(table, columns, prefix=""):
    items = []
    for state in sorted(columns, key=state_sort_key):
        col = columns[state]
        items.append("{0}{1} ({2})".format(prefix, state, column_letter(col)))
    return items


def show_table(path, table):
    keys = list(table.geometries)
    names = [table.geometries[key][0] for key in natural_sorted(keys)]
    first_row = min(row for _, row in table.geometries.values()) + 1
    say("  OK, energies sheet:  " + path)
    say("  Sheet '{0}': {1} geometr{2} in column {3}, from row {4}:".format(
        table.sheet, len(keys), "y" if len(keys) == 1 else "ies",
        column_letter(table.geometry_column), first_row))
    say("      " + short_list(names))
    if table.state_columns:
        say("  Energy columns (column letter in brackets):")
        show_wrapped(describe_columns(table, table.state_columns))
    if table.sum_columns:
        say("  Columns with S0 already added:")
        show_wrapped(describe_columns(table, table.sum_columns, "S0+"))
    if table.ambiguous:
        say("  Note: these names are in more than one column, with different numbers:")
        show_wrapped(["{0} ({1})".format(label_name(label), ", ".join(
            column_letter(col) for col in cols)) for label, cols in sorted_labels(table.ambiguous)])
        say("  If they are needed, you will be shown both and asked which to use.")
    for key in natural_sorted(table.duplicates):
        warn("{0} is in the sheet more than once (rows {1}) with different numbers.".format(
            table.geometries[key][0], ", ".join(str(r + 1) for r in table.duplicates[key])))


def spreadsheets_in(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return natural_sorted(
        os.path.join(folder, name) for name in names
        if name.lower().endswith(SHEET_EXTENSIONS) and not name.startswith(".")
        and os.path.isfile(os.path.join(folder, name)))


def ask_for_sheet():
    """Returns (path of the energies sheet, Table)."""
    say("")
    say(LINE)
    say("1. Where is the sheet with the energies?")
    say("  (one row per geometry, columns S0, S1 ... T4 and/or S0+S1 ... S0+T4;")
    say("   for example  jana/pp/opt/b3lyp/scan/plot_s_t.ods )")
    say("  .ods, .xlsx and .csv files can be read. Tab completes names.")
    say("  You are now in:  " + (current_folder() or "(unknown)"))
    say(LINE)
    while True:
        raw = ask("Path to the energies sheet: ")
        if not raw.strip():
            warn("Please type a path (or press Ctrl+C to stop).")
            continue
        if re.match(r"^\s*['\"]?https?://", raw):
            warn("This is a web link. Please download the sheet first (Google Sheets:")
            warn("File > Download > OpenDocument (.ods)) and type the path of that file.")
            continue
        path = existing_path_from(raw, "File")
        if path is None:
            continue
        if os.path.isdir(path):
            found = spreadsheets_in(path)
            if not found:
                warn("This is a folder with no .ods, .xlsx or .csv file in it:  " + path)
                warn("Please type the path of the sheet file itself.")
                continue
            if len(found) == 1:
                say("  This is a folder. The only sheet in it is:  " + found[0])
                if not ask_yes_no("  Use this sheet?"):
                    continue
                path = found[0]
            else:
                choice = ask_choice("  This is a folder. Which sheet in it?",
                                    found + ["None of these"])
                if choice == len(found):
                    continue
                path = found[choice]
        lower = path.lower()
        if lower.endswith(".xls"):
            warn("Old .xls files cannot be read. Please open it in LibreOffice and save it")
            warn("as .ods (File > Save As), then type the path of the .ods file.")
            continue
        if not lower.endswith(SHEET_EXTENSIONS):
            warn("This is not a sheet file (.ods, .xlsx or .csv):  " + path)
            continue
        folder, name = os.path.split(path)
        if os.path.exists(os.path.join(folder, ".~lock." + name + "#")):
            say("  Note: this sheet seems to be open in LibreOffice. Changes that are not")
            say("  saved yet are not seen; save it (Ctrl+S) first if you changed it.")
        try:
            sheets = read_workbook(path)
        except SheetError as err:
            warn(str(err) + "  " + path)
            continue
        tables = [table for table in (find_table(sheet, cells) for sheet, cells in sheets)
                  if table is not None]
        if not tables:
            warn("No energies were found in this file:  " + path)
            if looks_like_soc_pp(sheets):
                warn("It looks like a k ISC sheet (like SOC-PP.ods), not the sheet with")
                warn("the energies of every geometry.")
            warn("The energies sheet needs a row of column names (S0, S1 ... T4 or")
            warn("S0+S1 ...) with one row per geometry below it (g1.log or g1 ...).")
            continue
        if len(tables) > 1:
            choice = ask_choice("  Energies were found in more than one sheet. Which one?",
                                ["'{0}' ({1} geometries)".format(t.sheet, len(t.geometries))
                                 for t in tables])
            table = tables[choice]
        else:
            table = tables[0]
        show_table(path, table)
        return path, table


# ---------------------------------------------------------------------------
# Which transitions
# ---------------------------------------------------------------------------
def parse_transitions(text):
    """Returns ([(singlet, triplet), ...], notes) or raises ValueError(message)."""
    tokens = []
    leftover = list(text)
    for match in re.finditer(r"([sStT])\s*0*(\d+)", text):
        tokens.append(match.group(1).upper() + str(int(match.group(2))))
        for i in range(match.start(), match.end()):
            leftover[i] = " "
    rest = re.sub(r"(?i)\b(to|and)\b", " ", "".join(leftover))
    strange = re.sub(r"[\s,;/\-\u2013\u2014>|:&+()=_.]", "", rest)
    if strange:
        raise ValueError("Could not understand '{0}'.".format(strange))
    if not tokens:
        raise ValueError("Please type at least one pair, for example  S1 T2")
    if len(tokens) % 2:
        raise ValueError("{0} states were typed ({1}); they must come in pairs.".format(
            len(tokens), " ".join(tokens)))
    pairs, notes = [], []
    for first, second in zip(tokens[0::2], tokens[1::2]):
        if "T0" in (first, second):
            raise ValueError("There is no T0 (triplets start at T1).")
        if first[0] == second[0]:
            raise ValueError("{0} {1} is not a singlet-triplet pair (one S and one T are "
                             "needed).".format(first, second))
        pair = (first, second) if first[0] == "S" else (second, first)
        if first[0] == "T":
            notes.append("{0} {1} is read as {2}-{3}".format(first, second, pair[0], pair[1]))
        if pair in pairs:
            notes.append("{0}-{1} was typed twice; it is used once".format(*pair))
            continue
        pairs.append(pair)
    return pairs, notes


def ask_for_transitions(table):
    """Returns (pairs, plain_states): plain_states are used without S0 (agreed by the user)."""
    say("")
    say(LINE)
    say("2. Which transitions?")
    say("  Type them as pairs, singlet first. For example")
    say("      S1 T2 S2 T3 S3 T4     means   S1-T2, S2-T3 and S3-T4")
    say("  (commas or dashes are fine too:  S1-T2, S2-T3, S3-T4 )")
    say("  The rows of every geometry come in the order you type.")
    say("  In this sheet: " + ", ".join(table.available()))
    say(LINE)
    while True:
        raw = ask("Transitions: ")
        if not raw.strip():
            warn("Please type the transitions (or press Ctrl+C to stop).")
            continue
        try:
            pairs, notes = parse_transitions(raw)
        except ValueError as err:
            warn(str(err))
            warn("Type for example:  S1 T2 S2 T3 S3 T4")
            continue
        states = sorted(set(state for pair in pairs for state in pair), key=state_sort_key)
        missing = [s for s in states if not table.can_add_s0(s) and not table.plain_only(s)]
        if missing:
            warn("Not in the energies sheet: {0}.".format(", ".join(missing)))
            warn("This sheet has: {0}.".format(", ".join(table.available())))
            continue
        plain = [s for s in states if table.plain_only(s)]
        for note in notes:
            say("  Note: " + note + ".")
        say("  Read as:  " + ", ".join("{0}-{1}".format(s, t) for s, t in pairs))
        if plain:
            say("")
            warn("The sheet has no S0 column, so S0 cannot be added to: {0}.".format(
                ", ".join(plain)))
            say("  The plain energies could be used instead. E(S-T) and K ISC come out")
            say("  the same (S0 cancels in E = S - T); only the S and T columns differ.")
            if not ask_yes_no("  Use the plain energies for {0}?".format(", ".join(plain))):
                say("  Then please add an S0 column (or S0+ columns) to the sheet, or")
                say("  choose other transitions.")
                continue
        if ask_yes_no("  Is this right?"):
            return pairs, plain


# ---------------------------------------------------------------------------
# Names that are in more than one column (for example two columns called S1)
# ---------------------------------------------------------------------------
ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth")


def label_name(label):
    """'S1' for ('state', 'S1'), 'S0+S1' for ('sum', 'S1')."""
    return ("S0+" if label[0] == "sum" else "") + label[1]


def sorted_labels(labels):
    """(label, columns) sorted: S0, S1 ... T4 first, then S0+S1 ... S0+T4."""
    return sorted(labels.items(), key=lambda item: (item[0][0] == "sum", state_sort_key(item[0][1])))


def column_preview(table, col):
    """'H 'S1':  4.0749   4.0613   4.0475  ...  (41 of 41 filled)'"""
    keys = natural_sorted(table.geometries)
    shown = "  ".join("{0:>9}".format(fmt_ev(table.number(col, key))) for key in keys[:3])
    filled = sum(1 for key in keys if table.number(col, key) is not None)
    return "column {0:<3} '{1}':  {2}  ({3} of {4} filled)".format(
        column_letter(col), table.headers.get(col, ""), shown, filled, len(keys))


def holds_s0_added(table, plain_col, other_col, s0_col):
    """True if other_col = S0 + plain_col for every geometry (and S0 is not always 0)."""
    compared, s0_not_zero = 0, False
    for key in table.geometries:
        x, y, s0 = (table.number(plain_col, key), table.number(other_col, key),
                    table.number(s0_col, key))
        if x is None or y is None or s0 is None:
            continue
        if abs(y - (s0 + x)) > SUM_TOLERANCE:
            return False
        compared += 1
        if abs(s0) > SUM_TOLERANCE:
            s0_not_zero = True
    return compared > 0 and s0_not_zero


def same_column_numbers(table, cols):
    for key in table.geometries:
        if len(set(table.number(col, key) for col in cols)) > 1:
            return False
    return True


def ask_which_column(table, label, chosen):
    cols = table.ambiguous[label]
    choice = ask_choice("  Which column is {0}?".format(label_name(label)),
                        [column_preview(table, col) for col in cols])
    table.column_label(label, cols[choice])
    chosen.setdefault(label[1], set()).add(label[0])


def settle_duplicates(table, states):
    """
    For the needed names that are in more than one column with different
    numbers, decide which column to use: a column named T4 that holds S0 + T4
    is recognised by itself; for the rest the user is asked. Changes table.
    Returns {state: {'state' and/or 'sum'}}: the kind of column chosen here.
    """
    chosen = {}
    needed = [("state", "S0")] + [(kind, state) for state in states if state != "S0"
                                  for kind in ("state", "sum")]
    if not any(label in table.ambiguous for label in needed):
        return chosen
    say("")
    say("  Some names are in more than one column of the sheet, with different numbers.")
    shown_from = short_list([table.geometries[key][0] for key in natural_sorted(table.geometries)][:3])
    if ("state", "S0") in table.ambiguous:                 # S0 first: it is needed below
        say("  (the numbers shown are those of {0})".format(shown_from))
        ask_which_column(table, ("state", "S0"), chosen)
    s0_col = table.state_columns.get("S0")
    for label in needed[1:]:
        if label not in table.ambiguous or label[0] != "state" or s0_col is None:
            continue
        cols = table.ambiguous[label]
        added = [col for col in cols
                 if any(holds_s0_added(table, other, col, s0_col) for other in cols if other != col)]
        plain = [col for col in cols if col not in added]
        if added and len(plain) == 1 and same_column_numbers(table, added):
            state = label[1]
            say("  Column {0} '{1}' holds S0 + {1} (checked for every geometry), so column {2}"
                .format(column_letter(added[0]), state, column_letter(plain[0])))
            say("  is used as {0} (and S0 is added to it as usual).".format(state))
            table.column_label(label, plain[0])
            chosen.setdefault(state, set()).add("state")
            if state not in table.sum_columns:
                table.sum_columns[state] = added[0]
    left = [label for label in needed if label in table.ambiguous]
    if not left:
        return chosen
    say("  (the numbers shown are those of {0})".format(shown_from))
    if len(left) == 1:
        ask_which_column(table, left[0], chosen)
        return chosen
    for label in left:
        say("      {0}:".format(label_name(label)))
        for col in table.ambiguous[label]:
            say("          " + column_preview(table, col))
    sets = min(len(table.ambiguous[label]) for label in left)
    options = []
    for number in range(sets):
        options.append("the {0} column of each name:  {1}".format(
            ORDINALS[number] if number < len(ORDINALS) else "number {0}".format(number + 1),
            ", ".join(column_letter(table.ambiguous[label][number]) for label in left)))
    options.append("choose for each name separately")
    choice = ask_choice("  Which columns should be used?", options)
    for label in left:
        if choice < sets:
            table.column_label(label, table.ambiguous[label][choice])
            chosen.setdefault(label[1], set()).add(label[0])
        else:
            ask_which_column(table, label, chosen)
    return chosen


# ---------------------------------------------------------------------------
# The energies that go into the sheet (S0 added)
# ---------------------------------------------------------------------------
def fmt_ev(value):
    return "(empty)" if value is None else "{0:.6g}".format(value)


def resolve_energies(table, states, plain, chosen=None):
    """
    For every state: ({geometry key: energy or None}, description of where it
    comes from, short name such as 'S0 + T4'). May ask the user which numbers to use.
    chosen: {state: kinds of column picked when a name was in two columns}; if
    only the plain column (or only the S0+ column) was picked, that one is
    followed without asking again.
    """
    chosen = chosen or {}
    result = OrderedDict()
    s0_col = table.state_columns.get("S0")
    if s0_col is not None:
        big = [key for key in table.geometries
               if table.number(s0_col, key) is not None and abs(table.number(s0_col, key)) > S0_LIMIT]
        if big:
            say("")
            warn("Some S0 values in column {0} are bigger than {1} (for example {2}: {3}).".format(
                column_letter(s0_col), S0_LIMIT, table.geometries[big[0]][0],
                fmt_ev(table.number(s0_col, big[0]))))
            warn("They look like Hartree, not eV. S0 + S1 would then mix units.")
            if not ask_yes_no("  Use them anyway?"):
                raise UserQuit()
    for state in states:
        values = OrderedDict()
        if state == "S0":
            for key in table.geometries:
                values[key] = table.number(s0_col, key)
            result[state] = (values, "S0  (column {0})".format(column_letter(s0_col)), "S0")
            continue
        if state in plain:
            col = table.state_columns[state]
            for key in table.geometries:
                values[key] = table.number(col, key)
            result[state] = (values, "{0} without S0  (column {1}; the sheet has no S0)".format(
                state, column_letter(col)), state)
            continue
        short = "S0 + " + state
        sum_col = table.sum_columns.get(state)
        part_col = table.state_columns.get(state) if s0_col is not None else None
        from_sum, from_parts = OrderedDict(), OrderedDict()
        for key in table.geometries:
            from_sum[key] = table.number(sum_col, key) if sum_col is not None else None
            s0 = table.number(s0_col, key) if part_col is not None else None
            x = table.number(part_col, key) if part_col is not None else None
            from_parts[key] = (s0 + x) if (s0 is not None and x is not None) else None
        parts_text = "S0 + {0}  (columns {1} + {2})".format(
            state, column_letter(s0_col) if s0_col is not None else "?",
            column_letter(part_col) if part_col is not None else "?")
        sum_text = "column {0} '{1}'".format(
            column_letter(sum_col) if sum_col is not None else "?",
            table.headers.get(sum_col, "S0+" + state))
        if sum_col is not None and part_col is not None:
            differ = [key for key in natural_sorted(table.geometries)
                      if from_sum[key] is not None and from_parts[key] is not None
                      and abs(from_sum[key] - from_parts[key]) > SUM_TOLERANCE]
            follow = chosen.get(state, set())
            if differ and len(follow) == 1:
                kind = list(follow)[0]
                say("")
                say("  Note: {0} is not S0 + {1} for {2} geometr{3}.".format(
                    sum_text, state, len(differ), "y" if len(differ) == 1 else "ies"))
                say("  Column {0} is used for {1} (see above), so {2} is used.".format(
                    column_letter(part_col if kind == "state" else sum_col),
                    state if kind == "state" else "S0+" + state,
                    parts_text if kind == "state" else sum_text))
                result[state] = ((from_parts if kind == "state" else from_sum),
                                 (parts_text if kind == "state" else sum_text), short)
                continue
            if differ:
                say("")
                warn("In the sheet, {0} is not equal to S0 + {1} for {2} geometr{3}:".format(
                    sum_text, state, len(differ), "y" if len(differ) == 1 else "ies"))
                for key in differ[:5]:
                    say("      {0:<10} {1} = {2:<10}  but  S0 + {3} = {4} + {5} = {6}".format(
                        table.geometries[key][0], "S0+" + state, fmt_ev(from_sum[key]), state,
                        fmt_ev(table.number(s0_col, key)), fmt_ev(table.number(part_col, key)),
                        fmt_ev(from_parts[key])))
                if len(differ) > 5:
                    say("      ... and {0} more".format(len(differ) - 5))
                choice = ask_choice("  Which numbers should go under {0}?".format(state), [
                    "S0 + {0}, added from the S0 and {0} columns (recommended)".format(state),
                    "the '{0}' column as it is in the sheet".format(
                        table.headers.get(sum_col, "S0+" + state)),
                    "Stop (nothing is written)"])
                if choice == 2:
                    raise UserQuit()
                if choice == 0:
                    result[state] = (from_parts, parts_text, short)
                else:
                    result[state] = (from_sum, sum_text, short)
                continue
            merged = OrderedDict((key, from_sum[key] if from_sum[key] is not None
                                  else from_parts[key]) for key in table.geometries)
            result[state] = (merged, sum_text + "  (= S0 + {0}, checked)".format(state), short)
        elif sum_col is not None:
            result[state] = (from_sum, sum_text, short)
        else:
            result[state] = (from_parts, parts_text, short)
    return result


# ---------------------------------------------------------------------------
# Finding soc_singlet and its sub-folders (the same as in the other programs)
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
        say("  This is the '{0}' folder. The SOC values are in soc_singlet, so".format(name))
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
    say("3. Where is the 'soc_singlet' folder?")
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
            warn("Please type another path.")
            continue
        say("  OK, soc_singlet folder:  " + soc_dir)
        say("  {0} sub-folder(s) found:".format(len(subs) + len(links)))
        show_wrapped(natural_sorted(subs + links))
        if others:
            say("  ({0} other item(s) in soc_singlet are not g*.com sub-folders and are ignored.)"
                .format(others))
        return soc_dir, subs, links


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


# ---------------------------------------------------------------------------
# soc_out.dat
# ---------------------------------------------------------------------------
# <S(1)|Hso|T(2),1,0,-1>  (PySOC 2016)  or  <S1|Hso|T2,1,0,-1>  (older soc_td)
SOC_LINE = re.compile(r"<\s*([ST])\s*\(?\s*(\d+)\s*\)?\s*\|\s*H\s*so\s*\|\s*([ST])\s*\(?\s*(\d+)\s*\)?",
                      re.IGNORECASE)


def read_soc_out(path):
    """
    {(singlet number, triplet number): [(value or None, problem or None, line), ...]}
    for every <S|Hso|T> line of soc_out.dat. None if the file cannot be read.
    """
    text = read_text(path)
    if text is None:
        return None
    found = {}
    for line in text.splitlines():
        match = SOC_LINE.search(line)
        if not match:
            continue
        a, a_number = match.group(1).upper(), int(match.group(2))
        b, b_number = match.group(3).upper(), int(match.group(4))
        if a == b:
            continue
        key = (a_number, b_number) if a == "S" else (b_number, a_number)
        rest = line[match.end():]
        close = rest.find(">")
        if close >= 0:
            rest = rest[close + 1:]
        rest = re.sub(r"^\s*\(\s*cm\s*-?\s*1\s*\)", "", rest, flags=re.IGNORECASE)
        words = rest.lstrip(" \t:").split()
        if not words:
            value, problem = None, "no number after it"
        else:
            value = to_float(words[0])
            problem = None if value is not None else "the number is '{0}'".format(words[0])
        found.setdefault(key, []).append((value, problem, line.strip()))
    return found


def pair_name(pair):
    return "{0}-{1}".format(pair[0], pair[1])


def soc_value(found, pair):
    """(value, None) or (None, problem) for one transition from read_soc_out()."""
    key = (int(pair[0][1:]), int(pair[1][1:]))
    entries = found.get(key)
    if not entries:
        return None, "{0}: no <{1}|Hso|{2}> line".format(pair_name(pair), pair[0], pair[1])
    for value, problem, _ in entries:
        if problem:
            return None, "{0}: {1}".format(pair_name(pair), problem)
    values = sorted(set(value for value, _, _ in entries))
    if len(values) > 1:
        return None, "{0}: {1} lines with different numbers ({2})".format(
            pair_name(pair), len(entries), ", ".join("{0:g}".format(v) for v in values))
    return values[0], None


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------
class Block(object):
    """One geometry: its label and one row per transition."""

    def __init__(self, key, label):
        self.key = key
        self.label = label
        self.rows = []      # [(pair, singlet energy, triplet energy, SOC in cm-1)]


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def collect(table, energies, pairs, soc_dir, folders):
    """
    Returns (blocks, problems, example, older). problems: [(geometry, [reasons])];
    older: sub-folders whose soc_out.dat is older than their gaussian.log.
    """
    by_key = OrderedDict()
    for name in natural_sorted(folders):
        by_key.setdefault(folder_key(name), []).append(name)
    keys = natural_sorted(set(by_key) | set(table.geometries))
    blocks, problems, older = [], [], []
    example = None
    for key in keys:
        reasons = []
        names = by_key.get(key, [])
        label = os.path.splitext(names[0])[0] if names and names[0].lower().endswith(
            SUBFOLDER_EXTENSION) else (names[0] if names else table.geometries[key][0])
        if key not in table.geometries:
            reasons.append("not in the energies sheet")
        elif key in table.duplicates:
            reasons.append("more than once in the energies sheet, with different numbers")
        if not names:
            reasons.append("no sub-folder in soc_singlet")
        elif len(names) > 1:
            reasons.append("{0} sub-folders for it in soc_singlet ({1})".format(
                len(names), ", ".join(names)))
        found = None
        if len(names) == 1:
            path = os.path.join(soc_dir, names[0], SOC_OUT)
            if not os.path.isfile(path):
                reasons.append("no {0} in {1}".format(SOC_OUT, names[0]))
            else:
                found = read_soc_out(path)
                if found is None:
                    reasons.append("{0} in {1} cannot be read".format(SOC_OUT, names[0]))
                log_time = mtime(os.path.join(soc_dir, names[0], "gaussian.log"))
                out_time = mtime(path)
                if log_time is not None and out_time is not None and out_time < log_time:
                    older.append(names[0])
        block = Block(key, label)
        for pair in pairs:
            soc = None
            if found is not None:
                soc, problem = soc_value(found, pair)
                if problem:
                    reasons.append(problem + " in {0}/{1}".format(names[0], SOC_OUT))
                elif example is None:
                    example = (names[0], found[(int(pair[0][1:]), int(pair[1][1:]))][0][2])
            energy = []
            for state in pair:
                value = energies[state][0].get(key) if key in table.geometries else None
                if value is None and key in table.geometries:
                    reason = "no {0} in the sheet (empty, or not a number)".format(energies[state][2])
                    if reason not in reasons:
                        reasons.append(reason)
                energy.append(value)
            block.rows.append((pair, energy[0], energy[1], soc))
        if reasons:
            problems.append((names[0] if len(names) == 1 else label, reasons))
        else:
            blocks.append(block)
    return blocks, problems, example, older


# ---------------------------------------------------------------------------
# Writing soc_plot.ods
# ---------------------------------------------------------------------------
def row_results(singlet, triplet, soc):
    """Every number of one row, computed exactly like the formulas of SOC-PP.ods."""
    c, d, f = singlet, triplet, soc
    h, i, j, k = PLANCK_H, LAMBDA, BOLTZMANN, float(TEMPERATURE)
    e = c - d
    g = f / 8065.73
    l_value = math.exp(-(((e + i) ** 2) / (4 * i * j * k)))
    m = math.sqrt(4 * 3.1415 * i * 0.02585)
    n = l_value / m
    o = (4 * 3.1415 * 3.1415 * n * g * g) / h
    return OrderedDict([("C", c), ("D", d), ("E", e), ("F", f), ("G", g), ("H", h),
                        ("I", i), ("J", j), ("K", TEMPERATURE), ("L", l_value), ("M", m),
                        ("N", n), ("O", o)])


def text_general(value):
    """How the 'General' number format shows a number (about 10 digits)."""
    if value == 0:
        return "0"
    if 1e-4 <= abs(value) < 1e10:
        text = "%.10g" % value
        if "e" not in text:
            return text
    mantissa, exponent = ("%.9E" % value).split("E")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    exponent = int(exponent)
    return "{0}E{1}{2:02d}".format(mantissa, "-" if exponent < 0 else "+", abs(exponent))


def text_fixed4(value):
    return "%.4f" % value


def text_scientific(value, exponent_digits):
    mantissa, exponent = ("%.2E" % value).split("E")
    exponent = int(exponent)
    return "{0}E{1}{2}".format(mantissa, "-" if exponent < 0 else "+",
                               str(abs(exponent)).zfill(exponent_digits))


# style and display of every cell of a value row
VALUE_CELLS = OrderedDict([
    ("C", ("ce2", text_general)), ("D", ("ce2", text_general)), ("E", ("ce3", text_fixed4)),
    ("F", ("ce2", text_general)), ("G", ("ce5", lambda v: text_scientific(v, 3))),
    ("H", ("ce6", lambda v: text_scientific(v, 3))), ("I", ("ce2", text_general)),
    ("J", ("ce6", lambda v: text_scientific(v, 3))), ("K", ("ce2", text_general)),
    ("L", ("ce1", text_general)), ("M", ("ce1", text_general)), ("N", ("ce1", text_general)),
    ("O", ("ce7", lambda v: text_scientific(v, 2))),
])

NAMESPACES = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
    'xmlns:number="urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0" '
    'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" '
    'xmlns:of="urn:oasis:names:tc:opendocument:xmlns:of:1.2" '
    'xmlns:calcext="urn:org:documentfoundation:names:experimental:calc:xmlns:calcext:1.0" '
    'xmlns:loext="urn:org:documentfoundation:names:experimental:office:xmlns:loext:1.0" '
    'xmlns:css3t="http://www.w3.org/TR/css3-text/" office:version="1.2"')

FONTS = ('<office:font-face-decls>'
         '<style:font-face style:name="Arial" svg:font-family="Arial"/>'
         '<style:font-face style:name="Liberation Sans" svg:font-family="&apos;Liberation Sans&apos;" '
         'style:font-family-generic="swiss" style:font-pitch="variable"/>'
         '</office:font-face-decls>')


def cell_style(name, data_style, align, size, bold):
    """A cell style of SOC-PP.ods (Arial, centred, black)."""
    weight = "bold" if bold else "normal"
    return (
        '<style:style style:name="{0}" style:family="table-cell" style:parent-style-name="Default"{1}>'
        '<style:table-cell-properties style:text-align-source="fix" style:repeat-content="false" '
        'fo:wrap-option="no-wrap" style:direction="ltr" style:rotation-angle="0" '
        'style:rotation-align="none" style:shrink-to-fit="false" style:vertical-align="bottom"/>'
        '<style:paragraph-properties fo:text-align="{2}" css3t:text-justify="auto" '
        'fo:margin-left="0pt"/>'
        '<style:text-properties fo:color="#000000" style:font-name="Arial" fo:font-size="{3}pt" '
        'fo:font-style="normal" fo:font-weight="{4}" style:font-size-asian="{3}pt" '
        'style:font-weight-asian="{4}" style:font-name-complex="Arial" '
        'style:font-size-complex="{3}pt" style:font-weight-complex="{4}"/>'
        '</style:style>').format(
            name, ' style:data-style-name="{0}"'.format(data_style) if data_style else "",
            align, size, weight)


def automatic_styles():
    parts = ['<office:automatic-styles>']
    for index, (letter, width) in enumerate(COLUMN_WIDTHS.items()):
        parts.append('<style:style style:name="co{0}" style:family="table-column">'
                     '<style:table-column-properties fo:break-before="auto" '
                     'style:column-width="{1}pt"/></style:style>'.format(index + 1, width))
    parts.append('<style:style style:name="ro1" style:family="table-row">'
                 '<style:table-row-properties style:row-height="12.76pt" fo:break-before="auto" '
                 'style:use-optimal-row-height="false"/></style:style>')
    parts.append('<style:style style:name="ta1" style:family="table" '
                 'style:master-page-name="Default"><style:table-properties table:display="true" '
                 'style:writing-mode="lr-tb"/></style:style>')
    # number formats: 0.0000, 0.00E+000 and 0.00E+00 (as in SOC-PP.ods)
    parts.append('<number:number-style style:name="N125"><number:number number:decimal-places="4" '
                 'loext:min-decimal-places="4" number:min-integer-digits="1"/></number:number-style>')
    parts.append('<number:number-style style:name="N60"><number:scientific-number '
                 'number:decimal-places="2" loext:min-decimal-places="2" '
                 'number:min-integer-digits="1" number:min-exponent-digits="3" '
                 'loext:exponent-interval="1" loext:forced-exponent-sign="true"/>'
                 '</number:number-style>')
    parts.append('<number:number-style style:name="N61"><number:scientific-number '
                 'number:decimal-places="2" loext:min-decimal-places="2" '
                 'number:min-integer-digits="1" number:min-exponent-digits="2" '
                 'loext:exponent-interval="1" loext:forced-exponent-sign="true"/>'
                 '</number:number-style>')
    parts.append(cell_style("ce1", None, "center", 10, False))
    parts.append(cell_style("ce2", None, "center", 10, True))
    parts.append(cell_style("ce3", "N125", "center", 10, True))
    parts.append(cell_style("ce5", "N60", "center", 10, False))
    parts.append(cell_style("ce6", "N60", "center", 10, True))
    parts.append(cell_style("ce7", "N61", "center", 10, True))
    parts.append('</office:automatic-styles>')
    return "".join(parts)


def number_text(value):
    """office:value of a number (exact: reads back as the very same number)."""
    if isinstance(value, int):
        return str(value)
    return repr(float(value))


def xml_cell_text(style, text):
    return ('<table:table-cell table:style-name="{0}" office:value-type="string" '
            'calcext:value-type="string"><text:p>{1}</text:p></table:table-cell>').format(
                style, escape(text))


def xml_cell_number(style, value, shown, formula=None):
    return ('<table:table-cell table:style-name="{0}"{1} office:value-type="float" '
            'office:value="{2}" calcext:value-type="float"><text:p>{3}</text:p>'
            '</table:table-cell>').format(
                style, ' table:formula="{0}"'.format(escape(formula, {'"': "&quot;"}))
                if formula else "", number_text(value), escape(shown))


def build_sheet(blocks, pairs):
    """
    Returns (content.xml text, expected) where expected is
    {(row, column letter): (number or None, text or None, formula or None)},
    rows counted from 1 as in the sheet.
    """
    expected = {}
    rows_xml = []

    def add_row(cells):
        row_number = len(rows_xml) + 1
        xml = []
        for letter in COLUMNS:
            cell = cells.get(letter)
            if cell is None:
                xml.append("<table:table-cell/>")
                continue
            kind = cell[0]
            if kind == "text":
                _, style, text = cell
                xml.append(xml_cell_text(style, text))
                expected[(row_number, letter)] = (None, text, None)
            else:
                _, style, value, shown, formula = cell
                xml.append(xml_cell_number(style, value, shown, formula))
                expected[(row_number, letter)] = (value, None, formula)
        rows_xml.append('<table:table-row table:style-name="ro1">{0}</table:table-row>'.format(
            "".join(xml)))
        return row_number

    for block_index, block in enumerate(blocks):
        if block_index:
            add_row({})                                   # empty row between geometries
        add_row({"B": ("text", "ce1", block.label)})
        for row_index, (pair, singlet, triplet, soc) in enumerate(block.rows):
            header = {"C": ("text", "ce2", pair[0]), "D": ("text", "ce2", pair[1])}
            if block_index == 0 and row_index == 0:       # column titles, as in SOC-PP.ods
                for letter, title in TITLES.items():
                    header[letter] = ("text", "ce2", title)
            add_row(header)
            row_number = len(rows_xml) + 1
            values = row_results(singlet, triplet, soc)
            cells = {}
            for letter, (style, shown) in VALUE_CELLS.items():
                formula = FORMULAS[letter].format(r=row_number) if letter in FORMULAS else None
                cells[letter] = ("number", style, values[letter], shown(values[letter]), formula)
            add_row(cells)

    columns_xml = "".join(
        '<table:table-column table:style-name="co{0}" table:default-cell-style-name="Default"/>'
        .format(index + 1) for index in range(len(COLUMN_WIDTHS)))
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<office:document-content {0}><office:scripts/>{1}{2}'
        '<office:body><office:spreadsheet>'
        '<table:table table:name="Sheet1" table:style-name="ta1">{3}{4}</table:table>'
        '</office:spreadsheet></office:body></office:document-content>').format(
            NAMESPACES, FONTS, automatic_styles(), columns_xml, "".join(rows_xml))
    return content, expected


def styles_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<office:document-styles {0}>{1}<office:styles>'
        '<style:default-style style:family="table-cell">'
        '<style:paragraph-properties style:tab-stop-distance="36pt"/>'
        '<style:text-properties style:font-name="Liberation Sans" fo:language="en" '
        'fo:country="US"/></style:default-style>'
        '<style:style style:name="Default" style:family="table-cell">'
        '<style:table-cell-properties style:rotation-align="none" style:vertical-align="bottom"/>'
        '<style:text-properties fo:color="#000000" style:font-name="Arial" fo:font-family="Arial" '
        'style:font-name-complex="Arial" style:font-family-complex="Arial"/></style:style>'
        '</office:styles><office:automatic-styles>'
        '<style:page-layout style:name="pm1"><style:page-layout-properties '
        'style:writing-mode="lr-tb"/></style:page-layout></office:automatic-styles>'
        '<office:master-styles><style:master-page style:name="Default" '
        'style:page-layout-name="pm1"/></office:master-styles>'
        '</office:document-styles>').format(NAMESPACES, FONTS)


def meta_xml():
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<office:document-meta {0}><office:meta>'
            '<meta:generator>soc_plot.py (Creation-of-soc)</meta:generator>'
            '</office:meta></office:document-meta>').format(NAMESPACES)


MANIFEST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" '
    'manifest:version="1.2">\n'
    ' <manifest:file-entry manifest:full-path="/" manifest:version="1.2" '
    'manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>\n'
    ' <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>\n'
    ' <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>\n'
    ' <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>\n'
    '</manifest:manifest>\n')


def ods_bytes(content):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        stored = zipfile.ZipInfo("mimetype", date_time=(2026, 1, 1, 0, 0, 0))
        stored.compress_type = zipfile.ZIP_STORED
        package.writestr(stored, "application/vnd.oasis.opendocument.spreadsheet")
        for name, text in (("content.xml", content), ("styles.xml", styles_xml()),
                           ("meta.xml", meta_xml()), ("META-INF/manifest.xml", MANIFEST)):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


def check_written(path, expected):
    """Read the written file back; return a list of what is wrong (empty if all is right)."""
    errors = []
    try:
        with zipfile.ZipFile(path) as package:
            names = package.namelist()
            if not names or names[0] != "mimetype" or \
                    package.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                errors.append("the file does not start like an .ods file")
            if package.testzip() is not None:
                errors.append("the file is damaged")
            for name in ("styles.xml", "meta.xml", "META-INF/manifest.xml"):
                ET.fromstring(package.read(name))
            sheets = read_odf_xml(package.read("content.xml"))
    except Exception as err:   # anything at all means the file is not right
        return ["the file cannot be read back ({0})".format(err)]
    if len(sheets) != 1:
        return ["the file has {0} sheets instead of 1".format(len(sheets))]
    cells = sheets[0][1]
    seen = set()
    for (row, col), (number, text, formula) in cells.items():
        where = (row + 1, column_letter(col))
        seen.add(where)
        want = expected.get(where)
        if want is None:
            errors.append("unexpected cell {0}{1}".format(where[1], where[0]))
            continue
        want_number, want_text, want_formula = want
        if want_number is not None and number != want_number:
            errors.append("{0}{1} is {2}, not {3}".format(where[1], where[0], number, want_number))
        if want_text is not None and text != want_text:
            errors.append("{0}{1} says '{2}', not '{3}'".format(where[1], where[0], text, want_text))
        if formula != want_formula:
            errors.append("{0}{1} has the formula {2}, not {3}".format(
                where[1], where[0], formula, want_formula))
    for where in expected:
        if where not in seen:
            errors.append("cell {0}{1} is missing".format(where[1], where[0]))
    return errors


def free_old_name(folder):
    number = 1
    while True:
        name = "{0}_old{1}{2}".format(OUTPUT_STEM, number, OUTPUT_EXTENSION)
        if not os.path.lexists(os.path.join(folder, name)):
            return name
        number += 1


def write_output(folder, data, expected):
    """Write soc_plot.ods safely. Returns (path, name the old file was kept as, or None)."""
    final = os.path.join(folder, OUTPUT_STEM + OUTPUT_EXTENSION)
    temporary = os.path.join(folder, ".{0}{1}.part{2}".format(
        OUTPUT_STEM, OUTPUT_EXTENSION, os.getpid()))
    kept = None
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        errors = check_written(temporary, expected)
        if errors:
            raise IOError("the new file did not read back correctly: " + "; ".join(errors[:3]))
        if os.path.lexists(final):
            kept = free_old_name(folder)
            os.rename(final, os.path.join(folder, kept))
        os.rename(temporary, final)
    finally:
        if os.path.lexists(temporary):
            try:
                os.remove(temporary)       # only our own unfinished temporary file
            except OSError:
                pass
    errors = check_written(final, expected)
    if errors:
        raise IOError("soc_plot.ods did not read back correctly: " + "; ".join(errors[:3]))
    return final, kept


def folder_is_writable(folder):
    return os.path.isdir(folder) and os.access(folder, os.W_OK | os.X_OK)


def can_make_folder(folder):
    """True if folder does not exist yet but can be made (its nearest existing parent is writable)."""
    parent = folder
    while not os.path.exists(parent):
        up = os.path.dirname(parent)
        if up == parent:
            return False
        parent = up
    return folder_is_writable(parent)


def ask_for_output_folder(default):
    """Returns (folder for soc_plot.ods, True if that folder must still be made)."""
    name = OUTPUT_STEM + OUTPUT_EXTENSION
    say("")
    say(LINE)
    say("4. Where should {0} be saved?".format(name))
    say("  Type the folder (Tab completes names). A new folder is made if needed.")
    say("  Or just press Enter to save it next to the energies sheet:")
    say("      " + default)
    say(LINE)
    while True:
        raw = ask("Folder for {0}: ".format(name))
        if not raw.strip():
            folder = default
        elif re.match(r"^\s*['\"]?https?://", raw):
            warn("This is a web link. Please type a folder on this computer; to put the sheet")
            warn("on Google Drive, upload {0} there afterwards.".format(name))
            continue
        else:
            found, guess, suggestions = find_path(raw)
            folder = found or guess
            if found is None and suggestions:
                warn("Folder not found:  " + guess)
                picked = pick_suggestion(suggestions)
                if picked is not None:
                    folder = picked
            if folder.lower().endswith(OUTPUT_EXTENSION) and not os.path.isdir(folder):
                say("  This is a file name; the sheet is always called {0}, so it is".format(name))
                say("  saved in the folder of that name:  " + os.path.dirname(folder))
                folder = os.path.dirname(folder)
            elif os.path.isfile(folder):
                warn("This is a file, not a folder:  " + folder)
                continue
        folder = os.path.abspath(folder)
        if os.path.isdir(folder):
            if not folder_is_writable(folder):
                warn("You cannot write in this folder:  " + folder)
                warn("Please type another folder.")
                continue
            say("  OK, {0} will be saved in:  {1}".format(name, folder))
            return folder, False
        if os.path.exists(folder):
            warn("This is not a folder:  " + folder)
            continue
        if not can_make_folder(folder):
            warn("This folder does not exist and cannot be made here:  " + folder)
            continue
        say("  This folder does not exist yet:  " + folder)
        if ask_yes_no("  Make it (only after you confirm the summary)?"):
            return folder, True


# ---------------------------------------------------------------------------
# Summary and main program
# ---------------------------------------------------------------------------
def show_soc_table(blocks, pairs):
    for start in range(0, len(pairs), 5):
        chunk = pairs[start:start + 5]
        say("      {0:<12}".format("geometry") + "".join(
            "{0:>13}".format(pair_name(pair)) for pair in chunk))
        for block in blocks:
            values = [row[3] for row in block.rows[start:start + 5]]
            say("      {0:<12}".format(block.label) + "".join(
                "{0:>13.5f}".format(value) for value in values))
        say("")


def show_summary(sheet_path, table, soc_dir, pairs, energies, blocks, problems, example,
                 older, output_folder, new_folder):
    say("")
    say(LINE)
    say("SUMMARY")
    say("  Energies sheet : {0}  (sheet '{1}')".format(sheet_path, table.sheet))
    say("  soc_singlet    : " + soc_dir)
    say("  Transitions    : {0}  (this order in every geometry)".format(
        ", ".join(pair_name(pair) for pair in pairs)))
    say("  What goes under each label (energies in eV):")
    for state, (_, description, _) in energies.items():
        say("      under {0:<4}:  {1}".format(state, description))
    if example:
        say("  SOC (cm-1): the first number after '(cm-1):' in soc_out.dat, for example")
        say("      {0}:  {1}".format(example[0], example[1]))
    say("  Constants (as in SOC-PP.ods): h = 4.136E-15, lam = 0.2, kB = 8.6173E-05, T = 300")
    if blocks:
        first = blocks[0]
        say("  {0} as it goes into the sheet:".format(first.label))
        for pair, singlet, triplet, soc in first.rows:
            say("      {0:<7} {1} = {2:<10}  {3} = {4:<10}  SOC = {5:.5f} cm-1".format(
                pair_name(pair), pair[0], fmt_ev(singlet), pair[1], fmt_ev(triplet), soc))
        say("")
        say("  SOC (cm-1) from soc_out.dat:")
        show_soc_table(blocks, pairs)
    if older:
        say("  Note: in {0} sub-folder(s) soc_out.dat is OLDER than gaussian.log, so it may".format(
            len(older)))
        say("  be from before Gaussian was run again (run_init.py would run PySOC there")
        say("  again):")
        show_wrapped(older)
    if problems:
        warn("{0} geometr{1} cannot be used and will be LEFT OUT:".format(
            len(problems), "y" if len(problems) == 1 else "ies"))
        for name, reasons in problems:
            say("      {0}:  {1}".format(name, reasons[0]))
            for reason in reasons[1:]:
                say("      {0}   {1}".format(" " * len(name), reason))
    say("  Geometries in soc_plot.ods : {0}  ({1})".format(
        len(blocks), short_list(block.label for block in blocks) if blocks else "none"))
    final = os.path.join(output_folder, OUTPUT_STEM + OUTPUT_EXTENSION)
    say("  Will write                 : " + final)
    if new_folder:
        say("  (the folder {0} does not exist yet; it will be made)".format(output_folder))
    elif os.path.lexists(final):
        say("  ({0} is already there; it will be kept as {1})".format(
            OUTPUT_STEM + OUTPUT_EXTENSION, free_old_name(output_folder)))
    say(LINE)


def wait_until_closed(folder):
    lock = os.path.join(folder, ".~lock." + OUTPUT_STEM + OUTPUT_EXTENSION + "#")
    while os.path.exists(lock):
        warn("{0} seems to be open in LibreOffice. Please close it first.".format(
            OUTPUT_STEM + OUTPUT_EXTENSION))
        if ask_yes_no("  Is it closed now?") and os.path.exists(lock):
            say("  LibreOffice's lock file is still there (it can be left over after a")
            say("  crash). Going on: the old file is kept as it is anyway.")
            return


def main():
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        say(__doc__)
        return 0

    say(LINE)
    say("  SOC PLOT: makes soc_plot.ods (the layout of SOC-PP.ods) for every geometry:")
    say("  S0+S and S0+T from the energies sheet, SOC from soc_out.dat, then the")
    say("  same constants and formulas, up to K ISC.")
    say("  Nothing is written until you type y. Press Ctrl+C at any time to stop.")
    say(LINE)
    if sys.argv[1:]:
        say("  Note: the program asks for the paths itself; the words typed after")
        say("  the command are ignored.")
    enable_tab_completion()

    sheet_path, table = ask_for_sheet()
    pairs, plain = ask_for_transitions(table)
    states = sorted(set(state for pair in pairs for state in pair), key=state_sort_key)
    chosen = settle_duplicates(table, states)
    energies = resolve_energies(table, states, plain, chosen)
    soc_dir, subs, links = ask_for_soc_singlet()

    pid = running_pid(soc_dir, RUN_INIT_LOCK, "run_init")
    if pid is not None:
        say("")
        warn("run_init.py is still running PySOC in this soc_singlet (process {0}).".format(pid))
        warn("Sub-folders it has not reached yet have no new soc_out.dat.")
        if not ask_yes_no("  Go on anyway?"):
            say("  Nothing has been written.")
            return 0

    folder_keys = set(folder_key(name) for name in subs + links)
    if not folder_keys & set(table.geometries):
        say("")
        warn("None of the geometry names in the sheet matches a sub-folder of soc_singlet:")
        warn("    in the sheet   :  " + short_list(
            natural_sorted(table.geometries[key][0] for key in table.geometries)))
        warn("    in soc_singlet :  " + short_list(natural_sorted(subs + links)))
        warn("They are matched by name: g1.log (or g1) in the sheet goes with")
        warn("soc_singlet/g1.com. Nothing has been written.")
        return 1

    output_folder, new_folder = ask_for_output_folder(os.path.dirname(sheet_path))

    say("")
    say("  Reading {0} in {1} sub-folder(s) ...".format(SOC_OUT, len(subs) + len(links)))
    blocks, problems, example, older = collect(table, energies, pairs, soc_dir, subs + links)

    show_summary(sheet_path, table, soc_dir, pairs, energies, blocks, problems, example,
                 older, output_folder, new_folder)
    if not blocks:
        say("")
        warn("No geometry has everything that is needed, so there is nothing to write.")
        warn("Please fix the problems listed above and run the program again.")
        return 1

    content, expected = build_sheet(blocks, pairs)
    data = ods_bytes(content)
    say("")
    if problems:
        question = "Write {0} with these {1} geometries ({2} left out, listed above)?".format(
            OUTPUT_STEM + OUTPUT_EXTENSION, len(blocks), len(problems))
    else:
        question = "Write {0} with these {1} geometries?".format(
            OUTPUT_STEM + OUTPUT_EXTENSION, len(blocks))
    if not ask_yes_no(question):
        say("  Nothing has been written.")
        return 0
    if new_folder:
        try:
            os.makedirs(output_folder)
        except OSError as err:
            say("")
            warn("Could not make the folder {0}: {1}".format(
                output_folder, getattr(err, "strerror", None) or err))
            warn("Nothing has been written.")
            return 1
    wait_until_closed(output_folder)
    try:
        final, kept = write_output(output_folder, data, expected)
    except (IOError, OSError) as err:
        say("")
        warn("Could not write {0}: {1}".format(
            OUTPUT_STEM + OUTPUT_EXTENSION, getattr(err, "strerror", None) or err))
        warn("Nothing else was changed.")
        return 1
    say("")
    say(LINE)
    say("  Done. Written and checked cell by cell:")
    say("      " + final)
    if kept:
        say("  The earlier {0} is kept as {1}.".format(OUTPUT_STEM + OUTPUT_EXTENSION, kept))
    say("  {0} geometries x {1} transition(s); every result cell is a formula.".format(
        len(blocks), len(pairs)))
    say("  Open it in LibreOffice, or upload it to Google Drive (New > File upload);")
    say("  there it opens as a Google Sheet.")
    say(LINE)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, UserQuit):
        say("")
        say("")
        say("Stopped by you. Nothing has been written.")
        sys.exit(130)
