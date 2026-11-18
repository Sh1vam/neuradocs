---
name: make-presentation
description: Use when asked to create a PowerPoint, pptx, slides, a deck or a presentation. Slide structure and the limits of the generator, so nothing overflows.
---
The generator takes slides as a list of {"title", "content", "type"}; the first slide has "type": "title". Every bullet is drawn on its own single line.
1. 6 to 10 slides: a title slide, an agenda only if there are more than 6 slides, one idea per content slide, and a closing slide with the summary or next steps.
2. Titles are statements ("Revenue grew 12% in Q3"), at most 8 words.
3. Each content slide has 3 to 6 bullets and each bullet fits on one line (under 90 characters). Longer text overlaps the next bullet, so split it over two slides instead.
4. "content" is a list of short strings, never one long paragraph, and never contains bullet characters: the generator adds them.
5. Facts and figures come from the user's request or their documents. If a number is not known, leave it out rather than inventing one.
6. No filler slides ("Thank you", "Questions?") unless the user asks for them.
7. After the file is created, read the check line (slide and word count). If the counts look wrong, fix the content and generate once more.
