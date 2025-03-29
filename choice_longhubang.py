import os
import sys
import pandas as pd
import akshare as ak
import mplfinance as mpf
from PyQt5.QtWidgets import QApplication, QWidget, QMessageBox, QTableWidgetItem, QAbstractItemView
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from datetime import timedelta, datetime
import time
from plyer import notification
import warnings
from main_win_3 import Ui_Dialog
import queue
import math
from threading import Lock
import json
import logging
import chardet
import codecs
from conditions import check_stock_conditions
import requests
warnings.filterwarnings("ignore", category=DeprecationWarning)

class Config:
    def __init__(self):
        self.TOP_N_BOARDS = 7
        self.TOP_N_STOCKS = 15
        self.INTERVAL_GET_HOT_BOARDS = 10
        self.INTERVAL_CHECK_STOCKS = 3
        
        # 从配置文件加载
        self.load_from_file()
    
    def load_from_file(self):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.__dict__.update(config)
        except FileNotFoundError:
            pass
config = Config()

INTERVAL_GET_HOT_BOARDS = 10 #获取热门板块及其股票的数据的时间间隔（秒）
INTERVAL_CHECK_STOCKS = 3 #开市期间（9:25-11:30；13:00-15:00）获取所有股票详情及检查备选股票的时间间隔（秒），其他时段整15分钟1次

NDAYS_BEFORE_5 = 65 #显示多少天的K线图

MA1DAYS = 10 #第一组均线的天数
MA1MULTIPLES = 0 #第一组均线的布林带倍数
MA2DAYS = 20 #第二组均线的天数
MA2MULTIPLES = 2 #第二组均线的布林带倍数

# 使用字典替代全局变量,便于管理和访问
class GlobalVars:
    def __init__(self):
        self.suspend_selection = False
        self.get_hist_queue = queue.Queue()
        self.stocks_hist_df = pd.DataFrame()
        self.stocks_realtime_df = pd.DataFrame()

g_vars = GlobalVars()

#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ AK SHARE 函数封装 $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$#
#获取某支股票的历史数据
def get_stock_hist(symbol, startdate, enddate, adjust):
    #symbol = '000501'
    df = pd.DataFrame()        
    try:
        # 获取东方财富网的股票代码
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                start_date=startdate, end_date=enddate, adjust=adjust)
    except Exception as e:
        print("获取股票代码",symbol,"的历史数据时出错，错误信息：", e)
    return df

#获取所有股票的实时数据
def get_stocks_realtime_data():
    df = pd.DataFrame()        
    try:
        # 获取东方财富网的实时股票代码
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        print("获取全部股票的实时数据时出错，错误信息：", e)
    return df

#获取热门行业板块
def get_board_industry_name():
    df = pd.DataFrame()        
    try:
        df = ak.stock_board_industry_name_em()
    except Exception as e:
        print("获取热门板块数据时出错，错误信息：", e)
    return df

#获取某个行业板块的所有股票
def get_board_industry_cons(sector):
    df = pd.DataFrame()        
    try:
        df = ak.stock_board_industry_cons_em(symbol=sector)
    except Exception as e:
        print("获取板块", sector, "的股票列表时出错，错误信息：", e)
    return df

#获取热门概念板块
def get_board_concept_name():
    df = pd.DataFrame()        
    try:
        df = ak.stock_board_concept_name_em()
    except Exception as e:
        print("获取热门板块数据时出错，错误信息：", e)
    return df

#获取某个概念板块的所有股票
def get_board_concept_cons(sector):
    df = pd.DataFrame()        
    try:
        df = ak.stock_board_concept_cons_em(symbol=sector)
    except Exception as e:
        print("获取板块", sector, "的股票列表时出错，错误信息：", e)
    return df

#获取某支股票的龙虎榜数据
def get_longhubang_data(stock_code):
    df = ak.stock_lhb_stock_detail_date_em(symbol=stock_code) 
    # 获取当前日期
    current_date = pd.Timestamp.now()
    # 计算两个月前的日期
    two_month_ago = current_date - pd.DateOffset(months=2)

    # 将df中的交易日期列转换为datetime格式
    df['交易日'] = pd.to_datetime(df['交易日'])

    # 筛选最近一个月的数据
    df = df[df['交易日'] >= two_month_ago]
    # 如果行数大于2,只保留最前面的两行
    message = ""
    if len(df) == 0:
        message += "\n该股票最近两个月没有龙虎榜数据"
    else:
        message += f"\n该股票最近两个月有{len(df)}天有龙虎榜数据，最近的数据详情如下：\n"
        if len(df) > 2:
            df = df.head(2)
        # 遍历df中的每个交易日
        for index, row in df.iterrows():
            trade_date = row['交易日'].strftime('%Y%m%d')
            message += f"{trade_date}的龙虎榜买入数据:\n"
            # 获取该日期的龙虎榜数据
            lhb_detail = ak.stock_lhb_stock_detail_em(symbol=stock_code, date=trade_date, flag="买入")
            message += f"{lhb_detail}\n"
            message += f"{trade_date}的龙虎榜卖出数据:\n"
            lhb_detail = ak.stock_lhb_stock_detail_em(symbol=stock_code, date=trade_date, flag="卖出")
            message += f"{lhb_detail}\n"
    return message

#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ ANALYSE TOOLS $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$#
# 计算布林带指标
def calculate_bollinger_bands(df, n, k):
    # data: 输入的价格数据，如收盘价、开盘价等
    # n: 移动平均线的时间周期
    # k: 布林带的宽度倍数
    ma = df.rolling(n).mean()
    std = df.rolling(n).std()
    upper_band = ma + k * std
    lower_band = ma - k * std
    return ma, upper_band, lower_band

#判断是否是涨停板
def is_limit_up(symbol, price):
    if symbol[:2] in ("00", "60"):
        MAX_UPRATE = 9.9
    else:
        MAX_UPRATE = 19.9
    if price >= MAX_UPRATE:
        return True
    return False

#价格变化率
def price_increase_rate(p1, p2):
    return (p2-p1)/p2

#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ COMMON FUNCTION $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$#
def process_symbol_data(df, ma1d, ma1m, ma2d, ma2m, ma_5):
    # 调整 DataFrame 列名以符合 mplfinance 的要求
    df.rename(columns={
        '日期': 'date',
        '股票代码': 'symbol',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
        '涨跌幅': 'updownrate'
    }, inplace=True)
    # 将日期列设置为索引并转换为 datetime 类型
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)

    # 将收盘价作为价格数据，计算20日布林带指标和5日均线
    ma, upper_band, lower_band = calculate_bollinger_bands(
        df['close'], ma1d, ma1m)
    df['ma_1'] = ma
    df['upper_band_1'] = upper_band
    df['lower_band_1'] = lower_band
    ma, upper_band, lower_band = calculate_bollinger_bands(
        df['close'], ma2d, ma2m)
    df['ma_2'] = ma
    df['upper_band_2'] = upper_band
    df['lower_band_2'] = lower_band
    df['ma_5'] = df['close'].rolling(window=ma_5).mean()    
    return df             

#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ SUB THREAD $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$#
class get_stock_hist_thread(QThread):
    def __init__(self):
        super().__init__()
    
    def run(self):
        global g_vars
        while True:
            if not g_vars.get_hist_queue.empty():
                symbol = g_vars.get_hist_queue.get()
                if g_vars.stocks_hist_df.empty:
                    result = False
                else:
                    mask = g_vars.stocks_hist_df['symbol'].isin([symbol])
                    result = mask.any()
                if not result:
                    today = datetime.today()
                    delta = timedelta(days = NDAYS_BEFORE_5)
                    hundred_days_ago = today - delta
                    delta = timedelta(days = 1)
                    yesterday = today -delta
                    startdate = hundred_days_ago.strftime('%Y%m%d')
                    enddate = yesterday.strftime('%Y%m%d')

                    hist_df = get_stock_hist(symbol, startdate, enddate, "qfq") #数据分析时一般用后复权，考虑到要跟今天的数据对比，采用前复权
                    # 检查获取的 DataFrame 是否为空
                    if not hist_df.empty: #处理代码数据，包括将日期列设为索引，计算布林带
                        if hist_df is not None:
                            hist_df = process_symbol_data(hist_df, MA1DAYS-1, MA1MULTIPLES, MA2DAYS-1, MA2MULTIPLES, 4) #MA20和MA5都算到前一交易日，且天数少一天
                    g_vars.stocks_hist_df = pd.concat([g_vars.stocks_hist_df, hist_df], axis=0, ignore_index=True)
            else:
                time.sleep(1)

class get_stock_realtime_thread(QThread):
    got_stock_realtime_signal = pyqtSignal()
    def __init__(self):
        super().__init__()
    
    def run(self):
        global g_vars
        time.sleep(config.INTERVAL_GET_HOT_BOARDS) #先等待获取板块信息
        while True:
            g_vars.stocks_realtime_df = get_stocks_realtime_data()
            if g_vars.stocks_realtime_df.empty:
                # 显示吐司通知，设置标题、消息内容以及显示时长（可选，单位为秒）
                notification.notify('提醒','获取实时数据时出错','蚂蚁选股','ant.ico',2)
                time.sleep(1)
            else:
                self.got_stock_realtime_signal.emit()
                now = datetime.now()
                now_str = now.strftime('%H:%M:%S')
                if "09:25:00" < now_str < "11:31:59" or "12:59:00" < now_str < "23:59:00":#"15:05:59":
                    time.sleep(config.INTERVAL_CHECK_STOCKS)
                else:
                    minutes = now.minute
                    seconds = now.second
                    # 计算距离下一个整五分钟还需要的分钟数
                    minutes_next_five_minutes = 15 - (minutes % 15)
                    if minutes_next_five_minutes == 15:
                        minutes_next_five_minutes = 0
                    # 计算距离下一个整五分钟还需要的秒数
                    seconds_next_five_minutes = 60 - seconds
                    if seconds_next_five_minutes == 60:
                        seconds_next_five_minutes = 0
                    time.sleep(minutes_next_five_minutes*60 + seconds_next_five_minutes)

class refresh_board_thread(QThread):
    update_t_board_signal = pyqtSignal(str, pd.DataFrame)

    def __init__(self, board):
        super().__init__()
        self.board = board

    def run(self):
        global g_vars
        while True:
            if self.board == "industry":
                stock_board_name_em_df = get_board_industry_name()
            else:
                stock_board_name_em_df = get_board_concept_name()
            if stock_board_name_em_df.empty:
                time.sleep(1)
            else:
                top_boards = stock_board_name_em_df.head(config.TOP_N_BOARDS).copy()  # 获取前5个
                top_boards.drop('排名', axis = 1, inplace=True)
                top_boards['时间'] = datetime.now().strftime('%H:%M:%S')# 添加操作时间列
                columns_order = top_boards.columns.tolist()
                columns_order.insert(1, columns_order.pop(columns_order.index('时间')))
                top_boards = top_boards[columns_order]

                #获取热门板块的股票
                stocks_df = pd.DataFrame()
                for row_index, row_data in top_boards.iterrows():
                    sector = row_data['板块名称']
                    if self.board == "industry":
                        stock_board_cons_em_df = get_board_industry_cons(sector)
                    else:
                        stock_board_cons_em_df = get_board_concept_cons(sector)
                    top_stocks = stock_board_cons_em_df.head(config.TOP_N_STOCKS).copy()
                    if not top_stocks.empty:
                        condition = top_stocks['代码'].astype(str).str[:2].isin(["00","30","60"]) #只看这三个市场的
                        top_stocks = top_stocks[condition]
                        top_stocks['分析结果'] = ""
                        top_stocks['板块'] = sector
                        stocks_df = pd.concat([stocks_df, top_stocks], axis=0, ignore_index=True)

                if stocks_df.empty:            
                    time.sleep(1) #获取全部都失败则三秒钟后重试
                else:
                    stocks_df.drop('序号', axis = 1, inplace=True)
                    columns_order = stocks_df.columns.tolist()
                    columns_order.insert(0, columns_order.pop(columns_order.index('板块')))
                    columns_order.insert(1, columns_order.pop(columns_order.index('分析结果')))
                    stocks_df = stocks_df[columns_order]
                    self.update_t_board_signal.emit(self.board, stocks_df)

                    if g_vars.stocks_hist_df.empty:
                        for element in stocks_df['代码']:
                            g_vars.get_hist_queue.put(element)
                    else:
                        # 使用isin方法判断df1['column_name']中的值是否在df2['column_name']中出现
                        mask = ~stocks_df['代码'].isin(g_vars.stocks_hist_df['symbol'])

                        # 通过布尔索引获取df1中在df2中不存在的值
                        result = stocks_df[mask]['代码'].tolist()
                        # 将列表中的每个元素依次放入队列
                        for element in result:
                            g_vars.get_hist_queue.put(element)

                    time.sleep(config.INTERVAL_GET_HOT_BOARDS)
            

#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ MAIN $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$#
#                                                     MAIN                                         #
#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ MAIN $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$#
class ThreadSafeTable:
    def __init__(self):
        self.lock = Lock()
        
    def update_safely(self, func):
        with self.lock:
            return func()

class Logger:
    def __init__(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('stock_selector.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger()
    
    def info(self, msg):
        self.logger.info(msg)
    
    def error(self, msg):
        self.logger.error(msg)

logger = Logger()

class WeChatNotifier:
    def __init__(self):
        self.webhook_url = None
        self.load_config()
    
    def load_config(self):
        try:
            with open('notify_config.json', 'r', encoding='utf-8-sig') as f:
                try:
                    config = json.load(f)
                    self.webhook_url = config.get('webhook_url', '')
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析错误: {str(e)}")
        except FileNotFoundError:
            logger.error("未找到企业微信配置文件 notify_config.json")
        except Exception as e:
            logger.error(f"读取配置文件时发生错误: {str(e)}")
    
    def send_message(self, message):
        if not self.webhook_url:
            logger.error("未配置企业微信webhook地址")
            return False
            
        data = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }
        
        try:
            response = requests.post(self.webhook_url, json=data)
            result = response.json()
            
            if result.get('errcode') == 0:
                return True
            else:
                logger.error(f"发送企业微信消息失败: {result}")
                return False
        except Exception as e:
            logger.error(f"发送企业微信消息异常: {str(e)}")
            return False

class ServerChanNotifier:
    def __init__(self):
        self.send_keys = []
        self.load_config()
    
    def load_config(self):
        try:
            with open('notify_config.json', 'r', encoding='utf-8-sig') as f:
                try:
                    config = json.load(f)
                    # 支持字符串（单个key）或列表（多个key）
                    send_keys = config.get('server_chan_keys', [])
                    if isinstance(send_keys, str):
                        self.send_keys = [send_keys]
                    elif isinstance(send_keys, list):
                        self.send_keys = send_keys
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析错误: {str(e)}")
        except FileNotFoundError:
            logger.error("未找到配置文件 notify_config.json")
        except Exception as e:
            logger.error(f"读取配置文件时发生错误: {str(e)}")
    
    def send_message(self, title, message):
        if not self.send_keys:
            logger.error("未配置Server酱SendKey")
            return False
        
        success = True
        for send_key in self.send_keys:
            if not send_key:  # 跳过空的SendKey
                continue
                
            url = f"https://sctapi.ftqq.com/{send_key}.send"
            data = {
                "title": title,
                "desp": message
            }
            
            try:
                response = requests.post(url, data=data)
                result = response.json()
                
                if result.get('code') == 0:
                    logger.info(f"Server酱消息发送成功: {send_key}")
                else:
                    logger.error(f"发送Server酱消息失败 [{send_key}]: {result}")
                    success = False
            except Exception as e:
                logger.error(f"发送Server酱消息异常 [{send_key}]: {str(e)}")
                success = False
        
        return success

class NotificationManager:
    def __init__(self):
        self.wechat = WeChatNotifier()
        self.server_chan = ServerChanNotifier()
    
    def send_notification(self, title, message):
        # 发送企业微信通知
        self.wechat.send_message(message)
        
        # 发送Server酱通知
        self.server_chan.send_message(title, message)

class Main(QWidget, Ui_Dialog):
    def __init__(self, parent=None):
        super(Main, self).__init__(parent)
        self.setupUi(self)
        #设置按钮
        self.pushButton.clicked.connect(self.butt_clear_result) #清空选股数据
        self.pushButton_2.clicked.connect(self.butt_export_result) #导出选股列表
        self.pushButton_3.clicked.connect(self.butt_show_graphic) #显示所选股票的K线图
        self.pushButton_5.clicked.connect(self.close) #退出程序
        self.pushButton_6.clicked.connect(self.butt_stop_start) #暂停和重启选股
        #设置表格
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers) #设置表格不允许编辑
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows) # 设置双击模式为选中项（如果需要）
        self.tableWidget.cellDoubleClicked.connect(self.handle_double_click) # 连接doubleClicked信号到处理函数

        #启动两个子进程，分别定期获取当前的热门行业板块和概念板块及其股票
        self.board_thread_industry = refresh_board_thread("industry")
        self.board_thread_concept = refresh_board_thread("concept")
        #启动子进程，获取所有股票的实时数据
        self.get_stock_realtime_thread = get_stock_realtime_thread()
        self.connect_signals()
        self.board_thread_industry.start()
        self.board_thread_concept.start()        
        self.get_stock_realtime_thread.start()
        #启动子进程，获取热门板块股票的历史数据（截止到上一交易日的数据）
        self.get_stock_hist = get_stock_hist_thread()
        self.get_stock_hist.start()

        self.rt_df = pd.DataFrame()
        self.last_time = datetime.now()
        self.label_additonal_message = ""
        self.is_handling_table = False

        self.table_lock = ThreadSafeTable()

        filename = "selected_" + datetime.today().strftime('%Y-%m-%d').replace("-", "_") + ".csv"
        current_dir = os.getcwd()  # 获取当前工作目录
        filepath = os.path.join(current_dir, filename)
        print(filepath)
        if os.path.exists(filepath):
            reply = QMessageBox.question(self, '提示',
                                     "是否导入今天已选出的股票信息?",
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
            if reply == QMessageBox.Yes:
                df = pd.read_csv(filepath)
                df["代码"] = df["代码"].astype(str).str.zfill(6)
                row_count = self.tableWidget.rowCount()     
                if row_count == 0:#设置表头
                    self.tableWidget.setRowCount(df.shape[0])
                    self.tableWidget.setColumnCount(df.shape[1])
                    horizontal_headers = list(df.columns)
                    self.tableWidget.setHorizontalHeaderLabels(horizontal_headers)

                    # 将DataFrame的数据填充到QTableWidget中
                    for row in range(df.shape[0]):
                        for col in range(df.shape[1]):
                            item_value = df.iloc[row, col]
                            item = QTableWidgetItem(str(item_value))
                            self.tableWidget.setItem(row, col, item)
        
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_label)
        self.timer.start()

        # 初始化企业微信通知器
        self.wechat_notifier = WeChatNotifier()

        # 初始化通知管理器
        self.notifier = NotificationManager()

    def update_label(self):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.label.setText(f"今日选股：{current_time} {self.label_additonal_message}")

    def check_board(self, table):
        # 使用批量处理替代逐行处理
        symbols = []
        for row in range(table.rowCount()):
            item = table.item(row, 2) if table in (self.tableWidget_2, self.tableWidget_4) else table.item(row, 0)
            if item:
                symbol = item.text()
                rt_stock = self.rt_df[self.rt_df['代码'] == symbol]
                if rt_stock.empty:
                    table.setItem(row, 1, QTableWidgetItem("没有实时数据")) 
                    continue
                if g_vars.stocks_hist_df.empty:
                    continue
                hist_df = g_vars.stocks_hist_df[g_vars.stocks_hist_df['symbol'] == symbol]
                if hist_df.empty:
                    table.setItem(row, 1, QTableWidgetItem("没有历史数据")) 
                    continue
                result = check_stock_conditions(rt_stock, hist_df)
                #如果result以"符合"开头
                if result.startswith("符合"):
                    self.insert_t_selected(rt_stock, result)
                table.setItem(row, 1, QTableWidgetItem(result)) 

    def check_selected(self, table):
        row_count = table.rowCount()
        for row in range(row_count):
            item = table.item(row, 0)
            if item:
                symbol = item.text()
                rt_stock = self.rt_df[self.rt_df['代码'] == symbol]
                if rt_stock.empty:
                    #table.setItem(row, 1, QTableWidgetItem("没有实时数据")) 
                    continue
                if g_vars.stocks_hist_df.empty:
                    continue
                hist_df = g_vars.stocks_hist_df[g_vars.stocks_hist_df['symbol'] == symbol]
                if hist_df.empty:
                    #table.setItem(row, 1, QTableWidgetItem("没有历史数据")) 
                    continue
                result = check_stock_conditions(rt_stock, hist_df)
                self.insert_t_selected(rt_stock, result)
                
    def butt_clear_result(self):
        # 获取表格的行数
        row_count = self.tableWidget.rowCount()
        # 从最后一行开始删除，避免索引问题
        for row in range(row_count - 1, -1, -1):
            self.tableWidget.removeRow(row)

    def butt_stop_start(self):
        global g_vars
        if self.pushButton_6.text() == "暂停选股":
            self.pushButton_6.setText("继续选股")
            g_vars.suspend_selection = True
            self.pushButton_2.setText("导入")
            self.pushButton_3.setText("演算")
            
        elif self.pushButton_6.text() == "继续选股":
            self.pushButton_6.setText("暂停选股")
            g_vars.suspend_selection = False
            self.pushButton_2.setText("导出")
            self.pushButton_3.setText("看图")

    def butt_show_graphic(self):
        # 获取表格的行数和列数
        row_count = self.tableWidget.rowCount()
        if row_count == 0:
            QMessageBox.warning(self, '提示',
                                "尚无分析结果")
            return
        # 获取当前选中的行
        row = self.tableWidget.currentRow()
        if row < 0:
            QMessageBox.warning(self, '提示',
                                "请选择一行")
            return
        self.show_graphic(row)

    def handle_double_click(self, row, column):
        self.show_graphic(row)

    def show_graphic(self, row):
        symbol = self.tableWidget.item(row, 0).text()
        today = datetime.today()
        delta = timedelta(days = NDAYS_BEFORE_5)
        hundred_days_ago = today - delta
        startdate = hundred_days_ago.strftime('%Y%m%d')
        enddate = today.strftime('%Y%m%d')
        #从设置的起始日期，大致按照较大的中线值的2倍往前多取
        enough_start_days = int(MA2DAYS*2)
        delta = timedelta(days = NDAYS_BEFORE_5 + enough_start_days)
        enough_days_ago = today - delta
        enough_startdate = enough_days_ago.strftime('%Y%m%d')
        df = get_stock_hist(symbol, enough_startdate, enddate, "qfq") #图表展示时用前复权
        # 检查获取的 DataFrame 是否为空
        if df.empty:
            QMessageBox.warning(self, '提示', "未获取到数据")
        else:
            #处理代码数据，包括将日期列设为索引，计算布林带
            df = process_symbol_data(df, MA1DAYS, MA1MULTIPLES, MA2DAYS, MA2MULTIPLES, 5)
            # 截掉前面的数据
            date_obj = datetime.strptime(startdate, "%Y%m%d")
            startdate = date_obj.strftime("%Y-%m-%d")
            df = df.loc[df.index >= startdate]
            self.show_picture(symbol, df)

    def show_picture(self, symbol, df):
        # 定义 mplfinance 的自定义风格
        mc = mpf.make_marketcolors(up='r', down='g', volume='inherit')
        s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=mc, rc={'font.sans-serif': ['Microsoft YaHei']})

        # 添加布林带和MA5指标到 K 线图中
        ap = [mpf.make_addplot(df['ma_5'], panel=0, color='black', width=1, ylabel='MA(5)'),mpf.make_addplot(df['ma_1'], panel=0, color='orange', width=1, ylabel='MA(1)'),mpf.make_addplot(df['upper_band_1'], panel=0, color='blue', width=1, alpha=0.2),mpf.make_addplot(df['lower_band_1'], panel=0, color='blue', width=1, alpha=0.2),mpf.make_addplot(df['ma_2'], panel=0, color='black', width=1, ylabel='MA(2)'),mpf.make_addplot(df['upper_band_2'], panel=0, color='green', width=1, alpha=0.2),mpf.make_addplot(df['lower_band_2'], panel=0, color='green', width=1, alpha=0.2)]
        # 绘制 K 线图和布林带指标
        mpf.plot(df, type='candle', style=s,
            title=f"{symbol} K 线图",
            ylabel='价格',
            ylabel_lower='成交量',
            volume=True,
            #mav=(5),
            show_nontrading=False,
            #figratio=(16, 8), 
            #figscale=1.5, 
                addplot=ap)

    def butt_export_result(self):
        if self.pushButton_2.text() == "导出":
            #message = f"选股提醒：600XXX涨停"
            #self.wechat_notifier.send_message(message)
            self.export_result("")
        else:
            self.import_result()

    def import_csv(self, file_path):
        with open(file_path, 'rb') as file:
            rawdata = file.read()
            result = chardet.detect(rawdata)
            encoding = result['encoding']
        df = pd.read_csv(codecs.open(file_path, 'r', encoding=encoding))
        #print(df)
        return df

    def import_result(self):
        # 弹出文件选择对话框
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择CSV文件", "", "CSV files (*.csv)")
        
        if not filename:
            return
            
        try:
            # 读取CSV文件
            df = self.import_csv(filename)
            
            # 确保代码列格式正确(补齐6位)
            df["代码"] = df["代码"].astype(str).str.zfill(6)
            
            # 清空现有表格
            #self.tableWidget.setRowCount(0)
            
            # 设置表格的列
            row_count = self.tableWidget.rowCount()
            if row_count == 0:
                self.tableWidget.setColumnCount(len(df.columns))
                self.tableWidget.setHorizontalHeaderLabels(df.columns)
            
            # 填充数据
            for row_index, row in df.iterrows():
                self.tableWidget.insertRow(0)
                for col_index, value in enumerate(row):
                    item = QTableWidgetItem(str(value))
                    self.tableWidget.setItem(0, col_index, item)
                    
            QMessageBox.information(self, "完成", "导入选股列表成功")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入文件时出错:\n{str(e)}")

    def export_result(self, filename):
        # 获取表格的行数和列数
        row_count = self.tableWidget.rowCount()
        if row_count == 0:
            QMessageBox.warning(self, '提示',
                                "尚无分析结果")
            return

        row_count = self.tableWidget.rowCount()
        column_count = self.tableWidget.columnCount()

        # 提取表头
        headers = []
        for j in range(column_count):
            header_item = self.tableWidget.horizontalHeaderItem(j)
            if header_item:
                headers.append(header_item.text())

        # 提取表格数据
        table_data = []
        for i in range(row_count):
            row_data = []
            for j in range(column_count):
                item = self.tableWidget.item(i, j)
                if item:
                    row_data.append(item.text())
                else:
                    row_data.append("")
            table_data.append(row_data)

        # 使用pandas的DataFrame创建数据结构并导出到CSV
        df = pd.DataFrame(table_data, columns=headers)
        
        if filename == "":
            # 弹出文件选择对话框
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save CSV", "", "CSV files (*.csv)")
            if filename:
                df['代码'] = df['代码'].astype(str)
                #df.to_csv(filename, quoting=csv.QUOTE_ALL, index=False) #所有数据带引号
                df.to_csv(filename, index=False) #所有数据带引号
                QMessageBox.information(
                    self, "完成", "保存选股列表成功")
            else:
                QMessageBox.information(
                    self, "取消", "选股列表保存失败")
        else:
            df.to_csv(filename, index=False)
    
    def closeEvent(self, event):
        reply = QMessageBox.question(self, '提示',
                                     "是否要退出?",
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

    def connect_signals(self):
        self.board_thread_industry.update_t_board_signal.connect(self.update_t_board_slot)
        self.board_thread_concept.update_t_board_signal.connect(self.update_t_board_slot)
        self.get_stock_realtime_thread.got_stock_realtime_signal.connect(self.got_stock_realtime_slot)

    def update_t_board_slot(self, board, stocks_df):
        def update():
            if g_vars.suspend_selection == True:
                return
            if board == "industry":
                stocks_table = self.tableWidget_2
                label = self.label_2
                label_text = "热门行业板块："
            else:
                stocks_table = self.tableWidget_4
                label = self.label_4
                label_text = "热门概念板块："
            if stocks_table.columnCount() != len(stocks_df.columns): #设置表头
                stocks_table.setColumnCount(len(stocks_df.columns))
                horizontal_headers = list(stocks_df.columns)
                stocks_table.setHorizontalHeaderLabels(horizontal_headers)
            
            while self.is_handling_table:
                time.sleep(0.001)
            
            #删除历史数据
            row_count = stocks_table.rowCount()
            for row in range(row_count - 1, -1, -1): # 从最后一行开始删除，避免索引问题
                stocks_table.removeRow(row)
            
            symbols = []
            # 逐行逐列填充数据
            stocks_table.setRowCount(len(stocks_df))
            for row_index, row_data in stocks_df.iterrows():
                for col_index, cell_value in enumerate(row_data):
                    item = QTableWidgetItem(str(cell_value))
                    stocks_table.setItem(row_index, col_index, item)
                symbols.append(row_data['代码'])
            update_time = time.strftime("%H:%M:%S", time.localtime())
            label.setText(label_text + f"更新时间：{update_time}")
            
            self.is_updating_table = False
        self.table_lock.update_safely(update)

    def insert_t_selected(self, rt_df, result):
        rt_data = rt_df.copy()
        rt_data.drop('序号', axis = 1, inplace=True)
        rt_data['最新分析'] = result
        rt_data['上榜时间'] = datetime.now().strftime('%H:%M:%S')# 添加操作时间列
        rt_data['最新时间'] = datetime.now().strftime('%H:%M:%S')# 添加操作时间列
        rt_data['上榜价'] =  rt_data['最新价'].iloc[0]
        updownrate = rt_data['前涨跌幅'] =  rt_data['涨跌幅'].iloc[0]
        columns_order = rt_data.columns.tolist()
        columns_order.insert(2, columns_order.pop(columns_order.index('最新分析')))
        columns_order.insert(3, columns_order.pop(columns_order.index('上榜时间')))
        columns_order.insert(4, columns_order.pop(columns_order.index('最新时间')))
        columns_order.insert(5, columns_order.pop(columns_order.index('上榜价')))
        rt_data = rt_data[columns_order]
        symbol = rt_data['代码'].iloc[0]

        row_count = self.tableWidget.rowCount()
        
        if row_count == 0:#设置表头
            self.tableWidget.setRowCount(0)
            self.tableWidget.setColumnCount(len(rt_data.columns))
            horizontal_headers = list(rt_data.columns)
            self.tableWidget.setHorizontalHeaderLabels(horizontal_headers)
        
        first_time = ""
        first_price = ""
        #检查表格里是否已有该代码，有则先保存上榜时间，再删掉
        for i in range(row_count):
            item = self.tableWidget.item(i, 0)
            if item:
                if symbol == item.text():
                    first_time = self.tableWidget.takeItem(i, 3).text()
                    first_price = self.tableWidget.takeItem(i, 5).text()
                    # 删除第i行
                    self.tableWidget.removeRow(i)

        #将该记录插入到表格的第一行（如果之前有，则用之前的上榜时间）
        self.tableWidget.insertRow(0)
        # self.tableWidget.verticalScrollBar().setSliderPosition(0)
        for j in range(len(rt_data.columns)):
            item = QTableWidgetItem(str(rt_data.values[0][j]))
            if j == 3:
                if first_time != "":
                    item = QTableWidgetItem(first_time)
            if j == 5:
                if first_price != "":
                    item = QTableWidgetItem(first_price)
            self.tableWidget.setItem(0, j, item)
        if first_time == "": #说明是新增加的，这时做一下保存到csv的操作        
            notification.notify('提醒',f'{symbol}有新动向','蚂蚁选股','ant.ico',2)
            
            #如果当前时间大于等于9:30，则发送通知
            if datetime.now().hour >= 9 and datetime.now().minute >= 30:
                # 构建通知消息
                title = f"蚂蚁选股提醒：{symbol}有新动向"
                message = f"股票：{symbol}\n"
                message += f"最新价: {rt_data['最新价'].iloc[0]}\n"
                message += f"涨跌幅: {rt_data['涨跌幅'].iloc[0]}%\n"
                message += f"分析结果: {result}"
                message += f"龙虎榜数据：{get_longhubang_data(symbol)}"
                # 发送所有通知
                self.notifier.send_notification(title, message)
            
            print(f"{symbol}涨幅{rt_data['涨跌幅'].iloc[0]}")
            filename = "selected_" + datetime.today().strftime('%Y-%m-%d').replace("-", "_") + ".csv"
            self.export_result(filename)

    def got_stock_realtime_slot(self):
        self.rt_df = g_vars.stocks_realtime_df.copy()

        if g_vars.suspend_selection == True:
            self.label_additonal_message = "暂停选股"
            return
        else:
            self.label_additonal_message = "开始选股"
        start_time = datetime.now()
        self.check_board(self.tableWidget_2)
        self.check_board(self.tableWidget_4)
        self.check_selected(self.tableWidget) #重新检查一遍已选股票列表，以保证已不在热门板块列表的股票的数据也能更新
        self.tableWidget.sortItems(3, 1) #按上榜时间排序
        
        end_time = datetime.now()
        elapsed_time = (end_time - start_time).total_seconds()
        duration_time = (start_time - self.last_time).total_seconds()
        self.last_time = start_time

        self.label_additonal_message = f"用时{elapsed_time:.4f} 秒，距上次{duration_time:.4f}秒"

    

class SafeDataFetcher:
    @staticmethod
    def fetch_with_retry(fetch_func, max_retries=3, delay=1):
        for attempt in range(max_retries):
            try:
                return fetch_func()
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Failed after {max_retries} attempts: {str(e)}")
                    return pd.DataFrame()
                time.sleep(delay)
        return pd.DataFrame()

    @staticmethod
    def get_stock_hist(symbol, startdate, enddate, adjust):
        return SafeDataFetcher.fetch_with_retry(
            lambda: ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                     start_date=startdate, end_date=enddate, adjust=adjust)
        )

# 主程序入口
if __name__ == "__main__":
    app = QApplication(sys.argv)
    Main = Main()
    Main.show()
    sys.exit(app.exec())
