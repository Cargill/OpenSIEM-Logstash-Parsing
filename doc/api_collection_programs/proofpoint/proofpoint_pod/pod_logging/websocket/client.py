'''
The client class
'''
import certifi
import errno
import select
import six
import socket
import ssl
import threading
import websocket
import zlib

from contextlib import closing


def validate(self, skip_utf8_validation=False):
    '''Patching websocket.ABNF frame class to pass rsv1 validation
    '''
    self.rsv1 = 0
    validate.proto(self, skip_utf8_validation)


class ZlibDecoder(object):

    def __init__(self):
        self.obj = zlib.decompressobj(-zlib.MAX_WBITS)

    def decode(self, data):
        return self.obj.decompress(data + b'\x00\x00\xff\xff')


class WebSocket(websocket.WebSocket):

    def __init__(self, **kwargs):
        super(WebSocket, self).__init__(**kwargs)
        self.ping_interval = kwargs.pop('ping_interval', 0)
        self.decoder = None

    def _get_ext(self, headers):
        if headers:
            for key, value in headers.items():
                if key.lower() == 'sec-websocket-extensions':
                    return value.lower()

    def _cmp_ext(self, e1, e2):
        return sorted([v.strip() for v in e1.split(';')]) == sorted(
            [v.strip() for v in e2.split(';')])

    def connect(self, url, **options):
        super(WebSocket, self).connect(url, **options)
        extensions = self._get_ext(self.headers)
        if extensions:
            if 'header' not in options or not self._cmp_ext(
                    extensions, self._get_ext(options['header'])):
                raise websocket.WebSocketException(
                    'Unsupported websocket extensions: ' + extensions)
            if 'permessage-deflate' in extensions:
                self.decoder = ZlibDecoder()
            else:
                raise websocket.WebSocketException(
                    'Unsupported websocket compression: ' + extensions)

    def recv(self):
        data = super(WebSocket, self).recv()
        if self.decoder:
            return self.decoder.decode(data)
        return data


class Client(object):
    def __init__(self, configuration, credentials, logger):
        self.config = configuration
        self.credentials = credentials
        self.logger = logger

    def _patch_ABNF(self):
        six.PY3 = False
        validate.proto = websocket.ABNF.validate
        websocket.ABNF.validate = validate

    def _get_url(self, cid):
        if self.config.api == 'v1':
            url = '%s://%s:%s/v1/stream?cid=%s&type=%s' % (
                self.config.protocol, self.config.hostname, self.config.port,
                cid, self.config.msg_type)
            if self.config.since_time:
                url += '&sinceTime=' + self.config.since_time
            if self.config.to_time:
                url += '&toTime=' +self.config.to_time
        else:
            raise ValueError('%s PoD Logging API is not supported')
        return url

    def _pinger(fn):
        def decorator(self, ws):
            thread = event = None
            if ws.ping_interval:
                event = threading.Event()
                thread = threading.Thread(target=self._ping, args=(ws, event))
                thread.start()
            try:
                return fn(self, ws)
            finally:
                if thread and thread.isAlive():
                    event.set()
                    thread.join()
        return decorator

    def _ping(self, ws, event):
        interval = ws.ping_interval
        while not event.wait(interval):
            try:
                self.logger.debug('Pinging websocket server')
                ws.ping()
            except Exception as e:
                self.logger.warning('send_ping routine terminated: %s', e)
                break

    def create_connection(self):
        skip_utf8_validation = False
        cid, token = self.credentials
        url = self._get_url(cid)
        header = {'Authorization': 'Bearer %s' % (token,)}
        if self.config.websocket_extensions:
            skip_utf8_validation = True
            header['Sec-WebSocket-Extensions'] = self.config.websocket_extensions
        sslopt = {}
        if self.config.protocol.lower() == 'wss':
            sslopt = {'cert_reqs': ssl.CERT_REQUIRED,
                      'ca_certs': certifi.where(),
                      'check_hostname': True}
        sockopt = ((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),)
        enable_multithread = True if self.config.ping_interval else False
        websocket.enableTrace(self.config.trace)
        return websocket.create_connection(
            url,
            header=header,
            sockopt=sockopt,
            sslopt=sslopt,
            enable_multithread=enable_multithread,
            skip_utf8_validation=skip_utf8_validation,
            ping_interval=self.config.ping_interval,
            http_proxy_host=self.config.http_proxy_host, 
            http_proxy_port=self.config.http_proxy_port,
            class_=WebSocket)

    @_pinger
    def handle_connection(self, ws):
        # TODO: Error handling - 403, etc
        try:
            while ws.connected:
                r, _, _ = select.select((ws.sock,), (), ())
                if r:
                    message = ws.recv()
                    if len(message) < 1:
                        break
                    if self.config.filename:
                        self.logger.info("writing to file")
                        file_path = self.config.filename
                        with open(file_path, "ab") as output_file:
                            output_file.write(message)
                    else:
                        print(message)
                else:
                    break
        except select.error as e:
            if e[0] != errno.EINTR:
                self.logger.warning('I/O error: %s', e)

    def run(self):
        self.logger.info('PoD Logging client is starting up')
        self._patch_ABNF()
        try:
            if not self.config.hostname:
                raise ValueError('PoD Logging host is not set.')
            with closing(self.create_connection()) as ws:
                self.handle_connection(ws)
        except socket.error as e:
            self.logger.warning('Connection error: %s', e)
        except websocket.WebSocketException as e:
            self.logger.warning('Protocol error: %s', e)
        except KeyboardInterrupt as e:
            pass
        except ValueError as e:
            self.logger.warning(
                'Missing or invalid configuration value: %s', e)
        finally:
            self.logger.info('PoD Logging client is stopped')


class Pinger(object):

    def __init__(self, func):
        self.func = func

    def __call__(self, *args):
        ws = args[0]
        thread = event = None
        if ws.ping_interval:
            event = threading.Event()
            thread = threading.Thread(target=self._ping, args=(ws, event))
            thread.start()
        try:
            return self.func(*args)
        finally:
            if thread and thread.isAlive():
                event.set()
                thread.join()

    def _ping(self, ws, event):
        interval = ws.ping_interval
        while not event.wait(interval):
            try:
                #  logger.debug('Pinging websocket server')
                ws.ping()
            except Exception as e:
                #  logger.warning('send_ping routine terminated: %s', e)
                break