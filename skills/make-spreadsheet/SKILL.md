---
name: make-spreadsheet
description: Use when asked to create an Excel workbook, xlsx or spreadsheet: tables, budgets, trackers, calculations. Layout, formulas and the limits of the generator.
---
The generator takes {"title", "sheets": [{"name", "columns", "rows"}]}. "columns" is the header row; "rows" is a list of lists.
1. One table per sheet, starting at A1: a header row, then data. No blank rows or columns inside the table and no merged cells.
2. Sheet names are short (at most 31 characters, none of / \ ? * [ ] :). Put assumptions and inputs on their own sheet called Inputs and refer to them from formulas.
3. Totals and derived columns are formulas, written as strings that start with "=" (for example "=SUM(B2:B13)" or "=B2*C2"). Never type a calculated number by hand. Excel calculates formulas when the file is opened, so the check line counts them but cannot show their values.
4. Numbers are numbers, not text: write 1250, not "1,250". Put units in the column header ("Revenue (EUR)"). Write dates as ISO text ("2026-03-31") unless the user needs date arithmetic.
5. At most 10 sheets and 5,000 rows. Order columns the way the user will read them: identifiers, then measures, then totals.
6. Do not invent data. Use the user's figures or documents. When asked for a template, leave the data cells empty and keep the formulas.
7. After the file is created, read the check line (sheets, filled cells, formulas). If it says 0 formulas but the sheet should calculate something, generate once more.
