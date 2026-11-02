"""Use IPv4 for Fyers HTTPS calls to match the server's registered static IP."""
import http.client
import socket
import urllib.request
from requests.utils import default_user_agent


def connect_ipv4(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    last_error = None
    for family, kind, proto, _, endpoint in socket.getaddrinfo(
            address[0], address[1], socket.AF_INET, socket.SOCK_STREAM):
        connection = socket.socket(family, kind, proto)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            connection.connect(endpoint)
            return connection
        except OSError as error:
            last_error = error
            connection.close()
    raise last_error or OSError('No IPv4 address for Fyers endpoint')


class IPv4HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = connect_ipv4


class IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(IPv4HTTPSConnection, request,
                            context=self._context)


_opener = urllib.request.build_opener(IPv4HTTPSHandler())


def urlopen_ipv4(request, timeout=20):
    # FYERS edge rejects the default Python-urllib agent (403 / 1010).
    # Match the HTTP client identifier used by its official requests-based SDK.
    if isinstance(request, str):
        request = urllib.request.Request(request)
    if not request.has_header('User-agent'):
        request.add_header('User-Agent', default_user_agent())
    return _opener.open(request, timeout=timeout)
