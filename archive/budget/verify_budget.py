#!/usr/bin/env python
"""
verify_budget.py — Cross-verify extracted budget data against stated totals.

Usage:
    # Generate the DB first (20-page sample)
    ocr-env/bin/python pdf_to_excel_v2.py output/redbook.pdf --max-pages 20 --sqlite -o output/redbook-20.db

    # Then verify:
    python verify_budget.py output/redbook-20.db pages          # list all pages
    python verify_budget.py output/redbook-20.db page 8         # show all rows on page 8
    python verify_budget.py output/redbook-20.db sections       # list all sections
    python verify_budget.py output/redbook-20.db section अर्थ   # show one section's rows
    python verify_budget.py output/redbook-20.db verify         # cross-check all totals
    python verify_budget.py output/redbook-20.db totals         # list all total rows
    python verify_budget.py output/redbook-20.db page 8 --sum   # sum non-total rows & compare
"""

import argparse
import sqlite3
import sys
from collections import defaultdict

NUM_COLS = ['year_actual', 'year_revised', 'year_estimate',
            'total', 'current_exp', 'capital_exp', 'financial']

COL_LABELS = ['Year Actual', 'Revised', 'Estimate',
              'Total', 'Current Exp', 'Capital Exp', 'Financial']


def connect(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def fmt(n):
    if n is None:
        return ''
    return f'{n:,.0f}'


def fmt_short(n):
    if n is None:
        return ''
    if abs(n) >= 1e9:
        return f'{n/1e9:.2f}B'
    if abs(n) >= 1e7:
        return f'{n/1e7:.1f}Cr'
    if abs(n) >= 1e5:
        return f'{n/1e5:.1f}L'
    return f'{n:,.0f}'


def cmd_pages(conn):
    rows = conn.execute("""
        SELECT page_number, table_type,
               COUNT(*) AS rows,
               SUM(CASE WHEN is_total_row THEN 1 ELSE 0 END) AS totals,
               SUM(CASE WHEN is_grand_total_row THEN 1 ELSE 0 END) AS grand_totals
        FROM raw_budget_lines
        GROUP BY page_number
        ORDER BY page_number
    """).fetchall()
    if not rows:
        print('No data found.')
        return
    print(f'  {"Page":<6} {"Type":<10} {"Items":<6} {"Totals":<7} {"Grand":<6}')
    print(f'  {"":-<6} {"":-<10} {"":-<6} {"":-<7} {"":-<6}')
    for r in rows:
        print(f'  {r["page_number"]:<6} {r["table_type"]:<10} '
              f'{r["rows"]:<6} {r["totals"]:<7} {r["grand_totals"]:<6}')


def cmd_page(conn, page_num, do_sum=False):
    rows = conn.execute("""
        SELECT * FROM raw_budget_lines
        WHERE page_number = ?
        ORDER BY id
    """, (page_num,)).fetchall()
    if not rows:
        print(f'No data on page {page_num}.')
        return

    total_rows = []
    grand_rows = []
    data_rows = []

    for r in rows:
        if r['is_grand_total_row']:
            grand_rows.append(r)
        elif r['is_total_row']:
            total_rows.append(r)
        else:
            data_rows.append(r)

    # Print header
    print(f'\n=== Page {page_num} — {len(rows)} total rows '
          f'({len(data_rows)} data, {len(total_rows)} section totals, '
          f'{len(grand_rows)} grand totals) ===\n')

    for kind, grp in [('DATA', data_rows), ('SECTION TOTAL', total_rows),
                       ('GRAND TOTAL', grand_rows)]:
        if not grp:
            continue
        print(f'  ── {kind} ──')
        for r in grp:
            section_s = f'[{r["inferred_section"]}] ' if r['inferred_section'] else ''
            code_s = f'{r["budget_code"]}  ' if r['budget_code'] else ''
            desc = (r['description'] or '')[:80]
            vals = ', '.join(
                f'{COL_LABELS[i]}={fmt(v)}'
                for i, v in enumerate([r[c] for c in NUM_COLS])
                if v is not None
            )
            print(f'    {section_s}{code_s}{desc}')
            if vals:
                print(f'      → {vals}')
        print()

    if do_sum and data_rows:
        print(f'  ── SUM OF DATA ROWS (page {page_num}) ──')
        sums = {c: sum(r[c] for r in data_rows if r[c] is not None)
                for c in NUM_COLS}
        for c, label in zip(NUM_COLS, COL_LABELS):
            if sums[c]:
                print(f'    {label}: {fmt(sums[c])}  ({fmt_short(sums[c])})')

        if total_rows:
            print(f'\n  ── COMPARE TO STATED TOTALS ──')
            for t in total_rows:
                sec = t['inferred_section'] or '(unknown)'
                for c, label in zip(NUM_COLS, COL_LABELS):
                    stated = t[c]
                    if stated is None:
                        continue
                    computed = sum(r[c] for r in data_rows if r[c] is not None)
                    diff = computed - stated
                    flag = ' ✓' if abs(diff) < 1 else f' ✗ diff={fmt(diff)}'
                    print(f'    {sec} / {label}: computed={fmt(computed)} '
                          f'stated={fmt(stated)}{flag}')

        if grand_rows:
            for g in grand_rows:
                sec = g['inferred_section'] or '(unknown)'
                for c, label in zip(NUM_COLS, COL_LABELS):
                    stated = g[c]
                    if stated is None:
                        continue
                    computed = sum(r[c] for r in data_rows if r[c] is not None)
                    diff = computed - stated
                    flag = ' ✓' if abs(diff) < 1 else f' ✗ diff={fmt(diff)}'
                    print(f'    {sec} / {label} [GRAND]: computed={fmt(computed)} '
                          f'stated={fmt(stated)}{flag}')


def cmd_sections(conn):
    rows = conn.execute("""
        SELECT inferred_section,
               COUNT(*) AS rows,
               SUM(CASE WHEN is_total_row THEN 1 ELSE 0 END) AS totals,
               SUM(CASE WHEN is_grand_total_row THEN 1 ELSE 0 END) AS grand_totals,
               MIN(page_number) AS first_page,
               MAX(page_number) AS last_page
        FROM raw_budget_lines
        WHERE inferred_section IS NOT NULL AND inferred_section != ''
        GROUP BY inferred_section
        ORDER BY first_page
    """).fetchall()
    if not rows:
        print('No sections found.')
        return
    print(f'  {"Section":<40} {"Rows":<6} {"Totals":<7} {"Grand":<6} {"Pages":<10}')
    print(f'  {"":-<40} {"":-<6} {"":-<7} {"":-<6} {"":-<10}')
    for r in rows:
        pages = f'{r["first_page"]}-{r["last_page"]}' if r["first_page"] != r["last_page"] else str(r["first_page"])
        print(f'  {r["inferred_section"]:<40} {r["rows"]:<6} '
              f'{r["totals"]:<7} {r["grand_totals"]:<6} {pages:<10}')


def cmd_section(conn, section_kw):
    rows = conn.execute("""
        SELECT * FROM raw_budget_lines
        WHERE inferred_section LIKE ?
        ORDER BY page_number, id
    """, (f'%{section_kw}%',)).fetchall()
    if not rows:
        print(f'No rows matching section "{section_kw}".')
        return

    data = [r for r in rows if not r['is_total_row'] and not r['is_grand_total_row']]
    totals = [r for r in rows if r['is_total_row'] or r['is_grand_total_row']]

    sec_name = rows[0]['inferred_section']
    print(f'\n=== Section: {sec_name} ({len(rows)} rows: '
          f'{len(data)} data, {len(totals)} totals) ===\n')

    for r in data:
        code_s = f'{r["budget_code"]}  ' if r['budget_code'] else ''
        desc = (r['description'] or '')[:100]
        vals = ', '.join(fmt(v) for v in [r[c] for c in NUM_COLS] if v is not None)
        print(f'  P{r["page_number"]}  {code_s}{desc}')
        if vals:
            print(f'      {vals}')

    if totals:
        print()
        for t in totals:
            label = 'GRAND TOTAL' if t['is_grand_total_row'] else 'SECTION TOTAL'
            print(f'  >> {label}: {t["description"][:60]}')
            stated_vals = {c: t[c] for c in NUM_COLS if t[c] is not None}
            if stated_vals:
                for c, label2 in zip(NUM_COLS, COL_LABELS):
                    if c in stated_vals:
                        print(f'      {label2}: {fmt(stated_vals[c])}')

    # Auto-verify (page-by-page)
    if totals and data:
        print(f'\n  ── VERIFICATION (page-by-page) ──')
        for t in totals:
            pnum = t['page_number']
            page_data = [r for r in data if r['page_number'] == pnum]
            sec = t['inferred_section'] or '(unknown)'
            for c, label in zip(NUM_COLS, COL_LABELS):
                stated = t[c]
                if stated is None:
                    continue
                computed = sum(r[c] for r in page_data if r[c] is not None)
                diff = computed - stated
                flag = '✓' if abs(diff) < 1 else f'✗ (diff={fmt(diff)})'
                print(f'    P{pnum} {label}: computed={fmt(computed)}  '
                      f'stated={fmt(stated)}  {flag}')


def cmd_totals(conn):
    rows = conn.execute("""
        SELECT * FROM raw_budget_lines
        WHERE is_total_row = 1 OR is_grand_total_row = 1
        ORDER BY page_number, id
    """).fetchall()
    if not rows:
        print('No total rows found.')
        return

    print(f'\n  {"Page":<5} {"Type":<14} {"Section":<35} {"Total":<20} {"Description":<50}')
    print(f'  {"":-<5} {"":-<14} {"":-<35} {"":-<20} {"":-<50}')
    for r in rows:
        kind = 'GRAND' if r['is_grand_total_row'] else 'SECTION'
        sec = (r['inferred_section'] or '')[:34]
        total = fmt(r['total']) if r['total'] is not None else ''
        desc = (r['description'] or '')[:49]
        print(f'  {r["page_number"]:<5} {kind:<14} {sec:<35} {total:<20} {desc}')


def cmd_verify(conn):
    """Full cross-verification: per (page, section), sum data rows
    and compare to stated total rows on the same page."""
    groups = conn.execute("""
        SELECT DISTINCT page_number, inferred_section
        FROM raw_budget_lines
        WHERE inferred_section IS NOT NULL AND inferred_section != ''
        ORDER BY page_number, inferred_section
    """).fetchall()

    all_ok = True
    for g in groups:
        pnum = g['page_number']
        sec = g['inferred_section']

        data = conn.execute("""
            SELECT * FROM raw_budget_lines
            WHERE page_number = ? AND inferred_section = ?
              AND is_total_row = 0 AND is_grand_total_row = 0
            ORDER BY id
        """, (pnum, sec)).fetchall()

        totals = conn.execute("""
            SELECT * FROM raw_budget_lines
            WHERE page_number = ? AND inferred_section = ?
              AND (is_total_row = 1 OR is_grand_total_row = 1)
            ORDER BY id
        """, (pnum, sec)).fetchall()

        if not totals or not data:
            continue

        for t in totals:
            for c, label in zip(NUM_COLS, COL_LABELS):
                stated = t[c]
                if stated is None:
                    continue
                computed = sum(r[c] for r in data if r[c] is not None)
                kind = 'GRAND' if t['is_grand_total_row'] else 'SECTION'
                diff = computed - stated
                ok = abs(diff) < 1
                if not ok:
                    all_ok = False
                flag = '✓' if ok else '✗'
                print(f'  P{pnum:<3} {flag} [{kind}] {sec:<30} '
                      f'{label:<14} '
                      f'computed={fmt_short(computed):>8}  '
                      f'stated={fmt_short(stated):>8}  '
                      f'diff={fmt_short(diff):>8}'
                      f'{"  ***" if not ok else ""}')

    if all_ok:
        print('\n  ✓ All totals verified OK.')
    else:
        print('\n  ✗ Some totals have discrepancies (see above).')


def main():
    parser = argparse.ArgumentParser(
        description='Verify extracted budget data against stated totals.')
    parser.add_argument('db', help='SQLite DB path')
    parser.add_argument('command', nargs='?', default='verify',
                        choices=['pages', 'page', 'sections', 'section',
                                 'totals', 'verify'],
                        help='Command')
    parser.add_argument('arg', nargs='?', help='Command argument (page #, section name)')
    parser.add_argument('--sum', action='store_true',
                        help='With "page": show sum of data rows')
    args = parser.parse_args()

    conn = connect(args.db)

    if args.command == 'pages':
        cmd_pages(conn)
    elif args.command == 'page':
        if args.arg is None:
            print('Usage: verify_budget.py <db> page <N>')
            sys.exit(1)
        cmd_page(conn, int(args.arg), do_sum=args.sum)
    elif args.command == 'sections':
        cmd_sections(conn)
    elif args.command == 'section':
        if args.arg is None:
            print('Usage: verify_budget.py <db> section <name>')
            sys.exit(1)
        cmd_section(conn, args.arg)
    elif args.command == 'totals':
        cmd_totals(conn)
    elif args.command == 'verify':
        cmd_verify(conn)

    conn.close()


if __name__ == '__main__':
    main()
