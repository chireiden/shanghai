
import ast
from collections import OrderedDict
import importlib.util
import os
import sys

from .logging import current_logger


class Plugin:

    def __init__(self, info, module):
        self.info = info
        self.module = module

    def initialize(self):
        func_ref = getattr(self.module, 'initialize', None)
        if func_ref is None:
            current_logger.debug('No Initialization for plugin', self)
            return
        if not callable(func_ref):
            current_logger.warn("'Initialize' is not callable in {!r}"
                                .format(self.info['identifier']))
        current_logger.debug('Initialize plugin', self)
        func_ref(self)

    def __repr__(self):
        return '<Plugin {identifier}: {name} v{version} - {description}>'.format(**self.info)


class PluginSystem:
    if sys.platform == 'win32':
        # %APPDATA%/shanghai/plugins
        _home_config_path = os.path.expandvars(R"%APPDATA%\shanghai\plugins")
    else:
        # ~/.config/shanghai/plugins
        _home_config_path = os.path.expanduser("~/.config/shanghai/plugins")

    # TODO: add configuration location
    PLUGIN_SEARCH_PATHS = [
        # ./plugins/
        # TODO might be redundant
        os.path.join(os.getcwd(), 'plugins'),
        _home_config_path,
        # <SHANGHAI_PACKAGE_DIR>/plugins/
        os.path.join(os.path.dirname(__file__), 'plugins'),
    ]

    plugin_registry = {}
    plugin_factory = Plugin

    @classmethod
    def load_plugin(cls, identifier):
        current_logger.info('Loading plugin', identifier)
        if identifier in cls.plugin_registry:
            current_logger.warn('Plugin', identifier, 'already exists.')
            return cls.plugin_registry[identifier]
        for search_path in cls.PLUGIN_SEARCH_PATHS:
            try:
                plugin = cls.load_from_path(search_path, identifier)
            except OSError:
                pass
            else:
                break
        else:  # I always wanted to use this at least once
            raise FileNotFoundError('Could not find plugin {!r} in any of the search paths:\n{}'
                                    .format(identifier, '\n'.join(cls.PLUGIN_SEARCH_PATHS)))

        # add to registry
        cls.plugin_registry[identifier] = plugin
        plugin.initialize()
        return plugin

    @classmethod
    def load_from_path(cls, search_path, identifier):
        path = os.path.join(search_path, identifier)
        module_path = path + '.py'
        if not os.path.exists(module_path):
            raise FileNotFoundError('No such file {!r}'.format(module_path))
        if os.path.isfile(module_path):
            return cls._load_plugin_as_module(module_path, identifier)
        raise OSError('Error trying to load {!r}'.format(path))

    @classmethod
    def _load_plugin_as_module(cls, path, identifier):
        # TODO: load dependencies first!
        info = cls._get_plugin_info(path, identifier)
        # info['depends'] and info['conflicts']

        spec = importlib.util.spec_from_file_location(identifier, path)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        current_logger.info('Found plugin in', module.__file__)

        plugin = cls.plugin_factory(info, module)
        current_logger.info(plugin)
        return plugin

    @staticmethod
    def _get_plugin_info(filename, identifier):
        with open(filename, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename)

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
            if not isinstance(statement.value, ast.Str):
                continue
            if not target.id.startswith('__plugin_') or not target.id.endswith('__'):
                continue

            _id = target.id.strip('_')[7:]
            if _id in ignore_ids:
                continue
            if _id not in info:
                continue

            required_ids.remove(_id)  # might throw error if __plugin_name__ etc. occures twice
            info[_id] = statement.value.s

        if required_ids:
            # TODO: Use better exception.
            raise RuntimeError('Missing {} in {}'.format(
                ', '.join('__plugin_{}__'.format(i) for i in required_ids), filename))

        return info
