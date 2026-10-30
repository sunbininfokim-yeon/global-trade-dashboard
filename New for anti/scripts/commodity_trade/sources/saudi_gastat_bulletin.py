"""GASTAT bulletin oil-export VALUE series, explicitly not HS2709 volume.

Uses standard-library XLSX reading for one verified sheet, never evaluates
formulas and never infers missing cached values. Unexpected layouts fail closed.
"""
from __future__ import annotations

import calendar
import io
import math
import re
import zipfile
import posixpath
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

LISTING_URL = 'https://stats.gov.sa/ar/search?category=all&delta=60&sort=createDate-&start=1'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)


def official_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname not in {'stats.gov.sa', 'www.stats.gov.sa'} or p.username or p.password or p.port not in (None, 443):
        raise ValueError('only official GASTAT HTTPS links are accepted')
    return url


def fetch(url, timeout=150):
    req = Request(official_url(url), headers={'User-Agent': 'commodity-trade-bulletin/1.0'})
    with urlopen(req, timeout=timeout) as response:
        official_url(response.url)
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('GASTAT response exceeds 16 MiB bound')
    return data


def discover_publication(html, base=LISTING_URL):
    parser = Links()
    parser.feed(html)
    found = {}
    for href in parser.links:
        url = urljoin(base, href)
        match = re.search(r'/w/international-trade-in-goods-([a-z]+)-(20\d{2})$', urlsplit(url).path)
        if match and match[1] in MONTHS:
            official_url(url)
            found[f'{match[2]}-{MONTHS[match[1]]:02d}'] = url.split('?')[0]
    if not found:
        raise ValueError('no recognized monthly goods publication in official listing; retain last good output')
    month = max(found)
    return month, found[month]


def discover_workbook(html, base):
    parser = Links()
    parser.feed(html)
    urls = sorted({official_url(urljoin(base, x)) for x in parser.links
                   if '.xlsx/' in x and '/documents/' in x})
    if len(urls) != 1:
        raise ValueError('expected exactly one official bulletin XLSX link')
    return urls[0]


def worksheet_cells(document, sheet_name='1.2'):
    with zipfile.ZipFile(io.BytesIO(document)) as z:
        if sum(i.file_size for i in z.infolist()) > 64 * 1024 * 1024:
            raise ValueError('expanded workbook exceeds 64 MiB bound')
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(t.text or '' for t in s.findall('.//s:t', NS))
                       for s in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        sheets = ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet', NS)
        selected = next((s for s in sheets if s.get('name') == sheet_name), None)
        if selected is None:
            raise ValueError('missing verified bulletin sheet 1.2')
        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target = next(r.get('Target') for r in rels if r.get('Id') == selected.get(f'{{{REL}}}id'))
        path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
        if not path.startswith('xl/worksheets/'):
            raise ValueError('unexpected worksheet relationship')
        root = ET.fromstring(z.read(path))
        result = {}
        for c in root.findall('.//s:sheetData/s:row/s:c', NS):
            value = c.find('s:v', NS)
            if c.get('t') == 'inlineStr':
                result[c.get('r')] = ''.join(t.text or '' for t in c.findall('.//s:t', NS))
            elif value is not None and value.text is not None:
                result[c.get('r')] = strings[int(value.text)] if c.get('t') == 's' else value.text
        return result


def parse_bulletin(document, expected_month):
    cells = worksheet_cells(document)
    if ('value in SAR million' not in cells.get('A3', '')
            or 'Oil exports' not in cells.get('H5', '')
            or 'Total exports' not in cells.get('P4', '')):
        raise ValueError('bulletin measure/layout changed')
    points = {}
    rows = sorted({int(re.sub(r'\D', '', k)) for k in cells if k.startswith('C')})
    for row in rows:
        month = MONTHS.get(str(cells.get(f'C{row}', '')).strip().lower())
        year = str(cells.get(f'A{row}', ''))
        if not month or not re.fullmatch(r'20\d{2}\*?', year):
            continue  # Explicitly exclude quarter and annual total rows.
        period = f'{year[:4]}-{month:02d}'
        try:
            oil, total = (float(cells[f'{col}{row}']) for col in ('H', 'P'))
        except (ValueError, KeyError):
            raise ValueError(f'missing numeric bulletin value for {period}') from None
        if not all(math.isfinite(v) and v >= 0 for v in (oil, total)) or oil > total:
            raise ValueError(f'invalid bulletin values for {period}')
        if period in points:
            raise ValueError(f'duplicate monthly row for {period}')
        points[period] = {
            'month': period, 'value': oil, 'unit': 'SAR_million',
            'total_goods_exports_sar_million': total,
            'share_of_total_goods_export_value': oil / total if total else None,
            'preliminary': '*' in year,
            'source_cells': {'sheet': '1.2', 'oil_value': f'H{row}', 'total_value': f'P{row}'},
        }
    if not points or max(points) != expected_month:
        raise ValueError('publication month does not match last observed workbook month')
    return [points[m] for m in sorted(points)[-24:]]
