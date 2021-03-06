# Copyright: Damien Elmes <anki@ichi2.net>
# -*- coding: utf-8 -*-
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from aqt.qt import *
from http import HTTPStatus
import http.server
import socketserver
import errno
from anki.utils import devMode
import threading

# locate web folder in source/binary distribution
def _getExportFolder():
    # running from source?
    srcFolder = os.path.join(os.path.dirname(__file__), "..")
    webInSrcFolder = os.path.abspath(os.path.join(srcFolder, "web"))
    if os.path.exists(webInSrcFolder):
        return webInSrcFolder
    elif isMac:
        dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(dir + "/../../Resources/web")
    else:
      raise Exception("couldn't find web folder")

_exportFolder = _getExportFolder()

# webengine on windows sometimes opens a connection and fails to send a request,
# which will hang the server if unthreaded
class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    request_queue_size = 100

class MediaServer(threading.Thread):

    _port = None
    _ready = threading.Event()

    def run(self):
        self.server = ThreadedHTTPServer(("localhost", 0), RequestHandler)
        self._ready.set()
        self.server.serve_forever()

    def getPort(self):
        self._ready.wait()
        return self.server.server_port

    def shutdown(self):
        self.server.shutdown()

class RequestHandler(http.server.SimpleHTTPRequestHandler):

    timeout = 1

    def do_GET(self):
        f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            except Exception as e:
                if devMode:
                    print("http server caught exception:", e)
                else:
                    # swallow it - user likely surfed away from
                    # review screen before an image had finished
                    # downloading
                    pass
            finally:
                f.close()

    def send_head(self):
        path = self.translate_path(self.path)
        path = self._redirectWebExports(path)
        if os.path.isdir(path):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        ctype = self.guess_type(path)
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", ctype)
            fs = os.fstat(f.fileno())
            self.send_header("Content-Length", str(fs[6]))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return f
        except:
            f.close()
            raise

    def log_message(self, format, *args):
        if not devMode:
            return
        print("%s - - [%s] %s" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format%args))

    # catch /_anki references and rewrite them to web export folder
    def _redirectWebExports(self, path):
        targetPath = os.path.join(os.getcwd(), "_anki")
        if path.startswith(targetPath):
            newPath = os.path.join(_exportFolder, path[len(targetPath)+1:])
            return newPath
        return path
