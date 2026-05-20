import frappe
from frappe.model.document import Document


class Sensor(Document):
	def validate(self):
		if self.chart_color and not (self.chart_color.startswith("#") and len(self.chart_color) == 7):
			frappe.throw("Chart Color must be a 7-character #rrggbb value")
		if self.port and (self.port < 1 or self.port > 65535):
			frappe.throw("Port must be between 1 and 65535")
