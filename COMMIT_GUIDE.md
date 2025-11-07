# GitHub 提交指南

## 📁 需要提交的文件

### ✅ 核心代码文件
```
airtest_ocr_utils/
├── ocr_utils.py          # 主功能文件
├── ocr_utils.pyi         # 类型提示文件
├── py.typed              # 类型提示标记
├── __init__.py           # 包初始化文件
└── __init__.pyi          # 包类型提示
```

### ✅ 配置文件
```
README.md                 # 项目说明文档
requirements.txt          # 依赖列表
setup.py                 # 包安装配置
USAGE_GUIDE.md           # 使用指南
COMMIT_GUIDE.md          # 提交指南（本文件）
.gitignore               # Git忽略规则
```

### ✅ 示例文件（可选）
```
test.py                  # 测试示例（可选提交）
```

## 🚫 不需要提交的文件

### ❌ 自动生成文件
```
airtest_ocr_utils.egg-info/  # 包元数据（自动生成）
__pycache__/                 # Python缓存文件
*.pyc                        # 编译后的Python文件
```

### ❌ 虚拟环境
```
env/                        # 虚拟环境目录
venv/                       # 虚拟环境目录
```

### ❌ 临时文件
```
temp_screenshot*           # 临时截图文件
*.log                      # 日志文件
```

## 📋 提交命令

```bash
# 添加所有需要提交的文件
git add .

# 提交更改
git commit -m "feat: 添加Airtest OCR工具库"

# 推送到GitHub
git push origin main
```

## 🔧 首次设置（如果还没有关联远程仓库）

```bash
# 初始化Git（如果还没有）
git init

# 添加远程仓库
git remote add origin https://github.com/lovefan-fan/airtest-ocr.git

# 首次推送
git push -u origin main
```

## 💡 注意事项

1. **确保 `.gitignore` 文件已正确配置**
2. **不要提交虚拟环境文件**
3. **不要提交自动生成的包元数据**
4. **测试前确保激活虚拟环境**
5. **提交前运行测试确保功能正常**

现在您的项目已经准备好提交到 GitHub 了！🎉
