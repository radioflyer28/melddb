"""Install each release artifact in isolation and exercise its shipped workflows."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command, **kwargs):
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def qualify(artifacts):
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Qualification requires uv")
    repository = Path(__file__).resolve().parents[1]
    results = []
    for artifact in artifacts:
        artifact = artifact.resolve()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            env.pop("MELDDB_TEST_POSTGRES", None)
            run([uv, "venv", "--python", sys.executable, root / "env"], env=env)
            python = root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run([uv, "pip", "install", "--python", python, "--no-deps", artifact], env=env)
            probe = subprocess.check_output([str(python), "-I", "-c",
                "import json,sqlite3,melddb,importlib.metadata as m; "
                "assert not [d for d in m.requires('melddb') or [] if 'extra ==' not in d]; "
                "assert m.metadata('melddb')['License-Expression'] == 'Apache-2.0'; "
                "assert any(str(p).endswith('/licenses/LICENSE') for p in m.files('melddb')); "
                "print(json.dumps({'python':__import__('platform').python_version(),"
                "'sqlite':sqlite3.sqlite_version,'package':melddb.__file__,'version':m.version('melddb')}))"],
                cwd=root, env=env, text=True)
            details = json.loads(probe)
            assert Path(details["package"]).is_relative_to(root / "env")
            for folder in ("examples", "tests", "validation", "compat"):
                shutil.copytree(repository / folder, root / folder,
                                ignore=shutil.ignore_patterns("__pycache__"))
            for example in sorted((root / "examples").glob("*.py")):
                args = [root / "workflows"] if example.stem == "workflows" else (
                    [root / "queries"] if example.stem == "query_crud" else [])
                run([python, "-I", example, *args], cwd=root, env=env)
            # Test tooling is installed only after the dependency-free smoke run.
            run([uv, "pip", "install", "--python", python, "pytest>=8", "hypothesis>=6", "sqlalchemy>=2,<3"], env=env)
            run([python, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], cwd=root, env=env)
            results.append({"artifact": artifact.name, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                            **{k: v for k, v in details.items() if k != "package"},
                            "isolated_install": True, "all_examples": True, "installed_suite": "passed"})
    return {"platform": platform.platform(), "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(qualify(args.artifacts), indent=2) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
