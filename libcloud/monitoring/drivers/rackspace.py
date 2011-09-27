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
from libcloud.common.base import Response

from libcloud.monitoring.providers import Provider
from libcloud.monitoring.base import MonitoringDriver, Entity #, Check, Alarm

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
        if resp.status ==  httplib.NO_CONTENT:
            # location
            # /1.0/entities/enycekKZoN
            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')

            enId = location.rsplit('/')[-1]
            return self._read_entity(enId)
        else:
            raise LibcloudError('Unexpected status code: %s' % (response.status))

    def _read_entity(self, enId):
        resp = self.connection.request("/entities/%s" % (enId),
                                       method='GET')
        return self._to_entity(resp.object)

    def list_entities(self):
        response = self.connection.request('/entities')

        if response.status == httplib.NO_CONTENT:
            return []
        elif response.status == httplib.OK:
            return self._to_entity_list(json.loads(response.body))

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

    def _to_entity_list(self, response):
        # @TODO: Handle more then 10k containers - use "lazy list"?
        entities = []

        for entity in response:
            entities.append(self._to_entity(entity))
        return entities

    def list_check_types(self):
        resp = self.connection.request("/check_types",
                                       method='GET')
        print resp.object
        return resp.status == httplib.NO_CONTENT

    def list_monitoring_zones(self):
        resp = self.connection.request("/monitoring_zones",
                                       method='GET')
        print resp.object
        return resp.status == httplib.NO_CONTENT

    def list_checks(self, entity):
        resp = self.connection.request("/entities/%s/checks" % (entity.id),
                                       method='GET')
        print resp.object
        return resp.status == httplib.NO_CONTENT

    def _read_check(self, checkUrl):
        resp = self.connection.request(urlparse.urlparse(checkUrl).path,
                                       method='GET')
        print resp.object

        return resp.status == httplib.NO_CONTENT

    def create_check(self, entity, **kwargs):
        data = {'who': kwargs.get('who'),
                'why': kwargs.get('why'),
                'label': kwargs.get('name'),
                'timeout': kwargs.get('timeout', 29),
                'period': kwargs.get('period', 30),
                "mzones_poll": kwargs.get('monitoring_zones', []),
                "target_alias": kwargs.get('target_alias'),
                "target_resolver": kwargs.get('target_resolver'),
                'type': kwargs.get('type'),
                'details': kwargs.get('details'),
                }

        for k in data.keys():
            if data[k] == None:
                del data[k]

        resp = self.connection.request("/entities/%s/checks" % (entity.id),
                                       method='POST',
                                       data=data)
        if resp.status ==  httplib.NO_CONTENT:
            # location
            # /1.0/entities/enycekKZoN
            location = resp.headers.get('location')
            if not location:
                raise LibcloudError('Missing location header')

            return self._read_check(location)
        else:
            raise LibcloudError('Unexpected status code: %s' % (response.status))
