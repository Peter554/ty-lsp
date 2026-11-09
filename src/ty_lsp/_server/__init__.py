"""A long-lived ``ty server`` that later CLI commands send their queries to.

Starting ``ty server`` and letting it index the project is most of the time of a
query, so ``ty-lsp serve`` does it once. Other ``ty-lsp`` commands in the same
project find the server's Unix socket and send it their arguments; it runs them
the way the command line would, and sends back the output and exit code. Without a
server they run as before.

With ``--start-server`` a command starts the server itself if none is running, and
the server stops after a while without requests (``serve --idle-timeout``).

The ty server does not watch the files, so a watcher (``watchfiles``) collects the
changes, and they are sent to ty before the next request.

The modules: ``_common`` (where the socket and log are, and what a server says about
itself), ``_client`` (what other commands use to reach a server), ``_changes`` (the
file watcher) and ``_server`` (the server itself).
"""

from ._client import forward, list_servers, stop
from ._common import ServerInfo
from ._server import Server

__all__ = ["Server", "ServerInfo", "forward", "list_servers", "stop"]
