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

# Backward compatibility for Python 2.5
from __future__ import with_statement

import os
import os.path                          # pylint: disable-msg=W0404
import hashlib
from os.path import join as pjoin

from libcloud import utils
from libcloud.common.base import ConnectionUserAndKey
from libcloud.common.types import LibcloudError

class Entity(object):
    """
    Represents an entity to be monitored.
    """

    def __init__(self, id, name, extra, ip_addresses, driver):
        """
        @type name: C{str}
        @param name: Object name (must be unique per container).

        @type extra: C{dict}
        @param extra: Extra attributes.

        @type ip_addresses: C{list}
        @param ip_addresses: List of String aliases to IP Addresses tuples.

        @type driver: C{StorageDriver}
        @param driver: StorageDriver instance.
        """
        self.id = id
        self.name = name
        self.extra = extra or {}
        self.ip_addresses = ip_addresses or []
        self.driver = driver

    def delete(self):
        return self.driver.delete_entity(self)

    def __repr__(self):
        return ('<Object: id=%s name=%s provider=%s ...>' %
                (self.id, self.name, self.driver.name))


class Notification(object):
    def __init__(self, id, type, details):
        self.id = id
        self.type = type
        self.details = details

    def __repr__(self):
        return ('<Object: id=%s type=%s ...>' % (self.id, self.type))

class NotificationPlan(object):
    """
    Represents a notification plan.
    """
    def __init__(self, id, name, error_state, warning_state, ok_state):
        self.id = id
        self.name = name
        self.error_state = error_state
        self.warning_state = warning_state
        self.ok_state = ok_state

    def delete(self):
        return self.driver.delete_notification_plan(self)

    def __repr__(self):
        return ('<Object: id=%s ...>' % (self.id))

class MonitoringDriver(object):
    """
    A base MonitoringDriver to derive from.
    """

    connectionCls = ConnectionUserAndKey
    name = None

    def __init__(self, key, secret=None, secure=True, host=None, port=None):
        self.key = key
        self.secret = secret
        self.secure = secure
        args = [self.key]

        if self.secret != None:
            args.append(self.secret)

        args.append(secure)

        if host != None:
            args.append(host)

        if port != None:
            args.append(port)

        self.connection = self.connectionCls(*args, **self._ex_connection_class_kwargs())

        self.connection.driver = self
        self.connection.connect()

    def _ex_connection_class_kwargs(self):
        return {}

    def list_entities(self):
        raise NotImplementedError(
            'list_entities not implemented for this driver')
