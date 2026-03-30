#!/usr/bin/env python3
"""Strava MCP server and shared-auth bootstrap helper."""

from __future__ import annotations

import argparse
import shlex
import webbrowser
from pathlib import Path
from urllib import parse as urllib_parse

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.syntax import Syntax

from strava_mcp.runtime import build_service, resolve_storage_root
from strava_mcp.server import create_server
from strava_mcp.strava import (
    DEFAULT_PERSONAL_DATA_SCOPES,
    DEFAULT_STRAVA_ROOT,
    StravaAppCredentials,
    StravaService,
)


def _console() -> Console:
    return Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="strava-mcp",
        description="Strava MCP server backed by the shared Strava integration layer",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help=(
            "Directory that stores Strava auth state. Defaults to STRAVA_MCP_ROOT "
            f"or {DEFAULT_STRAVA_ROOT}."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run the Strava MCP server",
    )
    serve_parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport to expose",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind when using HTTP transports",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind when using HTTP transports",
    )
    serve_parser.set_defaults(func=run_server)

    authorize_parser = subparsers.add_parser(
        "authorize",
        help="Run the standard Strava OAuth authorization-code flow",
    )
    authorize_subparsers = authorize_parser.add_subparsers(
        dest="authorize_command",
        required=True,
    )

    authorize_start_parser = authorize_subparsers.add_parser(
        "start",
        help="Generate the Strava authorization URL and state",
    )
    authorize_start_parser.add_argument(
        "--approval-prompt",
        choices=("auto", "force"),
        default="auto",
        help="Pass-through Strava approval prompt mode",
    )
    authorize_start_parser.add_argument(
        "--launch-browser",
        action="store_true",
        help="Open the authorization URL in the local default browser",
    )
    authorize_start_parser.add_argument(
        "--scope",
        dest="scopes",
        action="append",
        default=None,
        help="OAuth scope to request. Repeat to override the default scope set.",
    )
    authorize_start_parser.set_defaults(func=run_authorize_start)

    authorize_complete_parser = authorize_subparsers.add_parser(
        "complete",
        help="Exchange the returned authorization code and persist session.json",
    )
    authorize_complete_parser.add_argument(
        "--state",
        required=True,
        help="OAuth state value emitted by `authorize start`",
    )
    authorize_complete_parser.add_argument(
        "--callback-url",
        help="Full redirect URL returned by Strava after authorization",
    )
    authorize_complete_parser.add_argument(
        "--scope",
        dest="scopes",
        action="append",
        default=None,
        help="OAuth scope originally requested. Repeat to override the default scope set.",
    )
    authorize_complete_parser.set_defaults(func=run_authorize_complete)

    return parser


def run_server(args: argparse.Namespace) -> int:
    server = create_server(
        host=args.host,
        port=args.port,
        service_factory=lambda: build_service(args.root),
    )
    server.run(transport=args.transport)
    return 0


def run_authorize_start(args: argparse.Namespace) -> int:
    service = build_service(args.root)
    _ensure_app_credentials(service)
    auth_request = service.prepare_authorization(
        scopes=_resolve_scopes(args.scopes),
        approval_prompt=args.approval_prompt,
    )
    console = _console()

    console.print(
        Panel.fit(
            auth_request.authorization_url,
            title="Open This URL To Authorize Strava Access",
            border_style="cyan",
        )
    )
    if args.launch_browser:
        webbrowser.open(auth_request.authorization_url)
        console.print(
            "[green]Launching the default browser for the Strava consent flow.[/green]"
        )
    console.print(
        "[bold]After approving access[/bold], copy the full redirect URL from the "
        "browser and run:"
    )
    console.print(
        Panel.fit(
            Syntax(
                _build_complete_command(auth_request.state, auth_request.scopes),
                "bash",
                word_wrap=True,
            ),
            title="Complete Authorization",
            border_style="green",
        )
    )
    return 0


def run_authorize_complete(args: argparse.Namespace) -> int:
    service = build_service(args.root)
    _ensure_app_credentials(service)
    console = _console()
    auth_request = service.prepare_authorization(
        scopes=_resolve_scopes(args.scopes),
        state=args.state,
    )
    callback_url = (
        args.callback_url
        or Prompt.ask("Paste the full redirect URL returned by Strava").strip()
    )
    if not callback_url:
        raise SystemExit("A Strava callback URL is required to complete authorization.")

    session = service.complete_authorization(
        authorization_request=auth_request,
        callback_url=callback_url,
    )

    session_path = service.storage.session_path
    console.print(
        Panel.fit(
            (
                f"Saved shared Strava session to {session_path}.\n"
                f"Authorized athlete ID: {session.athlete_id}\n"
                f"Granted scopes: {', '.join(session.scopes) or '<none>'}"
            ),
            title="Authorization Complete",
            border_style="green",
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _resolve_scopes(raw_scopes: list[str] | None) -> tuple[str, ...]:
    scopes = raw_scopes or list(DEFAULT_PERSONAL_DATA_SCOPES)
    normalized_scopes = tuple(dict.fromkeys(scope.strip() for scope in scopes if scope))
    if not normalized_scopes:
        raise SystemExit("At least one Strava scope is required.")
    return normalized_scopes


def _build_complete_command(state: str, scopes: tuple[str, ...]) -> str:
    parts = [
        "uv",
        "run",
        "strava-mcp",
        "--root",
        str(resolve_storage_root(None)),
        "authorize",
        "complete",
        "--state",
        state,
    ]
    for scope in scopes:
        parts.extend(["--scope", scope])
    return " ".join(shlex.quote(part) for part in parts)


def _ensure_app_credentials(service: StravaService) -> StravaAppCredentials:
    existing_credentials = service.storage.load_app_credentials(required=False)
    if existing_credentials is not None:
        return existing_credentials

    default_redirect_uri = "http://127.0.0.1:8765/exchange_token"
    app_path = service.storage.app_path
    console = _console()

    console.print(
        Panel.fit(
            (
                f"Strava app credentials not found at {app_path}.\n\n"
                "Create a Strava app at https://www.strava.com/settings/api if needed.\n"
                "You will need the Client ID, Client Secret, and a redirect URI whose "
                "host matches the Authorization Callback Domain in Strava."
            ),
            title="Bootstrap Strava Credentials",
            border_style="yellow",
        )
    )

    credentials = StravaAppCredentials(
        client_id=_prompt_client_id(),
        client_secret=_prompt_required_value("Strava Client Secret", password=True),
        redirect_uri=_prompt_redirect_uri(
            "Strava Redirect URI",
            default=default_redirect_uri,
        ),
    )
    service.save_app_credentials(credentials)
    console.print(f"[green]Saved Strava app credentials to {app_path}.[/green]")
    return credentials


def _prompt_client_id() -> int:
    while True:
        try:
            client_id = IntPrompt.ask("Strava Client ID")
        except ValueError:
            _console().print("[red]Client ID must be an integer.[/red]")
            continue
        if client_id <= 0:
            _console().print("[red]Client ID must be greater than zero.[/red]")
            continue
        return client_id


def _prompt_required_value(
    label: str,
    *,
    default: str | None = None,
    password: bool = False,
) -> str:
    while True:
        raw_value = Prompt.ask(label, default=default, password=password).strip()
        value = raw_value or (default or "")
        if value:
            return value
        _console().print(f"[red]{label} is required.[/red]")


def _prompt_redirect_uri(label: str, *, default: str | None = None) -> str:
    while True:
        value = _prompt_required_value(label, default=default)
        parsed_value = urllib_parse.urlparse(value)
        if parsed_value.scheme in {"http", "https"} and parsed_value.netloc:
            return value
        _console().print(
            "[red]Redirect URI must be a full http:// or https:// URL, for example "
            "http://127.0.0.1:8765/exchange_token.[/red]"
        )


if __name__ == "__main__":
    raise SystemExit(main())
