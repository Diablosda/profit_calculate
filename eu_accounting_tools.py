import os
import pandas as pd
import chardet
import re
import numpy as np
from pathlib import Path
from typing import List, Union, Dict

# 配置字典
COUNTRY_MAPPING = {
    "德国": ["de","DE","Germany","德国"],
    "英国": ["uk","UK","GB","gb","United Kingdom","英国"],
    "意大利": ["it","IT","Italy","意大利"],
    "法国": ["fr","FR","France","法国"],
    "西班牙": ["es","ES","Spain","西班牙"],
    "荷兰": ["nl","NL","Netherlands","荷兰"],
    "比利时": ["be","BE","Belgium","比利时"],
    "波兰": ["pl","PL","Poland","波兰"],
    "瑞典": ["se","SE","Sweden","瑞典"],
    "爱尔兰": ["ie","IE","Ireland","爱尔兰"],
    "沙特":["sa","SA","Saudi Arabia","沙特"],
    "阿联酋": ["ae","AE","United Arab Emirates","阿联酋"],
    "国家":["country","country_code","国家","Country"]
}

LANGUAGE_TRANSLATE = {
    'type': ['type','Typ','Tipo','typ','tipo'],
    'Order': ['Order','Bestellung','Ordine','Commande','Pedido','Bestelling','Zamówienie'],
    'Refund': ['Refund','Terugbetaling','Reembolso','Erstattung','Rimborso','Remboursement'],
    'Shipping Services':['Versanddienstleistungen'],
    'date/time':['Datum/Uhrzei','date/heure','Data/Ora:','fecha y hora','datum/tid','datum/tijd','data/godzina','date/time'],
    'order id':['Bestellnummer','order id','numéro de la commande','Numero ordine','número de pedido','bestelnummer','identyfikator zamówienia','beställnings-id','order ID'],
    'sku':['SKU','sku'],
    'quantity':['quantity','Menge','quantité','Quantità','cantidad','aantal','ilość','antal'],
    'marketplace':['marketplace','Marketplace','web de Amazon','rynek','site de vente','marknadsplats'],
    'fulfilment':['fulfilment','Versand','traitement','Gestione','gestión logística','fulfillment','realizacja','leverans'],
    'product sales':['product sales','Ums?tze','Umsätze','Vendite','ventes de produits','ventas de productos','f?rs?ljning av produkter','verkoop van producten','sprzeda? produkt車w','försäljning av produkter'],
    'product sales tax':['Produktumsatzsteuer','Taxes sur la vente des produits','imposta sulle vendite dei prodotti','impuesto de ventas de productos','geïnde omzetbelasting','Inkasserad moms','pobrany podatek od sprzedaży','taxe de ventes prélevée','product sales tax'],
    'postage credits':['postage credits','Gutschrift für Versandkosten',"crédits d'expédition",'Accrediti per le spedizioni','abonos de envío','Verzendtegoeden','noty kredytowe za wysyłkę','fraktkrediter','crédits d’expédition','shipping credits'],
    'promotional rebates':['promotional rebates','Rabatte aus Werbeaktionen','Rabais promotionnels','Sconti promozionali','devoluciones promocionales','promotiekortingen','rabaty promocyjne','kampanjrabatter','Total des réductions'],
    'selling fees':['selling fees','Verkaufsgeb¨¹hren','frais de vente','Commissioni di vendita','tarifas de venta','f?rs?ljningsavgifter','verkoopkosten','op?aty za sprzeda?','Verkaufsgebühren'],
    'fba fees':['fba fees','Geb¨¹hren zu Versand durch Amazon','Gebühren zu Versand durch Amazon','Frais Exp¨¦di¨¦ par Amazon','Costi del servicio Logistica di Amazon','tarifas de Log赤stica de Amazon','fba-avgifter','Frais pour le service Exp¨¦di¨¦ par Amazon','fba-vergoedingen','op?aty za fba','Frais pour le service Expédié par Amazon','Frais Expédié par Amazon','tarifas de Logística de Amazon'],
    'total':['total','Gesamt','totale','totalt','totaal','suma']
}

# 目标列顺序
TARGET_COLUMNS = [
    'date/time', 'order id', 'type', 'sku', 'quantity', 'marketplace', 
    'fulfilment', 'product sales','product sales tax', 'postage credits', 
    'promotional rebates', 'selling fees', 'fba fees', 'total'
]

# 数值处理列
NUMERIC_COLUMNS = [
    'quantity', 'product sales','product sales tax', 'postage credits', 
    'promotional rebates', 'selling fees', 'fba fees', 'total'
]

def get_country_info(filename):
    """返回 (国家标准名, 国家简码)"""
    for name, aliases in COUNTRY_MAPPING.items():
        for alias in aliases:
            if alias in filename:
                return name, aliases[0]  # 返回如 ("德国", "de")
    return None, None

def detect_file_encoding(file_path):
    with open(file_path, 'rb') as f:
        detected = chardet.detect(f.read(100000))
    enc = (detected.get('encoding') or 'utf-8').strip()
    # chardet 常把“整体是 UTF-8，但采样片段恰好只有 ASCII 字节”的文件误判为 ascii。
    # 这类文件直接按 utf-8 读取通常更稳，因为 utf-8 兼容纯 ascii 内容。
    if enc.lower() in {'ascii', 'ansi_x3.4-1968'}:
        return 'utf-8'
    return enc

def read_csv_with_fallback(file_path, **kwargs):
    """
    先用探测编码读取，失败后再按常见文本编码依次回退。
    这样可以避免 chardet 将 UTF-8 文件误判为 ascii 导致解码失败。
    """
    tried = []
    primary_enc = kwargs.pop("encoding", None) or detect_file_encoding(file_path)
    encodings = [primary_enc, 'utf-8', 'utf-8-sig', 'cp1252', 'ISO-8859-1']

    last_error = None
    for enc in encodings:
        if enc in tried:
            continue
        tried.append(enc)
        try:
            return pd.read_csv(file_path, encoding=enc, **kwargs)
        except UnicodeDecodeError as e:
            last_error = e
            continue

    if last_error is not None:
        raise last_error
    raise ValueError(f"无法读取文件 {file_path}，已尝试编码: {tried}")

def clean_eu_numeric(value, country_name):
    """处理欧洲多国复杂的千分符、小数点及特殊负号"""
    if pd.isna(value) or str(value).strip() == "":
        return 0.0
    
    val_str = str(value).strip()
    
    # 1. 处理特殊负号：将 Unicode 的减号 (U+2212) 替换为标准 ASCII 负号
    # 瑞典等国报表常出现此问题
    val_str = val_str.replace('−', '-') 
    
    if country_name == "英国":
        # 英国逻辑：剔除千分符逗号，保持小数点为点
        # 例如: "1,234.56" -> "1234.56"
        val_str = val_str.replace(',', '')
    else:
        # 非英国逻辑（法、德、意、瑞典等）：
        # a. 剔除所有空格（法国、瑞典的千分符）
        val_str = val_str.replace(' ', '').replace('\xa0', '') # 包含不换行空格
        # b. 转换小数点：将逗号替换为点
        # 例如: "-19 353,69" -> "-19353.69"
        if ',' in val_str:
            val_str = val_str.replace(',', '.')

    # 2. 正则清洗：只保留数字、负号和小数点，剔除所有货币符号或非法字符
    val_str = re.sub(r'[^0-9\.-]', '', val_str)
    
    # 3. 转换
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def process_translation_reports(dir_path):
    path_obj = Path(dir_path)
    all_dfs = []
    
    # 构建反向映射表
    rev_col_map = {alias.strip().lower(): std_name for std_name, aliases in LANGUAGE_TRANSLATE.items() for alias in aliases}

    for file in path_obj.glob("**/*.csv"):
        filename = file.name
        country_name, country_code = get_country_info(filename)
        
        if not country_code:
            continue

        # 编码与跳行逻辑
        is_uk = (country_name == "英国")
        enc = 'ISO-8859-1' if is_uk else detect_file_encoding(file)
        skip_r = 8 if country_name == "阿联酋" else 9

        try:
            # 严格以 dtype=str 读取，防止读取时就被截断或损坏
            df = read_csv_with_fallback(file, skiprows=skip_r, encoding=enc, dtype=str)
            
            # 统一列名
            df.columns = [str(c).strip().lower() for c in df.columns]
            df = df.rename(columns=rev_col_map)
            
            # 补齐并过滤列
            for col in TARGET_COLUMNS:
                if col not in df.columns:
                    df[col] = "0"
            df = df[TARGET_COLUMNS].copy()

            # 应用新的数值清洗逻辑
            for col in NUMERIC_COLUMNS:
                # 针对每一行、每一列应用 clean_eu_numeric
                df[col] = df[col].apply(lambda x: clean_eu_numeric(x, country_name))
            
            # 字符串 ID 保护
            df['order id'] = df['order id'].astype(str).str.strip()
            df['sku'] = df['sku'].astype(str).str.strip()
            df['Country'] = country_code
            
            all_dfs.append(df)
            print(f"✅ 处理成功: {filename} ({country_code})")

        except Exception as e:
            print(f"❌ 报错文件 {filename}: {e}")

    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()

def process_all_statements(root_dir):
    
    #### 处理各国子目录下的 All Statements (.txt) 报表
    #### 逻辑：遍历子目录 -> 识别国家 -> 过滤 RefundCommission -> 数值清洗 -> 汇总
    path_obj = Path(root_dir)
    all_dfs = []
    
    # 定义 All Statements 内部的标准字段（针对 TXT 报表常见列名）
    # TXT 报表列名通常包含短横线，这里也做一层映射保护
    txt_col_map = {
        'transaction-type': 'type',
        'amount-description': 'description',
        'amount': 'amount',
        'sku': 'sku',
        'order-id': 'order id'
    }

    # 1. 递归遍历目录下所有 .txt 文件 (包含各子目录)
    for file in path_obj.rglob("*.txt"):
        filename = file.name
        # 考虑到文件可能按国家分文件夹存放，同时检查父文件夹名和文件名来确定国家
        # 例如：./All_Statements/Germany/report.txt
        search_scope = f"{file.parent.name}_{filename}"
        country_name, country_code = get_country_info(search_scope)
        
        if not country_code:
            # 如果文件夹名和文件名都没匹配到，跳过
            continue

        # 2. 识别编码并读取 (All Statements 通常为 tab 分隔)
        # 英国 TXT 有时也会用 ISO-8859-1，为了保险动态识别
        enc = detect_file_encoding(file)
        
        try:
            # 严格以 dtype=str 读取，防止 Order ID 被转为浮点数
            df = read_csv_with_fallback(file, sep='\\t', encoding=enc, dtype=str)
            
            # 3. 列名标准化
            df.columns = [str(c).strip().lower() for c in df.columns]
            # 兼容处理：将 'transaction-type' 等映射为易处理的名称
            df = df.rename(columns=txt_col_map)
            
            # 4. 核心过滤逻辑：仅保留 Refund 且为 RefundCommission 的记录
            if 'type' in df.columns and 'description' in df.columns:
                mask = (df['type'].str.lower() == 'refund') & \
                       (df['description'].str.lower() == 'refundcommission')
                df = df[mask].copy()
            else:
                # 如果报表格式不对，跳过
                continue

            if df.empty:
                continue

            # 5. 数值清洗：应用之前验证过的极致清洗逻辑
            # 注意：All Statements 的金额通常在 'amount' 列
            if 'amount' in df.columns:
                df['amount'] = df['amount'].apply(lambda x: clean_eu_numeric(x, country_name))
            
            # 6. 字符串字段保护
            for col in ['order id', 'sku']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
            
            # 7. 注入 Country 简码
            df['Country'] = country_code
            
            all_dfs.append(df)
            print(f"✅ 已处理 {country_name} TXT: {filename} (提取到 {len(df)} 行 RefundCommission)")

        except Exception as e:
            print(f"❌ 读取 TXT 失败 {filename}: {e}")

    if not all_dfs:
        print("⚠️ 未在指定目录下找到任何有效的 All Statements 数据。")
        return pd.DataFrame()

    # 8. 合并全欧数据
    final_statements = pd.concat(all_dfs, ignore_index=True)
    return final_statements

# 1. 基础工具函数 (引自 matching_tools_new.py)

def find_col(df, candidates):
    """从候选列表中匹配 DataFrame 实际存在的列名"""
    if isinstance(candidates, str):
        candidates = [candidates]
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand is None: continue
        lc = str(cand).strip().lower()
        if lc in lower_map:
            return lower_map[lc]
    return None

def norm_str(x):
    """标准化字符串，用于字典键匹配"""
    if isinstance(x, pd.Series):
        x = x.iloc[0] if len(x) else None
    if x is None: return None
    try:
        if pd.isna(x): return None
    except Exception: pass
    s = str(x).strip()
    return s.upper() if s != "" else None

def build_norm_map(df, key_col, value_col):
    """构建标准化映射字典"""
    out: Dict[str, object] = {}
    if key_col is None or value_col is None:
        return out
    for _, row in df[[key_col, value_col]].iterrows():
        k = norm_str(row[key_col])
        if k is not None and k not in out:
            out[k] = row[value_col]
    return out

def lookup_value_with_fallback_for_series(df, df_sku_col, df_asin_col, ref_df, 
                                          ref_msku_col, ref_asin_col, ref_value_col):
    """级联查询：先查 SKU，查不到再查 ASIN"""
    if ref_value_col is None:
        return [None] * len(df)
    
    msku_map = build_norm_map(ref_df, ref_msku_col, ref_value_col) if ref_msku_col else {}
    asin_map = build_norm_map(ref_df, ref_asin_col, ref_value_col) if ref_asin_col else {}
    
    sku_series = df[df_sku_col] if df_sku_col else pd.Series([None]*len(df), index=df.index)
    asin_series = df[df_asin_col] if df_asin_col else pd.Series([None]*len(df), index=df.index)
    
    results = []
    for sku_raw, asin_raw in zip(sku_series, asin_series):
        val = None
        sku_norm = norm_str(sku_raw)
        asin_norm = norm_str(asin_raw)
        if sku_norm and msku_map:
            val = msku_map.get(sku_norm)
        if val is None and asin_norm and asin_map:
            val = asin_map.get(asin_norm)
        results.append(val)
    return results

# 2. 核心匹配引擎

def match_fields_to_df_robust(df, target_field, product_property, country=None):
    """执行单个字段的鲁棒性匹配 (支持 Amazon.Found. SKU 自动解析)"""
    df = df.copy()
    sku_candidates = ["sku", "SKU", "msku", "MSKU"]
    asin_candidates = ["ASIN", "asin"]
    
    df_sku_col = find_col(df, sku_candidates)
    df_asin_col = find_col(df, asin_candidates)
    
    # 自动解析 Amazon.Found. 格式的 SKU
    if df_sku_col and df_asin_col:
        asin_missing = df[df_asin_col].isna() | (df[df_asin_col].astype(str).str.strip() == "")
        def extract_asin(val):
            s = str(val).strip()
            if s.lower().startswith("amazon.found.") and len(s) >= 10:
                return s[-10:].upper()
            return None
        if asin_missing.any():
            extracted = df.loc[asin_missing, df_sku_col].apply(extract_asin)
            df.loc[asin_missing, df_asin_col] = df.loc[asin_missing, df_asin_col].fillna(extracted)

    prop_msku_col = find_col(product_property, ["MSKU", "msku", "SKU", "sku"])
    prop_asin_col = find_col(product_property, ["ASIN", "asin"])
    
    # 国家过滤
    ref_prop = product_property.copy()
    if country is not None:
        country_col = find_col(product_property, ["国家", "Country"])
        if country_col:
            ref_prop = ref_prop[ref_prop[country_col].astype(str).str.strip().str.upper() == str(country).upper()]

    # 准备标准化键
    df["_sku_norm"] = df[df_sku_col].apply(norm_str) if df_sku_col else None
    df["_asin_norm"] = df[df_asin_col].apply(norm_str) if df_asin_col else None
    
    # 字段映射
    field_map = {
        "物料大类": ["物料大类"],
        "运营负责人(核算参考)": ["上月运营负责人(核算参考)", "上月运营负责人"],
        "产品重要性": ["产品重要性"],
        "采购价(不含税)": ["采购价", "采购价(不含税)"],
        "头程": ["头程"],
    }
    candidates = field_map.get(target_field, [target_field])
    ref_val_col = find_col(ref_prop, candidates)
    
    if ref_val_col:
        df[target_field] = lookup_value_with_fallback_for_series(
            df, "_sku_norm", "_asin_norm", ref_prop, prop_msku_col, prop_asin_col, ref_val_col
        )
    
    df.drop(columns=["_sku_norm", "_asin_norm"], inplace=True, errors="ignore")
    return df

# 3. 欧洲专用批量匹配函数

def batch_match_fields_and_export_unmatched_eu(
    source_tables: Dict[str, pd.DataFrame],
    product_property: pd.DataFrame,
    country_mapping: dict,
    output_path="欧洲未匹配记录.csv"
):
    """
    欧洲站分流匹配主函数 - 修复版
    解决：标识符互补失效、反向一对多匹配、标签显示异常等问题
    """
    target_fields = ["上月运营负责人(核算参考)", "产品重要性", "采购价(不含税)", "头程"]
    processed = {}
    unmatched_rows = []

    # --- 1. 预处理属性表 ---
    # 强制转换 MSKU/ASIN 为纯字符串，并去除首尾空格
    for col in ['MSKU', 'ASIN']:
        if col in product_property.columns:
            product_property[col] = product_property[col].astype(str).str.strip().replace({'nan': np.nan, 'None': np.nan, '': np.nan})

    prop_country_col = find_col(product_property, country_mapping.get("国家", ["国家", "Country"]))
    if not prop_country_col:
        raise KeyError("属性表中缺失'国家'列，无法进行分流匹配。")
    
    prop_uk = product_property[product_property[prop_country_col].astype(str).str.upper() == "UK"].copy()
    prop_eu = product_property[product_property[prop_country_col].astype(str).str.upper() == "EU"].copy()
    
    # 构造映射字典 (ASIN -> MSKU 时取第一条记录)
    def create_mapping(p_df):
        clean = p_df.dropna(subset=['MSKU', 'ASIN'])
        # MSKU -> ASIN (通常是一对一)
        m2a = clean.drop_duplicates('MSKU').set_index('MSKU')['ASIN'].to_dict()
        # ASIN -> MSKU (一对多，取第一个)
        a2m = clean.drop_duplicates('ASIN', keep='first').set_index('ASIN')['MSKU'].to_dict()
        return m2a, a2m

    uk_m2a, uk_a2m = create_mapping(prop_uk)
    eu_m2a, eu_a2m = create_mapping(prop_eu)

    uk_aliases = [str(a).strip().lower() for a in country_mapping.get("英国", [])]

    # --- 2. 遍历处理源表 ---
    for name, df in source_tables.items():
        if isinstance(df, list):
            df = df[0] if len(df) > 0 else pd.DataFrame()

        cur = df.copy()
        
        # 寻找或创建核心列
        sku_col = find_col(cur, ["msku", "MSKU", "sku", "SKU"])
        asin_col = find_col(cur, ["asin", "ASIN"])
        src_country_col = find_col(cur, country_mapping.get("国家", ["国家", "Country"]))
        
        if not src_country_col:
            print(f"⚠️ 跳过 {name}: 未找到国家列")
            processed[name] = cur
            continue

        # 如果源表缺失 SKU 或 ASIN 其中的一列，则初始化为空列以便填充
        if not sku_col:
            cur['MSKU'] = np.nan
            sku_col = 'MSKU'
        if not asin_col:
            cur['ASIN'] = np.nan
            asin_col = 'ASIN'

        # 统一清洗源表中的标识符格式
        for c in [sku_col, asin_col]:
            cur[c] = cur[c].astype(str).str.strip().replace({'nan': np.nan, 'None': np.nan, '': np.nan})

        # --- A. MSKU 和 ASIN 互相补齐 (根据国家分流补齐) ---
        is_uk_mask = cur[src_country_col].astype(str).str.strip().str.lower().isin(uk_aliases)
        
        # 补齐逻辑：UK
        cur.loc[is_uk_mask & cur[asin_col].isna(), asin_col] = cur.loc[is_uk_mask, sku_col].map(uk_m2a)
        cur.loc[is_uk_mask & cur[sku_col].isna(), sku_col] = cur.loc[is_uk_mask, asin_col].map(uk_a2m)
        # 补齐逻辑：EU
        cur.loc[~is_uk_mask & cur[asin_col].isna(), asin_col] = cur.loc[~is_uk_mask, sku_col].map(eu_m2a)
        cur.loc[~is_uk_mask & cur[sku_col].isna(), sku_col] = cur.loc[~is_uk_mask, asin_col].map(eu_a2m)

        # --- B. 分流匹配业务字段 (target_fields) ---
        df_uk = cur[is_uk_mask].copy()
        df_eu = cur[~is_uk_mask].copy()

        for f in target_fields:
            if not df_uk.empty:
                df_uk = match_fields_to_df_robust(df_uk, f, prop_uk)
            if not df_eu.empty:
                df_eu = match_fields_to_df_robust(df_eu, f, prop_eu)

        # 合并并恢复原始顺序
        cur_matched = pd.concat([df_uk, df_eu]).sort_index()

        # --- C. 缺失统计与打标逻辑修正 ---
        # 综合判定：MSKU缺失 OR ASIN缺失 OR 业务字段缺失
        mask_id_na = cur_matched[sku_col].isna() | cur_matched[asin_col].isna()
        mask_target_na = cur_matched[target_fields].isna().any(axis=1)
        final_unmatched_mask = mask_id_na | mask_target_na

        if final_unmatched_mask.any():
            unmatched = cur_matched[final_unmatched_mask].copy()
            unmatched["源表"] = name
            
            # --- 新增：生成“表名-行号”格式的缺失标签 ---
            # 这确保了即便没有 ASIN/MSKU，手动填写后也能回填到源表的对应位置
            unmatched["缺失标签"] = [f"{name}-{i}" for i in unmatched.index]
            
            # 缺失状态判定逻辑保持不变
            unmatched["缺失状态"] = "" 
            both_missing = (unmatched[sku_col].isna()) & (unmatched[asin_col].isna())
            unmatched.loc[both_missing, "缺失状态"] = "MSKU与ASIN均缺失"
            
            # 统一输出列名
            unmatched["SKU_Final"] = unmatched[sku_col]
            unmatched["ASIN_Final"] = unmatched[asin_col]
            
            # 提取导出列（加入“缺失标签”）
            export_cols = ["源表", "缺失标签", "SKU_Final", "ASIN_Final", "缺失状态"] + target_fields
            unmatched_rows.append(unmatched[export_cols])

        processed[name] = cur_matched

    # --- 3. 最终汇总与导出 ---
    if unmatched_rows:
        df_unmatched = pd.concat(unmatched_rows, ignore_index=True)
        # 强制将输出的 nan 转回空字符串，确保 CSV 看起来整洁
        df_unmatched = df_unmatched.fillna("")
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True) if os.path.dirname(output_path) else None
        df_unmatched.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"✅ 处理完成。已导出 {len(df_unmatched)} 条异常/缺失记录。")
    else:
        df_unmatched = pd.DataFrame()
        print("✅ 恭喜，所有记录匹配完整。")

    return processed, df_unmatched

def refill_from_unmatched_eu(
    source_tables: Dict[str, pd.DataFrame],
    updated_unmatched_df: pd.DataFrame,
    target_fields: list = None
):
    """
    回填函数：将手动补全的未匹配记录表更新回源表
    """
    if target_fields is None:
        target_fields = ["上月运营负责人(核算参考)", "产品重要性", "采购价(不含税)", "头程"]

    def _normalize_series_to_na(s: pd.Series) -> pd.Series:
        return s.astype(str).str.strip().replace({"nan": np.nan, "None": np.nan, "": np.nan})

    def _empty_mask(s: pd.Series) -> pd.Series:
        if s is None:
            return pd.Series([True] * 0, dtype=bool)
        normalized = _normalize_series_to_na(s)
        return normalized.isna()
    
    # 清洗回填表：去重并确保字符串干净
    updated_unmatched_df = updated_unmatched_df.drop_duplicates().copy()
    for col in ["缺失标签", "SKU_Final", "ASIN_Final"]:
        if col in updated_unmatched_df.columns:
            updated_unmatched_df[col] = _normalize_series_to_na(updated_unmatched_df[col])

    result = {}

    for name, df in source_tables.items():
        cur = df.copy()
        # 筛选出属于当前表的补全记录
        # 注意：这里回填表里的列名是“源表”，需要与导出时一致
        sub = updated_unmatched_df[updated_unmatched_df["源表"] == name]
        
        if sub.empty:
            result[name] = cur
            continue

        # 1. 寻找源表中的标识符列
        asin_col = find_col(cur, ["ASIN", "asin"])
        sku_col = find_col(cur, ["sku", "SKU", "MSKU", "msku"])
        
        # 2. 确保源表中有“缺失标签”列，用于点对点回填
        if "缺失标签" not in cur.columns:
            cur["缺失标签"] = [f"{name}-{i}" for i in cur.index]
        else:
            cur["缺失标签"] = _normalize_series_to_na(cur["缺失标签"])

        if asin_col:
            cur[asin_col] = _normalize_series_to_na(cur[asin_col])
        if sku_col:
            cur[sku_col] = _normalize_series_to_na(cur[sku_col])

        # 3. 遍历目标字段进行回填
        for f in target_fields:
            if f not in cur.columns:
                cur[f] = np.nan
            else:
                cur[f] = _normalize_series_to_na(cur[f])
            
            # --- 逻辑 A：基于 MSKU/ASIN 回填业务字段 ---
            # 排除掉标识符列本身的回填，标识符建议通过标签回填
            if f.lower() not in ["asin", "sku", "msku", "sku_final", "asin_final"]:
                mask_na = _empty_mask(cur[f])
                
                # 基于 ASIN 映射
                if asin_col and "ASIN_Final" in sub.columns:
                    asin_map = sub.dropna(subset=["ASIN_Final", f]).set_index("ASIN_Final")[f].to_dict()
                    cur.loc[mask_na, f] = cur.loc[mask_na, asin_col].map(asin_map)
                
                # 基于 SKU 映射 (补全 ASIN 映射没抓到的部分)
                mask_na = _empty_mask(cur[f])
                if sku_col and "SKU_Final" in sub.columns:
                    sku_map = sub.dropna(subset=["SKU_Final", f]).set_index("SKU_Final")[f].to_dict()
                    cur.loc[mask_na, f] = cur.loc[mask_na, sku_col].map(sku_map)

            # --- 逻辑 B：基于“缺失标签”精准回填 (最高优先级/兜底) ---
            # 无论是标识符还是业务字段，只要标签对得上，就强行覆盖空值
            mask_na = _empty_mask(cur[f])
            if "缺失标签" in sub.columns:
                # 处理标识符字段的特殊映射关系
                sub_field = f
                if f.upper() == "ASIN" and "ASIN_Final" in sub.columns: sub_field = "ASIN_Final"
                if f.upper() in ["MSKU", "SKU"] and "SKU_Final" in sub.columns: sub_field = "SKU_Final"
                
                if sub_field in sub.columns:
                    tag_map = sub.dropna(subset=["缺失标签", sub_field]).set_index("缺失标签")[sub_field].to_dict()
                    cur.loc[mask_na, f] = cur.loc[mask_na, "缺失标签"].map(tag_map)

        # --- 4. 同步 SKU 到 MSKU ---
        # 欧洲逻辑：如果 MSKU 为空且已经通过回填拿到了 SKU 值，则同步
        if "MSKU" not in cur.columns:
            cur["MSKU"] = np.nan
        
        # 针对有缺失标签的行（即之前导出的异常行），确保 MSKU 与 SKU 一致
        current_sku_val = cur[sku_col] if sku_col else np.nan
        # 只在 MSKU 依然缺失的情况下，用当前最新的 SKU 值覆盖
        cur["MSKU"] = cur["MSKU"].fillna(current_sku_val)

        result[name] = cur

    return result

def fill_from_update_tables(target_dfs, columns_to_fill, match_key_column="ASIN"):
    if isinstance(columns_to_fill, str):
        columns_to_fill = [columns_to_fill]
    if not isinstance(target_dfs, list):
        target_dfs = [target_dfs]
        return_single = True
    else:
        return_single = False
    import inspect

    try:
        variable_context = inspect.currentframe().f_back.f_globals
    except AttributeError:
        variable_context = globals()
    results = []
    for main_df in target_dfs:
        main_name = None
        for name, obj in variable_context.items():
            if obj is main_df:
                main_name = name
                break
        if main_name is None:
            results.append(main_df)
            continue
        update_name = f"{main_name}_na_update"
        if update_name not in variable_context:
            results.append(main_df)
            continue
        update_df = variable_context[update_name]
        if match_key_column not in main_df.columns or match_key_column not in update_df.columns:
            results.append(main_df)
            continue
        for col in columns_to_fill:
            if update_df.empty:
                continue
            if col not in update_df.columns:
                continue
            update_subset = update_df.dropna(subset=[col, match_key_column])
            if update_subset.empty:
                continue
            asin_to_value_map = update_subset.set_index(match_key_column)[col].to_dict()
            mask = main_df[col].isna() & main_df[match_key_column].isin(asin_to_value_map.keys())
            main_df.loc[mask, col] = main_df.loc[mask, match_key_column].map(asin_to_value_map)
        results.append(main_df)
    return results[0] if return_single else results
