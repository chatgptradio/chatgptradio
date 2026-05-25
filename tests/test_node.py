import pytest

import core.node as node_module


@pytest.fixture(autouse=True)
def clear_registry():
    node_module.NODE_REGISTRY.clear()
    yield
    node_module.NODE_REGISTRY.clear()


def test_decorator_registers_sync_function():
    @node_module.node(name="test_fn", produces="excitement", color="#FF0000", label="Test")
    def my_fn(state):
        return 0.5

    assert "test_fn" in node_module.NODE_REGISTRY


def test_decorator_registers_async_function():
    @node_module.node(name="async_fn", produces="anxiety", color="#00FF00", label="Async")
    async def my_async_fn(state):
        return 0.3

    assert "async_fn" in node_module.NODE_REGISTRY


def test_decorator_does_not_change_behavior():
    @node_module.node(name="identity", produces="creativity", color="#0000FF", label="Id")
    def add_one(x):
        return x + 1

    assert add_one(41) == 42


def test_duplicate_name_raises_value_error():
    @node_module.node(name="dup", produces="x", color="#111", label="First")
    def fn1():
        pass

    with pytest.raises(ValueError, match="dup"):
        @node_module.node(name="dup", produces="y", color="#222", label="Second")
        def fn2():
            pass


def test_get_registry_returns_3_entries():
    @node_module.node(name="n1", produces="f1", color="#1", label="L1", reads=["a", "b"])
    def f1():
        pass

    @node_module.node(name="n2", produces="f2", color="#2", label="L2")
    def f2():
        pass

    @node_module.node(name="n3", produces="f3", color="#3", label="L3")
    def f3():
        pass

    reg = node_module.get_registry()
    assert len(reg) == 3
    names = {r["name"] for r in reg}
    assert names == {"n1", "n2", "n3"}


def test_registry_entry_has_correct_metadata():
    @node_module.node(
        name="openai_status",
        produces="openai_status",
        color="#FF4444",
        label="OpenAI Status RSS",
        reads=["openai_latency_ms"],
    )
    def collect_status(state):
        pass

    entry = node_module.NODE_REGISTRY["openai_status"]
    assert entry.produces == "openai_status"
    assert entry.color == "#FF4444"
    assert entry.label == "OpenAI Status RSS"
    assert entry.reads == ["openai_latency_ms"]


def test_get_registry_is_json_serializable():
    import json

    @node_module.node(name="x", produces="y", color="#z", label="Z")
    def fn():
        pass

    reg = node_module.get_registry()
    dumped = json.dumps(reg)
    assert "fn_module" in dumped
    assert "fn_name" in dumped
