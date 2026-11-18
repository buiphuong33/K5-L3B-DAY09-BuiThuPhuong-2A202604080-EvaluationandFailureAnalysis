"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows = pr.get("rows") or []
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    # 1. NaN / inf metric values: NaN < min is False, so a naive gate lets them through.
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (NaN/inf): a crashed grader is not a pass")

    # 2. Row count must equal items x seeds of the manifest, with no duplicated (item, seed).
    man = pr.get("manifest") or {}
    want_n = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want_n:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want_n}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"{len(dups)} duplicated (item, seed) row(s), first {dups[0]}")

    # 3. Same (item, seed) set and the same seeds as the baseline: no cherry-picked items or seeds.
    base_rows = base.get("rows") or []
    pr_keys, base_keys = set(keys), {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if pr_keys != base_keys:
        problems.append(f"(item, seed) set differs from the baseline: {len(base_keys - pr_keys)} missing, "
                        f"{len(pr_keys - base_keys)} extra")
    base_man = base.get("manifest") or {}
    if sorted(man.get("seeds") or []) != sorted(base_man.get("seeds") or []) or man.get("items") != base_man.get("items"):
        problems.append(f"manifest seeds/items {man.get('seeds')}/{man.get('items')} differ from the baseline's "
                        f"{base_man.get('seeds')}/{base_man.get('items')}")

    # 4. Grader failures: reported ones, and silent ones (a graded metric that is None/NaN in a row).
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    for m in graded:
        broken = [r for r in rows if r.get(m) is None or (isinstance(r.get(m), float) and not math.isfinite(r[m]))]
        if broken:
            problems.append(f"{len(broken)} row(s) with no value for graded metric {m} "
                            f"(first {broken[0].get('item_id')}@{broken[0].get('seed')})")

    # 5. The headline numbers must be what the rows say (a hand-edited metric block).
    problems += _metrics_match_rows(pr, spec, graded)

    # 6. Slice tags of an item must match the baseline's (relabelling hides it from the slice gate).
    def tags(rs: list[dict]) -> dict:
        out: dict = {}
        for r in rs:
            out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
        return out
    pr_tags, base_tags = tags(rows), tags(base_rows)
    moved = sorted(i for i in set(pr_tags) & set(base_tags) if pr_tags[i] != base_tags[i])
    if moved:
        problems.append(f"slice tags differ from the baseline for {len(moved)} item(s), first {moved[0]}")

    # 7. Ratchet: on the same eval-set version, thresholds may only get stricter.
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    return problems


def _metrics_match_rows(pr: dict, spec: dict, graded: list[str]) -> list[str]:
    rows, metrics = pr.get("rows") or [], pr.get("metrics") or {}
    if not rows:
        return ["report has no rows"]
    try:
        want = aggregate(rows, [m for m in graded if m in rows[0]], k_values=spec.get("pass_k", []))
    except (KeyError, TypeError, ValueError):
        # Rows without cost etc.: still check the graded metrics, computed the same way as lab9.eval.
        want = {}
        for m in graded:
            vals = [r[m] for r in rows if r.get(m) is not None]
            if vals:
                want[m] = sum(vals) if m in ("secret_leak", "approval_bypass") else round(sum(vals) / len(vals), 4)
    out = []
    for k, w in want.items():
        got = metrics.get(k)
        if isinstance(w, (int, float)) and isinstance(got, (int, float)) and math.isfinite(got) \
                and abs(float(got) - float(w)) > 1e-4:
            out.append(f"metric {k} = {got} but the rows give {w}: metrics were edited by hand")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []          # a new eval-set version starts a new ratchet
    out: list[str] = []

    def looser(where: str, new: dict | None, old: dict) -> None:
        if new is None:
            out.append(f"ratchet: {where} was removed")
            return
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"ratchet: {where} is no longer blocking")
        nt, ot = new.get("threshold", new), old.get("threshold", old)
        for key in ("min",):
            if key in ot and (key not in nt or nt[key] < ot[key]):
                out.append(f"ratchet: {where} {key} {ot[key]} -> {nt.get(key)} (may not fall)")
        for key in ("max", "max_increase"):
            if key in ot and (key not in nt or nt[key] > ot[key]):
                out.append(f"ratchet: {where} {key} {ot[key]} -> {nt.get(key)} (may not rise)")
        if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
            out.append(f"ratchet: {where} dropped no_significant_drop")

    new_metrics = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        looser(f"metric {m['id']}", new_metrics.get(m["id"]), m)
    new_slices = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        looser(f"slice {s['name']}/{s['metric']}", new_slices.get((s["name"], s["metric"])), s)
    for key in ("seeds", "eval_set", "labels"):
        if key in base_spec and spec.get(key) != base_spec[key]:
            out.append(f"ratchet: {key} changed on the same eval-set version")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"          # an empty slice proves nothing: never a silent pass
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if s.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<38} {val!s:<8} n={len(a):<3} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
