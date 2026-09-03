#!/usr/bin/env python3
r"""
Generate CV or cover-letter .tex files from structured JSON and LaTeX templates.

The template controls the layout, spacing, typography, section order,
header, and education section.

Text-bearing JSON fields are inserted as trusted LaTeX text. This allows
commands such as \textbf{}, \textit{}, \underline{}, and \href{} inside
those fields without requiring the rest of the JSON to contain LaTeX.

The generated .tex file can optionally be compiled to PDF using pdfLaTeX.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse


def normalize_unicode_text(text: str) -> str:
    """Normalize Unicode spacing characters that pdfLaTeX cannot process."""
    replacements = {
        "\u00a0": " ",  # non-breaking space
        "\u2007": " ",  # figure space
        "\u2009": " ",  # thin space
        "\u202f": " ",  # narrow no-break space
        "\ufeff": "",   # byte-order mark / zero-width no-break space
    }

    for source, replacement in replacements.items():
        text = text.replace(source, replacement)

    return text


def normalize_unicode(value):
    """Recursively normalize text in JSON-compatible values."""
    if isinstance(value, str):
        return normalize_unicode_text(value)

    if isinstance(value, list):
        return [normalize_unicode(item) for item in value]

    if isinstance(value, tuple):
        return tuple(normalize_unicode(item) for item in value)

    if isinstance(value, dict):
        return {
            key: normalize_unicode(item)
            for key, item in value.items()
        }

    return value

CV_PLACEHOLDERS = {
    "summary": "%%__SUMMARY__%%",
    "skills": "%%__SKILLS__%%",
    "projects": "%%__PROJECTS__%%",
    "work_experience": "%%__WORK_EXPERIENCE__%%",
    "awards": "%%__AWARDS__%%",
}


COVER_LETTER_PLACEHOLDERS = {
    "date": "%%__DATE__%%",
    "company_name": "%%__COMPANY_NAME__%%",
    "paragraph_1": "%%__PARAGRAPH_1__%%",
    "paragraph_2": "%%__PARAGRAPH_2__%%",
    "paragraph_3": "%%__PARAGRAPH_3__%%",
}


class CVGenerationError(ValueError):
    """Raised when the template, JSON data, or compilation is invalid."""


class TexCompiler(Protocol):
    """Interface for compiling a TeX file into another output format."""

    def compile(self, tex_path: Path) -> Path:
        """Compile the supplied TeX file and return the output path."""


@dataclass(frozen=True)
class PdfLatexCompiler:
    executable: str = "pdflatex"
    runs: int = 2
    interaction_mode: str = "nonstopmode"
    halt_on_error: bool = True
    keep_auxiliary_files: bool = False

    def compile(self, tex_path: Path) -> Path:
        tex_path = tex_path.resolve()

        if not tex_path.is_file():
            raise CVGenerationError(
                f"Cannot compile missing TeX file: {tex_path}"
            )

        executable_path = shutil.which(self.executable)

        if executable_path is None:
            raise CVGenerationError(
                f"Could not find {self.executable!r}. Install a LaTeX "
                "distribution containing pdfLaTeX and ensure it is available "
                "on PATH."
            )

        if self.runs < 1:
            raise CVGenerationError(
                "The number of pdfLaTeX compilation runs must be at least 1."
            )

        output_directory = tex_path.parent
        pdf_path = tex_path.with_suffix(".pdf")

        command = [
            executable_path,
            f"-interaction={self.interaction_mode}",
            f"-output-directory={output_directory}",
        ]

        if self.halt_on_error:
            command.append("-halt-on-error")

        command.append(tex_path.name)

        for run_number in range(1, self.runs + 1):
            result = subprocess.run(
                command,
                cwd=output_directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            if result.returncode != 0:
                log_path = tex_path.with_suffix(".log")

                details = [
                    f"pdfLaTeX failed on run {run_number}.",
                    f"Exit code: {result.returncode}.",
                ]

                if log_path.exists():
                    details.append(f"Compilation log: {log_path}")

                compiler_output = self._extract_relevant_output(
                    result.stdout,
                    result.stderr,
                )

                if compiler_output:
                    details.append(
                        "Compiler output:\n"
                        + compiler_output
                    )

                raise CVGenerationError("\n".join(details))

        if not pdf_path.is_file():
            raise CVGenerationError(
                f"pdfLaTeX completed without creating the expected PDF: "
                f"{pdf_path}"
            )

        if not self.keep_auxiliary_files:
            self._remove_auxiliary_files(tex_path)

        return pdf_path

    @staticmethod
    def _extract_relevant_output(
        stdout: str,
        stderr: str,
        max_lines: int = 30,
    ) -> str:
        combined = "\n".join(
            part.strip()
            for part in (stdout, stderr)
            if part.strip()
        )

        if not combined:
            return ""

        lines = combined.splitlines()
        return "\n".join(lines[-max_lines:])

    @staticmethod
    def _remove_auxiliary_files(tex_path: Path) -> None:
        auxiliary_suffixes = {
            ".aux",
            ".fls",
            ".fdb_latexmk",
            ".out",
            ".synctex.gz",
            ".toc",
        }

        for suffix in auxiliary_suffixes:
            auxiliary_path = tex_path.with_suffix(suffix)

            try:
                auxiliary_path.unlink(missing_ok=True)
            except OSError:
                # Failure to clean temporary files should not invalidate
                # an otherwise successful PDF compilation.
                pass


@dataclass(frozen=True)
class ContentItem:
    text: str
    bullet: bool = True


@dataclass(frozen=True)
class Entry:
    title: str = ""
    secondary: str = ""
    url: str = ""
    icon: str = ""
    organization: str = ""
    date: str = ""
    content: tuple[ContentItem, ...] = ()


@dataclass(frozen=True)
class CVData:
    summary: tuple[str, ...]
    skills: tuple[tuple[str, str], ...]
    projects: tuple[Entry, ...]
    work_experience: tuple[Entry, ...]
    awards: tuple[Entry, ...]


@dataclass(frozen=True)
class CoverLetterData:
    date: str
    company_name: str
    paragraphs: tuple[str, str, str]


@dataclass(frozen=True)
class GenerationResult:
    tex_path: Path
    pdf_path: Path | None = None


SAFE_LATEX_COMMANDS = {
    "emph", "textbf", "textit", "textnormal", "textrm", "textsf",
    "textsl", "textsc", "texttt", "underline", "mbox", "hbox",
    "href", "url", "nolinkurl", "email", "LaTeX", "TeX",
    "textsuperscript", "textsubscript", "small", "footnotesize",
    "scriptsize", "normalsize", "large", "Large", "LARGE",
    "today", "newline", "linebreak", "nobreakspace", "slash",
    "ldots", "dots", "copyright", "textcopyright", "pounds",
    "textregistered", "texttrademark", "textdegree", "textnumero",
    "textasciitilde", "textasciicircum", "textbackslash",
}

TEXT_VALUE_KEYS = {"text", "format"}
TEXT_FORMATS = {"auto", "plain", "latex"}

PLAIN_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "%": r"\%",
    "$": r"\$",
    "&": r"\&",
    "_": r"\_",
    "^": r"\textasciicircum{}",
    "#": r"\#",
    "~": r"\textasciitilde{}",
}

UNICODE_TO_LATEX = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "--",
    "\u2013": "--",
    "\u2014": "---",
    "\u2015": "---",
    "\u2212": "-",
    "\u2018": "`",
    "\u2019": "'",
    "\u201c": "``",
    "\u201d": "''",
    "\u2026": r"\ldots{}",
    "\u00b0": r"\textdegree{}",
    "\u00a9": r"\textcopyright{}",
    "\u00ae": r"\textregistered{}",
    "\u2122": r"\texttrademark{}",
}


def _escape_plain_latex(text: str) -> str:
    """Escape arbitrary plain text for insertion into a LaTeX argument."""
    output: list[str] = []
    for character in text:
        replacement = UNICODE_TO_LATEX.get(character)
        if replacement is not None:
            output.append(replacement)
        else:
            output.append(PLAIN_LATEX_ESCAPES.get(character, character))
    return "".join(output)


def _find_balanced_group(text: str, start: int, opener: str, closer: str) -> int | None:
    """Return the index after a balanced group, or None when unbalanced."""
    if start >= len(text) or text[start] != opener:
        return None

    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == opener:
            depth += 1
        elif character == closer:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _escape_url_for_latex(value: str) -> str:
    """Escape a validated URL for use as a LaTeX macro argument."""
    return "".join(
        {
            "%": r"\%",
            "#": r"\#",
            "&": r"\&",
            "_": r"\_",
            "{": r"\%7B",
            "}": r"\%7D",
            "\\": r"\%5C",
        }.get(character, character)
        for character in value
    )


def _render_safe_command(text: str, start: int) -> tuple[str, int] | None:
    """Render one allow-listed LaTeX command starting at a backslash."""
    command_match = re.match(r"\\([A-Za-z@]+|.)", text[start:])
    if command_match is None:
        return None

    command_name = command_match.group(1)
    command_end = start + command_match.end()

    if len(command_name) == 1 and command_name in "#$%&_{}~^\\":
        return text[start:command_end], command_end

    if command_name not in SAFE_LATEX_COMMANDS:
        return None

    rendered = [text[start:command_end]]
    index = command_end

    while index < len(text) and text[index].isspace() and text[index] != "\n":
        rendered.append(text[index])
        index += 1

    if index < len(text) and text[index] == "[":
        optional_end = _find_balanced_group(text, index, "[", "]")
        if optional_end is None:
            return None
        rendered.append(text[index:optional_end])
        index = optional_end

    argument_number = 0
    while index < len(text) and text[index] == "{":
        group_end = _find_balanced_group(text, index, "{", "}")
        if group_end is None:
            return None

        inner = text[index + 1:group_end - 1]
        if command_name in {"href", "url", "nolinkurl"} and argument_number == 0:
            rendered.append("{" + _escape_url_for_latex(inner) + "}")
        else:
            rendered.append("{" + _escape_auto_latex(inner) + "}")
        argument_number += 1
        index = group_end

    return "".join(rendered), index


def _escape_auto_latex(text: str) -> str:
    """Escape plain text while preserving a conservative LaTeX subset."""
    output: list[str] = []
    index = 0

    while index < len(text):
        character = text[index]

        if character == "\\":
            rendered_command = _render_safe_command(text, index)
            if rendered_command is not None:
                rendered, index = rendered_command
                output.append(rendered)
                continue

            output.append(r"\textbackslash{}")
            index += 1
            continue

        replacement = UNICODE_TO_LATEX.get(character)
        if replacement is not None:
            output.append(replacement)
        else:
            output.append(PLAIN_LATEX_ESCAPES.get(character, character))
        index += 1

    return "".join(output)


def _validate_raw_latex(text: str, field_name: str) -> None:
    """Reject obviously incomplete raw LaTeX before compilation."""
    stack: list[int] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == "%":
            newline = text.find("\n", index)
            if newline == -1:
                break
            index = newline + 1
            continue
        if character == "{":
            stack.append(index)
        elif character == "}":
            if not stack:
                raise CVGenerationError(
                    f"{field_name} contains an unmatched closing brace at character {index}."
                )
            stack.pop()
        index += 1

    if stack:
        raise CVGenerationError(
            f"{field_name} contains an unmatched opening brace at character {stack[-1]}."
        )


def latex_text(value: Any, field_name: str = "text") -> str:
    """
    Convert a JSON text value into safe LaTeX.

    A normal string uses auto mode: ordinary text is escaped while a
    conservative allow-list of common formatting commands is preserved.
    A value may instead be {"text": "...", "format": "plain"} to escape
    everything, or {"text": "...", "format": "latex"} for explicitly
    trusted raw LaTeX.
    """
    if value is None:
        return ""

    text_format = "auto"
    raw_value = value

    if isinstance(value, Mapping):
        reject_unknown_keys(value, TEXT_VALUE_KEYS, field_name)
        raw_value = value.get("text")
        text_format = value.get("format", "auto")
        if text_format not in TEXT_FORMATS:
            raise CVGenerationError(
                f"{field_name}.format must be one of: {', '.join(sorted(TEXT_FORMATS))}."
            )

    if not isinstance(raw_value, (str, int, float, bool)):
        raise CVGenerationError(
            f"{field_name} must be text or an object with text and format keys."
        )

    text = normalize_unicode_text(str(raw_value)).strip()
    if not text:
        return ""

    if text_format == "plain":
        return _escape_plain_latex(text)
    if text_format == "latex":
        _validate_raw_latex(text, field_name)
        return text
    return _escape_auto_latex(text)


def require_mapping(
    value: Any,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CVGenerationError(f"{field_name} must be a JSON object.")

    return value


def require_sequence(
    value: Any,
    field_name: str,
) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CVGenerationError(f"{field_name} must be a JSON array.")

    return value


def reject_unknown_keys(
    mapping: Mapping[str, Any],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(mapping) - allowed)

    if unknown:
        raise CVGenerationError(
            f"{field_name} contains unsupported keys: "
            f"{', '.join(unknown)}."
        )


def validate_url(
    value: str,
    field_name: str,
) -> str:
    if not value:
        return ""

    parsed = urlparse(value)
    allowed_schemes = {"http", "https", "mailto", "tel"}

    if parsed.scheme not in allowed_schemes:
        raise CVGenerationError(
            f"{field_name} must use one of these URL schemes: "
            f"{', '.join(sorted(allowed_schemes))}."
        )

    return value


def validate_icon_name(
    value: str,
    field_name: str,
) -> str:
    if value and not re.fullmatch(r"[A-Za-z0-9-]+", value):
        raise CVGenerationError(
            f"{field_name} contains an invalid Font Awesome icon name: "
            f"{value!r}."
        )

    return value


def parse_summary(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()

    if isinstance(value, (str, Mapping)):
        text = latex_text(value, "summary")
        return (text,) if text else ()

    items = require_sequence(value, "summary")
    paragraphs: list[str] = []

    for index, item in enumerate(items):
        if not isinstance(item, (str, Mapping)):
            raise CVGenerationError(
                f"summary[{index}] must be text or a text-format object."
            )

        text = latex_text(item, f"summary[{index}]")

        if text:
            paragraphs.append(text)

    return tuple(paragraphs)


def parse_skills(
    value: Any,
) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()

    rows = require_sequence(value, "skills")
    parsed_rows: list[tuple[str, str]] = []

    for index, row_value in enumerate(rows):
        field_name = f"skills[{index}]"
        row = require_mapping(row_value, field_name)

        reject_unknown_keys(
            row,
            {"label", "value"},
            field_name,
        )

        label = latex_text(row.get("label"))
        skill_value = latex_text(row.get("value"))

        if not label and not skill_value:
            raise CVGenerationError(
                f"{field_name} cannot be empty."
            )

        parsed_rows.append((label, skill_value))

    return tuple(parsed_rows)


def parse_content_item(
    value: Any,
    field_name: str,
) -> ContentItem:
    if isinstance(value, str):
        text = latex_text(value)

        if not text:
            raise CVGenerationError(
                f"{field_name} cannot be empty."
            )

        return ContentItem(text=text)

    item = require_mapping(value, field_name)

    reject_unknown_keys(
        item,
        {"text", "bullet"},
        field_name,
    )

    text = latex_text(item.get("text"))
    bullet = item.get("bullet", True)

    if not isinstance(bullet, bool):
        raise CVGenerationError(
            f"{field_name}.bullet must be true or false."
        )

    if not text:
        raise CVGenerationError(
            f"{field_name}.text cannot be empty."
        )

    return ContentItem(
        text=text,
        bullet=bullet,
    )


def parse_entry(
    value: Any,
    field_name: str,
) -> Entry:
    entry = require_mapping(value, field_name)

    reject_unknown_keys(
        entry,
        {
            "title",
            "secondary",
            "url",
            "icon",
            "organization",
            "date",
            "content",
        },
        field_name,
    )

    raw_content = require_sequence(
        entry.get("content", []),
        f"{field_name}.content",
    )

    parsed = Entry(
        title=latex_text(entry.get("title")),
        secondary=latex_text(entry.get("secondary")),
        url=_escape_url_for_latex(
            validate_url(
                "" if entry.get("url") is None else str(entry.get("url")).strip(),
                f"{field_name}.url",
            )
        ),
        icon=validate_icon_name(
            latex_text(entry.get("icon")),
            f"{field_name}.icon",
        ),
        organization=latex_text(entry.get("organization")),
        date=latex_text(entry.get("date")),
        content=tuple(
            parse_content_item(
                item,
                f"{field_name}.content[{index}]",
            )
            for index, item in enumerate(raw_content)
        ),
    )

    if not any(
        (
            parsed.title,
            parsed.secondary,
            parsed.url,
            parsed.organization,
            parsed.date,
            parsed.content,
        )
    ):
        raise CVGenerationError(
            f"{field_name} cannot be completely empty."
        )

    return parsed


def parse_entry_list(
    value: Any,
    field_name: str,
) -> tuple[Entry, ...]:
    if value is None:
        return ()

    entries = require_sequence(value, field_name)

    return tuple(
        parse_entry(
            entry,
            f"{field_name}[{index}]",
        )
        for index, entry in enumerate(entries)
    )


def parse_cv_data(
    raw: Mapping[str, Any],
) -> CVData:
    reject_unknown_keys(
        raw,
        {
            "summary",
            "skills",
            "projects",
            "work_experience",
            "awards",
        },
        "root",
    )

    return CVData(
        summary=parse_summary(raw.get("summary")),
        skills=parse_skills(raw.get("skills")),
        projects=parse_entry_list(
            raw.get("projects"),
            "projects",
        ),
        work_experience=parse_entry_list(
            raw.get("work_experience"),
            "work_experience",
        ),
        awards=parse_entry_list(
            raw.get("awards"),
            "awards",
        ),
    )


def indent_block(
    text: str,
    spaces: int,
) -> str:
    prefix = " " * spaces

    return "\n".join(
        prefix + line if line else ""
        for line in text.splitlines()
    )


def render_summary(
    paragraphs: Sequence[str],
) -> str:
    return "\n\n".join(
        "\\CVText{\n"
        + indent_block(paragraph, 2)
        + "\n}"
        for paragraph in paragraphs
    )


def render_skills(
    rows: Sequence[tuple[str, str]],
) -> str:
    if not rows:
        return ""

    rendered_rows = "\n".join(
        f"  \\CVLabelRow{{{label}}}{{{value}}}"
        for label, value in rows
    )

    return (
        "\\CVLabelRows{\n"
        + rendered_rows
        + "\n}"
    )


def render_content_item(
    item: ContentItem,
) -> str:
    command = (
        r"\CVContent"
        if item.bullet
        else r"\CVContent[false]"
    )

    return (
        f"{command}{{\n"
        + indent_block(item.text, 2)
        + "\n}"
    )


def render_entry(
    entry: Entry,
) -> str:
    rendered_content = "\n\n".join(
        render_content_item(item)
        for item in entry.content
    )

    body = (
        "{\n"
        + (
            indent_block(rendered_content, 2) + "\n"
            if rendered_content
            else ""
        )
        + "}"
    )

    arguments = [
        entry.title,
        entry.secondary,
        entry.url,
        entry.icon,
        entry.organization,
        entry.date,
        body,
    ]

    lines = [r"\CVEntry"]

    for argument in arguments[:-1]:
        lines.append(f"  {{{argument}}}")

    lines.append(
        indent_block(arguments[-1], 2)
    )

    return "\n".join(lines)


def render_entries(
    entries: Sequence[Entry],
) -> str:
    if not entries:
        return ""

    rendered_entries = "\n\n\\CVMediumGap\n\n".join(
        render_entry(entry)
        for entry in entries
    )

    return (
        "\\CVEntries{\n\n"
        + indent_block(rendered_entries, 2)
        + "\n\n}"
    )


def build_replacements(
    data: CVData,
) -> dict[str, str]:
    return {
        CV_PLACEHOLDERS["summary"]: render_summary(
            data.summary
        ),
        CV_PLACEHOLDERS["skills"]: render_skills(
            data.skills
        ),
        CV_PLACEHOLDERS["projects"]: render_entries(
            data.projects
        ),
        CV_PLACEHOLDERS["work_experience"]: render_entries(
            data.work_experience
        ),
        CV_PLACEHOLDERS["awards"]: render_entries(
            data.awards
        ),
    }



def parse_cover_letter_data(raw: Mapping[str, Any]) -> CoverLetterData:
    reject_unknown_keys(
        raw,
        {"date", "company_name", "paragraphs", "paragraph_1", "paragraph_2", "paragraph_3"},
        "root",
    )

    date = latex_text(raw.get("date"), "date")
    company_name = latex_text(raw.get("company_name"), "company_name")

    has_paragraphs_array = "paragraphs" in raw
    has_individual_paragraphs = any(
        key in raw for key in ("paragraph_1", "paragraph_2", "paragraph_3")
    )

    if has_paragraphs_array and has_individual_paragraphs:
        raise CVGenerationError(
            "Use either paragraphs or paragraph_1/paragraph_2/paragraph_3, not both."
        )

    if has_paragraphs_array:
        raw_paragraphs = require_sequence(raw.get("paragraphs"), "paragraphs")
        if len(raw_paragraphs) != 3:
            raise CVGenerationError("paragraphs must contain exactly 3 strings.")
        paragraph_values = raw_paragraphs
    else:
        paragraph_values = [
            raw.get("paragraph_1"),
            raw.get("paragraph_2"),
            raw.get("paragraph_3"),
        ]

    paragraphs: list[str] = []
    for index, value in enumerate(paragraph_values, start=1):
        if not isinstance(value, (str, Mapping)):
            raise CVGenerationError(
                f"paragraph_{index} must be text or a text-format object."
            )
        paragraph = latex_text(value, f"paragraph_{index}")
        if not paragraph:
            raise CVGenerationError(f"paragraph_{index} cannot be empty.")
        paragraphs.append(paragraph)

    if not date:
        raise CVGenerationError("date cannot be empty.")
    if not company_name:
        raise CVGenerationError("company_name cannot be empty.")

    return CoverLetterData(
        date=date,
        company_name=company_name,
        paragraphs=(paragraphs[0], paragraphs[1], paragraphs[2]),
    )


def render_cover_letter_paragraph(text: str) -> str:
    return "\\CLParagraph{\n" + indent_block(text, 2) + "\n}"


def build_cover_letter_replacements(data: CoverLetterData) -> dict[str, str]:
    return {
        COVER_LETTER_PLACEHOLDERS["date"]: data.date,
        COVER_LETTER_PLACEHOLDERS["company_name"]: data.company_name,
        COVER_LETTER_PLACEHOLDERS["paragraph_1"]: render_cover_letter_paragraph(data.paragraphs[0]),
        COVER_LETTER_PLACEHOLDERS["paragraph_2"]: render_cover_letter_paragraph(data.paragraphs[1]),
        COVER_LETTER_PLACEHOLDERS["paragraph_3"]: render_cover_letter_paragraph(data.paragraphs[2]),
    }

def inject_content(
    template: str,
    replacements: Mapping[str, str],
) -> str:
    output = template

    for marker, rendered_content in replacements.items():
        marker_count = output.count(marker)

        if marker_count != 1:
            raise CVGenerationError(
                f"Template must contain marker {marker!r} exactly once; "
                f"found {marker_count}."
            )

        output = output.replace(
            marker,
            rendered_content,
            1,
        )

    return output


def read_text_file(
    path: Path,
    description: str,
) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CVGenerationError(
            f"Could not read {description} {path}: {exc}"
        ) from exc


def load_json_mapping(
    path: Path,
) -> Mapping[str, Any]:
    raw_json = read_text_file(
        path,
        "JSON file",
    )

    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise CVGenerationError(
            f"Invalid JSON in {path} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc

    return require_mapping(decoded, "root")


def write_text_file(
    path: Path,
    content: str,
) -> None:
    try:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            content,
            encoding="utf-8",
        )
    except OSError as exc:
        raise CVGenerationError(
            f"Could not write generated file {path}: {exc}"
        ) from exc


def generate_tex(
    template_path: Path,
    data_path: Path,
    output_path: Path,
    document_type: str = "cv",
) -> Path:
    template = read_text_file(
        template_path,
        "template file",
    )

    raw_data = load_json_mapping(data_path)
    raw_data = normalize_unicode(raw_data)

    if document_type == "cv":
        replacements = build_replacements(parse_cv_data(raw_data))
    elif document_type == "cover-letter":
        replacements = build_cover_letter_replacements(
            parse_cover_letter_data(raw_data)
        )
    else:
        raise CVGenerationError(
            f"Unsupported document type: {document_type!r}."
        )

    generated = inject_content(
        template,
        replacements,
    )

    write_text_file(
        output_path,
        generated,
    )

    return output_path.resolve()


def generate_document(
    template_path: Path,
    data_path: Path,
    output_path: Path,
    document_type: str = "cv",
    compiler: TexCompiler | None = None,
) -> GenerationResult:
    """
    Generate a CV or cover-letter TeX file and optionally compile it.

    The default document type is CV, preserving the original behavior.
    """
    tex_path = generate_tex(
        template_path=template_path,
        data_path=data_path,
        output_path=output_path,
        document_type=document_type,
    )

    pdf_path = (
        compiler.compile(tex_path)
        if compiler is not None
        else None
    )

    return GenerationResult(
        tex_path=tex_path,
        pdf_path=pdf_path,
    )



def generate_cv(
    template_path: Path,
    data_path: Path,
    output_path: Path,
    compiler: TexCompiler | None = None,
) -> GenerationResult:
    """Backward-compatible CV generation entry point."""
    return generate_document(
        template_path=template_path,
        data_path=data_path,
        output_path=output_path,
        document_type="cv",
        compiler=compiler,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inject structured JSON content into a LaTeX CV or cover-letter "
            "template and optionally compile it to PDF using pdfLaTeX."
        )
    )

    parser.add_argument(
        "json_file",
        type=Path,
        help="Input JSON data file.",
    )

    parser.add_argument(
        "--type",
        dest="document_type",
        choices=("cv", "cover-letter"),
        default="cv",
        help="Document type. Default: cv",
    )

    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help=(
            "LaTeX template. Defaults to cv_template.tex for CVs or "
            "template_barebone.tex for cover letters."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Generated LaTeX file. Defaults to generated_cv.tex for CVs or "
            "generated_cover_letter.tex for cover letters."
        ),
    )

    parser.add_argument(
        "--pdf",
        action="store_true",
        help=(
            "Compile the generated TeX file to PDF using pdfLaTeX. "
            "The PDF is written beside the generated TeX file."
        ),
    )

    parser.add_argument(
        "--pdflatex",
        default="pdflatex",
        help=(
            "pdfLaTeX executable name or path. "
            "Default: pdflatex"
        ),
    )

    parser.add_argument(
        "--pdflatex-runs",
        type=int,
        default=2,
        help=(
            "Number of pdfLaTeX compilation runs. "
            "Default: 2"
        ),
    )

    parser.add_argument(
        "--keep-aux",
        action="store_true",
        help=(
            "Keep auxiliary LaTeX files such as .aux and .out "
            "after successful compilation."
        ),
    )

    return parser.parse_args()


def create_compiler(
    args: argparse.Namespace,
) -> TexCompiler | None:
    if not args.pdf:
        return None

    if args.pdflatex_runs < 1:
        raise CVGenerationError(
            "--pdflatex-runs must be at least 1."
        )

    return PdfLatexCompiler(
        executable=args.pdflatex,
        runs=args.pdflatex_runs,
        keep_auxiliary_files=args.keep_aux,
    )


def main() -> int:
    args = parse_args()

    try:
        compiler = create_compiler(args)

        template_path = args.template or (
            Path("cv_template.tex")
            if args.document_type == "cv"
            else Path("template_barebone.tex")
        )
        output_path = args.output or (
            Path("generated_cv.tex")
            if args.document_type == "cv"
            else Path("generated_cover_letter.tex")
        )

        result = generate_document(
            template_path=template_path,
            data_path=args.json_file,
            output_path=output_path,
            document_type=args.document_type,
            compiler=compiler,
        )
    except CVGenerationError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Generated TeX: {result.tex_path}")

    if result.pdf_path is not None:
        print(f"Generated PDF: {result.pdf_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
