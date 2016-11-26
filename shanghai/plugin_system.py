
import ast
from collections import OrderedDict
import importlib.util
import pathlib
import os
import sys
import keyword

from .logging import get_logger, get_default_logger


class CyclicDependency(Exception):
    pass


class Plugin:

    def __init__(self, info, module, namespace):
        self.logger = get_logger('plugin', info['identifier'])
        self.info = info
        self.module = module
        self.module_name = 'shanghai.{}.{}'.format(namespace, info['identifier'])

    def __repr__(self):
        return '<Plugin {module_name}: {name} {version} - {description}>'.format(
            module_name=self.module_name, **self.info)


class PluginSystem:
    if sys.platform == 'win32':
        # %APPDATA%/shanghai/plugins
        _home_config_path = pathlib.Path(os.path.expandvars(R"%APPDATA%\shanghai"))
    else:
        # ~/.config/shanghai/plugins
        _home_config_path = pathlib.Path("~/.config/shanghai").expanduser()

    _core_plugin_base_path = pathlib.Path(__file__).parent

    # TODO: add configuration location
    PLUGIN_SEARCH_BASE_PATHS = [
        # current directory
        # TODO might be redundant
        pathlib.Path(os.getcwd()),
        _home_config_path,
        # <SHANGHAI_PACKAGE_DIR>
        _core_plugin_base_path,
    ]

    plugin_factory = Plugin

    def __init__(self, namespace, is_core=False):
        if not namespace.isidentifier():
            raise ValueError(
                'Invalid plugin namespace. {!r} contains invalid symbol(s).'.format(namespace))
        if keyword.iskeyword(namespace):
            raise ValueError(
                'Invalid plugin namespace. {!r} is a built in keyword.'.format(namespace))

        self.namespace = namespace
        sys.modules['shanghai'].plugins = self
        sys.modules['shanghai.{}'.format(namespace)] = self

        if is_core:
            # just search in one single path
            self.plugin_search_paths = [str(pathlib.Path(self._core_plugin_base_path, namespace))]
        else:
            self.plugin_search_paths = []
            for base_path in self.PLUGIN_SEARCH_BASE_PATHS:
                self.plugin_search_paths.append(str(pathlib.Path(base_path, namespace)))

        self.plugin_registry = {}
        self.logger = get_default_logger()

    def __getattr__(self, item):
        if item in self.plugin_registry:
            return self.plugin_registry[item].module
        raise AttributeError(item)

    def load_plugin(self, identifier, *, dependency_path=None, is_core=False):
        if not identifier.isidentifier():
            raise ValueError(
                'Invalid plugin name. {!r} contains invalid symbol(s).'.format(identifier))
        if keyword.iskeyword(identifier):
            raise ValueError(
                'Invalid plugin name. {!r} is a built in keyword.'.format(identifier))

        if dependency_path is None:
            dependency_path = []
        if identifier in self.plugin_registry:
            if not dependency_path:
                self.logger.warn('Plugin', identifier, 'already exists.')
            return self.plugin_registry[identifier]
        for search_path in self.plugin_search_paths:
            try:
                module_path = self._find_module_path(search_path, identifier)
            except OSError:
                pass
            else:
                plugin = self._load_plugin_as_module(module_path, identifier,
                                                     dependency_path=dependency_path)
                break
        else:  # I always wanted to use this at least once
            raise FileNotFoundError('Could not find plugin {!r} in any of the search paths:\n{}'
                                    .format(identifier, '\n'.join(self.plugin_search_paths)))

        # add to registry
        self.plugin_registry[identifier] = plugin
        module_name = 'shanghai.{}.{}'.format(self.namespace, identifier)
        sys.modules[module_name] = plugin.module
        self.logger.debug("Setting sys.modules[{!r}] to {}".format(module_name, plugin.module))
        return plugin

    @classmethod
    def _find_module_path(cls, search_path: pathlib.Path, identifier) -> pathlib.Path:
        path = pathlib.Path(search_path, identifier)
        module_path = path.with_suffix('.py')
        if not module_path.exists():
            raise FileNotFoundError('No such file {!r}'.format(str(module_path)))
        if module_path.is_file():
            return module_path
        raise OSError('Error trying to load {!r}'.format(str(path)))

    def _load_plugin_as_module(self, path: pathlib.Path, identifier, *, dependency_path):
        info = self._get_plugin_info(path, identifier)
        # TODO info['conflicts']
        for dependency in info['depends']:
            if dependency in dependency_path:
                raise CyclicDependency('Cyclic dependency detected: {}'
                                       .format(' -> '.join([identifier] + dependency_path)))
            self.load_plugin(dependency, dependency_path=dependency_path + [identifier])

        if dependency_path:
            self.logger.info('Loading plugin', identifier,
                             'as dependency of', dependency_path)
        else:
            self.logger.info('Loading plugin', identifier)
        spec = importlib.util.spec_from_file_location(identifier, str(path))

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.logger.info('Found plugin in', module.__file__)

        plugin = self.plugin_factory(info, module, self.namespace)
        self.logger.info("Loaded plugin", plugin)
        return plugin

    @staticmethod
    def _get_plugin_info(path: pathlib.Path, identifier):
        with path.open('r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), str(path))

        info = OrderedDict([
            ('identifier', identifier),
            ('name', None),
            ('version', None),
            ('description', None),
            ('depends', []),
            ('conflicts', []),
        ])
        required_ids = {'name', 'version', 'description'}
        ignore_ids = {'identifier'}

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
            _id = target.id.strip('_')[7:]

            if _id in ('depends', 'conflicts'):
                listing = statement.value
                if not isinstance(listing, (ast.List, ast.Tuple)):
                    raise TypeError('Plugin {}: {} must be a list or a tuple.'
                                    .format(identifier, target.id))
                value = []
                for element in listing.elts:
                    if not isinstance(element, ast.Str):
                        raise TypeError('Plugin {}: {} must be a list/tuple and must only'
                                        ' contain strings.'.format(identifier, target.id))
                    value.append(element.s)
            else:
                if not isinstance(statement.value, ast.Str):
                    raise TypeError('Plugin {}: {} can only be a string.'
                                    .format(identifier, target.id))
                value = statement.value.s

            if _id in ignore_ids:
                continue
            if _id not in info:
                continue

            if _id in required_ids:
                required_ids.remove(_id)
            info[_id] = value

        if required_ids:
            # TODO: Use better exception.
            raise RuntimeError('Missing {} in {}'.format(
                ', '.join('__plugin_{}__'.format(i) for i in required_ids), str(path)))

        return info
