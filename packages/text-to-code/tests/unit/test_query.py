from augmentation.models.eicr import DataField
from text_to_code.models.query import VectorSearchParams
from text_to_code.services.query import KNNQuery
from text_to_code.services.query import QueryBuilder
from text_to_code.services.query import TermsFilter


class TestKNNQuery:
    def test_knn_query_defaults(self):
        query = KNNQuery(field="descriptionVector", vector=[0.1, 0.2, 0.3])
        expected_opensearch_query = {
            "knn": {
                "descriptionVector": {
                    "vector": [0.1, 0.2, 0.3],
                    "k": 10,
                }
            }
        }
        assert query.to_opensearch() == expected_opensearch_query

    def test_knn_query_customized_input(self):
        query = KNNQuery(field="customVector", vector=[0.1, 0.2, 0.3], k=8)
        expected_opensearch_query = {
            "knn": {
                "customVector": {
                    "vector": [0.1, 0.2, 0.3],
                    "k": 8,
                }
            }
        }
        assert query.to_opensearch() == expected_opensearch_query


class TestTermFilter:
    def test_term_filter_defaults(self):
        filter = TermsFilter(value=["Order"])
        expected_opensearch_query = {"terms": {"type": ["Order"]}}
        assert filter.to_opensearch() == expected_opensearch_query

    def test_term_filter_custom_field(self):
        filter = TermsFilter(field="customField", value=["Observation"])
        expected_opensearch_query = {"terms": {"customField": ["Observation"]}}
        assert filter.to_opensearch() == expected_opensearch_query

    def test_term_filter_multiple_values(self):
        filter = TermsFilter(value=["Order", "Observation"])
        expected_opensearch_query = {"terms": {"type": ["Order", "Observation"]}}
        assert filter.to_opensearch() == expected_opensearch_query


class TestQueryBuilder:
    def test_query_builder(self):
        size = 5
        vector = [0.1, 0.2, 0.3]
        data_field = DataField.LAB_TEST_NAME_ORDERED
        vector_field = "descriptionVector"
        filter_value = ["Order", "Both"]
        filter_field = "type"
        k = 10

        expected_query = {
            "size": size,
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {filter_field: filter_value}},
                    ],
                    "must": [
                        {
                            "knn": {
                                vector_field: {
                                    "vector": vector,
                                    "k": k,
                                }
                            }
                        }
                    ],
                }
            },
        }
        params = VectorSearchParams(
            vector=vector,
            data_field=data_field,
            size=size,
            filter_field=filter_field,
            filter_value=filter_value,
            vector_field=vector_field,
            k=k,
        )
        query = QueryBuilder().with_vector_search(params)
        assert query.build() == expected_query

    def test_query_builder_with_defaults(self):
        vector = [0.1, 0.2, 0.3]
        data_field = DataField.LAB_TEST_NAME_ORDERED

        expected_query = {
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {"type": ["Order", "Both"]}},
                    ],
                    "must": [
                        {
                            "knn": {
                                "descriptionVector": {
                                    "vector": vector,
                                    "k": 10,
                                }
                            }
                        }
                    ],
                }
            },
        }
        params = VectorSearchParams(
            vector=vector,
            data_field=data_field,
        )
        query = QueryBuilder().with_vector_search(params)
        assert query.build() == expected_query

    def test_query_builder_with_multiple_filters(self):
        vector = [0.1, 0.2, 0.3]
        data_field = DataField.LAB_TEST_NAME_ORDERED
        filter_field = "type"
        filter_value = ["Order", "Both"]

        expected_query = {
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {filter_field: filter_value}},
                    ],
                    "must": [
                        {
                            "knn": {
                                "descriptionVector": {
                                    "vector": vector,
                                    "k": 10,
                                }
                            }
                        }
                    ],
                }
            },
        }
        params = VectorSearchParams(
            vector=vector,
            data_field=data_field,
            filter_field=filter_field,
            filter_value=filter_value,
        )
        query = QueryBuilder().with_vector_search(params)
        assert query.build() == expected_query
