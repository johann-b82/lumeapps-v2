app_name = "whatsapp_broadcast"
app_title = "WhatsApp Broadcast"
app_publisher = "Lume"
app_description = "WhatsApp Cloud API broadcast app"
app_email = "admin@example.com"
app_license = "mit"
app_icon_url = "/assets/whatsapp_broadcast/images/whatsapp_broadcast_logo.svg"
app_logo_url = "/assets/whatsapp_broadcast/images/whatsapp_broadcast_logo.svg"

add_to_apps_screen = [
    {
        "name": "whatsapp_broadcast",
        "logo": "/assets/whatsapp_broadcast/images/whatsapp_broadcast_logo.svg",
        "title": "WhatsApp Broadcast",
        "route": "/app/whatsapp-broadcast",
    }
]

fixtures = [
    {"dt": "Role", "filters": [["role_name", "in", ["WhatsApp Manager", "WhatsApp User"]]]},
]

doctype_js = {
    "WhatsApp Post": "public/js/whatsapp_post.js",
}

after_install = "whatsapp_broadcast.install.after_install"
after_migrate = [
    "whatsapp_broadcast.install._set_desktop_icon",
    "whatsapp_broadcast.install._hide_home_workspace",
]
