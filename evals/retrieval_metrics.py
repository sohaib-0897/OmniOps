import math
from typing import Iterable, Sequence


def precision_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    selected = list(retrieved[:k])
    return sum(item in relevant_set for item in selected) / k if k else 0.0


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 1.0
    return len(set(retrieved[:k]).intersection(relevant_set)) / len(relevant_set)


def reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str]) -> float:
    relevant_set = set(relevant)
    for rank, item in enumerate(retrieved, 1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    dcg = sum((1.0 / math.log2(rank + 1)) for rank, item in enumerate(retrieved[:k], 1) if item in relevant_set)
    ideal_hits = min(len(relevant_set), k)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 1.0
