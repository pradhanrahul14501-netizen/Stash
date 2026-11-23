"""Small adapter that keeps route implementations wired to main's services."""

from functools import wraps
import sys

# `main.py` is also the executable entry point. When launched as a script,
# importing it here would load a second copy named `main` and recursively
# import these route modules before this module has finished initializing.
_main = sys.modules.get("main") or sys.modules.get("__main__")
if _main is None or not hasattr(_main, "_route_blueprint"):
    raise ImportError("Stash route modules must be loaded by main.py after route setup.")


def bind_routes(namespace):
    namespace.update({name: value for name, value in vars(_main).items() if not name.startswith("__")})
    namespace["__file__"] = _main.__file__

    def route(path, *args, **kwargs):
        def register(function):
            invoke = getattr(function, "__stash_route_wrapper__", None)
            if invoke is not None:
                return _main._route_blueprint(path).route(path, *args, **kwargs)(invoke)

            @wraps(function)
            def invoke(*call_args, **call_kwargs):
                namespace.update({
                    name: value
                    for name, value in vars(_main).items()
                    if not name.startswith("__")
                })
                namespace["__file__"] = _main.__file__
                return function(*call_args, **call_kwargs)

            invoke.__stash_route_wrapper__ = invoke
            _main._route_blueprint(path).route(path, *args, **kwargs)(invoke)
            return invoke

        return register

    return route
