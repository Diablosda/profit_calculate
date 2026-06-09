import pandas as pd

# ---------------- helper: 列名模糊查找 ----------------
def find_col(df, candidates):
    """
    在 df 中按 candidates 列名列表（一系列可能的名称）模糊匹配列名（不区分大小写）。
    返回第一个找到的实际列名字符串；找不到返回 None。
    """
    if isinstance(candidates, str):
        candidates = [candidates]
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand is None:
            continue
        lc = cand.lower()
        if lc in lower_map:
            return lower_map[lc]
    return None

# ---------------- helper: 规范化字符串用于匹配 ----------------
def norm_str(x):
    """把值转换成统一比较形式：str->strip->upper；None/NaN->None"""
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s == "":
        return None
    return s.upper()

# ---------------- helper: 从SKU中提取ASIN ----------------
def extract_asin_from_sku(sku_val):
    """
    逻辑：如果 sku 长度 > 10 且后 10 位以 'B0' 开头 (不区分大小写)，
    则截取后 10 位作为 ASIN。
    """
    if pd.isna(sku_val):
        return None
    s = str(sku_val).strip()
    if len(s) > 10:
        suffix = s[-10:]
        if suffix.upper().startswith("B0"):
            return suffix.upper()
    return None

# ---------------- 逐步前缀匹配 ----------------
def progressive_prefix_match_norm(sku_norm, msku_map):
    """
    sku_norm: 已规范化（upper）的 sku 字符串
    msku_map: dict: normalized_msku -> value
    逐步从整个 sku 长度缩短到 1，尝试匹配 msku_map 中的键。
    """
    if not sku_norm:
        return None
    L = len(sku_norm)
    for length in range(L, 0, -1):
        prefix = sku_norm[:length]
        if prefix in msku_map:
            return msku_map[prefix]
    return None

# ---------------- 构造映射（normalized key -> value） ----------------
def build_norm_map(df, key_col, value_col):
    out = {}
    if key_col is None or value_col is None:
        return out
    for _, row in df[[key_col, value_col]].iterrows():
        k = norm_str(row[key_col])
        if k is None:
            continue
        # 仅保留第一个遇到的
        if k not in out:
            out[k] = row[value_col]
    return out

def lookup_value_precise_then_prefix_for_series(df,
                                               df_sku_col_actual,
                                               df_asin_col_actual,
                                               ref_df,
                                               ref_msku_col_actual,
                                               ref_asin_col_actual,
                                               ref_value_col_actual):
    msku_map = build_norm_map(ref_df, ref_msku_col_actual, ref_value_col_actual)
    asin_map = build_norm_map(ref_df, ref_asin_col_actual, ref_value_col_actual)
    results = []
    if df_sku_col_actual is None:
        sku_series = pd.Series([None]*len(df))
    else:
        sku_series = df[df_sku_col_actual]
    if df_asin_col_actual is None:
        asin_series = pd.Series([None]*len(df))
    else:
        asin_series = df[df_asin_col_actual]
    for sku_raw, asin_raw in zip(sku_series, asin_series):
        val = None
        sku_norm = norm_str(sku_raw)
        asin_norm = norm_str(asin_raw)
        if sku_norm:
            val = msku_map.get(sku_norm)
        if val is None and asin_norm:
            val = asin_map.get(asin_norm)
        if val is None and sku_norm:
            val = progressive_prefix_match_norm(sku_norm, msku_map)
        results.append(val)
    return results

# ---------------- 核心查找功能 ----------------
def lookup_value_with_fallback_for_series(df,
                                         df_sku_col_actual,
                                         df_asin_col_actual,
                                         ref_df,
                                         ref_msku_col_actual,
                                         ref_asin_col_actual,
                                         ref_value_col_actual):
    """
    1) SKU -> MSKU 逐步前缀匹配
    2) ASIN -> ASIN 精确匹配
    """
    # 构建映射
    msku_map = build_norm_map(ref_df, ref_msku_col_actual, ref_value_col_actual)
    asin_map = build_norm_map(ref_df, ref_asin_col_actual, ref_value_col_actual)

    results = []
    
    # 准备 Series
    if df_sku_col_actual is None:
        sku_series = pd.Series([None]*len(df))
    else:
        sku_series = df[df_sku_col_actual]

    if df_asin_col_actual is None:
        asin_series = pd.Series([None]*len(df))
    else:
        asin_series = df[df_asin_col_actual]

    # 遍历查找
    for sku_raw, asin_raw in zip(sku_series, asin_series):
        val = None
        sku_norm = norm_str(sku_raw)
        asin_norm = norm_str(asin_raw)

        # 1. 尝试 SKU 前缀匹配
        if sku_norm:
            val = progressive_prefix_match_norm(sku_norm, msku_map)

        # 2. 尝试 ASIN 精确匹配
        if val is None and asin_norm:
            val = asin_map.get(asin_norm)

        results.append(val)
    return results

# ---------------- 解析来源表逻辑 ----------------
def resolve_source(ref_calc, ref_prop, target_field, use_ca_flag,
                   calculate_information, calculate_information_ca,
                   product_property, product_property_ca):
    """
    根据 use_ca_flag (True/False) 决定只看 US 还是只看 CA 组的表。
    """
    # 根据传入的 flag 严格选择表对象
    calc = calculate_information_ca if use_ca_flag else calculate_information
    prop = product_property_ca if use_ca_flag else product_property

    # 1. 常见字段规则
    if target_field in ["采购价", "头程" ]:
        ref_df = calc
        ref_msku = find_col(ref_df, ["MSKU", "msku", "Msku"])
        ref_asin = find_col(ref_df, ["ASIN", "asin"])
        ref_value = find_col(ref_df, [target_field])
        if ref_value is None:
            raise KeyError(f"在 {'CA表' if use_ca_flag else 'US表'} (Calculate Info) 中未找到字段 {target_field}")
        return ref_df, ref_msku, ref_asin, ref_value

    if target_field in ["产品负责人", "属性", "12月负责", "产品重要性"]:
        ref_df = calc
        ref_msku = find_col(ref_df, ["MSKU", "msku"])
        ref_asin = find_col(ref_df, ["ASIN", "asin"])
        mapping = {"产品负责人": ["12月负责", "负责人", "产品负责人"],
                   "属性": ["产品重要性", "属性"]}
        candidates = mapping.get(target_field, [target_field])
        ref_value = find_col(ref_df, candidates)
        # 尝试模糊匹配 "负责"
        if ref_value is None and target_field in ["产品负责人", "12月负责"]:
            for col in ref_df.columns:
                if "负责" in str(col):
                    ref_value = col
                    break
        if ref_value is None:
            raise KeyError(f"在 {'CA表' if use_ca_flag else 'US表'} (Calculate Info) 中未找到字段对应 {target_field}")
        return ref_df, ref_msku, ref_asin, ref_value

    if target_field in ["新分类一", "2024年11月始系统新分类一"]:
        ref_df = prop
        ref_msku = find_col(ref_df, ["MSKU", "msku"])
        ref_asin = find_col(ref_df, ["ASIN", "asin"])
        ref_value = find_col(ref_df, ["2024年11月始系统新分类一", "新分类一", "系统新分类一"])
        if ref_value is None:
            raise KeyError(f"在 {'CA表' if use_ca_flag else 'US表'} (Product Property) 中未找到字段 新分类一")
        return ref_df, ref_msku, ref_asin, ref_value

    # 特殊字段：单个产品体积 在 US 表名为 "单个产品体积"，在 CA 表名为 "单品体积"
    if target_field == "单个产品体积":
        ref_df = calc
        ref_msku = find_col(ref_df, ["MSKU", "msku"])
        ref_asin = find_col(ref_df, ["ASIN", "asin"])
        if use_ca_flag:
            candidates = ["单品体积", "单个产品体积"]
        else:
            candidates = ["单个产品体积", "单品体积"]
        ref_value = find_col(ref_df, candidates)
        if ref_value is None:
            raise KeyError(f"在 {'CA表' if use_ca_flag else 'US表'} (Calculate Info) 中未找到字段 {target_field}")
        return ref_df, ref_msku, ref_asin, ref_value

    # 2. 通用规则 (Calc -> Prop)
    ref_df = calc
    ref_msku = find_col(ref_df, ["MSKU", "msku"])
    ref_asin = find_col(ref_df, ["ASIN", "asin"])
    ref_value = find_col(ref_df, [target_field])
    if ref_value is not None:
        return ref_df, ref_msku, ref_asin, ref_value

    ref_df = prop
    ref_msku = find_col(ref_df, ["MSKU", "msku"])
    ref_asin = find_col(ref_df, ["ASIN", "asin"])
    ref_value = find_col(ref_df, [target_field])
    if ref_value is not None:
        return ref_df, ref_msku, ref_asin, ref_value

    raise KeyError(f"在 {'CA' if use_ca_flag else 'US'} 的 Calculate/Property 表中均未找到字段 {target_field}")


# ---------------- 主函数：Robust 匹配 (逻辑升级版) ----------------
def match_fields_to_df_robust(df,
                              target_field,
                              calculate_information,
                              calculate_information_ca,
                              product_property,
                              product_property_ca,
                              use_ca=False,
                              prefer_ca_first=None,
                              source_field_name=None,
                              sku_col_candidates=None,
                              asin_col_candidates=None,
                              fnsku_col_candidates=None):
    
    # --- 1. 初始化列名候选 ---
    if sku_col_candidates is None: sku_col_candidates = ["sku", "SKU"]
    if asin_col_candidates is None: asin_col_candidates = ["ASIN", "asin"]
    if fnsku_col_candidates is None: fnsku_col_candidates = ["fnsku", "FNSKU", "FNSku", "FNSku"]

    # --- 2. 查找并统一 ASIN 列 ---
    df_sku_col = find_col(df, sku_col_candidates)
    df_asin_col = find_col(df, asin_col_candidates)
    df_fnsku_col = find_col(df, fnsku_col_candidates)

    target_asin_col_name = "ASIN"
    # 确保有一个叫 "ASIN" 的列
    if df_asin_col is None:
        df[target_asin_col_name] = pd.NA
        df_asin_col = target_asin_col_name
    else:
        if df_asin_col != target_asin_col_name:
            df[target_asin_col_name] = df[df_asin_col]
            df_asin_col = target_asin_col_name

    # --- 3. 补全 ASIN (FNSKU 填充) ---
    if df_fnsku_col is not None:
        df[df_asin_col] = df[df_asin_col].where(df[df_asin_col].notna(), df[df_fnsku_col])

    # --- 4. 补全 ASIN (SKU 精确 -> 前缀) ---
    if df_sku_col is not None:
        missing_asin_mask = df[df_asin_col].isna() | (df[df_asin_col] == "")
        if missing_asin_mask.any():
            prefer_ca = prefer_ca_first if prefer_ca_first is not None else use_ca
            us_msku_col = find_col(calculate_information, ["MSKU", "msku", "Msku"]) if calculate_information is not None else None
            us_asin_col = find_col(calculate_information, ["ASIN", "asin"]) if calculate_information is not None else None
            ca_msku_col = find_col(calculate_information_ca, ["MSKU", "msku", "Msku"]) if calculate_information_ca is not None else None
            ca_asin_col = find_col(calculate_information_ca, ["ASIN", "asin"]) if calculate_information_ca is not None else None
            us_map = build_norm_map(calculate_information, us_msku_col, us_asin_col) if (us_msku_col and us_asin_col) else {}
            ca_map = build_norm_map(calculate_information_ca, ca_msku_col, ca_asin_col) if (ca_msku_col and ca_asin_col) else {}
            first_map = ca_map if prefer_ca else us_map
            second_map = us_map if prefer_ca else ca_map
            sku_norm_series = df.loc[missing_asin_mask, df_sku_col].apply(norm_str)
            asin_first = sku_norm_series.map(first_map)
            asin_second = sku_norm_series.map(second_map)
            filled = asin_first.fillna(asin_second)
            if first_map:
                filled = filled.fillna(sku_norm_series.apply(lambda s: progressive_prefix_match_norm(s, first_map)))
            if second_map:
                filled = filled.fillna(sku_norm_series.apply(lambda s: progressive_prefix_match_norm(s, second_map)))
            df.loc[missing_asin_mask, df_asin_col] = df.loc[missing_asin_mask, df_asin_col].where(df.loc[missing_asin_mask, df_asin_col].notna(), filled)

    # --- 5. 补全 ASIN (SKU 后缀提取) ---
    if df_sku_col is not None:
        missing_asin_mask = df[df_asin_col].isna() | (df[df_asin_col] == "")
        if missing_asin_mask.any():
            extracted_asins = df.loc[missing_asin_mask, df_sku_col].apply(extract_asin_from_sku)
            df.loc[missing_asin_mask, df_asin_col] = df.loc[missing_asin_mask, df_asin_col].where(df.loc[missing_asin_mask, df_asin_col].notna(), extracted_asins)

    # --- 6. 匹配逻辑 ---
    prefer_ca = prefer_ca_first if prefer_ca_first is not None else use_ca
    results_us = None
    results_ca = None
    if source_field_name:
        us_df = None
        us_msku = None
        us_asin = None
        us_val = None
        ca_df = None
        ca_msku = None
        ca_asin = None
        ca_val = None
        if calculate_information is not None:
            tmp = find_col(calculate_information, [source_field_name])
            if tmp:
                us_df, us_msku, us_asin, us_val = calculate_information, find_col(calculate_information, ["MSKU","msku","Msku"]), find_col(calculate_information, ["ASIN","asin"]), tmp
        if us_val is None and product_property is not None:
            tmp = find_col(product_property, [source_field_name])
            if tmp:
                us_df, us_msku, us_asin, us_val = product_property, find_col(product_property, ["MSKU","msku","Msku"]), find_col(product_property, ["ASIN","asin"]), tmp
        if calculate_information_ca is not None:
            tmp = find_col(calculate_information_ca, [source_field_name])
            if tmp:
                ca_df, ca_msku, ca_asin, ca_val = calculate_information_ca, find_col(calculate_information_ca, ["MSKU","msku","Msku"]), find_col(calculate_information_ca, ["ASIN","asin"]), tmp
        if ca_val is None and product_property_ca is not None:
            tmp = find_col(product_property_ca, [source_field_name])
            if tmp:
                ca_df, ca_msku, ca_asin, ca_val = product_property_ca, find_col(product_property_ca, ["MSKU","msku","Msku"]), find_col(product_property_ca, ["ASIN","asin"]), tmp
        results_us = lookup_value_precise_then_prefix_for_series(df, df_sku_col, df_asin_col, us_df, us_msku, us_asin, us_val) if us_val is not None else [None]*len(df)
        results_ca = lookup_value_precise_then_prefix_for_series(df, df_sku_col, df_asin_col, ca_df, ca_msku, ca_asin, ca_val) if ca_val is not None else [None]*len(df)
    else:
        try:
            us_df, us_msku, us_asin, us_val = resolve_source(ref_calc=None, ref_prop=None,
                                                             target_field=target_field,
                                                             use_ca_flag=False,
                                                             calculate_information=calculate_information,
                                                             calculate_information_ca=calculate_information_ca,
                                                             product_property=product_property,
                                                             product_property_ca=product_property_ca)
        except KeyError:
            us_df, us_msku, us_asin, us_val = None, None, None, None
        try:
            ca_df, ca_msku, ca_asin, ca_val = resolve_source(ref_calc=None, ref_prop=None,
                                                             target_field=target_field,
                                                             use_ca_flag=True,
                                                             calculate_information=calculate_information,
                                                             calculate_information_ca=calculate_information_ca,
                                                             product_property=product_property,
                                                             product_property_ca=product_property_ca)
        except KeyError:
            ca_df, ca_msku, ca_asin, ca_val = None, None, None, None
        results_us = lookup_value_precise_then_prefix_for_series(df, df_sku_col, df_asin_col, us_df, us_msku, us_asin, us_val) if us_val is not None else [None]*len(df)
        results_ca = lookup_value_precise_then_prefix_for_series(df, df_sku_col, df_asin_col, ca_df, ca_msku, ca_asin, ca_val) if ca_val is not None else [None]*len(df)

    s_us = pd.Series(results_us)
    s_ca = pd.Series(results_ca)
    final_results = s_ca.fillna(s_us).tolist() if prefer_ca else s_us.fillna(s_ca).tolist()

    # --- 7. 写入结果 ---
    df[target_field] = final_results
    
    return df

# 专门用于处理removal表的函数
def match_fields_us_ca(df,
                       calculate_information,
                       calculate_information_ca,
                       product_property,
                       target_fields=["采购价", "头程", "产品负责人", "属性", "单个产品体积"],
                       new_class_field="新分类一"):
    """
    US/CA 新场景匹配函数
    """
    df = df.copy()
    # ---------------- 标准化 SKU / ASIN ----------------
    sku_col = find_col(df, ["sku", "SKU"])
    asin_col = find_col(df, ["ASIN", "asin"])
    fnsku_col = find_col(df, ["fnsku", "FNSKU", "FNSku"])

    if sku_col is None:
        raise KeyError("输入 df 中找不到 SKU 列，请确认列名。")

    df["_sku_norm"] = df[sku_col].apply(norm_str)
    if asin_col:
        df["_asin_norm"] = df[asin_col].apply(norm_str)
    else:
        df["_asin_norm"] = pd.NA

    if fnsku_col is not None:
        df["_asin_norm"] = df["_asin_norm"].fillna(df[fnsku_col].apply(norm_str))

    # ---------------- 规范化参考表 ----------------
    for tbl, msku, asin in [(calculate_information, "MSKU", "ASIN"),
                            (calculate_information_ca, "MSKU", "ASIN"),
                            (product_property, "MSKU", "ASIN")]:
        tbl["_MSKU_norm"] = tbl[find_col(tbl, [msku])].apply(norm_str)
        tbl["_ASIN_norm"] = tbl[find_col(tbl, [asin])].apply(norm_str)

    # ---------------- Step1: 获取 ASIN + 国家 ----------------
    df["国家"] = pd.NA
    # SKU -> calculate_information (US)
    df["_asin_temp"] = lookup_value_with_fallback_for_series(
        df, "_sku_norm", "_asin_norm",
        calculate_information, "_MSKU_norm", "_ASIN_norm", "_ASIN_norm")
    mask_us = df["_asin_temp"].notna()
    df.loc[mask_us, "_asin_norm"] = df.loc[mask_us, "_asin_temp"]
    df.loc[mask_us, "国家"] = "US"
    # 对未匹配行，用 SKU -> calculate_information_ca (CA)
    mask_un = df["_asin_temp"].isna()
    df["_asin_temp"] = lookup_value_with_fallback_for_series(
        df[mask_un], "_sku_norm", "_asin_norm",
        calculate_information_ca, "_MSKU_norm", "_ASIN_norm", "_ASIN_norm")
    mask_ca = mask_un & df["_asin_temp"].notna()
    df.loc[mask_ca, "_asin_norm"] = df.loc[mask_ca, "_asin_temp"]
    df.loc[mask_ca, "国家"] = "CA"
    df.drop(columns=["_asin_temp"], inplace=True)

    # ---------------- Step2: 匹配目标字段 ----------------
    for f in target_fields:
        # US
        mask = df["国家"]=="US"
        if mask.any():
            df.loc[mask, f] = lookup_value_with_fallback_for_series(
                df[mask], "_sku_norm", "_asin_norm",
                calculate_information, "_MSKU_norm", "_ASIN_norm", f)
        # CA
        mask = df["国家"]=="CA"
        if mask.any():
            df.loc[mask, f] = lookup_value_with_fallback_for_series(
                df[mask], "_sku_norm", "_asin_norm",
                calculate_information_ca, "_MSKU_norm", "_ASIN_norm", f)

    # ---------------- Step3: 新分类一字段 ----------------
    prop_field = find_col(product_property, [new_class_field, "2024年11月始系统新分类一"])
    df[new_class_field] = lookup_value_with_fallback_for_series(
        df, "_sku_norm", "_asin_norm",
        product_property, "_MSKU_norm", "_ASIN_norm", prop_field)

    # ---------------- Step4: 输出未匹配 SKU ----------------
    unmatched_skus_df = df[df["国家"].isna()][[sku_col]].rename(columns={sku_col:"sku"})

    # ---------------- Step5: 清理临时列 ----------------
    df.drop(columns=["_sku_norm","_asin_norm"], inplace=True, errors="ignore")
    return df, unmatched_skus_df


def batch_match_fields_and_export_unmatched(
    source_tables,
    calculate_information,
    calculate_information_ca,
    product_property,
    product_property_ca,
    prefer_ca_first=False,
    output_path='未匹配记录.csv'
):
    target_fields = ['采购价','头程','产品负责人','属性','新分类一']
    processed = {}
    unmatched_rows = []

    for name, df in source_tables.items():
        cur = df.copy()

        for f in target_fields:
            cur = match_fields_to_df_robust(
                cur,
                f,
                calculate_information,
                calculate_information_ca,
                product_property,
                product_property_ca,
                prefer_ca_first=prefer_ca_first,
                sku_col_candidates=['sku','SKU','MSKU','msku']
            )

        sku_col = find_col(cur, ['sku','SKU','MSKU','msku'])
        asin_col = find_col(cur, ['ASIN','asin']) or 'ASIN'
        if asin_col not in cur.columns and 'ASIN' in cur.columns:
            asin_col = 'ASIN'

        sku_series = cur[sku_col] if sku_col else pd.Series([pd.NA]*len(cur), index=cur.index)
        asin_series = cur[asin_col] if asin_col in cur.columns else pd.Series([pd.NA]*len(cur), index=cur.index)

        sku_is_empty = sku_series.isna() | (sku_series.astype(str).str.strip() == '')
        asin_is_empty = asin_series.isna() | (asin_series.astype(str).str.strip() == '')
        both_missing = sku_is_empty & asin_is_empty

        cur['缺失标签'] = pd.NA
        cur.loc[both_missing, '缺失标签'] = pd.Series([f'{name}-{i}' for i in cur.index], index=cur.index).loc[both_missing]

        mask_unmatched = cur[target_fields].isna().any(axis=1)
        subset = pd.DataFrame(
            {
                '表': pd.Series([name]*len(cur), index=cur.index),
                'SKU': sku_series,
                'ASIN': asin_series,
                '缺失标签': cur['缺失标签']
            },
            index=cur.index
        )
        for f in target_fields:
            subset[f] = cur[f] if f in cur.columns else pd.NA

        unmatched_rows.append(subset.loc[mask_unmatched])
        processed[name] = cur

    if unmatched_rows:
        out_df = pd.concat(unmatched_rows, axis=0, ignore_index=True)
        out_df.to_csv(output_path, index=False)
    else:
        out_df = pd.DataFrame(columns=['表','SKU','ASIN','缺失标签']+target_fields)

    return processed, out_df

def match_fields_eu(df,
                    target_fields,
                    calculate_information_eu,
                    sku_col_candidates=None,
                    asin_col_candidates=None):
    """
    欧洲专用匹配函数
    逻辑：
    1. 优先使用 ASIN 匹配。
    2. 如果 ASIN 缺失，用 欧洲SKU 在 calculate_information_eu 中查找 ASIN 并补全。
    3. 始终使用 ASIN 在 calculate_information_eu 中查找 target_fields。
    
    target_fields: 可以是单个字段名字符串，也可以是字段名列表。
    """
    df = df.copy()
    
    # 兼容单个字段输入
    if isinstance(target_fields, str):
        target_fields = [target_fields]
    
    # 1. 确定列名
    if sku_col_candidates is None:
        sku_col_candidates = ["欧洲SKU", "SKU", "sku"]
    if asin_col_candidates is None:
        asin_col_candidates = ["ASIN", "asin"]
        
    df_sku_col = find_col(df, sku_col_candidates)
    df_asin_col = find_col(df, asin_col_candidates)
    
    # 确保 df 有 ASIN 列
    target_asin_col_name = "ASIN"
    if df_asin_col is None:
        df[target_asin_col_name] = pd.NA
        df_asin_col = target_asin_col_name
    elif df_asin_col != target_asin_col_name:
        if target_asin_col_name not in df.columns:
             df[target_asin_col_name] = df[df_asin_col]
        df_asin_col = target_asin_col_name

    # 信息表列名
    info_sku_col = find_col(calculate_information_eu, ["欧洲SKU", "SKU", "sku"])
    info_asin_col = find_col(calculate_information_eu, ["ASIN", "asin"])
    
    # 构建映射 SKU -> ASIN (用于补全)
    map_sku_to_asin = build_norm_map(calculate_information_eu, info_sku_col, info_asin_col) if (info_sku_col and info_asin_col) else {}
    
    # 3. 补全 ASIN
    if df_sku_col:
        sku_norm = df[df_sku_col].apply(norm_str)
        found_asins = sku_norm.map(map_sku_to_asin)
        
        asin_is_missing = df[df_asin_col].isna() | (df[df_asin_col].astype(str).str.strip() == "")
        if asin_is_missing.any():
            df.loc[asin_is_missing, df_asin_col] = found_asins[asin_is_missing]

    # 4. 循环匹配所有 Target Fields
    eu_field_mapping = {
        "负责人": ["负责人", "产品负责人", "运营负责人", "12月负责"],
        "大类": ["大类", "物料大类", "一级分类"],
        "中类": ["中类", "物料中类", "二级分类"],
        "小类": ["小类", "物料小类", "三级分类"]
    }

    asin_norm = df[df_asin_col].apply(norm_str)

    for target_field in target_fields:
        candidates = eu_field_mapping.get(target_field, [target_field])
        info_target_col = find_col(calculate_information_eu, candidates)
        
        # 尝试模糊匹配兜底
        if info_target_col is None and "负责" in target_field:
             for col in calculate_information_eu.columns:
                if "负责" in str(col):
                    info_target_col = col
                    break
        
        if info_target_col is None:
             print(f"Warning: 在 calculate_information_eu 中未找到字段: {target_field}，将跳过匹配。")
             df[target_field] = pd.NA
             continue

        # 构建映射 ASIN -> Target
        map_asin_to_target = build_norm_map(calculate_information_eu, info_asin_col, info_target_col) if (info_asin_col and info_target_col) else {}
        
        # 匹配 Target Field
        df[target_field] = asin_norm.map(map_asin_to_target)
    
    return df
