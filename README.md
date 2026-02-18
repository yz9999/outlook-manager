# Outlook 邮箱管理系统

多账号 Outlook 邮箱管理平台，支持邮件查看、分组管理、自动同步、批量导入。

## 技术栈

- **后端**: Python FastAPI + SQLite + Microsoft Graph API
- **前端**: Vue 3 + Vite + Pinia

## 功能

- ✅ 多账号管理 (添加/删除/同步)
- ✅ 分组管理 (创建/删除/分配账号)
- ✅ 批量导入
- ✅ 邮件列表查看 (收件箱)
- ✅ 邮件详情 (HTML 渲染)
- ✅ 按分组自动同步 (每 30 分钟，每批 10-15 个账号)
- ✅ 新邮件提醒
- ✅ 深色主题 UI

---

## 本地开发

配置文件：.env.example更改.env，
.env.example
# Auth credentials
AUTH_USERNAME=admin #用户名
AUTH_PASSWORD=your-password-here #密码，不设置默认change-me
AUTH_SECRET=your-random-secret-key-here

# Azure App client_id for device code flow
DEFAULT_CLIENT_ID=your-azure-app-client-id #client_id用于没有refresh_token的账号获取refresh_token

### 1. 安装后端依赖

```bash
cd backend
pip3 install -r requirements.txt
```

### 2. 安装前端依赖

```bash
cd frontend
npm install
```

### 3. 启动开发模式

```bash
# 后端 (端口 8000)
cd backend
python3 -m uvicorn main:app --reload --port 8000

# 前端 (端口 3000, 另一个终端)
cd frontend
npm run dev
```

访问 http://localhost:3000

---

## 🚀 服务器部署教程

### 前提条件

- Linux 服务器 (Ubuntu 20.04+ / CentOS 7+ / Debian 10+)
- Python 3.9+
- Node.js 18+ (仅构建时需要，部署后可卸载)
- 一个域名（可选，但推荐）

---

### 第一步：上传项目到服务器

**方式 A：使用 scp**
```bash
# 在本地执行，将整个项目上传到服务器
scp -r /path/to/outlook-manager user@your-server-ip:/opt/
```

**方式 B：使用 Git**
```bash
# 在服务器上
cd /opt
git clone <你的仓库地址> outlook-manager
```

**方式 C：使用 rsync（推荐，支持增量同步）**
```bash
rsync -avz --exclude 'node_modules' --exclude '__pycache__' --exclude '.DS_Store' \
  /path/to/outlook-manager/ user@your-server-ip:/opt/outlook-manager/
```

---

### 第二步：安装系统依赖

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm

# CentOS / RHEL
sudo yum install -y python3 python3-pip nodejs npm
```

---

### 第三步：配置后端

```bash
cd /opt/outlook-manager/backend

# 创建 Python 虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**可选：设置环境变量**

```bash
# 同步间隔（默认 30 分钟）
export SYNC_INTERVAL=30

# 每批同步账号数（默认 12）
export SYNC_BATCH_SIZE=12
```

---

### 第四步：构建前端

```bash
cd /opt/outlook-manager/frontend

# 安装依赖
npm install

# 构建生产版本（输出到 dist 目录）
npm run build

# 构建完成后，node_modules 可以删除以节省空间
rm -rf node_modules
```

> 构建后的前端静态文件在 `frontend/dist/`，后端会自动挂载该目录。

---

### 第五步：测试运行

```bash
cd /opt/outlook-manager/backend
source venv/bin/activate

# 测试启动（前台运行，确认无报错）
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

打开浏览器访问 `http://你的服务器IP:8000`，确认页面正常显示。

确认无误后 `Ctrl+C` 停止。

---

### 第六步：使用 systemd 守护进程（推荐）

创建服务文件：

```bash
sudo nano /etc/systemd/system/outlook-manager.service
```

写入以下内容：

```ini
[Unit]
Description=Outlook Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/outlook-manager/backend
Environment="PATH=/opt/outlook-manager/backend/venv/bin:/usr/local/bin:/usr/bin"
Environment="SYNC_INTERVAL=30"
Environment="SYNC_BATCH_SIZE=12"
ExecStart=/opt/outlook-manager/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用并启动服务：

```bash
# 重新加载配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start outlook-manager

# 设为开机自启
sudo systemctl enable outlook-manager

# 查看状态
sudo systemctl status outlook-manager

# 查看日志
sudo journalctl -u outlook-manager -f
```

**常用管理命令：**

```bash
sudo systemctl restart outlook-manager   # 重启
sudo systemctl stop outlook-manager      # 停止
sudo journalctl -u outlook-manager -n 50 # 查看最近 50 行日志
```

---

### 第七步：配置 Nginx 反向代理（推荐）

安装 Nginx：
```bash
sudo apt install -y nginx   # Ubuntu/Debian
sudo yum install -y nginx   # CentOS
```

创建配置文件：

```bash
sudo nano /etc/nginx/sites-available/outlook-manager
```

写入：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名或 IP

    # 前端静态文件
    location / {
        root /opt/outlook-manager/frontend/dist;
        index index.html;
        try_files $uri $uri/ /index.html;  # SPA 路由支持
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;  # 同步可能需要较长时间
    }
}
```

启用配置：

```bash
# Ubuntu/Debian
sudo ln -sf /etc/nginx/sites-available/outlook-manager /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# CentOS (直接编辑 /etc/nginx/conf.d/outlook-manager.conf)

# 测试配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

现在可以通过 `http://your-domain.com` 访问。

---

### 第八步：配置 HTTPS（可选但推荐）

使用免费的 Let's Encrypt 证书：

```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx   # Ubuntu/Debian

# 自动配置 HTTPS
sudo certbot --nginx -d your-domain.com

# 自动续期（Certbot 会自动添加定时任务）
sudo certbot renew --dry-run
```

---

### 第九步：配置防火墙

```bash
# Ubuntu (ufw)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# CentOS (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

---

## 更新部署

当代码更新后，在服务器上执行：

```bash
# 1. 上传新代码
rsync -avz --exclude 'node_modules' --exclude '__pycache__' --exclude 'data' \
  /path/to/outlook-manager/ user@server:/opt/outlook-manager/

# 2. 重新构建前端
cd /opt/outlook-manager/frontend
npm install && npm run build

# 3. 重启后端
sudo systemctl restart outlook-manager
```

> ⚠️ 注意：`--exclude 'data'` 确保不覆盖服务器上的数据库文件。

---

## 批量导入格式

一行一个账号，字段用 `----` 分隔：

```
邮箱----密码----client_id----refresh_token
```

---

## 目录结构

```
outlook-manager/
├── backend/
│   ├── main.py            # FastAPI 入口
│   ├── config.py           # 配置（同步间隔等）
│   ├── database.py         # 数据库连接
│   ├── models.py           # 数据模型 (Account, Group)
│   ├── schemas.py          # 请求/响应模型
│   ├── scheduler.py        # 定时同步任务
│   ├── outlook_client.py   # Microsoft Graph API 客户端
│   ├── routes/
│   │   ├── accounts.py     # 账号管理 API
│   │   ├── emails.py       # 邮件 API
│   │   └── groups.py       # 分组管理 API
│   ├── requirements.txt
│   └── data/
│       └── outlook.db      # SQLite 数据库（自动生成）
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── views/
│   │   └── stores/
│   ├── package.json
│   └── dist/               # 构建输出（npm run build 后生成）
└── README.md
```

---

## 常见问题

### Q: 页面刷新后显示 404？
使用 Nginx 反向代理时已通过 `try_files $uri $uri/ /index.html` 解决。如果不用 Nginx、直接访问后端 8000 端口，则不支持 SPA 路由刷新。

### Q: 如何备份数据？
```bash
cp /opt/outlook-manager/backend/data/outlook.db /backup/outlook-$(date +%Y%m%d).db
```

### Q: 同步间隔如何调整？
修改 systemd 服务文件中的环境变量：
```ini
Environment="SYNC_INTERVAL=15"     # 改为 15 分钟
Environment="SYNC_BATCH_SIZE=20"   # 每批 20 个账号
```
然后重启：`sudo systemctl restart outlook-manager`

### Q: 如何查看同步日志？
```bash
sudo journalctl -u outlook-manager -f --no-pager
```
