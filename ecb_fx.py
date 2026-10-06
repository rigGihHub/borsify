"""Dated ECB reference rates, only as fallback for missing quote conversion."""
from datetime import date
import math
from xml.etree import ElementTree
import requests

URL = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'


def parse_reference_rates(xml, *, today=None):
    root = ElementTree.fromstring(xml)
    for cube in root.iter():
        if 'time' not in cube.attrib:
            continue
        observed = date.fromisoformat(cube.attrib['time'])
        if not 0 <= ((today or date.today()) - observed).days <= 7:
            raise ValueError('Stale or future ECB rates')
        per_eur = {'EUR': 1.0}
        for child in cube:
            currency = child.attrib.get('currency')
            if currency:
                rate = float(child.attrib.get('rate', 'nan'))
                if math.isfinite(rate) and rate > 0:
                    per_eur[currency] = rate
        sek = per_eur.get('SEK')
        if not sek:
            raise ValueError('ECB SEK rate missing')
        return {currency: sek / value for currency, value in per_eur.items()}, observed.isoformat()
    raise ValueError('ECB observation date missing')


def fetch_reference_rates():
    response = requests.get(URL, timeout=(10, 15))
    response.raise_for_status()
    return parse_reference_rates(response.content)
