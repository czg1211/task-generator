import atexit
import os
import signal
import sys
import inspect
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from functools import wraps
from contextvars import ContextVar

from loguru import logger

# 上下文变量，用于存储请求ID、插件名等上下文信息
# request_id_var = ContextVar("request_id", default=None)
plugin_name_var = ContextVar("plugin_name", default=None)
module_name_var = ContextVar("module_name", default=None)


class BaseLogger:
    """
    统一的日志工具
    - 非插件日志：保存到公共日志文件
    - 插件日志：每个插件有独立的日志文件
    - 支持控制台输出和文件输出
    """

    _instance = None
    _initialized = False
    _plugin_loggers = {}  # 插件日志器缓存
    _handlers = []  # 存储处理器ID

    def __new__(cls, config: Optional[Dict[str, Any]] = None):
        if cls._instance is None:
            cls._instance = super(BaseLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        # 防止重复初始化
        if self._initialized:
            return

        self.config = config or self._get_default_config()
        self._setup_logging()
        self._initialized = True

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'log_dir': os.getenv('LOG_DIR', 'logs'),
            'public_log_file': 'application.log',
            'console_format': self._get_console_format(),
            'file_format': self._get_file_format(),
            'rotation': os.getenv('LOG_ROTATION', '10 MB'),
            'retention': os.getenv('LOG_RETENTION', '30 days'),
            'compression': os.getenv('LOG_COMPRESSION', 'zip'),
            'backtrace': True,
            'diagnose': True,
            'enqueue': False,
            'mode': 'a',  # 追加模式
            'buffer_size': 1,  # 缓冲区大小（行）
        }

    def _get_console_format(self) -> str:
        """获取控制台日志格式 - 增强版"""
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            # "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        )

    def _get_file_format(self) -> str:
        """获取文件日志格式"""
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            # "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

    def _setup_logging(self):
        """设置日志系统"""
        # 移除所有现有的处理器
        logger.remove()

        # 确保日志目录存在
        log_dir = Path(self.config['log_dir'])
        log_dir.mkdir(exist_ok=True, parents=True)

        # 添加控制台输出（公共日志）
        logger.add(
            sys.stderr,
            level=self.config['level'],
            format=self.config['console_format'],
            colorize=True,
            backtrace=self.config['backtrace'],
            diagnose=self.config['diagnose'],
            enqueue=self.config['enqueue'],
            filter=self._public_log_filter,
            catch=True,  # 捕获异常

        )

        # 添加公共日志文件
        public_log_path = log_dir / self.config['public_log_file']
        public_log_path.parent.mkdir(exist_ok=True, parents=True)
        if not public_log_path.exists():
            public_log_path.touch()
        logger.add(
            str(public_log_path),
            level=self.config['level'],
            format=self.config['file_format'],
            rotation=self.config['rotation'],
            retention=self.config['retention'],
            compression=self.config['compression'],
            backtrace=self.config['backtrace'],
            diagnose=self.config['diagnose'],
            enqueue=self.config['enqueue'],
            filter=self._public_log_filter,
            catch=True,
        )

        # 立即写入初始日志
        # self._write_initial_log()
        logger.info("日志系统初始化完成")


    def _public_log_filter(self, record) -> bool:
        """公共日志过滤器 - 只记录非插件日志"""
        # 如果记录有插件名，则不是公共日志
        plugin_name = record["extra"].get("plugin")
        return plugin_name is None


    def _plugin_log_filter(self, plugin_name: str):
        """插件日志过滤器工厂"""

        def filter_func(record):
            return record["extra"].get("plugin") == plugin_name

        return filter_func

    def get_plugin_logger(self, plugin_name: str) -> 'PluginLogger':
        """获取插件专用的日志器"""
        if plugin_name not in self._plugin_loggers:
            self._plugin_loggers[plugin_name] = PluginLogger(plugin_name, self)
        return self._plugin_loggers[plugin_name]

    def get_public_logger(self) -> 'PublicLogger':
        """获取公共日志器"""
        return PublicLogger(self)

    # 基本日志方法（公共日志）
    def debug(self, message: str, **kwargs):
        """调试日志（公共）"""
        self._log_with_context("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs):
        """信息日志（公共）"""
        self._log_with_context("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        """警告日志（公共）"""
        self._log_with_context("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        """错误日志（公共）"""
        self._log_with_context("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs):
        """严重错误日志（公共）"""
        self._log_with_context("CRITICAL", message, **kwargs)

    def exception(self, message: str, exc: Exception, **kwargs):
        """异常日志（公共）"""
        logger.opt(exception=exc).error(message, **kwargs)
        self._immediate_flush()

    def _log_with_context(self, level: str, message: str, **kwargs):
        """带上下文的日志记录"""
        extra = {}

        # 添加上下文信息
        # request_id = request_id_var.get()
        # if request_id:
        #     extra['request_id'] = request_id

        plugin_name = plugin_name_var.get()
        if plugin_name:
            extra['plugin'] = plugin_name

        module_name = module_name_var.get()
        if module_name:
            extra['module'] = module_name

        # 记录日志
        self.log(level, message, **{**extra, **kwargs})

    def log(self, level: str, message: str, **kwargs):
        """通用日志方法"""
        level = level.upper()
        if hasattr(logger, level.lower()):
            getattr(logger, level.lower())(message, **kwargs)
        else:
            logger.info(message, **kwargs)

        # 立即刷新日志缓冲区
        self._immediate_flush()

    def _immediate_flush(self):
        """立即刷新日志"""
        try:
            # 对于关键日志，我们可以强制刷新
            if self.config.get('level') in ['DEBUG', 'INFO']:
                # 记录一条空消息并刷新
                logger.debug("", flush=True)
        except:
            pass

    # 上下文管理器
    def context(self,
                # request_id: Optional[str] = None,
                plugin_name: Optional[str] = None,
                module_name: Optional[str] = None):
        """创建日志上下文"""
        return LoggingContext(self, plugin_name, module_name)

    # 装饰器
    def log_function_call(self, level: str = "INFO", with_args: bool = True):
        """记录函数调用的装饰器"""

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                func_name = func.__name__
                module_name = func.__module__

                # 记录函数调用
                if with_args:
                    args_str = ", ".join([repr(arg) for arg in args])
                    kwargs_str = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
                    all_args = ", ".join(filter(None, [args_str, kwargs_str]))
                    self.log(level, f"调用函数: {module_name}.{func_name}({all_args})")
                else:
                    self.log(level, f"调用函数: {module_name}.{func_name}()")

                # 执行函数
                start_time = datetime.now()
                try:
                    result = func(*args, **kwargs)
                    execution_time = (datetime.now() - start_time).total_seconds()

                    # 记录函数结果
                    self.log(level, f"函数完成: {module_name}.{func_name}(), 耗时: {execution_time:.3f}s")
                    return result

                except Exception as e:
                    execution_time = (datetime.now() - start_time).total_seconds()
                    self.error(f"函数异常: {module_name}.{func_name}(), 耗时: {execution_time:.3f}s, 错误: {str(e)}")
                    raise

            return wrapper

        return decorator


class PluginLogger:
    """插件专用的日志器"""

    def __init__(self, plugin_name: str, unified_logger: BaseLogger):
        self.plugin_name = plugin_name
        self.unified_logger = unified_logger
        self.logger = logger.bind(plugin=plugin_name)

        # 设置插件专用的日志文件
        self._setup_plugin_logging()



    def _setup_plugin_logging(self):
        """设置插件专用的日志文件"""
        log_dir = Path(self.unified_logger.config['log_dir'])
        plugin_log_dir = log_dir / "plugins" / self.plugin_name
        plugin_log_dir.mkdir(exist_ok=True, parents=True)

        # 插件日志文件名包含时间戳，便于区分不同运行实例
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{self.plugin_name}_{timestamp}.log"
        plugin_log_path = plugin_log_dir / log_filename

        plugin_log_path.parent.mkdir(exist_ok=True, parents=True)
        plugin_log_path.touch(exist_ok=True)

        # 添加插件专用的文件处理器
        handler_id = logger.add(
            str(plugin_log_path),
            level=self.unified_logger.config['level'],
            format=self.unified_logger.config['file_format'],
            rotation=self.unified_logger.config['rotation'],
            retention=self.unified_logger.config['retention'],
            compression=self.unified_logger.config['compression'],
            backtrace=self.unified_logger.config['backtrace'],
            diagnose=self.unified_logger.config['diagnose'],
            enqueue=self.unified_logger.config['enqueue'],
            mode=self.unified_logger.config['mode'],
            catch=True,
            filter=self.unified_logger._plugin_log_filter(self.plugin_name),

        )
        self.unified_logger._handlers.append(handler_id)
        self.log_file = plugin_log_path

        # 立即写入插件启动日志
        # self.info(f"插件日志器初始化完成: {self.plugin_name}")
        self._immediate_flush()

    def _immediate_flush(self):
        """立即刷新日志"""
        try:
            self.logger.debug("", flush=True)
        except:
            pass

    # 插件专用的日志方法
    def debug(self, message: str, **kwargs):
        """调试日志（插件专用）"""
        self._log_with_context("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs):
        """信息日志（插件专用）"""
        self._log_with_context("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        """警告日志（插件专用）"""
        self._log_with_context("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        """错误日志（插件专用）"""
        self._log_with_context("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs):
        """严重错误日志（插件专用）"""
        self._log_with_context("CRITICAL", message, **kwargs)

    def exception(self, message: str, exc: Exception, **kwargs):
        """异常日志（插件专用）"""
        self.logger.opt(exception=exc).error(message, **kwargs)
        self._immediate_flush()

    def _log_with_context(self, level: str, message: str, **kwargs):
        """带上下文的日志记录"""
        extra = {'plugin': self.plugin_name}

        # 添加上下文信息
        # request_id = request_id_var.get()
        # if request_id:
        #     extra['request_id'] = request_id

        module_name = module_name_var.get()
        if module_name:
            extra['module'] = module_name

        # 记录日志
        self.log(level, message, **{**extra, **kwargs})

    def log(self, level: str, message: str, **kwargs):
        """通用日志方法"""
        level = level.upper()
        if hasattr(self.logger, level.lower()):
            getattr(self.logger, level.lower())(message, **kwargs)
        else:
            self.logger.info(message, **kwargs)

        # 立即刷新日志缓冲区
        self._immediate_flush()

    # 插件专用方法
    def log_plugin_start(self, config: Dict[str, Any] = None):
        """记录插件启动"""
        config_info = f"配置: {config}" if config else "默认配置"
        self.info(f"插件启动 - {config_info}")

    def log_plugin_stop(self):
        """记录插件停止"""
        self.info("插件停止")

    def log_task_start(self, trace_id: str, task_data: Dict[str, Any]):
        """记录任务开始"""
        self.info(f"开始处理任务: {trace_id}", trace_id=trace_id, task_data=task_data)

    def log_task_result(self, trace_id: str, success: bool, result: Any = None, error: str = None):
        """记录任务结果"""
        if success:
            self.info(f"任务完成: {trace_id}", trace_id=trace_id, result=result)
        else:
            self.error(f"任务失败: {trace_id}", trace_id=trace_id, error=error)

    def log_performance(self, operation: str, duration: float, **metrics):
        """记录性能数据"""
        self.info(f"性能 - {operation}: {duration:.3f}s", operation=operation, duration=duration, **metrics)

    def get_log_file(self) -> Path:
        """获取插件日志文件路径"""
        return self.log_file

    def get_log_dir(self) -> Path:
        """获取插件日志目录"""
        return self.log_file.parent if self.log_file else Path(
            self.unified_logger.config['log_dir']) / "plugins" / self.plugin_name


class PublicLogger:
    """公共日志器（非插件使用）"""

    def __init__(self, unified_logger: BaseLogger):
        self.unified_logger = unified_logger
        self.logger = logger

    def _get_caller_info(self) -> Dict[str, str]:
        """获取调用者信息（模块名、函数名、文件名）"""
        try:
            # 获取当前调用栈
            frame = inspect.currentframe()
            # 向上回溯，跳过日志工具自身的调用栈
            for depth in range(1, 10):  # 最多回溯10层
                frame = frame.f_back
                if frame is None:
                    break

                # 获取帧的模块信息
                module_name = frame.f_globals.get('__name__', '')
                file_name = frame.f_code.co_filename

                # 跳过日志工具自身的模块和标准库模块
                if (module_name and
                        not module_name.startswith('utils.logger') and
                        not module_name.startswith('loguru') and
                        'site-packages' not in file_name and
                        'lib/python' not in file_name):
                    # 获取函数名
                    function_name = frame.f_code.co_name

                    # 获取文件名（不含路径）
                    file_name = Path(file_name).name

                    return {
                        'module': module_name,
                        'function': function_name,
                        'file': file_name,
                        'line': frame.f_lineno
                    }

        except Exception:
            pass

        return {'module': 'unknown', 'function': 'unknown', 'file': 'unknown', 'line': 0}

    def _log_with_caller_info(self, level: str, message: str, **kwargs):
        """带调用者信息的日志记录"""
        caller_info = self._get_caller_info()

        # 构建更详细的日志消息
        detailed_message = f"[{caller_info['file']}:{caller_info['line']}] {message}"

        # 添加调用者信息到extra
        extra = {
            'module': caller_info['module'],
            'function': caller_info['function'],
            'file': caller_info['file'],
            'line': caller_info['line']
        }

        # 记录日志
        self.log(level, detailed_message, **{**extra, **kwargs})

    # 公共日志方法
    def debug(self, message: str, **kwargs):
        self._log_with_caller_info("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log_with_caller_info("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log_with_caller_info("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log_with_caller_info("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log_with_caller_info("CRITICAL", message, **kwargs)

    def exception(self, message: str, exc: Exception, **kwargs):
        caller_info = self._get_caller_info()
        detailed_message = f"[{caller_info['file']}:{caller_info['line']}] {message}"
        self.logger.opt(exception=exc).error(detailed_message, **kwargs)
        self._immediate_flush()

    def log(self, level: str, message: str, **kwargs):
        """通用日志方法"""
        level = level.upper()
        if hasattr(self.logger, level.lower()):
            getattr(self.logger, level.lower())(message, **kwargs)
        else:
            self.logger.info(message, **kwargs)
        # 立即刷新日志缓冲区
        self._immediate_flush()

    def _immediate_flush(self):
        """立即刷新日志"""
        try:
            self.logger.debug("", flush=True)
        except:
            pass

class LoggingContext:
    """日志上下文管理器"""

    def __init__(self,
                 unified_logger: BaseLogger,
                 # request_id: Optional[str] = None,
                 plugin_name: Optional[str] = None,
                 module_name: Optional[str] = None):
        self.unified_logger = unified_logger
        # self.request_id = request_id or str(uuid.uuid4())[:8]
        self.plugin_name = plugin_name
        self.module_name = module_name
        # self.request_token = None
        self.plugin_token = None
        self.module_token = None

    def __enter__(self):
        # 设置上下文变量
        # self.request_token = request_id_var.set(self.request_id)
        if self.plugin_name:
            self.plugin_token = plugin_name_var.set(self.plugin_name)
        if self.module_name:
            self.module_token = module_name_var.set(self.module_name)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 恢复上下文变量
        # if self.request_token:
        #     request_id_var.reset(self.request_token)
        if self.plugin_token:
            plugin_name_var.reset(self.plugin_token)
        if self.module_token:
            module_name_var.reset(self.module_token)


# 全局实例和便捷函数
_unified_logger_instance = None


def setup_logging(config: Optional[Dict[str, Any]] = None) -> BaseLogger:
    """设置全局日志系统"""
    global _unified_logger_instance
    if _unified_logger_instance is None:
        _unified_logger_instance = BaseLogger(config)
    return _unified_logger_instance


def get_logger() -> BaseLogger:
    """获取全局日志器"""
    global _unified_logger_instance
    if _unified_logger_instance is None:
        _unified_logger_instance = setup_logging()
    return _unified_logger_instance


def get_public_logger() -> PublicLogger:
    """获取公共日志器（非插件使用）"""
    return get_logger().get_public_logger()


def get_plugin_logger(plugin_name: str) -> PluginLogger:
    """获取插件专用的日志器"""
    return get_logger().get_plugin_logger(plugin_name)


# 便捷函数 - 公共日志
def debug(message: str, **kwargs):
    """调试日志（公共）"""
    get_public_logger().debug(message, **kwargs)


def info(message: str, **kwargs):
    """信息日志（公共）"""
    get_public_logger().info(message, **kwargs)


def warning(message: str, **kwargs):
    """警告日志（公共）"""
    get_public_logger().warning(message, **kwargs)


def error(message: str, **kwargs):
    """错误日志（公共）"""
    get_public_logger().error(message, **kwargs)


def critical(message: str, **kwargs):
    """严重错误日志（公共）"""
    get_public_logger().critical(message, **kwargs)


def exception(message: str, exc: Exception, **kwargs):
    """异常日志（公共）"""
    get_public_logger().exception(message, exc, **kwargs)


def log(level: str, message: str, **kwargs):
    """通用日志（公共）"""
    get_public_logger().log(level, message, **kwargs)


def log_function_call(level: str = "INFO", with_args: bool = True):
    """函数调用日志装饰器（公共）"""
    return get_logger().log_function_call(level, with_args)


def context(
            # request_id: Optional[str] = None,
            plugin_name: Optional[str] = None,
            module_name: Optional[str] = None):
    """日志上下文管理器（公共）"""
    return get_logger().context(plugin_name, module_name)

def force_flush():
    """强制刷新所有日志"""
    try:
        # 记录一条空消息强制刷新
        logger.debug("", flush=True)
    except:
        pass


# 初始化时立即设置日志
def initialize_logging(config: Dict[str, Any] = None):
    """初始化日志系统并立即创建文件"""
    setup_logging(config)

    # 确保日志目录和文件被创建
    log_dir = Path(config.get('log_dir', 'logs') if config else 'logs')
    public_log_path = log_dir / (config.get('public_log_file', 'application.log') if config else 'application.log')

    # 立即创建目录和文件
    public_log_path.parent.mkdir(exist_ok=True, parents=True)
    public_log_path.touch(exist_ok=True)

    return get_public_logger()


# 在模块导入时自动初始化基础日志
try:
    setup_logging()
except Exception as e:
    print(f"自动日志初始化失败: {e}")