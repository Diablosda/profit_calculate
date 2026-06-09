import numpy as np
import pandas as pd
import pymysql
import sys
import inspect
from typing import List, Union

def create_flexible_pivot(   # 数据透视表函数
    df: pd.DataFrame, 
    index_cols: Union[str, List[str]], 
    value_col: Union[str, List[str]], 
    agg_func: Union[str, List[str]] = 'sum'
) -> pd.DataFrame:
    """
    创建一个灵活的数据透视表，支持多个 index、多个 value、多个聚合函数。

    Args:
        df (pd.DataFrame): 待透视的 DataFrame。
        index_cols (Union[str, List[str]]): 用作透视表行/索引的列名。
        value_col (Union[str, List[str]]): 进行聚合的列，可为单列或多列。
        agg_func (Union[str, List[str]]): 聚合函数，可为单个函数或多个函数。

    Returns:
        pd.DataFrame: 创建好的数据透视表 DataFrame。
    """

    # index_cols → list
    if isinstance(index_cols, str):
        index_cols = [index_cols]

    # value_col → list
    if isinstance(value_col, str):
        value_cols = [value_col]
    else:
        value_cols = value_col

    # 校验列
    required_cols = index_cols + value_cols
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"DataFrame 缺少必需的列: {missing_cols}")

    try:
        pivot_table = pd.pivot_table(
            df,
            index=index_cols,
            values=value_cols,
            aggfunc=agg_func
        )
        return pivot_table
    except Exception as e:
        print(f"创建透视表时发生错误: {e}")
        raise


def process_pivot_and_concat(  # 字符串拼接函数
    pivot_df: pd.DataFrame, 
    index_levels: List[str], 
    new_field_prefix: str = "sinowell-",  # 调整后的可自定义前缀参数
    sep: str = "",
    reset_index: bool = True
) -> pd.DataFrame:
    """
    处理 MultiIndex 数据透视表：拼接索引层级并进行文字替换。

    Args:
        pivot_df (pd.DataFrame): 具有 MultiIndex 的数据透视表。
        index_levels (List[str]): 用于拼接的索引层级名称列表 (例如：['产品负责人', '属性'])。
        new_field_prefix (str): 拼接字段的前缀。默认为 "ABC-"。
        sep (str): 索引层级之间的分隔符 (例如: "-")。默认为 "-"。
        reset_index (bool): 是否在返回前将索引转换为普通列。默认为 True。

    Returns:
        pd.DataFrame: 包含 '新拼接字段' 的 DataFrame。
    """
    
    # --- 参数检查与准备 ---
    if not isinstance(pivot_df.index, pd.MultiIndex):
        raise TypeError("输入的 DataFrame 索引不是 MultiIndex。")
        
    if not all(level in pivot_df.index.names for level in index_levels):
        missing = [level for level in index_levels if level not in pivot_df.index.names]
        raise ValueError(f"索引中缺少层级名称: {missing}")

    # 1. 提取所有索引层级的值并转换为字符串
    levels_data = [
        pivot_df.index.get_level_values(level).astype(str) 
        for level in index_levels
    ]

    # 2. 执行拼接
    # 从前缀和第一个层级开始
    new_field_series = new_field_prefix + levels_data[0]
    
    # 依次拼接后续层级
    for i in range(1, len(levels_data)):
        new_field_series = new_field_series.str.cat(levels_data[i], sep=sep)

    # 3. 执行文字替换 (替代功能)
    new_field_series = (
        new_field_series
        # 替换 '新品' 为 '新'
        .str.replace('新品', '新', regex=False)
        # 替换 '重点产品', '旧'
        .str.replace('重点产品', '旧', regex=False)
    )

    # 4. 赋值给 DataFrame
    pivot_df['新拼接字段'] = new_field_series

    # 5. 可选：转换索引为普通列
    if reset_index:
        pivot_df = pivot_df.reset_index()

    return pivot_df


def fill_from_update_tables(target_dfs, columns_to_fill, match_key_column='ASIN'):  # 空字段填充函数
    """
    根据命名约定自动查找内存中的 '_na_update' 表，并用其数据填充目标表中的空值。

    参数:
    - target_dfs (pd.DataFrame 或 list): 需要填充的主表(DataFrame) 或主表的列表。
    - columns_to_fill (str 或 list): 需要填充的目标列名，例如 '产品负责人'。
    - match_key_column (str): 用于匹配的唯一标识符列名，例如 'ASIN' 或 'SKU'。 (新增参数)

    返回:
    - 如果传入单个 DataFrame，返回填充后的该 DataFrame。
    - 如果传入 DataFrame 列表，返回包含所有填充后的 DataFrame 的列表。
    
    注意: 函数直接在传入的 DataFrame 对象上进行修改（In-Place Modification）。
    """
    
    # --- 1. 参数准备 ---
    if isinstance(columns_to_fill, str):
        columns_to_fill = [columns_to_fill]

    if not isinstance(target_dfs, list):
        target_dfs = [target_dfs]
        return_single = True
    else:
        return_single = False
    
    # 获取调用者命名空间中的所有变量
    try:
        variable_context = inspect.currentframe().f_back.f_globals
    except AttributeError:
        variable_context = globals()

    results = []

    # --- 2. 循环处理每个目标表 ---
    for main_df in target_dfs:
        main_name = None
        for name, obj in variable_context.items():
            if obj is main_df:
                main_name = name
                break
        
        if main_name is None:
            print(f"警告: 无法在内存中找到 DataFrame 的变量名，跳过该表。")
            results.append(main_df)
            continue
            
        update_name = f"{main_name}_na_update"
        
        # 动态获取更新表对象
        if update_name not in variable_context:
            print(f"警告: 找不到更新表 '{update_name}'，跳过 {main_name} 的填充。")
            results.append(main_df)
            continue

        update_df = variable_context[update_name]
        
        # --- 3. 检查匹配键列是否存在 ---
        if match_key_column not in main_df.columns or match_key_column not in update_df.columns:
            print(f"错误: 主表或更新表缺少匹配键列 '{match_key_column}'，跳过 {main_name}。")
            results.append(main_df)
            continue

        # --- 4. 遍历需要填充的列 ---
        for col in columns_to_fill:
            
            # --- 检查和跳过逻辑 ---
            if update_df.empty:
                print(f"信息: {update_name} 表为空，跳过字段 '{col}'。")
                continue
            
            if col not in update_df.columns:
                print(f"警告: {update_name} 缺少目标填充列 '{col}'，跳过。")
                continue
            
            # 核心映射：去除非空行，并创建字典
            update_subset = update_df.dropna(subset=[col, match_key_column]) # 确保匹配键也非空
            if update_subset.empty:
                 print(f"信息: {update_name} 中 '{col}' 字段或 '{match_key_column}' 字段全部为空，跳过。")
                 continue

            # 使用传入的 match_key_column 作为索引创建映射字典
            asin_to_value_map = update_subset.set_index(match_key_column)[col].to_dict()

            # --- 5. 填充逻辑 ---
            # 使用传入的 match_key_column 进行 Series 查找
            mask = main_df[col].isna() & main_df[match_key_column].isin(asin_to_value_map.keys())

            main_df.loc[mask, col] = main_df.loc[mask, match_key_column].map(asin_to_value_map)
            
            print(f"完成: {main_name} - 填充了 {mask.sum()} 行 '{col}' 字段 (基于键: {match_key_column})。")
            
        results.append(main_df)

    # 根据传入的类型返回结果
    return results[0] if return_single else results
