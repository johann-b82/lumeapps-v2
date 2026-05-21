COMPOSE      := docker compose -p erpnext
SITE         := frontend
BACKEND      := erpnext-backend-1

.PHONY: help build up down restart ps logs shell bench install-app migrate clear-cache fresh nuke

help:
	@echo "Targets:"
	@echo "  build         - build custom image (lumeapps/erpnext:local)"
	@echo "  up            - build + start stack (detached)"
	@echo "  down          - stop stack"
	@echo "  restart       - restart frappe services"
	@echo "  ps            - container status"
	@echo "  logs s=NAME   - tail logs for service NAME (default backend)"
	@echo "  shell         - bash into backend"
	@echo "  bench c='...' - run bench command on $(SITE) (e.g. c='list-apps')"
	@echo "  install-app   - install sensor_monitor on existing $(SITE)"
	@echo "  migrate       - bench migrate"
	@echo "  clear-cache   - clear app+website cache"
	@echo "  fresh         - down + wipe sites/logs/redis bind dirs + up (KEEPS DB volume)"
	@echo "  nuke          - down + REMOVE DB VOLUME + wipe binds (DESTROYS DATA)"

build:
	$(COMPOSE) build

up: build
	$(COMPOSE) up -d

down:
	$(COMPOSE) stop

restart:
	$(COMPOSE) restart backend frontend queue-long queue-short scheduler websocket

ps:
	$(COMPOSE) ps

s ?= backend
logs:
	$(COMPOSE) logs -f --tail=200 $(s)

shell:
	docker exec -it $(BACKEND) bash

bench:
	docker exec $(BACKEND) bench --site $(SITE) $(c)

install-app:
	docker exec $(BACKEND) bench --site $(SITE) install-app sensor_monitor || \
	  docker exec $(BACKEND) bench --site $(SITE) execute frappe.installer.add_to_installed_apps --kwargs "{'app_name': 'sensor_monitor'}"
	docker exec $(BACKEND) bench --site $(SITE) install-app whatsapp_broadcast || \
	  docker exec $(BACKEND) bench --site $(SITE) execute frappe.installer.add_to_installed_apps --kwargs "{'app_name': 'whatsapp_broadcast'}"

migrate:
	docker exec $(BACKEND) bench --site $(SITE) migrate

clear-cache:
	docker exec $(BACKEND) bench --site $(SITE) clear-cache
	docker exec $(BACKEND) bench --site $(SITE) clear-website-cache

fresh:
	$(COMPOSE) down
	rm -rf data/sites data/logs data/redis-queue
	mkdir -p data/sites data/logs data/redis-queue
	$(COMPOSE) up -d

nuke:
	$(COMPOSE) down -v
	rm -rf data/sites data/logs data/redis-queue
	mkdir -p data/sites data/logs data/redis-queue
	$(COMPOSE) up -d
