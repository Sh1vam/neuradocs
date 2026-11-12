---
name: read-documents
description: Use when asked about uploaded files such as a PDF, Word, PowerPoint or Excel file: summarize, find a figure, compare, answer from them. Inventory first, read what is needed, cite the page or slide.
---
1. Say what you are reading before you answer: file type, size (pages, slides or sheets) and whether any text was found. If the text says the PDF has no text layer (scanned) or reports an extraction error, tell the user plainly and stop. Never guess the content.
2. Read just enough. Search the uploaded documents first (rag_search or ask_documents) and open more only when the answer is not there. Do not paste whole files into the answer.
3. Keep the structure and cite it: page numbers for PDFs ("p. 4"), "Slide N" for decks, sheet names for workbooks, headings for Word files.
4. Tables arrive as rows separated by " | " or tabs. Quote figures exactly as extracted; never round, convert or fill gaps. If a table looks broken, say so.
5. Lines starting with "Notes:" are the speaker notes of the slide above them: the author's own words.
6. Report what you could not read: images inside files, charts, handwriting, rows beyond the first 200 of a sheet. Offer the next step (OCR, a cleaner export).
7. With several files, answer per file first, then compare. Name the file for every claim.
