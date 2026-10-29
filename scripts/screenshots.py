"""Screenshots and a short demo GIF of the web UI (needs a running server).

    uvicorn copilot.api:app --port 8077 &
    python scripts/screenshots.py --url http://localhost:8077
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8077")
    args = ap.parse_args()
    ASSETS.mkdir(exist_ok=True)
    frames: list[Image.Image] = []

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1180, "height": 860}, device_scale_factor=1)

        def snap(name: str | None = None, hold: int = 1):
            png = page.screenshot(full_page=False)
            if name:
                (ASSETS / name).write_bytes(png)
            img = Image.open(io.BytesIO(png)).convert("RGB").resize((885, 645))
            frames.extend([img] * hold)

        def login(username: str):
            page.goto(args.url)
            page.wait_for_selector(f'button[data-u="{username}"]')
            page.click(f'button[data-u="{username}"]')
            page.wait_for_selector("#q")

        def ask(q: str):
            page.fill("#q", "")
            page.type("#q", q, delay=8)
            snap(hold=1)
            page.click("#ask-form button")
            page.wait_for_selector(".answer")
            page.wait_for_timeout(250)

        page.goto(args.url)
        page.wait_for_selector(".users button")
        snap("01_login.png", hold=3)

        login("olga.operator")
        ask("What torque for the M10 flange bolts?")
        snap("02_operator_torque.png", hold=5)
        ask("What are the steps of lockout tagout?")
        snap("03_operator_procedure.png", hold=5)
        ask("What was the root cause of the oil leakage complaint?")
        snap("04_operator_restricted.png", hold=5)

        login("quinn.quality")
        ask("What was the root cause of the oil leakage complaint?")
        snap("05_quality_same_question.png", hold=5)

        login("emre.engineer")
        ask("What was the flange bolt torque in revision B of WI-ASM-014?")
        snap("06_engineer_old_revision.png", hold=5)
        page.click('.tab[data-tab="docs"]')
        page.wait_for_timeout(300)
        snap("07_documents_by_role.png", hold=4)
        b.close()

    frames[0].save(ASSETS / "demo.gif", save_all=True, append_images=frames[1:], duration=700, loop=0,
                   optimize=True)
    print(f"saved {len(list(ASSETS.glob('*.png')))} screenshots and demo.gif ({len(frames)} frames)")


if __name__ == "__main__":
    main()
