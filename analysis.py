import glob
import os
import pandas as pd
import akshare as ak
import time
import logging
from datetime import datetime
import chardet
from xtquant import xtdata

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
def get_stock_hist(symbol, startdate, enddate):
    stock = symbol2stock(symbol)
    print(f"股票代码: {stock}")
    period = "1d"

    # 获取历史行情数据
    code_list = [stock]  # 定义要下载和订阅的股票代码列表
    count = -1  # 设置count参数，使gmd_ex返回全部数据

    # 下载历史数据
    xtdata.download_history_data(stock, period, startdate, enddate)

    time.sleep(1)
    
    # 获取历史行情数据
    df = xtdata.get_market_data_ex([], code_list, period=period, start_time=startdate, end_time=enddate, count=count)
    #{'002600.SZ':            open   high    low  close   volume        amount  settelementPrice  openInterest  preClose  suspendFlag
    #20250102   7.97   8.14   7.72   7.82  1146436  9.103592e+08               0.0            15      8.00            0       
    #20250103   7.82   7.89   7.61   7.63  1169715  9.055436e+08               0.0            15      7.82            0 }
    if stock in df and len(df[stock]) > 0:
        data = pd.DataFrame(df[stock])
        data['股票代码'] = symbol        
        data['日期'] = data.index
        data = data.reset_index(drop=True)
        
        '''# 重命名列
        data = data.rename(columns={
            'close': '收盘',
            'high': '最高',
            'open': '开盘',
            'low': '最低'
        })
        
        # 计算涨跌幅 (避免使用inplace)
        data['涨跌幅'] = (data['收盘'] / data['收盘'].shift(1) - 1) * 100
        # 替换 fillna(inplace=True) 的写法
        data['涨跌幅'] = data['涨跌幅'].fillna(0)
        data['涨跌幅'] = data['涨跌幅'].round(2)
        
        # 计算涨跌额
        data['涨跌额'] = (data['收盘'] - data['收盘'].shift(1)).round(2)
        data['涨跌额'] = data['涨跌额'].fillna(0)'''
        return data
    else:
        logger.error(f"获取股票{symbol}历史数据失败")
        return None

    # 原版代码
    try:
        df = ak.stock_zh_a_hist(
            symbol=stock_code, 
            period="daily",
            start_date=start_date, 
            end_date=end_date, 
            adjust="qfq"
        )
        
        # 新版返回数据列名是中文，需要转换
        '''df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount'
        })'''
        
        print(f"成功获取 {stock_code} {start_date}-{end_date} 数据，共{len(df)}条记录")
        #print("前5行数据样例：")
        #print(df.head())
        return df
    except Exception as e:
        print(f"获取数据失败: {str(e)}")
        return pd.DataFrame()
start_date = "20250101"
end_date = datetime.now().strftime("%Y%m%d")
        
# 获取上证指数的历史数据
szzs_index_df = ak.index_zh_a_hist(symbol="000001", period="daily", start_date=start_date, end_date=end_date, )

szcz_index_df = ak.index_zh_a_hist(symbol="399001", period="daily", start_date=start_date, end_date=end_date, )

cybz_index_df = ak.index_zh_a_hist(symbol="399006", period="daily", start_date=start_date, end_date=end_date, )

# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(current_dir, "data")

# 使用glob匹配所有符合条件的CSV文件
file_pattern = "selected_stocks_*.csv"
csv_files = glob.glob(os.path.join(data_dir, file_pattern))

if not csv_files:
    raise FileNotFoundError(f"未找到匹配 {file_pattern} 的文件")

# 读取所有匹配的文件到DataFrame列表
data_stocks = []
data_frames = []
for file in csv_files:

    # 从文件名提取日期
    filename = os.path.basename(file)
    date_str = filename.replace("selected_stocks_", "").replace(".csv", "")
    
    # 如果date_str不是八位数字字符串，则跳过
    if not date_str.isdigit() or len(date_str) != 8:
        continue
    
    with open(file, 'rb') as f:
        result = chardet.detect(f.read())
        
    df = pd.read_csv(file, encoding=result['encoding'])
    
    
    # 添加日期列
    df['日期'] = date_str
    for index, row in df.iterrows():
        # 获取股票代码并标准化格式
        symbol = str(row['代码']).zfill(6)  # 补足6位数字
        
        start_date = "20250101"
        end_date = datetime.now().strftime("%Y%m%d")
        adjust = 'qfq'  # 使用前复权数据
        if symbol[:1] == "6":
            index_df = szzs_index_df.copy()
        elif symbol[:1] == "0":
            index_df = szcz_index_df.copy()
        elif symbol[:1] == "3":
            index_df = cybz_index_df.copy()
        else:
            index_df = pd.DataFrame()

        try:
            if not index_df.empty:
                target_date = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
                
                # 修改后的打印语句
                #print(f"目标日期: {target_date}, 指数日期范围: {index_df['日期'].min()} 至 {index_df['日期'].max()}")
                
                try:
                    target_index = index_df[index_df['日期'] == target_date].index[0]
                    start_idx = max(0, target_index - 4)
                    end_idx = min(len(index_df), target_index + 1)  # 包含当天
                    result_data = index_df.iloc[start_idx:end_idx]
                    
                    # 添加数据长度验证
                    if len(result_data) < 5:
                        logger.warning(f"指数数据不足5天，实际获取{len(result_data)}天")
                        continue
                        
                    # 先保留原始数值
                    raw_value = (result_data.iloc[-1]['开盘'] - result_data.iloc[-2]['收盘']) / result_data.iloc[-2]['收盘']
                    df.loc[index, '指数开盘较昨收盘涨跌幅_原始'] = raw_value  # 保持float类型
                    df.loc[index, '指数开盘较昨收盘涨跌幅'] = f"{raw_value*100:.2f}%"  # 新增格式化列
                    df.drop(columns=['指数开盘较昨收盘涨跌幅_原始'], inplace=True)
                    
                    df.loc[index, '前1天指数涨跌幅'] = result_data.iloc[-2]['涨跌幅']
                    df.loc[index, '前2天指数涨跌幅'] = result_data.iloc[-3]['涨跌幅']
                    df.loc[index, '前3天指数涨跌幅'] = result_data.iloc[-4]['涨跌幅']
                    df.loc[index, '前4天指数涨跌幅'] = result_data.iloc[-5]['涨跌幅']
                    #df示例
                    #open   high    low  close   volume  ...  openInterest  preClose  suspendFlag    股票代码        日期
                    #0    7.97   8.14   7.72   7.82  1146436  ...            15      8.00            0  002600  20250102
                except Exception as e:
                    print(f"获取指数数据失败: {str(e)}")
        except Exception as e:
            print(f"获取指数数据失败: {str(e)}")
            
        df_hist = get_stock_hist(symbol, start_date, end_date)
        #把df_hist的日期列转换为字符串类型
        df_hist['日期'] = df_hist['日期'].astype(str)

        #df_hist示例
        #open   high    low  close   volume  ...  openInterest  preClose  suspendFlag    股票代码        日期
        #0    7.97   8.14   7.72   7.82  1146436  ...            15      8.00            0  002600  20250102
        #1    7.82   7.89   7.61   7.63  1169715  ...            15      7.82            0  002600  20250103
        
        # 处理历史数据
        if not df_hist.empty:
            # 转换日期格式并排序
            
            # 获取包含目标日期在内的前后4个交易日数据
            target_date = date_str
            try:
                # 找到目标日期的索引
                target_index = df_hist[df_hist['日期'] == target_date].index[0]
                # 计算安全索引范围
                start_idx = max(0, target_index - 4)
                end_idx = min(len(df_hist), target_index + 5)  # +5 因为切片不包含结束索引                
                result_data = df_hist.iloc[start_idx:end_idx]
                
                # 验证数据长度
                if len(result_data) < 9:
                    logger.warning(f"股票 {symbol} 在 {date_str} 附近没有足够的交易日数据（实际获取 {len(result_data)} 天）")
                    continue
                else:
                    print(f"股票 {symbol} 在 {date_str} 附近有足够的交易日数据（实际获取 {len(result_data)} 天）")
                
            except IndexError:
                logger.warning(f"股票 {symbol} 在 {date_str} 无匹配数据")
                continue
            
            # 当天收盘价
            df.loc[index, 'n0c'] = result_data.iloc[4]['close']
            # 第1个交易日数据
            df.loc[index, 'n1o'] = result_data.iloc[5]['open']
            df.loc[index, 'n1c'] = result_data.iloc[5]['close']
            df.loc[index, 'n1h'] = result_data.iloc[5]['high']
            df.loc[index, 'n1l'] = result_data.iloc[5]['low']
            
            # 第2个交易日数据
            df.loc[index, 'n2o'] = result_data.iloc[6]['open']
            df.loc[index, 'n2c'] = result_data.iloc[6]['close']
            df.loc[index, 'n2h'] = result_data.iloc[6]['high']
            df.loc[index, 'n2l'] = result_data.iloc[6]['low']
            
            # 第3个交易日数据
            df.loc[index, 'n3o'] = result_data.iloc[7]['open']
            df.loc[index, 'n3c'] = result_data.iloc[7]['close']
            df.loc[index, 'n3h'] = result_data.iloc[7]['high']
            df.loc[index, 'n3l'] = result_data.iloc[7]['low']
            
            # 第4个交易日数据
            df.loc[index, 'n4o'] = result_data.iloc[8]['open']
            df.loc[index, 'n4c'] = result_data.iloc[8]['close']
            df.loc[index, 'n4h'] = result_data.iloc[8]['high']
            df.loc[index, 'n4l'] = result_data.iloc[8]['low']
        
            # 第-1个交易日数据
            df.loc[index, 'n-1o'] = result_data.iloc[3]['open']
            df.loc[index, 'n-1c'] = result_data.iloc[3]['close']
            df.loc[index, 'n-1h'] = result_data.iloc[3]['high']
            df.loc[index, 'n-1l'] = result_data.iloc[3]['low']
            df.loc[index, 'n-1v'] = result_data.iloc[3]['volume']
            df.loc[index, 'n-1a'] = result_data.iloc[3]['amount']

            # 第-2个交易日数据
            df.loc[index, 'n-2o'] = result_data.iloc[2]['open']
            df.loc[index, 'n-2c'] = result_data.iloc[2]['close']
            df.loc[index, 'n-2h'] = result_data.iloc[2]['high']
            df.loc[index, 'n-2l'] = result_data.iloc[2]['low']
            df.loc[index, 'n-2v'] = result_data.iloc[2]['volume']
            df.loc[index, 'n-2a'] = result_data.iloc[2]['amount']
            # 第-3个交易日数据
            df.loc[index, 'n-3o'] = result_data.iloc[1]['open']
            df.loc[index, 'n-3c'] = result_data.iloc[1]['close']
            df.loc[index, 'n-3h'] = result_data.iloc[1]['high']
            df.loc[index, 'n-3l'] = result_data.iloc[1]['low']
            df.loc[index, 'n-3v'] = result_data.iloc[1]['volume']
            df.loc[index, 'n-3a'] = result_data.iloc[1]['amount']

            # 第-4个交易日数据
            df.loc[index, 'n-4o'] = result_data.iloc[0]['open']
            df.loc[index, 'n-4c'] = result_data.iloc[0]['close']
            df.loc[index, 'n-4h'] = result_data.iloc[0]['high']
            df.loc[index, 'n-4l'] = result_data.iloc[0]['low']
            df.loc[index, 'n-4v'] = result_data.iloc[0]['volume']
            df.loc[index, 'n-4a'] = result_data.iloc[0]['amount']

    data_stocks.append(df)

# 合并所有数据并添加去重处理
combined_stocks = pd.concat(data_stocks, ignore_index=True)
combined_stocks = combined_stocks.drop_duplicates()

#对于combined_stocks中的每支股票，计算当天涨跌幅：(最新价-n0c)/n0c
combined_stocks['当天涨跌幅'] = (combined_stocks['最新价'] - combined_stocks['n0c']) / combined_stocks['n0c']
combined_stocks['当天涨跌幅'] = combined_stocks['当天涨跌幅'].apply(lambda x: f"{x*100:.2f}%")

# 计算交易后各天最高涨幅（修正公式）
for day in [1, 2, 3, 4]:
    # 正确公式：(nXh - n0c)/n0c 这里X代表交易日序号
    combined_stocks[f'交易后第{day}天最高涨幅'] = (combined_stocks[f'n{day}h'] - combined_stocks['n0c']) / combined_stocks['n0c']
    combined_stocks[f'交易后第{day}天最高涨幅'] = combined_stocks[f'交易后第{day}天最高涨幅'].apply(lambda x: f"{x*100:.2f}%")

for day in [-1, -2, -3]:
    combined_stocks[f'交易前第{day}天最高涨幅'] = (combined_stocks[f'n{day}h'] - combined_stocks['n-4c']) / combined_stocks['n-4c']
    combined_stocks[f'交易前第{day}天最高涨幅'] = combined_stocks[f'交易前第{day}天最高涨幅'].apply(lambda x: f"{x*100:.2f}%")
    combined_stocks[f'交易前第{day}天量增'] = (combined_stocks[f'n{day}v'] - combined_stocks['n-4v']) / combined_stocks['n-4v']
    combined_stocks[f'交易前第{day}天量增'] = combined_stocks[f'交易前第{day}天量增'].apply(lambda x: f"{x*100:.2f}%")
    combined_stocks[f'交易前第{day}天额增'] = (combined_stocks[f'n{day}a'] - combined_stocks['n-4a']) / combined_stocks['n-4a']
    combined_stocks[f'交易前第{day}天额增'] = combined_stocks[f'交易前第{day}天额增'].apply(lambda x: f"{x*100:.2f}%")

#保存股票数据到excel文件
combined_stocks.to_excel("combined_stocks_data.xlsx", index=False)
