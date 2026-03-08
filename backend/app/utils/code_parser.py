"""
Smart diff chunking for LLM-based code review.

Handles large diffs by:
1. Skipping non-reviewable files (locks, images, builds)
2. Prioritizing security-sensitive files
3. Splitting at function/class boundaries (never mid-function)
4. Grouping related hunks within the same logical scope
5. Enforcing per-chunk token budget for focused agent analysis
"""

import re
from dataclasses import dataclass, field


@dataclass
class DiffHunk:
    file_path: str
    language: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    content: str
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    context_lines: list[str] = field(default_factory=list)


@dataclass
class FileDiff:
    path: str
    language: str
    hunks: list[DiffHunk]
    is_new_file: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    old_path: str | None = None
    full_new_content: str | None = None


LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sql": "sql",
    ".sh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
}

# Pre-compiled patterns for performance (avoids recompilation on every call)
SKIP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\.lock$",
        r"package-lock\.json$",
        r"yarn\.lock$",
        r"pnpm-lock\.yaml$",
        r"\.min\.(js|css)$",
        r"\.(png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|mp4|webm)$",
        r"\.pyc$",
        r"__pycache__",
        r"node_modules/",
        r"\.git/",
        r"dist/",
        r"build/",
        r"\.next/",
        r"vendor/",
        r"\.DS_Store",
        r"Thumbs\.db",
    ]
]

# Files that touch these patterns get highest review priority
HIGH_PRIORITY_PATTERNS = [
    re.compile(p) for p in [
        r"auth", r"login", r"password", r"secret", r"crypto", r"encrypt",
        r"token", r"session", r"permission", r"middleware", r"security",
        r"payment", r"billing", r"checkout", r"transfer", r"api/",
        r"routes?\.", r"controller", r"handler", r"query", r"migration", r"schema",
    ]
]

MEDIUM_PRIORITY_PATTERNS = [
    re.compile(p) for p in [
        r"service", r"model", r"repository", r"database", r"cache",
        r"util", r"helper", r"lib/", r"core/", r"component", r"hook",
    ]
]

# Regex patterns for detecting function/class boundaries per language
FUNCTION_BOUNDARY_PATTERNS: dict[str, list[re.Pattern]] = {
    "python": [
        re.compile(r"^(\s*)(def |async def )\w+"),
        re.compile(r"^(\s*)(class )\w+"),
    ],
    "javascript": [
        re.compile(r"^(\s*)(function\s+\w+|const\s+\w+\s*=\s*(async\s+)?\()"),
        re.compile(r"^(\s*)(class\s+\w+)"),
        re.compile(r"^(\s*)(export\s+(default\s+)?(function|class|const))"),
    ],
    "typescript": [
        re.compile(r"^(\s*)(function\s+\w+|const\s+\w+\s*=\s*(async\s+)?\()"),
        re.compile(r"^(\s*)(class\s+\w+)"),
        re.compile(r"^(\s*)(export\s+(default\s+)?(function|class|const|interface|type))"),
        re.compile(r"^(\s*)(interface\s+\w+)"),
    ],
    "tsx": [
        re.compile(r"^(\s*)(function\s+\w+|const\s+\w+\s*=\s*(async\s+)?\()"),
        re.compile(r"^(\s*)(class\s+\w+)"),
        re.compile(r"^(\s*)(export\s+(default\s+)?(function|class|const))"),
    ],
    "jsx": [
        re.compile(r"^(\s*)(function\s+\w+|const\s+\w+\s*=\s*(async\s+)?\()"),
        re.compile(r"^(\s*)(class\s+\w+)"),
        re.compile(r"^(\s*)(export\s+(default\s+)?(function|class|const))"),
    ],
    "java": [
        re.compile(r"^(\s*)(public|private|protected|static|\s)*(class|interface|enum)\s+\w+"),
        re.compile(r"^(\s*)(public|private|protected|static|\s)+\w+[\w<>\[\],\s]*\s+\w+\s*\("),
    ],
    "go": [
        re.compile(r"^(\s*)(func\s+(\(\w+\s+\*?\w+\)\s+)?\w+)"),
        re.compile(r"^(\s*)(type\s+\w+\s+(struct|interface))"),
    ],
    "rust": [
        re.compile(r"^(\s*)(pub\s+)?(fn|struct|enum|impl|trait)\s+"),
    ],
    "ruby": [
        re.compile(r"^(\s*)(def\s+\w+)"),
        re.compile(r"^(\s*)(class\s+\w+)"),
        re.compile(r"^(\s*)(module\s+\w+)"),
    ],
    "cpp": [
        re.compile(r"^(\s*)(class\s+\w+)"),
        re.compile(r"^(\s*)(\w[\w:*&<>\s]+\s+\w+\s*\()"),
    ],
    "c": [
        re.compile(r"^(\s*)(\w[\w*\s]+\s+\w+\s*\()"),
    ],
    "csharp": [
        re.compile(r"^(\s*)(public|private|protected|internal|static|\s)*(class|interface|struct|enum)\s+\w+"),
        re.compile(r"^(\s*)(public|private|protected|internal|static|\s)+\w+[\w<>\[\],\s]*\s+\w+\s*\("),
    ],
    "php": [
        re.compile(r"^(\s*)(public|private|protected|static|\s)*(function\s+\w+)"),
        re.compile(r"^(\s*)(class\s+\w+)"),
    ],
    "kotlin": [
        re.compile(r"^(\s*)(fun\s+\w+)"),
        re.compile(r"^(\s*)(class\s+\w+)"),
    ],
    "swift": [
        re.compile(r"^(\s*)(func\s+\w+)"),
        re.compile(r"^(\s*)(class|struct|enum|protocol)\s+\w+"),
    ],
    "scala": [
        re.compile(r"^(\s*)(def\s+\w+)"),
        re.compile(r"^(\s*)(class|object|trait)\s+\w+"),
    ],
}

FUNCTION_NAME_PATTERN = re.compile(
    r"(?:def |async def |func(?:tion)?\s+|const\s+|class\s+|type\s+|interface\s+|impl\s+)"
    r"(\w+)"
)


def detect_language(file_path: str) -> str:
    for ext, lang in LANGUAGE_MAP.items():
        if file_path.endswith(ext):
            return lang
    return "unknown"


def should_skip_file(file_path: str) -> bool:
    return any(pattern.search(file_path) for pattern in SKIP_PATTERNS)


def _file_priority(file_path: str) -> int:
    """0 = highest priority (security-sensitive), 1 = medium, 2 = low."""
    path_lower = file_path.lower()
    for pattern in HIGH_PRIORITY_PATTERNS:
        if pattern.search(path_lower):
            return 0
    for pattern in MEDIUM_PRIORITY_PATTERNS:
        if pattern.search(path_lower):
            return 1
    return 2


def _detect_scope_name(content_lines: list[str], language: str) -> str | None:
    """Try to detect the function/class name that a set of lines belongs to."""
    patterns = FUNCTION_BOUNDARY_PATTERNS.get(language, [])
    for line in content_lines:
        clean = line.lstrip("+").lstrip("-").lstrip(" ")
        for pat in patterns:
            if pat.match(clean):
                m = FUNCTION_NAME_PATTERN.search(clean)
                if m:
                    return m.group(1)
    return None


def _is_function_boundary(line: str, language: str) -> bool:
    """Check if a line is the start of a new function/class definition."""
    clean = line.lstrip("+").lstrip("-").lstrip(" ")
    patterns = FUNCTION_BOUNDARY_PATTERNS.get(language, [])
    return any(pat.match(clean) for pat in patterns)


# --- Diff parsing (unchanged logic, clean implementation) ---

def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """Parse a unified diff into structured FileDiff objects."""
    file_diffs = []
    current_file = None
    current_hunks: list[DiffHunk] = []
    current_hunk_lines: list[str] = []
    current_hunk_header: str | None = None

    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            if current_hunk_header and current_hunk_lines and current_file:
                current_hunks.append(
                    _build_hunk(current_file, current_hunk_header, current_hunk_lines)
                )
            if current_file and current_hunks:
                file_diffs.append(_build_file_diff(current_file, current_hunks))
            current_file = None
            current_hunks = []
            current_hunk_lines = []
            current_hunk_header = None
            continue

        if line.startswith("--- a/") or line.startswith("--- /dev/null"):
            continue

        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue

        if line.startswith("+++ /dev/null"):
            continue

        if line.startswith("@@"):
            if current_hunk_header and current_hunk_lines and current_file:
                current_hunks.append(
                    _build_hunk(current_file, current_hunk_header, current_hunk_lines)
                )
            current_hunk_header = line
            current_hunk_lines = []
            continue

        if current_hunk_header is not None:
            current_hunk_lines.append(line)

    if current_hunk_header and current_hunk_lines and current_file:
        current_hunks.append(
            _build_hunk(current_file, current_hunk_header, current_hunk_lines)
        )

    if current_file and current_hunks:
        file_diffs.append(_build_file_diff(current_file, current_hunks))

    return file_diffs


def _build_hunk(file_path: str, header: str, lines: list[str]) -> DiffHunk:
    match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", header)
    old_start = int(match.group(1)) if match else 0
    old_count = int(match.group(2)) if match and match.group(2) else 1
    new_start = int(match.group(3)) if match else 0
    new_count = int(match.group(4)) if match and match.group(4) else 1

    added = [ln[1:] for ln in lines if ln.startswith("+")]
    removed = [ln[1:] for ln in lines if ln.startswith("-")]
    context = [
        ln[1:] if ln.startswith(" ") else ln
        for ln in lines
        if not ln.startswith("+") and not ln.startswith("-")
    ]

    return DiffHunk(
        file_path=file_path,
        language=detect_language(file_path),
        old_start=old_start,
        old_count=old_count,
        new_start=new_start,
        new_count=new_count,
        content="\n".join(lines),
        added_lines=added,
        removed_lines=removed,
        context_lines=context,
    )


def _build_file_diff(file_path: str, hunks: list[DiffHunk]) -> FileDiff:
    return FileDiff(
        path=file_path,
        language=detect_language(file_path),
        hunks=hunks,
        is_new_file=all(len(h.removed_lines) == 0 for h in hunks),
        is_deleted=all(len(h.added_lines) == 0 for h in hunks),
    )


# --- Smart chunking ---

@dataclass
class _ScopeGroup:
    """Hunks that belong to the same function/class scope."""
    scope_name: str | None
    hunks: list[DiffHunk]
    total_size: int = 0


def _group_hunks_by_scope(hunks: list[DiffHunk], language: str) -> list[_ScopeGroup]:
    """
    Group hunks that modify the same function/class together.
    Hunks that can't be attributed to a scope get their own group.
    """
    groups: list[_ScopeGroup] = []
    scope_map: dict[str, _ScopeGroup] = {}

    for hunk in hunks:
        scope = _detect_scope_name(hunk.content.split("\n"), language)

        if scope and scope in scope_map:
            group = scope_map[scope]
            group.hunks.append(hunk)
            group.total_size += len(hunk.content)
        elif scope:
            group = _ScopeGroup(scope_name=scope, hunks=[hunk], total_size=len(hunk.content))
            scope_map[scope] = group
            groups.append(group)
        else:
            groups.append(_ScopeGroup(scope_name=None, hunks=[hunk], total_size=len(hunk.content)))

    return groups


def _split_at_function_boundaries(hunk: DiffHunk, language: str, max_size: int) -> list[list[str]]:
    """
    Split a large hunk's content at function boundaries.
    Returns list of line-groups, each staying under max_size.
    """
    lines = hunk.content.split("\n")
    segments: list[list[str]] = []
    current_segment: list[str] = []
    current_size = 0

    for line in lines:
        is_boundary = _is_function_boundary(line, language)

        if is_boundary and current_segment and current_size > max_size * 0.3:
            segments.append(current_segment)
            current_segment = []
            current_size = 0

        current_segment.append(line)
        current_size += len(line) + 1

    if current_segment:
        segments.append(current_segment)

    return segments


def chunk_for_agents(
    file_diffs: list[FileDiff],
    max_chunk_size: int = 8000,
    max_chunks_per_agent: int = 12,
) -> list[dict]:
    """
    Smart chunking for LLM-based code review.

    Strategy:
    1. Skip non-reviewable files
    2. Sort by security/risk priority
    3. Group hunks by function/class scope (never split mid-function)
    4. Split oversized scopes at the next function boundary
    5. Enforce token budget (max_chunk_size per chunk, max_chunks_per_agent total)
    6. Attach metadata (scope name, priority) for agent context
    """
    reviewable = [fd for fd in file_diffs if not should_skip_file(fd.path)]
    reviewable.sort(key=lambda fd: (_file_priority(fd.path), fd.path))

    chunks: list[dict] = []

    for fd in reviewable:
        if len(chunks) >= max_chunks_per_agent:
            break

        priority = _file_priority(fd.path)
        scope_groups = _group_hunks_by_scope(fd.hunks, fd.language)

        for group in scope_groups:
            if len(chunks) >= max_chunks_per_agent:
                break

            if group.total_size <= max_chunk_size:
                chunks.append(_build_chunk(
                    fd, group.hunks, group.scope_name, priority
                ))
            else:
                # Scope is too large — split at function boundaries
                sub_chunks = _split_large_scope(fd, group, max_chunk_size)
                for sc in sub_chunks:
                    if len(chunks) >= max_chunks_per_agent:
                        break
                    chunks.append(sc)

    return chunks


def _split_large_scope(fd: FileDiff, group: _ScopeGroup, max_size: int) -> list[dict]:
    """Split an oversized scope group into multiple chunks at function boundaries."""
    result = []
    current_hunks: list[dict] = []
    current_size = 0

    for hunk in group.hunks:
        hunk_size = len(hunk.content)

        if hunk_size > max_size:
            # Single hunk exceeds limit — split at function boundaries within it
            if current_hunks:
                result.append(_build_chunk(
                    fd, None, group.scope_name, _file_priority(fd.path),
                    prebuilt_hunks=current_hunks
                ))
                current_hunks = []
                current_size = 0

            segments = _split_at_function_boundaries(hunk, fd.language, max_size)
            for seg_lines in segments:
                seg_content = "\n".join(seg_lines)
                result.append({
                    "file_path": fd.path,
                    "language": fd.language,
                    "is_new_file": fd.is_new_file,
                    "is_deleted": fd.is_deleted,
                    "scope_name": group.scope_name,
                    "priority": _file_priority(fd.path),
                    "hunks": [{
                        "new_start": hunk.new_start,
                        "new_count": hunk.new_count,
                        "content": seg_content,
                        "added_lines": [l[1:] for l in seg_lines if l.startswith("+")],
                        "removed_lines": [l[1:] for l in seg_lines if l.startswith("-")],
                    }],
                })
            continue

        if current_size + hunk_size > max_size and current_hunks:
            result.append(_build_chunk(
                fd, None, group.scope_name, _file_priority(fd.path),
                prebuilt_hunks=current_hunks
            ))
            current_hunks = []
            current_size = 0

        current_hunks.append({
            "new_start": hunk.new_start,
            "new_count": hunk.new_count,
            "content": hunk.content,
            "added_lines": hunk.added_lines,
            "removed_lines": hunk.removed_lines,
        })
        current_size += hunk_size

    if current_hunks:
        result.append(_build_chunk(
            fd, None, group.scope_name, _file_priority(fd.path),
            prebuilt_hunks=current_hunks
        ))

    return result


def _build_chunk(
    fd: FileDiff,
    hunks: list[DiffHunk] | None,
    scope_name: str | None,
    priority: int,
    prebuilt_hunks: list[dict] | None = None,
) -> dict:
    if prebuilt_hunks is not None:
        hunk_data = prebuilt_hunks
    else:
        hunk_data = [
            {
                "new_start": h.new_start,
                "new_count": h.new_count,
                "content": h.content,
                "added_lines": h.added_lines,
                "removed_lines": h.removed_lines,
            }
            for h in (hunks or [])
        ]

    return {
        "file_path": fd.path,
        "language": fd.language,
        "is_new_file": fd.is_new_file,
        "is_deleted": fd.is_deleted,
        "scope_name": scope_name,
        "priority": priority,
        "hunks": hunk_data,
    }
