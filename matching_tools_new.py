import pandas as pd
from typing import List, Union, Dict


def find_col(df, candidates):
    if isinstance(candidates, str):
        candidates = [candidates]
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand is None:
            continue
        lc = str(cand).strip().lower()
        if lc in lower_map:
            return lower_map[lc]
    return None


def norm_str(x):
    if isinstance(x, pd.Series):
        x = x.iloc[0] if len(x) else None
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    s = str(x).strip()
    return s.upper() if s != "" else None


def extract_asin_from_sku(sku_val):
    if pd.isna(sku_val):
        return None
    s = str(sku_val).strip()
    if len(s) > 10:
        suffix = s[-10:]
        if suffix.upper().startswith("B0"):
            return suffix.upper()
    return None


def build_norm_map(df, key_col, value_col):
    out: Dict[str, object] = {}
    if key_col is None or value_col is None:
        return out
    for _, row in df[[key_col, value_col]].iterrows():
        k = norm_str(row[key_col])
        if k is not None and k not in out:
            out[k] = row[value_col]
    return out


def lookup_value_with_fallback_for_series(df,
                                          df_sku_col_actual,
                                          df_asin_col_actual,
                                          ref_df,
                                          ref_msku_col_actual,
                                          ref_asin_col_actual,
                                          ref_value_col_actual):
    if ref_value_col_actual is None:
        return [None] * len(df)
    msku_map = build_norm_map(ref_df, ref_msku_col_actual, ref_value_col_actual) if ref_msku_col_actual is not None else {}
    asin_map = build_norm_map(ref_df, ref_asin_col_actual, ref_value_col_actual) if ref_asin_col_actual is not None else {}
    if df_sku_col_actual is None:
        sku_series = pd.Series([None] * len(df), index=df.index)
    else:
        sku_series = df[df_sku_col_actual]
    if df_asin_col_actual is None:
        asin_series = pd.Series([None] * len(df), index=df.index)
    else:
        asin_series = df[df_asin_col_actual]
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


def lookup_by_sku(df_subset, ref_df, ref_sku_col, ref_value_col):
    if ref_value_col is None or ref_sku_col is None:
        return pd.Series([pd.NA] * len(df_subset), index=df_subset.index)
    m = build_norm_map(ref_df, ref_sku_col, ref_value_col)
    keys = df_subset["_sku_norm"]
    return pd.Series([m.get(k) if k is not None else None for k in keys], index=df_subset.index)


def lookup_by_asin(df_subset, ref_df, ref_asin_col, ref_value_col):
    if ref_value_col is None or ref_asin_col is None:
        return pd.Series([pd.NA] * len(df_subset), index=df_subset.index)
    m = build_norm_map(ref_df, ref_asin_col, ref_value_col)
    keys = df_subset["_asin_norm"]
    return pd.Series([m.get(k) if k is not None else None for k in keys], index=df_subset.index)


def match_fields_cascading_fill(df,
                                product_property,
                                special_upon=None,
                                target_fields=None):
    df = df.copy()
    if target_fields is None:
        target_fields = [
            "物料大类",
            "上月运营负责人(核算参考)",
            "产品重要性",
            "采购价(不含税)",
            "头程"
        ]
    target_cols = target_fields
    currency_col = find_col(df, ["currency", "Currency"])
    sku_col = find_col(df, ["sku", "SKU", "msku", "MSKU"])
    if currency_col is None:
        raise KeyError("输入 df 缺少 'currency' 列。")
    if sku_col is None:
        raise KeyError("输入 df 缺少 SKU/MSKU 列。")
    asin_col = find_col(df, ["ASIN", "asin"])
    target_asin = "ASIN"
    if asin_col is None:
        df[target_asin] = pd.NA
        asin_col = target_asin
    elif asin_col != target_asin:
        df[target_asin] = df[asin_col]
        asin_col = target_asin
    msku_col_std = "MSKU"
    df[msku_col_std] = df[sku_col]
    for f in target_cols:
        if f not in df.columns:
            df[f] = pd.NA
    country_col_prop = find_col(product_property, ["国家"])
    prop_msku_col = find_col(product_property, ["MSKU", "msku", "SKU", "sku"])
    prop_asin_col = find_col(product_property, ["ASIN", "asin"])
    if country_col_prop is None:
        raise KeyError("product_property 缺少 '国家' 列。")
    if prop_msku_col is None and prop_asin_col is None:
        raise KeyError("product_property 需要包含 MSKU 或 ASIN 列。")

    # --- 准备国家对应的属性和重定向数据 ---
    us_ref = product_property[product_property[country_col_prop].astype(str).str.strip().str.upper() == "US"]
    ca_ref = product_property[product_property[country_col_prop].astype(str).str.strip().str.upper() == "CA"]
    au_ref = product_property[product_property[country_col_prop].astype(str).str.strip().str.upper() == "AU"]
    
    us_existing_mskus = set(us_ref[prop_msku_col].apply(norm_str).dropna().unique()) if prop_msku_col else set()
    ca_existing_mskus = set(ca_ref[prop_msku_col].apply(norm_str).dropna().unique()) if prop_msku_col else set()
    au_existing_mskus = set(au_ref[prop_msku_col].apply(norm_str).dropna().unique()) if prop_msku_col else set()

    us_redirect_map = {}
    ca_redirect_map = {}
    au_redirect_map = {}
    if special_upon is not None and not special_upon.empty:
        s_country_col = find_col(special_upon, ["国家", "Country", "country"])
        s_msku_col = find_col(special_upon, ["msku", "MSKU"])
        s_actual_msku_col = find_col(special_upon, ["实际MSKU", "实际msku", "actual_msku"])
        if s_country_col and s_msku_col and s_actual_msku_col:
            us_spec = special_upon[special_upon[s_country_col].astype(str).str.strip().str.upper() == "US"]
            ca_spec = special_upon[special_upon[s_country_col].astype(str).str.strip().str.upper() == "CA"]
            au_spec = special_upon[special_upon[s_country_col].astype(str).str.strip().str.upper() == "AU"]
            us_redirect_map = build_norm_map(us_spec, s_msku_col, s_actual_msku_col)
            ca_redirect_map = build_norm_map(ca_spec, s_msku_col, s_actual_msku_col)
            au_redirect_map = build_norm_map(au_spec, s_msku_col, s_actual_msku_col)

    if prop_msku_col is not None and prop_asin_col is not None:
        asin_missing = df[asin_col].isna() | (df[asin_col].astype(str).str.strip() == "")
        if asin_missing.any():
            msku_norm_series = df.loc[asin_missing, msku_col_std].apply(norm_str)
            msku_to_asin = build_norm_map(product_property, prop_msku_col, prop_asin_col)
            df.loc[asin_missing, asin_col] = msku_norm_series.map(msku_to_asin)
        msku_missing = df[msku_col_std].isna() | (df[msku_col_std].astype(str).str.strip() == "")
        if msku_missing.any():
            asin_norm_series = df.loc[msku_missing, asin_col].apply(norm_str)
            asin_to_msku = build_norm_map(product_property, prop_asin_col, prop_msku_col)
            df.loc[msku_missing, msku_col_std] = asin_norm_series.map(asin_to_msku)

    cur = df[currency_col].astype(str).str.strip().str.upper()
    usd_mask = cur.eq("USD")
    cad_mask = cur.eq("CAD")
    aud_mask = cur.eq("AUD")
    empty_mask = df[currency_col].isna() | (df[currency_col].astype(str).str.strip() == "")

    # 新增逻辑：处理空 currency
    if empty_mask.any():
        sku_for_empty = df.loc[empty_mask, sku_col].astype(str).str.strip().str.upper()
        # 最后一个字母是K的，我们认为是CA
        ends_with_k = sku_for_empty.str.endswith('K', na=False)
        # 在empty_mask中，实际应该归为CAD的行
        empty_to_cad_mask = empty_mask & ends_with_k.reindex(df.index, fill_value=False)
        # 在empty_mask中，剩下的归为USD
        empty_to_usd_mask = empty_mask & ~empty_to_cad_mask

        # 更新 currency 列
        df.loc[empty_to_cad_mask, currency_col] = "CAD"
        df.loc[empty_to_usd_mask, currency_col] = "USD"

        # 更新总的 usd_mask 和 cad_mask
        usd_mask = usd_mask | empty_to_usd_mask
        cad_mask = cad_mask | empty_to_cad_mask

    active_mask = usd_mask | cad_mask | aud_mask
    df.loc[active_mask, "_sku_norm"] = df.loc[active_mask, msku_col_std].apply(norm_str)
    df.loc[active_mask, "_asin_norm"] = df.loc[active_mask, asin_col].apply(norm_str)

    # --- 应用二次重定向逻辑 ---
    if usd_mask.any() and us_redirect_map:
        mask_redir_us = usd_mask & (~df["_sku_norm"].isin(us_existing_mskus)) & (df["_sku_norm"].isin(us_redirect_map.keys()))
        if mask_redir_us.any():
            df.loc[mask_redir_us, "_sku_norm"] = df.loc[mask_redir_us, "_sku_norm"].map(us_redirect_map).apply(norm_str)
            
    if cad_mask.any() and ca_redirect_map:
        mask_redir_ca = cad_mask & (~df["_sku_norm"].isin(ca_existing_mskus)) & (df["_sku_norm"].isin(ca_redirect_map.keys()))
        if mask_redir_ca.any():
            df.loc[mask_redir_ca, "_sku_norm"] = df.loc[mask_redir_ca, "_sku_norm"].map(ca_redirect_map).apply(norm_str)
            
    if aud_mask.any() and au_redirect_map:
        mask_redir_au = aud_mask & (~df["_sku_norm"].isin(au_existing_mskus)) & (df["_sku_norm"].isin(au_redirect_map.keys()))
        if mask_redir_au.any():
            df.loc[mask_redir_au, "_sku_norm"] = df.loc[mask_redir_au, "_sku_norm"].map(au_redirect_map).apply(norm_str)

    field_map = {
        "物料大类": ["物料大类", "2024年11月始系统新分类一"],
        "上月运营负责人(核算参考)": ["上月运营负责人(核算参考)", "上月运营负责人"],
        "产品重要性": ["产品重要性", "属性"],
        "采购价(不含税)": ["采购价", "采购价(不含税)"],
        "头程": ["头程"],
        "单个产品体积(m³)": ["单个产品体积(m³)", "单个产品体积"],
    }
    asin_field_candidates = ["ASIN", "asin"]

    # 处理 USD 的行
    df_us = df.loc[usd_mask]
    if len(df_us) > 0 and not us_ref.empty:
        prop_asin_col_us = find_col(us_ref, asin_field_candidates) if prop_asin_col is None else prop_asin_col
        asin_us = lookup_value_with_fallback_for_series(
            df_us, "_sku_norm", "_asin_norm", us_ref, prop_msku_col, prop_asin_col_us, prop_asin_col_us,
        )
        df.loc[usd_mask, asin_col] = pd.Series(asin_us, index=df_us.index).values
        for f in target_fields:
            candidates = field_map.get(f, [f])
            ref_val_col = find_col(us_ref, candidates)
            if ref_val_col is None:
                continue
            series_f = lookup_value_with_fallback_for_series(
                df_us, "_sku_norm", "_asin_norm", us_ref, prop_msku_col, prop_asin_col, ref_val_col,
            )
            df.loc[usd_mask, f] = pd.Series(series_f, index=df_us.index).values

    # 处理 CAD 的行
    df_ca = df.loc[cad_mask]
    if len(df_ca) > 0 and not ca_ref.empty:
        prop_asin_col_ca = find_col(ca_ref, asin_field_candidates) if prop_asin_col is None else prop_asin_col
        asin_ca = lookup_value_with_fallback_for_series(
            df_ca, "_sku_norm", "_asin_norm", ca_ref, prop_msku_col, prop_asin_col_ca, prop_asin_col_ca,
        )
        df.loc[cad_mask, asin_col] = pd.Series(asin_ca, index=df_ca.index).values
        for f in target_fields:
            candidates = field_map.get(f, [f])
            ref_val_col = find_col(ca_ref, candidates)
            if ref_val_col is None:
                continue
            series_f = lookup_value_with_fallback_for_series(
                df_ca, "_sku_norm", "_asin_norm", ca_ref, prop_msku_col, prop_asin_col, ref_val_col,
            )
            df.loc[cad_mask, f] = pd.Series(series_f, index=df_ca.index).values

    # 处理 AUD 的行
    df_au = df.loc[aud_mask]
    if len(df_au) > 0 and not au_ref.empty:
        prop_asin_col_au = find_col(au_ref, asin_field_candidates) if prop_asin_col is None else prop_asin_col
        asin_au = lookup_value_with_fallback_for_series(
            df_au, "_sku_norm", "_asin_norm", au_ref, prop_msku_col, prop_asin_col_au, prop_asin_col_au,
        )
        df.loc[aud_mask, asin_col] = pd.Series(asin_au, index=df_au.index).values
        for f in target_fields:
            candidates = field_map.get(f, [f])
            ref_val_col = find_col(au_ref, candidates)
            if ref_val_col is None:
                continue
            series_f = lookup_value_with_fallback_for_series(
                df_au, "_sku_norm", "_asin_norm", au_ref, prop_msku_col, prop_asin_col, ref_val_col,
            )
            df.loc[aud_mask, f] = pd.Series(series_f, index=df_au.index).values

    if "_sku_norm" in df.columns:
        df.drop(columns=["_sku_norm"], inplace=True)
    if "_asin_norm" in df.columns:
        df.drop(columns=["_asin_norm"], inplace=True)

    return df


def match_fields_to_df_robust(df,
                              target_field,
                              product_property,
                              country=None,
                              sku_col_candidates=None,
                              asin_col_candidates=None,
                              fnsku_col_candidates=None):
    df = df.copy()
    if product_property is None:
        raise KeyError("必须提供 product_property 表。")
    if sku_col_candidates is None:
        sku_col_candidates = ["sku", "SKU", "msku", "MSKU"]
    if asin_col_candidates is None:
        asin_col_candidates = ["ASIN", "asin"]
    if fnsku_col_candidates is None:
        fnsku_col_candidates = ["fnsku", "FNSKU", "FNSku", "FNSku"]
    df_sku_col = find_col(df, sku_col_candidates)
    df_asin_col = find_col(df, asin_col_candidates)
    df_fnsku_col = find_col(df, fnsku_col_candidates)
    if df_sku_col is None and df_asin_col is None:
        raise KeyError("输入 df 中找不到 SKU/MSKU 或 ASIN 列。")
    target_asin_col_name = "ASIN"
    if df_asin_col is None:
        df[target_asin_col_name] = pd.NA
        df_asin_col = target_asin_col_name
    elif df_asin_col != target_asin_col_name:
        df[target_asin_col_name] = df[df_asin_col]
        df_asin_col = target_asin_col_name
    msku_col_std = "MSKU"
    if df_sku_col is not None:
        df[msku_col_std] = df[df_sku_col]
    else:
        df[msku_col_std] = pd.NA
    if df_fnsku_col is not None:
        df[df_asin_col] = df[df_asin_col].where(df[df_asin_col].notna(), df[df_fnsku_col])

    # --- 新增逻辑：处理 Amazon.Found. 开头的 SKU ---
    if df_sku_col is not None:
        def extract_asin_from_amazon_found(sku_val):
            """
            如果 SKU 以 'Amazon.Found.' (忽略大小写) 开头，且长度足够，
            提取后 10 位作为 ASIN。
            """
            if pd.isna(sku_val):
                return None
            s = str(sku_val).strip()
            # 检查是否以 amazon.found. 开头 (不区分大小写)
            if s.lower().startswith("amazon.found.") and len(s) >= 10:
                # 提取后 10 位
                candidate = s[-10:]
                # 简单校验一下是不是 B0 开头，或者只要是后10位即可？
                # 用户需求只说“后10位”，且举例是 B0C4GCW5WW。
                # 这里直接提取后10位。
                return candidate.upper()
            return None

        # 找出 ASIN 为空 或者 ASIN 是空字符串 的行
        asin_missing_mask = df[df_asin_col].isna() | (df[df_asin_col].astype(str).str.strip() == "")
        
        if asin_missing_mask.any():
            # 只对这些行应用提取逻辑
            extracted_asins = df.loc[asin_missing_mask, df_sku_col].apply(extract_asin_from_amazon_found)
            # 填充回去
            df.loc[asin_missing_mask, df_asin_col] = df.loc[asin_missing_mask, df_asin_col].fillna(extracted_asins)
            # 注意：fillna 可能不够（因为前面可能是空字符串），用 where 或者直接赋值非空值
            # 更稳妥的方式：
            valid_extracted = extracted_asins.notna()
            # 更新那些确实提取到了值的行
            rows_to_update = asin_missing_mask & valid_extracted.reindex(df.index, fill_value=False)
            if rows_to_update.any():
                 df.loc[rows_to_update, df_asin_col] = extracted_asins[rows_to_update]

    country_col = find_col(product_property, ["国家"])
    prop_msku_col = find_col(product_property, ["MSKU", "msku", "Msku", "SKU", "sku"])
    prop_asin_col = find_col(product_property, ["ASIN", "asin"])
    
    if country is not None:
        if country_col is None:
            raise KeyError("product_property 表缺少 '国家' 列。")
            
    if prop_msku_col is None and prop_asin_col is None:
        raise KeyError("product_property 表需要包含 MSKU 或 ASIN 列。")
    
    if country is not None:
        mask_country = product_property[country_col].astype(str).str.strip().str.upper() == str(country).upper()
        ref_prop = product_property[mask_country].copy()
        if ref_prop.empty:
            raise ValueError(f"product_property 中未找到国家为 {country} 的记录。")
    else:
        ref_prop = product_property.copy()
    if prop_msku_col is not None and prop_asin_col is not None:
        asin_missing = df[df_asin_col].isna() | (df[df_asin_col].astype(str).str.strip() == "")
        if asin_missing.any():
            msku_norm_series = df.loc[asin_missing, msku_col_std].apply(norm_str)
            msku_to_asin = build_norm_map(ref_prop, prop_msku_col, prop_asin_col)
            df.loc[asin_missing, df_asin_col] = msku_norm_series.map(msku_to_asin)
        msku_missing = df[msku_col_std].isna() | (df[msku_col_std].astype(str).str.strip() == "")
        if msku_missing.any():
            asin_norm_series = df.loc[msku_missing, df_asin_col].apply(norm_str)
            asin_to_msku = build_norm_map(ref_prop, prop_asin_col, prop_msku_col)
            df.loc[msku_missing, msku_col_std] = asin_norm_series.map(asin_to_msku)
    df["_sku_norm"] = df[msku_col_std].apply(norm_str)
    df["_asin_norm"] = df[df_asin_col].apply(norm_str)
    field_map = {
        "物料大类": ["物料大类"],
        "上月运营负责人(核算参考)": ["上月运营负责人(核算参考)", "上月运营负责人"],
        "产品重要性": ["产品重要性", "属性"],
        "采购价(不含税)": ["采购价", "采购价(不含税)"],
        "头程": ["头程"],
        "单个产品体积(m³)": ["单个产品体积(m³)", "单个产品体积"],
    }
    candidates = field_map.get(target_field, [target_field])
    ref_value_col = find_col(ref_prop, candidates)
    if ref_value_col is None:
        raise KeyError(f"product_property 表中未找到用于匹配字段 {target_field} 的列。")
    df[target_field] = lookup_value_with_fallback_for_series(
        df,
        "_sku_norm",
        "_asin_norm",
        ref_prop,
        prop_msku_col,
        prop_asin_col,
        ref_value_col,
    )
    df.drop(columns=["_sku_norm", "_asin_norm"], inplace=True, errors="ignore")
    return df


def batch_match_fields_and_export_unmatched(
    source_tables,
    product_property,
    special_upon=None,
    country=None,
    output_path="未匹配记录.csv",
):
    """
    批量匹配字段并导出未匹配记录（增强版：全向量化匹配 + 国家对齐重定向 + 链条断裂拦截）
    """
    target_fields = [
        "物料大类",
        "上月运营负责人(核算参考)",
        "产品重要性",
        "采购价(不含税)",
        "头程"
    ]

    def get_country_context(target_country):
        """
        获取特定国家下的属性表子集和重定向映射。
        """
        # 1. 属性表预处理
        prop_msku_col = find_col(product_property, ["MSKU", "msku", "Msku", "SKU", "sku"])
        prop_country_col = find_col(product_property, ["国家"])
        
        ref_prop = product_property.copy()
        if target_country and prop_country_col:
            ref_prop = ref_prop[ref_prop[prop_country_col].astype(str).str.strip().str.upper() == str(target_country).upper()]
        
        ref_prop["_norm_msku_key"] = ref_prop[prop_msku_col].apply(norm_str) if prop_msku_col else pd.NA
        ref_prop = ref_prop.drop_duplicates(subset=["_norm_msku_key"])
        existing_mskus = set(ref_prop["_norm_msku_key"].dropna().unique())
        
        # 2. 重定向映射预处理
        r_map = {}
        if special_upon is not None and not special_upon.empty:
            s_country_col = find_col(special_upon, ["国家", "Country", "country"])
            filtered_s = special_upon
            # 严格国家对齐：仅提取当前国家的映射关系
            if s_country_col and target_country:
                filtered_s = special_upon[special_upon[s_country_col].astype(str).str.strip().str.upper() == str(target_country).upper()]
            
            s_msku_col = find_col(filtered_s, ["msku", "MSKU"])
            s_actual_msku_col = find_col(filtered_s, ["实际MSKU", "实际msku", "actual_msku"])
            if s_msku_col and s_actual_msku_col:
                r_map = build_norm_map(filtered_s, s_msku_col, s_actual_msku_col)
        
        return ref_prop, existing_mskus, r_map

    # 预计算主国家上下文
    primary_prop, primary_existing, primary_redirect = get_country_context(country)
    
    # 建立 ASIN 到 MSKU 的反向映射（取第一条），用于 MSKU 缺失时的预填充
    primary_asin_to_msku = {}
    prop_msku_col = find_col(product_property, ["MSKU", "msku", "Msku", "SKU", "sku"])
    prop_asin_col = find_col(product_property, ["ASIN", "asin"])
    if not primary_prop.empty and prop_msku_col and prop_asin_col:
        primary_asin_to_msku = build_norm_map(primary_prop, prop_asin_col, prop_msku_col)

    # 如果是 CA 或 AU，预计算 US 上下文用于兜底
    us_context = None
    us_asin_to_msku = {}
    if country is not None and str(country).upper() in ["CA", "AU"]:
        us_context = get_country_context("US")
        us_prop, _, _ = us_context
        if not us_prop.empty and prop_msku_col and prop_asin_col:
            us_asin_to_msku = build_norm_map(us_prop, prop_asin_col, prop_msku_col)

    processed = {}
    unmatched_rows = []

    for name, df in source_tables.items():
        cur = df.copy()
        df_sku_col = find_col(cur, ["sku", "SKU", "msku", "MSKU"])
        df_asin_col = find_col(cur, ["ASIN", "asin"]) or "ASIN"
        
        if df_sku_col is None:
            # 如果原表完全没 SKU 列，创建一个空的
            cur["MSKU"] = pd.NA
            df_sku_col = "MSKU"
        
        if df_asin_col not in cur.columns:
            cur[df_asin_col] = pd.NA

        # --- 标识符判定与缺失标签生成 ---
        s_sku = cur[df_sku_col]
        s_asin = cur[df_asin_col]
        
        sku_is_empty = s_sku.isna() | (s_sku.astype(str).str.strip() == "")
        asin_is_empty = s_asin.isna() | (s_asin.astype(str).str.strip() == "")
        both_missing = sku_is_empty & asin_is_empty

        # 仅当 MSKU 和 ASIN 同时为空时，才生成缺失标签
        if "缺失标签" not in cur.columns:
            cur["缺失标签"] = pd.NA
            if both_missing.any():
                cur.loc[both_missing, "缺失标签"] = [f"{name}-{i}" for i in cur.index[both_missing]]

        # --- 步骤 0：如果 MSKU 缺失但 ASIN 存在，先尝试从 ASIN 反向匹配 MSKU ---
        # 这一步是为了让后续的 special_upon 重定向逻辑能基于匹配到的 MSKU 运行
        cur["_temp_msku_for_redir"] = cur[df_sku_col]
        mask_need_msku = sku_is_empty & (~asin_is_empty)
        if mask_need_msku.any() and primary_asin_to_msku:
            cur["_asin_norm_temp"] = cur[df_asin_col].apply(norm_str)
            cur.loc[mask_need_msku, "_temp_msku_for_redir"] = cur.loc[mask_need_msku, "_asin_norm_temp"].map(primary_asin_to_msku)
            cur.drop(columns=["_asin_norm_temp"], inplace=True)

        # --- 步骤 1：处理重定向逻辑 ---
        cur["_norm_orig_msku"] = cur["_temp_msku_for_redir"].apply(norm_str)
        cur["_redirected_msku"] = pd.NA
        
        if primary_redirect:
            # 判定：不在当前属性表 且 在重定向表中有映射
            mask_redir = (~cur["_norm_orig_msku"].isin(primary_existing)) & (cur["_norm_orig_msku"].isin(primary_redirect.keys()))
            if mask_redir.any():
                cur.loc[mask_redir, "_redirected_msku"] = cur.loc[mask_redir, "_norm_orig_msku"].map(primary_redirect)

        # --- 步骤 2：主匹配逻辑 ---
        sku_candidates = ["sku", "SKU", "msku", "MSKU"]
        # 优先级：1. 重定向后的 MSKU > 2. 反向匹配/原始的 MSKU > 3. 原始列
        cur["_msku_for_matching"] = cur["_temp_msku_for_redir"]
        mask_has_redir = cur["_redirected_msku"].notna()
        if mask_has_redir.any():
            cur.loc[mask_has_redir, "_msku_for_matching"] = cur.loc[mask_has_redir, "_redirected_msku"]
        sku_candidates = ["_msku_for_matching"] + sku_candidates

        for f in target_fields:
            cur = match_fields_to_df_robust(
                cur,
                f,
                product_property=product_property,
                country=country,
                sku_col_candidates=sku_candidates,
            )

        # --- 步骤 3：CA/AU -> US 兜底逻辑 ---
        if us_context:
            mask_missing = cur[target_fields].isna().all(axis=1)
            if mask_missing.any():
                subset_us = cur.loc[mask_missing].copy()
                us_prop, us_existing, us_redirect = us_context
                
                # 兜底时也执行同样的 ASIN -> MSKU 预填充逻辑
                subset_us["_temp_msku_us"] = subset_us[df_sku_col]
                sku_is_empty_us = subset_us[df_sku_col].isna() | (subset_us[df_sku_col].astype(str).str.strip() == "")
                asin_is_empty_us = subset_us[df_asin_col].isna() | (subset_us[df_asin_col].astype(str).str.strip() == "")
                mask_need_msku_us = sku_is_empty_us & (~asin_is_empty_us)
                if mask_need_msku_us.any() and us_asin_to_msku:
                    subset_us["_asin_norm_us"] = subset_us[df_asin_col].apply(norm_str)
                    subset_us.loc[mask_need_msku_us, "_temp_msku_us"] = subset_us.loc[mask_need_msku_us, "_asin_norm_us"].map(us_asin_to_msku)
                
                subset_us["_norm_orig_msku_us"] = subset_us["_temp_msku_us"].apply(norm_str)
                us_sku_candidates = ["sku", "SKU", "msku", "MSKU"]
                
                if us_redirect:
                    mask_redir_us = (~subset_us["_norm_orig_msku_us"].isin(us_existing)) & (subset_us["_norm_orig_msku_us"].isin(us_redirect.keys()))
                    subset_us["_msku_for_matching_us"] = subset_us["_temp_msku_us"]
                    if mask_redir_us.any():
                        subset_us.loc[mask_redir_us, "_msku_for_matching_us"] = subset_us.loc[mask_redir_us, "_norm_orig_msku_us"].map(us_redirect)
                    us_sku_candidates = ["_msku_for_matching_us"] + us_sku_candidates
                
                for f in target_fields:
                    subset_us = match_fields_to_df_robust(
                        subset_us,
                        f,
                        product_property=product_property,
                        country="US",
                        sku_col_candidates=us_sku_candidates,
                    )
                cur.loc[mask_missing, target_fields] = subset_us[target_fields]

        # --- 步骤 4：识别并收集未匹配记录 ---
        mask_unmatched = cur[target_fields].isna().any(axis=1)
        
        sku_series = cur[df_sku_col]
        asin_series = cur[df_asin_col]
        
        subset = pd.DataFrame({
            "表": name,
            "SKU": sku_series,
            "ASIN": asin_series,
            "缺失标签": cur["缺失标签"],
        }, index=cur.index)
        
        for f in target_fields:
            subset[f] = cur[f] if f in cur.columns else pd.NA
        
        unmatched_rows.append(subset.loc[mask_unmatched])
        
        # 清理内部辅助列
        drop_cols = ["_norm_orig_msku", "_redirected_msku", "_msku_for_matching", 
                     "_norm_orig_msku_us", "_msku_for_matching_us", "_temp_msku_for_redir",
                     "_temp_msku_us", "_asin_norm_us"]
        cur.drop(columns=[c for c in drop_cols if c in cur.columns], inplace=True)
        processed[name] = cur

    if unmatched_rows:
        out_df = pd.concat(unmatched_rows, axis=0, ignore_index=True)
        out_df = out_df.drop_duplicates()
        out_df.to_csv(output_path, index=False)
    else:
        out_df = pd.DataFrame(columns=["表", "SKU", "ASIN", "缺失标签"] + target_fields)
    return processed, out_df


def refill_from_unmatched(
    source_tables,
    updated_unmatched_df,
    target_fields=None,
):
    if target_fields is None:
        target_fields = [
            "物料大类",
            "上月运营负责人(核算参考)",
            "产品重要性",
            "采购价(不含税)",
            "头程"
        ]
    updated_unmatched_df = updated_unmatched_df.drop_duplicates()
    result = {}
    for name, df in source_tables.items():
        cur = df.copy()
        sub = updated_unmatched_df[updated_unmatched_df["表"] == name]
        asin_col = find_col(cur, ["ASIN", "asin"])
        sku_col = find_col(cur, ["sku", "SKU", "MSKU", "msku"])
        if "缺失标签" not in cur.columns:
            s_sku = cur[sku_col] if sku_col else pd.Series([pd.NA] * len(cur), index=cur.index)
            s_asin = cur[asin_col] if asin_col else pd.Series([pd.NA] * len(cur), index=cur.index)
            sku_empty = s_sku.isna() | (s_sku.astype(str).str.strip() == "")
            asin_empty = s_asin.isna() | (s_asin.astype(str).str.strip() == "")
            both_missing = sku_empty & asin_empty
            cur["缺失标签"] = pd.NA
            cur.loc[both_missing, "缺失标签"] = pd.Series(
                [f"{name}-{i}" for i in cur.index],
                index=cur.index,
            ).loc[both_missing]
        if sub.empty:
            result[name] = cur
            continue
        for f in target_fields:
            if f not in cur.columns:
                cur[f] = pd.NA
            
            # --- 新增逻辑：对于 MSKU/ASIN，只允许通过“缺失标签”回填 ---
            f_lower = str(f).strip().lower()
            is_key_field = f_lower in ["asin", "sku", "msku"]
            
            mask_na = cur[f].isna()
            
            # 如果是 MSKU/ASIN，跳过基于 ASIN/SKU 的常规匹配
            if not is_key_field:
                if asin_col and ("ASIN" in sub.columns):
                    sub_asin = sub.dropna(subset=["ASIN", f]).copy()
                    if not sub_asin.empty:
                        cur["_asin_norm"] = cur[asin_col].apply(norm_str)
                        sub_asin["_asin_norm"] = sub_asin["ASIN"].apply(norm_str)
                        asin_map = sub_asin.set_index("_asin_norm")[f].to_dict()
                        fill_mask = mask_na & cur["_asin_norm"].notna()
                        cur.loc[fill_mask, f] = cur.loc[fill_mask, "_asin_norm"].map(asin_map)
                        cur.drop(columns=["_asin_norm"], inplace=True, errors="ignore")
                
                mask_na = cur[f].isna()
                if sku_col and ("SKU" in sub.columns):
                    sub_sku = sub.dropna(subset=["SKU", f]).copy()
                    if not sub_sku.empty:
                        cur["_sku_norm"] = cur[sku_col].apply(norm_str)
                        sub_sku["_sku_norm"] = sub_sku["SKU"].apply(norm_str)
                        sku_map = sub_sku.set_index("_sku_norm")[f].to_dict()
                        fill_mask = mask_na & cur["_sku_norm"].notna()
                        cur.loc[fill_mask, f] = cur.loc[fill_mask, "_sku_norm"].map(sku_map)
                        cur.drop(columns=["_sku_norm"], inplace=True, errors="ignore")
            
            mask_na = cur[f].isna()
            s_sku = cur[sku_col] if sku_col else pd.Series([pd.NA] * len(cur), index=cur.index)
            s_asin = cur[asin_col] if asin_col else pd.Series([pd.NA] * len(cur), index=cur.index)
            sku_empty = s_sku.isna() | (s_sku.astype(str).str.strip() == "")
            asin_empty = s_asin.isna() | (s_asin.astype(str).str.strip() == "")
            both_missing_cur = sku_empty & asin_empty
            if "缺失标签" in sub.columns and "缺失标签" in cur.columns:
                sub_tag = sub.dropna(subset=["缺失标签", f]).copy()
                if not sub_tag.empty:
                    tag_map = sub_tag.set_index("缺失标签")[f].to_dict()
                    fill_mask = mask_na & both_missing_cur & cur["缺失标签"].notna()
                    cur.loc[fill_mask, f] = cur.loc[fill_mask, "缺失标签"].map(tag_map)
        
        # --- 新增逻辑：同步 SKU 到 MSKU (仅限缺失标签不为空的情况) ---
        if "缺失标签" in cur.columns:
            tag_not_na = cur["缺失标签"].notna()
            if tag_not_na.any():
                # 确保有 SKU 列 (作为源)
                current_sku_col = find_col(cur, ["sku", "SKU", "msku", "MSKU"])
                if current_sku_col:
                    # 确保有 MSKU 列 (作为目标)，没有则创建
                    if "MSKU" not in cur.columns:
                        cur["MSKU"] = pd.NA
                    
                    # 同步值：MSKU = SKU
                    # 注意：只针对缺失标签不为空的行
                    cur.loc[tag_not_na, "MSKU"] = cur.loc[tag_not_na, current_sku_col]

        result[name] = cur
    return result


def create_flexible_pivot(df: pd.DataFrame,
                          index_cols: Union[str, List[str]],
                          value_col: Union[str, List[str]],
                          agg_func: Union[str, List[str]] = "sum") -> pd.DataFrame:
    if isinstance(index_cols, str):
        index_cols = [index_cols]
    if isinstance(value_col, str):
        value_cols = [value_col]
    else:
        value_cols = value_col
    required_cols = index_cols + value_cols
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"DataFrame 缺少必需的列: {missing_cols}")
    pivot_table = pd.pivot_table(
        df,
        index=index_cols,
        values=value_cols,
        aggfunc=agg_func,
    )
    return pivot_table.reset_index()


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


def batch_match_fields_and_export_unmatched_eu(
    source_tables,
    calculate_information_eu,
    country=None,
    target_fields=None,
    output_path="欧洲未匹配记录.csv",
):
    """
    Europe matching function.
    Similar to batch_match_fields_and_export_unmatched but tailored for EU.
    Uses calculate_information_eu as the information table.
    Matches using ASIN and MSKU. If one is missing, tries to fill it using the other from the info table.
    """
    if target_fields is None:
        target_fields = [
            "物料大类",
            "物料中类",
            "物料小类",
            "辅助分类",
            "运营负责人",
            "采购价(不含税)",
            "头程"
        ]
        
    processed = {}
    unmatched_rows = []
    
    for name, df in source_tables.items():
        cur = df.copy()
        
        # Match fields
        for f in target_fields:
            cur = match_fields_to_df_robust(
                cur,
                f,
                product_property=calculate_information_eu,
                country=country,
                sku_col_candidates=["sku", "SKU", "msku", "MSKU"],
            )
            
        # Check for unmatched (logic reused from batch_match_fields_and_export_unmatched)
        sku_col = find_col(cur, ["sku", "SKU", "msku", "MSKU"])
        asin_col = find_col(cur, ["ASIN", "asin"]) or "ASIN"
        
        if asin_col not in cur.columns and "ASIN" in cur.columns:
            asin_col = "ASIN"
            
        sku_series = cur[sku_col] if sku_col else pd.Series([pd.NA] * len(cur), index=cur.index)
        asin_series = cur[asin_col] if asin_col in cur.columns else pd.Series([pd.NA] * len(cur), index=cur.index)
        
        # Missing keys
        sku_is_empty = sku_series.isna() | (sku_series.astype(str).str.strip() == "")
        asin_is_empty = asin_series.isna() | (asin_series.astype(str).str.strip() == "")
        both_missing = sku_is_empty & asin_is_empty
        
        # Tag missing
        cur["缺失标签"] = pd.NA
        cur.loc[both_missing, "缺失标签"] = pd.Series(
            [f"{name}-{i}" for i in cur.index],
            index=cur.index,
        ).loc[both_missing]
        
        # Identify rows where ANY target field is missing
        mask_unmatched = cur[target_fields].isna().any(axis=1)
        
        subset = pd.DataFrame(
            {
                "表": pd.Series([name] * len(cur), index=cur.index),
                "SKU": sku_series,
                "ASIN": asin_series,
                "缺失标签": cur["缺失标签"],
            },
            index=cur.index,
        )
        
        for f in target_fields:
            subset[f] = cur[f] if f in cur.columns else pd.NA
            
        unmatched_rows.append(subset.loc[mask_unmatched])
        processed[name] = cur

    if unmatched_rows:
        out_df = pd.concat(unmatched_rows, axis=0, ignore_index=True)
        out_df = out_df.drop_duplicates()
        out_df.to_csv(output_path, index=False)
    else:
        out_df = pd.DataFrame(columns=["表", "SKU", "ASIN", "缺失标签"] + target_fields)
        
    return processed, out_df
