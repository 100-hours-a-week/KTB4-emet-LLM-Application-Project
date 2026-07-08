"""
2단계: recipe_ids.json에 담긴 레시피들을 하나씩 PDF로 저장
사용법: python save_recipes_pdf.py [시작인덱스] [끝인덱스]
       -> 예: python save_recipes_pdf.py 0 200   (0번째부터 199번째까지만 처리, 배치 실행용)
"""
## 0 300
## 300 500

import asyncio
import json
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

BASE = "https://www.10000recipe.com"
INPUT_FILE = "recipe_ids.json"
OUTPUT_DIR = Path("./recipe_pdfs")
OUTPUT_DIR.mkdir(exist_ok=True)

DELAY_SEC = 5.0  # 레시피 간 딜레이 (서버 부하 최소화 목적, 절대 줄이지 마세요)
MAX_CONSECUTIVE_FAILS = 5  # 연속 실패 시 차단 가능성 -> 자동 중단


async def save_one(page, recipe_id: str) -> bool:
    url = f"{BASE}/recipe/print.html?seq={recipe_id}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_load_state("load", timeout=10000)
    except PWTimeout:
        print(f"  [{recipe_id}] 타임아웃, 건너뜀")
        return False

    # 제목 추출 (파일명용)
    title = await page.title()
    safe_title = "".join(c for c in title if c not in '\\/:*?"<>|').strip()
    filename = OUTPUT_DIR / f"{recipe_id}_{safe_title[:40]}.pdf"

    if filename.exists():
        print(f"  [{recipe_id}] 이미 존재, 건너뜀")
        return True

    # 인쇄용 CSS 미디어로 렌더링 (실제 인쇄 버튼과 동일 효과)
    await page.emulate_media(media="print")
    await page.pdf(path=str(filename), format="A4", print_background=True)
    print(f"  [{recipe_id}] 저장 완료 -> {filename.name}")
    return True


async def main(start: int, end: int):
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        recipe_ids = json.load(f)

    batch = recipe_ids[start:end]
    print(f"총 {len(recipe_ids)}개 중 {start}~{end} 구간, {len(batch)}개 처리 예정")

    consecutive_fails = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36 (personal-research-script)"
            )
        )

        for i, recipe_id in enumerate(batch, 1):
            print(f"[{i}/{len(batch)}] recipe_id={recipe_id}")
            ok = await save_one(page, recipe_id)

            if ok:
                consecutive_fails = 0
            else:
                consecutive_fails += 1
                if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                    print("\n연속 실패 다수 발생. 차단되었을 가능성이 있어 중단합니다.")
                    break

            await asyncio.sleep(DELAY_SEC)

        await browser.close()

    print("\n작업 종료.")


if __name__ == "__main__":
    start_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    asyncio.run(main(start_arg, end_arg))
