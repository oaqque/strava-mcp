# Strava MCP Server

`strava-mcp` is a standalone MCP server for read-only personal Strava inspection.

It includes:

- a thin MCP surface in `src/strava_mcp/server.py`
- a small CLI in `src/strava_mcp/main.py`
- a local Strava auth and API layer in `src/strava_mcp/strava/`

Local auth state is stored in:

- `vault/strava/app.json` for Strava app credentials
- `vault/strava/session.json` for the personal session

Those files are intentionally ignored by git.

## Setup

Install dependencies:

```bash
uv sync
```

Create or inspect your Strava developer app:

1. Sign in to Strava with the athlete account you want to use.
2. Open `https://www.strava.com/settings/api`.
3. Create an API application if needed.
4. Copy the `Client ID` and `Client Secret`.
5. Set `Authorization Callback Domain` to the host used by your redirect URI.
   For the example below, use `127.0.0.1`.
6. Save the app settings.

Configure Strava app credentials in `vault/strava/app.json`:

```json
{
  "client_id": 12345,
  "client_secret": "your-strava-client-secret",
  "redirect_uri": "http://127.0.0.1:8765/exchange_token"
}
```

If `vault/strava/app.json` is missing, `uv run strava-mcp authorize start` will
prompt for these values and create the file for you.

## One-Time Authorization

Generate the authorization URL:

```bash
uv run strava-mcp authorize start --launch-browser
```

After approving access in Strava, copy the full redirect URL from the browser and complete the token exchange:

```bash
uv run strava-mcp authorize complete --state '<state-from-start>'
```

For non-interactive usage:

```bash
uv run strava-mcp authorize complete \
  --state '<state-from-start>' \
  --callback-url 'http://127.0.0.1:8765/exchange_token?state=...&code=...'
```

This writes the local auth state to `vault/strava/session.json`.

## Run The Server

For direct local use:

```bash
uv run strava-mcp serve
```

Optional transports:

```bash
uv run strava-mcp serve --transport sse --host 127.0.0.1 --port 8000
uv run strava-mcp serve --transport streamable-http --host 127.0.0.1 --port 8000
```

## Register With Codex

From this repo root:

```bash
codex mcp add strava -- uv run strava-mcp serve
codex mcp get strava --json
```

## Tools

The server exposes these read-only tools:

- `get_athlete_profile`
- `get_athlete_stats`
- `get_athlete_zones`
- `list_activities`
- `get_activity_detail`
- `get_activity_streams`

## Example Prompts

- `Use the strava MCP server to show my last 5 activities with sport type, distance, and start date.`
- `Fetch my athlete stats and summarize year-to-date ride totals.`
- `Get activity detail for the most recent ride and then fetch heartrate and watts streams.`
- `Inspect my athlete zones and tell me whether power zones are configured.`
