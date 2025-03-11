import pandas as pd
import logging

logger = logging.getLogger('mytrade')

def check_stock_conditions(updownrate, last_price, hist_dict):
    """检查股票条件"""
    try:
        selected = False
        if pd.isnull(updownrate) or pd.isnull(last_price):
            return selected,"数据不完整"
        #hist_dict举例
        #{'股票代码': '301035', '开盘': 47.37, '收盘': 48.89, '最高': 49.36, '最低': 47.31, 
        # '成交量': 10545, '成交额': 51170954.0, '振幅': 4.32, '涨跌幅': 2.93, '涨跌额': 1.39, '换手率': 0.38, 
        # '涨幅阈值': 24.0, '历史涨幅阈值': 19.0, 
        # '布林中轨': 46.36, '布林上轨': 48.95, '布林下轨': 43.77, '5日均线': 46.95, 
        # '涨停板观察天数': 60, '涨停板观察期内最近涨停板到今天的交易日天数': 61, 
        # '最高价观察天数': 40, '最高价观察期内最高价到今天的交易日天数': 35, '最高价观察期内最高价': 52.42,
        # '趋势观察天数': 30, '趋势观察期内趋势模式': 'U', '趋势观察期内趋势R²': 0.36, '趋势观察期内趋势系数': 0.01,
        # '最大涨幅观察天数': 10, '最大涨幅观察期内最大涨幅距今天的交易日天数': 11, '最大涨幅观察期内最大涨幅': 4.16}
        
        # 检查涨跌幅是否达到阈值
        if updownrate < hist_dict.get('涨幅阈值', ''):
            result = f"涨幅不够{updownrate}<{hist_dict.get('涨幅阈值', '')}"
            return selected,result
        
        # 检查布林带条件
        if '布林上轨' in hist_dict:
            upper_band = hist_dict['布林上轨']
        else:
            logger.error(f"布林上轨不存在{hist_dict}")
            return selected,"布林上轨不存在"
        if last_price < upper_band:
            result = f"未突破布林带上轨{last_price}<{upper_band}"
            return selected,result
        
        # 检查五日均线条件
        if '5日均线' in hist_dict:
            ma_5 = hist_dict['5日均线']
        else:
            logger.error(f"5日均线不存在{hist_dict}")
            return selected,"5日均线不存在"
        if last_price <= ma_5:
            result = f"未突破五日线{last_price}<{ma_5}"
            return selected,result
        
        # 检查涨幅条件
        if '最大涨幅观察期内最大涨幅' in hist_dict:
            max_updownrate = hist_dict['最大涨幅观察期内最大涨幅']
        else:
            logger.error(f"最大涨幅观察期内最大涨幅不存在{hist_dict}")
            return selected,"最大涨幅观察期内最大涨幅不存在"
        if max_updownrate > hist_dict.get('涨幅阈值', ''):  
            result = f"最大涨幅观察期内最大涨幅{max_updownrate}>涨幅阈值{hist_dict.get('涨幅阈值', '')}"
            return selected,result

        # 检查趋势条件
        if '趋势观察期内趋势模式' in hist_dict:
            trend_mode = hist_dict['趋势观察期内趋势模式']
            if trend_mode == 'L':
                if '趋势观察期内趋势R²' in hist_dict and abs(hist_dict['趋势观察期内趋势R²']) > 0.5:
                    result = f"趋势为{trend_mode}且R²{hist_dict['趋势观察期内趋势R²']}大于0.5"
                    return selected,result
                else:
                    trend_result = f"趋势为{trend_mode}且R²{hist_dict['趋势观察期内趋势R²']}小于0.5"
            elif trend_mode == 'N':
                if '趋势观察期内趋势R²' in hist_dict and hist_dict['趋势观察期内趋势R²'] > 0.7:
                    result = f"趋势为{trend_mode}且R²{hist_dict['趋势观察期内趋势R²']}大于0.7"
                    return selected,result
                else:
                    trend_result = f"趋势为{trend_mode}但R²{hist_dict['趋势观察期内趋势R²']}小于0.7"
            else:
                trend_result = f"趋势为{trend_mode}，R²为{hist_dict['趋势观察期内趋势R²']}"
        else:
            logger.error(f"趋势观察期内趋势模式不存在{hist_dict}")
            return selected,"趋势观察期内趋势模式不存在"
        
        # 检查涨停板条件
        if '涨停板观察期内最近涨停板到今天的交易日天数' in hist_dict and '涨停板观察天数' in hist_dict:
            if hist_dict['涨停板观察期内最近涨停板到今天的交易日天数'] < hist_dict['涨停板观察天数']:
                result = f"涨停板观察期内有涨停板{hist_dict['涨停板观察期内最近涨停板到今天的交易日天数']}<{hist_dict['涨停板观察天数']}"
                return selected,result
        else:
            logger.error(f"涨停板观察期内最近涨停板到今天的交易日天数或涨停板观察天数不存在{hist_dict}")
            return selected,"涨停板观察期内最近涨停板到今天的交易日天数或涨停板观察天数不存在"
        
        # 检查最高价条件
        selected = True
        if '最高价观察期内最高价' in hist_dict:
            max_hist_price = hist_dict['最高价观察期内最高价']
            if max_hist_price > hist_dict.get('历史涨幅阈值', ''):
                result = f"符合股价低于近期最高价型{hist_dict.get('最高价观察期内最高价到今天的交易日天数', '')}天内最高价{max_hist_price}>当前价{last_price}"
                return selected,result+";"+trend_result
        else:
            logger.error(f"最高价观察期内最高价或最高价观察期内最高价距今天的交易日天数不存在{hist_dict}")
            return selected,"最高价观察期内最高价或最高价观察期内最高价距今天的交易日天数不存在"
        
        result = "符合条件"
        return selected,result+";"+trend_result
        
    except Exception as e:
        logger.error(f"检查股票条件时出错：{e}")
        return selected,"检查条件时出错"