# Budget PDF extraction helpers
SHELL := /usr/bin/env bash
VENV := ocr-env/bin/python

# Defaults
PDF  ?= output/redbook.pdf
PAGES ?= 20
DB   ?= output/slice.db

# Generate SQLite DB for first N pages (no physical slice needed)
db:
	$(VENV) pdf_to_excel_v2.py $(PDF) --max-pages $(PAGES) --sqlite -o $(DB)

# Slice a page range and generate DB (e.g. make slice FROM=29 TO=40)
FROM ?= 0
TO   ?= 10
slice:
	python3 -c "\
	from pypdf import PdfWriter, PdfReader; \
	w = PdfWriter(); \
	r = PdfReader('$(PDF)'); \
	[w.add_page(r.pages[i]) for i in range($(FROM)-1, $(TO))]; \
	w.write('output/slice-$(FROM)-$(TO).pdf')"
	$(VENV) pdf_to_excel_v2.py output/slice-$(FROM)-$(TO).pdf --sqlite -o $(DB)

# Quick verify against a DB
verify:
	python3 verify_budget.py $(DB) verify

# List all pages in a DB
pages:
	python3 verify_budget.py $(DB) pages

.PHONY: db slice verify pages
