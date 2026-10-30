"""Exercise the actual entry point and port ownership without a browser."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest

from competition.v2.launch import PROJECT
from competition.v2.version import API_VERSION


class LaunchTests(unittest.TestCase):
    def launch(self, *args):
        return subprocess.run([sys.executable, str(PROJECT/'competition/v2/launch.py'),
                               '--no-browser', *args], cwd=PROJECT.parent,
                              capture_output=True, text=True, timeout=15)

    def service(self, ours, api_version=API_VERSION):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                payload = {'status': 'ok', 'source': 'LOCAL_2D_SIM' if ours else 'other_app',
                           'runtime_version': 'competition-v2-runtime-0.1', 'api_version':api_version}
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_direct_script_check_avoids_stdlib_selectors_shadowing(self):
        result = self.launch('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['ready'])
        self.assertEqual(report['dependency_mismatches'], [])
        self.assertEqual(Path(report['project']), PROJECT)

    def test_duplicate_launch_reuses_our_service(self):
        server = self.service(True)
        result = self.launch('--port', str(server.server_port))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('已经启动', result.stdout)

    def test_unrelated_port_is_reported_without_killing_it(self):
        server = self.service(False)
        result = self.launch('--port', str(server.server_port))
        self.assertEqual(result.returncode, 1)
        self.assertIn('被其他程序占用', result.stderr)
        self.assertNotEqual(server.socket.fileno(), -1)

    def test_explicit_database_does_not_silently_reuse_unknown_database(self):
        server = self.service(True)
        result = self.launch('--port', str(server.server_port), '--db', 'different.sqlite3')
        self.assertEqual(result.returncode, 1)
        self.assertIn('不能确认其记录库', result.stderr)

    def test_invalid_port_does_not_start_server(self):
        result = self.launch('--port', '99999')
        self.assertEqual(result.returncode, 2)
        self.assertIn('端口需要', result.stderr)

    def test_old_api_service_is_not_silently_reused(self):
        server = self.service(True, api_version=None)
        result = self.launch('--port', str(server.server_port))
        self.assertEqual(result.returncode, 1)
        self.assertIn('被其他程序占用', result.stderr)


if __name__ == '__main__':
    unittest.main()
