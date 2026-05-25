app_name = "hvv_departures"
app_title = "HVV Departures"
app_publisher = "Lume"
app_description = "HVV Geofox GTI departures viewer"
app_email = "admin@example.com"
app_license = "mit"
app_icon_url = "/assets/hvv_departures/images/hvv_departures_logo.svg"
app_logo_url = "/assets/hvv_departures/images/hvv_departures_logo.svg"

add_to_apps_screen = [
    {
        "name": "hvv_departures",
        "logo": "/assets/hvv_departures/images/hvv_departures_logo.svg",
        "title": "HVV Departures",
        "route": "/app/hvv-departures",
    }
]

after_install = "hvv_departures.install.after_install"
after_migrate = [
    "hvv_departures.install._set_desktop_icon",
]
