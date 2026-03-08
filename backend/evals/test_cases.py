"""
Evaluation test cases — known-bad code with expected findings.

Each case has:
- A synthetic diff containing deliberate bugs/vulnerabilities
- Expected findings the agents should detect
- Metadata for scoring (which agent, severity, category)

Used to measure precision/recall of the review pipeline.
"""

EVAL_CASES = [
    # ── Case 1: SQL injection ──
    {
        "id": "sql_injection",
        "name": "SQL Injection via string formatting",
        "diff": (
            "diff --git a/app/db.py b/app/db.py\n"
            "--- a/app/db.py\n"
            "+++ b/app/db.py\n"
            "@@ -10,6 +10,12 @@\n"
            " import sqlite3\n"
            " \n"
            "+def get_user(username):\n"
            "+    conn = sqlite3.connect('users.db')\n"
            "+    query = f\"SELECT * FROM users WHERE username = '{username}'\"\n"
            "+    result = conn.execute(query)\n"
            "+    return result.fetchone()\n"
            "+"
        ),
        "expected": [
            {"agent": "security", "keywords": ["sql injection", "parameterized"], "severity_min": "high"},
        ],
    },

    # ── Case 2: Hardcoded secrets ──
    {
        "id": "hardcoded_secret",
        "name": "Hardcoded API key and database password",
        "diff": (
            "diff --git a/config.py b/config.py\n"
            "--- a/config.py\n"
            "+++ b/config.py\n"
            "@@ -1,4 +1,8 @@\n"
            "+API_KEY = \"sk-proj-abc123def456ghi789\"\n"
            "+DB_PASSWORD = \"super_secret_password_123\"\n"
            "+AWS_SECRET_KEY = \"AKIAIOSFODNN7EXAMPLE\"\n"
            "+\n"
            " class Config:\n"
            "-    DEBUG = False\n"
            "+    DEBUG = True\n"
            "+    SECRET_KEY = \"hardcoded-jwt-secret-key-do-not-use\"\n"
        ),
        "expected": [
            {"agent": "security", "keywords": ["hardcoded", "secret", "api key"], "severity_min": "high"},
            {"agent": "security", "keywords": ["password", "credential"], "severity_min": "high"},
        ],
    },

    # ── Case 3: N+1 query ──
    {
        "id": "n_plus_one",
        "name": "N+1 query pattern in ORM loop",
        "diff": (
            "diff --git a/app/views.py b/app/views.py\n"
            "--- a/app/views.py\n"
            "+++ b/app/views.py\n"
            "@@ -5,6 +5,15 @@\n"
            " from app.models import Order, Customer\n"
            " \n"
            "+def get_order_summaries():\n"
            "+    orders = Order.objects.all()\n"
            "+    summaries = []\n"
            "+    for order in orders:\n"
            "+        customer = Customer.objects.get(id=order.customer_id)\n"
            "+        summaries.append({\n"
            "+            'order_id': order.id,\n"
            "+            'customer_name': customer.name,\n"
            "+            'total': order.total\n"
            "+        })\n"
            "+    return summaries\n"
        ),
        "expected": [
            {"agent": "performance", "keywords": ["n+1", "query", "loop"], "severity_min": "medium"},
        ],
    },

    # ── Case 4: Missing error handling ──
    {
        "id": "missing_error_handling",
        "name": "No error handling for file I/O and API calls",
        "diff": (
            "diff --git a/app/processor.py b/app/processor.py\n"
            "--- a/app/processor.py\n"
            "+++ b/app/processor.py\n"
            "@@ -1,4 +1,18 @@\n"
            " import requests\n"
            "+import json\n"
            " \n"
            "+def process_config(path):\n"
            "+    data = json.loads(open(path).read())\n"
            "+    response = requests.post('http://api.example.com/submit', json=data)\n"
            "+    result = response.json()\n"
            "+    return result['status']\n"
            "+\n"
            "+def delete_user_data(user_id):\n"
            "+    import os\n"
            "+    os.remove(f'/data/users/{user_id}')\n"
            "+    os.remove(f'/data/cache/{user_id}')\n"
            "+    os.remove(f'/data/logs/{user_id}.log')\n"
            "+    return True\n"
        ),
        "expected": [
            {"agent": "style", "keywords": ["error handling", "try", "except"], "severity_min": "medium"},
            {"agent": "security", "keywords": ["path traversal", "injection", "sanitiz"], "severity_min": "medium"},
        ],
    },

    # ── Case 5: Missing tests for critical logic ──
    {
        "id": "missing_tests",
        "name": "Payment processing with zero test coverage",
        "diff": (
            "diff --git a/app/payments.py b/app/payments.py\n"
            "--- /dev/null\n"
            "+++ b/app/payments.py\n"
            "@@ -0,0 +1,25 @@\n"
            "+class PaymentProcessor:\n"
            "+    def __init__(self, gateway):\n"
            "+        self.gateway = gateway\n"
            "+\n"
            "+    def charge(self, amount, currency, card_token):\n"
            "+        if amount <= 0:\n"
            "+            raise ValueError('Amount must be positive')\n"
            "+        fee = self._calculate_fee(amount)\n"
            "+        total = amount + fee\n"
            "+        result = self.gateway.create_charge(\n"
            "+            amount=total, currency=currency, source=card_token\n"
            "+        )\n"
            "+        return {'id': result.id, 'amount': total, 'status': result.status}\n"
            "+\n"
            "+    def refund(self, charge_id, amount=None):\n"
            "+        return self.gateway.create_refund(charge_id, amount=amount)\n"
            "+\n"
            "+    def _calculate_fee(self, amount):\n"
            "+        if amount > 1000:\n"
            "+            return amount * 0.025\n"
            "+        return amount * 0.03\n"
        ),
        "expected": [
            {"agent": "test_coverage", "keywords": ["test", "payment", "charge"], "severity_min": "high"},
            {"agent": "test_coverage", "keywords": ["refund", "edge case"], "severity_min": "medium"},
        ],
    },

    # ── Case 6: Blocking I/O in async + memory leak ──
    {
        "id": "async_blocking_io",
        "name": "Blocking calls inside async function + resource leak",
        "diff": (
            "diff --git a/app/service.py b/app/service.py\n"
            "--- a/app/service.py\n"
            "+++ b/app/service.py\n"
            "@@ -1,5 +1,20 @@\n"
            " import asyncio\n"
            "+import time\n"
            "+import requests\n"
            " \n"
            "+async def fetch_all_reports(report_ids):\n"
            "+    results = []\n"
            "+    for rid in report_ids:\n"
            "+        time.sleep(1)  # rate limiting\n"
            "+        resp = requests.get(f'http://api.internal/reports/{rid}')\n"
            "+        results.append(resp.json())\n"
            "+    return results\n"
            "+\n"
            "+async def stream_logs(path):\n"
            "+    f = open(path, 'r')\n"
            "+    while True:\n"
            "+        line = f.readline()\n"
            "+        if line:\n"
            "+            yield line\n"
            "+        await asyncio.sleep(0.1)\n"
        ),
        "expected": [
            {"agent": "performance", "keywords": ["blocking", "async", "time.sleep"], "severity_min": "high"},
            {"agent": "performance", "keywords": ["blocking", "requests", "async"], "severity_min": "high"},
            {"agent": "style", "keywords": ["resource", "leak", "close", "context manager"], "severity_min": "medium"},
        ],
    },

    # ── Case 7: XSS + CSRF + insecure deserialization ──
    {
        "id": "xss_csrf_pickle",
        "name": "XSS vulnerability, missing CSRF, unsafe pickle",
        "diff": (
            "diff --git a/app/web.py b/app/web.py\n"
            "--- a/app/web.py\n"
            "+++ b/app/web.py\n"
            "@@ -1,5 +1,22 @@\n"
            " from flask import Flask, request, render_template_string\n"
            "+import pickle\n"
            "+import base64\n"
            " \n"
            " app = Flask(__name__)\n"
            " \n"
            "+@app.route('/search')\n"
            "+def search():\n"
            "+    query = request.args.get('q', '')\n"
            "+    return render_template_string(f'<h1>Results for: {query}</h1>')\n"
            "+\n"
            "+@app.route('/load', methods=['POST'])\n"
            "+def load_data():\n"
            "+    encoded = request.form.get('data')\n"
            "+    obj = pickle.loads(base64.b64decode(encoded))\n"
            "+    return str(obj)\n"
            "+\n"
            "+@app.route('/update_profile', methods=['POST'])\n"
            "+def update_profile():\n"
            "+    name = request.form.get('name')\n"
            "+    # No CSRF token validation\n"
            "+    db.execute(f\"UPDATE users SET name='{name}' WHERE id={request.form.get('id')}\")\n"
            "+    return 'OK'\n"
        ),
        "expected": [
            {"agent": "security", "keywords": ["xss", "render_template_string", "cross-site", "ssti", "template injection"], "severity_min": "high"},
            {"agent": "security", "keywords": ["pickle", "deserialization", "arbitrary code"], "severity_min": "critical"},
            {"agent": "security", "keywords": ["sql injection"], "severity_min": "high"},
        ],
    },

    # ── Case 8: O(n²) algorithm ──
    {
        "id": "quadratic_algorithm",
        "name": "O(n^2) duplicate check instead of set lookup",
        "diff": (
            "diff --git a/app/utils.py b/app/utils.py\n"
            "--- a/app/utils.py\n"
            "+++ b/app/utils.py\n"
            "@@ -1,4 +1,12 @@\n"
            " \n"
            "+def find_duplicates(items):\n"
            "+    duplicates = []\n"
            "+    for i in range(len(items)):\n"
            "+        for j in range(i + 1, len(items)):\n"
            "+            if items[i] == items[j]:\n"
            "+                if items[i] not in duplicates:\n"
            "+                    duplicates.append(items[i])\n"
            "+    return duplicates\n"
        ),
        "expected": [
            {"agent": "performance", "keywords": ["o(n", "quadratic", "set", "nested loop"], "severity_min": "medium"},
        ],
    },
]
