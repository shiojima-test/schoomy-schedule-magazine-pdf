"""SchooMy Festa annual schedule (magazine layout) — HTML→Playwright→PDF."""
# v1: is_published == 'TRUE' で PDF 掲載判定 (HP と同じフラグを兼用)
# v2: 新列 show_in_pdf で PDF 掲載判定。is_published による PDF 除外は廃止
#     (HP 側ロジックは無変更)。show_in_pdf が FALSE/0/NO のときだけ非掲載、
#     空欄・TRUE・列なしは掲載 (後方互換)。
# v3: 常に1ページに収める自動フィットを追加 (縮小変形方式)。
# v4: 縮小変形をやめ、CSS段組み + 文字サイズ係数(--k)方式に変更。
#     - 本文は column-fill:auto の2段組。左段を最後まで埋めてから右段へ流すので
#       月ブロック単位の振り分けで生じていた下部の空白が出ない
#     - template.html の __fitToOnePage() が --k (文字サイズ・余白の一括係数) を
#       二分探索し、2段に収まる範囲で最大＝紙面を最も埋める値を採用
#     - transform を使わないため右端にも余白が出ない
#     - page.pdf に page_ranges='1' を付与し、出力を物理的に1ページへ固定
__version__ = '4'

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

SHEET_BASE = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRooWpJWGHr60e039XzbxEbeZ7p6zEL-wuP-xrq4jv1TnZXHSOWjtT8FvScuKsQn05aZx8PfIW14d83/pub"
)
CSV_URL = f"{SHEET_BASE}?output=csv"
CONFIG_CSV_URL = f"{SHEET_BASE}?gid=918840879&single=true&output=csv"


def fetch_config():
    """configシートから version と lastUpdate を読む。
    キャッシュ回避のため URL にタイムスタンプを付与する。"""
    import time
    url = f"{CONFIG_CSV_URL}&_ts={int(time.time())}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    reader = csv.DictReader(StringIO(resp.text))
    kv = {row['key'].strip(): row['value'].strip() for row in reader if row.get('key')}
    if 'version' not in kv or 'lastUpdate' not in kv:
        raise RuntimeError(f'config sheet missing required keys; got {list(kv)}')
    return {
        'version': int(kv['version']),
        'last_update': kv['lastUpdate'],
    }


def resolve_year_month(row):
    """date_start があればそこから year/month を導出。無ければ year/month カラムを使う。
    CSV の year/month が date_start とズレている行（typo 等）も自動補正される。"""
    ds = (row.get('date_start') or '').strip()
    if ds:
        parts = ds.replace('/', '-').split('-')
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return parts[0], parts[1].zfill(2)
    return row.get('year', ''), (row.get('month') or '').zfill(2)


def _is_pdf_visible(row):
    """PDF 掲載可否を判定する (v2)。
    show_in_pdf が FALSE/0/NO (大文字小文字問わず) のときだけ非掲載。
    空欄・TRUE・列が存在しない場合は掲載 (後方互換)。
    is_published は参照しない。"""
    v = (row.get('show_in_pdf') or '').strip().upper()
    return v not in ('FALSE', '0', 'NO')


def fetch_rows():
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    reader = csv.DictReader(StringIO(resp.text))
    rows = []
    total = 0
    for r in reader:
        total += 1
        if not _is_pdf_visible(r):
            continue
        if r.get('type') == 'local':
            continue
        if not r.get('title'):
            continue
        rows.append(r)
    print(f'rows: {total} in CSV -> {len(rows)} visible in PDF (script v{__version__})')

    def sort_key(row):
        ds = (row.get('date_start') or '').strip()
        if ds:
            return ds.replace('/', '-')
        y, m = resolve_year_month(row)
        return f"{y or '9999'}-{m or '12'}-01"

    rows.sort(key=sort_key)
    return rows


def month_key_of(row):
    """行の年月を 'YYYY-MM' で返す。判定できない場合は None。"""
    y, m = resolve_year_month(row)
    if y and m:
        return f'{y}-{m}'
    return None


def next_month_jst():
    """JST の翌月を 'YYYY-MM' で返す（掲載用の既定の開始月）。"""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone(timedelta(hours=9)))
    y, m = now.year, now.month + 1
    if m > 12:
        y, m = y + 1, 1
    return f'{y}-{m:02d}'


def filter_from_month(rows, start_month):
    """start_month ('YYYY-MM') より前の月の行を除外する。
    年月が判定できない行は残す（掲載漏れを防ぐため）。"""
    if not start_month:
        return rows
    kept = []
    for r in rows:
        key = month_key_of(r)
        if key is None or key >= start_month:
            kept.append(r)
    print(f'start-month {start_month}: {len(rows)} -> {len(kept)} rows')
    return kept


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
    t = (row.get('type') or '').strip().lower()
    if t == 'contest':
        kind, kind_class = 'コンテスト', 'contest'
    elif t == 'festa':
        kind, kind_class = 'フェスタ', 'festa'
    else:
        kind, kind_class = '説明会', 'setsumei'

    target = (row.get('target') or '').strip()
    if target.startswith('・'):
        target = target[1:]

    r1 = (row.get('entry_result_1') or '').strip()
    r2 = (row.get('entry_result_2') or '').strip()
    result = ' / '.join([x for x in [r1, r2] if x]) or '—'

    return {
        'kind': kind,
        'kind_class': kind_class,
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


def render_html(groups, version, update_date, logo_data_uri):
    env = Environment(loader=FileSystemLoader(Path(__file__).parent))
    template = env.get_template('template.html')

    blocks = [(month_label(k), evs) for k, evs in groups.items()]

    return template.render(
        version=version,
        update_date=update_date,
        logo_data_uri=logo_data_uri,
        blocks=blocks,
    )


PAGE_W_MM = 210
PAGE_H_MM = 257
PX_PER_MM = 96 / 25.4


async def html_to_pdf(html, output_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # 紙面と同じピクセル寸法で組むことで、画面上の実測値が印刷結果と一致する
        page = await browser.new_page(viewport={
            'width': round(PAGE_W_MM * PX_PER_MM),
            'height': round(PAGE_H_MM * PX_PER_MM),
        })
        await page.set_content(html, wait_until='networkidle')
        try:
            await page.evaluate('() => document.fonts.ready')
        except Exception as e:  # noqa: BLE001
            print(f'font wait skipped: {e}')
        await page.wait_for_timeout(1200)

        fit = await page.evaluate('() => window.__fitToOnePage()')
        print(f'fit: {fit}')
        if isinstance(fit, dict) and fit.get('k', 1) <= 0.56:
            print('WARNING: 文字サイズ係数が下限に達しました。行数が多すぎる可能性があります。')

        await page.pdf(
            path=output_path,
            width=f'{PAGE_W_MM}mm', height=f'{PAGE_H_MM}mm',
            print_background=True,
            page_ranges='1',
            margin={'top': '0', 'bottom': '0', 'left': '0', 'right': '0'},
        )
        await browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument(
        '--start-month',
        help="この月以降だけを掲載する (例: 2026-09)。'next' でJSTの翌月。省略時は全期間。",
    )
    args = parser.parse_args()

    start_month = args.start_month
    if start_month == 'next':
        start_month = next_month_jst()

    config = fetch_config()
    print(f"config: version={config['version']} lastUpdate={config['last_update']}")

    rows = fetch_rows()
    rows = filter_from_month(rows, start_month)
    groups = group_by_month(rows)

    repo_root = Path(__file__).resolve().parent.parent
    logo_path = repo_root / 'assets' / 'schoomy_logo.svg'
    logo_b64 = base64.b64encode(logo_path.read_bytes()).decode('ascii')
    logo_data_uri = f"data:image/svg+xml;base64,{logo_b64}"

    html = render_html(groups, config['version'], config['last_update'], logo_data_uri)
    asyncio.run(html_to_pdf(html, args.output))
    print(f"Generated: {args.output}")


if __name__ == '__main__':
    main()
