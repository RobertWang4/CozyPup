"""CLI entrypoint for local agent harness runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
import httpx

from .artifacts import read_json, write_json
from .client import AgentHarnessClient, ChatResult
from .export import append_sft_jsonl, trace_to_sft_row
from .report import build_eval_report
from .render import render_result
from .runner import ScenarioRunner
from .scenario import load_scenario
from .trace_schema import TraceArtifact, normalize_trace_artifact
from app.agents.tools.registry import get_tool_specs

DEV_BASE_URL = "http://localhost:8000"
PROD_BASE_URL = "https://backend-601329501885.northamerica-northeast1.run.app"


@click.group()
def cli():
    """Run CozyPup agent harness commands."""
    pass


@cli.group("tools")
def tools_cmd():
    """Inspect the agent tool manifest."""
    pass


@tools_cmd.command("list")
def tools_list_cmd():
    """List registered tools and compact manifest flags."""
    for name, spec in sorted(get_tool_specs().items()):
        click.echo(
            f"{name} "
            f"read_only={str(spec.read_only).lower()} "
            f"destructive={str(spec.destructive).lower()} "
            f"requires_confirmation={str(spec.requires_confirmation).lower()}"
        )


@tools_cmd.command("describe")
@click.argument("tool_name")
def tools_describe_cmd(tool_name: str):
    """Print one tool manifest as JSON."""
    spec = get_tool_specs().get(tool_name)
    if spec is None:
        raise click.ClickException(f"Unknown tool: {tool_name}")
    click.echo(json.dumps(spec.to_manifest(), ensure_ascii=False, indent=2))


@cli.command("chat")
@click.argument("message")
@click.option("--base-url", default=None, help="Backend root URL. Overrides --env.")
@click.option("--env", "env_name", type=click.Choice(["dev", "prod"]), default="dev", show_default=True)
@click.option("--email", default=None, help="Dev auth email. Defaults to a fresh harness user.")
@click.option("--debug", is_flag=True, help="Send X-Debug: true and render trace data if returned.")
@click.option("--verbose", is_flag=True, help="Print trace steps and token metrics.")
@click.option("--save-trace", default=None, help="Write normalized trace artifact JSON to this path.")
@click.option(
    "--pet",
    "pets",
    multiple=True,
    help="Pre-create a pet as NAME[:species]. May be passed multiple times.",
)
@click.option("--language", default=None, help="Optional request language override, e.g. zh or en.")
def chat_cmd(
    message: str,
    base_url: str | None,
    env_name: str,
    email: str | None,
    debug: bool,
    verbose: bool,
    save_trace: str | None,
    pets: tuple[str, ...],
    language: str | None,
):
    """Send one chat message to the backend without opening the iOS app."""
    resolved_base_url = _resolve_base_url(base_url, env_name)
    try:
        result_text = asyncio.run(_run_chat(
            message=message,
            base_url=resolved_base_url,
            email=email,
            debug=debug,
            verbose=verbose,
            save_trace=save_trace,
            pets=pets,
            language=language,
        ))
    except httpx.ConnectError as exc:
        raise click.ClickException(
            "Could not connect to CozyPup backend at "
            f"{resolved_base_url}.\n"
            "Check that --base-url is correct, the server is reachable, "
            "and the backend exposes /api/v1/auth/dev for harness runs."
        ) from exc
    click.echo(result_text)


async def _run_chat(
    *,
    message: str,
    base_url: str,
    email: str | None,
    debug: bool,
    verbose: bool,
    save_trace: str | None,
    pets: tuple[str, ...],
    language: str | None,
) -> str:
    client = AgentHarnessClient(base_url, debug=debug or save_trace is not None)
    try:
        await client.auth_dev(email=email)
        for spec in pets:
            name, species = _parse_pet_spec(spec)
            await client.create_pet(name, species)
        result = await client.chat(message, language=language)
        if save_trace:
            artifact = normalize_trace_artifact(
                scenario_id=None,
                user_email=client.email,
                input_messages=[message],
                result=result,
            )
            write_json(save_trace, artifact.to_dict())
        return render_result(result, verbose=verbose)
    finally:
        await client.close()


@cli.command("replay")
@click.argument("trace_path")
def replay_cmd(trace_path: str):
    """Render a saved trace artifact without calling the backend."""
    artifact = TraceArtifact.from_dict(read_json(trace_path))
    result = ChatResult(
        text=artifact.output_text,
        cards=artifact.cards,
        elapsed_ms=artifact.elapsed_ms,
        trace=artifact.raw_trace,
    )
    click.echo(render_result(result, verbose=True))
    if artifact.tools_called:
        click.echo("")
        click.echo("RECORDED TOOLS")
        click.echo(", ".join(artifact.tools_called))


@cli.command("run")
@click.argument("scenario_path")
@click.option("--base-url", default=None, help="Backend root URL. Overrides --env.")
@click.option("--env", "env_name", type=click.Choice(["dev", "prod"]), default="dev", show_default=True)
@click.option("--save-trace", default=None, help="Write normalized trace artifact JSON to this path.")
@click.option("--export-jsonl", default=None, help="Append an SFT JSONL row for this run.")
def run_cmd(
    scenario_path: str,
    base_url: str | None,
    env_name: str,
    save_trace: str | None,
    export_jsonl: str | None,
):
    """Run one scenario JSON file and grade the final result."""
    resolved_base_url = _resolve_base_url(base_url, env_name)
    scenario = load_scenario(scenario_path)
    run = asyncio.run(_run_scenario(scenario, resolved_base_url))
    if save_trace:
        write_json(save_trace, run.artifact.to_dict())
    if export_jsonl:
        append_sft_jsonl(
            export_jsonl,
            trace_to_sft_row(run.artifact, success=run.grade.passed),
        )

    status = "PASS" if run.grade.passed else "FAIL"
    click.echo(f"{status} {run.grade.scenario_id}")
    for reason in run.grade.reasons:
        click.echo(f"- {reason}")
    click.echo("")
    click.echo(render_result(run.result, verbose=True))


async def _run_scenario(scenario, base_url: str):
    client = AgentHarnessClient(base_url, debug=True)
    try:
        return await ScenarioRunner(client).run(scenario)
    finally:
        await client.close()


@cli.command("eval")
@click.argument("scenario_dir")
@click.option("--base-url", default=None, help="Backend root URL. Overrides --env.")
@click.option("--env", "env_name", type=click.Choice(["dev", "prod"]), default="dev", show_default=True)
@click.option("--report", "report_path", default=None, help="Write JSON eval report to this path.")
@click.option("--trace-dir", default=None, help="Write one normalized trace JSON per scenario.")
@click.option("--fail-fast", is_flag=True, help="Stop after the first failed scenario.")
def eval_cmd(
    scenario_dir: str,
    base_url: str | None,
    env_name: str,
    report_path: str | None,
    trace_dir: str | None,
    fail_fast: bool,
):
    """Run every scenario JSON file in a directory."""
    resolved_base_url = _resolve_base_url(base_url, env_name)
    scenario_paths = sorted(Path(scenario_dir).glob("*.json"))
    runs = asyncio.run(_run_scenarios(
        scenario_paths,
        resolved_base_url,
        trace_dir=trace_dir,
        fail_fast=fail_fast,
    ))
    report = build_eval_report(runs)
    if report_path:
        write_json(report_path, report)

    click.echo(f"PASS RATE {report['passed']}/{report['total']} ({report['pass_rate']:.0%})")
    for item in report["results"]:
        status = "PASS" if item["passed"] else "FAIL"
        click.echo(f"{status} {item['scenario_id']}")
        for reason in item["reasons"]:
            click.echo(f"- {reason}")


async def _run_scenarios(
    scenario_paths,
    base_url: str,
    *,
    trace_dir: str | None = None,
    fail_fast: bool = False,
):
    runs = []
    for path in scenario_paths:
        client = AgentHarnessClient(base_url, debug=True)
        try:
            scenario = load_scenario(path)
            run = await ScenarioRunner(client).run(scenario)
            runs.append(run)
            if trace_dir:
                trace_path = Path(trace_dir) / f"{scenario.id}.trace.json"
                write_json(trace_path, run.artifact.to_dict())
            if fail_fast and not run.grade.passed:
                break
        finally:
            await client.close()
    return runs


def _parse_pet_spec(spec: str) -> tuple[str, str]:
    if ":" not in spec:
        return spec, "dog"
    name, species = spec.split(":", 1)
    name = name.strip()
    species = species.strip() or "dog"
    if not name:
        raise click.BadParameter("--pet must include a non-empty name")
    return name, species


def _resolve_base_url(base_url: str | None, env_name: str) -> str:
    if base_url:
        return base_url.rstrip("/")
    return PROD_BASE_URL if env_name == "prod" else DEV_BASE_URL


if __name__ == "__main__":
    cli()
