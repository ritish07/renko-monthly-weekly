"""Service-local correction for FYERS full-mode index delta decoding."""
import inspect
import textwrap
from types import SimpleNamespace


def install():
    from fyers_apiv3.FyersWebsocket import data_ws
    # The SDK's symbol-token HTTP POST otherwise has no timeout and can stall
    # the reconnect supervisor indefinitely. Limit only this module's calls.
    if not isinstance(data_ws.requests, SimpleNamespace):
        requests = data_ws.requests
        def post(*args, **kwargs):
            kwargs.setdefault('timeout', 3)
            return requests.post(*args, **kwargs)
        data_ws.requests = SimpleNamespace(get=requests.get, post=post)
    cls = data_ws.FyersDataSocket
    name = '_FyersDataSocket__datafeed_resp'
    original = getattr(cls, name)
    if getattr(original, '_renko_fixed', False):
        return
    source = textwrap.dedent(inspect.getsource(original))
    broken = 'value != "-2147483648"'
    if broken not in source:
        return  # Newer SDKs already compare the integer sentinel correctly.
    # Compile inside a class to preserve Python's private attribute mangling.
    source = source.replace(broken, 'value != -2147483648')
    namespace = {}
    exec('class FyersDataSocket:\n' + textwrap.indent(source, '    '),
         vars(data_ws), namespace)
    fixed = getattr(namespace['FyersDataSocket'], name)
    fixed._renko_fixed = True
    setattr(cls, name, fixed)
