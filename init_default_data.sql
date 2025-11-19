-- =====================================================
-- 智能代码知识沉淀平台 - 默认数据SQL脚本
-- =====================================================
-- 说明：此脚本仅插入默认数据（默认管理员用户）
-- 使用方法：
--   mysql -u root -p code_review_db < scripts/init_default_data.sql
-- =====================================================

USE `code_review_db`;

-- =====================================================
-- 插入默认管理员用户
-- =====================================================
-- 用户名: root
-- 密码: 123456
-- 密码哈希: $2b$12$EF8fVrdHP6zZ6TSrkcb6WurAq9mKSpy7mwlrU2gj/WLg5Hc2zogz.
-- 角色: admin
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
    `is_active` = 1,
    `email` = 'admin@example.com';

-- =====================================================
-- 可选：插入示例测试用户（开发环境使用）
-- =====================================================
-- 取消下面的注释以创建测试用户

/*
-- 测试审核员用户
INSERT INTO `users` (`username`, `password_hash`, `role`, `is_active`, `email`) 
VALUES (
    'reviewer', 
    '$2b$12$EF8fVrdHP6zZ6TSrkcb6WurAq9mKSpy7mwlrU2gj/WLg5Hc2zogz.', 
    'reviewer', 
    1,
    'reviewer@example.com'
) ON DUPLICATE KEY UPDATE 
    `password_hash` = '$2b$12$EF8fVrdHP6zZ6TSrkcb6WurAq9mKSpy7mwlrU2gj/WLg5Hc2zogz.',
    `role` = 'reviewer',
    `is_active` = 1;

-- 测试开发者用户
INSERT INTO `users` (`username`, `password_hash`, `role`, `is_active`, `email`) 
VALUES (
    'developer', 
    '$2b$12$EF8fVrdHP6zZ6TSrkcb6WurAq9mKSpy7mwlrU2gj/WLg5Hc2zogz.', 
    'developer', 
    1,
    'developer@example.com'
) ON DUPLICATE KEY UPDATE 
    `password_hash` = '$2b$12$EF8fVrdHP6zZ6TSrkcb6WurAq9mKSpy7mwlrU2gj/WLg5Hc2zogz.',
    `role` = 'developer',
    `is_active` = 1;
*/

SELECT '默认数据插入完成！' AS message;
SELECT '默认管理员账号: root / 123456' AS login_info;
SELECT COUNT(*) AS user_count FROM users;

