from flask import Flask, render_template, request, jsonify
import configparser
from PyQt5.QtWidgets import QApplication, QFileDialog
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from market_data import my_market
import tkinter as tk
from tkinter import filedialog
import os
import werkzeug
import socket
from contextlib import closing
import json
from flask_socketio import SocketIO
import eventlet

# 在导入其他模块之前先打补丁
import eventlet.support.greendns
eventlet.support.greendns.is_enabled = lambda: False

# 设置 Werkzeug 的日志级别为 WARNING，这样就不会显示 INFO 级别的访问日志
werkzeug.serving.WSGIRequestHandler.log = lambda self, type, message, *args: None
logging.getLogger('werkzeug').setLevel(logging.WARNING)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # 添加密钥
socketio = SocketIO(app, async_mode='eventlet')

# 配置日志
def setup_logger():
    """设置日志"""
    logger = logging.getLogger('web_ui')
    logger.setLevel(logging.INFO)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 创建文件处理器
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, 'web_ui.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    
    # 设置格式化器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# 读取配置
def load_config():
    """加载配置"""
    config = configparser.ConfigParser(interpolation=None)  # 禁用插值
    config_file = 'config.ini'
    
    if os.path.exists(config_file):
        config.read(config_file, encoding='utf-8')
    
    return config

# 初始化日志
logger = setup_logger()

# 配置项名称映射
CONFIG_NAME_MAP = {
    'Trading': '交易设置',
    'top_n_boards': '热门板块数量',
    'top_n_stocks': '热门股票数量',
    'interval_get_hot_boards': '刷新板块间隔(秒)',
    
    'MA': '均线设置',
    'boll_days': '布林线天数',
    'boll_multiples': '布林线倍数',
    'ma_5': '五日均线',
    
    'Account': '账户设置',
    'path_qmt': '交易端路径',
    'account_id': '账户ID',
    
    'Threshold': '阈值设置',
    'threshold_cur_updownrate_hushen': '沪深股涨跌幅阈值',
    'threshold_hist_updownrate_heshen': '历史涨跌幅阈值',
    'threshold_cur_updownrate_feihushen': '非沪深股涨跌幅阈值',
    'threshold_hist_updownrate_feiheshen': '非沪深历史涨跌幅阈值',
    
    'Days': '时间设置',
    'ndays_before_1': '涨幅检查天数',
    'ndays_before_2': '平稳检查天数',
    'ndays_before_3': '最高价检查天数',
    'ndays_before_4': '涨停板检查天数',
    'ndays_before_5': 'K线图显示天数'
}

def read_config():
    """读取配置文件"""
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    return config

def save_config(config_data):
    """保存配置文件"""
    config = configparser.ConfigParser()
    for section, items in config_data.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, value in items.items():
            config.set(section, key, str(value))
    
    with open('config.ini', 'w', encoding='utf-8') as f:
        config.write(f)

@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html', 
                         # Trading
                         top_n_boards=my_market.TOP_N_BOARDS,
                         top_n_stocks=my_market.TOP_N_STOCKS,
                         interval_get_hot_boards=my_market.INTERVAL_GET_HOT_BOARDS,
                         
                         # MA
                         boll_days=my_market.BOLL_DAYS,
                         boll_multiples=my_market.BOLL_MULTIPLES,
                         ma_5=my_market.MA_5,
                         
                         # Account
                         path_qmt=my_market.PATH_QMT,
                         account_id=my_market.ACCOUNT_ID,
                         
                         # Threshold
                         threshold_cur_10pct=my_market.THRESHOLD_CUR_UPDOWNRATE_10PCT,
                         threshold_hist_10pct=my_market.THRESHOLD_HIST_UPDOWNRATE_10PCT,
                         threshold_cur_20pct=my_market.THRESHOLD_CUR_UPDOWNRATE_20PCT,
                         threshold_hist_20pct=my_market.THRESHOLD_HIST_UPDOWNRATE_20PCT,
                         threshold_cur_30pct=my_market.THRESHOLD_CUR_UPDOWNRATE_30PCT,
                         threshold_hist_30pct=my_market.THRESHOLD_HIST_UPDOWNRATE_30PCT,
                         
                         # Days
                         ndays_before_1=my_market.NDAYS_BEFORE_1,
                         ndays_before_2=my_market.NDAYS_BEFORE_2,
                         ndays_before_3=my_market.NDAYS_BEFORE_3,
                         ndays_before_4=my_market.NDAYS_BEFORE_4)

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """处理配置文件的读写"""
    if request.method == 'GET':
        try:
            config = read_config()
            result = {}
            # 遍历所有配置节
            for section in config.sections():
                try:
                    # 安全地获取每个节的内容
                    result[section] = dict(config.items(section))
                except Exception as e:
                    logger.error(f"读取配置节 {section} 时出错: {e}")
                    result[section] = {}
            
            return jsonify({
                "config": result,
                "name_map": CONFIG_NAME_MAP
            })
        except Exception as e:
            logger.error(f"读取配置文件时出错: {e}")
            return jsonify({
                "config": {},
                "name_map": CONFIG_NAME_MAP
            })
    else:
        config_data = request.json
        save_config(config_data)
        return jsonify({"status": "success"})

@app.route('/api/trading_info')
def get_trading_info():
    """获取交易相关信息"""
    try:
        asset_info = my_market.get_asset_info()
        positions_info = my_market.get_positions_info()
        orders_info = my_market.get_orders_info()
        trades_info = my_market.get_trades_info()
        
        # 获取toast消息
        toast_message = my_market.get_toast_message()        


        data = {
            'asset': asset_info,
            'positions': positions_info,
            'orders': orders_info,
            'trades': trades_info,
            'toast_message': toast_message  # 添加toast消息
        }
        return jsonify(data)

    except Exception as e:
        logger.error(f"获取交易信息时出错：{e}")
        return jsonify({
            'asset': {
                'account_id': my_market.ACCOUNT_ID,
                'cash': 0.0,
                'total_asset': 0.0,
                'market_value': 0.0
            },
            'positions': [],
            'orders': [],
            'trades': [],
            'order_error': None
        }), 200

@app.route('/api/market_info')
def get_market_info():
    """获取市场信息"""
    try:
        industry_info = my_market.get_industry_info()
        
        concept_info = my_market.get_concept_info()
        
        selected_info = my_market.get_selected_info()
        
        return jsonify({
            'industry': industry_info,
            'concept': concept_info,
            'selected': selected_info
        })
    except Exception as e:
        logger.error(f"获取市场信息时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'industry': [],
            'concept': [],
            'selected_stocks': []
        })

@app.route('/api/select_path', methods=['GET'])
def select_path():
    """打开文件夹选择对话框"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    path = QFileDialog.getExistingDirectory(None, "选择文件夹", "")
    return jsonify({"path": path if path else ""})

@app.route('/api/account_info')
def get_account_info():
    try:
        if my_market.asset:
            return jsonify({
                'account_id': my_market.ACCOUNT_ID,
                'total_asset': my_market.asset.total_asset,
                'cash': my_market.asset.cash
            })
        else:
            return jsonify({
                'total_asset': 0,
                'cash': 0
            })
    except Exception as e:
        logger.error(f"获取账户信息时出错：{e}")
        return jsonify({
            'total_asset': 0,
            'cash': 0
        })

@app.route('/select_qmt_path', methods=['POST'])
def select_qmt_path():
    """打开文件选择对话框"""
    try:
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        root.attributes('-topmost', True)  # 保持在最上层
        
        # 获取当前QMT路径作为初始目录
        initial_dir = my_market.PATH_QMT if os.path.exists(my_market.PATH_QMT) else "/"
        
        # 打开文件夹选择对话框
        path = filedialog.askdirectory(
            initialdir=initial_dir,
            title="选择QMT路径"
        )
        
        if path:
            # 更新配置
            config = configparser.ConfigParser()
            config_file = 'config.ini'
            
            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')
            
            if 'Account' not in config:
                config['Account'] = {}
            
            config['Account']['PATH_QMT'] = path
            
            # 保存到文件
            with open(config_file, 'w', encoding='utf-8') as f:
                config.write(f)
            
            # 重新加载配置
            my_market.load_config()
            
            return jsonify({'success': True, 'path': path})
        return jsonify({'success': False, 'error': '未选择路径'})
    except Exception as e:
        logger.error(f"选择QMT路径时出错：{e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/save_qmt_path', methods=['POST'])
def save_qmt_path():
    """保存新的 QMT 路径到配置文件"""
    try:
        data = request.get_json()
        new_path = data.get('path')
        
        if new_path:
            # 更新配置文件
            config = configparser.ConfigParser()
            config_file = 'config.ini'
            
            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')
            
            if 'Account' not in config:
                config['Account'] = {}
            
            config['Account']['PATH_QMT'] = new_path
            
            with open(config_file, 'w', encoding='utf-8') as f:
                config.write(f)
            
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'No path provided'})
    except Exception as e:
        logger.error(f"保存QMT路径时出错：{e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/save_config', methods=['POST'])
def save_config():
    try:
        config_data = request.json
        
        # 保存配置
        config = configparser.ConfigParser(interpolation=None)
        config.read('config.ini', encoding='utf-8')
        
        # 更新配置
        for section, values in config_data.items():
            if not config.has_section(section):
                config.add_section(section)
            for key, value in values.items():
                config.set(section, key, str(value))
        
        # 写入文件
        with open('config.ini', 'w', encoding='utf-8') as f:
            config.write(f)
            
        # 重新加载配置
        my_market.load_config()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"保存配置时出错: {e}")
        return jsonify({'success': False, 'error': str(e)})

def find_free_port():
    """找到一个可用的端口"""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
        return port

@app.route('/update_single_buy_amount', methods=['POST'])
def update_single_buy_amount():
    try:
        data = request.get_json()
        my_market.SINGLE_BUY_AMOUNT = float(data['single_buy_amount'])
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"更新单次买入金额失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_single_buy_amount')
def get_single_buy_amount():
    try:
        return jsonify({'success': True, 'amount': my_market.SINGLE_BUY_AMOUNT})
    except Exception as e:
        logger.error(f"获取单次买入金额失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_max_stocks', methods=['POST'])
def update_max_stocks():
    try:
        data = request.get_json()
        my_market.MAX_STOCKS_PER_DAY = int(data['max_stocks'])
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"更新买入股票支数限制失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_max_stocks')
def get_max_stocks():
    try:
        return jsonify({'success': True, 'amount': my_market.MAX_STOCKS_PER_DAY})
    except Exception as e:
        logger.error(f"获取买入股票支数限制失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_cancel_seconds', methods=['POST'])
def update_cancel_seconds():
    try:
        data = request.get_json()
        my_market.CANCEL_ORDER_SECONDS = int(data['cancel_seconds'])
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"更新撤单时间失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_cancel_seconds')
def get_cancel_seconds():
    try:
        return jsonify({'success': True, 'amount': my_market.CANCEL_ORDER_SECONDS})
    except Exception as e:
        logger.error(f"获取撤单时间失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/health_check')
def health_check():
    """健康检查接口"""
    return jsonify({'status': 'ok'})

def start_web_server():
    host = '127.0.0.1'
    port = 8080
    
    logger.info("网页服务器正在启动...")
    logger.info(f"请在浏览器中访问: http://{host}:{port}")
    
    # 使用 eventlet 作为服务器
    socketio.run(app, 
                host=host, 
                port=port, 
                debug=False)

if __name__ == '__main__':
    start_web_server() 