# api.py: the HTTP API of Adventure Land: log in, read the server and character
# lists, and make the WebSocket URL of a game server.
# Needs: pip install httpx==0.27.2
#
# The HTTP API is on the website (AL_BASE_URL), not on the game servers. Every
# call is a POST of a JSON object to /api/<method> (common_engine/handlers.js:1).
# The reply is HTTP 200 with a JSON object, also when the call fails: then the
# object has `failed: true` and a `reason`. Extra replies come in a list `infs`.
import os
from dataclasses import dataclass
from typing import Any, TypedDict
from urllib.parse import urlsplit

import httpx

# A server and a character are the JSON objects of the server list, kept as
# dicts. The fields that the course reads:
#   Server:    name ("I"), region ("EU"), players, key ("SR_EUI"), address, path
#   Character: id ("CH_..."), name, type (the class), level, server (only when online)
Server = dict[str, Any]
Character = dict[str, Any]


@dataclass(frozen=True)
class Auth:
    """A login session. AL_AUTH holds it as one string: <user>-<auth>."""

    user: str  # the user id, for example "US_tester"
    auth: str  # the session token


class ServersAndCharacters(TypedDict):
    servers: list[Server]
    characters: list[Character]


def base_url() -> str:
    """The website and its HTTP API: AL_BASE_URL, or the live site."""
    return (os.environ.get("AL_BASE_URL") or "https://adventure.land").rstrip("/")


# region api-call
async def api_call(method: str, body: dict[str, Any] | None = None, auth: Auth | None = None) -> dict[str, Any]:
    """POST `body` as JSON to /api/<method>. Returns the parsed JSON reply, also
    when it has `failed` (the caller decides what a failure means). Raises
    httpx.HTTPStatusError for an HTTP status other than 200: that is a network
    or server problem, not a game answer."""
    headers = {}
    if auth is not None:
        # After the login, the session goes in a cookie: auth=<user>-<auth>.
        headers["Cookie"] = f"auth={auth.user}-{auth.auth}"
    # 15 s: much more than a normal reply needs, but a slow link can be slow.
    async with httpx.AsyncClient(timeout=15) as http:
        res = await http.post(f"{base_url()}/api/{method}", json=body or {}, headers=headers)
    if res.status_code != 200:
        res.raise_for_status()  # 4xx and 5xx raise here
        raise RuntimeError(f"{method}: HTTP {res.status_code}")  # 1xx and 3xx
    data: dict[str, Any] = res.json()
    return data
# endregion api-call


def parse_auth(text: str) -> Auth:
    """Split "<user>-<auth>" at the FIRST dash (a user id has no dash)."""
    user, dash, auth = text.strip().partition("-")
    if not dash or not user or not auth:
        raise ValueError("AL_AUTH must look like <user>-<auth>")
    return Auth(user, auth)


# region login
async def login() -> Auth:
    """Use AL_AUTH when it is set: then no password goes over the network. Only
    when AL_AUTH is empty, log in with AL_EMAIL and AL_PASSWORD, and print the
    AL_AUTH value to save. Each password login adds a token to the account
    (200 at most), so do it one time, not on each run."""
    saved = os.environ.get("AL_AUTH")
    if saved:
        return parse_auth(saved)
    email = os.environ.get("AL_EMAIL")
    password = os.environ.get("AL_PASSWORD")
    if not email or not password:
        raise RuntimeError("set AL_AUTH, or AL_EMAIL and AL_PASSWORD")

    # only_login: never make a new account by mistake (api.js:84-133).
    data = await api_call("signup_or_login", {"email": email, "password": password, "only_login": True})
    # Success: {"success": true, "user", "auth", ...}. Failure: {"failed": true, "reason"}.
    if data.get("success") is not True:
        raise RuntimeError(f"login failed: {data.get('reason', 'unknown reason')}")
    auth = Auth(data["user"], data["auth"])
    value = f"{auth.user}-{auth.auth}"
    print("Logged in with the password. Save this value, and use it from now on:")
    print(f"  export AL_AUTH='{value}'")
    print(f"  PowerShell: $env:AL_AUTH = '{value}'")
    return auth
# endregion login


# region servers-and-characters
async def servers_and_characters(auth: Auth) -> ServersAndCharacters:
    """The two lists come in the `infs` item of type "servers_and_characters"
    (api.js:451-472)."""
    data = await api_call("servers_and_characters", {}, auth)
    if data.get("reason") == "not_logged_in":
        raise RuntimeError("the token in AL_AUTH is not valid any more. "
                           "Unset AL_AUTH and log in with the password again.")
    if data.get("failed"):
        raise RuntimeError(f"servers_and_characters failed: {data.get('reason')}")
    for inf in data.get("infs", []):
        if inf.get("type") == "servers_and_characters":
            return {"servers": inf["servers"], "characters": inf["characters"]}
    raise RuntimeError(f"servers_and_characters: unexpected reply {str(data)[:200]}")
# endregion servers-and-characters


# region find-server
def find_server(servers: list[Server], key: str | None = None) -> Server:
    """The server whose region + name is `key` (for example "EUI"). The key
    comes from AL_SERVER when not given. An empty key means the first server
    of the list (the list is in the order EU, US, ASIA)."""
    if key is None:
        key = os.environ.get("AL_SERVER", "")
    if not servers:
        raise RuntimeError("the server list is empty")
    if not key:
        return servers[0]
    for s in servers:
        if s["region"] + s["name"] == key:
            return s
    names = ", ".join(s["region"] + s["name"] for s in servers)
    raise RuntimeError(f"no server {key}; the list has: {names}")
# endregion find-server


def find_character(characters: list[Character], name: str | None = None) -> Character:
    """The character called `name` (AL_CHARACTER when not given). The match is
    exact: the name, not the id (CH_...)."""
    if name is None:
        name = os.environ.get("AL_CHARACTER", "")
    if not name:
        raise RuntimeError("set AL_CHARACTER to the name of a character (run login.py to see the list)")
    for c in characters:
        if c["name"] == name:
            return c
    names = ", ".join(c["name"] for c in characters)
    raise RuntimeError(f"no character {name}; the list has: {names}")


# region socket-url
def socket_url(server: Server, base: str | None = None) -> str:
    """The WebSocket URL of a game server. The scheme follows the website:
    http -> ws, https -> wss. The path must end with exactly one "/" (the
    server matches "/ws1/"). The two options at the end are the ones that the
    browser client sends (js/game.js:1525): map_protocol=1 says that we accept
    generated maps, and no_graphics=1 asks for no tile data in them."""
    scheme = "wss" if urlsplit(base or base_url()).scheme == "https" else "ws"
    path = server["path"].rstrip("/")
    return (f"{scheme}://{server['address']}{path}/"
            "?EIO=4&transport=websocket&map_protocol=1&no_graphics=1")
# endregion socket-url
