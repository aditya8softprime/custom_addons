from odoo import models, fields, api, _

class WebsiteMenu(models.Model):
    _inherit = 'website.menu'

    @api.model
    def create_service_menus(self):
        """Create website menu items for services"""
        # Find the services parent menu
        services_parent = self.env.ref('clinic_management.menu_clinic_services_parent', raise_if_not_found=False)
        if not services_parent:
            return
        
        # Remove existing service menus
        existing_service_menus = self.search([
            ('parent_id', '=', services_parent.id),
            ('name', '!=', 'All Services')
        ])
        existing_service_menus.unlink()
        
        # Create "All Services" menu if it doesn't exist
        all_services_menu = self.search([
            ('parent_id', '=', services_parent.id),
            ('name', '=', 'All Services')
        ], limit=1)
        if not all_services_menu:
            self.create({
                'name': 'All Services',
                'url': '/clinic/services',
                'parent_id': services_parent.id,
                'sequence': 1,
            })
        
        # Get active services
        services = self.env['clinic.service'].search([('active', '=', True)], order='name')
        
        # Create menu item for each service
        sequence = 10
        for service in services:
            self.create({
                'name': service.name,
                'url': f'/clinic/service/{service.id}',
                'parent_id': services_parent.id,
                'sequence': sequence,
            })
            sequence += 1


class ClinicService(models.Model):
    _inherit = 'clinic.service'

    @api.model_create_multi
    def create(self, vals_list):
        """Update website menus when new service is created"""
        services = super().create(vals_list)
        # Update website menus
        self.env['website.menu'].create_service_menus()
        return services

    def write(self, vals):
        """Update website menus when service is updated"""
        result = super().write(vals)
        if 'name' in vals or 'active' in vals:
            self.env['website.menu'].create_service_menus()
        return result

    def unlink(self):
        """Update website menus when service is deleted"""
        result = super().unlink()
        self.env['website.menu'].create_service_menus()
        return result
