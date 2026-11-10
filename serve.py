"""Run the website locally: http://localhost:8000

  python serve.py [port]

Serves the site (web/) and the published data files (out/data, written by publish.py) at
data/, the way the deployed site will see them. Publish first: python publish.py
"""
import functools, http.server, os, sys
import config

WEB = os.path.join(config.HERE, "web")
DATA = os.path.join(config.OUT, "data")

class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = path.split("?", 1)[0].split("#", 1)[0]
        if p == "/data" or p.startswith("/data/"):
            rel = p[len("/data"):].lstrip("/")
            full = os.path.realpath(os.path.join(DATA, rel))
            return full if full.startswith(os.path.realpath(DATA)) else DATA
        return super().translate_path(path)
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")          # always show the latest while developing
        super().end_headers()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    if not os.path.exists(os.path.join(DATA, "v1", "spots", "index.json")):
        print("no published data yet: run  python publish.py  first")
    print(f"http://localhost:{port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=WEB)).serve_forever()
