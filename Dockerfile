ARG ERPNEXT_VERSION=v16.19.1
FROM frappe/erpnext:${ERPNEXT_VERSION}

USER frappe
WORKDIR /home/frappe/frappe-bench

COPY --chown=frappe:frappe sensor_monitor /home/frappe/frappe-bench/apps/sensor_monitor

RUN /home/frappe/frappe-bench/env/bin/pip install --no-cache-dir \
        "pysnmp>=7.0.0" \
        -e /home/frappe/frappe-bench/apps/sensor_monitor \
    && printf '\nsensor_monitor\n' >> /home/frappe/frappe-bench/sites/apps.txt \
    && sort -u /home/frappe/frappe-bench/sites/apps.txt -o /home/frappe/frappe-bench/sites/apps.txt \
    && sed -i '/^$/d' /home/frappe/frappe-bench/sites/apps.txt \
    && ln -sf /home/frappe/frappe-bench/apps/sensor_monitor/sensor_monitor/public \
              /home/frappe/frappe-bench/assets/sensor_monitor \
    && cd /home/frappe/frappe-bench \
    && bench build --app sensor_monitor
