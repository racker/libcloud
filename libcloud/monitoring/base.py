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

    def __init__(self, id, name, ip_addresses, driver, extra=None):
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
    def __init__(self, id, type, details, driver=None):
        self.id = id
        self.type = type
        self.details = details
        self.driver = driver

    def delete(self):
        return self.driver.delete_notification(self)

    def __repr__(self):
        return ('<Notification: id=%s type=%s ...>' % (self.id, self.type))

class NotificationPlan(object):
    """
    Represents a notification plan.
    """
    def __init__(self, id, name, driver, error_state=None, warning_state=None, ok_state=None):
        self.id = id
        self.name = name
        self.error_state = error_state
        self.warning_state = warning_state
        self.ok_state = ok_state
        self.driver = driver

    def delete(self):
        return self.driver.delete_notification_plan(self)

    def __repr__(self):
        return ('<NotificationPlan: id=%s...>' % (self.id))

class CheckType(object):
    def __init__(self, id, fields, is_remote):
        self.id = id
        self.is_remote = is_remote
        self.fields = fields

    def __repr__(self):
        return ('<CheckType: id=%s ...>' % (self.id))


class Alarm(object):
    def __init__(self, id, type, criteria, driver, entity_id, notification_plan_id=None):
        self.id = id
        self.type = type
        self.criteria = criteria
        self.driver = driver
        self.notification_plan_id = notification_plan_id
        self.entity_id = entity_id

    def delete(self):
        return self.driver.delete_alarm(self)

    def __repr__(self):
        return ('<Alarm: id=%s ...>' % (self.id))

class Check(object):
    def __init__(self, id, name, timeout, period, monitoring_zones, target_alias, target_resolver, type, details, entity_id, driver):
        self.id = id
        self.name = name
        self.timeout = timeout
        self.period = period
        self.monitoring_zones = monitoring_zones
        self.target_alias = target_alias
        self.target_resolver = target_resolver
        self.type = type
        self.details = details
        self.entity_id = entity_id
        self.driver = driver

    def __repr__(self):
        return ('<Check: id=%s name=%s...>' % (self.id, self.name))

    def delete(self):
        return self.driver.delete_check(self)

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

    def list_checks(self):
        raise NotImplementedError(
            'list_checks not implemented for this driver')

    def list_check_types(self):
        raise NotImplementedError(
            'list_check_types not implemented for this driver')

    def list_monitoring_zones(self):
        raise NotImplementedError(
            'list_monitoring_zones not implemented for this driver')

    def list_notifications(self):
        raise NotImplementedError(
            'list_notifications not implemented for this driver')

    def list_notification_plans(self):
        raise NotImplementedError(
            'list_notification_plans not implemented for this driver')

    def delete_entity(self):
        raise NotImplementedError(
            'delete_entity not implemented for this driver')

    def delete_notification(self, notification):
        raise NotImplementedError(
            'delete_notification not implemented for this driver')

    def delete_notification_plan(self, notification):
        raise NotImplementedError(
            'delete_notification_plan not implemented for this driver')

    def create_check(self, notification):
        raise NotImplementedError(
            'create_check not implemented for this driver')

    def create_entity(self, notification):
        raise NotImplementedError(
            'create_entity not implemented for this driver')

    def create_notification(self, notification):
        raise NotImplementedError(
            'create_notification not implemented for this driver')

    def create_notification_plan(self, notification):
        raise NotImplementedError(
            'create_notification_plan not implemented for this driver')
