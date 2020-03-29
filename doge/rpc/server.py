# coding: utf-8

import logging
import signal

from gevent.server import StreamServer
from mprpc import RPCServer
from mprpc.exceptions import MethodNotFoundError

from doge.config.config import Config
from doge.rpc.context import Context
from doge.common.exceptions import ServerLoadError
from doge.common.doge import Request

logger = logging.getLogger("doge.rpc.server")


class DogeRPCServer(RPCServer):
    def __init__(self, context, cls):
        super(DogeRPCServer, self).__init__()
        self._name = context.url.get_param("name")
        self._filter = context.get_filter(self)
        self._methods = cls()

    def __getattr__(self, method_name):
        if not hasattr(self._methods, method_name):
            raise MethodNotFoundError('Method not found: %s', method_name)

        def function(*args):
            req = Request(self._name, method_name, *args[1:], meta=args[0])
            return self._filter.execute(req)
        return function

    def execute(self, req):
        method = getattr(self._methods, req.method)
        return method(*req.args)


class Server(object):
    def __init__(self, context):
        self.name = context.url.get_param("name")
        self.url = context.url
        self.context = context
        self.registry = context.get_registry()
        self.handler = None
        self.limit = context.url.get_param("limitConn", "default")

    def load(self, cls):
        u"""加载RPC methods类"""
        self.handler = DogeRPCServer(self.context, cls)

    def register(self):
        u"""向registry服务"""
        self.registry.register(self.name, self.url)

    def handle_signal(self):
        u"""注册信号"""

        def handler(signum, frame):
            self.registry.deregister(self.name, self.url)

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def run(self):
        u"""启动RPC服务"""
        if not self.handler:
            raise ServerLoadError("Methods not exits.")

        logger.info(
            "Starting server at %s:%s" % (self.url.host, str(self.url.port)))

        self.handle_signal()

        server = StreamServer(
            (self.url.host, self.url.port), self.handler, spawn=self.limit
        )

        self.register()

        server.serve_forever()

    def __call__(environ, start_response):
        # for gunicorn wsgi app
        pass


def new_server(config_file):
    u"""从配置文件生成server"""
    config = Config(config_file)
    context = Context(config.parse_service(), config.parse_registry())
    return Server(context)
