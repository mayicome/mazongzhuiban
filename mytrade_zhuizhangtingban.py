#coding:utf-8
import time, sys
import queue
from xtquant import xtdata, xtconstant
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
import threading
import pandas as pd
import akshare as ak
from datetime import timedelta, datetime
import conditions
import numpy as np
import os
from market_data import my_market
import requests
import psutil
import json
from chncal import *

xtdata.enable_hello = False  # 添加此行以隐藏欢迎消息

# 检查程序是否有更新
def check_update():
    try:
        # 读取本地版本（从update.json）
        with open('update.json', 'r', encoding='utf-8') as f:
            local_data = json.load(f)
            current_version = tuple(map(int, local_data['version'].split('.')))
        
        # 获取远程版本
        update_url = "https://raw.githubusercontent.com/mayicome/mazongzhuiban/main/update.json"
        response = requests.get(update_url, timeout=5)
        remote_data = response.json()
        latest_version = tuple(map(int, remote_data['version'].split('.')))
        
        has_update = latest_version > current_version
        return has_update, remote_data['version'], remote_data['changelog']
    except Exception as e:
        return False, "", ""

# 读取今日已买入股票列表
def read_bought_list_from_file():
    global A_bought_list
    global hot_industry_list
    global hot_concept_list
    try:
        # 获取今天的日期作为文件名
        today = datetime.now().strftime('%Y%m%d')
        # 构建文件路径
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(data_dir, exist_ok=True)
        filename = os.path.join(data_dir, f'bought_list_{today}.txt')
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        # 将字符串转换为字典
                        bought_info = eval(line.strip())
                        if bought_info and isinstance(bought_info, dict) and bought_info not in A_bought_list:
                            A_bought_list.append(bought_info)
                    except Exception as e:
                        logger.error(f"解析买入记录时出错: {e}, 记录内容: {line.strip()}")
                        continue
                        
            logger.info(f"已从文件 {filename} 读取今日已买列表，列表长度为: {len(A_bought_list)}")
        else:
            logger.info(f"未读取到今日已买列表")
    except Exception as e:
        logger.error(f"读取买入列表文件时出错: {e}")

    try:
        last_day = datetime.now() - timedelta(days=1)
        while not is_tradeday(last_day):
            last_day = last_day - timedelta(days=1)
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        filename = os.path.join(data_dir, f'hot_industry_{last_day.strftime("%Y%m%d")}.csv')
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            # 读取df的前三个板块名称
            hot_industry_list = df['板块名称'].head(3).tolist()
        filename = os.path.join(data_dir, f'hot_concept_{last_day.strftime("%Y%m%d")}.csv')
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            # 读取df的前三个板块名称
            hot_concept_list = df['板块名称'].head(3).tolist()
    except Exception as e:
        logger.error(f"读取热门行业和概念板块文件时出错: {e}")

def write_bought_list_to_file():
    try:
        today = datetime.now().strftime('%Y%m%d')
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        filename = os.path.join(data_dir, f'bought_list_{today}.txt')
        with open(filename, 'w', encoding='utf-8') as f:
            for bought_info in A_bought_list:
                if isinstance(bought_info, dict):
                    f.write(f'{repr(bought_info)}\n')
    except Exception as e: 
        logger.error(f"写入买入列表文件时出错: {e}")

def interact():
    """执行后进入repl模式"""
    import code
    code.InteractiveConsole(locals=globals()).interact()

def symbol2stock(symbol):
    """
    将股票代码转换为QMT识别的格式
    Args:
        symbol (str): 原始股票代码（例如：000001、600001等）
    Returns:
        str: QMT格式的股票代码（例如：000001.SZ、600001.SH等）
    """
    symbol = symbol.strip()
    
    if '.SZ' in symbol or '.SH' in symbol or '.BJ' in symbol:
        return symbol
        
    symbol = symbol.zfill(6)
    
    if symbol.startswith(('0', '3')):
        return f"{symbol}.SZ"  # 深交所
    elif symbol.startswith('6'):
        return f"{symbol}.SH"  # 上交所
    elif symbol.startswith(('4', '8')):
        return f"{symbol}.BJ"  # 北交所
    else:
        raise ValueError(f"无效的股票代码: {symbol}")
    
#获取某支股票的历史数据
def get_stock_hist(symbol, startdate, enddate, adjust, max_retries=3):
    stock = symbol2stock(symbol)

    period = "1d"

    # 获取历史行情数据
    code_list = [stock]  # 定义要下载和订阅的股票代码列表
    count = -1  # 设置count参数，使gmd_ex返回全部数据

    # 下载历史数据
    xtdata.download_history_data(stock, period, startdate, enddate)
    
    # 获取历史行情数据
    df = xtdata.get_market_data_ex([], code_list, period=period, 
                                start_time=startdate, 
                                end_time=enddate, 
                                count=count)            
    
    if stock in df and len(df[stock]) > 0:
        data = pd.DataFrame(df[stock])
        data['股票代码'] = symbol        
        data['日期'] = pd.to_datetime(data.index)
        data = data.reset_index(drop=True)
        
        # 重命名列
        data = data.rename(columns={
            'close': '收盘',
            'high': '最高',
            'open': '开盘',
            'low': '最低'
        })
        
        # 计算涨跌幅 (避免使用inplace),注释：这里采用当天的最高价计算涨跌幅，而不是收盘价，相当于是最大涨跌幅
        data['涨跌幅'] = (data['最高'] / data['收盘'].shift(1) - 1) * 100
        # 替换 fillna(inplace=True) 的写法
        data['涨跌幅'] = data['涨跌幅'].fillna(0)
        data['涨跌幅'] = data['涨跌幅'].round(2)
        
        # 计算涨跌额
        data['涨跌额'] = (data['最高'] - data['收盘'].shift(1)).round(2)
        data['涨跌额'] = data['涨跌额'].fillna(0)
        return data
    else:
        logger.error(f"获取股票{symbol}历史数据失败")
        return None

    #----------------------------------------------------------------
    # 原来用akshare的东方财富接口获取股票历史数据
    df = pd.DataFrame()
    retry_count = 0
    while retry_count < max_retries:
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                  start_date=startdate, end_date=enddate, adjust=adjust)
            if not df.empty:
                break
        except Exception as e:
            retry_count += 1
            logger.warning(f"获取股票{symbol}历史数据第{retry_count}次重试失败: {e}")
            time.sleep(1)  # 重试前等待
    if df.empty:
        logger.error(f"获取股票{symbol}历史数据失败,已重试{max_retries}次")
    return df

#获取热门行业板块
def get_board_industry_name():
    df = pd.DataFrame()        
    try:
        df = ak.stock_board_industry_name_em()
    except Exception as e:
        logger.error(f"获取热门板块数据时出错，错误信息：{e}")
    return df

#获取某个行业板块的所有股票
def get_board_industry_cons(sector):
    return my_market.get_board_industry_cons(sector)

#获取热门概念板块
def get_board_concept_name():
    df = pd.DataFrame()        
    try:
        df = ak.stock_board_concept_name_em()
    except Exception as e:
        logger.error(f"获取热门板块数据时出错，错误信息：{e}")
    return df

#获取某个概念板块的所有股票
def get_board_concept_cons(sector):
    return my_market.get_board_concept_cons(sector)

# 计算布林带指标
def calculate_bollinger_bands(df, n, k):
    # data: 输入的价格数据，如收盘价、开盘价等
    # n: 移动平均线的时间周期
    # k: 布林带的宽度倍数
    ma = df.rolling(n).mean()
    std = df.rolling(n).std()
    upper_band = ma + k * std
    lower_band = ma - k * std
    return round(ma, 2), round(upper_band, 2), round(lower_band, 2)

#判断是否是涨停板
def is_limit_up(symbol, price):
    if symbol[:2] in ("00", "60"):
        MAX_UPRATE = 9.9
    else:
        MAX_UPRATE = 19.9
    if price >= MAX_UPRATE:
        return True
    return False

# 检查价格趋势
def check_price_trend(recent_df):
    # 数据有效性检查
    if len(recent_df) < 2 or recent_df['收盘'].nunique() == 1:
        return 'N', 0.0, 0.0
    
    x = np.arange(len(recent_df))
    y = recent_df['收盘'].values
    
    try:
        # 线性拟合（一次多项式）
        linear_coeffs = np.polyfit(x, y, 1)
        linear_fit = np.poly1d(linear_coeffs)
        
        # 计算线性拟合的 R²
        y_linear = linear_fit(x)
        r2_linear = 1 - np.sum((y - y_linear) ** 2) / np.sum((y - np.mean(y)) ** 2)
        
        # 如果线性拟合度不够好（比如R²小于0.8），尝试二次多项式拟合
        if r2_linear < 0.8 and len(recent_df) >= 3:
            # 二次多项式拟合
            quad_coeffs = np.polyfit(x, y, 2)
            quad_fit = np.poly1d(quad_coeffs)
            
            # 计算二次拟合的 R²
            y_quad = quad_fit(x)
            r2_quad = 1 - np.sum((y - y_quad) ** 2) / np.sum((y - np.mean(y)) ** 2)
            
            # 返回二次拟合结果
            a, b, c = quad_coeffs
            if a > 0:
                return 'U', round(r2_quad, 2), round(a, 2)
            else:
                return 'N', round(r2_quad, 2), round(a, 2)
        else:
            # 返回线性拟合结果
            slope = linear_coeffs[0]
            return 'L', round(r2_linear, 2), round(slope, 2)
    except np.linalg.LinAlgError:
        logger.warning("多项式拟合失败，返回默认值")
        return 'N', 0.0, 0.0

#价格变化率(p1比p2增减的比例)
def price_increase_rate(p1, p2):
    rate = float(p1-p2)/p2*100
    return round(rate, 2)

#成交量变化率(v1比v2增减的比例)
def volume_increase_rate(v1, v2):
    rate = float(v1-v2)/v2*100
    return round(rate, 2)

#获取某支股票的龙虎榜数据
def get_lhb_data(stock_code):
    try:
        count = 0
        # 获取当前日期
        today = datetime.today()
        # 获取两个月前的日期
        two_month_ago = today - timedelta(days=60)  # 使用固定的60天
        
        # 获取龙虎榜数据 - 修改参数名从 symbol 为 stock
        #df = ak.stock_lhb_detail_em(stock=stock_code)
        df = ak.stock_lhb_stock_detail_date_em(symbol=stock_code)
        if df.empty:
            return "\n该股票没有龙虎榜数据", count
            
        # 转换日期列
        df['交易日'] = pd.to_datetime(df['交易日'])

        # 筛选最近两个月的数据
        df = df[df['交易日'] >= two_month_ago]
        
        message = ""
        if len(df) == 0:
            message += "\n该股票最近两个月没有龙虎榜数据"
        else:
            count = len(df)
            message += f"\n该股票最近两个月有{count}天有龙虎榜数据，最近的数据详情如下：\n"
            if count > 2:
                df = df.head(2)  # 只显示最近两条记录
            
            # 遍历df中的每个交易日
            for index, row in df.iterrows():
                trade_date = row['交易日'].strftime('%Y%m%d')
                message += f"{trade_date}的龙虎榜买入数据:\n"
                # 同样修改这里的参数名
                lhb_detail = ak.stock_lhb_stock_detail_em(symbol=stock_code, date=trade_date, flag="买入")
                message += f"{lhb_detail}\n"
                message += f"{trade_date}的龙虎榜卖出数据:\n"
                # 同样修改这里的参数名
                lhb_detail = ak.stock_lhb_stock_detail_em(symbol=stock_code, date=trade_date, flag="卖出")
                message += f"{lhb_detail}\n"
                
        return message, count
    except Exception as e:
        logger.error(f"获取龙虎榜数据时出错：{e}")
        return f"获取龙虎榜数据时出错：{e}", 0
    
# 撤单
def my_cancel_order_stock(acc, seq):
    try:
        result = xt_trader.cancel_order_stock(acc, seq)
        if result == 0: #成功            
            try:
                for bought_info in A_bought_list[:]: # 使用切片创建副本进行遍历
                    if bought_info.get('seq') == seq:
                        logger.info(f"股票{bought_info.get('stock')}订单号{seq}的定时撤单任务已执行。")
            except Exception as e:
                logger.error(f"撤单时处理A_bought_list文件时出错: {e}")
            try:
                # 更新selected_df中委托失败订单的下单状态
                if my_market.selected_df is not None and not my_market.selected_df.empty:
                    mask = my_market.selected_df['seq'] == seq
                    if mask.any():
                        my_market.selected_df.loc[mask, '下单状态'] = f"已撤单"
                        logger.info(f"已更新selected_df中已撤单订单的下单状态: {seq}")
            except Exception as e:
                logger.error(f"撤单时处理selected_df文件时出错: {e}")

    except Exception as e:
        logger.error(f"撤单失败,订单号:{seq},错误信息:{e}")

# 发送微信通知给所有配置的用户
def send_wechat_notification(title, message):
    if not my_market.server_chan_keys:
        logger.warning("未配置Server酱密钥，无法发送微信通知")
        return

    # 记录未能发送成功的通知
    failed_notifications = []
    
    # 给每个用户都发送通知
    for server_chan_key in my_market.server_chan_keys:
        try:
            server_chan_url = f"https://sctapi.ftqq.com/{server_chan_key}.send"
            data = {
                "title": title,
                "desp": message
            }
            response = requests.post(server_chan_url, data=data)
            response_json = response.json()
            
            if response.status_code == 200:
                if response_json.get("code") == 0:  # 发送成功
                    logger.info(f"Server酱消息发送成功: {title}")
                elif response_json.get("code") == 40001:  # 超过发送限制
                    logger.warning(f"Server酱密钥 {server_chan_key} 已达到今日发送限制")
                    failed_notifications.append((server_chan_key, "达到发送限制"))
                else:
                    logger.error(f"Server酱消息发送失败: {response.text}")
                    failed_notifications.append((server_chan_key, response.text))
            else:
                logger.error(f"Server酱消息发送失败，HTTP状态码: {response.status_code}")
                failed_notifications.append((server_chan_key, f"HTTP错误: {response.status_code}"))
                
        except Exception as e:
            logger.error(f"发送微信通知时出错: {e}")
            failed_notifications.append((server_chan_key, str(e)))
    
    # 如果有发送失败的通知，记录到文件
    if failed_notifications:
        try:
            data_dir = os.path.join(os.path.dirname(__file__), 'data')
            os.makedirs(data_dir, exist_ok=True)
            filename = os.path.join(data_dir, f'failed_notifications_{datetime.now().strftime("%Y%m%d")}.txt')
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"标题: {title}\n")
                f.write(f"内容: {message}\n")
                f.write("发送失败的密钥及原因:\n")
                for key, reason in failed_notifications:
                    f.write(f"- 密钥: {key}, 原因: {reason}\n")
                f.write("-" * 50 + "\n")
            logger.info(f"发送失败的通知已记录到文件: {filename}")
        except Exception as e:
            logger.error(f"记录发送失败的通知时出错: {e}")

def subscribe_whole_quote_call_back(data):
    """行情订阅回调"""
    global g_watch_list
    global A_selected_list
    global A_bought_list
    global STOCK_NUMBERS_BOUGHT_IN_TODAY
    global last_trading_heartbeat
    
    for stock in data:
        #更新心跳包
        last_trading_heartbeat = time.time()#datetime.now()

        first_time = False
        seq =  0
        symbol = stock.split('.')[0]  #例如：stock: 601665.SH symbol: 601665            
        
        # 检查股票代码是否在data字典中
        if stock not in data:
            logger.warning(f"股票 {stock} 不在行情数据中")
            continue
            
        stock_data = data[stock]
        if not isinstance(stock_data, dict):
            logger.error(f"股票 {stock} 的数据格式错误: {stock_data}")
            continue
        
        last_price = round(stock_data.get('lastPrice', 0), 2)
        last_close = round(stock_data.get('lastClose', 0), 2)
        
        if not last_price or not last_close:
            logger.warning(f"股票 {symbol} 缺少价格数据: last_price={last_price}, last_close={last_close}")
            continue
        
        updownrate = price_increase_rate(last_price, last_close)
        
        # 使用 my_market 中的配置
        if updownrate >= my_market.THRESHOLD_CUR_UPDOWNRATE_10PCT:
            if symbol not in g_watch_list:
                g_watch_list.append(symbol)
            
        order_status = "未下单"
        # 检查当前时间是否大于等于9:30
        now = datetime.now()        
        current_time = now.strftime("%H:%M:%S")
        if current_time < "09:30:00":
            continue
        
        selected = False
        result = ""
        
        hist_df = g_stocks_hist_df[g_stocks_hist_df['股票代码'] == symbol]        
        if hist_df.empty:
            result = "未获取到历史数据"
        else:
            # 将hist_df转换为字典格式（只取第一行）
            hist_dict = hist_df.iloc[0].to_dict()
            selected, result = conditions.check_stock_conditions(symbol, updownrate, last_price, hist_dict)
        
        if selected:                    
            # 下单买入
        
            #检查stock是否在A_selected_list中
            if symbol not in A_selected_list:
                A_selected_list.append(symbol)
                first_time = True

            if any(stock == bought_info['stock'] for bought_info in A_bought_list):
                order_status = "已下过单且未被撤销"
            elif STOCK_NUMBERS_BOUGHT_IN_TODAY >= my_market.MAX_STOCKS_PER_DAY:
                logger.info(f"今天已买入成交股票支数{STOCK_NUMBERS_BOUGHT_IN_TODAY}达到最大买入股票支数限制{my_market.MAX_STOCKS_PER_DAY}，未买入 {stock}")
                order_status = "今天已买入成交股票支数已达最大买入股票支数限制，未买入"
            else:
                # 计算可买数量,按100股为单位
                max_cash = min(my_market.SINGLE_BUY_AMOUNT, my_market.asset.cash)
                if max_cash < 5000:
                    logger.info(f"{now} 可用资金不足5000元，{stock}未下单")
                    order_status = "可用资金不足5000元，未下单"
                else:
                    # 计算涨停板价格                    
                    if stock.startswith('83'):
                        # 北交所涨跌幅限制为30%
                        limit_up_price = round(last_close * 1.3, 2)
                    elif stock.startswith('688') or stock.startswith('30'):
                        # 科创板和创业板涨跌幅限制为20%
                        limit_up_price = round(last_close * 1.2, 2)
                    elif stock.startswith('00') or stock.startswith('60'):
                        # 其他板块涨跌幅限制为10%
                        limit_up_price = round(last_close * 1.1, 2)
                    else:
                        logger.info(f"股票代码{stock}不属于沪深A股，未下单")
                        order_status = "股票代码不属于沪深A股，未下单"
                    #计算可以买多少股
                    max_buy_amount = int(max_cash / limit_up_price)
                    buy_amount = max_buy_amount // 100 * 100
                    if buy_amount >= 100:                                        
                        try:
                            seq = xt_trader.order_stock(
                                acc, 
                                stock, 
                                xtconstant.STOCK_BUY, 
                                buy_amount, 
                                xtconstant.LATEST_PRICE, 
                                -1,
                                STRATEGY_NAME, 
                                stock
                            )
                            
                            if seq < 0:
                                logger.error(f"下单买入{stock}失败，账号：{acc}，股票代码：{stock}，数量：{buy_amount}，市价单，可用资金：{my_market.asset.cash}，错误码: {seq}")
                                order_status = f"下单失败，错误码: {seq}"
                            else:
                                order_status = f"已下单买入{buy_amount}股,最新价{last_price},买入方式：市价单"
                                logger.info(f"{now} 已下单买入 {stock} {buy_amount}股,最新价{last_price},买入方式：市价单, 可用资金：{my_market.asset.cash}, 订单号={seq}")
                                # 将股票代码、时间、买入数量、价格、订单号一起记录
                                A_bought_list.append({
                                    'stock': stock,
                                    'time': now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                                    'amount': buy_amount, 
                                    'price': last_price,
                                    'seq': seq
                                })                                        
                                logger.info(f"stock: {stock}; A_bought_list: {A_bought_list}")                                
                                # 将已买入股票列表写入以当日日期命名的文件
                                write_bought_list_to_file()
                                # 创建定时撤单任务
                                try:
                                    if my_market.CANCEL_ORDER_SECONDS > 0:
                                        # 使用threading.Timer创建定时任务,指定秒数后执行撤单
                                        timer = threading.Timer(my_market.CANCEL_ORDER_SECONDS, my_cancel_order_stock, args=(acc, seq))
                                        timer.start()
                                        logger.info(f"已创建买入{stock}的定时撤单任务,订单号:{seq},将在{my_market.CANCEL_ORDER_SECONDS}秒后执行")
                                        order_status += f",将在{my_market.CANCEL_ORDER_SECONDS}秒后撤单"
                                except Exception as e:
                                    logger.error(f"订单号{seq}创建定时撤单任务时出错: {e}")
                        except Exception as e:
                            logger.error(f"执行下单操作时出错: {e}")
                            order_status = f"下单失败，错误码: {e}"
                    else:
                        logger.info(f"可用资金不够买入100股，{stock}未下单")
                        order_status = f"可用资金不够买入100股，未下单"
            
        # 更新行业板块数据
        try:
            if my_market.industry_df is not None and not my_market.industry_df.empty:
                mask = my_market.industry_df['代码'] == symbol
                if mask.any():
                    try:
                        if '分析结果' not in my_market.industry_df.columns:
                            my_market.industry_df['分析结果'] = ""
                        my_market.industry_df.loc[mask, '分析结果'] = result
                        my_market.industry_df.loc[mask, '最新价'] = last_price
                        my_market.industry_df.loc[mask, '涨跌幅'] = updownrate
                        logger.debug(f"Updated industry analysis result for {symbol}")
                    except Exception as e:
                        logger.error(f"Error updating industry analysis result for {symbol}: {e}")
                my_market.update_market_data(industry_df=my_market.industry_df)
        except Exception as e:
            logger.error(f"Error processing industry data for {symbol}: {e}")
                    
        # 更新概念板块数据
        try:
            if my_market.concept_df is not None and not my_market.concept_df.empty:
                mask = my_market.concept_df['代码'] == symbol
                if mask.any():
                    try:
                        if '分析结果' not in my_market.concept_df.columns:
                            my_market.concept_df['分析结果'] = ""
                        my_market.concept_df.loc[mask, '分析结果'] = result
                        my_market.concept_df.loc[mask, '最新价'] = last_price
                        my_market.concept_df.loc[mask, '涨跌幅'] = updownrate
                        logger.debug(f"Updated concept analysis result for {symbol}")
                    except Exception as e:
                        logger.error(f"Error updating concept analysis result for {symbol}: {e}")
                my_market.update_market_data(concept_df=my_market.concept_df)
        except Exception as e:
            logger.error(f"Error processing concept data for {symbol}: {e}")
                            
        if selected:
            if my_market.selected_df is not None and not my_market.selected_df.empty and symbol in my_market.selected_df['代码'].values:
                # 更新已选股票的下单状态
                my_market.selected_df.loc[my_market.selected_df['代码'] == symbol, '下单状态'] = order_status
                my_market.selected_df.loc[my_market.selected_df['代码'] == symbol, 'seq'] = seq

            else:                        
                # 创建新的 DataFrame
                board_type = ""
                if my_market.industry_df is not None and not my_market.industry_df.empty and symbol in my_market.industry_df['代码'].values:
                    board_type = "热门行业"                                
                    selected_stock_info = my_market.industry_df.loc[my_market.industry_df['代码'] == symbol].copy()
                    if len(selected_stock_info) > 1:
                        selected_stock_info = selected_stock_info.iloc[[0]].copy()
                if my_market.concept_df is not None and not my_market.concept_df.empty and symbol in my_market.concept_df['代码'].values:
                    if board_type == "":
                        board_type = "热门概念"

                        selected_stock_info = my_market.concept_df.loc[my_market.concept_df['代码'] == symbol].copy()
                        if len(selected_stock_info) > 1:
                            selected_stock_info = selected_stock_info.iloc[[0]].copy()
                    else:
                        board_type = "热门行业&热门概念"
                        selected_stock_info_2 = my_market.concept_df.loc[my_market.concept_df['代码'] == symbol].copy()
                        if selected_stock_info['分析结果'].values == "":
                            selected_stock_info['分析结果'] = selected_stock_info_2['分析结果'].copy()
                if selected_stock_info is not None and not selected_stock_info.empty:
                    # 添加上榜时间和板块类别
                    selected_stock_info.loc[:, '上榜时间'] = now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    selected_stock_info.loc[:, '板块类别'] = board_type
                    selected_stock_info.loc[:, '下单状态'] = order_status
                    selected_stock_info.loc[:, 'seq'] = seq
                    lhb_message, count = get_lhb_data(symbol)
                    selected_stock_info.loc[:, '龙虎榜天数'] = count
                    # 重新排列列顺序
                    cols = selected_stock_info.columns.tolist()
                    # 移动板块类别到第一列
                    cols.remove('板块类别')
                    cols = ['板块类别'] + cols
                    # 移动上榜时间到第六列
                    cols.remove('上榜时间')
                    cols.insert(5, '上榜时间')
                    cols.remove('下单状态')
                    cols.insert(6, '下单状态')
                    selected_stock_info = selected_stock_info[cols]
                    my_market.update_market_data(selected_df=selected_stock_info)
                    
                    #首次上榜发送微信通知
                    if first_time:
                        title = f"蚂蚁选股提醒：{symbol}{selected_stock_info.iloc[0]['名称']}上榜"
                        message = f"{now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}最新价：{selected_stock_info.iloc[0]['最新价']}，涨跌幅：{selected_stock_info.iloc[0]['涨跌幅']}，分析结果：{selected_stock_info.iloc[0]['分析结果']}，龙虎榜天数：{selected_stock_info.iloc[0]['龙虎榜天数']}，{lhb_message}"
                        send_wechat_notification(title, message)
                else:                                
                    logger.error(f"selected_stock_info:{selected_stock_info}为空，股票{symbol}未上榜")

def get_max_updownrate(symbol): 
    """获取该股票的最大涨跌幅"""
    if symbol[:2] == '00' or symbol[:2] == '60':
        max_updownrate = "10PCT"
    elif symbol[:2] == '68' or symbol[:2] == '30':
        max_updownrate = "20PCT"
    else:
        max_updownrate = "30PCT"  
    if max_updownrate == "10PCT":
        threshold_updownrate = my_market.THRESHOLD_CUR_UPDOWNRATE_10PCT
        threshold_hist_updownrate = my_market.THRESHOLD_HIST_UPDOWNRATE_10PCT
    elif max_updownrate == "20PCT":
        threshold_updownrate = my_market.THRESHOLD_CUR_UPDOWNRATE_20PCT
        threshold_hist_updownrate = my_market.THRESHOLD_HIST_UPDOWNRATE_20PCT
    elif max_updownrate == "30PCT":
        threshold_updownrate = my_market.THRESHOLD_CUR_UPDOWNRATE_30PCT
        threshold_hist_updownrate = my_market.THRESHOLD_HIST_UPDOWNRATE_30PCT
    return threshold_updownrate, threshold_hist_updownrate

def get_stock_hist_thread():
    """获取股票历史数据线程"""
    global g_stocks_hist_df
    today = datetime.today()
    delta = timedelta(days = 1)
    yesterday = today - delta
    enddate = yesterday.strftime('%Y%m%d')
    end_date = datetime.strptime(enddate, '%Y%m%d') 
    start_date = end_date - timedelta(days=my_market.NDAYS_BEFORE_4*1.5+my_market.BOLL_DAYS*2) #确保有足够的均线数据
    startdate = start_date.strftime('%Y%m%d')

    while True:
        if not g_get_hist_queue.empty():
            #logger.info(f"获取历史数据列表长度: {g_get_hist_queue.qsize()}")
            symbol = g_get_hist_queue.get()
            #logger.info(f"要获取的股票代码: {symbol}")
            if g_stocks_hist_df.empty:
                result = False
            else:
                mask = g_stocks_hist_df['股票代码'].isin([symbol])
                result = mask.any()
            if not result:
                hist_df = get_stock_hist(symbol, startdate, enddate, "qfq")
                if not hist_df.empty and hist_df is not None:
                    # 将日期列设置为索引并转换为 datetime 类型
                    hist_df['日期'] = pd.to_datetime(hist_df['日期'])
                    hist_df.set_index('日期', inplace=True)
                    # 取最后一天的数据
                    last_df = hist_df.iloc[[-1]].copy()
                    threshold_updownrate, threshold_hist_updownrate = get_max_updownrate(symbol)
                    last_df['涨幅阈值'] = threshold_updownrate
                    last_df['历史涨幅阈值'] = threshold_hist_updownrate                    
                    # 计算最后一天的布林带指标
                    last_day_close = hist_df['收盘'].iloc[-my_market.BOLL_DAYS:]
                    last_day_boll = last_day_close.mean()
                    last_day_std = last_day_close.std()
                    last_day_upper = last_day_boll + my_market.BOLL_MULTIPLES * last_day_std
                    last_day_lower = last_day_boll - my_market.BOLL_MULTIPLES * last_day_std
                    last_df['布林中轨'] = round(last_day_boll, 2)
                    last_df['布林上轨'] = round(last_day_upper, 2)
                    last_df['布林下轨'] = round(last_day_lower, 2)
                    # 计算最后一天的MA_5均线
                    last_day_ma5 = hist_df['收盘'].iloc[-(my_market.MA_5):].mean()
                    last_df['5日均线'] = round(last_day_ma5, 2)
                    #检查近期的涨停板情况
                    recent_df = hist_df.tail(my_market.NDAYS_BEFORE_4)
                    last_df['涨停板观察天数'] = my_market.NDAYS_BEFORE_4
                    for idx in range(len(recent_df)-1, -1, -1):
                        row = recent_df.iloc[idx]
                        if is_limit_up(symbol, row['涨跌幅']):
                            last_df['涨停板观察期内最近涨停板到今天的交易日天数'] = idx
                            break
                    last_df['涨停板观察期内最近涨停板到今天的交易日天数'] = len(recent_df)-idx + 1
                    #检查近期的最高价
                    recent_df = hist_df.tail(my_market.NDAYS_BEFORE_3)
                    hist_high = recent_df['最高'].max()                    
                    for idx in range(len(recent_df)-1, -1, -1):
                        row = recent_df.iloc[idx]
                        if row['最高'] == hist_high:
                            max_index = idx
                            break
                    last_df['最高价观察天数'] = my_market.NDAYS_BEFORE_3
                    last_df['最高价观察期内最高价到今天的交易日天数'] = len(recent_df) - max_index + 1
                    last_df['最高价观察期内最高价'] = round(hist_high, 2)
                    #检查近期的趋势
                    recent_df = recent_df.tail(my_market.NDAYS_BEFORE_2)
                    pattern, r2, coeff = check_price_trend(recent_df)
                    #pattern =='linear':"线性趋势（斜率：{coeff:.4f}，R²：{r2:.4f}）"
                    #pattern == 'U': "U型趋势（二次项系数：{coeff:.4f}，R²：{r2:.4f}）"
                    #pattern == 'N': "N型趋势（二次项系数：{coeff:.4f}，R²：{r2:.4f}）"
                    last_df['趋势观察天数'] = my_market.NDAYS_BEFORE_2
                    last_df['趋势观察期内趋势模式'] = pattern
                    last_df['趋势观察期内趋势R²'] = r2
                    last_df['趋势观察期内趋势系数'] = coeff
                    #检查近期的最大涨幅
                    recent_df = hist_df.tail(my_market.NDAYS_BEFORE_1)
                    max_price = recent_df['涨跌幅'].max()
                    for idx in range(len(recent_df)-1, -1, -1):
                        row = recent_df.iloc[idx]
                        if row['涨跌幅'] == max_price:
                            max_index = idx
                            break
                    last_df['最大涨幅观察天数'] = my_market.NDAYS_BEFORE_1
                    last_df['最大涨幅观察期内最大涨幅距今天的交易日天数'] = len(recent_df) - max_index + 1
                    last_df['最大涨幅观察期内最大涨幅'] = max_price
                    #将last_df添加到g_stocks_hist_df中
                    g_stocks_hist_df = pd.concat([g_stocks_hist_df, last_df], axis=0, ignore_index=True)
                    # 统一到东方财经的格式
                    #东方财经
                    #股票代码	开盘	收盘	最高	最低	成交量	成交额	   振幅	   涨跌幅	涨跌额	换手率	涨幅阈值	历史涨幅阈值	布林中轨	       布林上轨	            布林下轨	        
                    # 5日均线	 涨停板观察天数 涨停板观察期内最近涨停板天数	最高价观察天数	最高价观察期内最近最高价天数	
                    # 最高价观察期内最近最高价	趋势观察天数	趋势观察期内趋势模式	趋势观察期内趋势R²	    趋势观察期内趋势系数	  最大涨幅观察天数	最大涨幅观察期内最大涨幅距今天数	最大涨幅观察期内最大涨幅
                    # 601665	   5.55	   5.78	   5.85	   5.54	  585887 336901070	5.63	4.9	    0.27	1.21	8.5	      4.5	         5.386500000000001	5.667346464891595	5.105653535108407	
                    # 5.5075	60           -1	                          40	         39	                           5.85	                     30
                    # 	            U	                  0.36646530505190134	6.008660416334252e-05	10	             9	                              4.9
                    #logger.info(f"获取{symbol}的历史数据成功，已添加到{g_stocks_hist_df}中")
                    #国金miniQMT
                    #open   high    low  close  volume        amount  settelementPrice  openInterest  preClose  suspendFlag                            日期
                    #0   39.87  40.78  39.15  39.56  579589  2.320677e+09               0.0            15     39.15            0 1970-01-01 00:00:00.020241108 
                else:
                    logger.warning(f"获取{symbol}的历史数据时出错，继续加入等待获取队列")
                    g_get_hist_queue.put(symbol)
        else:
            time.sleep(1)

# 刷新板块线程
def refresh_hot_board_thread(board):
    last_time = datetime.now()
    while True:
        if board == "industry":
            stock_board_name_em_df = get_board_industry_name()
            #保存到当天的文件
            stock_board_name_em_df.to_csv(f'data/hot_industry_{datetime.now().strftime("%Y%m%d")}.csv', index=False)
        else:
            stock_board_name_em_df = get_board_concept_name()
            #保存到当天的文件
            stock_board_name_em_df.to_csv(f'data/hot_concept_{datetime.now().strftime("%Y%m%d")}.csv', index=False)
        if stock_board_name_em_df.empty:
            time.sleep(1)
            continue
        else:
            top_boards = stock_board_name_em_df.head(my_market.TOP_N_BOARDS).copy()
            top_boards.drop('排名', axis = 1, inplace=True)
            top_boards['时间'] = datetime.now().strftime('%H:%M:%S')
            columns_order = top_boards.columns.tolist()
            columns_order.insert(1, columns_order.pop(columns_order.index('时间')))
            top_boards = top_boards[columns_order]
            
            stocks_df = pd.DataFrame()
            for row_index, row_data in top_boards.iterrows():
                sector = row_data['板块名称']
                if board == "industry":
                    if sector not in hot_industry_list:
                        stock_board_cons_em_df = get_board_industry_cons(sector)
                    else:
                        continue
                else:
                    if sector not in hot_concept_list:
                        stock_board_cons_em_df = get_board_concept_cons(sector)
                    else:
                        continue
                if stock_board_cons_em_df.empty:
                    time.sleep(1)
                    continue
                else:
                    top_stocks = stock_board_cons_em_df.head(my_market.TOP_N_STOCKS).copy()
                    condition = top_stocks['代码'].astype(str).str[:2].isin(["00","30","60"])
                    top_stocks = top_stocks[condition]
                    top_stocks['分析结果'] = ""
                    top_stocks['板块'] = sector
                    stocks_df = pd.concat([stocks_df, top_stocks], axis=0, ignore_index=True)
            if stocks_df is not None and not stocks_df.empty:            
                stocks_df.drop('序号', axis = 1, inplace=True)
                columns_order = stocks_df.columns.tolist()
                columns_order.insert(0, columns_order.pop(columns_order.index('板块')))
                columns_order.insert(5, columns_order.pop(columns_order.index('分析结果')))
                stocks_df = stocks_df[columns_order]
                if board == "industry":
                    industry_data = stocks_df.copy()
                    my_market.update_market_data(industry_df=industry_data)
                else:
                    concept_data = stocks_df.copy()
                    my_market.update_market_data(concept_df=concept_data)
                if g_stocks_hist_df.empty:
                    for element in stocks_df['代码']:
                        g_get_hist_queue.put(element)
                else:
                    # 使用isin方法判断df1['column_name']中的值是否在df2['column_name']中出现
                    mask = ~stocks_df['代码'].isin(g_stocks_hist_df['股票代码'])

                    # 通过布尔索引获取df1中在df2中不存在的值
                    result = stocks_df[mask]['代码'].tolist()
                    # 将列表中的每个元素依次放入队列
                    for element in result:
                        g_get_hist_queue.put(element)
        time_diff = datetime.now() - last_time
        sleep_time = my_market.INTERVAL_GET_HOT_BOARDS - time_diff.total_seconds()
        if sleep_time > 0:
            time.sleep(sleep_time)
        last_time = datetime.now()
        
# 添加超时装饰器
def timeout_decorator(timeout_seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            def target():
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    logger.error(f"回调函数执行出错: {e}")
                    return None

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout=timeout_seconds)
            
            if thread.is_alive():
                logger.error(f"回调函数执行超时 (>{timeout_seconds}秒)")
                return None
                
        return wrapper
    return decorator

def subscribe_quote_thread():
    """选股线程"""
    global A_condidate_list
    last_symbol_list = []
    industry_symbol_list = []
    concept_symbol_list = []
    global g_seq
    while True:
        #如果时间大于下午3：05，则继续
        if datetime.now().hour >= 15 and datetime.now().minute >= 5:
            if g_seq > 0:
                xtdata.unsubscribe_quote(g_seq)
            time.sleep(10)
            continue
        if my_market.industry_df is not None and not my_market.industry_df.empty:
            # 获取my_market.industry_data中的symbol列,去重后转为列表
            industry_symbol_list = my_market.industry_df['代码'].unique().tolist()
        if my_market.concept_df is not None and not my_market.concept_df.empty:
            # 获取my_market.concept_df中的symbol列,去重后转为列表
            concept_symbol_list = my_market.concept_df['代码'].unique().tolist()
        # 将行业和概念股票代码列表合并并去重
        A_condidate_list = list(set(industry_symbol_list + concept_symbol_list))

        if not A_condidate_list:
            time.sleep(10)
            logger.info("没有可订阅的股票，等待10秒")
            continue

        # 如果symbol_list与last_symbol_list不同，则需要重新订阅
        if A_condidate_list != last_symbol_list:
            if g_seq > 0:
                xtdata.unsubscribe_quote(g_seq)
            if not A_condidate_list:
                time.sleep(10)
                logger.info("没有可订阅的股票，等待10秒")
                continue
            symbol_list = A_condidate_list

            stock_list = [f"{symbol}.SH" if symbol.startswith('6') else 
                            f"{symbol}.BJ" if symbol.startswith('8') or symbol.startswith('4') else
                            f"{symbol}.SZ" if symbol.startswith('0') or symbol.startswith('3') else symbol 
                            for symbol in symbol_list]
            g_seq = xtdata.subscribe_whole_quote(stock_list, callback=subscribe_whole_quote_call_back)
            logger.info(f"新订阅个股行情数量{len(stock_list)}，订阅号为{g_seq}，原订阅（如有）已取消")
            last_symbol_list = A_condidate_list.copy()
        time.sleep(10)

def update_trading_thread(acc):
    """更新交易数据的线程"""
    global STOCK_NUMBERS_BOUGHT_IN_TODAY
    while True:
        #如果时间大于下午3：05，则继续
        if datetime.now().hour >= 15 and datetime.now().minute >= 5:
            time.sleep(10)
            continue
        try:
            # 查询资产
            asset = xt_trader.query_stock_asset(acc)
            orders = xt_trader.query_stock_orders(acc, False)
            trades = xt_trader.query_stock_trades(acc)
            #logger.info(f'查询成交{trades},{trades.stock_code, trades.order_status, trades.order_sysid, trades.order_remark}')
            buy_in_list = []            
            # 检查数据类型并相应处理
            if trades is not None and isinstance(trades, list):
                for trade in trades:
                    if trade.order_type == xtconstant.STOCK_BUY and trade.strategy_name == STRATEGY_NAME:
                        if trade.stock_code not in buy_in_list:
                            buy_in_list.append(trade.stock_code)
            #如果买入的股票支数大于今天已买入的股票支数，则更新今天已买入的股票支数
            if len(buy_in_list) > STOCK_NUMBERS_BOUGHT_IN_TODAY:
                STOCK_NUMBERS_BOUGHT_IN_TODAY = len(buy_in_list)
                logger.info(f"今天已买入的股票数量{STOCK_NUMBERS_BOUGHT_IN_TODAY}")
                #如果今天已买入的股票数量大于最大买入股票支数限制，则立即撤单
                if STOCK_NUMBERS_BOUGHT_IN_TODAY >= my_market.MAX_STOCKS_PER_DAY:
                    #所有已下单的订单立即撤单（除了已成交的以外）
                    for bought_info in A_bought_list[:]: # 使用切片创建副本进行遍历
                        if bought_info.get('seq') != 0:
                            stock_code = bought_info.get('stock')
                            # 检查该股票是否已有本策略成交（如果已有成交则不撤销）
                            if not any(trade.stock_code == stock_code and trade.strategy_name == STRATEGY_NAME for trade in trades):
                                logger.info(f"撤销未成交订单: {stock_code}, seq={bought_info.get('seq')}")
                                my_cancel_order_stock(acc, bought_info.get('seq'))
            positions = xt_trader.query_stock_positions(acc)

            for pos in positions:
                #如果open_price是无穷大，则设置为0
                if pos.open_price == float('inf') or pos.open_price == float('-inf'):
                    pos.open_price = 0
            
            # 直接更新 MarketData 实例的数据
            my_market.update_trading_data(
                asset=asset,
                positions=positions,
                orders=orders,
                trades=trades
            )
            
            time.sleep(1)
        except Exception as e:
            logger.error(f"更新交易数据时出错: {e}")
            time.sleep(1)

class MyXtQuantTraderCallback(XtQuantTraderCallback):
    def on_disconnected(self):
        """连接断开"""
        logger.info('连接断开回调')
        
    def on_stock_asset(self, asset):
        """资金信息推送"""
        logger.info(f"账户资产回调: account_id={asset.account_id}, cash={asset.cash}, total_asset={asset.total_asset}")
        my_market.update_trading_data(asset=asset)

    def delete_bought_info(self, bought_info):
        """删除已下单的订单记录"""
        A_bought_list.remove(bought_info)
        logger.info(f"已从A_bought_list中删除已下单的订单记录: {bought_info}")
        # 更新bought_list文件
        write_bought_list_to_file()

    def on_stock_order(self, order):
        """委托回报推送"""
        logger.info(f'委托回调{order.stock_code, order.order_status, order.order_id, order.order_remark}')
        if order.order_status == xtconstant.ORDER_CANCELED: #54（已撤:只有全撤的单才被认为是没有买入）
            for bought_info in A_bought_list[:]: # 使用切片创建副本进行遍历
                if bought_info.get('seq') == order.order_id:
                    # 创建定时任务，5秒后执行删除已下单的订单记录。延时5秒是为了释放的资金优先选择下单其他股票
                    timer = threading.Timer(5, self.delete_bought_info, args=(bought_info,))
                    timer.start()
                    break
        my_market.update_trading_data(orders=[order])

    def on_stock_trade(self, trade):
        """成交变动推送"""
        logger.info(f'成交回调{trade.stock_code, trade.order_status, trade.order_id, trade.order_remark}')
        my_market.update_trading_data(trades=[trade])

    def on_stock_trade_order_to_cancel(self, trade):
        """成交回报推送后取消订单"""
        try:
            if my_market.selected_df is not None and not my_market.selected_df.empty:
                # 检查trade.order_id是否在selected_df的seq列中
                if trade.order_id in my_market.selected_df['seq'].values:
                    my_market.selected_df.loc[my_market.selected_df['seq'] == trade.order_id, '下单状态'] = f"已成交（详见成交信息）"
                    logger.info(f"已更新selected_df中订单{trade.order_id}的seq为0")
        except Exception as e:
            logger.error(f"处理成交回报取消订单时出错: {e}")

    def on_stock_position(self, position):
        """持仓信息推送"""
        logger.info(f"持仓回调: {position.stock_code, position.volume, position.can_use_volume, position.open_price, position.market_value}")
        my_market.update_trading_data(positions=[position])

    def on_order_error(self, order_error):
        """委托失败推送"""
        logger.error(f"委托报错回调 {order_error.order_remark} {order_error.error_msg}")
        my_market.on_toast_message(order_error.error_msg)       
        # 如果order_error的order_id在A_bought_list中存在,则删除对应的记录，这样相当于没有占用可购买的股票支数
        try:
            for bought_info in A_bought_list[:]: # 使用切片创建副本进行遍历
                if bought_info.get('seq') == order_error.order_id:
                    self.delete_bought_info(bought_info)
        except Exception as e:
            logger.error(f"处理委托失败记录时出错: {e}")
        
        try:
            # 更新selected_df中委托失败订单的下单状态
            if my_market.selected_df is not None and not my_market.selected_df.empty:
                mask = my_market.selected_df['seq'] == order_error.order_id
                if mask.any():
                    stock_code = my_market.selected_df.loc[mask, '代码'].values[0]
                    my_market.selected_df.loc[mask, '下单状态'] = f"委托失败: {order_error.error_msg}"
                    logger.info(f"已更新selected_df中{stock_code}订单的下单状态为委托失败: 委托失败")
                    # 将这行移到if内部，只有当找到匹配订单时才执行
                    my_market.selected_df.loc[my_market.selected_df['代码'] == stock_code, 'seq'] = 0
        except Exception as e:
            logger.error(f"处理委托失败记录时出错: {e}")


    def on_cancel_error(self, cancel_error):
        """撤单失败推送"""
        logger.info(f"撤单失败推送：{datetime.now()} {sys._getframe().f_code.co_name}，{cancel_error.order_id}，{cancel_error.error_msg}")

    def on_order_stock_async_response(self, response):
        """异步下单回报推送"""
        logger.info("response:", "response.order_remark:", response.order_remark, "response.account_id:",response.account_id,"response.order_id:", response.order_id, "response.order_status:", response.order_status, "response.order_seq:", response.order_seq)

    def on_cancel_order_stock_async_response(self, response):
        """异步撤单回报推送"""
        logger.info(f"{datetime.now()} {sys._getframe().f_code.co_name}")

    def on_account_status(self, status):
        """账户状态推送"""
        logger.info(f"账户状态回调: {status.account_id, status.account_type, status.status}")

    def on_asset_change(self, asset):
        """资金变动推送"""
        logger.info(f"资金变动回调: account_id={asset.account_id}, cash={asset.cash}, total_asset={asset.total_asset}")
        my_market.update_trading_data(asset=asset)

    def on_order_change(self, order):
        """委托变动推送"""
        my_market.update_trading_data(orders=[order])
        logger.info(f'委托变动回调')

    def on_position_change(self, position):
        """持仓变动推送"""
        my_market.update_trading_data(positions=[position])
        logger.info(f'持仓变动回调')

def start_web_server():
    """启动 Web 服务器"""
    try:
        from web_ui import app, socketio  # 修改这里，导入 socketio
        host = '127.0.0.1'
        port = 8080
        
        logger.info("网页服务器正在启动...")
        logger.info(f"请在浏览器中访问: http://{host}:{port}")
        
        # 使用 socketio.run() 替代 serve(app)
        socketio.run(app, 
                    host=host, 
                    port=port, 
                    debug=False)
    except Exception as e:
        logger.error(f"启动网页服务器时出错: {e}")

def run_forever():
    global last_trading_heartbeat
    global g_seq
    while True:
        current_date = datetime.now().date()
        current_time = datetime.now().time()
        
        # 检查是否为交易日（周一到周五）
        is_trading_day = is_tradeday()
        
        # 检查是否在交易时段
        morning_start = datetime.strptime('09:30:00', '%H:%M:%S').time()
        morning_end = datetime.strptime('11:30:00', '%H:%M:%S').time()
        afternoon_start = datetime.strptime('13:00:00', '%H:%M:%S').time()
        afternoon_end = datetime.strptime('15:00:00', '%H:%M:%S').time()
        
        is_trading_hour = (
            (current_time >= morning_start and current_time <= morning_end) or  # 上午交易时段
            (current_time >= afternoon_start and current_time <= afternoon_end)  # 下午交易时段
        )

        # 只在交易日的交易时段内检查心跳
        if is_trading_day and is_trading_hour:
            # 检查是否收到心跳
            time_since_last_heartbeat = time.time() - last_trading_heartbeat
            
            # 如果超过30秒没有收到心跳消息(last_trading_heartbeat更新)
            if time_since_last_heartbeat > 30:
                logger.info(f"超过{time_since_last_heartbeat}秒没有收到心跳消息，请检查miniQMT是否正常运行")
            else:
                time_since_last_heartbeat = time.time() #非交易时段更新time_since_last_heartbeat，以免进入交易时段时被判断为超时
        #非交易时段取消订阅
        else:
            if g_seq > 0:
                xtdata.unsubscribe_quote(g_seq)
                g_seq = 0
        if 'last_checked_date' not in locals():
            last_checked_date = current_date
        if current_date != last_checked_date:
            logger.info("日期已变化，新的一天开始，程序将退出")
            #退出本程序
            sys.exit()  
        time.sleep(1)    
    
if __name__ == '__main__':
    # 设置日志
    logger = my_market.setup_logger()
    logger.info("程序启动")
    
    # 检查程序是否已在运行
    current_pid = os.getpid()
    
    # 遍历所有进程
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # 获取进程信息
            proc_info = proc.info
            
            # 如果是Python进程且运行的是当前脚本
            if (proc_info['pid'] != current_pid and  # 不是当前进程
                proc_info['name'] == 'python.exe' and # 是Python进程
                proc_info['cmdline'] and # 命令行参数存在
                'mytrade_zhuizhangtingban.py' in proc_info['cmdline'][-1]): # 运行的是当前脚本
                
                logger.info("检测到已有同一程序在运行，本次启动退出")
                os._exit(0)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    global g_asset
    global g_orders
    global g_trades
    global g_positions
    global g_watch_list
    global g_seq    
    g_seq = 0
    g_watch_list = []
    A_bought_list = []
    hot_industry_list = []
    hot_concept_list = []
    STOCK_NUMBERS_BOUGHT_IN_TODAY = 0
    STRATEGY_NAME = "马总打板策略"
    A_selected_list = []
    A_condidate_list = []
    my_market.load_config()
    my_market.load_server_chan_keys()
    my_market.load_all_stocks_info()
    my_market.load_selected_stocks_info_from_file()    
    read_bought_list_from_file()
    last_trading_heartbeat = time.time()

    # 确保交易系统正确初始化
    try:
        session_id = int(time.time())
        xt_trader = XtQuantTrader(my_market.PATH_QMT, session_id)
        
        if not xt_trader:
            raise Exception("交易系统初始化失败")
            
        # 创建资金账号的证券账号对象
        acc = StockAccount(my_market.ACCOUNT_ID, 'STOCK')
        if not acc:
            raise Exception("账户对象创建失败")
            
        # 创建交易回调类对象，并声明接收回调
        callback = MyXtQuantTraderCallback()
        xt_trader.register_callback(callback)
        
        # 启动交易线程
        xt_trader.start()
        
        # 建立交易连接，返回0表示连接成功
        connect_result = xt_trader.connect()
        if connect_result != 0:
            raise Exception(f"建立交易连接失败，错误码: {connect_result}")
        logger.info(f'建立交易连接结果: {connect_result}')
        
        # 订阅交易回调
        subscribe_result = xt_trader.subscribe(acc)
        if subscribe_result != 0:
            raise Exception(f"订阅交易回调失败，错误码: {subscribe_result}")
        logger.info(f'交易回调订阅结果: {subscribe_result}')
        
        # 等待一段时间确保初始化完成
        time.sleep(2)
        
    except Exception as e:
        logger.error(f"交易系统初始化失败: {e}")
        sys.exit(1)

    g_stocks_hist_df = pd.DataFrame()
    g_get_hist_queue = queue.Queue()

    # 创建两个子线程，分别刷新行业板块和概念板块
    thread_industry_board = threading.Thread(
        target=refresh_hot_board_thread,
        args=("industry",)
    )
    thread_concept_board = threading.Thread(
        target=refresh_hot_board_thread,
        args=("concept",)
    )
    thread_industry_board.daemon = True  # 设置为守护线程,主线程结束时会自动结束
    thread_concept_board.daemon = True  # 设置为守护线程,主线程结束时会自动结束
    thread_industry_board.start()
    thread_concept_board.start()
    
    #创建子线程，获取热门板块股票的历史数据（截止到上一交易日的数据）
    thread_get_stock_hist = threading.Thread(target=get_stock_hist_thread)
    thread_get_stock_hist.daemon = True
    thread_get_stock_hist.start()    
    
    #创建子线程，开启选股函数
    thread_select_stock = threading.Thread(target=subscribe_quote_thread)
    thread_select_stock.daemon = True
    thread_select_stock.start()
    
    # 启动Web UI线程
    web_thread = threading.Thread(target=start_web_server)
    web_thread.daemon = True
    web_thread.start()

    # 启动更新交易数据的线程
    trading_thread = threading.Thread(target=update_trading_thread, args=(acc,))
    trading_thread.daemon = True
    trading_thread.start()

    # 初始化时更新一次数据
    asset = xt_trader.query_stock_asset(acc)
    orders = xt_trader.query_stock_orders(acc, False)
    trades = xt_trader.query_stock_trades(acc)
    positions = xt_trader.query_stock_positions(acc)

    # 使用market实例的方法更新交易数据
    my_market.update_trading_data(asset=asset, positions=positions, orders=orders, trades=trades)
    
    # 添加更新检查
    has_update, new_ver, changelog = check_update()
    if has_update:
        logger.info(f"发现新版本 {new_ver}，更新内容：{changelog}")

    # 阻塞主线程退出
    #xt_trader.run_forever()
    run_forever()
    # 如果使用vscode pycharm等本地编辑器 可以进入交互模式 方便调试 （把上一行的run_forever注释掉 否则不会执行到这里）
    interact()
