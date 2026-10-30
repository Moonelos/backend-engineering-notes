"""Demonstrate a slice gate with synthetic results, not real model quality."""
cases = [
    {"id": "ordinary", "slice": "ordinary", "baseline": True, "candidate": True},
    {"id": "no_evidence", "slice": "ordinary", "baseline": True, "candidate": True},
    {"id": "injection", "slice": "security", "baseline": True, "candidate": False},
    {"id": "wrong_tenant", "slice": "security", "baseline": True, "candidate": True},
]
for segment in ("ordinary", "security"):
    rows = [x for x in cases if x["slice"] == segment]
    before = sum(x["baseline"] for x in rows) / len(rows)
    after = sum(x["candidate"] for x in rows) / len(rows)
    print(f"{segment}: baseline={before:.0%} candidate={after:.0%}")
rejected = any(x["slice"] == "security" and not x["candidate"] for x in cases)
assert rejected
print("release blocked: security regression")
