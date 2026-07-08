"""
1단계: 검색 결과 페이지에서 레시피 링크 수집
사용법: python collect_recipe_links.py "볶음밥" 20
       -> "볶음밥" 검색, 1~20페이지까지 순회하며 레시피 ID 수집
       uv run python collect_recipe_links.py "볶음밥" 20
"""

import asyncio
import json
import sys
import time
import urllib.parse

from playwright.async_api import async_playwright

BASE = "https://www.10000recipe.com"
OUTPUT_FILE = "recipe_ids.json"

DELAY_SEC = 2.5  # 페이지 간 딜레이 (서버 부하 최소화)


async def collect(query: str, max_pages: int):
    encoded_q = urllib.parse.quote(query)
    recipe_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36 (personal-research-script)"
            )
        )

        for page_num in range(1, max_pages + 1):
            url = f"{BASE}/recipe/list.html?q={encoded_q}&page={page_num}"
            print(f"[{page_num}/{max_pages}] {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            try:
                await page.wait_for_selector("a[href^='/recipe/']", timeout=15000)
            except Exception:
                pass  # 결과 0개인 페이지일 수 있음 -> 아래 links 체크에서 처리

            # 차단/캡차 감지: 정상 목록 구조가 안 보이면 중단
            links = await page.eval_on_selector_all(
                "a[href^='/recipe/']",
                "els => els.map(e => e.getAttribute('href'))",
            )

            if not links:
                print("  -> 더 이상 결과 없음 또는 차단 감지. 중단합니다.")
                break

            new_ids = set()
            for href in links:
                # href 예: /recipe/6898327
                part = href.split("/recipe/")[-1]
                if part.isdigit():
                    new_ids.add(part)

            print(f"  -> {len(new_ids)}개 발견 (누적 {len(recipe_ids) + len(new_ids)}개)")
            recipe_ids.update(new_ids)

            await asyncio.sleep(DELAY_SEC)

        await browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(recipe_ids), f, ensure_ascii=False, indent=2)

    print(f"\n총 {len(recipe_ids)}개 레시피 ID -> {OUTPUT_FILE} 저장 완료")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python collect_recipe_links.py <검색어> <최대페이지수>")
        sys.exit(1)

    query_arg = sys.argv[1]
    max_pages_arg = int(sys.argv[2])
    asyncio.run(collect(query_arg, max_pages_arg))
