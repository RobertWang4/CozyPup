"""`admin login / logout / whoami / config / ping` commands."""
from __future__ import annotations

import http.server
import socketserver
import time
import urllib.parse
import webbrowser

import click

from .client import AdminClient, AdminClientError
from .config import AdminConfig
from .output import die, emit_json, emit_table


def _load_config_for_env(env: str | None) -> tuple[AdminConfig, AdminClient]:
    try:
        cfg = AdminConfig.load()
    except PermissionError as e:
        die(str(e))
        raise  # unreachable
    return cfg, AdminClient(cfg, env=env)


@click.command("login")
@click.option("--dev", "dev", is_flag=True, help="Use dev-login instead of browser OAuth")
@click.option("--email", help="Email for dev-login")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def login_cmd(ctx, dev, email, env, as_json):
    cfg, client = _load_config_for_env(env)
    if dev:
        if not email:
            die("--email is required with --dev")
        try:
            envelope = client.post("/admin/auth/dev-login", {"email": email})
        except AdminClientError as e:
            die(str(e))
        data = envelope.data
        cfg.token = data["token"]
        cfg.token_expires_at = int(time.time()) + int(data["expires_in"])
        cfg.email = data["email"]
        cfg.default_env = envelope.env or client.env
        cfg.save()
        if as_json:
            emit_json({"email": cfg.email, "env": cfg.default_env, "expires_in": data["expires_in"]}, env=cfg.default_env)
        else:
            emit_table("Logged in", [("email", cfg.email), ("env", cfg.default_env), ("expires_in", f"{data['expires_in']}s")])
        return

    # Browser OAuth loopback.
    with socketserver.TCPServer(("127.0.0.1", 0), _OAuthHandler) as httpd:
        port = httpd.server_address[1]
        callback = f"http://127.0.0.1:{port}/callback"
        start_url = f"{client.base_url}/api/v1/admin/auth/oauth/start?callback={urllib.parse.quote(callback, safe='')}"
        click.echo(f"Opening browser: {start_url}")
        webbrowser.open(start_url)
        httpd.timeout = 180
        _OAuthHandler.result = None
        while _OAuthHandler.result is None:
            httpd.handle_request()

    result = _OAuthHandler.result
    if "token" not in result:
        die(f"OAuth failed: {result}")
    cfg.token = result["token"][0]
    cfg.token_expires_at = int(time.time()) + int(result["expires_in"][0])
    cfg.email = result["email"][0]
    cfg.default_env = client.env
    cfg.save()
    if as_json:
        emit_json({"email": cfg.email, "env": cfg.default_env}, env=client.env)
    else:
        emit_table("Logged in", [("email", cfg.email), ("env", cfg.default_env)])


class _OAuthHandler(http.server.BaseHTTPRequestHandler):
    result: dict | None = None

    def log_message(self, *a, **kw):  # silence
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404); self.end_headers(); return
        _OAuthHandler.result = urllib.parse.parse_qs(parsed.query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>CozyPup admin login complete.</h1><p>You can close this window.</p>")


@click.command("logout")
def logout_cmd():
    try:
        cfg = AdminConfig.load()
    except PermissionError as e:
        die(str(e)); return
    cfg.clear_token()
    cfg.save()
    click.secho("Logged out.", fg="green")


@click.command("whoami")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def whoami_cmd(env, as_json):
    cfg, client = _load_config_for_env(env)
    if not cfg.token:
        die("not logged in; run `admin login --dev --email <you>` or `admin login`")
    try:
        envelope = client.get("/admin/auth/whoami")
    except AdminClientError as e:
        die(str(e))
    data = envelope.data
    if as_json:
        emit_json(data, env=envelope.env)
    else:
        emit_table("Admin session", [
            ("email", data["email"]),
            ("scope", data["scope"]),
            ("user_id", data["user_id"]),
            ("env", envelope.env),
        ])


@click.command("ping")
@click.option("--reason", required=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def ping_cmd(reason, env, as_json):
    cfg, client = _load_config_for_env(env)
    if not cfg.token:
        die("not logged in")
    try:
        envelope = client.post("/admin/ping", {"reason": reason})
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Ping", [("pong", envelope.data["pong"]), ("admin", envelope.data["admin"]), ("audit_id", envelope.audit_id)])


@click.group("config")
def config_group():
    pass


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    cfg = AdminConfig.load()
    if key == "default_env":
        if value not in ("prod", "dev"):
            die("default_env must be prod|dev")
        cfg.default_env = value
    else:
        die(f"unknown key: {key}")
    cfg.save()
    click.secho(f"set {key}={value}", fg="green")


@config_group.command("show")
def config_show():
    cfg = AdminConfig.load()
    emit_table("Admin config", [
        ("default_env", cfg.default_env),
        ("email", cfg.email or "-"),
        ("token", "set" if cfg.token else "missing"),
    ])
