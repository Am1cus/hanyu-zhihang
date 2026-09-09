"""Copy the existing local web/backend/demo source into the GitHub repository.

Explicit source allowlist. Never copy databases, raw datasets, dependencies,
private configuration, hidden files or symlinks. Existing source paths stay put.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="Parent containing LSTM and project")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    workspace = args.workspace.resolve()
    if (workspace / "LSTM/learn").resolve() != repo:
        parser.error("Expected the existing LSTM/learn checkout; no arbitrary source copying")
    allowed = {".java", ".vue", ".js", ".css", ".html", ".sql", ".xml", ".json", ".svg", ".png", ".ico"}
    pairs = []
    for project in ("cold-region-aviation-frontend", "cold-region-aviation-backend"):
        source = workspace / "project" / project
        for folder in ("src", "public", "tests"):
            for path in sorted((source / folder).rglob("*")):
                relative = path.relative_to(source)
                if path.is_file() and not path.is_symlink() and path.suffix in allowed and not any(p.startswith(".") for p in relative.parts):
                    pairs.append((path, repo / "platform" / project / relative))
        for name in ("package.json", "package-lock.json", "vite.config.js", "index.html", "pom.xml",
                     "src/main/resources/application.yml", "src/main/resources/application-demo.yml"):
            path = source / name
            if path.is_file(): pairs.append((path, repo / "platform" / project / name))
    for path in sorted((workspace / "LSTM/demo").iterdir()):
        if path.is_file() and path.suffix in {".sh", ".py", ".js", ".md"}:
            pairs.append((path, repo / "demo" / path.name))
    manifest = {"scope": "frontend_backend_demo_source_only", "files": {}}
    for source, destination in pairs:
        if source.is_symlink() or destination.is_symlink(): raise ValueError("Symlinks not allowed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == digest
        manifest["files"][destination.relative_to(repo).as_posix()] = digest
    (repo / "workspace-source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Verified {len(manifest['files'])} source files; original workspace untouched.")


if __name__ == "__main__": main()
