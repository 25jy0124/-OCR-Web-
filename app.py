import streamlit as st
import cv2
import numpy as np
from PIL import Image
import easyocr
import pymysql
import time
import difflib

# ==========================================
# 1. 页面基本配置
# ==========================================
st.set_page_config(
    page_title="日本食品过敏原OCR识别助手",
    page_icon="🔍",
    layout="centered"
)

st.title("🔍 日本食品成分・过敏原识别")
st.caption("Docker MySQL 持久化存储 + 日文 OCR 实时识别")

# ==========================================
# 2. MySQL 数据库连接与 CRUD 操作
# ==========================================
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "rootpassword",
    "database": "allergen_db",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def fetch_default_allergens():
    """从 SQL 获取系统默认常见过敏原"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT keyword, zh_name, en_name, risk_level FROM default_allergens ORDER BY id ASC")
            return cursor.fetchall()
    finally:
        conn.close()

def fetch_user_allergens(user_id):
    """从 SQL 获取指定用户的个人自定义过敏原"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT id, keyword, zh_name, en_name FROM user_allergens WHERE user_id = %s ORDER BY created_at DESC"
            cursor.execute(sql, (user_id,))
            return cursor.fetchall()
    finally:
        conn.close()

def add_user_allergen(user_id, keyword, zh_name, en_name):
    """向 SQL 插入用户自定义过敏原"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO user_allergens (user_id, keyword, zh_name, en_name)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE zh_name = VALUES(zh_name), en_name = VALUES(en_name)
            """
            cursor.execute(sql, (user_id, keyword.strip(), zh_name.strip(), en_name.strip() or "Custom"))
        conn.commit()
    finally:
        conn.close()

def delete_user_allergen(record_id):
    """从 SQL 删除用户自定义过敏原"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM user_allergens WHERE id = %s", (record_id,))
        conn.commit()
    finally:
        conn.close()

# ==========================================
# 3. 加载 OCR 模型
# ==========================================
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['ja', 'en'], gpu=False)

with st.spinner("正在初始化日文 OCR 识别引擎..."):
    reader = load_ocr_model()

# ==========================================
# 4. 图像预处理与过敏原检索逻辑
# ==========================================
def preprocess_image(pil_image, use_clahe=True, use_denoise=True):
    img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if use_clahe:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    if use_denoise:
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return gray

def detect_allergens(text_list, target_dict, enable_fuzzy=True):
    detected = []
    full_text = "".join(text_list)
    
    for keyword, info in target_dict.items():
        if keyword in full_text:
            detected.append({
                "keyword": keyword,
                "info": info,
                "match_type": "精确匹配",
                "matched_word": keyword
            })
        elif enable_fuzzy and len(keyword) >= 2:
            window_size = len(keyword)
            for i in range(len(full_text) - window_size + 1):
                sub = full_text[i:i + window_size]
                similarity = difflib.SequenceMatcher(None, keyword, sub).ratio()
                if similarity >= 0.5 and keyword[0] == sub[0]:
                    detected.append({
                        "keyword": keyword,
                        "info": info,
                        "match_type": f"模糊容错 (识别为:{sub})",
                        "matched_word": sub
                    })
                    break
    return detected, full_text

# ==========================================
# 5. 连接数据库并读取数据
# ==========================================
try:
    default_list = fetch_default_allergens()
except Exception as e:
    st.error(f"❌ 无法连接到 Docker MySQL 数据库，请先运行 `docker compose up -d`。错误详情: {e}")
    st.stop()

# 侧边栏：实验控制开关
with st.sidebar:
    st.header("👤 当前用户档案")
    current_user = st.text_input("输入用户名/学号 (隔离个人SQL列表)", value="student_01")
    
    st.divider()
    st.header("🔬 论文实验控制面板")
    enable_preprocess = st.checkbox("启用 OpenCV 抗反光预处理", value=True)
    enable_fuzzy = st.checkbox("启用形近字模糊容错匹配", value=True)
    show_bbox = st.checkbox("在原图上绘制 OCR 识别框", value=True)

user_custom_list = fetch_user_allergens(current_user)

# ==========================================
# 6. 主界面双标签页：拍照识别 vs 过敏原SQL管理
# ==========================================
tab_scan, tab_db = st.tabs(["📷 拍照识别配料表", "🗄️ 过敏原与个人禁忌库 (SQL)"])

# --- 标签页 2：查看默认库 & 增删个人 SQL 列表 ---
with tab_db:
    st.subheader(f"➕ 添加个人专属过敏原/禁忌 (用户: {current_user})")
    with st.form("add_allergen_form", clear_on_submit=True):
        col_a, col_b, col_c = st.columns([2, 2, 2])
        new_kw = col_a.text_input("日文关键词 (必填)", placeholder="例: マンゴー / ラード")
        new_zh = col_b.text_input("中文说明 (必填)", placeholder="例: 芒果 / 猪油")
        new_en = col_c.text_input("英文说明 (可选)", placeholder="例: Mango / Lard")
        submitted = st.form_submit_button("💾 保存到个人 SQL 列表", use_container_width=True)
        
        if submitted:
            if new_kw.strip() and new_zh.strip():
                add_user_allergen(current_user, new_kw, new_zh, new_en)
                st.success(f"已将「{new_kw} ({new_zh})」存入 MySQL 数据库！")
                st.rerun()
            else:
                st.warning("请填写日文关键词和中文说明。")

    st.divider()
    st.subheader(f"📌 我的个人 SQL 过敏原列表 ({len(user_custom_list)} 项)")
    if user_custom_list:
        for item in user_custom_list:
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"- **{item['keyword']}** — {item['zh_name']} ({item['en_name']}) `[个人自定义]`")
            if c2.button("删除", key=f"del_{item['id']}"):
                delete_user_allergen(item['id'])
                st.rerun()
    else:
        st.info("当前个人 SQL 列表为空，可在上方表单添加（如：ラード/猪油、キウイ/猕猴桃）。")

    st.divider()
    st.subheader(f"📚 系统默认常见过敏原库 ({len(default_list)} 项 - 来自 MySQL)")
    st.dataframe(
        default_list,
        column_config={
            "keyword": "日文关键词",
            "zh_name": "中文释义",
            "en_name": "英文释义",
            "risk_level": "风险等级"
        },
        use_container_width=True,
        hide_index=True
    )

# --- 标签页 1：拍照识别 ---
with tab_scan:
    # 构建本次检测使用的目标字典（默认选中项 + 个人SQL全量项）
    default_keywords = [row["keyword"] for row in default_list]
    
    with st.expander("🎯 选择本次要排查的【系统默认过敏原】（个人SQL列表将自动全部纳入排查）", expanded=False):
        selected_defaults = st.multiselect(
            "勾选默认过敏原：",
            options=default_keywords,
            default=["小麦", "卵", "乳成分", "豚肉", "ゼラチン", "アルコール", "えび"]
        )

    # 合并目标字典
    active_targets = {}
    for row in default_list:
        if row["keyword"] in selected_defaults:
            active_targets[row["keyword"]] = {
                "zh": row["zh_name"],
                "en": row["en_name"],
                "source": "系统默认库"
            }
    for row in user_custom_list:
        active_targets[row["keyword"]] = {
            "zh": row["zh_name"],
            "en": row["en_name"],
            "source": "个人SQL自定义"
        }

    st.caption(f"当前生效排查规则：系统默认 {len(selected_defaults)} 项 + 个人自定义 {len(user_custom_list)} 项")

    uploaded_file = st.file_uploader(
        "📷 点击下方按钮拍摄或选择商品配料表照片",
        type=["jpg", "jpeg", "png"]
    )

    if uploaded_file is not None:
        raw_image = Image.open(uploaded_file).convert("RGB")
        max_width = 1000
        if raw_image.width > max_width:
            ratio = max_width / raw_image.width
            raw_image = raw_image.resize((max_width, int(raw_image.height * ratio)))

        st.image(raw_image, caption="已上传的包装图像", use_container_width=True)

        if st.button("🚀 开始识别分析", type="primary", use_container_width=True):
            start_time = time.time()
            with st.spinner("正在进行图像增强与日文 OCR 提取..."):
                processed_img = preprocess_image(raw_image) if enable_preprocess else np.array(raw_image)
                ocr_results = reader.readtext(processed_img, detail=1)
                
                extracted_texts = [res[1] for res in ocr_results]
                confidences = [res[2] for res in ocr_results]
                avg_conf = (sum(confidences) / len(confidences) * 100) if confidences else 0
                
                detected_items, _ = detect_allergens(extracted_texts, active_targets, enable_fuzzy)
                
            elapsed_time = time.time() - start_time

            st.divider()
            st.subheader("📋 检测结果")
            
            if detected_items:
                st.error(f"⚠️ 警告：检测到 {len(detected_items)} 项关注成分！")
                for item in detected_items:
                    info = item["info"]
                    st.markdown(
                        f"- **{item['keyword']}** ({info['zh']} / {info['en']}) "
                        f"— `{item['match_type']}` | 来源: **{info['source']}**"
                    )
            else:
                st.success("✅ 未在识别文本中发现您设定的过敏原或禁忌成分。")

            col1, col2, col3 = st.columns(3)
            col1.metric("处理总耗时", f"{elapsed_time:.2f} 秒")
            col2.metric("提取文本块", f"{len(extracted_texts)} 处")
            col3.metric("平均置信度", f"{avg_conf:.1f} %")

            if show_bbox and ocr_results:
                vis_img = np.array(raw_image).copy()
                for (bbox, text, prob) in ocr_results:
                    top_left = tuple(map(int, bbox[0]))
                    bottom_right = tuple(map(int, bbox[2]))
                    is_danger = any(d["matched_word"] in text for d in detected_items)
                    color = (255, 0, 0) if is_danger else (0, 200, 0)
                    cv2.rectangle(vis_img, top_left, bottom_right, color, 3)
                st.image(vis_img, caption="OCR 定位框 (红框=命中禁忌成分，绿框=普通文本)", use_container_width=True)

            with st.expander("查看 OCR 提取的完整日文原文"):
                st.write(" / ".join(extracted_texts))