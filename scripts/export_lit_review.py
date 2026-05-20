#!/usr/bin/env python3
"""Export a local litlib search result into a literature-review folder."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable


LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-']+|\d+(?:\.\d+)?")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
SPACE_RE = re.compile(r"[ \t\r\f\v]+")
BAD_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')

ZH_EN_QUERY_TERMS = [
    ("内江", "Neijiang"),
    ("四川", "Sichuan"),
    ("同一个地点", "same location"),
    ("同一地点", "same location"),
    ("同一地区", "same area"),
    ("连续几天", "several days"),
    ("连续", "consecutive"),
    ("多次", "multiple"),
    ("4级", "M4 magnitude 4 Mw 4 ML 4"),
    ("地震", "earthquake seismicity"),
    ("震群", "earthquake swarm"),
    ("重复地震", "repeating earthquakes"),
    ("波形相似", "waveform similarity"),
    ("同一震源区", "same source area"),
    ("诱发地震", "induced seismicity"),
    ("流体触发", "fluid triggering"),
    ("孔隙压力", "pore pressure"),
    ("断层活化", "fault activation"),
    ("地震序列", "earthquake sequence"),
    ("余震", "aftershock sequence"),
    ("时空迁移", "spatiotemporal migration"),
    ("地震目录", "earthquake catalog"),
    ("重定位", "earthquake relocation"),
]


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"-\n(?=[A-Za-z])", "", text)
    text = re.sub(r"(?<![。！？；：])\n(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = SPACE_RE.sub(" ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    lower = text.lower()
    tokens = LATIN_RE.findall(lower)
    cjk = CJK_RE.findall(text)
    tokens.extend("".join(cjk[i : i + 2]) for i in range(max(0, len(cjk) - 1)))
    tokens.extend("".join(cjk[i : i + 3]) for i in range(max(0, len(cjk) - 2)))
    return [t for t in tokens if t.strip()]


def load_records(index_file: Path) -> list[dict]:
    records = []
    with index_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))
    return records


def read_text(workspace: Path, rec: dict) -> str:
    rel = rec.get("text_path") or ""
    if not rel:
        return ""
    path = workspace / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_queries(args: argparse.Namespace) -> list[str]:
    queries = []
    if args.question:
        queries.append(args.question)
    if args.query:
        queries.extend(args.query)
    if args.queries_file:
        path = Path(args.queries_file)
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    queries.append(line)

    seen = set()
    unique = []
    for query in queries:
        normalized = SPACE_RE.sub(" ", query).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return expand_bilingual_queries(unique)


def expand_bilingual_queries(queries: list[str]) -> list[str]:
    expanded = list(queries)
    for query in queries:
        if not CJK_RE.search(query):
            continue
        english_terms = []
        for zh, en in ZH_EN_QUERY_TERMS:
            if zh in query:
                english_terms.append(en)
        if english_terms:
            expanded.append(" ".join(dict.fromkeys(" ".join(english_terms).split())))
        if "地震" in query:
            expanded.extend([
                "earthquake swarm same location consecutive days",
                "multiple M4 earthquakes same area earthquake sequence",
                "repeating earthquakes waveform similarity same source area",
                "seismicity cluster spatiotemporal migration earthquake catalog",
            ])

    seen = set()
    unique = []
    for query in expanded:
        normalized = SPACE_RE.sub(" ", query).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique


def slugify(text: str, fallback: str = "lit-review") -> str:
    text = clean_text(text)
    cjk = "".join(re.findall(r"[\u4e00-\u9fff0-9]+", text))
    latin = "-".join(LATIN_RE.findall(text.lower()))
    if cjk:
        base = cjk[:18]
    elif latin:
        base = latin[:60].strip("-")
    else:
        base = fallback
    base = BAD_FILENAME_RE.sub("-", base)
    base = re.sub(r"-{2,}", "-", base).strip("-._ ")
    return base or fallback


def truncate_utf8(text: str, max_bytes: int) -> str:
    out = []
    used = 0
    for char in text:
        size = len(char.encode("utf-8"))
        if used + size > max_bytes:
            break
        out.append(char)
        used += size
    return "".join(out).rstrip("._ ")


def clean_filename_part(text: str) -> str:
    text = unicodedata.normalize("NFKC", clean_text(text))
    text = "".join(char for char in text if not unicodedata.category(char).startswith("C"))
    text = BAD_FILENAME_RE.sub("_", text)
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text


def safe_pdf_name(rank: int, rec: dict) -> str:
    source_name = Path(rec.get("path") or "").stem
    title = clean_filename_part(source_name) or clean_filename_part(rec.get("title") or rec.get("id") or "paper")
    title = truncate_utf8(title, 72)
    if not title:
        title = "paper"
    return f"{rank:02d}_{rec.get('id', 'unknown')}_{title}.pdf"


def snippet(text: str, terms: Iterable[str], width: int = 520) -> str:
    if not text:
        return ""
    lower = text.lower()
    positions = []
    for term in terms:
        term = term.lower().strip()
        if not term:
            continue
        pos = lower.find(term)
        if pos >= 0:
            positions.append(pos)
    pos = min(positions) if positions else 0
    start = max(0, pos - width // 4)
    return clean_text(text[start : start + width]).replace("\n", " ")


def build_idf(records: list[dict], query_tokens: set[str]) -> dict[str, float]:
    doc_freq = Counter()
    for rec in records:
        combined = " ".join([rec.get("title", ""), rec.get("abstract", "")])
        doc_freq.update(set(tokenize(combined)))
    total = max(1, len(records))
    return {t: math.log((1 + total) / (1 + doc_freq.get(t, 0))) + 1 for t in query_tokens}


def score_counts(content: str, query_tokens: list[str], idf: dict[str, float]) -> float:
    counts = Counter(tokenize(content))
    return score_counter(counts, query_tokens, idf)


def score_counter(counts: Counter, query_tokens: list[str], idf: dict[str, float]) -> float:
    return sum((1 + math.log(counts[t])) * idf.get(t, 1.0) for t in query_tokens if counts.get(t))


def search_records(workspace: Path, records: list[dict], queries: list[str], limit: int) -> list[dict]:
    query_tokens_by_query = {q: tokenize(q) for q in queries}
    all_tokens = {t for tokens in query_tokens_by_query.values() for t in tokens}
    idf = build_idf(records, all_tokens)
    prepared = [
        (
            rec,
            Counter(tokenize(rec.get("title", ""))),
            Counter(tokenize(rec.get("abstract", ""))),
        )
        for rec in records
    ]
    candidates: dict[str, dict] = {}

    for query, query_tokens in query_tokens_by_query.items():
        if not query_tokens:
            continue
        for rec, title_counts, abstract_counts in prepared:
            title = rec.get("title", "")
            abstract = rec.get("abstract", "")
            title_score = score_counter(title_counts, query_tokens, idf)
            abstract_score = score_counter(abstract_counts, query_tokens, idf)
            primary_score = 8.0 * title_score + 4.0 * abstract_score
            if primary_score <= 0:
                continue

            rec_id = rec["id"]
            existing = candidates.get(rec_id)
            hit = {
                "_rec": rec,
                "_best_single_score": primary_score,
                "id": rec_id,
                "title": title,
                "year": rec.get("year", ""),
                "authors": rec.get("authors", ""),
                "abstract": abstract,
                "path": rec.get("path", ""),
                "text_path": rec.get("text_path", ""),
                "score": round(primary_score, 4),
                "best_query": query,
                "matched_queries": [query],
                "match_fields": [],
                "snippet": snippet(abstract or title, [query] + query_tokens),
            }
            if title_score > 0:
                hit["match_fields"].append("title")
            if abstract_score > 0:
                hit["match_fields"].append("abstract")

            if existing:
                existing["score"] = round(existing["score"] + primary_score, 4)
                existing["matched_queries"].append(query)
                existing["match_fields"] = sorted(set(existing["match_fields"]) | set(hit["match_fields"]))
                if primary_score > existing.get("_best_single_score", 0):
                    existing["_best_single_score"] = primary_score
                    existing["best_query"] = query
                    existing["snippet"] = hit["snippet"]
            else:
                candidates[rec_id] = hit

    candidate_limit = max(limit * 8, 60)
    hits = sorted(candidates.values(), key=lambda item: item["score"], reverse=True)[:candidate_limit]
    for hit in hits:
        rec = hit.pop("_rec")
        full_text = read_text(workspace, rec)[:250000]
        if not full_text:
            continue
        text_counts = Counter(tokenize(full_text))
        text_score = 0.0
        text_terms: list[str] = []
        for query in hit["matched_queries"]:
            query_tokens = query_tokens_by_query.get(query, [])
            text_score += score_counter(text_counts, query_tokens, idf)
            text_terms.extend(query_tokens)
        if text_score > 0:
            hit["score"] = round(hit["score"] + text_score, 4)
            hit["match_fields"] = sorted(set(hit["match_fields"]) | {"text"})
            hit["snippet"] = snippet(full_text, [hit["best_query"]] + text_terms)

    hits = sorted(hits, key=lambda item: item["score"], reverse=True)
    for hit in hits:
        hit.pop("_best_single_score", None)
        hit["matched_queries"] = sorted(set(hit["matched_queries"]))
    return hits[:limit]


def make_output_dir(output_root: str | None, question: str) -> Path:
    root = Path(output_root).expanduser() if output_root else Path.cwd() / "文献梳理"
    if not root.is_absolute():
        root = Path.cwd() / root
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = root / f"{stamp}-{slugify(question)}"
    if out.exists():
        suffix = hashlib.sha1(str(datetime.now().timestamp()).encode()).hexdigest()[:6]
        out = root / f"{stamp}-{slugify(question)}-{suffix}"
    (out / "pdfs").mkdir(parents=True, exist_ok=True)
    return out


def copy_pdfs(workspace: Path, out_dir: Path, hits: list[dict]) -> tuple[int, list[dict]]:
    missing = []
    copied = 0
    for rank, hit in enumerate(hits, 1):
        rel = hit.get("path") or ""
        src = workspace / rel
        if not rel or not src.exists():
            missing.append({"id": hit["id"], "title": hit.get("title", ""), "path": rel})
            continue
        dest = out_dir / "pdfs" / safe_pdf_name(rank, hit)
        shutil.copy2(src, dest)
        hit["copied_pdf"] = str(dest.relative_to(out_dir))
        copied += 1
    return copied, missing


def group_hits(hits: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    patterns = [
        ("诱发地震与工程活动", re.compile(r"induced|reservoir|wastewater|geothermal|injection|水库|诱发|注水|地热", re.I)),
        ("震群与重复地震", re.compile(r"swarm|sequence|cluster|repeat|multiplet|震群|序列|重复", re.I)),
        ("流体与孔隙压力触发", re.compile(r"fluid|pore|pressure|hydraulic|overpressure|流体|孔隙|压力", re.I)),
        ("断层活动与构造背景", re.compile(r"fault|tectonic|rupture|stress|断层|构造|破裂|应力", re.I)),
        ("目录统计与时空迁移方法", re.compile(r"catalog|migration|spatiotemporal|relocation|statistics|目录|迁移|定位|统计", re.I)),
    ]
    for hit in hits:
        text = " ".join([hit.get("title", ""), hit.get("abstract", ""), hit.get("snippet", "")])
        placed = False
        for group, pattern in patterns:
            if pattern.search(text):
                groups[group].append(hit)
                placed = True
        if not placed:
            groups["其他相关文献"].append(hit)
    return dict(groups)


def write_literature_list(out_dir: Path, question: str, queries: list[str], hits: list[dict], copied: int, missing: list[dict]) -> None:
    lines = [
        "# 文献列表",
        "",
        f"- 研究想法：{question}",
        f"- 检索时间：{datetime.now().isoformat(timespec='minutes')}",
        f"- 检索式数量：{len(queries)}",
        f"- 入选文献：{len(hits)}",
        f"- 已复制 PDF：{copied}",
        "",
        "## 检索式",
        "",
    ]
    lines.extend(f"- {query}" for query in queries)
    lines.extend(["", "## 入选文献", ""])

    if not hits:
        lines.extend([
            "未找到匹配文献。建议补充更具体的地点、机制、英文术语或研究对象后重新检索。",
            "",
        ])
    for rank, hit in enumerate(hits, 1):
        lines.extend([
            f"### {rank}. {hit.get('title') or hit['id']}",
            "",
            f"- ID：`{hit['id']}`",
            f"- 年份：{hit.get('year') or '?'}",
            f"- 作者：{hit.get('authors') or '未从 PDF 元数据识别'}",
            f"- 分数：{hit.get('score')}",
            f"- 匹配字段：{', '.join(hit.get('match_fields') or [])}",
            f"- 最佳检索式：{hit.get('best_query')}",
            f"- 源 PDF：`{hit.get('path')}`",
            f"- 复制 PDF：`{hit.get('copied_pdf', '未复制')}`",
            "",
            "摘要/片段：",
            "",
            f"> {hit.get('snippet') or clean_text(hit.get('abstract', ''))[:520]}",
            "",
        ])

    if missing:
        lines.extend(["## 未复制的 PDF", ""])
        for item in missing:
            lines.append(f"- `{item['id']}` {item.get('title', '')}：`{item.get('path', '')}`")
        lines.append("")

    (out_dir / "文献列表.md").write_text("\n".join(lines), encoding="utf-8")


def write_summary(out_dir: Path, question: str, hits: list[dict]) -> None:
    groups = group_hits(hits)
    lines = [
        "# 总结报告",
        "",
        f"## 研究想法",
        "",
        question,
        "",
        "## 初步研究方向图谱",
        "",
        "- 事件现象：同一地点、短时间内、多次中等强度地震，适合从震群、重复地震或主震-余震序列角度判断。",
        "- 触发机制：重点检查流体压力、工程扰动、断层应力状态和构造加载是否能解释时间集中性。",
        "- 数据方法：需要地震目录重定位、震源机制、震级-频度关系、时空迁移、波形相似性和区域构造背景。",
        "- 研究产出：可形成事件成因判别、危险性讨论、与典型诱发或自然震群案例对比的文献综述。",
        "",
        "## 文献分组",
        "",
    ]

    if not hits:
        lines.extend([
            "本次检索未得到候选文献。下一步应扩大关键词，加入具体地点名、英文地名、震级写法（M4, Mw 4, ML 4）、机制词和相邻区域名。",
            "",
        ])
    else:
        for group, items in groups.items():
            lines.append(f"### {group}")
            lines.append("")
            for item in items[:8]:
                lines.append(f"- {item.get('title') or item['id']} ({item.get('year') or '?'})：匹配 `{item.get('best_query')}`。")
            lines.append("")

    lines.extend([
        "## 可借鉴方法",
        "",
        "- 先建立事件序列的精定位目录，确认是否真正在同一断层段或同一震源区重复发生。",
        "- 用波形相似性、震源机制和应力场约束区分重复破裂、震群活动和普通余震序列。",
        "- 若区域存在水库、地热、注采或采矿活动，应加入水位、注采量、孔隙压力扩散或库仑应力变化资料。",
        "- 对比自然构造震群和工程诱发地震案例，避免只根据时间集中性直接归因。",
        "",
        "## 后续精读建议",
        "",
        "- 优先精读 `文献列表.md` 中匹配字段包含 title 或 abstract 的文献。",
        "- 对只在 full text 命中的文献，先确认片段是否真正讨论目标机制。",
        "- 回到 PDF 核对图件、数据来源、事件筛选标准和作者对成因的限制性表述。",
        "",
    ])
    (out_dir / "总结报告.md").write_text("\n".join(lines), encoding="utf-8")


def write_record(out_dir: Path, question: str, queries: list[str], hits: list[dict], copied: int, missing: list[dict], workspace: Path) -> None:
    data = {
        "question": question,
        "workspace": str(workspace),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "queries": queries,
        "selected_count": len(hits),
        "copied_pdf_count": copied,
        "missing_pdfs": missing,
        "hits": hits,
    }
    (out_dir / "检索记录.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export local litlib matches into a literature-review folder.")
    parser.add_argument("--workspace", default=".", help="EndNote/litlib workspace containing litlib/index/papers.jsonl.")
    parser.add_argument("--question", required=True, help="Research idea or question.")
    parser.add_argument("--query", action="append", help="Additional search query. May be repeated.")
    parser.add_argument("--queries-file", help="UTF-8 text file with one query per line.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum selected records.")
    parser.add_argument("--output-root", help="Output root. Defaults to ./文献梳理 in the directory where the command is run.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    index_file = workspace / "litlib" / "index" / "papers.jsonl"
    text_dir = workspace / "litlib" / "index" / "texts"
    if not index_file.exists() or not text_dir.exists():
        print(
            "This does not look like a litlib workspace. Provide --workspace pointing to a directory containing litlib/index/papers.jsonl.",
            file=sys.stderr,
        )
        return 2

    queries = read_queries(args)
    if not queries:
        print("No search queries were provided.", file=sys.stderr)
        return 2

    records = load_records(index_file)
    out_dir = make_output_dir(args.output_root, args.question)
    hits = search_records(workspace, records, queries, args.limit)
    copied, missing = copy_pdfs(workspace, out_dir, hits)
    write_literature_list(out_dir, args.question, queries, hits, copied, missing)
    write_summary(out_dir, args.question, hits)
    write_record(out_dir, args.question, queries, hits, copied, missing, workspace)

    print(f"Output: {out_dir}")
    print(f"Selected records: {len(hits)}")
    print(f"Copied PDFs: {copied}")
    if missing:
        print(f"Missing PDFs: {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
