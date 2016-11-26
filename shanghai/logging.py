
from datetime import datetime
from enum import Enum
import functools
import hashlib
import io
import logging
import os

import colorama
import pytz

from .config import Configuration

_default_logger = None


class LogLevels(int, Enum):
    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG
    DDEBUG = 5
    NOTSET = logging.NOTSET

logging.addLevelName(LogLevels.DDEBUG, "DDEBUG")


def _print_like(func):
    @functools.wraps(func)
    def _wrap(self, *args, **kwargs):
        f = io.StringIO()
        print(*args, file=f)
        return func(self, f.getvalue().strip(), **kwargs)
    return _wrap


class Logger(logging.Logger):
    """Wrap _print_link around so we can use logger.info etc. similar to the
    print function. e.g. logging.info('foo', 'bar', 'baz')"""
    debug = _print_like(logging.Logger.debug)
    info = _print_like(logging.Logger.info)
    warn = _print_like(logging.Logger.warn)
    warning = _print_like(logging.Logger.warning)
    error = _print_like(logging.Logger.error)
    exception = _print_like(logging.Logger.exception)
    critical = _print_like(logging.Logger.critical)

    def ddebug(self, *args, **kwargs):
        f = io.StringIO()
        print(*args, file=f)
        self.log(LogLevels.DDEBUG, f.getvalue().strip(), **kwargs)


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
        for log_level in sorted(LogLevels, reverse=True):
            if level >= log_level.value:
                return getattr(cls, log_level.name, "")
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


def set_default_logger(logger: Logger):
    global _default_logger
    _default_logger = logger


def get_default_logger():
    global _default_logger
    return _default_logger


def get_logger(context, name, config=None, open_msg=False):
    """
    context: i.e. 'network', 'channel', 'core', whatvever.
    name: some preferably unique name inside of context
          e.g. 'freenode' in context 'network'
    """
    if config is None:
        config = Configuration()

    logging.setLoggerClass(Logger)
    # use a hashed version to avoid it containing dots.
    hashed_name = hashlib.sha256(name.lower().encode('utf-8')).hexdigest()[:12]
    logger = logging.getLogger('{}.{}'.format(context.lower(), hashed_name))

    # TODO cache timezone
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
    name_attributes = dict(context=context, name=name, date=now)

    level = config.get('logging.level', 'INFO')
    logger.setLevel(LogLevels[level])

    if not config.get('logging.disable', False):
        file_formatter = Formatter(context, name, tz=timezone)
        # TODO use rotating file handler
        file_handler = FileHandler(
            'logs/{context}-{name}-{date:%Y-%m}.log'
            .format(**name_attributes))
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        if open_msg:
            # Realistically, we don't need this in a terminal
            logger.info('*' * 50)
            logger.info('Opened log.')

    if not config.get('logging.disable_stdout', False):
        terminal_formatter = Formatter(context, name, tz=timezone, terminal=True)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(terminal_formatter)
        logger.addHandler(stream_handler)

    return logger

# Disable logging for the 'default' default logger
_default_logger = get_logger('logging', 'default',
                             Configuration({'logging': {'disable': True}}))
