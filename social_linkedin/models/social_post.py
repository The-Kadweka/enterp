# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, api, fields


class SocialPostLinkedin(models.Model):
    _inherit = 'social.post'

    display_linkedin_preview = fields.Boolean('Display LinkedIn Preview', compute='_compute_display_linkedin_preview')
    linkedin_preview = fields.Html('LinkedIn Preview', compute='_compute_linkedin_preview')

    @api.depends('message', 'account_ids.media_id.media_type')
    def _compute_display_linkedin_preview(self):
        for post in self:
            post.display_linkedin_preview = (
                post.message and
                'linkedin' in post.account_ids.media_id.mapped('media_type'))

    @api.depends('message', 'scheduled_date', 'image_ids')
    def _compute_linkedin_preview(self):
        for post in self:
            post.linkedin_preview = self.env.ref('social_linkedin.linkedin_preview').render({
                'message': post.message,
                'published_date': post.scheduled_date if post.scheduled_date else fields.Datetime.now(),
                'images': post.image_ids.with_context(bin_size=False).mapped('datas'),
            })
