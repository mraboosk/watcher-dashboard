# Copyright (c) 2016 b<>com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
import horizon.exceptions
from horizon import forms
import horizon.tables
import horizon.tabs
from horizon.utils import functions as utils
from horizon.utils import memoized
import horizon.workflows

from watcher_dashboard.api import watcher
from watcher_dashboard.content.action_plans import tables as action_plan_tables
from watcher_dashboard.content.audits import forms as wforms
from watcher_dashboard.content.audits import tables
from watcher_dashboard.content.audits import tabs as wtabs
from watcher_dashboard.utils import utils as watcher_utils

LOG = logging.getLogger(__name__)


class IndexView(horizon.tables.DataTableView):
    table_class = tables.AuditsTable
    template_name = 'infra_optim/audits/index.html'
    page_title = _("Audits")

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        create_action = {
            'name': _("New Audit"),
            'url': reverse('horizon:admin:audits:create'),
            'icon': 'fa-plus',
            'ajax_modal': True,
        }
        context['header_actions'] = [create_action]
        context['audits_count'] = self.get_audits_count()
        return context

    def get_data(self):
        audits = []
        search_opts = self.get_filters()
        try:
            audits = watcher.Audit.list(self.request, **search_opts)
        except Exception:
            horizon.exceptions.handle(
                self.request,
                _("Unable to retrieve audit information."))
        return audits

    def get_audits_count(self):
        return len(self.get_data())

    def get_filters(self):
        filters = {}
        filter_action = self.table._meta._filter_action
        if filter_action:
            filter_field = self.table.get_filter_field()
            if filter_action.is_api_filter(filter_field):
                filter_string = self.table.get_filter_string()
                if filter_field and filter_string:
                    filters[filter_field] = filter_string
        return filters


class CreateView(forms.ModalFormView):
    form_class = wforms.CreateForm
    form_id = "create_audit_form"
    modal_header = _("Create Audit")
    template_name = 'infra_optim/audits/create.html'
    success_url = reverse_lazy("horizon:admin:audits:index")
    page_title = _("Create Audit")
    submit_label = _("Create Audit")
    submit_url = reverse_lazy("horizon:admin:audits:create")


class DetailView(horizon.tables.MultiTableView):
    table_classes = (action_plan_tables.RelatedActionPlansTable,)
    tab_group_class = wtabs.AuditDetailTabs
    template_name = 'infra_optim/audits/details.html'
    redirect_url = 'horizon:admin:audits:index'
    page_title = _("Audit Details: {{ audit.name }}")

    # Query parameters used to paginate the action plans accordion. They are
    # distinct from the DataTable defaults ('marker'/'prev_marker') so they
    # never clash with the related action plans table on the same view.
    ap_pagination_param = 'ap_marker'
    ap_prev_pagination_param = 'ap_prev_marker'

    _ap_has_more = False
    _ap_has_prev = False

    @memoized.memoized_method
    def _get_data(self):
        audit_uuid = None
        try:
            audit_uuid = self.kwargs['audit_uuid']
            audit = watcher.Audit.get(self.request, audit_uuid)
        except Exception:
            msg = _('Unable to retrieve details for audit "%s".') \
                % audit_uuid
            horizon.exceptions.handle(
                self.request, msg,
                redirect=self.redirect_url)
        return audit

    @memoized.memoized_method
    def _get_action_plans(self):
        prev_marker = self.request.GET.get(self.ap_prev_pagination_param)
        if prev_marker is not None:
            marker, sort_dir, reversed_order = prev_marker, 'asc', True
        else:
            marker = self.request.GET.get(self.ap_pagination_param)
            sort_dir, reversed_order = 'desc', False
        page_size = utils.get_page_size(self.request)
        try:
            audit = self._get_data()
            action_plans = watcher.ActionPlan.list(
                self.request, audit=audit.uuid, limit=page_size + 1,
                marker=marker, sort_key='created_at', sort_dir=sort_dir)
        except Exception as exc:
            LOG.exception(exc)
            msg = _('Action plan list cannot be retrieved.')
            horizon.exceptions.handle(self.request, msg)
            self._ap_has_more = self._ap_has_prev = False
            return []
        action_plans, self._ap_has_more, self._ap_has_prev = \
            watcher_utils.update_pagination(
                action_plans, page_size, marker, reversed_order)
        return action_plans

    def get_related_action_plans_data(self):
        return self._get_action_plans()

    def get_context_data(self, **kwargs):
        context = super(DetailView, self).get_context_data(**kwargs)
        audit = self._get_data()
        context["audit"] = audit

        action_plans = self._get_action_plans()
        action_plans_with_actions = []
        for ap in action_plans:
            try:
                actions = watcher.Action.list(
                    self.request, action_plan=ap.uuid)
            except Exception:
                actions = []
            action_plans_with_actions.append({
                'action_plan': ap,
                'actions': actions,
            })
        context['action_plans_with_actions'] = action_plans_with_actions
        context['ap_has_more'] = self._ap_has_more
        context['ap_has_prev'] = self._ap_has_prev
        context['ap_marker'] = action_plans[-1].uuid if action_plans else ''
        context['ap_prev_marker'] = \
            action_plans[0].uuid if action_plans else ''
        return context

    def get_tabs(self, request, *args, **kwargs):
        audit = self._get_data()
        # ports = self._get_ports()
        return self.tab_group_class(request, audit=audit, **kwargs)
