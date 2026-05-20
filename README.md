# Skill EndNote Research

Turn a rough research idea into a local EndNote literature pack.

`skill-endnote-research` is a Codex skill for researchers who keep PDFs in a local EndNote library indexed by `litlib`. Give it an idea such as "I want to study multiple M4 earthquakes occurring at the same place over several days"; it analyzes the possible research directions, searches the local literature index, copies matching PDFs, and creates a project-local literature review folder.

## What It Does

- Analyzes a research idea into searchable research directions.
- Translates Chinese research ideas into English and generates bilingual query families instead of relying on one keyword.
- Searches `litlib/index/papers.jsonl` with title/abstract priority.
- Confirms matches with cached full-text snippets.
- Copies matched PDFs into the project where the skill is invoked.
- Creates `文献列表.md`, `总结报告.md`, `检索记录.json`, and a `pdfs/` folder.

## Output Layout

When used from a project directory, the result is created in that project:

```text
文献梳理/
  <timestamp>-<question-slug>/
    文献列表.md
    总结报告.md
    检索记录.json
    pdfs/
```

The EndNote library path and the project output path are intentionally separate. `--workspace` points to the EndNote/litlib library; output defaults to `./文献梳理` in the directory where the command is run.

## Example

```bash
python3 ~/.codex/skills/skill-endnote-research/scripts/export_lit_review.py \
  --workspace /mnt/d/YIN/BaiduSyncdisk/endnote_file \
  --question "我要研究内江地区连续几天发生多次4级地震" \
  --query "内江 连续 多次 4级 地震" \
  --query "Neijiang multiple M4 earthquakes consecutive days" \
  --query "repeating earthquakes waveform similarity same source area" \
  --query "earthquake swarm same location M4 sequence" \
  --limit 20
```

If the input question is Chinese, the script adds conservative English query expansions for common seismology terms. Codex should still generate higher-quality bilingual queries from the research context before running the script.

## Promotional Taglines

- From a research hunch to a curated PDF pack.
- Your EndNote library, turned into a research scout.
- Ask a question; get directions, papers, PDFs, and a review folder.
- Stop searching file by file. Start from the research idea.
- A Codex skill for idea-driven literature discovery.

## Requirements

- A local `litlib` index with `litlib/index/papers.jsonl`.
- Cached full texts under `litlib/index/texts/`.
- PDF paths recorded in each paper record's `path` field.

## Included Files

- `SKILL.md`: Codex skill instructions.
- `scripts/export_lit_review.py`: deterministic export script.
- `agents/openai.yaml`: UI metadata.
