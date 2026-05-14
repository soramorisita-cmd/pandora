from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://repsmaster.x.yupoo.com/categories/4791258', wait_until='domcontentloaded', timeout=30000)
    time.sleep(2)

    result = page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll('a.categories__box-right-category-item'));
        return links.map(a => ({
            name: a.textContent.trim(),
            href: a.getAttribute('href')
        }));
    }""")

    print(f'categories__box-right-category-item: {len(result)}件')
    for r in result:
        print(f'  {r["name"]} | {r["href"]}')