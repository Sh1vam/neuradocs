---
name: make-report
description: Use when asked to create a Word document, docx, a PDF report, memo, guide or write-up as a file. Section structure and the pitfalls of both generators.
---
Both generators take sections as a list of {"heading", "content"}. Paragraphs inside "content" are separated by a blank line.
1. Structure: a clear title, a short summary section first, then 3 to 7 sections in the order a reader needs them, and a last section with conclusions or next steps.
2. Headings describe the content ("Why sales dropped in March"), not the genre ("Overview").
3. Paragraphs of 2 to 5 sentences. Use a list only when the content is a list, one item per line.
4. Facts, numbers and quotes come from the user's material or uploaded documents; name the source file in the text. Never invent statistics.
5. PDF: never use Unicode subscript or superscript characters (H₂O, x²). The built-in fonts have no glyph for them and they print as black boxes. Write H2O, or use the markup <sub>2</sub> and <super>2</super>.
6. Word: headings come from the "heading" field. Do not type bullet characters or numbers by hand.
7. After the file is created, read the check line (headings or pages, word count) and generate once more if it looks wrong.
