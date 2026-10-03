from io import BytesIO
import os
import subprocess
import time

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

import report_fetcher as fetcher


def pdf_bytes():
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 30 700 Td (Example AB Q2 2026 Revenue SEK 100 million) Tj ET')
    page[NameObject('/Contents')] = stream
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class Response:
    headers = {'content-type': 'application/octet-stream'}

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.data[:limit]

    def geturl(self):
        return 'https://www.investorab.com/download?id=report'


def test_real_pdf_extraction_in_child():
    assert 'Revenue SEK 100 million' in fetcher._pdf_text(pdf_bytes(), timeout=5)


def test_corrupt_pdf_is_not_report_text():
    assert fetcher._pdf_text(b'%PDF-1.4\ncorrupt', timeout=5) == ''


def test_binary_pdf_without_extension_is_detected(monkeypatch):
    monkeypatch.setattr(fetcher, 'urlopen', lambda *a, **k: Response(pdf_bytes()))
    result = fetcher.fetch_report_text('https://www.investorab.com/download?id=report', timeout=5)
    assert result['ok'] and 'Revenue SEK 100 million' in result['text']
    assert '%PDF' not in result['text']


def test_download_and_pdf_parsing_share_budget(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(fetcher.time, 'monotonic', lambda: clock[0])
    def open_url(*args, **kwargs):
        clock[0] += 6.0
        return Response(b'%PDF-1.4')
    budgets = []
    def parse(data, timeout):
        budgets.append(timeout)
        return 'Report text'
    monkeypatch.setattr(fetcher, 'urlopen', open_url)
    monkeypatch.setattr(fetcher, '_pdf_text', parse)
    assert fetcher.fetch_report_text('https://www.investorab.com/report.pdf', timeout=8)['ok']
    assert budgets == [2.0]


def test_no_parser_started_when_download_used_budget(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(fetcher.time, 'monotonic', lambda: clock[0])
    def open_url(*args, **kwargs):
        clock[0] += 9.0
        return Response(b'%PDF-1.4')
    monkeypatch.setattr(fetcher, 'urlopen', open_url)
    monkeypatch.setattr(fetcher.subprocess, 'run', lambda *a, **k: pytest.fail('No remaining budget'))
    result = fetcher.fetch_report_text('https://www.investorab.com/report.pdf', timeout=8)
    assert not result['ok'] and result['text'] == ''
    assert 'tidsbudget' in result['error']


def test_stuck_parser_is_killed_and_reaped_then_next_pdf_works(monkeypatch, tmp_path):
    pid_file = tmp_path / 'pid'
    worker = tmp_path / 'stuck.py'
    worker.write_text('import os, time\nfrom pathlib import Path\n'
                      f'Path({str(pid_file)!r}).write_text(str(os.getpid()))\n'
                      'time.sleep(60)\n')
    original = fetcher.PDF_WORKER
    monkeypatch.setattr(fetcher, 'PDF_WORKER', worker)
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        fetcher._pdf_text(b'%PDF-1.4', timeout=1)
    assert time.monotonic() - start < 5
    if os.name == 'posix':
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)
    monkeypatch.setattr(fetcher, 'PDF_WORKER', original)
    assert 'Revenue' in fetcher._pdf_text(pdf_bytes(), timeout=5)


def test_parser_timeout_never_marks_report_read(monkeypatch):
    monkeypatch.setattr(fetcher, 'urlopen', lambda *a, **k: Response(b'%PDF-1.4'))
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('parser', 1)
    monkeypatch.setattr(fetcher, '_pdf_text', timeout)
    report = fetcher.verify_primary_report_from_events({'news': [{
        'title': 'Company A Q2 2026 report',
        'link': 'https://view.news.eu.nasdaq.com/view?id=report',
    }]}, 'Sverige', company_name='Company A')
    assert report['Rapport läst'] is False
    assert 'tidsbudget' in report['Rapport kontroll']


def test_zero_budget_does_not_open_network(monkeypatch):
    monkeypatch.setattr(fetcher, 'urlopen', lambda *a, **k: pytest.fail('No budget'))
    assert not fetcher.fetch_report_text('https://www.investorab.com/report.pdf', timeout=0)['ok']
