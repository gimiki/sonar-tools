#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

import sonarqube.utilities as util


class Changelog():

    def __init__(self, jsonlog):
        self._json = jsonlog
        self._change_type = None

    def __str__(self):
        return str(self._json)

    def __is_resolve_as(self, resolve_reason):
        cond1 = False
        cond2 = False
        for diff in self._json['diffs']:
            if diff['key'] == 'resolution' and 'newValue' in diff and diff['newValue'] == 'FIXED':
                cond1 = True
            if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == resolve_reason:
                cond2 = True
        return cond1 and cond2

    def is_resolve_as_fixed(self):
        return self.__is_resolve_as('FIXED')

    def is_resolve_as_fp(self):
        return self.__is_resolve_as('FALSE-POSITIVE')

    def is_resolve_as_wf(self):
        return self.__is_resolve_as('WONTFIX')

    def is_closed(self):
        return self.__is_resolve_as('CLOSED')

    def __is_status(self, status):
        d = self._json['diffs'][0]
        return d.get('key', '') == "status" and d.get('newValue', '') == status

    def is_reopen(self):
        d = self._json['diffs'][0]
        return self.__is_status("REOPENED") and d.get('oldVal', '') != "CONFIRMED"

    def is_confirm(self):
        return self.__is_status("CONFIRMED")

    def is_unconfirm(self):
        d = self._json['diffs'][0]
        return self.__is_status("REOPENED") and d.get('oldVal', '') == "CONFIRMED"

    def is_change_severity(self):
        d = self._json['diffs'][0]
        return d.get('key', '') == "severity"

    def new_severity(self):
        if self.is_change_severity():
            d = self._json['diffs'][0]
            return d.get('newValue', None)
        return None

    def is_change_type(self):
        d = self._json['diffs'][0]
        return d.get('key', '') == "type"

    def new_type(self):
        if self.is_change_type():
            d = self._json['diffs'][0]
            return d.get('newValue', None)
        return None

    def is_technical_change(self):
        d = self._json['diffs'][0]
        key = d.get('key', '')
        return key in ('from_short_branch', 'from_branch', 'effort')

    def is_assignment(self):
        d = self._json['diffs'][0]
        return d.get('key', '') == "assignee"

    def new_assignee(self):
        d = self._json['diffs'][0]
        return d.get('newValue', None)

    def old_assignee(self):
        d = self._json['diffs'][0]
        return d.get('oldValue', None)

    def date(self):
        return self._json['creationDate']

    def author(self):
        return self._json.get('user', None)

    def is_tag(self):
        d = self._json['diffs'][0]
        return d.get('key', '') == "tag"

    def tags(self):
        if not self.is_tag():
            return None
        d = self._json['diffs'][0]
        return d.get('newValue', '').replace(' ', ',')

    def changelog_type(self):
        ctype = (None, None)
        if self.is_assignment():
            ctype = ('ASSIGN', self.new_assignee())
        elif self.is_reopen():
            ctype = ('REOPEN', None)
        elif self.is_confirm():
            ctype = ('CONFIRM', None)
        elif self.is_unconfirm():
            ctype = ('UNCONFIRM', None)
        elif self.is_change_severity():
            ctype = ('SEVERITY', self.new_severity())
        elif self.is_change_type():
            ctype = ('TYPE', self.new_type())
        elif self.is_resolve_as_fixed():
            ctype = ('FIXED', None)
        elif self.is_resolve_as_fp():
            ctype = ('FALSE-POSITIVE', None)
        elif self.is_resolve_as_wf():
            ctype = ('WONT-FIX', None)
        elif self.is_tag():
            ctype = ('TAG', self.tags())
        elif self.is_closed():
            ctype = ('INTERNAL', None)
        elif self.is_technical_change():
            ctype = ('INTERNAL', None)
        else:
            util.logger.warning("Could not determine changelog type for %s", str(self))
        return ctype
