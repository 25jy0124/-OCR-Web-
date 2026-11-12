import streamlit as st
import cv2
import numpy as np
from PIL import Image
import easyocr
import time
import difflib

# ==========================================
# 1. 页面基本配置 (适配手机屏幕)
# ==========================================
st.set_page_config(
    page_title="日本食品过敏原OCR识别助手",
    page_icon="🔍",
    layout="centered"
)

st.title("🔍 日本食品成分・过敏原识别")
st.caption("拍摄食品包装背面的「原材料名」，自动检测过敏原与饮食禁忌")

# ==========================================
# 2. 过敏原与饮食禁忌字典 (日本特定原材料 + 常见禁忌)
# ==========================================
ALLERGEN_DB = {
    # 日本法定8大特定原材料 (必标)
    "小麦": {"en": "Wheat", "zh": "小麦 (麸质)", "level": "high"},
    "卵": {"en": "Egg", "zh": "鸡蛋/蛋类", "level": "high"},
    "乳成分": {"en": "Milk", "zh": "乳制品", "level": "high"},
    "えび": {"en": "Shrimp", "zh": "虾", "level": "high"},
    "かに": {"en": "Crab", "zh": "蟹", "level": "high"},
    "そば": {"en": "Buckwheat", "zh": "荞麦", "level": "high"},
    "落花生": {"en": "Peanut", "zh": "花生", "level": "high"},
    "くるみ": {"en": "Walnut", "zh": "核桃", "level": "high"},
    # 常见过敏原及留学生饮食禁忌 (猪肉/酒精等)
    "大豆": {"en": "Soybean", "zh": "大豆", "level": "medium"},
    "豚肉": {"en": "Pork", "zh": "猪肉 (清真禁忌)", "level": "high"},
    "牛肉": {"en": "Beef", "zh": "牛肉", "level": "medium"},
    "鶏肉": {"en": "Chicken", "zh": "鸡肉", "level": "medium"},
    "さけ": {"en": "Salmon", "zh": "三文鱼", "level": "medium"},
    "さば": {"en": "Mackerel", "zh": "鲭鱼", "level": "medium"},
    "ゼラチン": {"en": "Gelatin", "zh": "明胶 (常提取自猪/牛皮)", "level": "high"},
    "酒精": {"en": "Alcohol", "zh": "食用酒精 (清真禁忌)", "level": "high"},
    "アルコール": {"en": "Alcohol", "zh": "酒精", "level": "high"},
    "ごま": {"en": "Sesame", "zh": "芝麻", "level": "medium"},
    "アーモンド": {"en": "Almond", "zh": "杏仁/扁桃仁", "level": "medium"},
}

# ==========================================
# 3. 加载 OCR 模型 (使用缓存避免每次刷新重新加载)
# ==========================================
@st.cache_resource
def load_ocr_model():
    # 加载日语和英语模型，gpu=False 保证普通笔记本CPU也能稳定运行
    reader = easyocr.Reader(['ja', 'en'], gpu=False)
    return reader

with st.spinner("正在初始化日文 OCR 识别引擎 (首次启动需下载模型，约1分钟)..."):
    reader = load_ocr_model()

# ==========================================
# 4. 图像预处理函数 (小论文对比实验核心模块)
# ==========================================
def preprocess_image(pil_image, use_clahe=True, use_denoise=True):
    # 将 PIL 图像转换为 OpenCV BGR 格式
    img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    
    # 1. 转为灰度图
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. 限制对比度自适应直方图均衡化 (CLAHE) -> 专门抑制食品塑料袋表面反光
    if use_clahe:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
    # 3. 高斯滤波去噪 -> 消除包装印刷纹理干扰
    if use_denoise:
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        
    return gray

# ==========================================
# 5. 过敏原匹配算法 (支持精确匹配 + 容错模糊匹配)
# ==========================================
def detect_allergens(text_list, selected_targets, enable_fuzzy=True):
    detected = []
    full_text = "".join(text_list)
    
    for target in selected_targets:
        info = ALLERGEN_DB[target]
        # 策略A：精确子串匹配
        if target in full_text:
            detected.append({
                "keyword": target,
                "info": info,
                "match_type": "精确匹配",
                "matched_word": target
            })
        # 策略B：针对汉字易错字 (如"小麦"误识别为"小変") 的滑动窗口模糊匹配
        elif enable_fuzzy and len(target) >= 2:
            window_size = len(target)
            for i in range(len(full_text) - window_size + 1):
                sub = full_text[i:i + window_size]
                similarity = difflib.SequenceMatcher(None, target, sub).ratio()
                if similarity >= 0.5 and target[0] == sub[0]: # 首字相同且相似度达标
                    detected.append({
                        "keyword": target,
                        "info": info,
                        "match_type": f"模糊容错匹配 (识别为:{sub})",
                        "matched_word": sub
                    })
                    break
    return detected, full_text

# ==========================================
# 6. 侧边栏：实验参数与用户饮食偏好设置
# ==========================================
with st.sidebar:
    st.header("⚙️ 个人禁忌设置")
    selected_allergens = st.multiselect(
        "选择需要重点排查的成分：",
        options=list(ALLERGEN_DB.keys()),
        default=["小麦", "卵", "乳成分", "豚肉", "ゼラチン", "アルコール", "えび"]
    )
    
    st.divider()
    st.header("🔬 论文实验控制面板")
    enable_preprocess = st.checkbox("启用 OpenCV 抗反光预处理", value=True)
    enable_fuzzy = st.checkbox("启用形近字模糊容错匹配", value=True)
    show_bbox = st.checkbox("在原图上绘制 OCR 识别框", value=True)

# ==========================================
# 7. 主界面：手机拍照 / 上传与结果展示
# ==========================================
uploaded_file = st.file_uploader(
    "📷 点击下方按钮拍摄或选择商品配料表照片",
    type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
    # 读取图片并限制最大宽度以加快手机端处理速度
    raw_image = Image.open(uploaded_file).convert("RGB")
    max_width = 1000
    if raw_image.width > max_width:
        ratio = max_width / raw_image.width
        raw_image = raw_image.resize((max_width, int(raw_image.height * ratio)))

    st.image(raw_image, caption="已上传的包装图像", use_container_width=True)

    if st.button("🚀 开始识别分析", type="primary", use_container_width=True):
        start_time = time.time()
        
        with st.spinner("正在进行图像增强与日文 OCR 提取..."):
            # 1. 图像预处理
            if enable_preprocess:
                processed_img = preprocess_image(raw_image)
            else:
                processed_img = np.array(raw_image)
                
            # 2. 执行 OCR 识别
            # detail=1 返回 [(坐标框, 识别文本, 置信度), ...]
            ocr_results = reader.readtext(processed_img, detail=1)
            
            extracted_texts = [res[1] for res in ocr_results]
            confidences = [res[2] for res in ocr_results]
            avg_conf = (sum(confidences) / len(confidences) * 100) if confidences else 0
            
            # 3. 过敏原检索
            detected_items, combined_text = detect_allergens(
                extracted_texts, selected_allergens, enable_fuzzy
            )
            
        elapsed_time = time.time() - start_time

        # --- 结果展示区 ---
        st.divider()
        st.subheader("📋 检测结果")
        
        if detected_items:
            st.error(f"⚠️ 警告：检测到 {len(detected_items)} 项关注成分！")
            for item in detected_items:
                info = item["info"]
                st.markdown(
                    f"- **{item['keyword']}** ({info['zh']} / {info['en']}) "
                    f"— `{item['match_type']}`"
                )
        else:
            st.success("✅ 未在识别文本中发现您设定的过敏原或禁忌成分。")

        # --- 性能指标 (方便写小论文记录数据) ---
        col1, col2, col3 = st.columns(3)
        col1.metric("处理总耗时", f"{elapsed_time:.2f} 秒")
        col2.metric("提取文本块", f"{len(extracted_texts)} 处")
        col3.metric("平均置信度", f"{avg_conf:.1f} %")

        # --- 可视化检测框与原始文本 ---
        if show_bbox and ocr_results:
            vis_img = np.array(raw_image).copy()
            for (bbox, text, prob) in ocr_results:
                top_left = tuple(map(int, bbox[0]))
                bottom_right = tuple(map(int, bbox[2]))
                # 如果该文本框包含过敏原，用红色框标出，否则用绿色框
                is_danger = any(d["matched_word"] in text for d in detected_items)
                color = (255, 0, 0) if is_danger else (0, 200, 0)
                cv2.rectangle(vis_img, top_left, bottom_right, color, 3)
            st.image(vis_img, caption="OCR 定位框 (红框=命中禁忌成分，绿框=普通文本)", use_container_width=True)

        with st.expander("查看 OCR 提取的完整日文原文"):
            st.write(" / ".join(extracted_texts))