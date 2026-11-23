"""Serve the shared shell and the three pages of the local workbench."""
from pathlib import Path
from string import Template

from fastapi.responses import HTMLResponse


PRESENTATION = Path(__file__).parent / "presentation"
PAGES = {
    "endurance": ("续航与路线", PRESENTATION.parents[1] / "endurance/presentation/index.html"),
    "simulation": ("巡看仿真", PRESENTATION / "live.html"),
    "history": ("运行记录", PRESENTATION / "history.html"),
}


def render_workbench(section):
    title, content = PAGES[section]
    shell = Template((PRESENTATION / "workbench.html").read_text(encoding="utf-8"))
    current = {f"{name}_current": ' aria-current="page"' if name == section else "" for name in PAGES}
    markup = content.read_text(encoding="utf-8")
    if section in {"simulation", "history"}:
        detail = (PRESENTATION / "mission-detail.html").read_text(encoding="utf-8")
        markup = markup.replace("<!-- mission-detail -->", detail)
    return HTMLResponse(shell.substitute(
        title=title, section=section, content=markup, **current,
    ))
