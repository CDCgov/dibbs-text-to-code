import json

SCORE_FILE = "../../../../data/training_files/scored_search_results.json"

with open(SCORE_FILE) as fp:
    score_data = json.loads(fp.read())

"""
Questions to answer:
- how many right answers there are total in this sample
- number of times the right answer occurs at each rank
- average gap between the answers of each rank
- when the right answer is at rank X, what is the gap between X and X+1, for each X
"""

query_results = score_data["query_score_distribution"]

# The "Auto-Classification" Threshold
# If something is in this category, just return the top score and don't
# even worry about reranking or other processing
# Basically all sum threshold values above 0.9 are somewhat interesting
# 1.0 cuts out 13.5k at 97.5% accuracy
# 0.98 is probably the best, as it cuts out a quarter with 97% top-1 accuracy
# 0.95 cuts out 21k at 96% accuracy
# 0.9 cuts out ~29k at 92% accuracy
query_results = [
    q
    for q in query_results
    if (q["search_scores"][0] >= 0.7) and (2 * q["search_scores"][0] - q["search_scores"][1]) >= 0.9
]

# The "No Good Matches" Threshold
# If something has a top score that's below a certain threshold,
# just don't even try to match it to begin with and return nothing
# This has basically almost no impact at all
query_results = [q for q in query_results if q["search_scores"][0] >= 0.5]

# Bottom threshold works as follows:
# For a given query, don't even consider an option as possibly the right
# answer if its score is below X and the score of the next best rank is
# at least Y better. Actually, maybe it's not the next best rank, because
# when we get into the worse positions on the list, the scores tend to
# clump up. Maybe it's that the current option has a low score and that
# score is below a specified margin of being within the top score for this
# query (that could also be better with first rule: the lower the top score
# score is, the super worse a bad option needs to be for us to auto-reject it)
# For 90 - 100, consider everything 60+
# For 80 - 89, consider everything 55+
# For 70 - 79, consider everything 50+
# For 60 - 69, consider everything 40+
# For 50 - 59, consider everything 35+
# Basically consider everything 60% of the ceiling of the tens range
# Formula is cutoff_threshold = (1 + int(10 * top_score)) * 6 / 100.0
# 80% of ceiling cuts out almost half the neighbors but maybe is a bit harsh,
# 75% cuts out a quarter of the neighbors and is kind of ideal for scoring
for i in range(len(query_results)):
    qr = query_results[i]
    top_score = qr["search_scores"][0]
    cutoff_threshold = (1 + int(10 * top_score)) * 7.5 / 100.0
    cutoff_idx = -1
    for j in range(1, len(qr["search_scores"])):
        if qr["search_scores"][j] < cutoff_threshold:
            cutoff_idx = j
            break
    qr["search_results"] = qr["search_results"][:j]
    qr["search_scores"] = qr["search_scores"][:j]

num_right_answers = 0
total_num_neighbors = 0
right_answers_at_rank = {int(k): 0 for k in range(1, 11)}
scores_at_rank = {int(k): [] for k in range(1, 11)}
right_answer_scores_at_rank = {int(k): [] for k in range(1, 11)}
# Note: only counts k values ranked above right answer's rank
# Slots below the right answer don't' have the opportunity to be wrong
wrong_scores_at_rank = {int(k): [] for k in range(1, 10)}
score_gap_with_next_rank = {int(k): [] for k in range(1, 10)}
right_answer_rank_gap = {int(k): [] for k in range(1, 10)}
wrong_answer_rank_gap = {int(k): [] for k in range(1, 10)}

for query in query_results:
    neighbors = query["search_results"]
    scores = query["search_scores"]
    right_answer = query["correct_code"]
    right_answer_rank = -1

    for i, n in enumerate(neighbors):
        total_num_neighbors += 1
        if n == right_answer and right_answer_rank == -1:
            right_answer_rank = i + 1
            num_right_answers += 1
            right_answers_at_rank[i + 1] = right_answers_at_rank[i + 1] + 1
            right_answer_scores_at_rank[i + 1].append(scores[i])
        scores_at_rank[i + 1].append(scores[i])

    for i in range(len(scores) - 1):
        gap = scores[i] - scores[i + 1]
        score_gap_with_next_rank[i + 1].append(gap)
        if i + 1 < right_answer_rank:
            wrong_scores_at_rank[i + 1].append(scores[i])
            wrong_answer_rank_gap[i + 1].append(gap)

    if right_answer_rank != -1 and right_answer_rank < len(scores):
        gap = scores[right_answer_rank - 1] - scores[right_answer_rank]
        right_answer_rank_gap[right_answer_rank].append(gap)

top_k_accuracies_stopping_at = {
    int(k): round(
        float(100 * sum([right_answers_at_rank[j] for j in range(1, k + 1)]))
        / float(len(query_results)),
        3,
    )
    for k in range(1, 11)
}

for k in right_answer_scores_at_rank:
    if len(right_answer_scores_at_rank[k]) == 0:
        right_answer_scores_at_rank[k] = "n/a"
    else:
        right_answer_scores_at_rank[k] = round(
            float(sum(right_answer_scores_at_rank[k])) / float(len(right_answer_scores_at_rank[k])),
            3,
        )

for k in scores_at_rank:
    if len(scores_at_rank[k]) == 0:
        scores_at_rank[k] = "n/a"
    else:
        scores_at_rank[k] = round(float(sum(scores_at_rank[k])) / float(len(scores_at_rank[k])), 3)

for k in wrong_scores_at_rank:
    if len(wrong_scores_at_rank[k]) == 0:
        wrong_scores_at_rank[k] = "n/a"
    else:
        wrong_scores_at_rank[k] = round(
            float(sum(wrong_scores_at_rank[k])) / float(len(wrong_scores_at_rank[k])), 3
        )

for k in score_gap_with_next_rank:
    if len(score_gap_with_next_rank[k]) == 0:
        score_gap_with_next_rank[k] = "n/a"
    else:
        score_gap_with_next_rank[k] = round(
            float(sum(score_gap_with_next_rank[k])) / float(len(score_gap_with_next_rank[k])), 3
        )

for k in right_answer_rank_gap:
    if len(right_answer_rank_gap[k]) == 0:
        right_answer_rank_gap[k] = "n/a"
    else:
        right_answer_rank_gap[k] = round(
            float(sum(right_answer_rank_gap[k])) / float(len(right_answer_rank_gap[k])), 3
        )

for k in wrong_answer_rank_gap:
    if len(wrong_answer_rank_gap[k]) == 0:
        wrong_answer_rank_gap[k] = "n/a"
    else:
        wrong_answer_rank_gap[k] = round(
            float(sum(wrong_answer_rank_gap[k])) / float(len(wrong_answer_rank_gap[k])), 3
        )


for k in right_answers_at_rank:
    pass
for k in top_k_accuracies_stopping_at:
    pass
for k in scores_at_rank:
    pass
for k in right_answer_scores_at_rank:
    pass
for k in wrong_scores_at_rank:
    pass
for k in score_gap_with_next_rank:
    pass
for k in right_answer_rank_gap:
    pass
for k in wrong_answer_rank_gap:
    pass
