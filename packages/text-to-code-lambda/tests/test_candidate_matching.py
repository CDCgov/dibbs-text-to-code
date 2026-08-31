from lambda_handler.models import (
    OpenSearchHit,
    OpenSearchHits,
    OpenSearchHitSource,
    OpenSearchResult,
    OpenSearchShards,
)
from shared_models import DataField
from text_to_code.models import Candidate, LabXPaths
from text_to_code.models.registry import (
    HIGH_RANK_THRESHOLD,
    HIGH_SCORE,
    LEADER_MARGIN,
    LOW_SCORE,
    MAX_MARGIN,
    MIN_MARGIN,
)
from text_to_code_lambda import lambda_function


class TestCandidateMatching:
    def test_match_candidate_prunes_results_outside_adaptive_margin(
        self,
        mock_opensearch,
        mocker,
    ):
        selected_candidate = Candidate(
            value="weed allergen mix 3",
            xpath=LabXPaths.CODE_DISPLAY_NAME,
        )

        opensearch_retrieved_scores = OpenSearchResult(
            took=1,
            timed_out=False,
            _shards=OpenSearchShards(total=3, successful=1, skipped=0, failed=0),
            hits=OpenSearchHits(
                total={"value": 3},
                hits=[
                    OpenSearchHit(
                        _id="top-result",
                        _index="ttc_index",
                        _score=LOW_SCORE,
                        _source=OpenSearchHitSource(
                            description="Top Result",
                            id=0,
                            loinc_code="11111-1",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="within-margin",
                        _index="ttc_index",
                        _score=LOW_SCORE - (MAX_MARGIN / 2.0),
                        _source=OpenSearchHitSource(
                            description="Within Margin Result",
                            id=1,
                            loinc_code="22222-2",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-margin",
                        _index="ttc_index",
                        _score=LOW_SCORE - (MAX_MARGIN * 2),
                        _source=OpenSearchHitSource(
                            description="Outside Margin Result",
                            id=2,
                            loinc_code="33333-3",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                ],
            ),
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=opensearch_retrieved_scores,
        )

        reranker_model_mock = mocker.patch(
            "text_to_code.services.reranker._RERANKER.rank",
            return_value=[
                {"corpus_id": 0, "score": 0.9},
                {"corpus_id": 1, "score": 0.8},
                {"corpus_id": 2, "score": 0.7},
            ],
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.put_new_cached_result",
        )

        lambda_function._match_candidate(
            selected_candidate=selected_candidate,
            embedding=[0.1, 0.2, 0.3],
            data_field=DataField.LAB_TEST_NAME_ORDERED,
            cache_key="cache-key",
            opensearch_client=mock_opensearch,
        )

        reranker_model_mock.assert_called_once_with(
            "weed allergen mix 3",
            [
                "Top Result",
                "Within Margin Result",
                "Outside Margin Result",
            ],
        )

    def test_match_candidate_prunes_results_using_min_margin_for_high_score(
        self,
        mock_opensearch,
        mocker,
    ):
        selected_candidate = Candidate(
            value="weed allergen mix 3",
            xpath=LabXPaths.CODE_DISPLAY_NAME,
        )

        opensearch_retrieved_scores = OpenSearchResult(
            took=1,
            timed_out=False,
            _shards=OpenSearchShards(total=4, successful=1, skipped=0, failed=0),
            hits=OpenSearchHits(
                total={"value": 4},
                hits=[
                    OpenSearchHit(
                        _id="top-result",
                        _index="ttc_index",
                        _score=HIGH_SCORE,
                        _source=OpenSearchHitSource(
                            description="Top Result",
                            id=0,
                            loinc_code="11111-1",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="within-margin-1",
                        _index="ttc_index",
                        _score=HIGH_SCORE - (MIN_MARGIN / 3.0),
                        _source=OpenSearchHitSource(
                            description="Within Margin Result 1",
                            id=1,
                            loinc_code="22222-2",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="within-margin-2",
                        _index="ttc_index",
                        _score=HIGH_SCORE - (MIN_MARGIN / 2.0),
                        _source=OpenSearchHitSource(
                            description="Within Margin Result 2",
                            id=2,
                            loinc_code="33333-3",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-margin",
                        _index="ttc_index",
                        _score=HIGH_SCORE - (MIN_MARGIN * 5),
                        _source=OpenSearchHitSource(
                            description="Outside Margin Result",
                            id=3,
                            loinc_code="44444-4",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                ],
            ),
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=opensearch_retrieved_scores,
        )

        reranker_model_mock = mocker.patch(
            "text_to_code.services.reranker._RERANKER.rank",
            return_value=[
                {"corpus_id": 0, "score": 0.9},
                {"corpus_id": 1, "score": 0.8},
                {"corpus_id": 2, "score": 0.7},
            ],
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.put_new_cached_result",
        )

        lambda_function._match_candidate(
            selected_candidate=selected_candidate,
            embedding=[0.1, 0.2, 0.3],
            data_field=DataField.LAB_TEST_NAME_ORDERED,
            cache_key="cache-key",
            opensearch_client=mock_opensearch,
        )

        reranker_model_mock.assert_called_once_with(
            "weed allergen mix 3",
            [
                "Top Result",
                "Within Margin Result 1",
                "Within Margin Result 2",
            ],
        )

    def test_match_candidate_prunes_results_using_interpolated_margin(
        self,
        mock_opensearch,
        mocker,
    ):
        selected_candidate = Candidate(
            value="weed allergen mix 3",
            xpath=LabXPaths.CODE_DISPLAY_NAME,
        )

        top_score = (LOW_SCORE + HIGH_SCORE) / 2
        adaptive_margin = (MAX_MARGIN + MIN_MARGIN) / 2

        opensearch_retrieved_scores = OpenSearchResult(
            took=1,
            timed_out=False,
            _shards=OpenSearchShards(total=4, successful=1, skipped=0, failed=0),
            hits=OpenSearchHits(
                total={"value": 4},
                hits=[
                    OpenSearchHit(
                        _id="top-result",
                        _index="ttc_index",
                        _score=top_score,
                        _source=OpenSearchHitSource(
                            description="Top Result",
                            id=0,
                            loinc_code="11111-1",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="within-margin-1",
                        _index="ttc_index",
                        _score=top_score - (adaptive_margin / 3),
                        _source=OpenSearchHitSource(
                            description="Within Margin Result 1",
                            id=1,
                            loinc_code="22222-2",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="within-margin-2",
                        _index="ttc_index",
                        _score=top_score - (adaptive_margin / 2),
                        _source=OpenSearchHitSource(
                            description="Within Margin Result 2",
                            id=2,
                            loinc_code="33333-3",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-margin",
                        _index="ttc_index",
                        _score=top_score - (adaptive_margin * 2),
                        _source=OpenSearchHitSource(
                            description="Outside Margin Result",
                            id=3,
                            loinc_code="44444-4",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                ],
            ),
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=opensearch_retrieved_scores,
        )

        reranker_model_mock = mocker.patch(
            "text_to_code.services.reranker._RERANKER.rank",
            return_value=[
                {"corpus_id": 0, "score": 0.9},
                {"corpus_id": 1, "score": 0.8},
                {"corpus_id": 2, "score": 0.7},
            ],
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.put_new_cached_result",
        )

        lambda_function._match_candidate(
            selected_candidate=selected_candidate,
            embedding=[0.1, 0.2, 0.3],
            data_field=DataField.LAB_TEST_NAME_ORDERED,
            cache_key="cache-key",
            opensearch_client=mock_opensearch,
        )

        reranker_model_mock.assert_called_once_with(
            "weed allergen mix 3",
            [
                "Top Result",
                "Within Margin Result 1",
                "Within Margin Result 2",
            ],
        )

    def test_match_candidate_keeps_result_at_margin_boundary(
        self,
        mock_opensearch,
        mocker,
    ):
        selected_candidate = Candidate(
            value="weed allergen mix 3",
            xpath=LabXPaths.CODE_DISPLAY_NAME,
        )

        opensearch_retrieved_scores = OpenSearchResult(
            took=1,
            timed_out=False,
            _shards=OpenSearchShards(total=4, successful=1, skipped=0, failed=0),
            hits=OpenSearchHits(
                total={"value": 4},
                hits=[
                    OpenSearchHit(
                        _id="top-result",
                        _index="ttc_index",
                        _score=LOW_SCORE,
                        _source=OpenSearchHitSource(
                            description="Top Result",
                            id=0,
                            loinc_code="11111-1",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="within-margin-result",
                        _index="ttc_index",
                        _score=LOW_SCORE - (MAX_MARGIN / 2),
                        _source=OpenSearchHitSource(
                            description="Within Margin Result",
                            id=1,
                            loinc_code="22222-2",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="boundary-result",
                        _index="ttc_index",
                        _score=LOW_SCORE - MAX_MARGIN,
                        _source=OpenSearchHitSource(
                            description="Boundary Result",
                            id=2,
                            loinc_code="33333-3",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-margin",
                        _index="ttc_index",
                        _score=LOW_SCORE - MAX_MARGIN - 0.001,
                        _source=OpenSearchHitSource(
                            description="Outside Margin Result",
                            id=3,
                            loinc_code="44444-4",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                ],
            ),
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=opensearch_retrieved_scores,
        )

        reranker_model_mock = mocker.patch(
            "text_to_code.services.reranker._RERANKER.rank",
            return_value=[
                {"corpus_id": 0, "score": 0.9},
                {"corpus_id": 1, "score": 0.8},
                {"corpus_id": 2, "score": 0.7},
            ],
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.put_new_cached_result",
        )

        lambda_function._match_candidate(
            selected_candidate=selected_candidate,
            embedding=[0.1, 0.2, 0.3],
            data_field=DataField.LAB_TEST_NAME_ORDERED,
            cache_key="cache-key",
            opensearch_client=mock_opensearch,
        )

        reranker_model_mock.assert_called_once_with(
            "weed allergen mix 3",
            [
                "Top Result",
                "Within Margin Result",
                "Boundary Result",
            ],
        )

    def test_match_candidate_caches_only_reranker_results_that_survive_pruning(
        self,
        mock_opensearch,
        mocker,
    ):
        selected_candidate = Candidate(
            value="weed allergen mix 3",
            xpath=LabXPaths.CODE_DISPLAY_NAME,
        )

        opensearch_retrieved_scores = OpenSearchResult(
            took=1,
            timed_out=False,
            _shards=OpenSearchShards(total=3, successful=1, skipped=0, failed=0),
            hits=OpenSearchHits(
                total={"value": 3},
                hits=[
                    OpenSearchHit(
                        _id="top-result",
                        _index="ttc_index",
                        _score=LOW_SCORE,
                        _source=OpenSearchHitSource(
                            description="Top Result",
                            id=0,
                            loinc_code="11111-1",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="within-margin",
                        _index="ttc_index",
                        _score=LOW_SCORE - (MAX_MARGIN / 2),
                        _source=OpenSearchHitSource(
                            description="Within Margin Result",
                            id=1,
                            loinc_code="22222-2",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-margin",
                        _index="ttc_index",
                        _score=LOW_SCORE - (MAX_MARGIN * 2),
                        _source=OpenSearchHitSource(
                            description="Outside Margin Result",
                            id=2,
                            loinc_code="33333-3",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                ],
            ),
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=opensearch_retrieved_scores,
        )

        mocker.patch(
            "text_to_code.services.reranker._RERANKER.rank",
            return_value=[
                {"corpus_id": 0, "score": 0.9},
                {"corpus_id": 1, "score": 0.8},
            ],
        )

        put_cached_mock = mocker.patch(
            "text_to_code_lambda.lambda_function.put_new_cached_result",
        )

        (
            new_translation,
            unmatched_message,
            retrieved_scores,
            ranked_results,
        ) = lambda_function._match_candidate(
            selected_candidate=selected_candidate,
            embedding=[0.1, 0.2],
            data_field=DataField.LAB_TEST_NAME_ORDERED,
            cache_key="cache-key",
            opensearch_client=mock_opensearch,
        )

        assert new_translation is not None
        assert unmatched_message is None
        assert retrieved_scores == opensearch_retrieved_scores
        assert len(retrieved_scores.hits.hits) == 3  # noqa - PLR2004
        assert ranked_results == [
            {"code_string": "Top Result", "score": 0.9},
            {"code_string": "Within Margin Result", "score": 0.8},
        ]

        put_cached_mock.assert_called_once()
        assert (
            put_cached_mock.call_args.kwargs["opensearch_retrieved_scores"]
            == opensearch_retrieved_scores
        )
        assert put_cached_mock.call_args.kwargs["reranker_processed_results"] == [
            {"code_string": "Top Result", "score": 0.9},
            {"code_string": "Within Margin Result", "score": 0.8},
        ]

    def test_perfect_sim_match_heuristic(self, mock_opensearch, mocker):
        selected_candidate = Candidate(
            value="Nucleated erythrocytes/Leukocytes [Ratio] in Blood by Automated count",
            xpath=LabXPaths.CODE_DISPLAY_NAME,
        )

        opensearch_retrieved_scores = OpenSearchResult(
            took=1,
            timed_out=False,
            _shards=OpenSearchShards(total=4, successful=1, skipped=0, failed=0),
            hits=OpenSearchHits(
                total={"value": 4},
                hits=[
                    OpenSearchHit(
                        _id="perfect-match",
                        _index="ttc_index",
                        _score=1.0,
                        _source=OpenSearchHitSource(
                            description="Nucleated erythrocytes/Leukocytes [Ratio] in Blood by Automated count",
                            id=0,
                            loinc_code="11111-1",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="near-perfect-1",
                        _index="ttc_index",
                        _score=0.99999,
                        _source=OpenSearchHitSource(
                            description="Near Perfect Below Leader Margin",
                            id=1,
                            loinc_code="22222-2",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="near-perfect-2",
                        _index="ttc_index",
                        _score=0.99,
                        _source=OpenSearchHitSource(
                            description="Near Perfect Above Leader Margin",
                            id=2,
                            loinc_code="33333-3",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-margin",
                        _index="ttc_index",
                        _score=HIGH_SCORE,
                        _source=OpenSearchHitSource(
                            description="Outside Margin Result",
                            id=3,
                            loinc_code="44444-4",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                ],
            ),
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=opensearch_retrieved_scores,
        )

        mocker.patch(
            "text_to_code.services.reranker._RERANKER.rank",
            return_value=[
                {"corpus_id": 1, "score": 0.9},
                {"corpus_id": 0, "score": 0.8},
                {"corpus_id": 2, "score": 0.7},
            ],
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.put_new_cached_result",
        )

        new_translation, _, _, _ = lambda_function._match_candidate(
            selected_candidate=selected_candidate,
            embedding=[0.1, 0.2, 0.3],
            data_field=DataField.LAB_TEST_NAME_ORDERED,
            cache_key="cache-key",
            opensearch_client=mock_opensearch,
        )
        assert new_translation is not None
        assert new_translation.display_name == selected_candidate.value

    def test_leader_margin_heuristic(self, mock_opensearch, mocker):
        selected_candidate = Candidate(
            value="NRBC Count",
            xpath=LabXPaths.CODE_DISPLAY_NAME,
        )

        top_score = 0.98
        runner_up_score = 2 * top_score - LEADER_MARGIN - 0.001

        opensearch_retrieved_scores = OpenSearchResult(
            took=1,
            timed_out=False,
            _shards=OpenSearchShards(total=4, successful=1, skipped=0, failed=0),
            hits=OpenSearchHits(
                total={"value": 4},
                hits=[
                    OpenSearchHit(
                        _id="top-result",
                        _index="ttc_index",
                        _score=top_score,
                        _source=OpenSearchHitSource(
                            description="Nucleated erythrocytes/Leukocytes [Ratio] in Blood by Automated count",
                            id=0,
                            loinc_code="11111-1",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="runner-up",
                        _index="ttc_index",
                        _score=runner_up_score,
                        _source=OpenSearchHitSource(
                            description="Second Place, Below Leader Margin",
                            id=1,
                            loinc_code="22222-2",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="third-place",
                        _index="ttc_index",
                        _score=runner_up_score - 0.01,
                        _source=OpenSearchHitSource(
                            description="Third Place",
                            id=2,
                            loinc_code="33333-3",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-margin",
                        _index="ttc_index",
                        _score=runner_up_score - 0.02,
                        _source=OpenSearchHitSource(
                            description="Last Place",
                            id=3,
                            loinc_code="44444-4",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                ],
            ),
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=opensearch_retrieved_scores,
        )

        mocker.patch(
            "text_to_code.services.reranker._RERANKER.rank",
            return_value=[
                {"corpus_id": 0, "score": 0.9},
                {"corpus_id": 1, "score": 0.8},
                {"corpus_id": 2, "score": 0.7},
            ],
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.put_new_cached_result",
        )

        new_translation, _, _, _ = lambda_function._match_candidate(
            selected_candidate=selected_candidate,
            embedding=[0.1, 0.2, 0.3],
            data_field=DataField.LAB_TEST_NAME_ORDERED,
            cache_key="cache-key",
            opensearch_client=mock_opensearch,
        )
        assert new_translation is not None
        assert (
            new_translation.display_name
            == "Nucleated erythrocytes/Leukocytes [Ratio] in Blood by Automated count"
        )

    def test_high_threshold_ranking_heuristic(self, mock_opensearch, mocker):
        selected_candidate = Candidate(
            value="NRBC Count",
            xpath=LabXPaths.CODE_DISPLAY_NAME,
        )

        opensearch_retrieved_scores = OpenSearchResult(
            took=1,
            timed_out=False,
            _shards=OpenSearchShards(total=4, successful=1, skipped=0, failed=0),
            hits=OpenSearchHits(
                total={"value": 4},
                hits=[
                    OpenSearchHit(
                        _id="top-result",
                        _index="ttc_index",
                        _score=HIGH_RANK_THRESHOLD + 0.02,
                        _source=OpenSearchHitSource(
                            description="Nucleated erythrocytes/Leukocytes [Ratio] in Blood by Automated count",
                            id=0,
                            loinc_code="11111-1",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="runner-up",
                        _index="ttc_index",
                        _score=HIGH_RANK_THRESHOLD + 0.01,
                        _source=OpenSearchHitSource(
                            description="Second Place, Above HRT",
                            id=1,
                            loinc_code="22222-2",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-hrt-1",
                        _index="ttc_index",
                        _score=HIGH_RANK_THRESHOLD - 0.01,
                        _source=OpenSearchHitSource(
                            description="Outside HRT 1",
                            id=2,
                            loinc_code="33333-3",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                    OpenSearchHit(
                        _id="outside-hrt-2",
                        _index="ttc_index",
                        _score=HIGH_RANK_THRESHOLD - 0.02,
                        _source=OpenSearchHitSource(
                            description="Outside HRT 2",
                            id=3,
                            loinc_code="44444-4",
                            loinc_name_type="Long Common Name",
                            loinc_type="Order",
                        ),
                    ),
                ],
            ),
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.lambda_handler.retrieve_opensearch_results",
            return_value=opensearch_retrieved_scores,
        )

        reranker_model_mock = mocker.patch(
            "text_to_code.services.reranker._RERANKER.rank",
            return_value=[
                {"corpus_id": 0, "score": 0.9},
                {"corpus_id": 1, "score": 0.8},
            ],
        )

        mocker.patch(
            "text_to_code_lambda.lambda_function.put_new_cached_result",
        )

        new_translation, _, _, _ = lambda_function._match_candidate(
            selected_candidate=selected_candidate,
            embedding=[0.1, 0.2],
            data_field=DataField.LAB_TEST_NAME_ORDERED,
            cache_key="cache-key",
            opensearch_client=mock_opensearch,
        )
        assert new_translation is not None
        assert (
            new_translation.display_name
            == "Nucleated erythrocytes/Leukocytes [Ratio] in Blood by Automated count"
        )

        reranker_model_mock.assert_called_once_with(
            "NRBC Count",
            [
                "Nucleated erythrocytes/Leukocytes [Ratio] in Blood by Automated count",
                "Second Place, Above HRT",
            ],
        )
