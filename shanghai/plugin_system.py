# Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
# Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>
#
# This file is part of Shanghai, an asynchronous multi-server IRC bot.
#
# Shanghai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shanghai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Shanghai.  If not, see <http://www.gnu.org/licenses/>.

import ast
import importlib.util
import pathlib
import os
import sys
from typing import Dict, Generator, Iterable, NamedTuple, Type, TypeVar, Union
from types import ModuleType
import keyword

from .logging import get_logger, get_default_logger

T = TypeVar('T')
TType = Type[T]


class CyclicDependency(Exception):
    pass


class PluginModuleInfo(NamedTuple):

    """Storage type holding infor about a plugin."""

    name: str
    version: str
    description: str
    depends: Iterable[str] = ()
    conflicts: Iterable[str] = ()

    @classmethod
    def read_from_file(cls, path: pathlib.Path, identifier: str) -> 'PluginModuleInfo':
        with path.open('r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), str(path))

        info_dict: Dict[str, Union[str, Iterable]] = {}
        required_ids = set(cls._fields) - set(cls._field_defaults.keys())

        for statement in tree.body:
            if not isinstance(statement, ast.Assign):
                continue
            if len(statement.targets) != 1:
                continue
            target = statement.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if not target.id.startswith('__plugin_') or not target.id.endswith('__'):
                continue
            _id: str = target.id.strip('_')[7:]

            if _id not in cls._fields:
                continue
            elif _id in ('depends', 'conflicts'):
                listing = statement.value
                if not isinstance(listing, ast.Tuple):
                    raise TypeError(f"Plugin {identifier!r}: {target.id} must be a tuple.")
                list_value = []
                for element in listing.elts:
                    if not isinstance(element, ast.Str):
                        raise TypeError(f"Plugin {identifier!r}: {target.id} must be a tuple"
                                        " and must only contain strings.")
                    list_value.append(element.s)
                info_dict[_id] = tuple(list_value)
            else:
                if not isinstance(statement.value, ast.Str):
                    raise TypeError(f"Plugin {identifier!r}: {target.id} can only be a string")
                str_value = statement.value.s
                info_dict[_id] = str_value

            if _id in required_ids:
                required_ids.remove(_id)

        if required_ids:
            # TODO: Use better exception.
            missing_str = ', '.join(f'__plugin_{i}__' for i in required_ids)
            raise RuntimeError(f"Missing {missing_str} in {str(path)!r}")

        return cls(**info_dict)  # type: ignore


class PluginModule:

    def __init__(self, module: ModuleType, identifier: str, namespace: str,
                 info: PluginModuleInfo
                 ) -> None:
        self.module = module
        self.identifier = identifier
        self.namespace = namespace
        self.info = info

        self.logger = get_logger(namespace, self.identifier)
        self.module_name = module.__name__

    def __repr__(self) -> str:
        return (f"<PluginModule {self.module_name}:"
                f" {self.info.name} {self.info.version} - {self.info.description}>")


class PluginManager:

    if sys.platform == 'win32':
        _home_config_path = pathlib.Path(os.path.expandvars(R"%APPDATA%\shanghai"))
    else:
        if 'XDG_CONFIG_HOME' in os.environ:
            _home_config_path = pathlib.Path(os.path.expandvars("$XDG_CONFIG_HOME/shanghai"))
        else:
            _home_config_path = pathlib.Path("~/.config/shanghai").expanduser()

    _shanghai_base_path = pathlib.Path(__file__).parent

    # From higher to lower priority
    PLUGIN_SEARCH_BASE_PATHS = [
        # current directory
        pathlib.Path(os.getcwd()),
        # user config base
        _home_config_path,
        # <SHANGHAI_PACKAGE_DIR>
        _shanghai_base_path,
    ]

    plugin_registry: Dict[str, PluginModule]

    def __init__(self, namespace: str, is_core: bool = False) -> None:
        # TODO add search base paths parameter
        if not namespace.isidentifier():
            raise ValueError("Invalid plugin namespace."
                             f" {namespace!r} contains invalid symbol(s).")
        if keyword.iskeyword(namespace):
            raise ValueError("Invalid plugin namespace."
                             f" {namespace!r} is a built-in keyword.")

        self.namespace = namespace
        if f'{__package__}.{namespace}' in sys.modules:
            raise RuntimeError(f"Expected '{__package__}.{namespace}' in `sys.modules` to be unset"
                               " but it was not")
        setattr(sys.modules[__package__], namespace, self)
        sys.modules[f'{__package__}.{namespace}'] = self

        if is_core:
            # just search in base path
            self.plugin_search_paths = [pathlib.Path(self._shanghai_base_path, namespace)]
        else:
            self.plugin_search_paths = [pathlib.Path(base_path, namespace)
                                        for base_path in self.PLUGIN_SEARCH_BASE_PATHS]

        self.plugin_registry = {}
        self.logger = get_default_logger()

    def __getattr__(self, item: str) -> ModuleType:
        if item in self.plugin_registry:
            return self.plugin_registry[item].module
        raise AttributeError(item)

    def load_all_plugins(self) -> None:
        plugins_to_load: Dict[str, pathlib.Path] = {}

        for search_path in self.plugin_search_paths:
            for module_path in search_path.glob("*.py"):
                identifier = module_path.stem
                plugins_to_load.setdefault(identifier, module_path)

        loaded_before = set(self.plugin_registry.keys())
        for identifier, module_path in plugins_to_load.items():
            if identifier in loaded_before:
                self.logger.warn(f"PluginModule {identifier!r} already exists")
                continue
            elif identifier in self.plugin_registry:
                continue  # loaded as a dependency
            try:
                plugin = self._load_plugin_as_module(module_path, identifier)
            except Exception as e:
                self.logger.exception(f"Unable to load plugin {identifier!r}: {e!s}")
            self._register_plugin(plugin)

    def load_plugin(self, identifier: str, *,
                    dependency_path: Iterable[str] = (),
                    is_core: bool = False,
                    ) -> PluginModule:
        if not identifier.isidentifier():
            raise ValueError(f"Invalid plugin name. {identifier!r} contains invalid symbol(s).")
        if keyword.iskeyword(identifier):
            raise ValueError(f"Invalid plugin name. {identifier!r} is a built-in keyword.")

        if identifier in self.plugin_registry:
            if not dependency_path:
                self.logger.warn(f"PluginModule {identifier!r} already exists")
            return self.plugin_registry[identifier]

        for search_path in self.plugin_search_paths:
            try:
                module_path = self._find_module_path(search_path, identifier)
            except OSError:
                continue
            else:
                break
        else:
            raise FileNotFoundError(
                f"Could not find plugin {identifier!r} in any of the search paths:"
                "\n  " + "".join(f'\n  {path!s}' for path in self.plugin_search_paths)
            )

        plugin = self._load_plugin_as_module(module_path, identifier,
                                             dependency_path=dependency_path)
        self._register_plugin(plugin)
        return plugin

    def _register_plugin(self, plugin: PluginModule) -> None:
        self.plugin_registry[plugin.identifier] = plugin
        sys.modules[plugin.module_name] = plugin.module
        self.logger.debug(f"Setting sys.modules[{plugin.module_name!r}] to {plugin.module}")

    @staticmethod
    def _find_module_path(search_path: pathlib.Path, identifier: str) -> pathlib.Path:
        path = pathlib.Path(search_path, identifier)
        module_path = path.with_suffix(".py")
        if not module_path.exists():
            raise FileNotFoundError(f"No such file {str(module_path)!r}")
        if module_path.is_file():
            return module_path
        raise OSError(f"Error trying to load {str(path)!r}")

    def _load_plugin_as_module(self, path: pathlib.Path, identifier: str, *,
                               dependency_path: Iterable[str] = (),
                               ) -> PluginModule:
        info = PluginModuleInfo.read_from_file(path, identifier)

        # TODO info.conflicts
        for dependency in info.depends:
            new_dependency_path = (*dependency_path, identifier)
            if dependency in dependency_path:
                raise CyclicDependency(
                    f"Cyclic dependency detected: {' -> '.join(new_dependency_path)}"
                )
            self.load_plugin(dependency, dependency_path=new_dependency_path)

        if dependency_path:
            self.logger.info(f"Loading plugin {identifier!r} as dependency of {dependency_path!r}")
        else:
            self.logger.info(f"Loading plugin {identifier!r}")

        module_name = f'{__package__}.{self.namespace}.{identifier}'
        spec = importlib.util.spec_from_file_location(module_name, str(path))

        module = importlib.util.module_from_spec(spec)
        if spec.loader is None:
            raise ImportError("No loader for module available")
        spec.loader.exec_module(module)
        self.logger.debug("Found plugin in", module.__file__)

        plugin = PluginModule(module, identifier, self.namespace, info)
        self.logger.info("Loaded plugin", plugin)
        return plugin

    def discover_plugins(self, plugin_class: TType) -> Generator[TType, None, None]:
        for plugin_mod in self.plugin_registry.values():
            self.logger.debug(f"scanning for plugins in {plugin_mod}")
            for name, value in plugin_mod.module.__dict__.items():
                if name.startswith("_"):
                    continue
                if (
                    isinstance(value, type)
                    and issubclass(value, plugin_class)
                    and value is not plugin_class
                ):
                    self.logger.info(f"found plugin: {value}")
                    yield value
