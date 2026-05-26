from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

NODE_REGISTRY: dict[str, "NodeMeta"] = {}


@dataclass
class NodeMeta:
    name: str
    produces: str | list[str]
    color: str
    label: str
    fn_module: str
    fn_name: str
    reads: list[str] = field(default_factory=list)


def node(
    *,
    name: str,
    produces: str | list[str],
    color: str,
    label: str,
    reads: list[str] | None = None,
) -> Callable:
    def decorator(fn: Callable) -> Callable:
        if name in NODE_REGISTRY:
            raise ValueError(f"Node '{name}' is already registered")
        NODE_REGISTRY[name] = NodeMeta(
            name=name,
            produces=produces,
            color=color,
            label=label,
            fn_module=fn.__module__,
            fn_name=fn.__qualname__,
            reads=reads or [],
        )

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def get_registry() -> list[dict]:
    return [
        {
            "name": m.name,
            "produces": m.produces,
            "color": m.color,
            "label": m.label,
            "fn_module": m.fn_module,
            "fn_name": m.fn_name,
            "reads": m.reads,
        }
        for m in NODE_REGISTRY.values()
    ]
