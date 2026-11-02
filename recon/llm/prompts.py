"""Prompt construction for the explanation investigator."""

from __future__ import annotations

import json
from collections.abc import Sequence

from recon.evidence.packet import EvidencePacket, packet_json
from recon.llm.schema import output_schema

SYSTEM_PROMPT = (
    "You are the explanation writer of a bank reconciliation tool.\n"
    "\n"
    "The reconciliation is already decided. Deterministic rules produced the finding you\n"
    "are given, and their decision is final. You never decide, confirm, deny, reclassify\n"
    "or question a match or a discrepancy. You never write that records do match, do not\n"
    "match, are or are not duplicates, or should be treated differently. Any sentence\n"
    "that argues about the decision itself is an error.\n"
    "\n"
    "Use only the evidence in the packet. Every amount, date, identifier and number you\n"
    "write must already appear in the packet's allowed_values. Never invent, estimate,\n"
    "round, convert or restate a value, and never use knowledge about a specific bank.\n"
    "Write plain English for a finance auditor: short, factual, no hedging filler.\n"
    "\n"
    "Set likely_cause to one value from the packet's allowed_causes. If the evidence is\n"
    'not enough to choose a cause, you must use "unknown" and confidence "low", and\n'
    "name the missing evidence in uncertainties.\n"
    "\n"
    "Answer with a single JSON object and nothing else, matching this schema exactly. It\n"
    "has no field for a match decision, and adding one is an error.\n"
    f"{json.dumps(output_schema(), sort_keys=True)}"
)


def user_prompt(packet: EvidencePacket, error_codes: Sequence[str] = ()) -> str:
    """Render the packet, plus the verifier's codes when a retry is requested."""
    text = f"Evidence packet (JSON):\n{packet_json(packet)}"
    if error_codes:
        codes = ", ".join(sorted(set(error_codes)))
        text += (
            "\n\nYour previous answer was rejected by the verifier. Failure codes: "
            f"{codes}. Send one JSON object again that fixes exactly those problems. Keep "
            "every cited value inside allowed_values, choose likely_cause from "
            "allowed_causes, and do not argue about the matching decision."
        )
    return text
