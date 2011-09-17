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

"""
Common utilities for OpenStack
"""
import httplib
from urllib2 import urlparse
from libcloud.common.base import ConnectionUserAndKey
from libcloud.compute.types import InvalidCredsError, MalformedResponseError

try:
    import simplejson as json
except ImportError:
    import json

AUTH_API_VERSION = 'v1.0'

__all__ = [
    "OpenStackBaseConnection",
    "OpenStackAuthDriver",
    ]

class OpenStackAuthConnection(ConnectionUserAndKey):

    name = 'OpenStack Auth'

    def __init__(self, auth_url, user_id, key):
        self.auth_url = auth_url
        self.urls = {}
        self.driver = self
        scheme, server, request_path, param, query, fragment = urlparse.urlparse(auth_url)

        super(OpenStackAuthConnection, self).__init__(
            user_id, key, url=auth_url)

    def add_default_headers(self, headers):
        headers['Accept'] = 'application/json'
        headers['Content-Type'] = 'application/json; charset=UTF-8'
        return headers

    def authenticate(self):
        """
        @TODO: error handling
                                             driver=self.driver)
        elif resp.status == httplib.UNAUTHORIZED:
            # HTTP UNAUTHORIZED (401): auth failed
            raise InvalidCredsError()
        else:
            # Any response code != 401 or 204, something is wrong
            raise MalformedResponseError('Malformed response',
                    body='code: %s body:%s' % (resp.status, ''.join(resp.body.readlines())),
                    driver=self.driver)

        """
        reqbody = json.dumps({'credentials': {'username': self.user_id, 'key': self.key}})
        resp = self.request("/auth",
                    data=reqbody,
                    headers={
                        'X-Auth-User': self.user_id,
                        'X-Auth-Key': self.key,
                    },
                    method='POST')

        if resp.status != httplib.OK:
            raise InvalidCredsError('Unexpected')
        else:
            try:
                body = json.loads(resp.body)
            except Exception, e:
                raise MalformedResponseError('Failed to parse JSON', e)
            
            self.auth_token = body['auth']['token']['id']
            self.urls = body['auth']['serviceCatalog']


class OpenStackBaseConnection(ConnectionUserAndKey):

    auth_host = None

    def __init__(self, user_id, key, secure, host=None, port=None):
        self.cdn_management_url = None
        self.storage_url = None
        self.auth_token = None
        if host is not None:
            self.auth_host = host
        if port is not None:
            self.port = (port, port)

        super(OpenStackBaseConnection, self).__init__(
            user_id, key, secure=secure)

    def add_default_headers(self, headers):
        headers['X-Auth-Token'] = self.auth_token
        headers['Accept'] = self.accept_format
        return headers

    @property
    def request_path(self):
        return self._get_request_path(url_key=self._url_key)

    @property
    def host(self):
        # Default to server_host
        return self._get_host(url_key=self._url_key)

    def _get_request_path(self, url_key):
        value_key = '__request_path_%s' % (url_key)
        value = getattr(self, value_key, None)

        if not value:
            self._populate_hosts_and_request_paths()
            value = getattr(self, value_key, None)

        return value

    def _get_host(self, url_key):
        value_key = '__%s' % (url_key)
        value = getattr(self, value_key, None)

        if not value:
            self._populate_hosts_and_request_paths()
            value = getattr(self, value_key, None)

        return value

    def _get_default_region(self, arr):
        if len(arr):
            for i in arr:
                if i.get('v1Default', False):
                    return i
            # uber lame
            return arr[0]
        return None

    def _populate_hosts_and_request_paths(self):
        """
        OpenStack uses a separate host for API calls which is only provided
        after an initial authentication request. If we haven't made that
        request yet, do it here. Otherwise, just return the management host.
        """
        if not self.auth_token:
            # TODO improve URL passing in all the lower level drivers
            auth_url = 'https://%s/v1.1/' % (self.auth_host)

            osa = OpenStackAuthConnection(auth_url, self.user_id, self.key)

            # may throw InvalidCreds, etc
            osa.authenticate()

            self.auth_token = osa.auth_token

            # TODO: Multi-region support
            self.server_url = self._get_default_region(osa.urls.get('cloudServers', []))
            self.cdn_management_url = self._get_default_region(osa.urls.get('cloudFilesCDN', []))
            self.storage_url = self._get_default_region(osa.urls.get('cloudFiles', []))
            # TODO: this is even more broken, the service catalog does NOT show load
            # balanacers :(  You must hard code in the Rackspace Load balancer URLs...
            self.lb_url = self.server_url.replace("servers", "ord.loadbalancers")

            for key in ['server_url', 'storage_url', 'cdn_management_url',
                        'lb_url']:
                scheme, server, request_path, param, query, fragment = (
                    urlparse.urlparse(getattr(self, key)))
                # Set host to where we want to make further requests to
                setattr(self, '__%s' % (key), server)
                setattr(self, '__request_path_%s' % (key), request_path)
