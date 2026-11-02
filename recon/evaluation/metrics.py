"""Deterministic precision, recall, and F1 metrics for labeled findings."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from recon.llm.verifier import VERDICT_ACCEPTED, VERDICT_ERROR, VERDICT_REJECTED

FindingRecord = dict[str, Any]
FindingKey = tuple[str, tuple[str, ...]]
PairKey = tuple[tuple[str, ...], tuple[str, ...]]


def finding_key(finding: FindingRecord) -> FindingKey:
    """Return the architecture-defined type plus complete source-ID set key."""
    record_ids = tuple(sorted([*finding["ledger_ids"], *finding["bank_ids"]]))
    return (finding["type"], record_ids)


def pair_key(finding: FindingRecord) -> PairKey:
    """Return source-separated record ID sets for match-pair evaluation."""
    return (tuple(sorted(finding["ledger_ids"])), tuple(sorted(finding["bank_ids"])))


def derived_metrics(
    true_positive: int, false_positive: int, false_negative: int
) -> dict[str, float | int]:
    """Return the confusion counts plus precision, recall and F1 for a score triple."""
    detected = true_positive + false_positive
    labelled = true_positive + false_negative
    precision = true_positive / detected if detected else 0.0
    recall = true_positive / labelled if labelled else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _score(predicted: Counter[Any], expected: Counter[Any]) -> dict[str, float | int]:
    """Calculate confusion counts and derived metrics from keyed finding counts."""
    return derived_metrics(
        sum((predicted & expected).values()),
        sum((predicted - expected).values()),
        sum((expected - predicted).values()),
    )


def per_type_metrics(
    predicted: list[FindingRecord], expected: list[FindingRecord]
) -> dict[str, dict[str, float | int]]:
    """Score labeled findings per type and include a deterministic overall score."""
    predicted_by_type: dict[str, Counter[FindingKey]] = {}
    expected_by_type: dict[str, Counter[FindingKey]] = {}
    for finding in predicted:
        predicted_by_type.setdefault(finding["type"], Counter())[finding_key(finding)] += 1
    for finding in expected:
        expected_by_type.setdefault(finding["type"], Counter())[finding_key(finding)] += 1
    result = {
        finding_type: _score(
            predicted_by_type.get(finding_type, Counter()),
            expected_by_type.get(finding_type, Counter()),
        )
        for finding_type in sorted(set(predicted_by_type) | set(expected_by_type))
    }
    result["overall"] = _score(
        Counter(finding_key(finding) for finding in predicted),
        Counter(finding_key(finding) for finding in expected),
    )
    return result


def match_pair_metrics(
    predicted_matches: list[FindingRecord], expected_matches: list[FindingRecord]
) -> dict[str, float | int]:
    """Score match pairs independently from the predicted match classification."""
    return _score(
        Counter(pair_key(finding) for finding in predicted_matches),
        Counter(pair_key(finding) for finding in expected_matches),
    )


def cause_accuracy(
    predicted: Sequence[FindingRecord], expected: Sequence[FindingRecord]
) -> dict[str, Any]:
    """Score each explanation cause against the generator cause of the same finding.

    Only a finding whose type and record-ID set equal a labelled expected entry is
    scored, so a wrong match decision can never be rewarded with a cause point.
    """
    truth = {finding_key(item): item["cause"] for item in expected if item.get("cause")}
    by_type: dict[str, dict[str, int]] = {}
    for item in predicted:
        key = finding_key(item)
        if key not in truth or not item.get("likely_cause"):
            continue
        counts = by_type.setdefault(item["type"], {"scored": 0, "correct": 0})
        counts["scored"] += 1
        counts["correct"] += int(item["likely_cause"] == truth[key])
    scored = sum(counts["scored"] for counts in by_type.values())
    correct = sum(counts["correct"] for counts in by_type.values())
    return {
        "scored": scored,
        "correct": correct,
        "accuracy": correct / scored if scored else 0.0,
        "by_type": {
            name: {**counts, "accuracy": counts["correct"] / counts["scored"]}
            for name, counts in sorted(by_type.items())
        },
    }


def verifier_stats(
    records: Sequence[Mapping[str, Any]], provider: str, model: str
) -> dict[str, Any]:
    """Summarise the ask-retry-fallback outcome of every packet from its attempts.

    `catch_rate` is the share of first answers the verifier rejected, counting only
    packets whose first answer arrived; it is 1.0 for a provider that injects a fault
    into every packet and 0.0 for a clean provider.
    """
    packets: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        packets.setdefault(str(record["packet_hash"]), []).append(record)
    outcomes = [
        sorted(attempts, key=lambda item: int(item["attempt"])) for attempts in packets.values()
    ]
    first = [attempts[0] for attempts in outcomes]
    accepted_first = sum(1 for attempt in first if attempt["verdict"] == VERDICT_ACCEPTED)
    rejected_first = sum(1 for attempt in first if attempt["verdict"] == VERDICT_REJECTED)
    answered = accepted_first + rejected_first
    return {
        "provider": provider,
        "model": model,
        "packets": len(outcomes),
        "pass_first_try": accepted_first,
        "pass_after_retry": sum(
            1
            for attempts in outcomes
            if attempts[-1]["verdict"] == VERDICT_ACCEPTED
            and attempts[0]["verdict"] != VERDICT_ACCEPTED
        ),
        "fallback": sum(1 for attempts in outcomes if attempts[-1]["verdict"] != VERDICT_ACCEPTED),
        "rejected_first_try": rejected_first,
        "provider_errors": sum(1 for attempt in first if attempt["verdict"] == VERDICT_ERROR),
        "rejected_answers": sum(
            1
            for attempts in outcomes
            for attempt in attempts
            if attempt["verdict"] == VERDICT_REJECTED
        ),
        "catch_rate": rejected_first / answered if answered else 0.0,
    }
