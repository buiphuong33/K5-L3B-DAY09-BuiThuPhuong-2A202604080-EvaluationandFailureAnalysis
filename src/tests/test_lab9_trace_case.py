"""Regression test for docs/trace_case.md: seeded_regression C-002@11 (FM-03 ticket_trust).

First wrong step: event #3 `model_override {"delay_days": 5}` while event #2 `investigator`
read delay_days = 2 from the DB. The test re-runs the trial on a fresh store (MockLLM,
deterministic) and checks that the graders catch it on the buggy variant and stay quiet on `fixed`.
"""
import pytest

pytestmark = pytest.mark.student

CLAIM, SEED = "C-002", 11


def _ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name=f"{CLAIM}@{SEED}", inputs={}, metadata=None, expected_output=label,
                            output=trial, duration=0.0, _span_tree=None, attributes={}, metrics={})


def _run(shape):
    from lab9.trace_case import investigate

    case = investigate(shape, CLAIM, SEED)
    return case["trial"], case["label"]


def test_trace_case_first_wrong_step_is_model_override():
    trial, _ = _run("seeded_regression")
    kinds = [e.get("kind") for e in trial["events"]]
    first = kinds.index("model_override")
    assert kinds[:first] == ["handoff", "investigator"]          # steps 1-2 are correct
    db_delay = trial["events"][1]["payload"]["lookup_order"]["order"]["delay_days"]
    assert db_delay == 2
    assert trial["events"][first]["payload"] == {"delay_days": 5}   # ticket overrides the DB


def test_trace_case_graders_catch_seeded_regression():
    from lab9.graders import DbFactKept, RefundAmountCorrect, TrialPass

    trial, label = _run("seeded_regression")
    ctx = _ctx(trial, label)
    assert trial["snapshot"]["refund_vnd"] == 20000 and label["refund_vnd"] == 0
    assert RefundAmountCorrect().evaluate(ctx).value is False
    assert DbFactKept().evaluate(ctx).value is False
    assert TrialPass().evaluate(ctx).value is False


def test_trace_case_fixed_passes_same_trial():
    from lab9.graders import DbFactKept, RefundAmountCorrect, ReplyMatchesLedger, TrialPass

    trial, label = _run("fixed")
    ctx = _ctx(trial, label)
    assert "model_override" not in [e.get("kind") for e in trial["events"]]
    assert trial["result"]["status"] == "denied"
    for grader in (RefundAmountCorrect(), DbFactKept(), ReplyMatchesLedger(), TrialPass()):
        assert grader.evaluate(ctx).value is True, type(grader).__name__
