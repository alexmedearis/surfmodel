"""Build the website for one environment: copy web/ to build/web with a config.js that points
at that environment's data (deploy/<env>.env).

  python deploy/build_web.py emulator | staging | prod
"""
import json, os, shutil, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_env(name):
    path = os.path.join(HERE, "deploy", f"{name}.env")
    if not os.path.exists(path):
        sys.exit(f"no settings for '{name}': expected {os.path.relpath(path, HERE)}")
    env = {}
    for line in open(path):
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env

def build(name):
    env = load_env(name)
    out = os.path.join(HERE, "build", "web")
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(os.path.join(HERE, "web"), out)
    cfg = dict(env=name, storage=dict(host=env["STORAGE_HOST"], bucket=env["BUCKET"]))
    with open(os.path.join(out, "config.js"), "w") as fh:
        fh.write(f"// Built by deploy/build_web.py for '{name}'.\nwindow.SURF_CONFIG = {json.dumps(cfg)};\n")
    print(f"built build/web for {name}: data from {env['BUCKET']}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
