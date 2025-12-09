"""
Core Text to Code code. This is the shared logic used for both the API/demo site and the Lambda.
"""


class SchematronError:
    location: str


class Eicr:
    pass


class Observation:
    pass


class Vector:
    pass


def resolve_nonstandard_text(schematron_output: str, eicr_id: str) -> str:
    """Given a schematron output and an eICR return a list of XPaths and new codes.

    Used by the Lambda.
    """

    errors = _get_relevant_errors(schematron_output)
    eicr = _retrieve_ecir(eicr_id)

    output = dict()

    for error in errors:
        embedding_candidates = _get_possibly_relevant_string(error, eicr)

        best_string = _get_best_candidate(embedding_candidates)

        opensearch_result = get_best_match(best_string)

        output[error.location] = opensearch_result

    return opensearch_result


def get_best_match(string: str) -> str:
    """Given a string return the best match.

    Used by the API and demo site.
    """

    vectorized_input = _vectorize(string)

    return _vector_search(vectorized_input)

    pass


def _retrieve_ecir(ecir_id) -> Eicr:
    pass


def _get_relevant_errors(schematron_output: str) -> list[SchematronError]:
    pass


def _get_possibly_relevant_string(error: SchematronError, eicr: Eicr) -> set[str]:
    pass


def _get_best_candidate(candidates: set[str]) -> str:
    pass


def _vectorize(string: str) -> Vector:
    pass


def _vector_search(search_vector: Vector) -> str:
    pass
