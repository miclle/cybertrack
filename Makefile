PYTHON ?= python3
PORT ?= 24173

.PHONY: help deps build serve

help:
	@printf '%s\n' \
	  'make deps   按锁文件安装网页依赖' \
	  'make build  构建静态文档站和网页模型到 build/web/' \
	  'make serve  构建并启动本地文档站，可用 PORT 指定端口'

deps: web/node_modules/.cybertrack-installed

web/node_modules/.cybertrack-installed: web/package.json web/package-lock.json
	npm --prefix web ci
	@touch "$@"

build: deps
	npm --prefix web run build

serve: build
	"$(PYTHON)" -m http.server --bind 127.0.0.1 --directory build/web "$(PORT)"
