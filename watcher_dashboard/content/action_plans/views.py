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

from django import shortcuts
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from django import views as django_views
import horizon.exceptions
import horizon.messages
from horizon import forms
import horizon.tables
import horizon.tabs
from horizon.utils import memoized
import horizon.workflows


from openstack_dashboard.api import nova

from watcher_dashboard.api import watcher
from watcher_dashboard.common import client as common_client
from watcher_dashboard.content.action_plans import tables
from watcher_dashboard.content.actions import tables as action_tables
from watcher_dashboard.content.audits import forms as wforms
from watcher_dashboard.utils import utils as watcher_utils

LOG = logging.getLogger(__name__)


class IndexView(horizon.tables.PagedTableMixin, horizon.tables.DataTableView):
    table_class = tables.ActionPlansTable
    template_name = "infra_optim/action_plans/index.html"
    page_title = _("Action Plans")

    def get_data(self):
        action_plans = []
        marker, sort_dir = self._get_marker()
        reversed_order = sort_dir == "asc"
        search_opts = self.get_filters()
        page_size = watcher_utils.DEFAULT_PAGE_SIZE
        try:
            action_plans = watcher.ActionPlan.list(
                self.request,
                limit=page_size + 1,
                marker=marker,
                sort_key="created_at",
                sort_dir=sort_dir,
                **search_opts
            )
            action_plans, self._has_more_data, self._has_prev_data = (
                watcher_utils.update_pagination(
                    action_plans, page_size, marker, reversed_order
                )
            )
            audits = watcher.Audit.list(self.request)
            audit_map = {a.uuid: a for a in audits}
            for ap in action_plans:
                audit = audit_map.get(ap.audit_uuid)
                if audit:
                    ap.audit_name = audit.name or ap.audit_uuid
                    ap.strategy_name = audit.strategy_name or "-"
                else:
                    ap.audit_name = ap.audit_uuid
                    ap.strategy_name = "-"
        except Exception as exc:
            LOG.exception(exc)
            horizon.exceptions.handle(
                self.request, _("Unable to retrieve action_plan information.")
            )
        return action_plans

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


class ArchiveView(forms.ModalFormView):
    form_class = wforms.CreateForm
    form_id = "create_audit_form"
    modal_header = _("Create Audit")
    template_name = "infra_optim/audits/create.html"
    page_title = _("Create Audit")
    submit_label = _("Create Audit")


class DetailView(horizon.tables.MultiTableView):
    table_classes = (
        action_tables.RelatedActionsTable,
        tables.RelatedEfficacyIndicatorsTable,
    )
    template_name = "infra_optim/action_plans/details.html"
    page_title = _("Action Plan Details: {{ action_plan.uuid }}")
    redirect_url = "horizon:admin:action_plans:index"

    @memoized.memoized_method
    def max_version(self):
        return common_client.get_max_version(self.request)

    @memoized.memoized_method
    def _get_data(self):
        action_plan_uuid = None
        try:
            action_plan_uuid = self.kwargs["action_plan_uuid"]
            server_version = self.max_version()
            version = (
                common_client.MV_SKIP_ACTION
                if common_client.is_microversion_supported(
                    server_version, common_client.MV_SKIP_ACTION
                )
                else None
            )
            action_plan = watcher.ActionPlan.get(
                self.request, action_plan_uuid, api_version=version
            )
        except Exception as exc:
            LOG.exception(exc)
            msg = (
                _('Unable to retrieve details for action_plan "%s".') % action_plan_uuid
            )
            horizon.exceptions.handle(self.request, msg, redirect=self.redirect_url)
        return action_plan

    @memoized.memoized_method
    def _get_actions(self):
        try:
            action_plan = self._get_data()
            return watcher.Action.list(self.request, action_plan=action_plan.uuid)
        except Exception as exc:
            LOG.exception(exc)
            msg = _("Action list can not be retrieved.")
            horizon.exceptions.handle(self.request, msg)
            return []

    def get_related_wactions_data(self):
        return self._get_actions()

    @memoized.memoized_method
    def _flavor_map(self):
        """Return a {flavor_id: flavor_name} map, fetched from Nova once.

        Rarely needed fallback for the case where a server's flavor
        wasn't resolved by id below (very old Nova microversions).
        Memoized so we hit Nova at most once per request, and only if
        a fallback lookup actually needs it.
        """
        try:
            flavors = nova.flavor_list(self.request, is_public=None)
        except Exception as exc:
            LOG.warning("Unable to list flavors: %s", exc)
            return {}
        return {f.id: f.name for f in flavors}

    def _fetch_server_flavor(self, server_id):
        """Resolve a single server's flavor name via a targeted Nova GET.

        Nova >= 2.47 snapshots the flavor's ``original_name`` onto the
        server at boot time, so this keeps working even after the
        flavor itself is later renamed or deleted. Falls back to a
        by-id lookup in ``_flavor_map`` for older microversions.
        """
        try:
            server = nova.server_get(self.request, server_id)
        except Exception as exc:
            LOG.warning("Unable to get server %s: %s", server_id, exc)
            return None
        flavor = getattr(server, "flavor", None) or {}
        return flavor.get("original_name") or self._flavor_map().get(flavor.get("id"))

    @memoized.memoized_method
    def _server_flavor_map(self):
        """Return a {server_id: flavor_name} map for this plan's actions.

        Only fetches the specific instances referenced by the actions in
        this action plan (one targeted Nova GET per distinct instance,
        each individually cached), instead of listing every server in
        the cloud. Memoized so repeated lookups within a request don't
        re-hit the cache backend once per action.
        """
        server_ids = {
            dict(getattr(action, "input_parameters", None) or {}).get("resource_id")
            for action in self._get_actions()
        }
        server_ids.discard(None)
        result = {}
        for server_id in server_ids:
            cache_key = "server_flavor:%s" % server_id
            flavor_name = cache.get(cache_key)
            if flavor_name is None:
                flavor_name = self._fetch_server_flavor(server_id)
                if flavor_name:
                    cache.set(cache_key, flavor_name, timeout=60 * 60)
            result[server_id] = flavor_name
        return result

    def _server_flavor(self, server_id):
        """Resolve the flavor name of a server from the plan-scoped map."""
        if not server_id:
            return None
        return self._server_flavor_map().get(server_id)

    def _get_actions_dag(self):
        """Build a JSON-serializable node list describing the action DAG.

        Each node carries the fields the workflow visualization needs:
        uuid, action_type, state, the list of parent action UUIDs (the
        dependency edges), the action's input parameters and, when the
        action targets an instance, the instance's flavor name. When the
        Watcher API does not report ``parents`` (older/sequential plans),
        edges are derived from the ``next_uuid`` chain instead.
        """
        actions = self._get_actions()
        server_version = self.max_version()
        supports_skip = common_client.is_microversion_supported(
            server_version, common_client.MV_SKIP_ACTION
        )
        parent_succeeded = self._get_data().state == "SUCCEEDED"
        nodes = []
        by_id = {}
        for action in actions:
            params = dict(getattr(action, "input_parameters", None) or {})
            node = {
                "uuid": getattr(action, "uuid", ""),
                "action_type": getattr(action, "action_type", "") or "",
                "state": getattr(action, "state", None) or "NO STATE",
                "parents": list(getattr(action, "parents", None) or []),
                "parameters": params,
                "flavor": self._server_flavor(params.get("resource_id")),
            }
            skippable = (
                supports_skip
                and not parent_succeeded
                and node["state"] in ("PENDING", "SKIPPED")
            )
            node["skippable"] = skippable
            node["skip_url"] = (
                reverse("horizon:admin:actions:skip", args=[node["uuid"]])
                if skippable
                else None
            )
            nodes.append(node)
            by_id[node["uuid"]] = node

        if not any(node["parents"] for node in nodes):
            for action in actions:
                next_uuid = getattr(action, "next_uuid", None)
                target = by_id.get(next_uuid)
                if target is not None:
                    target["parents"].append(getattr(action, "uuid", ""))
        return nodes

    @memoized.memoized_method
    def get_related_efficacy_indicators_data(self):
        efficacy_indicators = []
        try:
            action_plan = self._get_data()
            efficacy_indicators = [
                watcher.EfficacyIndicator(indicator)
                for indicator in getattr(action_plan, "efficacy_indicators", None) or []
            ]
        except Exception as exc:
            LOG.exception(exc)
            msg = _("Failed to get the efficacy indicators: %s") % str(exc)
            LOG.info(msg)
            horizon.messages.warning(self.request, msg)
            efficacy_indicators = []
        return efficacy_indicators

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        action_plan = self._get_data()
        context["action_plan"] = action_plan
        try:
            audit = watcher.Audit.get(self.request, action_plan.audit_uuid)
        except Exception:
            audit = None
        context["audit"] = audit
        context["actions_dag"] = self._get_actions_dag()
        context["global_efficacy"] = tables.build_global_efficacy_dict(action_plan)
        context["efficacy_indicators"] = self.get_related_efficacy_indicators_data()
        return context

    def get_tables(self):
        """Configure the actions table with skip-support flags.

        Horizon calls get_tables() multiple times per request: first
        from construct_tables() which loads data into each table, then
        again from get_context_data() to build the template context.
        We must update the existing table instance rather than replace
        it, otherwise the data loaded by construct_tables() is lost.
        """
        table_dict = super().get_tables()
        action_plan = self._get_data()
        mv = self.max_version()
        table = table_dict["related_wactions"]
        table._supports_skip = common_client.is_microversion_supported(
            mv, common_client.MV_SKIP_ACTION
        )
        table._parent_succeeded = action_plan.state == "SUCCEEDED"
        return table_dict

    def get_tabs(self, request, *args, **kwargs):
        action_plan = self._get_data()
        return self.tab_group_class(request, action_plan=action_plan, **kwargs)


class StartView(django_views.View):
    redirect_url = "horizon:admin:action_plans:detail"

    def post(self, request, action_plan_uuid):
        try:
            watcher.ActionPlan.start(request, action_plan_uuid)
            horizon.messages.success(
                request, _("Action plan %s started.") % action_plan_uuid
            )
        except Exception:
            horizon.exceptions.handle(request, _("Unable to start action plan."))
        return shortcuts.redirect(reverse(self.redirect_url, args=[action_plan_uuid]))
