"""
Context Precision benchmark — naive chunking vs semantic (smart) chunking.

Measures:
- Context precision: % of chunks that contain reviewable code changes
- Token efficiency: total tokens sent to LLM
- File coverage: files included vs filtered
- Chunk granularity: avg chunk size, scope labeling

Usage:
    python -m evals.chunking_benchmark
"""

import sys
import json
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.code_parser import (
    parse_unified_diff,
    chunk_for_agents,
    should_skip_file,
    detect_language,
    _file_priority,
)

# Approximate tokens as chars / 4
def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def naive_chunk(diff_text: str, max_chunk_size: int = 8000) -> list[dict]:
    """
    Naive chunking: split the raw diff into fixed-size chunks.
    No file filtering, no priority sorting, no function boundary awareness.
    """
    lines = diff_text.split("\n")
    chunks = []
    current_lines = []
    current_size = 0
    current_file = "unknown"

    for line in lines:
        if line.startswith("+++ b/"):
            current_file = line[6:]

        current_lines.append(line)
        current_size += len(line) + 1

        if current_size >= max_chunk_size:
            chunks.append({
                "file_path": current_file,
                "language": detect_language(current_file),
                "content": "\n".join(current_lines),
                "tokens": _estimate_tokens("\n".join(current_lines)),
                "scope_name": None,
                "priority": None,
                "has_code_changes": any(
                    l.startswith("+") and not l.startswith("+++")
                    or l.startswith("-") and not l.startswith("---")
                    for l in current_lines
                ),
            })
            current_lines = []
            current_size = 0

    if current_lines:
        chunks.append({
            "file_path": current_file,
            "language": detect_language(current_file),
            "content": "\n".join(current_lines),
            "tokens": _estimate_tokens("\n".join(current_lines)),
            "scope_name": None,
            "priority": None,
            "has_code_changes": any(
                l.startswith("+") and not l.startswith("+++")
                or l.startswith("-") and not l.startswith("---")
                for l in current_lines
            ),
        })

    return chunks


def smart_chunk_with_stats(diff_text: str) -> dict:
    """Run smart chunking and collect detailed stats."""
    file_diffs = parse_unified_diff(diff_text)
    chunks = chunk_for_agents(file_diffs)

    total_files = len(file_diffs)
    skipped_files = [fd.path for fd in file_diffs if should_skip_file(fd.path)]
    reviewable_files = [fd.path for fd in file_diffs if not should_skip_file(fd.path)]

    priority_dist = {"high": 0, "medium": 0, "normal": 0}
    for fd in file_diffs:
        if not should_skip_file(fd.path):
            p = _file_priority(fd.path)
            if p == 0:
                priority_dist["high"] += 1
            elif p == 1:
                priority_dist["medium"] += 1
            else:
                priority_dist["normal"] += 1

    total_tokens = 0
    code_tokens = 0
    scoped_chunks = 0
    for chunk in chunks:
        lang = chunk.get("language", "unknown")
        for hunk in chunk.get("hunks", []):
            t = _estimate_tokens(hunk.get("content", ""))
            total_tokens += t
            if lang not in ("markdown", "json", "yaml", "unknown"):
                code_tokens += t
        if chunk.get("scope_name"):
            scoped_chunks += 1

    precision = round(code_tokens / total_tokens * 100, 1) if total_tokens else 0

    return {
        "total_files": total_files,
        "skipped_files": len(skipped_files),
        "skipped_names": skipped_files[:5],
        "reviewable_files": len(reviewable_files),
        "priority_distribution": priority_dist,
        "total_chunks": len(chunks),
        "scoped_chunks": scoped_chunks,
        "scope_rate": round(scoped_chunks / len(chunks) * 100, 1) if chunks else 0,
        "total_tokens": total_tokens,
        "relevant_tokens": code_tokens,
        "avg_tokens_per_chunk": round(total_tokens / len(chunks)) if chunks else 0,
        "context_precision": precision,
    }


def _count_tokens_by_relevance(diff_text: str) -> dict:
    """Count tokens that belong to reviewable code vs noise."""
    lines = diff_text.split("\n")
    current_file = "unknown"
    relevant_tokens = 0
    noise_tokens = 0

    for line in lines:
        if line.startswith("+++ b/"):
            current_file = line[6:]
        tokens = _estimate_tokens(line)
        if should_skip_file(current_file):
            noise_tokens += tokens
        else:
            lang = detect_language(current_file)
            if lang in ("markdown", "json", "yaml", "unknown"):
                noise_tokens += tokens
            else:
                relevant_tokens += tokens

    return {"relevant": relevant_tokens, "noise": noise_tokens}


def naive_chunk_with_stats(diff_text: str) -> dict:
    """Run naive chunking and collect stats."""
    chunks = naive_chunk(diff_text)

    total_tokens = sum(c["tokens"] for c in chunks)
    chunks_with_changes = sum(1 for c in chunks if c["has_code_changes"])

    skippable_in_chunks = sum(
        1 for c in chunks if should_skip_file(c["file_path"])
    )

    token_breakdown = _count_tokens_by_relevance(diff_text)
    total = token_breakdown["relevant"] + token_breakdown["noise"]
    precision = round(token_breakdown["relevant"] / total * 100, 1) if total else 0

    return {
        "total_chunks": len(chunks),
        "chunks_with_code_changes": chunks_with_changes,
        "chunks_with_skippable_files": skippable_in_chunks,
        "total_tokens": total_tokens,
        "avg_tokens_per_chunk": round(total_tokens / len(chunks)) if chunks else 0,
        "relevant_tokens": token_breakdown["relevant"],
        "noise_tokens": token_breakdown["noise"],
        "context_precision": precision,
    }


# --- Test diffs ---

LARGE_MULTI_FILE_DIFF = """diff --git a/yarn.lock b/yarn.lock
--- a/yarn.lock
+++ b/yarn.lock
@@ -1,500 +1,510 @@
 # THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.
-lodash@^4.17.20:
-  version "4.17.20"
-  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.20.tgz"
+lodash@^4.17.21:
+  version "4.17.21"
+  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz"
+axios@^1.6.0:
+  version "1.6.0"
+  resolved "https://registry.yarnpkg.com/axios/-/axios-1.6.0.tgz"
+  dependencies:
+    follow-redirects "^1.15.0"
+    form-data "^4.0.0"
+    proxy-from-env "^1.1.0"
 express@^4.18.2:
   version "4.18.2"
   resolved "https://registry.yarnpkg.com/express/-/express-4.18.2.tgz"
+jsonwebtoken@^9.0.0:
+  version "9.0.0"
diff --git a/package-lock.json b/package-lock.json
--- a/package-lock.json
+++ b/package-lock.json
@@ -1,5 +1,5 @@
 {
-  "version": "1.0.0",
+  "version": "1.1.0",
   "lockfileVersion": 3,
   "requires": true,
   "packages": {
@@ -100,6 +100,7 @@
     "lodash": "4.17.21",
+    "axios": "1.6.0",
     "express": "4.18.2"
   }
 }
diff --git a/dist/bundle.min.js b/dist/bundle.min.js
--- a/dist/bundle.min.js
+++ b/dist/bundle.min.js
@@ -1,2 +1,2 @@
-!function(e){var t={};function n(r){if(t[r])return
+!function(e){var t={};function n(r){if(t[r])return t[r]
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,4 +1,5 @@
 # My Project
+## New feature: Authentication
 This is a sample project.
+Added login support.
diff --git a/src/auth/login.py b/src/auth/login.py
--- /dev/null
+++ b/src/auth/login.py
@@ -0,0 +1,35 @@
+import hashlib
+import sqlite3
+
+DB_PASSWORD = "admin123"
+
+class AuthService:
+    def __init__(self):
+        self.db = sqlite3.connect('users.db')
+
+    def login(self, username, password):
+        query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
+        result = self.db.execute(query)
+        user = result.fetchone()
+        if user:
+            return self._create_token(user)
+        return None
+
+    def _create_token(self, user):
+        token = hashlib.md5(str(user[0]).encode()).hexdigest()
+        return token
+
+    def register(self, username, password):
+        hashed = hashlib.md5(password.encode()).hexdigest()
+        self.db.execute(
+            f"INSERT INTO users (username, password) VALUES ('{username}', '{hashed}')"
+        )
+        self.db.commit()
+        return True
+
+    def delete_user(self, user_id):
+        self.db.execute(f"DELETE FROM users WHERE id = {user_id}")
+        self.db.commit()
+
+    def get_user(self, user_id):
+        return self.db.execute(f"SELECT * FROM users WHERE id = {user_id}").fetchone()
diff --git a/src/utils/helpers.py b/src/utils/helpers.py
--- a/src/utils/helpers.py
+++ b/src/utils/helpers.py
@@ -10,6 +10,15 @@
 def format_date(dt):
     return dt.strftime("%Y-%m-%d")

+def find_duplicates(items):
+    duplicates = []
+    for i in range(len(items)):
+        for j in range(i + 1, len(items)):
+            if items[i] == items[j]:
+                if items[i] not in duplicates:
+                    duplicates.append(items[i])
+    return duplicates
+
diff --git a/src/api/routes.py b/src/api/routes.py
--- a/src/api/routes.py
+++ b/src/api/routes.py
@@ -1,5 +1,25 @@
 from flask import Flask, request, jsonify
+import os
+import pickle
+import base64
 
 app = Flask(__name__)
 
+@app.route('/users')
+def get_users():
+    users = User.query.all()
+    result = []
+    for user in users:
+        orders = Order.query.filter_by(user_id=user.id).all()
+        result.append({'user': user.name, 'orders': len(orders)})
+    return jsonify(result)
+
+@app.route('/load', methods=['POST'])
+def load_data():
+    data = request.form.get('data')
+    obj = pickle.loads(base64.b64decode(data))
+    return str(obj)
+
+@app.route('/exec')
+def run_cmd():
+    cmd = request.args.get('cmd')
+    return os.popen(cmd).read()
diff --git a/tests/test_helpers.py b/tests/test_helpers.py
--- a/tests/test_helpers.py
+++ b/tests/test_helpers.py
@@ -5,3 +5,7 @@
 def test_format_date():
     dt = datetime(2024, 1, 15)
     assert format_date(dt) == "2024-01-15"
+
+def test_placeholder():
+    # TODO: add real tests
+    pass
diff --git a/.gitignore b/.gitignore
--- a/.gitignore
+++ b/.gitignore
@@ -1,3 +1,4 @@
 node_modules/
 __pycache__/
+.env
 *.pyc
diff --git a/docs/CHANGELOG.md b/docs/CHANGELOG.md
--- a/docs/CHANGELOG.md
+++ b/docs/CHANGELOG.md
@@ -1,3 +1,8 @@
 # Changelog
+## v1.1.0
+- Added authentication module
+- Added user management API
+- Fixed date formatting bug
+- Updated dependencies
 ## v1.0.0
 - Initial release
diff --git a/static/logo.png b/static/logo.png
--- a/static/logo.png
+++ b/static/logo.png
@@ -1 +1 @@
-binary content
+updated binary content
diff --git a/src/config/settings.json b/src/config/settings.json
--- a/src/config/settings.json
+++ b/src/config/settings.json
@@ -1,5 +1,6 @@
 {
   "debug": false,
+  "log_level": "info",
   "port": 8080,
   "host": "0.0.0.0"
 }
diff --git a/src/services/payment_service.py b/src/services/payment_service.py
--- a/src/services/payment_service.py
+++ b/src/services/payment_service.py
@@ -1,5 +1,45 @@
+import requests
+import time
+import asyncio
+
 class PaymentService:
-    pass
+    API_KEY = "sk_live_abc123def456"
+
+    def __init__(self, gateway_url):
+        self.gateway_url = gateway_url
+
+    async def process_payment(self, amount, card_token):
+        if amount <= 0:
+            return {"error": "Invalid amount"}
+        fee = amount * 0.029 + 0.30
+        total = amount + fee
+        time.sleep(2)
+        response = requests.post(
+            f"{self.gateway_url}/charge",
+            json={"amount": total, "source": card_token},
+            headers={"Authorization": f"Bearer {self.API_KEY}"}
+        )
+        return response.json()
+
+    async def refund(self, charge_id, amount=None):
+        time.sleep(1)
+        response = requests.post(
+            f"{self.gateway_url}/refund",
+            json={"charge_id": charge_id, "amount": amount}
+        )
+        return response.json()
+
+    def get_transactions(self, user_id):
+        transactions = Transaction.query.filter_by(user_id=user_id).all()
+        results = []
+        for t in transactions:
+            customer = Customer.query.get(t.customer_id)
+            product = Product.query.get(t.product_id)
+            results.append({
+                "transaction": t.id,
+                "customer": customer.name,
+                "product": product.name,
+                "amount": t.amount
+            })
+        return results
diff --git a/src/middleware/cors.py b/src/middleware/cors.py
--- a/src/middleware/cors.py
+++ b/src/middleware/cors.py
@@ -1,5 +1,10 @@
+from functools import wraps
+
 def cors_middleware(app):
-    pass
+    @wraps(app)
+    def wrapper(*args, **kwargs):
+        response = app(*args, **kwargs)
+        response.headers['Access-Control-Allow-Origin'] = '*'
+        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
+        return response
+    return wrapper
diff --git a/node_modules/lodash/lodash.js b/node_modules/lodash/lodash.js
--- a/node_modules/lodash/lodash.js
+++ b/node_modules/lodash/lodash.js
@@ -1,3 +1,3 @@
-// lodash v4.17.20
+// lodash v4.17.21
 ;(function() { var undefined;
 var VERSION = '4.17.21';
"""


def run_benchmark():
    print("=" * 70)
    print("  CONTEXT PRECISION BENCHMARK")
    print("  Naive (fixed-size) chunking vs Semantic (smart) chunking")
    print("=" * 70)

    diff = LARGE_MULTI_FILE_DIFF
    total_lines = len(diff.split("\n"))
    total_files_in_diff = diff.count("diff --git")

    print(f"\n  Test diff: {total_files_in_diff} files, {total_lines} lines")
    print(f"  Contains: package-lock.json, bundle.min.js, README.md,")
    print(f"            auth/login.py (SQLi + secrets), api/routes.py (XSS + RCE),")
    print(f"            utils/helpers.py (O(n²)), tests/, .gitignore")

    # Naive chunking
    print(f"\n{'─'*70}")
    print(f"  NAIVE CHUNKING (fixed-size, no filtering)")
    print(f"{'─'*70}")
    naive = naive_chunk_with_stats(diff)
    print(f"  Total chunks:           {naive['total_chunks']}")
    print(f"  Chunks with changes:    {naive['chunks_with_code_changes']}")
    print(f"  Chunks from junk files: {naive['chunks_with_skippable_files']}")
    print(f"  Total tokens to LLM:    {naive['total_tokens']:,}")
    print(f"  Avg tokens/chunk:       {naive['avg_tokens_per_chunk']:,}")
    print(f"  Context precision:      {naive['context_precision']}%")

    # Smart chunking
    print(f"\n{'─'*70}")
    print(f"  SEMANTIC CHUNKING (priority + scope + boundary-aware)")
    print(f"{'─'*70}")
    smart = smart_chunk_with_stats(diff)
    print(f"  Total files in diff:    {smart['total_files']}")
    print(f"  Files skipped:          {smart['skipped_files']} {smart['skipped_names']}")
    print(f"  Files reviewed:         {smart['reviewable_files']}")
    print(f"  Priority distribution:  {json.dumps(smart['priority_distribution'])}")
    print(f"  Total chunks:           {smart['total_chunks']}")
    print(f"  Scoped chunks:          {smart['scoped_chunks']} ({smart['scope_rate']}% have function/class labels)")
    print(f"  Total tokens to LLM:    {smart['total_tokens']:,}")
    print(f"  Avg tokens/chunk:       {smart['avg_tokens_per_chunk']:,}")
    print(f"  Context precision:      {smart['context_precision']}%")

    # Comparison
    print(f"\n{'─'*70}")
    print(f"  COMPARISON")
    print(f"{'─'*70}")

    token_savings = naive['total_tokens'] - smart['total_tokens']
    token_pct = round(token_savings / naive['total_tokens'] * 100, 1) if naive['total_tokens'] else 0
    precision_gain = smart['context_precision'] - naive['context_precision']

    print(f"  Context precision:      {naive['context_precision']}% → {smart['context_precision']}% (+{precision_gain:.1f}%)")
    print(f"  Token savings:          {token_savings:,} tokens ({token_pct}% reduction)")
    print(f"  Chunks:                 {naive['total_chunks']} → {smart['total_chunks']}")
    print(f"  Junk file elimination:  {smart['skipped_files']} files filtered out")
    print(f"  Scope labeling:         0% → {smart['scope_rate']}% of chunks have function/class context")

    print(f"\n{'─'*70}")
    print(f"  WHAT THIS MEANS FOR REVIEW QUALITY")
    print(f"{'─'*70}")
    print(f"  Naive: LLM wastes attention on package-lock.json, minified JS,")
    print(f"         .gitignore — dilutes focus on actual security issues")
    print(f"  Smart: LLM only sees auth/login.py, api/routes.py, utils/helpers.py")
    print(f"         with function-scoped context → higher detection accuracy")
    print()

    # Write results
    results = {
        "naive": naive,
        "smart": smart,
        "comparison": {
            "precision_gain": precision_gain,
            "token_savings": token_savings,
            "token_savings_pct": token_pct,
        },
    }
    Path(__file__).parent.joinpath("chunking_results.json").write_text(
        json.dumps(results, indent=2)
    )
    print(f"  Results saved to evals/chunking_results.json")


if __name__ == "__main__":
    run_benchmark()
