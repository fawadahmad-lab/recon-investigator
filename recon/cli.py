"""Command-line interface for Recon Investigator."""

from __future__ import annotations

import argparse
from pathlib import Path

from recon import __version__
from recon.api.app import run_server
from recon.api.routes import DEMO_PROFILE, DEMO_SEED
from recon.config import get_settings
from recon.errors import ReconError
from recon.evaluation.aggregate import write_final_eval
from recon.evaluation.runner import run_evaluations
from recon.llm.base import PROVIDER_NAMES, build_provider
from recon.logging_setup import configure_logging
from recon.matching.engine import run_pipeline
from recon.report.builder import REPORT_NAME, write_run_artifacts
from recon.synth.generator import generate_dataset
from recon.synth.profiles import profile_names

LLM_CHOICES = ("none", *PROVIDER_NAMES)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    parser = argparse.ArgumentParser(
        prog="recon",
        description="Deterministic reconciliation with verified AI explanations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("version", help="Print the Recon Investigator version.")
    generate = subparsers.add_parser(
        "generate", help="Create seeded synthetic reconciliation data."
    )
    generate.add_argument("--profile", choices=profile_names(), required=True)
    generate.add_argument("--seed", type=int, required=True)
    generate.add_argument("--out", type=Path, required=True)
    evaluate = subparsers.add_parser(
        "eval", help="Evaluate deterministic matching against synthetic truth."
    )
    evaluate.add_argument("--profiles", choices=profile_names(), nargs="+", required=True)
    evaluate.add_argument("--seeds", type=int, nargs="+", required=True)
    evaluate.add_argument(
        "--llm",
        choices=LLM_CHOICES,
        default="mock",
        help="Explanation provider to score; none runs the deterministic pipeline only.",
    )
    demo = subparsers.add_parser(
        "demo", help="Generate the demo dataset, run it, and print the report path."
    )
    demo.add_argument("--profile", choices=profile_names(), default=DEMO_PROFILE)
    demo.add_argument("--seed", type=int, default=DEMO_SEED)
    demo.add_argument("--out", type=Path, default=Path("reports/demo"))
    demo.add_argument(
        "--llm",
        choices=LLM_CHOICES,
        default="mock",
        help="Explanation provider; the demo runs offline unless a real provider is named.",
    )
    run = subparsers.add_parser("run", help="Reconcile a bank file against a ledger file.")
    run.add_argument("--bank", type=Path, required=True)
    run.add_argument("--ledger", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument(
        "--llm",
        choices=LLM_CHOICES,
        default=None,
        help="Explanation provider; defaults to LLM_PROVIDER (mock). Use none to skip.",
    )
    serve = subparsers.add_parser("serve", help="Start the web UI and API.")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def _command_eval(args: argparse.Namespace) -> None:
    """Run the evaluation grid and refresh the aggregate report."""
    paths = run_evaluations(
        args.profiles,
        args.seeds,
        Path("reports"),
        Path("data/synthetic"),
        llm=args.llm,
    )
    for path in paths:
        print(path)
    print(write_final_eval(Path("reports"), paths))


def _command_demo(args: argparse.Namespace) -> None:
    """Generate the demo dataset, run the shipped pipeline and write every artifact."""
    folder = Path("data/synthetic") / f"demo_{args.profile}_{args.seed}"
    dataset = generate_dataset(args.profile, args.seed, folder)
    settings = get_settings()
    provider = None if args.llm == "none" else build_provider(settings, args.llm)
    result = run_pipeline(dataset / "bank.csv", dataset / "ledger.csv", settings, provider=provider)
    for artifact in write_run_artifacts(args.out, result):
        print(artifact)
    print(
        f"run_id={result.run_id} findings={len(result.findings)} "
        f"validation_issues={len(result.issues)} llm={args.llm}"
    )
    print(f"report: {args.out / REPORT_NAME}")


def main() -> None:
    """Run the command-line interface."""
    configure_logging()
    parser = build_parser()
    try:
        args = parser.parse_args()
        if args.command == "version":
            print(__version__)
        elif args.command == "generate":
            print(generate_dataset(args.profile, args.seed, args.out))
        elif args.command == "eval":
            _command_eval(args)
        elif args.command == "demo":
            _command_demo(args)
        elif args.command == "run":
            settings = get_settings()
            name = args.llm if args.llm is not None else settings.llm_provider
            provider = None if name == "none" else build_provider(settings, name)
            result = run_pipeline(args.bank, args.ledger, settings, provider=provider)
            for artifact in write_run_artifacts(args.out, result):
                print(artifact)
            print(
                f"run_id={result.run_id} findings={len(result.findings)} "
                f"validation_issues={len(result.issues)} llm={name}"
            )
        elif args.command == "serve":
            run_server(port=args.port)
    except ReconError as error:
        parser.exit(2, f"error: {error}\n")
