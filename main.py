#!/usr/bin/env python3
"""
Simple HTTP File Server with Custom 404 Page
Auto-set directory to ./data, logs to ./log
"""

import http.server
import socketserver
import os
import sys
import platform
import datetime
import configparser
from pathlib import Path
from urllib.parse import unquote

# ==================== 自动配置 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "log")  # 日志目录
CONFIG_FILE = os.path.join(BASE_DIR, "conf.txt")

DEFAULT_CONFIG = f"""; HTTP File Server Configuration
; 数据目录: {DATA_DIR}
; 日志目录: {LOG_DIR}

[server]
port = 8080

[logging]
enable_access_log = true
log_to_file = false
log_file = server.log

[security]
directory_listing = true
cors_origin = *

[advanced]
bind_address = 0.0.0.0
index_files = index.html,index.htm,default.html
"""
# =================================================

class ColoredLogger:
    """彩色控制台日志"""
    COLORS = {
        'green': '\033[92m', 'yellow': '\033[93m', 'red': '\033[91m',
        'blue': '\033[94m', 'cyan': '\033[96m', 'white': '\033[97m',
        'gray': '\033[90m', 'reset': '\033[0m', 'bold': '\033[1m',
        'magenta': '\033[95m'
    }
    
    @classmethod
    def log(cls, level, message, color='white'):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        color_code = cls.COLORS.get(color, cls.COLORS['white'])
        reset = cls.COLORS['reset']
        bold = cls.COLORS['bold']
        
        level_tags = {
            'INFO': f"{cls.COLORS['blue']}INFO{reset}",
            'SUCCESS': f"{cls.COLORS['green']}OK{reset}",
            'WARN': f"{cls.COLORS['yellow']}WARN{reset}",
            'ERROR': f"{cls.COLORS['red']}ERR{reset}",
            'REQ': f"{cls.COLORS['cyan']}REQ{reset}",
            'FILE': f"{cls.COLORS['green']}FILE{reset}",
            'CONFIG': f"{cls.COLORS['yellow']}CONF{reset}",
            'CACHE': f"{cls.COLORS['magenta']}CACHE{reset}"
        }
        
        tag = level_tags.get(level, level)
        print(f"{cls.COLORS['gray']}[{timestamp}]{reset} {bold}{tag}{reset} {color_code}{message}{reset}")
        
        # 写入日志文件到 log 目录
        if Config.LOG_TO_FILE and hasattr(Config, 'LOG_FILE'):
            try:
                # 确保 log 目录存在
                if not os.path.exists(LOG_DIR):
                    os.makedirs(LOG_DIR, exist_ok=True)
                
                log_path = os.path.join(LOG_DIR, Config.LOG_FILE)
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(f"[{timestamp}] [{level}] {message}\n")
            except Exception as e:
                # 日志写入失败不中断程序
                pass

class Config:
    """配置管理类"""
    PORT = 8080
    ENABLE_ACCESS_LOG = True
    LOG_TO_FILE = False
    LOG_FILE = "server.log"
    DIRECTORY_LISTING = True
    CORS_ORIGIN = "*"
    BIND_ADDRESS = "0.0.0.0"
    INDEX_FILES = ["index.html", "index.htm", "default.html"]
    
    @classmethod
    def load(cls):
        """加载配置"""
        if not os.path.exists(CONFIG_FILE):
            ColoredLogger.log('CONFIG', f"创建配置文件: {CONFIG_FILE}", 'yellow')
            try:
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    f.write(DEFAULT_CONFIG)
            except Exception as e:
                ColoredLogger.log('ERROR', f"无法创建配置: {e}", 'red')
        
        try:
            config = configparser.ConfigParser()
            config.read(CONFIG_FILE, encoding='utf-8')
            
            if 'server' in config:
                cls.PORT = config.getint('server', 'port', fallback=8080)
            
            if 'logging' in config:
                cls.ENABLE_ACCESS_LOG = config.getboolean('logging', 'enable_access_log', fallback=True)
                cls.LOG_TO_FILE = config.getboolean('logging', 'log_to_file', fallback=False)
                cls.LOG_FILE = config.get('logging', 'log_file', fallback='server.log')
            
            if 'security' in config:
                cls.DIRECTORY_LISTING = config.getboolean('security', 'directory_listing', fallback=True)
                cls.CORS_ORIGIN = config.get('security', 'cors_origin', fallback='*')
            
            if 'advanced' in config:
                cls.BIND_ADDRESS = config.get('advanced', 'bind_address', fallback='0.0.0.0')
                index_str = config.get('advanced', 'index_files', fallback='index.html,index.htm')
                cls.INDEX_FILES = [f.strip() for f in index_str.split(',') if f.strip()]
            
            ColoredLogger.log('SUCCESS', "配置加载成功", 'green')
            return True
        except Exception as e:
            ColoredLogger.log('ERROR', f"配置错误: {e}", 'red')
            return False

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义请求处理器"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DATA_DIR, **kwargs)
        self._logged_transfer = False
    
    def log_message(self, format, *args):
        """重写日志"""
        if not Config.ENABLE_ACCESS_LOG:
            return
            
        client_ip = self.address_string()
        method = self.command
        path = unquote(self.path)
        status = self.status_code if hasattr(self, 'status_code') else '-'
        
        status_str = str(status)
        if status_str.startswith('2'):
            status_color = 'green'
        elif status_str.startswith('3'):
            status_color = 'magenta'
        elif status_str.startswith('4'):
            status_color = 'yellow'
        else:
            status_color = 'red'
        
        marker = ""
        if status == 304:
            marker = " [缓存]"
        elif status == 404:
            marker = " [未找到]"
        
        ColoredLogger.log('REQ', f"{client_ip:<15} | {method:4} {path:35} | {status}{marker}", status_color)
    
    def do_GET(self):
        """处理GET请求"""
        self._logged_transfer = False
        super().do_GET()
        
        if Config.ENABLE_ACCESS_LOG and not self._logged_transfer:
            if hasattr(self, 'status_code') and self.status_code == 200:
                translated = self.translate_path(self.path)
                if os.path.isfile(translated):
                    try:
                        size = os.path.getsize(translated)
                        size_str = self._format_size(size)
                        path_display = unquote(self.path) if self.path != '/' else '/ (index)'
                        ColoredLogger.log('FILE', f"传输: {path_display} ({size_str})", 'green')
                    except:
                        pass
    
    def send_error(self, code, message=None, explain=None):
        """自定义错误页面"""
        if code == 404:
            self._serve_404_page()
        else:
            super().send_error(code, message, explain)
    
    def _serve_404_page(self):
        """提供自定义404页面"""
        self.send_response(404)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        
        html = self._get_404_template()
        self.wfile.write(html.encode('utf-8'))
        
        if Config.ENABLE_ACCESS_LOG:
            ColoredLogger.log('REQ', f"{self.client_address[0]:<15} | GET  {unquote(self.path):35} | 404 [自定义页面]", 'yellow')
    
    def _get_404_template(self):
        """404页面模板"""
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>404 - 页面未找到</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            color: white;
        }
        .container {
            text-align: center;
            padding: 40px;
            max-width: 600px;
        }
        .error-code {
            font-size: 8rem;
            font-weight: bold;
            text-shadow: 4px 4px 0 rgba(0,0,0,0.2);
            margin-bottom: 0;
            line-height: 1;
            opacity: 0.9;
        }
        .error-text {
            font-size: 1.8rem;
            margin: 20px 0;
            font-weight: 300;
        }
        .icon { font-size: 4rem; margin: 20px 0; }
        .path {
            background: rgba(255,255,255,0.2);
            padding: 15px 25px;
            border-radius: 10px;
            margin: 30px 0;
            font-family: 'Courier New', monospace;
            word-break: break-all;
            font-size: 1rem;
            border: 2px dashed rgba(255,255,255,0.3);
        }
        .back-btn {
            display: inline-block;
            margin-top: 30px;
            padding: 15px 40px;
            background: white;
            color: #764ba2;
            text-decoration: none;
            border-radius: 30px;
            font-weight: bold;
            font-size: 1.1rem;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        .back-btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }
        .tips {
            margin-top: 30px;
            opacity: 0.8;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🔍</div>
        <div class="error-code">404</div>
        <div class="error-text">页面未找到</div>
        <div class="path" id="path">/</div>
        <a href="/" class="back-btn">🏠 返回首页</a>
        <div class="tips">请检查URL是否正确，或联系管理员</div>
    </div>
    <script>
        document.getElementById('path').textContent = location.pathname;
    </script>
</body>
</html>"""
    
    def send_response(self, code, message=None):
        """捕获响应码"""
        self.status_code = code
        super().send_response(code, message)
    
    def translate_path(self, path):
        """支持多首页文件"""
        path = super().translate_path(path)
        
        if os.path.isdir(path):
            for index_file in Config.INDEX_FILES:
                index_path = os.path.join(path, index_file)
                if os.path.exists(index_path):
                    return index_path
            
            if not Config.DIRECTORY_LISTING and self.path != '/':
                self.send_error(403, "Directory listing disabled")
                return os.devnull
        
        return path
    
    def list_directory(self, path):
        """重写目录列表"""
        if not Config.DIRECTORY_LISTING:
            self.send_error(403, "Directory listing disabled")
            return None
        return super().list_directory(path)
    
    def end_headers(self):
        """添加CORS"""
        self.send_header('Access-Control-Allow-Origin', Config.CORS_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, HEAD')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()
    
    @staticmethod
    def _format_size(size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

def check_privileges():
    """检查管理员权限"""
    if platform.system() == "Windows":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    else:
        try:
            return os.geteuid() == 0
        except:
            return False

def setup_directories():
    """初始化所有目录"""
    # 创建 data 目录
    if not os.path.exists(DATA_DIR):
        ColoredLogger.log('INFO', f"创建数据目录: {DATA_DIR}", 'blue')
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except Exception as e:
            ColoredLogger.log('ERROR', f"无法创建数据目录: {e}", 'red')
            sys.exit(1)
    
    # 创建 log 目录（自动创建，不需要提示）
    if not os.path.exists(LOG_DIR):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
        except Exception as e:
            ColoredLogger.log('WARN', f"无法创建日志目录: {e}", 'yellow')
    
    # 创建默认首页
    index_path = os.path.join(DATA_DIR, "index.html")
    if not os.path.exists(index_path):
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>HTTP Server</title>
    <style>
        body{{font-family:system-ui;margin:40px;background:#f5f5f5}}
        .container{{max-width:800px;margin:0 auto;background:white;padding:40px;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}
        h1{{color:#333}}
        .info{{background:#e3f2fd;padding:15px;border-radius:8px;margin:20px 0;color:#1976d2}}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 HTTP File Server</h1>
        <div class="info">
            <strong>数据目录:</strong> {DATA_DIR}<br>
            <strong>日志目录:</strong> {LOG_DIR}<br>
            <strong>时间:</strong> {now_str}
        </div>
        <p>服务器运行正常！在 <code>data</code> 文件夹中添加您的文件。</p>
    </div>
</body>
</html>"""
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(html)
            ColoredLogger.log('SUCCESS', f"创建首页: {index_path}", 'green')
        except Exception as e:
            ColoredLogger.log('WARN', f"创建首页失败: {e}", 'yellow')

def get_ip_addresses():
    """获取IP地址"""
    ips = []
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        ips.append(("本地", "localhost"))
        ips.append(("局域网", local_ip))
    except:
        ips.append(("访问", "127.0.0.1"))
    return ips

def print_banner():
    """打印启动横幅"""
    ips = get_ip_addresses()
    ip_lines = "\n".join([f"  🌐 {name}: http://{ip}:{Config.PORT}/" for name, ip in ips])
    
    print(f"""
╔══════════════════════════════════════════════════════════╗
║              🌐 HTTP File Server v2.1                    ║
╠══════════════════════════════════════════════════════════╣
  💻 系统: {platform.system()} {platform.release()}
  📂 数据: {DATA_DIR}
  📝 日志: {LOG_DIR}
{ip_lines}
╚══════════════════════════════════════════════════════════╝
    """)

def main():
    """主函数"""
    print("正在初始化...")
    
    Config.load()
    
    is_admin = check_privileges()
    if Config.PORT < 1024 and not is_admin:
        ColoredLogger.log('WARN', f"端口 {Config.PORT} 需要管理员权限", 'yellow')
        input("按 Enter 继续，或 Ctrl+C 退出...")
    
    setup_directories()
    os.chdir(DATA_DIR)
    
    print_banner()
    
    try:
        with socketserver.TCPServer((Config.BIND_ADDRESS, Config.PORT), CustomHTTPRequestHandler) as httpd:
            ColoredLogger.log('SUCCESS', f"服务器启动！监听 {Config.BIND_ADDRESS}:{Config.PORT}", 'green')
            if Config.LOG_TO_FILE:
                log_path = os.path.join(LOG_DIR, Config.LOG_FILE)
                ColoredLogger.log('INFO', f"日志文件: {log_path}", 'blue')
            print("-" * 60)
            httpd.serve_forever()
    except PermissionError:
        ColoredLogger.log('ERROR', f"权限不足: 端口 {Config.PORT}", 'red')
    except OSError as e:
        if "Address already in use" in str(e):
            ColoredLogger.log('ERROR', f"端口 {Config.PORT} 已被占用", 'red')
        else:
            ColoredLogger.log('ERROR', f"启动失败: {e}", 'red')
    except KeyboardInterrupt:
        print("\n")
        ColoredLogger.log('INFO', "服务器已停止", 'blue')

if __name__ == "__main__":
    main()