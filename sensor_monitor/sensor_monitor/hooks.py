app_name = "sensor_monitor"
app_title = "Sensor Monitor"
app_publisher = "Lume"
app_description = "SNMP temperature/humidity logger"
app_email = "admin@example.com"
app_license = "mit"
app_icon_url = "/assets/sensor_monitor/images/sensor_monitor_logo.svg"
app_logo_url = "/assets/sensor_monitor/images/sensor_monitor_logo.svg"

app_include_js = [
	"/assets/sensor_monitor/js/sensor_dashboard.js",
	"/assets/sensor_monitor/js/sensor_monitor_redirect.js",
]

add_to_apps_screen = [
	{
		"name": "sensor_monitor",
		"logo": "/assets/sensor_monitor/images/sensor_monitor_logo.svg",
		"title": "Sensor Monitor",
		"route": "/app/sensor-monitor",
	}
]


fixtures = [
	{"dt": "Role", "filters": [["role_name", "in", ["Sensor Manager", "Sensor Viewer"]]]},
]


scheduler_events = {
	"cron": {
		"* * * * *": [
			"sensor_monitor.sensor_monitor.poller.poll_all",
		],
	},
	"daily": [
		"sensor_monitor.sensor_monitor.poller.purge_old_readings",
	],
}


after_install = "sensor_monitor.install.after_install"
