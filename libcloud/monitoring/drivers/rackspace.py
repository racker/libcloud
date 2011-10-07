# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import httplib
import urlparse
import os.path
import urllib

try:
    import simplejson as json
except:
    import json

from libcloud import utils
from libcloud.common.types import MalformedResponseError, LibcloudError
from libcloud.common.types import LazyList
from libcloud.common.base import Response

from libcloud.monitoring.providers import Provider

from libcloud.monitoring.base import MonitoringDriver, Entity, NotificationPlan, \
                                     CheckType, Check, Notification, NotificationType
#, Check, Alarm

from libcloud.common.rackspace import AUTH_URL_US
from libcloud.common.openstack import OpenStackBaseConnection

API_VERSION = '1.1'

class RackspaceMonitoringResponse(Response):

    valid_response_codes = [ httplib.NOT_FOUND, httplib.CONFLICT ]

    def success(self):
        i = int(self.status)
        return i >= 200 and i <= 299 or i in self.valid_response_codes

    def parse_body(self):
        if not self.body:
            return None

        if 'content-type' in self.headers:
            key = 'content-type'
        elif 'Content-Type' in self.headers:
            key = 'Content-Type'
        else:
            raise LibcloudError('Missing content-type header')

        content_type = self.headers[key]
        if content_type.find(';') != -1:
            content_type = content_type.split(';')[0]

        if content_type == 'application/json':
            try:
                data = json.loads(self.body)
            except:
                raise MalformedResponseError('Failed to parse JSON',
                                             body=self.body,
                                             driver=RackspaceMonitoringDriver)
        elif content_type == 'text/plain':
            data = self.body
        else:
            data = self.body

        return data


class RackspaceMonitoringConnection(OpenStackBaseConnection):
    """
    Base connection class for the Rackspace Monitoring driver.
    """

    type = Provider.RACKSPACE
    responseCls = RackspaceMonitoringResponse
    auth_url = AUTH_URL_US
    _url_key = "monitoring_url"

    def __init__(self, user_id, key, secure=False, ex_force_base_url=None):
        self.api_version = API_VERSION
        self.monitoring_url = ex_force_base_url
        self.accept_format = 'application/json'
        super(RackspaceMonitoringConnection, self).__init__(user_id, key, secure=secure, ex_force_base_url=None)

    def request(self, action, params=None, data='', headers=None, method='GET',
                raw=False):
        if not headers:
            headers = {}
        if not params:
            params = {}

        headers['Accept'] = 'application/json'

        if method in [ 'POST', 'PUT']:
            headers['Content-Type']  = 'application/json; charset=UTF-8'
            data = json.dumps(data)

        return super(RackspaceMonitoringConnection, self).request(
            action=action,
            params=params, data=data,
            method=method, headers=headers,
            raw=raw
        )


class RackspaceMonitoringDriver(MonitoringDriver):
    """
    Base Rackspace Monitoring driver.

    """
    name = 'Rackspace Monitoring'
    connectionCls = RackspaceMonitoringConnection

    def __init__(self, *args, **kwargs):
        self._ex_force_base_url = kwargs.pop('ex_force_base_url', None)
        super(RackspaceMonitoringDriver, self).__init__(*args, **kwargs)

    def _ex_connection_class_kwargs(self):
        if self._ex_force_base_url:
            return {'ex_force_base_url': self._ex_force_base_url}
        return {}

    def create_entity(self, **kwargs):

        data = {'who': kwargs.get('who'),
                'why': kwargs.get('why'),
                'ip_addresses': kwargs.get('ip_addresses', {}),
                'label': kwargs.get('name'),
                'metadata': kwargs.get('extra', {})}

        resp = self.connection.request("/entities",
                                       method='POST',
                                       data=data)
        if resp.status ==  httplib.CREATED:
            # location
            # /1.0/entities/enycekKZoN
            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')

            #return self._read_response(location, self._to_entity)
        else:
            raise LibcloudError('Unexpected status code: %s' % (resp.status))

    def _grab_action_from_url(self, url):
        rp = self.connection.request_path
        p = urlparse.urlparse(url)
        if p.path.startswith(rp):
            # /entites/enXXXXX/check/chAAAAAA
            return p.path[len(rp):]
        else:
            raise LibcloudError('Unexpected URL: ' + url)

    def _read_entity(self, enId):
        resp = self.connection.request("/entities/%s" % (enId),
                                       method='GET')
        return self._to_entity(resp.object)

    def _read_notification_plan(self, npId):
        resp = self.connection.request("/notification_plan/%s" % (npId),
                                       method='GET')
        return self._to_notification_plan(resp.object)

    def list_entities(self, ex_next_marker=None):
        value_dict = { 'url': '/entities',
                       'start_marker': ex_next_marker,
                       'object_mapper': self._to_entity_list}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def _get_more(self, last_key, value_dict):
        key = None

        params = {}

        if not last_key:
            key = value_dict.get('start_marker')
        else:
            key = last_key

        if key:
            params['marker'] = key

        response = self.connection.request(value_dict['url'], params)

        # newdata, self._last_key, self._exhausted
        if response.status == httplib.NO_CONTENT:
            return [], None, False
        elif response.status == httplib.OK:
            resp = json.loads(response.body)
            l = value_dict['object_mapper'](resp)
            m = resp['metadata'].get('next_marker')
            return l, m, m == None

        raise LibcloudError('Unexpected status code: %s' % (response.status))

    def delete_entity(self, entity):
        resp = self.connection.request("/entities/%s" % (entity.id),
                                       method='DELETE')
        return resp.status == httplib.NO_CONTENT

    def _to_entity(self, entity):
        ips = []
        ipaddrs = entity.get('ip_addresses', {})
        for key in ipaddrs.keys():
            ips.append((key, ipaddrs[key]))
        return Entity(id=entity['key'], name=entity['label'], extra=entity['metadata'], driver=self, ip_addresses = ips)

    def _to_notification_plan(self, notification_plan):
        error_state = notification_plan.get('error_state', [])
        warning_state = notification_plan.get('warning_state', [])
        ok_state = notification_plan.get('ok_state', [])
        return NotificationPlan(id=notification_plan['key'], name=notification_plan['name'],
            error_state=error_state, warning_state=warning_state, ok_state=ok_state, 
            driver=self)

    def _to_notification(self, notification):
        return Notification(self, **notification)

    def _to_entity_list(self, response):
        # @TODO: Handle more then 10k containers - use "lazy list"?
        entities = []

        for entity in response['values']:
            entities.append(self._to_entity(entity))
        return entities

    def _to_check_list(self, response):
        checks = []

        for check in response['values']:
            checks.append(self._to_check(check))
        return checks

    def _to_notification_plan_list(self, response):
        notification_plans = []

        for notification_plan in response['values']:
            notification_plans.append(self._to_notification_plan(notification_plan))
        return notification_plans

    def _to_notification_list(self, response):
        notifications = []

        for notification in response['values']:
            notifications.append(self._to_notification(notification))
        return notifications

    def list_check_types(self):
        value_dict = { 'url': '/check_types',
                       'object_mapper': self._to_check_types_list}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def _to_check_type(self, obj):
        return CheckType(id=obj['key'],
                         fields=obj.get('fields', []),
                         is_remote=obj.get('type') == 'remote')

    def _to_check(self, obj):
        return Check(self, **obj)

    def _to_check_types_list(self, resp):
        check_types = []

        for check_type in resp['values']:
            check_types.append(self._to_check_type(check_type))

        return check_types

    def list_notification_types(self):
        value_dict = { 'url': '/notification_types',
                       'object_mapper': self._to_notification_types_list}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def _to_notification_type(self, obj):
        return NotificationType(self, **obj)


    def _to_notification_types_list(self, resp):
        notification_types = []

        for notification_type in resp['values']:
            notification_types.append(self._to_notification_type(notification_type))

        return notification_types

    def list_monitoring_zones(self):
        resp = self.connection.request("/monitoring_zones",
                                       method='GET')
        return resp.status == httplib.NO_CONTENT

    def list_notifications(self):
        value_dict = { 'url': '/notifications',
                       'object_mapper': self._to_notification_list}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def delete_notification(self, notification):
        resp = self.connection.request("/notifications/%s" % (notification.id),
                                       method='DELETE')
        return resp.status == httplib.NO_CONTENT

    def create_notification(self, **kwargs):
        data = {'type': kwargs.get('type'),
                'details': kwargs.get('details')}

        for k in data.keys():
            if data[k] == None:
                del data[k]

        resp = self.connection.request("/notifications",
                                       method='POST',
                                       data=data)
        if resp.status ==  httplib.CREATED:
            # location
            # /1.0/notification_plans/npycekKZoN
            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')

            return self._read_response(location, self._to_notification)
        else:
            raise LibcloudError('Unexpected status code: %s' % (resp.status))

    def delete_notification_plan(self, notification_plan):
        resp = self.connection.request("/notification_plans/%s" % (notification_plan.id), method='DELETE')
        return resp.status == httplib.NO_CONTENT


    def list_notification_plans(self, ex_next_marker=None):
        value_dict = { 'url': '/notification_plans',
                       'start_marker': ex_next_marker,
                       'object_mapper': self._to_notification_plan_list}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def create_notification_plan(self, **kwargs):
        data = {'name': kwargs.get('name'),
                'error_state': kwargs.get('error_state', []),
                'warning_state': kwargs.get('warning_state', []),
                'ok_state': kwargs.get('ok_state', []),
                }

        for k in data.keys():
            if data[k] == None:
                del data[k]

        resp = self.connection.request("/notification_plans",
                                       method='POST',
                                       data=data)
        if resp.status ==  httplib.CREATED:
            # location
            # /1.0/notification_plans/npycekKZoN
            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')

            return self._read_response(location, self._to_notification_plan)
        else:
            raise LibcloudError('Unexpected status code: %s' % (resp.status))

    def list_checks(self, entity, ex_next_marker=None):
        value_dict = { 'url': '/entities/%s/checks' % (entity.id,),
                       'start_marker': ex_next_marker,
                       'object_mapper': self._to_check_list}

        return LazyList(get_more=self._get_more, value_dict=value_dict)
        resp = self.connection.request("/entities/%s/checks" % (entity.id),
                                       method='GET')
        return resp.status == httplib.NO_CONTENT

    def _read_response(self, url, to_func):
        if not to_func:
            raise LibcloudError('Expected a conversion function')

        resp = self.connection.request(self._grab_action_from_url(url),
                                       method='GET')
        obj = to_func(resp.object)
        return obj

    def update_check(self, entity, check, **kwargs):
        data = check.update_payload()
        resp = self.connection.request("/entities/%s/checks/%s" % (entity.id, check.id),
                                       method='PUT',
                                       data=data)
        if resp.status ==  httplib.NO_CONTENT:
            # location

            import pdb; pdb.set_trace()
            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')

            return self._read_response(location, self._to_check)
        else:
            raise LibcloudError('Unexpected status code: %s' % (resp.status))

    def create_check(self, entity, **kwargs):
        check = Check(self, **kwargs)
        data = check.payload()

        resp = self.connection.request("/entities/%s/checks" % (entity.id),
                                       method='POST',
                                       data=data)
        if resp.status ==  httplib.CREATED:
            # location

            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')

            return self._read_response(location, self._to_check)
        else:
            raise LibcloudError('Unexpected status code: %s' % (resp.status))

    def delete_check(self, entity, check):
        resp = self.connection.request("/entities/%s/checks/%s" % (entity.id, check.id),
                                       method='DELETE')
        return resp.status == httplib.NO_CONTENT
