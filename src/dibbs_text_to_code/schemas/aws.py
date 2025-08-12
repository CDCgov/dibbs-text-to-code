import typing


class EventBridgeBucket(typing.TypedDict):
    name: str


class EventBridgeObject(typing.TypedDict):
    key: str


class EventBridgeDetail(typing.TypedDict):
    bucket: EventBridgeBucket
    object: EventBridgeObject


class EventBridgeEvent(typing.TypedDict):
    detail: EventBridgeDetail
