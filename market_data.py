import pandas as pd
import logging
import configparser
import os
import akshare as ak
from xtquant import xtconstant
from datetime import datetime
import logging.handlers

class MarketData:
    def __init__(self):        
        """初始化市场数据类"""
        # 初始化日志配置
        self.logger = self.setup_logger()
        self.all_a_stocks = None
        # 初始化数据属性
        self.industry_df = None
        self.concept_df = None
        self.selected_df = None
        self.asset = None
        self.positions = None
        self.orders = None
        self.trades = None
        self.toast_message = None  # toast消息

        # Server酱配置
        self.server_chan_keys = []
        
        self.CANCEL_ORDER_SECONDS = 0  # 默认0秒后撤单
        self.SINGLE_BUY_AMOUNT = 0  # 默认值0万元
        self.MAX_STOCKS_PER_DAY = 0  # 默认每日最多买入0支股票

    def setup_logger(self):
        """设置日志"""
        logger = logging.getLogger('my_logger')
        # 防止重复添加处理器
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            
            # 创建控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 创建一个自定义的TimedRotatingFileHandler
            log_dir = os.path.join(os.path.dirname(__file__), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'market_data.log')
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_file,
                when='midnight',  # 每天午夜切换到新文件
                interval=1,       # 间隔为1天
                backupCount=30,   # 保留30天的日志文件
                encoding='utf-8'
            )
            # 设置新日志文件的命名格式
            file_handler.suffix = "%Y%m%d.log"
            file_handler.setLevel(logging.INFO)
            
            # 创建格式化器
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
            
            # 将格式化器添加到处理器
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)
            
            # 将处理器添加到日志记录器
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)
        
        return logger

    def load_config(self):
        """加载配置"""
        try:
            config = configparser.ConfigParser(interpolation=None)
            config_file = 'config.ini'
            
            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')
                self.logger.info("从config.ini文件加载配置")
                # Trading
                self.TOP_N_BOARDS = config.getint('Trading', 'TOP_N_BOARDS', fallback=5)
                self.TOP_N_STOCKS = config.getint('Trading', 'TOP_N_STOCKS', fallback=10)
                self.INTERVAL_GET_HOT_BOARDS = config.getint('Trading', 'INTERVAL_GET_HOT_BOARDS', fallback=60)
                self.BUY_AMOUNT = config.getint('Trading', 'BUY_AMOUNT', fallback=100)
                self.TIMEOUT_SECONDS = config.getint('Trading', 'TIMEOUT_SECONDS', fallback=5)
                
                # MA
                self.BOLL_DAYS = config.getint('MA', 'BOLL_DAYS', fallback=20)
                self.BOLL_MULTIPLES = config.getint('MA', 'BOLL_MULTIPLES', fallback=2)
                self.MA_5 = config.getint('MA', 'MA_5', fallback=5)
                
                # Account
                self.PATH_QMT = config.get('Account', 'PATH_QMT', fallback='D:\\国金证券QMT交易端\\userdata_mini')
                self.ACCOUNT_ID = config.get('Account', 'ACCOUNT_ID', fallback='8881234567')
                
                # Threshold
                self.THRESHOLD_CUR_UPDOWNRATE_10PCT = config.getfloat('Threshold', 'THRESHOLD_CUR_UPDOWNRATE_10PCT', fallback=8.5)
                self.THRESHOLD_HIST_UPDOWNRATE_10PCT = config.getfloat('Threshold', 'THRESHOLD_HIST_UPDOWNRATE_10PCT', fallback=4.5)
                self.THRESHOLD_CUR_UPDOWNRATE_20PCT = config.getfloat('Threshold', 'THRESHOLD_CUR_UPDOWNRATE_20PCT', fallback=17)
                self.THRESHOLD_HIST_UPDOWNRATE_20PCT = config.getfloat('Threshold', 'THRESHOLD_HIST_UPDOWNRATE_20PCT', fallback=9)
                self.THRESHOLD_CUR_UPDOWNRATE_30PCT = config.getfloat('Threshold', 'THRESHOLD_CUR_UPDOWNRATE_30PCT', fallback=24)
                self.THRESHOLD_HIST_UPDOWNRATE_30PCT = config.getfloat('Threshold', 'THRESHOLD_HIST_UPDOWNRATE_30PCT', fallback=19)
                
                # Days
                #最大涨幅观察天数
                self.NDAYS_BEFORE_1 = config.getint('Days', 'NDAYS_BEFORE_1', fallback=10)
                #趋势观察天数
                self.NDAYS_BEFORE_2 = config.getint('Days', 'NDAYS_BEFORE_2', fallback=30)
                #最高价观察天数
                self.NDAYS_BEFORE_3 = config.getint('Days', 'NDAYS_BEFORE_3', fallback=40)
                #涨停板观察天数
                self.NDAYS_BEFORE_4 = config.getint('Days', 'NDAYS_BEFORE_4', fallback=60)
                #涨停板观察天数
                self.NDAYS_BEFORE_5 = config.getint('Days', 'NDAYS_BEFORE_5', fallback=65)
                
                self.logger.info("配置已（重新）加载")

        except Exception as e:
            self.logger.error(f"加载配置时出错: {e}")

    def load_all_stocks_info(self):
        """加载股票基本信息"""
        # 确保data目录存在
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        # 检查是否存在all_a_stocks.csv文件且是今天创建的
        csv_file = os.path.join(data_dir, 'all_a_stocks.csv')
        if os.path.exists(csv_file):
            # 获取文件的最后修改时间
            file_mtime = datetime.fromtimestamp(os.path.getmtime(csv_file))
            today = datetime.now().date()
            
            # 如果文件是今天修改的,则直接读取CSV文件
            if file_mtime.date() == today:
                try:
                    self.all_a_stocks = pd.read_csv(csv_file, dtype={'证券代码': str})
                    self.logger.info(f"已从{csv_file}文件读取全A股股票名称信息")
                    return
                except Exception as e:
                    self.logger.error(f"读取{csv_file}文件时出错: {e}")

        if self.all_a_stocks is None:
            # 获取沪深京 A 股的基本信息
            stock_info_sh_name_code_df = ak.stock_info_sh_name_code()
            # 先创建副本，然后选择需要的列
            stock_info_sh = stock_info_sh_name_code_df[['证券代码', '证券简称', '上市日期']].copy()
            # 使用 loc 设置数据类型
            stock_info_sh.loc[:, '证券代码'] = stock_info_sh['证券代码'].astype(str)
            
            stock_info_sz_name_code_df = ak.stock_info_sz_name_code()
            # 先创建副本，然后选择需要的列
            stock_info_sz = stock_info_sz_name_code_df[['A股代码', 'A股简称', 'A股上市日期']].copy()
            # 使用 loc 设置数据类型
            stock_info_sz.loc[:, 'A股代码'] = stock_info_sz['A股代码'].astype(str)
            # 重命名列
            stock_info_sz = stock_info_sz.rename(columns={
                'A股代码': '证券代码',
                'A股简称': '证券简称', 
                'A股上市日期': '上市日期'
            })
            
            stock_info_bj_name_code_df = ak.stock_info_bj_name_code()
            # 先创建副本，然后选择需要的列
            stock_info_bj = stock_info_bj_name_code_df[['证券代码', '证券简称', '上市日期']].copy()
            # 使用 loc 设置数据类型
            stock_info_bj.loc[:, '证券代码'] = stock_info_bj['证券代码'].astype(str)
            
            # 合并所有数据
            self.all_a_stocks = pd.concat([stock_info_sh, stock_info_sz, stock_info_bj])
            
            # 将所有股票信息写入CSV文件
            try:
                self.all_a_stocks.to_csv(csv_file, index=False, encoding='utf-8')
                self.logger.info(f"已将股票信息写入文件: {csv_file}")
            except Exception as e:
                self.logger.error(f"写入{csv_file}文件时出错: {e}")

    def load_selected_stocks_info_from_file(self):
        """加载已选股票数据"""
        # 获取当前日期
        today = datetime.now().date()
        # 构建文件名,格式为 selected_stocks_YYYYMMDD.csv
        csv_file = os.path.join(os.path.dirname(__file__), 'data', f'selected_stocks_{today.strftime("%Y%m%d")}.csv')
        
        if os.path.exists(csv_file):
            try:
                self.selected_df = pd.read_csv(csv_file, dtype={'代码': str})
                self.logger.info(f"已从{csv_file}文件读取今日已选股票数据")
            except Exception as e:
                self.logger.error(f"读取{csv_file}文件时出错: {e}")
                self.selected_df = pd.DataFrame()
        else:
            self.selected_df = pd.DataFrame()
            self.logger.info(f"没有{csv_file}文件")

    def get_stock_name(self, stock_code):
        # 查找匹配的股票代码
        result = self.all_a_stocks[self.all_a_stocks['证券代码'] == stock_code[:6]]
        if not result.empty:
            return result['证券简称'].values[0]
        return None
    
    def get_order_status(self, status):
        if status == xtconstant.ORDER_UNREPORTED:
            ret = "未报"
        elif status == xtconstant.ORDER_WAIT_REPORTING:
            ret = "待报"
        elif status == xtconstant.ORDER_REPORTED:
            ret = "已报"
        elif status == xtconstant.ORDER_REPORTED_CANCEL:
            ret = "已报待撤"
        elif status == xtconstant.ORDER_PARTSUCC_CANCEL:
            ret = "部成待撤"
        elif status == xtconstant.ORDER_PART_CANCEL:
            ret = "部撤"
        elif status == xtconstant.ORDER_CANCELED:
            ret = "已撤"
        elif status == xtconstant.ORDER_PART_SUCC:
            ret = "部成"
        elif status == xtconstant.ORDER_SUCCEEDED:
            ret = "已成"
        elif status == xtconstant.ORDER_JUNK:
            ret = "废单"
        elif status == xtconstant.ORDER_UNKNOWN:
            ret = "未知"
        return ret
        
    def update_market_data(self, industry_df=None, concept_df=None, selected_df=None):
        """更新市场数据"""
        try:
            if industry_df is not None:
                self.industry_df = industry_df.copy()
                
            if concept_df is not None:
                self.concept_df = concept_df.copy()
                
            if selected_df is not None:
                if self.selected_df is None or self.selected_df.empty:
                    self.selected_df = selected_df.copy()
                else:
                    # 检查第一个股票代码是否已存在
                    if not selected_df.empty and selected_df.iloc[0]['代码'] in self.selected_df['代码'].values:
                        # 更新已存在股票的下单状态
                        mask = self.selected_df['代码'] == selected_df.iloc[0]['代码']
                        self.selected_df.loc[mask, '下单状态'] = selected_df.iloc[0]['下单状态']
                    else:
                        self.selected_df = pd.concat([self.selected_df, selected_df], ignore_index=True)
                    # 保存已选股票数据到CSV文件
                    try:
                        if self.selected_df is not None and not self.selected_df.empty:
                            # 获取今天的日期作为文件名
                            today = datetime.now().strftime('%Y%m%d')
                            # 构建文件路径
                            data_dir = os.path.join(os.path.dirname(__file__), 'data')
                            os.makedirs(data_dir, exist_ok=True)
                            filename = os.path.join(data_dir, f'selected_stocks_{today}.csv')
                            # 保存到CSV,如果已存在则覆盖
                            self.selected_df.to_csv(filename, index=False, encoding='utf-8-sig')
                            self.logger.info(f"已选股票数据已保存到文件: {filename}")
                    except Exception as e:
                        self.logger.error(f"保存已选股票数据到CSV时出错: {e}")
            '''# 保存板块和已选股票数据到CSV文件
            try:
                # 构建文件路径
                data_dir = os.path.join(os.path.dirname(__file__), 'data')
                os.makedirs(data_dir, exist_ok=True)

                # 保存行业板块数据
                if self.industry_df is not None and not self.industry_df.empty:
                    industry_filename = os.path.join(data_dir, f'industry.csv')
                    self.industry_df.to_csv(industry_filename, index=False, encoding='utf-8-sig')
                    self.logger.info(f"行业板块数据已保存到文件: {industry_filename}")

                # 保存概念板块数据
                if self.concept_df is not None and not self.concept_df.empty:
                    concept_filename = os.path.join(data_dir, f'concept.csv')
                    self.concept_df.to_csv(concept_filename, index=False, encoding='utf-8-sig')
                    self.logger.info(f"概念板块数据已保存到文件: {concept_filename}")

                # 保存已选股票数据
                if self.selected_df is not None and not self.selected_df.empty:
                    selected_filename = os.path.join(data_dir, f'selected.csv')
                    self.selected_df.to_csv(selected_filename, index=False, encoding='utf-8-sig')
                    self.logger.info(f"已选股票数据已保存到文件: {selected_filename}")

            except Exception as e:
                self.logger.error(f"保存板块数据到CSV时出错: {e}")'''
        except Exception as e:
            self.logger.error(f"更新市场数据时出错: {e}")
        
    def update_trading_data(self, asset=None, positions=None, orders=None, trades=None):
        """更新交易数据"""
        if asset is not None:
            self.asset = asset
        if positions is not None:
            self.positions = positions
        if orders is not None:
            self.orders = orders
        if trades is not None:
            self.trades = trades

    def get_industry_info(self):
        """获取行业板块信息"""
        try:
            if self.industry_df is not None:
                #行业板块数据列名: ['板块', '代码','名称', '分析结果', '最新价', '涨跌幅', '涨跌额', '成交量', '成交额', '振幅', '最高', '最低', '今开', '昨收', '换手率', '市盈率-动态', '市净率']
                result = self.industry_df[['板块', '代码', '名称', '最新价', '涨跌幅', '分析结果']].copy()
                result.columns = ['板块', '代码', '名称', '最新价', '涨跌幅', '分析结果']
                return result.to_dict('records')
            return []
        except Exception as e:
            self.logger.error(f"获取行业板块信息时出错: {e}")
            return []

    def get_concept_info(self):
        """获取概念板块信息"""
        try:
            if self.concept_df is not None:
                #概念板块数据列名: ['板块', '代码', '名称', '分析结果', '最新价', '涨跌幅', '涨跌额', '成交量', '成交额', '振幅', '最高', '最低', '今开', '昨收', '换手率', '市盈率-动态', '市净率']
                result = self.concept_df[['板块', '代码', '名称', '最新价', '涨跌幅', '分析结果']].copy()
                result.columns = ['板块', '代码', '名称', '最新价', '涨跌幅', '分析结果']
                return result.to_dict('records')
            return []
        except Exception as e:
            self.logger.error(f"获取概念板块信息时出错: {e}")
            return []

    def get_selected_info(self):
        """获取已选股票信息"""
        if self.selected_df is not None and not self.selected_df.empty:
            return self.selected_df.to_dict('records')
        return []

    def get_asset_info(self):
        """获取资产信息"""
        if self.asset is not None:
            asset_info = {
                'account_id': str(self.ACCOUNT_ID),
                'cash': float(self.asset.cash) if hasattr(self.asset, 'cash') else 0.0,
                'total_asset': float(self.asset.total_asset) if hasattr(self.asset, 'total_asset') else 0.0,
                'market_value': float(self.asset.market_value) if hasattr(self.asset, 'market_value') else 0.0
            }
            return asset_info
        
        return {
            'account_id': str(self.ACCOUNT_ID),
            'cash': 0.0,
            'total_asset': 0.0,
            'market_value': 0.0
        }

    def get_positions_info(self):
        """获取持仓信息"""
        if hasattr(self, 'positions'):
            return [{
                'stock_code': pos.stock_code,
                'stock_name': self.get_stock_name(pos.stock_code),
                'volume': pos.volume,
                'can_use_volume': pos.can_use_volume,
                'open_price': 0 if pd.isna(pos.open_price) else pos.open_price,
                'market_value': pos.market_value
            } for pos in self.positions] if self.positions else []
        return []

    def get_orders_info(self):
        """获取委托信息"""
        if hasattr(self, 'orders'):
            return [{
                'order_id': order.order_id,
                'order_time': datetime.fromtimestamp(order.order_time).strftime('%Y-%m-%d %H:%M:%S'),
                'stock_code': order.stock_code,
                'order_type': "买入" if order.order_type == xtconstant.STOCK_BUY else "卖出",
                'price_type': "最新价" if order.price_type == xtconstant.LATEST_PRICE else "指定价",
                'price': order.price,
                'order_volume': order.order_volume,
                'order_status': self.get_order_status(order.order_status),
                'status_msg': order.status_msg,
                'strategy_name':order.strategy_name,
                'order_remark':order.order_remark,
                'stock_name':self.get_stock_name(order.stock_code)
            } for order in self.orders] if self.orders else []
        return []

    def get_trades_info(self):
        """获取成交信息"""
        if hasattr(self, 'trades'):
            return [{
                'traded_id': trade.traded_id,
                'stock_code': trade.stock_code,
                'order_type': "买入" if trade.order_type == xtconstant.STOCK_BUY else "卖出",
                'traded_volume': trade.traded_volume,
                'traded_price': trade.traded_price,
                'traded_time': datetime.fromtimestamp(trade.traded_time).strftime('%Y-%m-%d %H:%M:%S'),
                'stock_name':self.get_stock_name(trade.stock_code),
                'strategy_name':trade.strategy_name,
                'order_remark':trade.order_remark,
            } for trade in self.trades] if self.trades else []
        return []

    def update_market_info(self):
        """更新市场数据"""
        try:
            # 获取行业板块数据
            industry_df = self.get_industry_boards()
            if industry_df is not None:  # 只检查是否为 None
                self.industry_df = industry_df
                self.logger.info("已更新行业板块数据")
            
            # 获取概念板块数据
            concept_df = self.get_concept_boards()
            if concept_df is not None:  # 只检查是否为 None
                self.concept_df = concept_df
                self.logger.info("已更新概念板块数据")
            
        except Exception as e:
            self.logger.error(f"更新市场数据时出错: {e}")

    def on_toast_message(self, toast_message):
        """toast消息回调"""
        self.toast_message = toast_message


    def get_toast_message(self):
        """获取并清除toast消息"""
        toast_message = self.toast_message
        self.toast_message = None  # 清除toast信息
        return toast_message


    def get_board_industry_cons(self, sector):
        df = pd.DataFrame()        
        try:
            #self.logger.info(f"开始获取行业板块 {sector} 的股票列表")
            df = ak.stock_board_industry_cons_em(symbol=sector)
            if df.empty:
                self.logger.warning(f"获取到的行业板块 {sector} 股票列表为空")
            #else:
            #    self.logger.info(f"成功获取行业板块 {sector} 的股票列表，包含 {len(df)} 条记录")
        except Exception as e:
            self.logger.error(f"获取行业板块 {sector} 的股票列表时出错，错误信息：{str(e)}")
            #self.logger.error(f"错误类型：{type(e)}")
        return df

    def get_board_concept_cons(self, sector):
        df = pd.DataFrame()        
        try:
            #self.logger.info(f"开始获取概念板块 {sector} 的股票列表")
            df = ak.stock_board_concept_cons_em(symbol=sector)
            if df.empty:
                self.logger.warning(f"获取到的概念板块 {sector} 股票列表为空")
            #else:
            #    self.logger.info(f"成功获取概念板块 {sector} 的股票列表，包含 {len(df)} 条记录")
        except Exception as e:
            self.logger.error(f"获取概念板块 {sector} 的股票列表时出错，错误信息：{str(e)}")
            #self.logger.error(f"错误类型：{type(e)}")
        return df

    def load_server_chan_keys(self):
        """加载Server酱密钥"""
        try:
            # 构建文件路径
            data_dir = os.path.join(os.path.dirname(__file__), 'data')
            os.makedirs(data_dir, exist_ok=True)
            filename = os.path.join(data_dir, 'server_chan_keys.txt')
            
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    for line in f:
                        key = line.strip()
                        if key and not key.startswith('#'):  # 忽略空行和注释
                            self.server_chan_keys.append(key)
                self.logger.info(f"已加载 {len(self.server_chan_keys)} 个Server酱密钥")
            else:
                self.logger.warning("Server酱密钥文件不存在")
        except Exception as e:
            self.logger.error(f"加载Server酱密钥时出错: {e}")

    def save_server_chan_keys(self):
        """保存Server酱密钥"""
        try:
            data_dir = os.path.join(os.path.dirname(__file__), 'data')
            os.makedirs(data_dir, exist_ok=True)
            filename = os.path.join(data_dir, 'server_chan_keys.txt')
            
            with open(filename, 'w', encoding='utf-8') as f:
                for key in self.server_chan_keys:
                    f.write(f"{key}\n")
            self.logger.info("Server酱密钥已保存")
        except Exception as e:
            self.logger.error(f"保存Server酱密钥时出错: {e}")

    def add_server_chan_key(self, key):
        """添加Server酱密钥"""
        if key not in self.server_chan_keys:
            self.server_chan_keys.append(key)
            self.save_server_chan_keys()
            self.logger.info(f"已添加新的Server酱密钥")
        else:
            self.logger.info("该Server酱密钥已存在")

    def remove_server_chan_key(self, key):
        """删除Server酱密钥"""
        if key in self.server_chan_keys:
            self.server_chan_keys.remove(key)
            self.save_server_chan_keys()
            self.logger.info(f"已删除Server酱密钥")
        else:
            self.logger.info("要删除的Server酱密钥不存在")

# 创建全局实例
my_market = MarketData()

if __name__ == "__main__":
    logger = my_market.setup_logger()
    logger.info("程序启动")
    