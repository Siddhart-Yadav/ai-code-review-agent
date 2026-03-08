"""
Pre-computed demo review results for portfolio showcase.

These are realistic review outputs generated from real freeCodeCamp PRs,
allowing the app to work without any LLM API key configured.
"""

from datetime import datetime, timedelta

DEMO_REVIEWS = [
    {
        "id": "demo-review-001",
        "repo_full_name": "freeCodeCamp/freeCodeCamp",
        "pr_number": 66214,
        "pr_title": "refactor: move static curriculum data out of redux",
        "pr_url": "https://github.com/freeCodeCamp/freeCodeCamp/pull/66214",
        "status": "completed",
        "overall_score": 7.5,
        "summary": (
            "Well-structured refactor that moves static curriculum data out of Redux "
            "into a dedicated singleton service. This improves render performance by "
            "avoiding Redux immutability checks on unchanging data. The CurriculumDataService "
            "pattern is clean, but the singleton could benefit from explicit lifecycle management."
        ),
        "recommendation": "approve",
        "security_findings": [
            {
                "file": "client/src/services/curriculum-data.ts",
                "line": 8,
                "severity": "low",
                "title": "Singleton pattern uses mutable private fields",
                "description": (
                    "The CurriculumDataService uses private fields (#challengeNodes, etc.) "
                    "that can be re-initialized at any time via initialize(). While this is "
                    "fine for the current use case, it means any code path calling initialize() "
                    "could silently replace data mid-session."
                ),
                "suggestion": (
                    "Consider adding a guard: if (this.hasData) throw new Error('already initialized') "
                    "or at minimum logging a warning on re-initialization."
                ),
                "confidence": 0.72,
            },
        ],
        "performance_findings": [
            {
                "file": "client/src/redux/selectors.js",
                "line": 137,
                "severity": "medium",
                "title": "createSelector memoization broken by inline object creation",
                "description": (
                    "The completionStateSelector creates a new object reference on every call: "
                    "{ challengeNodes: curriculumData.challengeNodes, certificateNodes: ... }. "
                    "This defeats createSelector's memoization since the input selector "
                    "always returns a new reference."
                ),
                "suggestion": (
                    "Access curriculumData properties directly inside the result function "
                    "rather than creating an intermediate object in the input selector."
                ),
                "confidence": 0.88,
            },
            {
                "file": "client/src/templates/Challenges/redux/selectors.js",
                "line": 123,
                "severity": "medium",
                "title": "Redundant object allocation in currentBlockIdsSelector",
                "description": (
                    "Similar issue: allChallengesInfo object is reconstructed on every selector "
                    "call with { challengeNodes: curriculumData.challengeNodes, ... }, creating "
                    "unnecessary GC pressure."
                ),
                "suggestion": (
                    "Refactor getCurrentBlockIds to accept curriculumData directly, or "
                    "cache the wrapper object."
                ),
                "confidence": 0.85,
            },
        ],
        "style_findings": [
            {
                "file": "client/src/services/curriculum-data.ts",
                "line": 1,
                "severity": "info",
                "title": "Missing JSDoc on public API",
                "description": (
                    "The CurriculumDataService class has a good block comment, but "
                    "individual public methods (initialize, getters) lack JSDoc "
                    "documentation. Since this is a core singleton, documenting the "
                    "contract helps maintainers."
                ),
                "suggestion": "Add @param and @returns JSDoc to initialize() and getSuperBlockStructure().",
                "confidence": 0.65,
            },
            {
                "file": "client/src/templates/Challenges/utils/fetch-all-curriculum-data.tsx",
                "line": 68,
                "severity": "low",
                "title": "useEffect dependency array includes unstable references",
                "description": (
                    "The useEffect depends on [challengeNodes, certificateNodes, superBlockStructureNodes] "
                    "which are destructured from useStaticQuery. If Gatsby's static query returns new "
                    "references on HMR, this could cause repeated re-initialization."
                ),
                "suggestion": (
                    "Add a hasData guard: if (curriculumData.hasData) return; inside the effect."
                ),
                "confidence": 0.70,
            },
        ],
        "test_coverage_findings": [
            {
                "file": "client/src/services/curriculum-data.ts",
                "line": 1,
                "severity": "medium",
                "title": "New CurriculumDataService has no dedicated unit tests",
                "description": (
                    "The new singleton service is only tested indirectly through "
                    "completion-modal.test.tsx. A dedicated test file should cover "
                    "initialize(), hasData, and getSuperBlockStructure() edge cases."
                ),
                "suggestion": (
                    "Create curriculum-data.test.ts testing: double initialization, "
                    "empty data, getSuperBlockStructure with unknown key."
                ),
                "confidence": 0.90,
            },
        ],
        "meta_review": {
            "overall_score": 7.5,
            "recommendation": "approve",
            "summary": (
                "Well-structured refactor that moves static curriculum data out of Redux "
                "into a dedicated singleton service. Improves render performance by "
                "avoiding Redux immutability checks on unchanging data."
            ),
            "key_issues": [
                "Selector memoization broken by inline object creation in 2 selectors",
                "New CurriculumDataService lacks dedicated unit tests",
                "Singleton re-initialization has no guard or warning",
            ],
            "positive_aspects": [
                "Clean separation of static data from reactive state",
                "CurriculumDataService has a clear, minimal API",
                "Existing tests updated to use new pattern",
                "Removed 4 Redux actions/reducers, simplifying the store",
            ],
            "risk_assessment": "low",
        },
        "files_reviewed": 11,
        "total_issues": 5,
        "created_at": datetime.utcnow() - timedelta(minutes=2),
        "completed_at": datetime.utcnow() - timedelta(seconds=30),
        "duration_seconds": 42.3,
        "triggered_by": "demo",
    },
    {
        "id": "demo-review-002",
        "repo_full_name": "freeCodeCamp/freeCodeCamp",
        "pr_number": 66259,
        "pr_title": "feat(client): add tsconfig support to editor for TS challenges",
        "pr_url": "https://github.com/freeCodeCamp/freeCodeCamp/pull/66259",
        "status": "completed",
        "overall_score": 8.0,
        "summary": (
            "Adds tsconfig.json support to the Monaco editor, enabling per-challenge "
            "TypeScript compiler configuration. Well-implemented with proper validation, "
            "JSONC parsing, and comprehensive test coverage."
        ),
        "recommendation": "approve",
        "security_findings": [
            {
                "file": "tools/client-plugins/browser-scripts/modules/typescript-compiler.ts",
                "line": 20,
                "severity": "medium",
                "title": "Unsanitized compiler options from user-provided tsconfig",
                "description": (
                    "The rawCompilerOptions string is parsed with jsonc-parser and passed "
                    "directly to ts.convertCompilerOptionsFromJson(). A malicious challenge "
                    "author could inject compiler options that alter code behavior (e.g., "
                    "setting paths to rewrite imports)."
                ),
                "suggestion": (
                    "Allowlist specific compiler options (target, module, strict, jsx) and "
                    "reject unknown or dangerous ones before passing to TypeScript."
                ),
                "confidence": 0.75,
            },
        ],
        "performance_findings": [],
        "style_findings": [
            {
                "file": "packages/challenge-builder/src/build.ts",
                "line": 169,
                "severity": "info",
                "title": "hasTS and isTSConfig could be shared utilities",
                "description": (
                    "The helper functions hasTS() and isTSConfig() are defined locally in "
                    "build.ts but could be useful in other parts of the challenge pipeline."
                ),
                "suggestion": "Consider moving to packages/shared/src/utils/ for reuse.",
                "confidence": 0.55,
            },
        ],
        "test_coverage_findings": [
            {
                "file": "packages/challenge-builder/src/build.test.ts",
                "line": 1,
                "severity": "info",
                "title": "Good test coverage for getTSConfig edge cases",
                "description": (
                    "Tests cover: tsconfig exists, no tsconfig, and multiple tsconfigs (error). "
                    "Could additionally test malformed JSON content."
                ),
                "suggestion": "Add a test for contents being invalid JSON to verify error handling.",
                "confidence": 0.60,
            },
        ],
        "meta_review": {
            "overall_score": 8.0,
            "recommendation": "approve",
            "summary": (
                "Solid feature implementation. Adds tsconfig.json support with proper JSONC parsing, "
                "validation, and test coverage across the full stack."
            ),
            "key_issues": [
                "Unsanitized compiler options could be exploited by malicious challenges",
            ],
            "positive_aspects": [
                "Clean integration across editor, builder, and parser",
                "JSONC support (comments in JSON) is a nice touch",
                "Good test coverage with edge cases",
                "Proper separation: configureTSCompiler is called once at build time",
            ],
            "risk_assessment": "low",
        },
        "files_reviewed": 18,
        "total_issues": 3,
        "created_at": datetime.utcnow() - timedelta(minutes=3),
        "completed_at": datetime.utcnow() - timedelta(minutes=1),
        "duration_seconds": 67.8,
        "triggered_by": "demo",
    },
]


def get_demo_review(review_id: str) -> dict | None:
    """Get a demo review by ID."""
    for review in DEMO_REVIEWS:
        if review["id"] == review_id:
            return review
    return None


def get_demo_reviews_list() -> list[dict]:
    """Get all demo reviews as list items."""
    return [
        {
            "id": r["id"],
            "repo_full_name": r["repo_full_name"],
            "pr_number": r["pr_number"],
            "pr_title": r["pr_title"],
            "status": r["status"],
            "overall_score": r["overall_score"],
            "recommendation": r["recommendation"],
            "total_issues": r["total_issues"],
            "created_at": r["created_at"],
        }
        for r in DEMO_REVIEWS
    ]
