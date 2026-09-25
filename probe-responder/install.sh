#!/usr/bin/env bash
# AxisNow 拨测应答器 —— 一键部署脚本
#
# 用法（在被探测的那台服务器上以 root 执行）：
#   bash install.sh              # 默认端口 4895
#   PORT=9000 bash install.sh    # 自定义端口
#
# 幂等：重复执行会更新配置并重建容器，不会重复占用端口。
# 卸载：cd /opt/axisnow-probe && docker compose down && cd - && rm -rf /opt/axisnow-probe

set -euo pipefail

PORT="${PORT:-4895}"
DIR="${DIR:-/opt/axisnow-probe}"

if ! command -v docker >/dev/null 2>&1; then
    echo "❌ 没找到 docker，请先安装" >&2
    exit 1
fi
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    echo "❌ 没找到 docker compose / docker-compose" >&2
    exit 1
fi

echo "==> 目录: $DIR    端口: $PORT"
mkdir -p "$DIR"
cd "$DIR"

cat > nginx.conf <<'NGINX_EOF'
# AxisNow 拨测应答器：任何 Host 命中 /aegis_node_ping/ 都返回 200，其余 404
server {
    listen 80 default_server;
    server_name _;
    access_log off;
    server_tokens off;

    location = /aegis_node_ping/ {
        add_header Content-Type "text/plain" always;
        add_header Cache-Control "no-store" always;
        return 200 "ok\n";
    }
    location = /aegis_node_ping {
        return 301 /aegis_node_ping/;
    }
    location / {
        return 404;
    }
}
NGINX_EOF

cat > docker-compose.yml <<COMPOSE_EOF
name: axisnow-probe-responder

services:
  probe-responder:
    image: nginx:1.27-alpine
    container_name: axisnow-probe-responder
    restart: unless-stopped
    ports:
      - "${PORT}:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    read_only: true
    tmpfs:
      - /var/cache/nginx
      - /var/run
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD-SHELL", "wget -q -O- http://127.0.0.1/aegis_node_ping/ || exit 1"]
      interval: 60s
      timeout: 5s
      retries: 3
      start_period: 5s
COMPOSE_EOF

echo "==> 启动容器"
$DC up -d

echo "==> 等待就绪"
for i in $(seq 1 15); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:${PORT}/aegis_node_ping/" || true)
    [ "$code" = "200" ] && break
    sleep 1
done

echo
echo "==> 本机自检"
printf "   HEAD /aegis_node_ping/  -> %s (期望 200)\n" \
    "$(curl -s -o /dev/null -w '%{http_code}' -I --max-time 3 "http://127.0.0.1:${PORT}/aegis_node_ping/")"
printf "   用公网 IP 当 Host 访问  -> %s (期望 200，证明 follow_target 能命中)\n" \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 -H "Host: 127.0.0.1" "http://127.0.0.1:${PORT}/aegis_node_ping/")"
printf "   随便一个路径            -> %s (期望 404)\n" \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:${PORT}/")"

PUBIP=$(curl -s --max-time 6 https://api.ipify.org || echo "")
if [ -n "$PUBIP" ]; then
    echo
    echo "==> 公网可用性"
    printf "   出口公网 IP: %s\n" "$PUBIP"
    if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "http://${PUBIP}:${PORT}/aegis_node_ping/" || true)" = "200" ]; then
        echo "   ✅ 公网可访问，AxisNow 探针能探到"
    else
        echo "   ⚠️ 从本机访问出口 IP 未通（可能是 NAT 回环问题，不代表外网不通）"
        echo "      请确认安全组 / 防火墙已放行 TCP ${PORT}"
    fi
fi

echo
echo "✅ 完成。接下来到 AxisNow DNS Scheduler 的「拨测」页："
echo "   1) 一键创建统一模板（scheme=http, port=${PORT}, path=/aegis_node_ping/, host=follow_target）"
echo "   2) 把它应用到所有规则"
echo "   3) 清理掉重复的旧拨测任务"
echo
echo "   记得在防火墙/安全组放行 TCP ${PORT}"
