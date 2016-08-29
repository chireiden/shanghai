
from datetime import datetime
import functools
import hashlib
import io
import logging
import os

import pytz

from .local import LocalStack, LocalProxy


_LOGGING_CONFIG = {}


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


class Formatter(logging.Formatter):

    def __init__(self, context, name, tz):
        super().__init__()
        self._context = context
        self._name = name
        self._tz = tz

    def format(self, record: logging.LogRecord):
        now = datetime.now(tz=self._tz)
        data = dict(
            context=self._context,
            name=self._name,
            message=record.getMessage(),
            level=record.levelname,
            date=now,
        )
        s = '{context}/{name} - {level} [{date:%Y-%m-%d %H:%M:%S %z}]' \
            ' {message}'.format(**data)
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
        self.logger = None

    def __enter__(self):
        self.push()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pop()

    def push(self):
        if self.logger is None:
            self.logger = self._get_logger(
                self.context, self.name, self.config)
        _logging_ctx_stack.push(self)

    def pop(self):
        _logging_ctx_stack.pop()

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

        tzname = os.environ.get('TZ', None)

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

        file_handler = FileHandler(
            'logs/{context}-{name}-{date:%Y-%m}.log'.format(**name_attributes))
        stream_handler = logging.StreamHandler()

        formatter = Formatter(context, name, tz=timezone)

        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        level = config.get('logging', {}).get('level', 'INFO')
        logger.setLevel(level)

        logger.info('*'*50)
        logger.info('Opened log.'.format(date=now))

        return logger


def _get_current_logger():
    top = _logging_ctx_stack.top
    if top is None:
        raise RuntimeError("Working outside logging context")
    return top.logger


_logging_ctx_stack = LocalStack()
current_logger = LocalProxy(_get_current_logger)  # type: Logger
