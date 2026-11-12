SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS allergen_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE allergen_db;

-- 1. 系统默认常见过敏原表
CREATE TABLE IF NOT EXISTS default_allergens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(50) NOT NULL UNIQUE COMMENT '日文关键词',
    zh_name VARCHAR(100) NOT NULL COMMENT '中文释义',
    en_name VARCHAR(100) NOT NULL COMMENT '英文释义',
    risk_level VARCHAR(20) DEFAULT 'high' COMMENT '风险等级'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 用户个人自定义过敏原/禁忌表
CREATE TABLE IF NOT EXISTS user_allergens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL COMMENT '用户标识(如学号/昵称)',
    keyword VARCHAR(50) NOT NULL COMMENT '自定义日文关键词',
    zh_name VARCHAR(100) NOT NULL COMMENT '中文备注',
    en_name VARCHAR(100) DEFAULT 'Custom' COMMENT '英文备注',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_keyword (user_id, keyword)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 插入原有的默认过敏原初始数据
INSERT IGNORE INTO default_allergens (keyword, zh_name, en_name, risk_level) VALUES
('小麦', '小麦 (麸质)', 'Wheat', 'high'),
('卵', '鸡蛋/蛋类', 'Egg', 'high'),
('乳成分', '乳制品', 'Milk', 'high'),
('えび', '虾', 'Shrimp', 'high'),
('かに', '蟹', 'Crab', 'high'),
('そば', '荞麦', 'Buckwheat', 'high'),
('落花生', '花生', 'Peanut', 'high'),
('くるみ', '核桃', 'Walnut', 'high'),
('大豆', '大豆', 'Soybean', 'medium'),
('豚肉', '猪肉 (清真禁忌)', 'Pork', 'high'),
('牛肉', '牛肉', 'Beef', 'medium'),
('鶏肉', '鸡肉', 'Chicken', 'medium'),
('さけ', '三文鱼', 'Salmon', 'medium'),
('さば', '鲭鱼', 'Mackerel', 'medium'),
('ゼラチン', '明胶 (常提取自猪/牛皮)', 'Gelatin', 'high'),
('酒精', '食用酒精 (清真禁忌)', 'Alcohol', 'high'),
('アルコール', '酒精', 'Alcohol', 'high'),
('ごま', '芝麻', 'Sesame', 'medium'),
('アーモンド', '杏仁/扁桃仁', 'Almond', 'medium');