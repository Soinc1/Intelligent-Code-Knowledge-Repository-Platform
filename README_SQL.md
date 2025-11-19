# SQL脚本使用说明

本目录包含用于手动初始化数据库的SQL脚本。

## 脚本文件说明

### 1. `init_database.sql` - 完整初始化脚本（推荐）

**功能：**
- 创建数据库（如果不存在）
- 创建所有表结构
- 创建索引和外键约束
- 创建统计视图
- 插入默认管理员用户

**使用场景：**
- 全新安装
- 需要完整重建数据库

**使用方法：**

```bash
# 方法1: 在MySQL命令行中执行
mysql -u root -p < scripts/init_database.sql

# 方法2: 登录MySQL后执行
mysql -u root -p
source scripts/init_database.sql

# 方法3: 指定数据库执行
mysql -u root -p code_review_db < scripts/init_database.sql
```

### 2. `init_database_structure_only.sql` - 仅表结构脚本

**功能：**
- 仅创建表结构
- 创建索引和外键约束
- 创建统计视图
- **不包含**默认数据

**使用场景：**
- 已有数据库，只需要创建表结构
- 不想覆盖现有数据
- 分步骤初始化

**使用方法：**

```bash
# 确保数据库已存在
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS code_review_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 执行表结构脚本
mysql -u root -p code_review_db < scripts/init_database_structure_only.sql
```

### 3. `init_default_data.sql` - 仅默认数据脚本

**功能：**
- 仅插入默认管理员用户
- 使用 `ON DUPLICATE KEY UPDATE` 避免重复插入

**使用场景：**
- 表结构已存在，只需要添加默认用户
- 重置管理员密码

**使用方法：**

```bash
mysql -u root -p code_review_db < scripts/init_default_data.sql
```

## 默认账号信息

执行脚本后，系统会创建默认管理员账号：

- **用户名**: `root`
- **密码**: `123456`
- **角色**: `admin`
- **权限**: 拥有所有功能权限

**⚠️ 安全提示：** 生产环境请立即修改默认密码！

## 数据库结构

### 表列表

1. **users** - 用户表
   - 存储用户账号、密码、角色等信息

2. **code_files** - 代码文件表
   - 存储上传的代码文件内容、AST解析结果等

3. **review_comments** - 审查评论表
   - 存储代码审查的评论和建议

4. **knowledge_base** - 知识库表
   - 存储团队知识库条目

5. **code_reviews** - 代码审查记录表
   - 存储完整的审查记录和结果

6. **operation_logs** - 操作日志表
   - 记录所有用户操作

### 视图列表

1. **v_review_statistics** - 审查统计视图
   - 按日期统计审查数据

2. **v_knowledge_statistics** - 知识库统计视图
   - 按日期统计知识库数据

## 常见问题

### Q1: 执行脚本时提示"数据库不存在"

**解决：**
```bash
# 先创建数据库
mysql -u root -p -e "CREATE DATABASE code_review_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 再执行脚本
mysql -u root -p code_review_db < scripts/init_database.sql
```

### Q2: 执行脚本时提示"外键约束错误"

**解决：**
- 确保使用 `init_database.sql` 完整脚本，它会按正确顺序创建表
- 或者先执行 `init_database_structure_only.sql` 创建表结构

### Q3: 如何重置数据库？

**解决：**
```bash
# 删除数据库（⚠️ 会丢失所有数据）
mysql -u root -p -e "DROP DATABASE IF EXISTS code_review_db;"

# 重新执行初始化脚本
mysql -u root -p < scripts/init_database.sql
```

### Q4: 如何修改默认管理员密码？

**方法1：** 使用系统前端修改（登录后修改密码）

**方法2：** 使用SQL修改
```sql
-- 需要先使用Python生成新的密码哈希
-- python -c "from passlib.context import CryptContext; pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto'); print(pwd_context.hash('新密码'))"

-- 然后执行SQL
UPDATE users SET password_hash = '新的密码哈希值' WHERE username = 'root';
```

### Q5: 如何备份数据库？

**解决：**
```bash
# 备份整个数据库
mysqldump -u root -p code_review_db > backup_$(date +%Y%m%d_%H%M%S).sql

# 仅备份表结构
mysqldump -u root -p --no-data code_review_db > backup_structure.sql

# 仅备份数据
mysqldump -u root -p --no-create-info code_review_db > backup_data.sql
```

### Q6: 如何恢复数据库？

**解决：**
```bash
# 恢复整个数据库
mysql -u root -p code_review_db < backup_20240101_120000.sql

# 或先创建数据库再恢复
mysql -u root -p -e "CREATE DATABASE code_review_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p code_review_db < backup_20240101_120000.sql
```

## 字符集说明

所有表和数据库都使用 `utf8mb4` 字符集和 `utf8mb4_unicode_ci` 排序规则，支持完整的UTF-8字符（包括emoji）。

## 索引说明

为了提高查询性能，脚本为以下字段创建了索引：

- **users**: `username` (唯一), `role`, `is_active`
- **code_files**: `file_hash` (唯一), `language`, `created_at`
- **review_comments**: `code_file_id`, `comment_type`, `severity`, `review_date`, `reviewer_id`
- **knowledge_base**: `category`, `status`, `created_by`, `created_at`, `source_comment_id`
- **code_reviews**: `code_file_id`, `created_at`
- **operation_logs**: `user_id`, `operation_type`, `created_at`

## 外键约束说明

外键约束确保数据完整性：

- `review_comments.code_file_id` → `code_files.id` (CASCADE删除)
- `knowledge_base.source_comment_id` → `review_comments.id` (SET NULL删除)
- `code_reviews.code_file_id` → `code_files.id` (CASCADE删除)
- `operation_logs.user_id` → `users.id` (CASCADE删除)

## 注意事项

1. **生产环境**：执行脚本前请先备份现有数据
2. **权限要求**：执行脚本需要CREATE、DROP、ALTER等权限
3. **字符集**：确保MySQL服务器支持utf8mb4字符集
4. **版本要求**：MySQL 8.0+（支持JSON字段）
5. **默认密码**：生产环境请立即修改默认管理员密码

## 相关文档

- [主README.md](../README.md) - 项目主文档
- [技术方案实现文档.md](../技术方案实现文档.md) - 技术架构文档

