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

try:
    import simplejson as json
except:
    import json

from libcloud.common.types import MalformedResponseError, LibcloudError
from libcloud.common.types import LazyList
from libcloud.common.base import Response

from libcloud.monitoring.providers import Provider

from libcloud.monitoring.base import MonitoringDriver, Entity, NotificationPlan, \
                                     Notification, CheckType, Alarm, Check

from libcloud.common.rackspace import AUTH_URL_US
from libcloud.common.openstack import OpenStackBaseConnection

API_VERSION = '1.1'

class RackspaceMonitoringValidationError(LibcloudError):

    def __init__(self, code, type, message, details, driver):
        self.code = code
        self.type = type
        self.message = message
        self.details = details
        super(RackspaceMonitoringValidationError, self).__init__(value=message,
                                                                 driver=driver)

    def __str__(self):
        string = '<ValidationError type=%s, ' % (self.type)
        string += 'message="%s", details=%s>' % (self.message, self.details)
        return string

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

    def parse_error(self):
        body = self.parse_body()
        if self.status == httplib.BAD_REQUEST:
            error = RackspaceMonitoringValidationError(message=body['message'],
                                                       code=body['code'],
                                                       type=body['type'],
                                                       details=body['details'],
                                                       driver=self.connection.driver)
            return error

        return body


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

    def _get_more(self, last_key, value_dict):
        key = None

        params = value_dict.get('params', {})

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
            l = None

            if value_dict.has_key('list_item_mapper'):
                func = value_dict['list_item_mapper']
                l = [func(x, value_dict) for x in resp['values']]
            else:
                l = value_dict['object_mapper'](resp, value_dict)
            m = resp['metadata'].get('next_marker')
            return l, m, m == None

        raise LibcloudError('Unexpected status code: %s' % (response.status))

    def _plural_to_singular(self, name):
        kv = {'entities': 'entity',
              'alarms': 'alarm',
              'checks': 'check',
              'notifications': 'notification',
              'notification_plans': 'notificationPlan'}

        return kv[name]

    def _url_to_obj_ids(self, url):
        rv = {}
        rp = self.connection.request_path
        path = urlparse.urlparse(url).path

        if path.startswith(rp):
            # remove version string stuff
            path = path[len(rp):]

        chunks = path.split('/')[1:]

        for i in range(0, len(chunks), 2):
            key = self._plural_to_singular(chunks[i]) + "Id"
            rv[key] =  chunks[i+1]

        return rv;

    def _create(self, url, data, coerce):
        for k in data.keys():
            if data[k] == None:
                del data[k]

        resp = self.connection.request(url,
                                       method='POST',
                                       data=data)
        if resp.status ==  httplib.CREATED:
            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')
            objIds = self._url_to_obj_ids(location)
            return coerce(**objIds)
        else:
            raise LibcloudError('Unexpected status code: %s' % (resp.status))

    def _update(self, url, key, data, coerce):
        for k in data.keys():
            if data[k] == None:
                del data[k]

        resp = self.connection.request(url, method='PUT', data=data)
        if resp.status ==  httplib.NO_CONTENT:
            # location
            # /v1.0/{object_type}/{id}
            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')

            objIds = self._url_to_obj_ids(location)
            return coerce(**objIds)
        else:
            raise LibcloudError('Unexpected status code: %s' % (resp.status))

    def list_check_types(self):
        value_dict = { 'url': '/check_types',
                       'list_item_mapper': self._to_check_type}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def _to_check_type(self, obj, value_dict):
        return CheckType(id=obj['id'],
                         fields=obj.get('fields', []),
                         is_remote=obj.get('type') == 'remote')

    def list_monitoring_zones(self):
        resp = self.connection.request("/monitoring_zones",
                                       method='GET')
        return resp.status == httplib.NO_CONTENT

    #######
    ## Alarms
    #######
    def _read_alarm(self, entityId, alarmId):
        url = "/entities/%s/alarms/%s" % (entityId, alarmId)
        resp = self.connection.request(url)
        return self._to_alarm(resp.object, {'entity_id': entityId})

    def _to_alarm(self, alarm, value_dict):
        return Alarm(id=alarm['id'], type=alarm['check_type'],
            criteria=alarm['criteria'], notification_plan_id=alarm['notification_plan_id'],
            driver=self, entity_id=value_dict['entity_id'])

    def list_alarms(self, entity, ex_next_marker=None):
        value_dict = { 'url': '/entities/%s/alarms' % (entity.id),
                       'start_marker': ex_next_marker,
                       'list_item_mapper': self._to_alarm,
                       'entity_id': entity.id}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def get_alarm(self, entity, alarm):
        return self._read_alarm(entity.id, alarm.id)

    def delete_alarm(self, alarm):
        resp = self.connection.request("/entities/%s/alarms/%s" % (alarm.entity_id, alarm.id),
            method='DELETE')
        return resp.status == httplib.NO_CONTENT

    def update_alarm(self, entity, alarm):
        data = {'check_type': alarm.check_type,
                'criteria': alarm.criteria,
                'notification_plan_id': alarm.notification_plan_id }
        return self._update("/entities/%s/alarms/%s" % (alarm.entity_id, alarm.id),
            key=alarm.id, data=data, coerce=self._read_alarm)

    def create_alarm(self, entity, **kwargs):
        data = {'check_type': kwargs.get('check_type'),
                'criteria': kwargs.get('criteria'),
                'notification_plan_id': kwargs.get('notification_plan_id')}

        return self._create("/entities/%s/alarms" % (entity.id),
            data=data, coerce=self._read_alarm)

    def test_alarm(self, entity, **kwargs):
        data = {'criteria': kwargs.get('criteria'),
                'check_data': kwargs.get('check_data')}
        resp = self.connection.request("/entities/%s/test-alarm" % (entity.id),
                                       method='POST',
                                       data=data)
        return resp.object

    #######
    ## Notifications
    #######

    def list_notifications(self, ex_next_marker=None):
        value_dict = { 'url': '/notifications',
                       'start_marker': ex_next_marker,
                       'list_item_mapper': self._to_notification}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def _to_notification(self, noticiation, value_dict):
        return Notification(id=noticiation['id'], type=noticiation['type'], details=noticiation['details'], driver=self)

    def _read_notification(self, notificationId):
        resp = self.connection.request("/notifications/%s" % (notificationId))

        return self._to_notification(resp.object, {})

    def get_notification(self, notification):
        return self._read_notification(notification.id)

    def delete_notification(self, notification):
        resp = self.connection.request("/notifications/%s" % (notification.id),
                                       method='DELETE')
        return resp.status == httplib.NO_CONTENT

    def update_notification(self, notification):
        data = {'type': notification.type,
                'details': notification.details }

        return self._update("/notifications/%s" % (notification.id),
            key=notification.id, data=data, coerce=self._read_notification)

    def create_notification(self, **kwargs):
        data = {'type': kwargs.get('type'),
                'details': kwargs.get('details')}

        return self._create("/notifications", data=data, coerce=self._read_notification)

    #######
    ## Notification Plan
    #######

    def _to_notification_plan(self, notification_plan, value_dict):
        error_state = notification_plan.get('error_state', [])
        warning_state = notification_plan.get('warning_state', [])
        ok_state = notification_plan.get('ok_state', [])
        return NotificationPlan(id=notification_plan['id'], name=notification_plan['name'],
            error_state=error_state, warning_state=warning_state, ok_state=ok_state,
            driver=self)

    def _read_notification_plan(self, notificationPlanId):
        resp = self.connection.request("/notification_plans/%s" % (notificationPlanId))
        return self._to_notification_plan(resp.object, {})

    def delete_notification_plan(self, notification_plan):
        resp = self.connection.request("/notification_plans/%s" % (notification_plan.id), method='DELETE')
        return resp.status == httplib.NO_CONTENT

    def list_notification_plans(self, ex_next_marker=None):
        value_dict = { 'url': "/notification_plans",
                       'start_marker': ex_next_marker,
                       'list_item_mapper': self._to_notification_plan}
        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def update_notification_plan(self, notification_plan):
        data = {'name': notification_plan.name,
                'error_state': notification_plan.error_state,
                'warning_state': notification_plan.warning_state,
                'ok_state': notification_plan.ok_state
                }

        return self._update("/notification_plans/%s" % (notification_plan.id),
            id=notification_plan.id, data=data, coerce=self._read_notification_plan)

    def get_notification_plan(self, notification_plan):
        return self._read_notification_plan(notification_plan.id)

    def create_notification_plan(self, **kwargs):
        data = {'name': kwargs.get('name'),
                'error_state': kwargs.get('error_state', []),
                'warning_state': kwargs.get('warning_state', []),
                'ok_state': kwargs.get('ok_state', []),
                }
        return self._create("/notification_plans", data=data, coerce=self._read_notification_plan)

    #######
    ## Checks
    #######

    def _read_check(self, entityId, checkId):
        resp = self.connection.request('/entities/%s/checks/%s' % (entityId, checkId))
        return self._to_check(resp.object, {'entity_id': entityId})

    def _to_check(self, obj, value_dict):
        return Check(**{
            'id': obj['id'],
            'name': obj.get('label'),
            'timeout': obj['timeout'],
            'period': obj['period'],
            'monitoring_zones': obj['monitoring_zones_poll'],
            'target_alias': obj['target_alias'],
            'target_resolver': obj['target_resolver'],
            'type': obj['type'],
            'details': obj['details'],
            'driver': self,
            'entity_id': value_dict['entity_id']})

    def list_checks(self, entity, ex_next_marker=None):
        value_dict = { 'url': "/entities/%s/checks" % (entity.id),
                       'start_marker': ex_next_marker,
                       'list_item_mapper': self._to_check,
                       'entity_id': entity.id}
        return LazyList(get_more=self._get_more, value_dict=value_dict)


    def _check_kwarg_to_data(self, kwargs):
        data = {'who': kwargs.get('who'),
                'why': kwargs.get('why'),
                'label': kwargs.get('name'),
                'timeout': kwargs.get('timeout', 29),
                'period': kwargs.get('period', 30),
                "monitoring_zones_poll": kwargs.get('monitoring_zones', []),
                "target_alias": kwargs.get('target_alias'),
                "target_resolver": kwargs.get('target_resolver'),
                'type': kwargs.get('type'),
                'details': kwargs.get('details'),
                }

        for k in data.keys():
            if data[k] == None:
                del data[k]

        return data

    def test_check(self, entity, **kwargs):
        data = self._check_kwarg_to_data(kwargs)
        resp = self.connection.request("/entities/%s/test-check" % (entity.id),
                                       method='POST',
                                       data=data)
        # TODO: create native types
        return resp.object

    def create_check(self, entity, **kwargs):
        data = self._check_kwarg_to_data(kwargs)
        return self._create("/entities/%s/checks" % (entity.id),
            data=data, coerce=self._read_check)

    def delete_check(self, check):
        resp = self.connection.request("/entities/%s/checks/%s" %
                                       (check.entity_id, check.id),
                                       method='DELETE')
        return resp.status == httplib.NO_CONTENT

    #######
    ## Entity
    #######

    def _read_entity(self, entityId):
        resp = self.connection.request("/entities/%s" % (entityId))
        return self._to_entity(resp.object, {})

    def _to_entity(self, entity, value_dict):
        ips = []
        ipaddrs = entity.get('ip_addresses', {})
        for key in ipaddrs.keys():
            ips.append((key, ipaddrs[key]))
        return Entity(id=entity['id'], name=entity['label'], extra=entity['metadata'], driver=self, ip_addresses = ips)

    def delete_entity(self, entity):
        resp = self.connection.request("/entities/%s" % (entity.id),
                                       method='DELETE')
        return resp.status == httplib.NO_CONTENT

    def list_entities(self, ex_next_marker=None):
        value_dict = { 'url': '/entities',
                       'start_marker': ex_next_marker,
                       'list_item_mapper': self._to_entity}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    def create_entity(self, **kwargs):

        data = {'who': kwargs.get('who'),
                'why': kwargs.get('why'),
                'ip_addresses': kwargs.get('ip_addresses', {}),
                'label': kwargs.get('name'),
                'metadata': kwargs.get('extra', {})}

        return self._create("/entities", data=data, coerce=self._read_entity)

    def usage(self):
        resp = self.connection.request("/usage")
        return resp.object

    def _to_audit(self, audit, value_dict):
        # TODO: add class
        return audit

    def list_audits(self, start_from = None, to=None):
        # TODO: add start/end date support
        value_dict = { 'url': '/audits',
                       'params': {'limit': 200},
                       'list_item_mapper': self._to_audit}

        return LazyList(get_more=self._get_more, value_dict=value_dict)

    #######
    ## Other
    #######

    def test_check_and_alarm(self, entity, criteria, **kwargs):
        check_data = self.test_check(entity=entity, **kwargs)
        data = { 'criteria': criteria, 'check_data': check_data }
        result = self.test_alarm(entity=entity, **data)
        return result
