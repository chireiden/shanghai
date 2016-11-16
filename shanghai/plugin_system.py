
import ast
from collections import OrderedDict, defaultdict
import importlib.util
import os

from .logging import current_logger


class Plugin:

    def __init__(self, info, module_or_package):
        self.info = info
        self.module_or_package = module_or_package

        self.registered_events = defaultdict(list)

    def register_event(self, event, func_ref, data=None, priority=0):
        current_logger.debug(
            'Registering event', repr(event), 'to', self,
            'with data', repr(data), 'and priority', priority)
        # TODO: Implement.
        raise NotImplementedError

    def initialize(self):
        func_ref = getattr(self.module_or_package, 'initialize', None)
        if func_ref is None:
            current_logger.debug('No Initialization for plugin', self)
            return
        if not callable(func_ref):
            current_logger.warn("'Initialize' is not callable in {!r}"
                                .format(self.info['identifier']))
        current_logger.debug('Initialize plugin', self)
        func_ref(self)

    def _get_event_funcs(self, event):
        if event in self.registered_events:
            for func_ref in self.registered_events[event]:
                if not callable(func_ref):
                    current_logger.error('Registered function for event {} in plugin {} is not'
                                         ' callable'.format(event, self.info['identifier']))
                    continue
                yield func_ref

    async def dispatch(self, event, *args, **kwargs):
        results = []
        for func_ref in self._get_event_funcs(event):
            results.append(await func_ref(self, *args, **kwargs))
        return results

    def sync_dispatch(self, event, *args, **kwargs):
        """Will this even be necessary? Should we enforce the async always?"""
        results = []
        for func_ref in self._get_event_funcs(event):
            results.append(func_ref(self, *args, **kwargs))
        return results

    def __repr__(self):
        return '<Plugin {identifier}: {name} v{version} - {description}>'.format(**self.info)


class PluginSystem:

    PLUGIN_SEARCH_PATHS = [
        # ./plugins/
        os.path.join(os.getcwd(), 'plugins'),

        # ~/.config/shanghai/plugins/
        os.path.join(os.environ['HOME'], '.config', 'shanghai', 'plugins'),

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
        plugin = None
        for search_path in cls.PLUGIN_SEARCH_PATHS:
            try:
                plugin = cls.load_from_path(search_path, identifier)
            except OSError:
                pass
            else:
                break
        if plugin is None:
            raise FileNotFoundError('Could not find plugin {!r} in any of the search paths:\n{}'
                                    .format(identifier, '\n'.join(cls.PLUGIN_SEARCH_PATHS)))

        # add to registry
        cls.plugin_registry[identifier] = plugin
        plugin.initialize()
        return plugin

    @classmethod
    def load_from_path(cls, search_path, identifier):
        path = os.path.join(search_path, identifier)
        package_path = os.path.join(path, '__init__.py')
        module_path = path + '.py'
        if not os.path.exists(package_path) \
                and not os.path.exists(module_path):
            raise FileNotFoundError('No such file {!r} or {!r}'
                                    .format(package_path, module_path))
        if os.path.isfile(package_path):
            return cls._load_plugin_as_module_or_package(package_path, identifier, package=True)
        if os.path.isfile(module_path):
            return cls._load_plugin_as_module_or_package(module_path, identifier)
        raise OSError('Error trying to load {!r}'.format(path))

    @classmethod
    def _load_plugin_as_module_or_package(cls, path, identifier, package=False):
        # TODO: load dependencies first!
        info = cls._get_plugin_info(path, identifier)
        # info['depends'] and info['conflicts']

        if package:
            spec = importlib.util.spec_from_file_location(
                identifier, path, submodule_search_locations=[])
        else:
            spec = importlib.util.spec_from_file_location(identifier, path)

        module_or_package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module_or_package)
        current_logger.info('Found plugin in', module_or_package.__file__)

        plugin = cls.plugin_factory(info, module_or_package)
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
        # is it reasonable to simply use __name__ and __version__ etc.?
        target_ids = ['__plugin_{}__'.format(_id) for _id in info]
        required_ids = {'name', 'version', 'description'}

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
            if target.id not in target_ids:
                continue
            _id = target.id[9:-2]
            required_ids.remove(_id)  # might throw error if __name__ etc. occures twice
            info[_id] = statement.value.s

        if required_ids:
            # TODO: Use better exception.
            raise RuntimeError('Missing {} in {}'.format(
                ', '.join('__plugin_{}__'.format(i) for i in required_ids), filename))

        return info

    @classmethod
    def dispatch_to_plugins(cls, event, *args, **kwargs):
        pass
