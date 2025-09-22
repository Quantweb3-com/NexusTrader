"""Strategy-aware FastAPI app utilities."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import update_wrapper
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI
from fastapi.routing import APIRouter, APIRoute


@dataclass
class _StrategyRoute:
    path: str
    endpoint: Callable[..., Any]
    kwargs: Dict[str, Any]
    bound_route: Optional[APIRoute] = None
    bound_endpoint: Optional[Callable[..., Any]] = None


class StrategyAPIRouter(APIRouter):
    """APIRouter that defers binding of strategy instance methods."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._strategy_routes: List[_StrategyRoute] = []
        self._baseline_route_count = len(self.routes)

    # when @app.post(...) is called, this method is invoked
    def add_api_route(
        self, path: str, endpoint: Callable[..., Any], **kwargs: Any
    ) -> None:  # type: ignore[override]
        if self._is_strategy_endpoint(
            endpoint
        ):  # first parameter is 'self', indicating a method, save it to self._strategy_routes
            self._strategy_routes.append(
                _StrategyRoute(path=path, endpoint=endpoint, kwargs=dict(kwargs))
            )
            return None
        return super().add_api_route(path, endpoint, **kwargs)

    def bind_strategy(self, strategy: Any) -> None:
        for route_def in self._strategy_routes:
            self._remove_existing_route(route_def)
            bound = self._wrap_endpoint(route_def.endpoint, strategy)
            super().add_api_route(route_def.path, bound, **route_def.kwargs)
            # Newly added route is the last item in self.routes
            route_def.bound_route = self.routes[-1]  # type: ignore[assignment]
            route_def.bound_endpoint = bound

    def unbind_strategy(self) -> None:
        for route_def in self._strategy_routes:
            if route_def.bound_route and route_def.bound_route in self.routes:
                self.routes.remove(route_def.bound_route)
                route_def.bound_route = None
                route_def.bound_endpoint = None

    def has_strategy_routes(self) -> bool:
        return bool(self._strategy_routes)

    def has_user_defined_routes(self) -> bool:
        return (
            self.has_strategy_routes() or len(self.routes) > self._baseline_route_count
        )

    @staticmethod
    def _is_strategy_endpoint(endpoint: Callable[..., Any]) -> bool:
        try:
            signature = inspect.signature(endpoint)
        except (TypeError, ValueError):
            return False

        params = list(signature.parameters.values())
        if not params:
            return False
        return params[0].name == "self"

    @staticmethod
    def _wrap_endpoint(
        endpoint: Callable[..., Any], strategy: Any
    ) -> Callable[..., Any]:
        signature = inspect.signature(endpoint)
        params = list(signature.parameters.values())
        if not params or params[0].name != "self":
            return endpoint

        stripped_signature = signature.replace(parameters=params[1:])

        if inspect.iscoroutinefunction(endpoint):

            async def _call(*args: Any, **kwargs: Any) -> Any:
                return await endpoint(strategy, *args, **kwargs)

        else:

            def _call(*args: Any, **kwargs: Any) -> Any:
                return endpoint(strategy, *args, **kwargs)

        update_wrapper(_call, endpoint)
        _call.__signature__ = stripped_signature  # type: ignore[attr-defined]
        return _call

    def _remove_existing_route(self, route_def: _StrategyRoute) -> None:
        if not route_def.bound_route:
            return
        if route_def.bound_route in self.routes:
            self.routes.remove(route_def.bound_route)
        route_def.bound_route = None
        route_def.bound_endpoint = None


class StrategyFastAPI(FastAPI):
    """FastAPI application that understands strategy instance methods."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        original_router: APIRouter = self.router
        router = StrategyAPIRouter(
            prefix=original_router.prefix,
            tags=original_router.tags,
            dependencies=original_router.dependencies,
            default_response_class=original_router.default_response_class,
            responses=original_router.responses,
            callbacks=original_router.callbacks,
            routes=list(original_router.routes),
            deprecated=original_router.deprecated,
            include_in_schema=original_router.include_in_schema,
            generate_unique_id_function=original_router.generate_unique_id_function,
        )
        router.route_class = original_router.route_class
        router.on_startup = original_router.on_startup
        router.on_shutdown = original_router.on_shutdown
        router.lifespan_context = original_router.lifespan_context

        self.router = router
        self._strategy_router: StrategyAPIRouter = router

    def bind_strategy(self, strategy: Any) -> None:
        self._strategy_router.bind_strategy(strategy)

    def unbind_strategy(self) -> None:
        self._strategy_router.unbind_strategy()

    def has_strategy_routes(self) -> bool:
        return self._strategy_router.has_strategy_routes()

    def has_user_routes(self) -> bool:
        return self._strategy_router.has_user_defined_routes()


def create_strategy_app(**kwargs: Any) -> StrategyFastAPI:
    """Create a strategy-aware FastAPI application."""

    return StrategyFastAPI(**kwargs)
