import pkgutil
import importlib
from ..core.plugin_base import AnalysisPlugin


def discover_plugins():
    plugins = []
    package = __package__

    for _, module_name, _ in pkgutil.iter_modules([__path__[0]]):
        mod = importlib.import_module(f'.{module_name}', package)
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, AnalysisPlugin)
                and attr is not AnalysisPlugin
            ):
                plugins.append(attr())

    return plugins
