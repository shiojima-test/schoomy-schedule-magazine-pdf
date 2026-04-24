"""SchooMy Festa annual schedule (magazine layout) — HTML→Playwright→PDF."""
import argparse
import asyncio
import base64
import csv
from io import StringIO
from pathlib import Path
from collections import OrderedDict

import requests
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRooWpJWGHr60e039XzbxEbeZ7p6zEL-wuP-xrq4jv1TnZXHSOWjtT8FvScuKsQn05aZx8PfIW14d83"
    "/pub?output=csv"
)


def resolve_year_month(row):
    """date_start があればそこから year/month を導出。無ければ year/month カラムを使う。
    CSV の year/month が date_start とズレている行（typo 等）も自動補正される。"""
    ds = (row.get('date_start') or '').strip()
    if ds:
        parts = ds.replace('/', '-').split('-')
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return parts[0], parts[1].zfill(2)
    return row.get('year', ''), (row.get('month') or '').zfill(2)


def fetch_rows():
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    reader = csv.DictReader(StringIO(resp.text))
    rows = []
    for r in reader:
        if (r.get('is_published') or '').strip().upper() != 'TRUE':
            continue
        if r.get('type') == 'local':
            continue
        if not r.get('title'):
            continue
        rows.append(r)

    def sort_key(row):
        ds = (row.get('date_start') or '').strip()
        if ds:
            return ds.replace('/', '-')
        y, m = resolve_year_month(row)
        return f"{y or '9999'}-{m or '12'}-01"

    rows.sort(key=sort_key)
    return rows


def format_date(row):
    dt = (row.get('date_text') or '').strip()
    if dt:
        y = row.get('year', '')
        return f"{y}/{dt}" if y else dt

    ds = (row.get('date_start') or '').strip().replace('-', '/')
    de = (row.get('date_end') or '').strip().replace('-', '/')

    if not ds:
        return ''
    if not de:
        return ds

    ds_parts = ds.split('/')
    de_parts = de.split('/')
    if len(ds_parts) == 3 and len(de_parts) == 3:
        if ds_parts[:2] == de_parts[:2]:
            return f"{ds}〜{de_parts[2]}"
        return f"{ds}〜{de_parts[1]}/{de_parts[2]}"
    return f"{ds}〜{de}"


def shorten_host(host):
    if not host:
        return ''
    return host.replace(
        '一般社団法人 Mt.Fuji イノベーションエンジン',
        '(一社)Mt.Fujiイノベーションエンジン',
    )


def normalize_event(row):
    kind = 'フェスタ' if row['type'] == 'festa' else '説明会'

    target = (row.get('target') or '').strip()
    if target.startswith('・'):
        target = target[1:]

    r1 = (row.get('entry_result_1') or '').strip()
    r2 = (row.get('entry_result_2') or '').strip()
    result = ' / '.join([x for x in [r1, r2] if x]) or '—'

    return {
        'kind': kind,
        'kind_class': 'festa' if kind == 'フェスタ' else 'setsumei',
        'date': format_date(row),
        'time': (row.get('time') or '').strip() if kind == '説明会' else '',
        'title': row.get('title', '').strip(),
        'sub': target,
        'location': (row.get('location') or '').strip() or '未定',
        'host': shorten_host((row.get('host') or '').strip()) or '—',
        'entry': (row.get('entry_start') or '').strip() or '—',
        'result': result,
    }


def group_by_month(rows):
    groups = OrderedDict()
    for r in rows:
        y, m = resolve_year_month(r)
        key = f"{y}-{m}"
        if (y, m) in (('2026', '10'), ('2026', '11')):
            key = '2026-10-11'
        if key not in groups:
            groups[key] = []
        groups[key].append(normalize_event(r))
    return groups


def month_label(key):
    if key == '2026-10-11':
        return '2026年10月〜11月'
    y, m = key.split('-')
    return f'{y}年{int(m)}月'


def estimate_block_mm(events):
    h = 5.0 + 1.2
    for ev in events:
        eh = 2.4 + 4.0
        name_lines = max(1, (len(ev['title']) * 1.5) // 42 + 1)
        eh += name_lines * 3.0
        if ev['sub']:
            sub_lines = max(1, (len(ev['sub']) * 1.5) // 50 + 1)
            eh += sub_lines * 2.4 + 0.8
        eh += 2.5
        if ev['kind'] == 'フェスタ':
            eh += 2.5
        eh += 0.4
        h += eh
    h += 2.0
    return h


def split_columns(blocks):
    heights = [estimate_block_mm(evs) for _, evs in blocks]
    best_i, best_diff = 1, float('inf')
    for i in range(1, len(blocks)):
        left = sum(heights[:i])
        right = sum(heights[i:])
        diff = abs(left - right)
        if diff < best_diff:
            best_diff = diff
            best_i = i
    return best_i


def render_html(groups, version, update_date, logo_data_uri):
    env = Environment(loader=FileSystemLoader(Path(__file__).parent))
    template = env.get_template('template.html')

    blocks = [(month_label(k), evs) for k, evs in groups.items()]
    split = split_columns(blocks)

    return template.render(
        version=version,
        update_date=update_date,
        logo_data_uri=logo_data_uri,
        left_blocks=blocks[:split],
        right_blocks=blocks[split:],
    )


async def html_to_pdf(html, output_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until='networkidle')
        await page.wait_for_timeout(1500)
        await page.pdf(
            path=output_path,
            width='210mm', height='257mm',
            print_background=True,
            margin={'top': '0', 'bottom': '0', 'left': '0', 'right': '0'},
        )
        await browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', type=int, required=True)
    parser.add_argument('--update-date', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    rows = fetch_rows()
    groups = group_by_month(rows)

    repo_root = Path(__file__).resolve().parent.parent
    logo_path = repo_root / 'assets' / 'schoomy_logo.svg'
    logo_b64 = base64.b64encode(logo_path.read_bytes()).decode('ascii')
    logo_data_uri = f"data:image/svg+xml;base64,{logo_b64}"

    html = render_html(groups, args.version, args.update_date, logo_data_uri)
    asyncio.run(html_to_pdf(html, args.output))
    print(f"Generated: {args.output}")


if __name__ == '__main__':
    main()
