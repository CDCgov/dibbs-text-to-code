from dibbs_text_to_code import main


def test_handler():
    resp = main.handler({}, {})
    assert resp == {"message": "DIBBS Text to Code!", "event": {}}
