from __future__ import annotations

import sqlite3
import sys
import time
from typing import List, Tuple

from aeternitas.common.config import get_openai_api_key
from aeternitas.common.openai_client import call_openai_responses


def fetch_timeline_rows(
    con: sqlite3.Connection,
    date_from: str,
    date_to: str,
) -> List[sqlite3.Row]:
    q = """
    SELECT t.date, t.kind, t.title, t.snippet, t.doc_id
    FROM timeline t
    WHERE t.date >= ? AND t.date <= ?
    ORDER BY t.date ASC
    """
    return con.execute(q, (date_from, date_to)).fetchall()


def build_items_text(rows: List[sqlite3.Row]) -> str:
    lines: List[str] = []
    for r in rows:
        date = r["date"]
        kind = r["kind"]
        title = r["title"] or ""
        snippet = r["snippet"] or ""
        lines.append(f"- {date} [{kind}] {title}: {snippet}")
    return "\n".join(lines)


def chunk_text(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for line in text.splitlines():
        add_len = len(line) + 1
        if cur_len + add_len > max_chars and cur:
            chunks.append("\n".join(cur))
            cur = [line]
            cur_len = len(line) + 1
        else:
            cur.append(line)
            cur_len += add_len
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def summarize_chunk(model: str, text: str) -> str:
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("Missing OpenAI API key. Set OPENAI_API_KEY or ~/.aeternitas/ai.json")
    prompt = (
        "Tiivistä seuraavat aikajanamerkinnät 3–6 lauseella. "
        "Pidä kronologia, älä keksi uusia faktoja. "
        "Lopuksi listaa 3–7 avainsanaa (henkilöt/paikat/aiheet).\n\n"
        "Merkinnät:\n"
        f"{text}"
    )
    return call_openai_responses(api_key=api_key, model=model, input_text=prompt, temperature=0.2)


def narrate(
    con: sqlite3.Connection,
    date_from: str,
    date_to: str,
    model: str,
    max_chars: int = 6000,
    delay_seconds: float = 1.0,
) -> Tuple[str, List[str]]:
    rows = fetch_timeline_rows(con, date_from, date_to)
    items_text = build_items_text(rows)
    if not items_text.strip():
        return ("", [])

    chunks = chunk_text(items_text, max_chars=max_chars)
    print(f"[narrate] {len(chunks)} chunks to summarize.", file=sys.stderr, flush=True)
    summaries: List[str] = []
    for i, ch in enumerate(chunks, start=1):
        print(f"[narrate] Summarizing chunk {i}/{len(chunks)}...", file=sys.stderr, flush=True)
        summaries.append(summarize_chunk(model=model, text=ch))
        print(f"[narrate] Chunk {i}/{len(chunks)} done.", file=sys.stderr, flush=True)
        if delay_seconds > 0 and i < len(chunks):
            time.sleep(delay_seconds)

    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("Missing OpenAI API key. Set OPENAI_API_KEY or ~/.aeternitas/ai.json")

    final_prompt = (
        f"Kirjoita kooste ajanjaksolle {date_from}–{date_to}. "
        "Käytä vain annettuja tiivistelmiä, älä keksi uutta. "
        "Pidä kronologia ja tee neutraali, selkeä kertomus.\n\n"
        "Tiivistelmät:\n"
        + "\n\n".join(f"[Osa {i+1}] {s}" for i, s in enumerate(summaries))
    )
    print("[narrate] Building final narrative...", file=sys.stderr, flush=True)
    narrative = call_openai_responses(api_key=api_key, model=model, input_text=final_prompt, temperature=0.2)
    print("[narrate] Narrative done.", file=sys.stderr, flush=True)
    return (narrative, summaries)
