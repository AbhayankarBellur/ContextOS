"""
ContextOS evaluator.py — Retrieval quality evaluation harness.

Measures retrieval accuracy against a golden question set.
Zero external dependencies — uses existing embedder + store.

Metrics:
  Hit Rate @K   — fraction of queries where expected doc is in top-K results
  MRR           — Mean Reciprocal Rank (1/rank of first correct result)
  Avg top-1     — mean similarity score of the top result
  No-result %   — fraction of queries returning zero results

Question format (eval/questions.json):
  [
    {
      "query": "how does payment retry work",
      "expected_title": "Payment Domain Model",
      "expected_type": "domain",
      "project": "my-project"
    }
  ]
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EvalQuestion:
    query:          str
    expected_title: str
    project:        Optional[str] = None
    expected_type:  Optional[str] = None
    k:              int = 5


@dataclass
class EvalResult:
    question:       EvalQuestion
    results:        list[dict]
    hit:            bool        # expected doc in top-K
    rank:           int         # 1-indexed rank of expected doc, 0 if not found
    top1_score:     float       # score of rank-1 result
    latency_ms:     int


@dataclass
class EvalSummary:
    total:          int
    hit_rate:       float       # 0.0 – 1.0
    mrr:            float       # Mean Reciprocal Rank
    avg_top1_score: float
    no_result_pct:  float
    avg_latency_ms: float
    results:        list[EvalResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total":           self.total,
            "hit_rate":        round(self.hit_rate, 4),
            "mrr":             round(self.mrr, 4),
            "avg_top1_score":  round(self.avg_top1_score, 4),
            "no_result_pct":   round(self.no_result_pct, 4),
            "avg_latency_ms":  round(self.avg_latency_ms, 1),
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_questions(path: Path) -> list[EvalQuestion]:
    """Load evaluation questions from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Eval questions file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Eval questions file must be a JSON array")
    questions = []
    for item in raw:
        questions.append(EvalQuestion(
            query          = item["query"],
            expected_title = item["expected_title"],
            project        = item.get("project"),
            expected_type  = item.get("expected_type"),
            k              = item.get("k", 5),
        ))
    return questions


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def run_eval(
    questions: list[EvalQuestion],
    embedder,
    store,
    use_hybrid: bool = True,
    hybrid_alpha: float = 0.7,
) -> EvalSummary:
    """
    Run retrieval evaluation against a golden question set.
    Returns EvalSummary with Hit Rate, MRR, avg scores.
    """
    results: list[EvalResult] = []

    for q in questions:
        t0 = time.time()

        try:
            qv = embedder.embed_query(q.query)

            if use_hybrid:
                raw = store.hybrid_search(
                    query_text=q.query,
                    query_vector=qv,
                    project=q.project,
                    type_filter=q.expected_type,
                    limit=q.k,
                    alpha=hybrid_alpha,
                )
            else:
                raw = store.search(
                    query_vector=qv,
                    project=q.project,
                    type_filter=q.expected_type,
                    limit=q.k,
                )
        except Exception as exc:
            logger.warning("Eval query failed '%s': %s", q.query, exc)
            raw = []

        latency_ms = int((time.time() - t0) * 1000)

        # Find rank of expected document
        rank = 0
        for i, r in enumerate(raw, 1):
            title = r.get("title", "").lower()
            if q.expected_title.lower() in title or title in q.expected_title.lower():
                rank = i
                break

        hit = rank > 0

        # Top-1 score
        top1_score = 0.0
        if raw:
            if "_rrf_score" in raw[0]:
                top1_score = min(float(raw[0]["_rrf_score"]) * 100, 1.0)
            else:
                top1_score = max(0.0, 1.0 - float(raw[0].get("_distance", 1.0)))

        results.append(EvalResult(
            question   = q,
            results    = raw,
            hit        = hit,
            rank       = rank,
            top1_score = top1_score,
            latency_ms = latency_ms,
        ))

    # Compute summary metrics
    total        = len(results)
    hits         = sum(1 for r in results if r.hit)
    hit_rate     = hits / total if total > 0 else 0.0
    mrr          = sum(1.0 / r.rank for r in results if r.rank > 0) / total if total > 0 else 0.0
    avg_top1     = sum(r.top1_score for r in results) / total if total > 0 else 0.0
    no_results   = sum(1 for r in results if not r.results)
    no_res_pct   = no_results / total if total > 0 else 0.0
    avg_latency  = sum(r.latency_ms for r in results) / total if total > 0 else 0.0

    return EvalSummary(
        total          = total,
        hit_rate       = hit_rate,
        mrr            = mrr,
        avg_top1_score = avg_top1,
        no_result_pct  = no_res_pct,
        avg_latency_ms = avg_latency,
        results        = results,
    )


def save_results(summary: EvalSummary, output_path: Path) -> None:
    """Save detailed eval results to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "summary": summary.as_dict(),
        "results": [
            {
                "query":          r.question.query,
                "expected_title": r.question.expected_title,
                "hit":            r.hit,
                "rank":           r.rank,
                "top1_score":     round(r.top1_score, 4),
                "latency_ms":     r.latency_ms,
                "top_results":    [
                    {"title": x.get("title",""), "score": round(
                        min(float(x.get("_rrf_score",0))*100, 1.0)
                        if "_rrf_score" in x
                        else max(0.0, 1.0 - float(x.get("_distance",1.0))), 4
                    )}
                    for x in r.results[:5]
                ],
            }
            for r in summary.results
        ],
    }
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Eval results saved to %s", output_path)
