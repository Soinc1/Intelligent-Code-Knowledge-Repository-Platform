-- =====================================================
-- 智能代码知识沉淀平台 - 数据库初始化SQL脚本
-- =====================================================
-- 说明：此脚本用于手动创建数据库和所有表结构
-- 使用方法：
--   1. 登录MySQL: mysql -u root -p
--   2. 执行此脚本: source scripts/init_database.sql
--   或: mysql -u root -p < scripts/init_database.sql
-- =====================================================

-- 设置字符集
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- =====================================================
-- 1. 创建数据库（如果不存在）
-- =====================================================
CREATE DATABASE IF NOT EXISTS `code_review_db` 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

USE `code_review_db`;

-- =====================================================
-- 2. 创建用户表 (users)
-- =====================================================
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    `username` VARCHAR(50) NOT NULL COMMENT '用户名',
    `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希',
    `email` VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
    `role` VARCHAR(20) DEFAULT 'user' COMMENT '角色: admin/reviewer/curator/developer/viewer',
    `is_active` INT DEFAULT 1 COMMENT '是否激活: 1=激活, 0=禁用',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `idx_username` (`username`),
    KEY `idx_role` (`role`),
    KEY `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- =====================================================
-- 3. 创建代码文件表 (code_files)
-- =====================================================
DROP TABLE IF EXISTS `code_files`;
CREATE TABLE `code_files` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '文件ID',
    `file_name` VARCHAR(255) NOT NULL COMMENT '文件名',
    `file_path` TEXT COMMENT '文件路径',
    `file_content` TEXT NOT NULL COMMENT '文件内容',
    `language` VARCHAR(50) DEFAULT NULL COMMENT '编程语言',
    `file_hash` VARCHAR(64) DEFAULT NULL COMMENT '文件哈希值（用于去重）',
    `ast_json` JSON DEFAULT NULL COMMENT 'AST解析结果（JSON格式）',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `idx_file_hash` (`file_hash`),
    KEY `idx_language` (`language`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='代码文件表';

-- =====================================================
-- 4. 创建审查评论表 (review_comments)
-- =====================================================
DROP TABLE IF EXISTS `review_comments`;
CREATE TABLE `review_comments` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '评论ID',
    `code_file_id` INT DEFAULT NULL COMMENT '关联的代码文件ID',
    `code_snippet` TEXT COMMENT '代码片段',
    `comment_text` TEXT NOT NULL COMMENT '评论内容',
    `comment_type` VARCHAR(50) DEFAULT NULL COMMENT '评论类型: security/performance/style/best_practice/general',
    `severity` VARCHAR(20) DEFAULT NULL COMMENT '严重程度: high/medium/low',
    `reviewer_id` INT DEFAULT NULL COMMENT '审查员ID',
    `review_date` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '审查时间',
    `milvus_id` VARCHAR(64) DEFAULT NULL COMMENT 'Milvus向量ID',
    `meta_data` JSON DEFAULT NULL COMMENT '元数据（JSON格式）',
    PRIMARY KEY (`id`),
    KEY `idx_code_file_id` (`code_file_id`),
    KEY `idx_comment_type` (`comment_type`),
    KEY `idx_severity` (`severity`),
    KEY `idx_review_date` (`review_date`),
    KEY `idx_reviewer_id` (`reviewer_id`),
    CONSTRAINT `fk_review_comments_code_file` 
        FOREIGN KEY (`code_file_id`) 
        REFERENCES `code_files` (`id`) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='审查评论表';

-- =====================================================
-- 5. 创建知识库表 (knowledge_base)
-- =====================================================
DROP TABLE IF EXISTS `knowledge_base`;
CREATE TABLE `knowledge_base` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '知识ID',
    `title` VARCHAR(255) NOT NULL COMMENT '知识标题',
    `content` TEXT NOT NULL COMMENT '知识内容',
    `category` VARCHAR(50) DEFAULT NULL COMMENT '分类: security/performance/style/best_practice',
    `code_pattern` TEXT COMMENT '代码模式',
    `best_practice` TEXT COMMENT '最佳实践',
    `milvus_id` VARCHAR(64) DEFAULT NULL COMMENT 'Milvus向量ID',
    `created_by` INT DEFAULT NULL COMMENT '创建者ID',
    `status` VARCHAR(20) DEFAULT 'pending_review' COMMENT '状态: draft/pending_review/published',
    `tags` JSON DEFAULT NULL COMMENT '标签（JSON数组）',
    `source_comment_id` INT DEFAULT NULL COMMENT '来源评论ID',
    `last_reviewed_by` INT DEFAULT NULL COMMENT '最后审核者ID',
    `review_notes` TEXT COMMENT '审核备注',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_category` (`category`),
    KEY `idx_status` (`status`),
    KEY `idx_created_by` (`created_by`),
    KEY `idx_created_at` (`created_at`),
    KEY `idx_source_comment_id` (`source_comment_id`),
    CONSTRAINT `fk_knowledge_base_source_comment` 
        FOREIGN KEY (`source_comment_id`) 
        REFERENCES `review_comments` (`id`) 
        ON DELETE SET NULL 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库表';

-- =====================================================
-- 6. 创建代码审查记录表 (code_reviews)
-- =====================================================
DROP TABLE IF EXISTS `code_reviews`;
CREATE TABLE `code_reviews` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '审查记录ID',
    `code_file_id` INT DEFAULT NULL COMMENT '关联的代码文件ID',
    `review_result` JSON DEFAULT NULL COMMENT '审查结果（JSON格式）',
    `matched_knowledge_ids` JSON DEFAULT NULL COMMENT '匹配的知识ID列表（JSON数组）',
    `review_time_ms` INT DEFAULT NULL COMMENT '审查耗时（毫秒）',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_code_file_id` (`code_file_id`),
    KEY `idx_created_at` (`created_at`),
    CONSTRAINT `fk_code_reviews_code_file` 
        FOREIGN KEY (`code_file_id`) 
        REFERENCES `code_files` (`id`) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='代码审查记录表';

-- =====================================================
-- 7. 创建操作日志表 (operation_logs)
-- =====================================================
DROP TABLE IF EXISTS `operation_logs`;
CREATE TABLE `operation_logs` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `user_id` INT DEFAULT NULL COMMENT '用户ID',
    `operation_type` VARCHAR(50) NOT NULL COMMENT '操作类型: code_review/knowledge_add/knowledge_extract/history_query/knowledge_approve/knowledge_reject',
    `operation_detail` JSON DEFAULT NULL COMMENT '操作详情（JSON格式）',
    `ip_address` VARCHAR(50) DEFAULT NULL COMMENT 'IP地址',
    `user_agent` VARCHAR(255) DEFAULT NULL COMMENT '用户代理',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_operation_type` (`operation_type`),
    KEY `idx_created_at` (`created_at`),
    CONSTRAINT `fk_operation_logs_user` 
        FOREIGN KEY (`user_id`) 
        REFERENCES `users` (`id`) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='操作日志表';

-- =====================================================
-- 8. 插入默认数据
-- =====================================================

-- 插入默认管理员用户
-- 用户名: root
-- 密码: 123456
-- 密码哈希: $2b$12$EF8fVrdHP6zZ6TSrkcb6WurAq9mKSpy7mwlrU2gj/WLg5Hc2zogz.
INSERT INTO `users` (`username`, `password_hash`, `role`, `is_active`, `email`) 
VALUES (
    'root', 
    '$2b$12$EF8fVrdHP6zZ6TSrkcb6WurAq9mKSpy7mwlrU2gj/WLg5Hc2zogz.', 
    'admin', 
    1,
    'admin@example.com'
) ON DUPLICATE KEY UPDATE 
    `password_hash` = '$2b$12$EF8fVrdHP6zZ6TSrkcb6WurAq9mKSpy7mwlrU2gj/WLg5Hc2zogz.',
    `role` = 'admin',
    `is_active` = 1;

-- =====================================================
-- 9. 创建视图（可选，用于统计查询）
-- =====================================================

-- 审查统计视图
CREATE OR REPLACE VIEW `v_review_statistics` AS
SELECT 
    DATE(rc.review_date) AS review_date,
    COUNT(*) AS total_comments,
    COUNT(DISTINCT rc.code_file_id) AS reviewed_files,
    COUNT(CASE WHEN rc.severity = 'high' THEN 1 END) AS high_severity_count,
    COUNT(CASE WHEN rc.severity = 'medium' THEN 1 END) AS medium_severity_count,
    COUNT(CASE WHEN rc.severity = 'low' THEN 1 END) AS low_severity_count,
    COUNT(CASE WHEN rc.comment_type = 'security' THEN 1 END) AS security_count,
    COUNT(CASE WHEN rc.comment_type = 'performance' THEN 1 END) AS performance_count,
    COUNT(CASE WHEN rc.comment_type = 'style' THEN 1 END) AS style_count,
    COUNT(CASE WHEN rc.comment_type = 'best_practice' THEN 1 END) AS best_practice_count
FROM review_comments rc
GROUP BY DATE(rc.review_date);

-- 知识库统计视图
CREATE OR REPLACE VIEW `v_knowledge_statistics` AS
SELECT 
    DATE(kb.created_at) AS created_date,
    COUNT(*) AS total_knowledge,
    COUNT(CASE WHEN kb.status = 'published' THEN 1 END) AS published_count,
    COUNT(CASE WHEN kb.status = 'pending_review' THEN 1 END) AS pending_count,
    COUNT(CASE WHEN kb.status = 'draft' THEN 1 END) AS draft_count,
    COUNT(CASE WHEN kb.category = 'security' THEN 1 END) AS security_count,
    COUNT(CASE WHEN kb.category = 'performance' THEN 1 END) AS performance_count,
    COUNT(CASE WHEN kb.category = 'style' THEN 1 END) AS style_count,
    COUNT(CASE WHEN kb.category = 'best_practice' THEN 1 END) AS best_practice_count
FROM knowledge_base kb
GROUP BY DATE(kb.created_at);

-- =====================================================
-- 10. 恢复外键检查
-- =====================================================
SET FOREIGN_KEY_CHECKS = 1;

-- =====================================================
-- 完成提示
-- =====================================================
SELECT '数据库初始化完成！' AS message;
SELECT '默认管理员账号: root / 123456' AS login_info;
SELECT COUNT(*) AS user_count FROM users;
SELECT COUNT(*) AS table_count FROM information_schema.tables 
    WHERE table_schema = 'code_review_db' 
    AND table_type = 'BASE TABLE';

