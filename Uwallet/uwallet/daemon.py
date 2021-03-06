#-*- coding: UTF-8 -*-
import ast
import os

import jsonrpclib
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCRequestHandler, SimpleJSONRPCServer

from uwallet.commands import Commands, known_commands
from uwallet.util import DaemonThread
import thread
import time
from multiprocessing import Process

def lockfile(config):
    return os.path.join(config.path, 'daemon')


def get_daemon(config):
    try:
        with open(lockfile(config)) as f:
            host, port = ast.literal_eval(f.read())
    except:
        return
    server = jsonrpclib.Server('http://%s:%d' % (host, port))
    # check if daemon is running
    try:
        server.ping()
        return server
    except:
        pass


class RequestHandler(SimpleJSONRPCRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Headers",
                         "Origin, X-Requested-With, Content-Type, Accept")
        self.send_header("Access-Control-Allow-Origin", "*")
        SimpleJSONRPCRequestHandler.end_headers(self)


class Daemon(DaemonThread):
    def __init__(self, config, network):
        DaemonThread.__init__(self)
        self.config = config
        self.network = network
        self.cmd_runner = Commands(self.config, self.network)

        host = config.get('rpchost', '0.0.0.0')
        port = config.get('rpcport', 8000)
        self.server = SimpleJSONRPCServer((host, port), requestHandler=RequestHandler,
                                          logRequests=False)
        with open(lockfile(config), 'w') as f:
            f.write(repr(self.server.socket.getsockname()))
        self.server.timeout = 0.1
        for cmdname in known_commands:
            # rpc直接调用命令 --hetao
            self.server.register_function(getattr(self.cmd_runner, cmdname), cmdname)
        self.server.register_function(self.ping, 'ping')
        self.server.register_function(self.run_daemon, 'daemon')

    def ping(self):
        return True

    def run_daemon(self, config):
        sub = config.get('subcommand')
        assert sub in ['start', 'stop', 'status']
        if sub == 'start':
            response = "Daemon already running"
        elif sub == 'status':
            p = self.network.get_parameters()
            response = {
                'path': self.network.config.path,
                'server': p[0],
                'blockchain_height': self.network.get_local_height(),
                'server_height': self.network.get_server_height(),
                'nodes': self.network.get_interfaces(),
                'connected': self.network.is_connected(),
                'auto_connect': p[3],
                'wallets': dict([(k, w.is_up_to_date()) for k, w in self.wallets.items()]),
            }
        elif sub == 'stop':
            self.stop()
            response = "Daemon stopped"
        return response


    def run(self):
        i = 0
        while self.is_running():
            # self.server.handle_request()
            try:
                thread.start_new_thread(self.server.handle_request, ())
                time.sleep(0.01)
                i = i+1
            except Exception,ex:
                i = 0
                print ex
                continue
        os.unlink(lockfile(self.config))

    def runProc(self):
        i = 0
        while True:
            try:
                p = Process(target=self.server.handle_request, args=((),))
                p.start()
                p.join()
                i = i+1
            except Exception,ex:
                i = 0
                print ex
                continue
        os.unlink(lockfile(self.config))

    def stop(self):
        for k, wallet in self.wallets.items():
            wallet.stop_threads()
        DaemonThread.stop(self)
