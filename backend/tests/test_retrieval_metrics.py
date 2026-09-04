from evals.retrieval_metrics import precision_at_k, recall_at_k, reciprocal_rank, ndcg_at_k


def test_retrieval_metrics_are_calculated_from_ranked_results():
    retrieved = ["irrelevant", "relevant-a", "relevant-b"]
    relevant = {"relevant-a", "relevant-b"}
    assert precision_at_k(retrieved, relevant, 3) == 2 / 3
    assert recall_at_k(retrieved, relevant, 2) == 1 / 2
    assert reciprocal_rank(retrieved, relevant) == 1 / 2
    assert 0 < ndcg_at_k(retrieved, relevant, 3) < 1
