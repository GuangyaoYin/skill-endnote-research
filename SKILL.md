---
name: litlib-research-scout
description: Use when the user gives a research idea and wants Codex to analyze possible research directions, search the local EndNote litlib index, create a literature list, copy matching PDFs, and generate a literature-review folder with a report. This skill is designed for the local EndNote workspace that contains litlib/index/papers.jsonl and My EndNote Library-Saved(1).Data/PDF.
---

# Litlib Research Scout

Use this skill for Chinese or English research-idea prompts such as:

- "我要研究同一个地点连续几天发生多次4级地震"
- "帮我从本地 EndNote 库找这个想法相关的文献并整理"
- "根据这个研究问题生成文献梳理文件夹"

## Workflow

1. Identify two paths and keep them separate.
   - **Output path**: use the directory where the user invoked Codex as the project output location. Create `文献梳理/` there by default.
   - **EndNote/litlib workspace**: use the directory that contains `litlib/index/papers.jsonl`; for this user's local library, the usual path is `/mnt/d/YIN/BaiduSyncdisk/endnote_file`.
   - If the current directory is not the EndNote workspace, still keep output in the current project directory and pass the EndNote library path via `--workspace`.
2. Analyze the idea before searching.
   - State the likely research directions and why they matter.
   - For earthquake/seismology ideas, consider directions such as earthquake swarms, repeated earthquakes, induced seismicity, fluid triggering, fault activation, catalog statistics, migration patterns, focal mechanisms, stress transfer, geothermal/reservoir/wastewater contexts, and hazard implications.
3. Translate Chinese research ideas into English before searching.
   - If the user prompt is Chinese, write an English translation first. Example: `我要研究内江地区连续几天发生多次4级地震` -> `I want to study multiple magnitude-4 earthquakes occurring in the Neijiang area over several consecutive days`.
   - Search both Chinese-language and English-language literature in the local library. Do not treat a Chinese prompt as Chinese-only retrieval.
4. Generate multiple Chinese and English search queries.
   - Include the original Chinese wording, the English translation, location names in Chinese and English, domain synonyms, mechanism terms, and method terms.
   - For the Neijiang example, include queries such as `内江 连续 多次 4级 地震`, `Neijiang multiple M4 earthquakes consecutive days`, `earthquake swarm same location magnitude 4`, `repeating earthquakes waveform similarity`, and `seismicity cluster spatiotemporal migration`.
   - Write these queries to a temporary text file when using the export script.
5. Run the bundled script to create the archive.
   - Script path: `scripts/export_lit_review.py`
   - Example:

```bash
python3 ~/.codex/skills/litlib-research-scout/scripts/export_lit_review.py \
  --workspace /mnt/d/YIN/BaiduSyncdisk/endnote_file \
  --question "我要研究同一个地点连续几天发生多次4级地震" \
  --queries-file /tmp/litlib_queries.txt \
  --limit 20
```

6. Read `文献列表.md` and `检索记录.json`.
   - Use title/abstract matches as the primary retrieval evidence.
   - Use full-text snippets for confirmation and close-reading direction.
   - If the result set is weak, say so explicitly and suggest better query families.
7. Write or revise `总结报告.md` in the created output folder.
   - Include: research-direction map, key literature groups, useful methods, initial research questions, likely data requirements, and next close-reading steps.
   - Distinguish what the literature supports from Codex interpretation.

## Script Behavior

The script reads:

- `litlib/index/papers.jsonl`
- `litlib/index/texts/*.txt`
- each record's `path` field for the source PDF

It creates:

```text
<directory where the command is run>/文献梳理/
  <timestamp>-<question-slug>/
    文献列表.md
    总结报告.md
    检索记录.json
    pdfs/
```

Default retrieval is title/abstract first, then full-text confirmation. It copies PDFs for matched records when the source files exist.

## Output Guidance

When reporting back to the user, mention:

- the created folder path
- how many literature records were selected
- how many PDFs were copied
- any missing PDFs or weak-result caveats
- the main research directions found

Do not modify `litlib/litlib.py` unless the user explicitly asks to change the library tool itself.
