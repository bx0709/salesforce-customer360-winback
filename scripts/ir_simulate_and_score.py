#!/usr/bin/env python3
"""
Identity-resolution simulator + scorer for the Nestora Home dataset.

  python3 ir_simulate_and_score.py simulate
      Applies approximate versions of Data 360 match rules to the CSVs and scores them
      against ground_truth_person_map.csv. Gives you target numbers BEFORE you build rulesets.
      (Salesforce's real fuzzy/normalization logic is proprietary, so treat these as ballpark.)

  python3 ir_simulate_and_score.py score links.csv crm_map.csv
      Scores your REAL Data 360 result.
        links.csv   export of the Unified Link DMO: columns SourceRecordId__c, UnifiedRecordId__c
                    (extra columns are fine)
        crm_map.csv export of: SELECT Id__c, Description__c FROM Contact_Home__dll
                    (Description__c holds "Legacy ID: CRM-000123", used to tie CRM contacts to the answer key)
      E-commerce records need no mapping: their source id is already customer_id (CUST-xxxxxx).
"""
import csv, os, re, sys
from collections import defaultdict
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")


def load_truth():
    """source_record_id -> person_id, plus metadata."""
    truth, role = {}, {}
    for r in csv.DictReader(open(os.path.join(OUT, "ground_truth_person_map.csv"), encoding="utf-8")):
        truth[r["source_record_id"]] = r["person_id"]
        role[r["source_record_id"]] = r["link_mode"]
    return truth, role


def pair_set(clusters):
    s = set()
    for members in clusters.values():
        for a, b in combinations(sorted(members), 2):
            s.add((a, b))
    return s


def score(pred, truth, label, role=None):
    """pred: source_record_id -> unified cluster id. Only records present in truth are scored."""
    ids = [i for i in pred if i in truth]
    pc, tc = defaultdict(list), defaultdict(list)
    for i in ids:
        pc[pred[i]].append(i)
        tc[truth[i]].append(i)
    pp, tp = pair_set(pc), pair_set(tc)
    hit = len(pp & tp)
    prec = hit / len(pp) if pp else 1.0
    rec = hit / len(tp) if tp else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    mixed = sum(1 for m in pc.values() if len({truth[i] for i in m}) > 1)
    split = sum(1 for m in tc.values() if len({pred[i] for i in m}) > 1)
    print(f"\n== {label}")
    print(f"  source records scored      : {len(ids):,}")
    print(f"  unified profiles produced  : {len(pc):,}   (ideal: {len(tc):,})")
    print(f"  consolidation rate         : {1 - len(pc) / len(ids):.1%}   (ideal: {1 - len(tc) / len(ids):.1%})")
    print(f"  pairwise precision         : {prec:.1%}   (wrongly merged people lower this)")
    print(f"  pairwise recall            : {rec:.1%}   (missed links lower this)")
    print(f"  pairwise F1                : {f1:.1%}")
    print(f"  profiles mixing >1 person  : {mixed:,}   (false merges)")
    print(f"  people split across >1 prof: {split:,}   (missed merges)")
    if role:
        by = defaultdict(lambda: [0, 0])
        for p, mem in tc.items():
            m = {role[i] for i in mem}
            if len(mem) > 1 and any(i.startswith("CRM") for i in mem) and any(i.startswith("CUST") for i in mem):
                k = next(iter(m)) if len(m) == 1 else "mixed"
                by[k][0] += 1
                by[k][1] += int(len({pred[i] for i in mem}) == 1)
        print("  cross-system people correctly unified, by how linkable they are:")
        for k in ("email_and_phone", "email_only", "phone_only", "fuzzy_only"):
            tot, ok = by[k]
            if tot:
                print(f"    {k:<16}: {ok:>4}/{tot:<4} ({ok / tot:.0%})")


# ---------------------------------------------------------------- simulation
def norm_email(e):
    return (e or "").strip().lower()


def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    return d[-10:] if len(d) >= 10 else ""


def lev1(a, b):
    """True if edit distance <= 1."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def fuzzy_first(a, b):
    a, b = a.strip().lower().rstrip("."), b.strip().lower().rstrip(".")
    if not a or not b:
        return False
    return lev1(a, b) or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b))


class UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def load_records():
    recs = []
    for r in csv.DictReader(open(os.path.join(OUT, "crm_contacts.csv"), encoding="utf-8")):
        rid = r["Description"].split(": ")[1]
        recs.append(dict(id=rid, first=r["FirstName"], last=r["LastName"], email=norm_email(r["Email"]),
                         phone=norm_phone(r["Phone"]), city=r["MailingCity"].strip().lower(),
                         state=r["MailingState"].strip().lower()))
    for r in csv.DictReader(open(os.path.join(OUT, "ecom_customers.csv"), encoding="utf-8")):
        recs.append(dict(id=r["customer_id"], first=r["first_name"], last=r["last_name"], email=norm_email(r["email"]),
                         phone=norm_phone(r["phone"]), city=r["city"].strip().lower(), state=r["state"].strip().lower()))
    return recs


def run_rules(recs, rules):
    uf = UF([r["id"] for r in recs])
    for rule in rules:
        buckets = defaultdict(list)
        for r in recs:
            k = rule["key"](r)
            if k:
                buckets[k].append(r)
        for group in buckets.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if rule["cond"](group[i], group[j]):
                        uf.union(group[i]["id"], group[j]["id"])
    return {r["id"]: uf.find(r["id"]) for r in recs}


def last_ok(a, b):
    return a["last"].strip().lower() == b["last"].strip().lower()


R_EMAIL = dict(key=lambda r: r["email"], cond=lambda a, b: True)
R_PHONE = dict(key=lambda r: r["phone"], cond=lambda a, b: True)
R_EMAIL_NAME = dict(key=lambda r: r["email"], cond=lambda a, b: fuzzy_first(a["first"], b["first"]) and last_ok(a, b))
R_PHONE_NAME = dict(key=lambda r: r["phone"], cond=lambda a, b: fuzzy_first(a["first"], b["first"]) and last_ok(a, b))
R_NAME_CITY = dict(key=lambda r: (r["last"].strip().lower(), r["city"], r["state"]) if r["city"] else None,
                   cond=lambda a, b: fuzzy_first(a["first"], b["first"]))


def simulate():
    truth, role = load_truth()
    recs = load_records()
    print("Approximate simulation (Salesforce's real fuzzy matching differs; use for ballpark targets only).")
    score(run_rules(recs, [R_EMAIL, R_PHONE]), truth,
          "RULESET A  exact normalized email  OR  exact normalized phone (no name condition)", role)
    score(run_rules(recs, [R_EMAIL_NAME, R_PHONE_NAME]), truth,
          "RULESET B  (fuzzy first + exact last name) AND email  OR  ... AND phone", role)
    score(run_rules(recs, [R_EMAIL_NAME, R_PHONE_NAME, R_NAME_CITY]), truth,
          "RULESET C  = B  OR  (fuzzy first + exact last name AND same city+state)", role)
    score(run_rules(recs, [R_EMAIL, R_PHONE, R_NAME_CITY]), truth,
          "RULESET D  = A  OR  (fuzzy first + exact last name AND same city+state)", role)


# ---------------------------------------------------------------- real scoring
def score_real(links_path, crm_map_path):
    truth, role = load_truth()
    legacy = {}
    for r in csv.DictReader(open(crm_map_path, encoding="utf-8-sig")):
        m = re.search(r"CRM-\d+", r.get("Description__c", "") or "")
        if m:
            legacy[r["Id__c"]] = m.group(0)
    pred = {}
    for r in csv.DictReader(open(links_path, encoding="utf-8-sig")):
        src, uni = r["SourceRecordId__c"], r["UnifiedRecordId__c"]
        src = legacy.get(src, src)
        if src in truth:
            pred[src] = uni
    missing = [i for i in truth if i not in pred]
    print(f"Matched {len(pred):,} of {len(truth):,} answer-key records ({len(missing):,} not found in your export).")
    if missing[:5]:
        print("  e.g. not found:", missing[:5])
    score(pred, truth, "YOUR DATA 360 RESULT", role)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "simulate":
        simulate()
    elif len(sys.argv) == 4 and sys.argv[1] == "score":
        score_real(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
