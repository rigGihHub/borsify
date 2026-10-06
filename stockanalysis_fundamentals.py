"""Bounded, public-page fallback; keep provider identity and units explicit."""
from datetime import datetime, timezone
import math
import re
from threading import Semaphore

from bs4 import BeautifulSoup
import requests

from resilience import call_with_resilience
from data_errors import format_error

SOURCE = "Stock Analysis / S&P Global Market Intelligence"
_EXCHANGES = {"ST": ("sto", "SEK"), "OL": ("osl", "NOK"), "CO": ("cph", "DKK")}
_REQUESTS = Semaphore(2)


def listing(symbol):
    ticker, _, suffix = str(symbol).upper().rpartition('.')
    if suffix not in _EXCHANGES or not re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9]+)*', ticker):
        return None
    exchange, currency = _EXCHANGES[suffix]
    ticker = ticker.replace('-', '.')
    return exchange, ticker, currency, f'https://stockanalysis.com/quote/{exchange}/{ticker}/statistics/'


def number(text, *, percent=False):
    text = str(text or '').strip().replace(',', '').replace('−', '-')
    pattern = r'([+-]?\d+(?:\.\d+)?)%' if percent else r'([+-]?\d+(?:\.\d+)?)([KMBT]?)'
    match = re.fullmatch(pattern, text)
    if not match:
        return math.nan
    value = float(match[1])
    if percent:
        return value / 100
    return value * {'': 1, 'K': 1e3, 'M': 1e6, 'B': 1e9, 'T': 1e12}[match[2]]


def parse_statistics(html, symbol, *, now=None):
    identity = listing(symbol)
    if not identity:
        raise ValueError('Unsupported listing')
    exchange, ticker, currency, url = identity
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    marker = f'({exchange.upper()}:{ticker})'
    if marker not in title:
        raise ValueError('Listing identity mismatch')
    text = soup.get_text(' ', strip=True)
    if not re.search(r'Currency is\s+' + currency + r'\b', text):
        raise ValueError('Listing currency missing or mismatched')
    dated = re.search(r'Last updated:\s*([A-Z][a-z]{2} \d{1,2}, \d{4})', text)
    if not dated:
        raise ValueError('Source update date missing')
    observed = datetime.strptime(dated[1], '%b %d, %Y').replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if not 0 <= (current.date() - observed.date()).days <= 7:
        raise ValueError('Source statistics stale or future dated')
    cells = {}
    for row in soup.select('tr'):
        cols = row.find_all('td', recursive=False)
        if len(cols) == 2:
            cells[cols[0].get_text(' ', strip=True)] = cols[1].get_text(' ', strip=True)
    payload = {
        'Namn': title.split(marker)[0].strip(), 'Sektor': 'Okänd', 'Bransch': 'Okänd',
        'Valuta': currency, 'Finansiell valuta': currency,
        'Fundamental källa': SOURCE, 'Fundamental käll-URL': url,
        'Fundamental källdatum': observed.date().isoformat(),
        'Fundamental hämtad': current.isoformat(timespec='seconds'),
        'Fundamental reservkälla': True,
        '_Fundamental cache': 'Stock Analysis',
        'Utdelningsenhet version': 1,
        'Direktavkastning källa': SOURCE + ': procent omräknat till andel',
    }
    for label, field in {'PE Ratio':'P/E', 'Forward PE':'Forward P/E', 'PB Ratio':'P/B',
                         'EV / EBITDA':'EV/EBITDA'}.items():
        payload[field] = number(cells.get(label))
    for label, field in {'Return on Equity (ROE)':'ROE', 'Profit Margin':'Vinstmarginal',
                         'FCF Yield':'FCF-yield', 'Dividend Yield':'Direktavkastning',
                         'Payout Ratio':'Utdelningsandel'}.items():
        payload[field] = number(cells.get(label), percent=True)
    # Borsify's existing debt/equity contract uses Yahoo's percent units.
    payload['Skuld/eget kapital'] = number(cells.get('Debt / Equity')) * 100
    cap = number(cells.get('Market Cap'))
    payload['Börsvärde lokal mdr'] = cap / 1e9
    payload['Börsvärde BSEK'] = cap / 1e9  # converted by add_sek_conversions later
    payload['_Raw marketCap'] = cap
    # Forecast growth is NOT historical growth. Leave unobserved fields missing.
    payload['Omsättningstillväxt'] = math.nan
    payload['Vinsttillväxt'] = math.nan
    if not 0 <= payload['Direktavkastning'] <= 1:
        payload['Direktavkastning'] = math.nan
    core = ['P/E', 'Forward P/E', 'EV/EBITDA', 'FCF-yield', 'ROE', 'Vinstmarginal', 'Skuld/eget kapital']
    if not any(math.isfinite(payload[k]) for k in core):
        raise ValueError('No observed fundamental ratios')
    return payload


def fetch_stockanalysis(symbol):
    identity = listing(symbol)
    health = {'source': SOURCE, 'status': 'NO_DATA', 'errors': [], 'attempts': 0}
    if not identity:
        return {}, health
    url = identity[3]

    def request():
        response = requests.get(url, timeout=(10, 20), headers={'User-Agent': 'Borsify/4.41 (+https://borsify.streamlit.app)'})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if response.url.rstrip('/').lower() != url.rstrip('/').lower():
            raise ValueError('Unexpected listing redirect')
        response.encoding = 'utf-8'
        return response.text

    # Two in-flight requests maximum across all scan workers. Provider failures
    # open the shared circuit; no proxy rotation or access-control workarounds.
    with _REQUESTS:
        html, result = call_with_resilience(request, provider_key='stockanalysis:fundamentals',
            context='stockanalysis:fundamentals', max_attempts=1, cooldown_seconds=600)
    health['attempts'] = result['attempts']
    if not result['ok']:
        health['status'] = 'ERROR'
        health['errors'].append(format_error(result['error'] or {}))
        return {}, health
    if not html:
        health['errors'].append('Stock Analysis: listing not found')
        return {}, health
    try:
        payload = parse_statistics(html, symbol)
    except ValueError as exc:
        health['errors'].append(str(exc))
        return {}, health
    health['status'] = 'PARTIAL'
    return payload, health
