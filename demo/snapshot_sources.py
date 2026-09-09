"""Create a local, hash-indexed implementation snapshot without publishing data.

Not a replacement for a Git history: records the exact source/release bytes of
one acceptance revision. Does not alter the user's repositories or source files.
"""
import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error("Use a new output directory")
    root = Path(__file__).resolve().parents[1]
    project = root.parent / "project"
    frontend = project / "cold-region-aviation-frontend"
    backend = project / "cold-region-aviation-backend"
    files = {}
    allowed = {".py", ".java", ".js", ".vue", ".css", ".html", ".sql", ".xml", ".sh", ".md", ".json", ".svg", ".png", ".ico", ".txt", ".pt"}

    def include_tree(directory, label):
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(directory)
            if path.is_file() and not path.is_symlink() and path.suffix in allowed and not any(p.startswith(".") or p == "__pycache__" for p in relative.parts):
                files[f"{label}/{relative.as_posix()}"] = path

    def include_file(path, label):
        if path.is_file() and not path.is_symlink(): files[label] = path

    for directory, label in [(frontend / "src", "project/cold-region-aviation-frontend/src"),
                             (frontend / "public", "project/cold-region-aviation-frontend/public"),
                             (frontend / "tests", "project/cold-region-aviation-frontend/tests"),
                             (backend / "src", "project/cold-region-aviation-backend/src"),
                             (root / "learn/tests", "LSTM/learn/tests"),
                             (root / "learn/Phase3", "LSTM/learn/Phase3"),
                             (root / "learn/Phase4/releases/energy_residual_lstm_v3_rc1", "LSTM/learn/Phase4/releases/energy_residual_lstm_v3_rc1")]:
        include_tree(directory, label)
    for directory, label in [(root / "demo", "LSTM/demo"), (root / "learn/Phase4", "LSTM/learn/Phase4")]:
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix in allowed:
                include_file(path, f"{label}/{path.name}")
    for name in ("package.json", "package-lock.json", "vite.config.js", "index.html"):
        include_file(frontend / name, f"project/cold-region-aviation-frontend/{name}")
    include_file(backend / "pom.xml", "project/cold-region-aviation-backend/pom.xml")
    include_file(backend / "src/main/resources/application-demo.yml", "project/cold-region-aviation-backend/src/main/resources/application-demo.yml")
    include_file(root / "learn/requirements.txt", "LSTM/learn/requirements.txt")
    args.output.mkdir(parents=True)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "scope": "local_source_snapshot_not_complete_environment_backup",
                "excluded": ["raw datasets", "databases", "node_modules and Python environments", "training experiment directories", "production/local YAML configs", "existing Git histories", "legacy V1/V2 model assets"],
                "learn_git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root / "learn", text=True).strip(), "files": {}}
    archive = args.output / "source-snapshot.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, path in sorted(files.items()):
            content = path.read_bytes()
            manifest["files"][name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = path.stat().st_mode & 0o777
            tar.addfile(info, io.BytesIO(content))
    manifest["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.output / "source-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    with tarfile.open(archive, "r:gz") as tar:
        assert len(tar.getmembers()) == len(files)
        for name, entry in manifest["files"].items():
            assert hashlib.sha256(tar.extractfile(name).read()).hexdigest() == entry["sha256"]
    print(json.dumps({"file_count": len(files), "archive_bytes": archive.stat().st_size,
                      "archive_sha256": manifest["archive_sha256"], "verified": True}))


if __name__ == "__main__": main()
