"""Export the final PPTX with bundled LO and a private, explicit font configuration."""
from pathlib import Path
import json
import os
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "output/4C/.build/presentation"
RUNTIME = Path("/Users/kedong/.cache/codex-runtimes/codex-primary-runtime/dependencies")
LO = RUNTIME / "bin/override/soffice"
result = json.loads((BUILD / "build-result.json").read_text())
pptx = Path(result["pptx"])
font_dir = ROOT / "output/4C/.build/fonts"
font_config = BUILD / "fonts.conf"
cache = BUILD / "fontconfig-cache"
cache.mkdir(exist_ok=True)
config = ET.Element("fontconfig")
ET.SubElement(config, "dir").text = str(font_dir)
ET.SubElement(config, "dir").text = str(RUNTIME / "native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/Resources/fonts/truetype")
ET.SubElement(config, "cachedir").text = str(cache)
ET.ElementTree(config).write(font_config, encoding="UTF-8", xml_declaration=True)
env = dict(os.environ)
env.update(FONTCONFIG_FILE=str(font_config), FONTCONFIG_PATH=str(BUILD), SAL_FONTPATH=str(font_dir))
pdf_dir = BUILD / "pdf-export"
pdf_dir.mkdir(exist_ok=True)
subprocess.run([str(LO), f"-env:UserInstallation={(BUILD / 'lo-profile-fonts').as_uri()}", "--headless", "--convert-to", "pdf", "--outdir", str(pdf_dir), str(pptx)], env=env, check=True)
print(pdf_dir / pptx.with_suffix(".pdf").name)
