import asyncio
import io
import json
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

import llm_client
import main
import skillset

client = TestClient(main.app)


def docx_bytes():
    from docx import Document
    d = Document()
    d.add_heading('Plan', 1)
    d.add_paragraph('Intro text here.')
    t = d.add_table(rows=2, cols=2)
    for (r, c), v in {(0, 0): 'A', (0, 1): 'B', (1, 0): '1', (1, 1): '2'}.items():
        t.cell(r, c).text = v
    d.add_paragraph('After the table.')
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def pdf_bytes(with_text):
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b)
    if with_text:
        c.drawString(72, 720, 'Hello from page one. Totals are 1,250 euros.')
    else:
        c.rect(50, 50, 100, 100, fill=1)                      # a page with no text: like a scan
    c.showPage()
    c.save()
    return b.getvalue()


def test_word_headings_and_tables_are_read_in_document_order():
    assert main.extract_text_from_file(docx_bytes(), 'plan.docx').splitlines() == \
        ['# Plan', 'Intro text here.', 'A | B', '1 | 2', 'After the table.']


def test_powerpoint_text_tables_groups_and_notes_are_read():
    from pptx import Presentation
    from pptx.util import Inches
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[5])
    s.shapes.title.text = 'Quarterly plan'
    s.shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(1)).text_frame.text = 'Ship the builder'
    t = s.shapes.add_table(2, 2, Inches(1), Inches(3), Inches(4), Inches(1)).table
    for (r, c), v in {(0, 0): 'Metric', (0, 1): 'Value', (1, 0): 'Users', (1, 1): '42'}.items():
        t.cell(r, c).text = v
    s.shapes.add_group_shape().shapes.add_textbox(Inches(1), Inches(5), Inches(3), Inches(1)).text_frame.text = 'Inside a group'
    s.notes_slide.notes_text_frame.text = 'Say this slowly'
    b = io.BytesIO()
    p.save(b)
    text = main.extract_text_from_file(b.getvalue(), 'deck.pptx')
    assert text.startswith('## Slide 1: Quarterly plan')
    for part in ('Ship the builder', 'Metric | Value', 'Users | 42', 'Inside a group', 'Notes: Say this slowly'):
        assert part in text


def test_excel_sheets_are_read_with_their_names():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Data'
    ws.append(['name', 'qty'])
    ws.append(['apples', 3])
    wb.create_sheet('Notes').append(['hello'])
    b = io.BytesIO()
    wb.save(b)
    text = main.extract_text_from_file(b.getvalue(), 'book.xlsx')
    assert '## Sheet: Data' in text and 'apples\t3' in text and '## Sheet: Notes' in text


def test_pdf_pages_are_marked_and_a_scan_or_a_broken_file_is_reported():
    assert main.extract_text_from_file(pdf_bytes(True), 'r.pdf').startswith('[Page 1]\nHello from page one')
    scanned = main.extract_text_from_file(pdf_bytes(False), 's.pdf')
    assert scanned.startswith('[PDF has no text layer') and 'OCR' in scanned
    assert main.extract_text_from_file(b'not a pdf', 'x.pdf').startswith('[PDF extraction error')


def test_upload_refuses_what_could_not_be_read_instead_of_indexing_the_message():
    r = client.post('/api/upload', files={'file': ('scan.pdf', pdf_bytes(False), 'application/pdf')})
    assert r.status_code == 422 and 'no text layer' in r.text
    assert client.post('/api/upload', files={'file': ('ok.pdf', pdf_bytes(True), 'application/pdf')}).status_code == 200


def test_pdf_generator_survives_markup_characters(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'OUTPUT_DIR', tmp_path)
    name = main.create_pdf_file('R&D < Plan', [{'heading': 'a < b & c', 'content': 'x & y\n\nH<sub>2</sub>O is water.'}])
    text = main.extract_text_from_file((tmp_path / name).read_bytes(), name)
    assert 'a < b & c' in text and 'water' in text


def test_generated_files_are_read_back_and_counted(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'OUTPUT_DIR', tmp_path)
    deck = main.create_pptx_file('Topic', [{'type': 'title', 'title': 'Sub'}, {'title': 'Plan', 'content': ['one', 'two']}])
    assert '2 slides' in main.check_file(deck)
    assert main.check_file(main.create_docx_file_py('T', [])).startswith('Check: ')


def test_generate_file_tool_makes_docx_with_the_skill_and_a_check(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'OUTPUT_DIR', tmp_path)
    seen = []
    body = json.dumps({'title': 'Sales report', 'sections': [{'heading': 'Summary', 'content': 'Sales rose 12 percent in the third quarter, driven by the new product line.'}]})

    def create(**kw):
        seen.append(kw)
        return NS(choices=[NS(message=NS(content=body, tool_calls=None))], usage=NS(prompt_tokens=1, completion_tokens=1))
    monkeypatch.setattr(main, 'groq_client', llm_client.GroqAdapter(NS(chat=NS(completions=NS(create=create)))))
    msg = asyncio.run(main.tool_generate_file('docx', 'Quarterly sales report'))
    assert 'File generated' in msg and '.docx' in msg and 'Check:' in msg
    assert 'make-report' in seen[0]['messages'][0]['content']                 # the file skill was in the prompt


def test_file_skills_match_file_requests():
    assert skillset.match('make a presentation about our sales')[0]['name'] == 'make-presentation'
    assert skillset.match('summarize this PDF')[0]['name'] == 'read-documents'
    assert skillset.match('write a Word report on churn')[0]['name'] == 'make-report'


def test_excel_files_are_generated_and_checked(monkeypatch, tmp_path):
    from openpyxl import load_workbook
    monkeypatch.setattr(main, 'OUTPUT_DIR', tmp_path)
    name = main.create_xlsx_file('Budget', [{'name': 'Q1/Plan', 'columns': ['Item', 'Cost'],
                                             'rows': [['Rent', 1200], ['Food', 300], ['Total', '=SUM(B2:B3)']]}])
    ws = load_workbook(tmp_path / name)['Q1_Plan']                           # "/" is not allowed in a sheet name
    assert ws['A1'].font.bold and ws.freeze_panes == 'A2' and ws['B4'].value == '=SUM(B2:B3)'
    assert '1 sheets' in main.check_file(name) and '1 formulas' in main.check_file(name)
    assert 'empty' in main.check_file(main.create_xlsx_file('E', [{'name': 'S', 'columns': [], 'rows': []}]))


def test_generate_file_tool_makes_xlsx_with_the_skill(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'OUTPUT_DIR', tmp_path)
    seen = []
    body = json.dumps({'title': 'Budget', 'sheets': [{'name': 'Plan', 'columns': ['Item', 'Cost'], 'rows': [['Rent', 1200], ['Total', '=SUM(B2:B2)']]}]})

    def create(**kw):
        seen.append(kw)
        return NS(choices=[NS(message=NS(content=body, tool_calls=None))], usage=NS(prompt_tokens=1, completion_tokens=1))
    monkeypatch.setattr(main, 'groq_client', llm_client.GroqAdapter(NS(chat=NS(completions=NS(create=create)))))
    msg = asyncio.run(main.tool_generate_file('xlsx', 'Monthly budget spreadsheet'))
    assert 'File generated' in msg and '.xlsx' in msg and 'Check: 1 sheets' in msg
    assert 'make-spreadsheet' in seen[0]['messages'][0]['content']
