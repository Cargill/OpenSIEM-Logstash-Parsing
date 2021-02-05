'''
This is the configuration class.
'''

DEFAULT_PORT = 443
DEFAULT_API = 'v1'
DEFAULT_PROTOCOL = 'wss'
DEFAULT_MSG_TYPE = 'message'


class Config(object):

    def __init__(self, hostname, port=DEFAULT_PORT, protocol=DEFAULT_PROTOCOL,
                 api=DEFAULT_API, msg_type=DEFAULT_MSG_TYPE, since_time=None, to_time=None, filename=None,
                 ping_interval=0, websocket_extensions=None, trace=False,
                 http_proxy_host=None, http_proxy_port=None):
        if not hostname:
            raise ValueError('PoD Logging hostname is empty')
        self.hostname = hostname
        self.port = port or DEFAULT_PORT
        self.protocol = protocol or DEFAULT_PROTOCOL
        self.api = api or DEFAULT_API
        self.msg_type = msg_type or DEFAULT_MSG_TYPE
        self.since_time = since_time
        self.to_time = to_time
        self.filename = filename
        self.ping_interval = float(ping_interval) if ping_interval else 0
        self.websocket_extensions = websocket_extensions
        self.trace = trace
        self.http_proxy_port = http_proxy_port
        self.http_proxy_host = http_proxy_host