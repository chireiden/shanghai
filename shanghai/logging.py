
from datetime import datetime
from enum import Enum
import functools
import hashlib
import io
import logging
import os
import typing as t

import colorama
import pytz

from .local import LocalStack, LocalProxy


_LOGGING_CONFIG = {}  # type: t.Dict[str, t.Any]


def set_logging_config(config):
    global _LOGGING_CONFIG
    _LOGGING_CONFIG = config


def _print_like(func):
    @functools.wraps(func)
    def _wrap(self, *args):
        f = io.StringIO()
        print(*args, file=f)
        return func(self, f.getvalue().strip())
    return _wrap


class Logger(logging.Logger):
    """Wrap _print_link around so we can use logger.info etc. similar to the
    print function. e.g. logging.info('foo', 'bar', 'baz')"""
    info = _print_like(logging.Logger.info)
    debug = _print_like(logging.Logger.debug)
    warn = _print_like(logging.Logger.warn)
    warning = _print_like(logging.Logger.warning)
    error = _print_like(logging.Logger.error)
    exception = _print_like(logging.Logger.exception)


class FileHandler(logging.FileHandler):

    def __init__(self, filename):
        filename = os.path.abspath(filename)
        basedir = os.path.dirname(filename)
        os.makedirs(basedir, 0o755, exist_ok=True)
        super().__init__(filename, 'a', 'utf-8', None)


class TerminalColor(str, Enum):

    DEBUG = colorama.Fore.CYAN
    INFO = colorama.Fore.GREEN
    WARNING = colorama.Fore.YELLOW + colorama.Style.BRIGHT
    ERROR = colorama.Fore.RED + colorama.Style.BRIGHT
    CRITICAL = colorama.Fore.RED + colorama.Style.BRIGHT + colorama.Back.YELLOW

    @classmethod
    def for_level(cls, level):
        names = ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG')
        for name in names:
            if level >= getattr(logging, name):
                return getattr(cls, name)
        return ""


class Formatter(logging.Formatter):

    def __init__(self, context, name, tz, terminal=False):
        super().__init__()
        self._context = context
        self._name = name
        self._tz = tz
        self._terminal = terminal

    _max_logging_level_length = len("CRITICAL")

    def format(self, record: logging.LogRecord):
        now = datetime.now(tz=self._tz)
        data = dict(
            context=self._context,
            name=self._name,
            message=record.getMessage(),
            level=record.levelname,
            date=now,
            color_start="",
            color_end="",
        )
        if self._terminal:
            data['color_start'] = TerminalColor.for_level(record.levelno)
            if data['color_start']:
                data['color_end'] = colorama.Style.RESET_ALL

        s = (
            "{context}/{name}"
            " [{date:%Y-%m-%d %H:%M:%S %z}]"
            " {color_start}| "
            "{level:{level_name_length}}"
            " | {message}"
            "{color_end}"
        ).format(level_name_length=self._max_logging_level_length, **data)
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if s[-1:] != "\n":
                s += "\n"
            s = s + record.exc_text
        if record.stack_info:
            if s[-1:] != "\n":
                s += "\n"
            s = s + self.formatStack(record.stack_info)
        return s


class LogContext:

    def __init__(self, context, name, config=None):
        self.context = context
        self.name = name
        self.config = _LOGGING_CONFIG if config is None else config
        self.logger = self._get_logger(self.context, self.name, self.config)

    def __enter__(self):
        self.push()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pop()

    def push(self):
        _logging_ctx_stack.push(self)

    def pop(self):
        if _logging_ctx_stack.top is self:
            _logging_ctx_stack.pop()
        else:
            raise RuntimeError("Unexpected stack element; "
                               "stack top is not self")

    @staticmethod
    def _get_logger(context, name, config):
        """
        context: i.e. 'network', 'channel', 'core', whatvever.
        name: some preferably unique name inside of context
              e.g. 'freenode' in context 'network'
        """
        logging.setLoggerClass(Logger)
        # use a hashed version to avoid it containing dots.
        hashed_name = hashlib.sha256(
            name.lower().encode('utf-8')).hexdigest()[:12]
        logger = logging.getLogger(
            '{}.{}'.format(context.lower(), hashed_name))

        # TODO cache timezone
        tzname = os.environ.get('TZ', None)

        config = {**_LOGGING_CONFIG, **config}

        if tzname is None:
            tzname = config.get('timezone', None)

        if tzname is None:
            tzfile = '/etc/timezone'
            if os.path.exists(tzfile) and os.path.isfile(tzfile):
                with open(tzfile, 'r') as f:
                    tzname = f.read().strip()

        if tzname is None:
            tzname = 'UTC'

        timezone = pytz.timezone(tzname)
        now = datetime.now(tz=timezone)
        name_attributes = dict(
            context=context,
            name=name,
            date=now
        )

        disable_logging = config.get('disable-logging', False)
        disable_logging_output = config.get('disable-logging-output', False)

        if not disable_logging:
            file_formatter = Formatter(context, name, tz=timezone)
            # TODO use rotating file handler
            file_handler = FileHandler(
                'logs/{context}-{name}-{date:%Y-%m}.log'
                .format(**name_attributes))
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        if not disable_logging_output:
            terminal_formatter = Formatter(context, name, tz=timezone,
                                           terminal=True)
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(terminal_formatter)
            logger.addHandler(stream_handler)

        level = config.get('logging', {}).get('level', 'INFO')
        logger.setLevel(level)

        logger.info('*' * 50)
        logger.info('Opened log.')

        return logger


def with_log_context(log_context_factory):

    def real_deco(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            log_context = log_context_factory(*args, **kwargs)
            with log_context:
                return await func(*args, **kwargs)

        return wrapper

    return real_deco


def _get_current_logger():
    top = _logging_ctx_stack.top
    if top is None:
        raise RuntimeError("Working outside logging context")
    return top.logger


_logging_ctx_stack = LocalStack()
current_logger = t.cast(Logger, LocalProxy(_get_current_logger))
